from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, g
from flask_cors import CORS
from flask_security import Security, SQLAlchemyUserDatastore, login_required, roles_required, current_user, hash_password
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
import os
import json
import secrets
from werkzeug.utils import secure_filename
from datetime import datetime
from app.agents.agent import generate_reply

from app.config.knowledge_config import (
    load_knowledge_config, add_knowledge_base, remove_knowledge_base, 
    get_active_knowledge_bases, update_embedding_status,
    save_knowledge_config, cleanup_orphaned_kb_references
)
from app.utils.knowledge_processor import process_knowledge_base
from app.api.agent_api import AgentAPI
from app.models.chat_session import chat_session_manager
from app.models.user import db, User, Role
from app.models.audit_log import AuditLog

app = Flask(__name__)

# Generate secure secret keys (persistent across restarts)
def get_or_create_secret(filename, key_name):
    """Get or create a persistent secret key"""
    secret_file = os.path.join(os.path.dirname(__file__), '..', 'config', filename)
    if os.path.exists(secret_file):
        with open(secret_file, 'r') as f:
            return f.read().strip()
    else:
        secret = secrets.token_hex(32)
        with open(secret_file, 'w') as f:
            f.write(secret)
        return secret

app.secret_key = os.environ.get('SECRET_KEY', get_or_create_secret('.secret_key', 'SECRET_KEY'))
app.config['SECURITY_PASSWORD_SALT'] = os.environ.get('SECURITY_PASSWORD_SALT', get_or_create_secret('.password_salt', 'SECURITY_PASSWORD_SALT'))

# Database configuration
# Calculate absolute path to app/config/users.db
basedir = os.path.abspath(os.path.dirname(__file__))  # Gets app/web/
config_dir = os.path.join(basedir, '..', 'config')     # Gets app/config/
os.makedirs(config_dir, exist_ok=True)                 # Ensure directory exists
db_path = os.path.join(config_dir, 'users.db')         # Full path to users.db

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Flask-Security configuration
app.config['SECURITY_PASSWORD_HASH'] = 'argon2'
app.config['SECURITY_REGISTERABLE'] = False  # No public registration
app.config['SECURITY_RECOVERABLE'] = False  # Admin-only password reset
app.config['SECURITY_TRACKABLE'] = True  # Track login time/IP
app.config['SECURITY_CHANGEABLE'] = True  # Allow password changes
app.config['SECURITY_SEND_REGISTER_EMAIL'] = False
app.config['SECURITY_SEND_PASSWORD_CHANGE_EMAIL'] = False
app.config['SECURITY_SEND_PASSWORD_RESET_EMAIL'] = False

# Session security
app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True  # XSS protection
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection

# Upload configuration
app.config['UPLOAD_FOLDER'] = 'app/knowledge_bases'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Configure ProxyFix for reverse proxy
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,      # X-Forwarded-For
    x_proto=1,    # X-Forwarded-Proto (HTTP/HTTPS)
    x_host=1,     # X-Forwarded-Host
    x_prefix=1    # X-Forwarded-Prefix
)

# Initialize database
db.init_app(app)

# Setup Flask-Security
user_datastore = SQLAlchemyUserDatastore(db, User, Role)
security = Security(app, user_datastore)

# Account lockout - Reset counter on successful authentication
from flask_security.signals import user_authenticated

@user_authenticated.connect_via(app)
def on_user_authenticated(sender, user, **extra):
    """Reset failed login count on successful authentication"""
    user.reset_failed_login()
    db.session.commit()

@app.before_request
def check_account_lockout():
    """Check if account is locked and track failed attempts"""
    if request.endpoint == 'security.login' and request.method == 'POST':
        email = request.form.get('email')
        if email:
            user = user_datastore.find_user(email=email)
            if user:
                # Check if account is locked
                if user.is_locked():
                    minutes_left = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
                    if minutes_left > 0:
                        flash(f"Account locked. Try again in {minutes_left} minutes.", "error")
                        return redirect(url_for('security.login'))
                    else:
                        # Lock expired, reset it
                        user.locked_until = None
                        user.failed_login_count = 0
                        db.session.commit()

@app.after_request
def track_failed_login(response):
    """Track failed login attempts after authentication"""
    if request.endpoint == 'security.login' and request.method == 'POST':
        email = request.form.get('email')
        # If not authenticated after POST to login, it failed
        if email and not current_user.is_authenticated:
            user = user_datastore.find_user(email=email)
            if user and not user.is_locked():
                user.increment_failed_login()
                db.session.commit()
                
                if user.is_locked():
                    flash("Too many failed attempts. Account locked for 15 minutes.", "error")
    
    return response

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200 per day", "50 per hour"]
)

# Enable CORS for external embedding (quiz widgets remain public)
CORS(app, resources={
    r"/api/chat/*": {"origins": "*"},
    r"/embed/*": {"origins": "*"},
    r"/api/quiz/*": {"origins": "*"},
    r"/quiz/*": {"origins": "*"}
})

# First-run setup: Create tables and default admin user
def create_initial_setup():
    """Create database tables and default admin user on first run"""
    # Create all tables
    db.create_all()
    
    # Create roles if they don't exist
    if not user_datastore.find_role('admin'):
        user_datastore.create_role(name='admin', description='Administrator')
    if not user_datastore.find_role('user'):
        user_datastore.create_role(name='user', description='Regular User')
    
    # Create default admin if no users exist
    if not user_datastore.find_user(email='admin@example.com'):
        admin_password = secrets.token_urlsafe(16)
        user_datastore.create_user(
            email='admin@example.com',
            password=hash_password(admin_password),
            active=True,
            roles=['admin'],
            fs_uniquifier=secrets.token_urlsafe(32)
        )
        db.session.commit()
        
        print("\n" + "="*60)
        print("INITIAL ADMIN ACCOUNT CREATED")
        print("="*60)
        print(f"Email:    admin@example.com")
        print(f"Password: {admin_password}")
        print("="*60)
        print("PLEASE SAVE THESE CREDENTIALS AND CHANGE PASSWORD IMMEDIATELY")
        print("="*60 + "\n")

# Initialize database on first request (Flask 3.x pattern)
_db_initialized = False

@app.before_request
def initialize_database_once():
    """Initialize database on first request (Flask 3.x pattern)"""
    global _db_initialized
    if not _db_initialized:
        # Check if database is already initialized by checking if tables exist
        try:
            # Try to query users table - if it works, DB is initialized
            User.query.first()
            _db_initialized = True
        except:
            # Database not initialized, create it
            create_initial_setup()
            _db_initialized = True

# Global template context processor to check API key status and inject user
@app.context_processor
def inject_context():
    """Inject API key status and current user into all templates"""
    try:
        from app.config.api_config import get_api_key_info
        api_info = get_api_key_info()
        return {
            'api_key_has_key': api_info.get('has_key', False),
            'api_key_status': api_info.get('test_status', 'unknown'),
            'current_user': current_user
        }
    except:
        return {
            'api_key_has_key': False,
            'api_key_status': 'unknown',
            'current_user': current_user
        }

ALLOWED_EXTENSIONS = {'pdf', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
@login_required
def home():
    # Load agents for chat interface
    from app.api.agent_api import AgentAPI
    from app.config.model_config import get_current_model
    from app.config.knowledge_config import load_knowledge_config
    
    agents_result = AgentAPI.get_active_agents()
    agents = agents_result.get("agents", []) if agents_result["success"] else []
    
    # Get stats for system overview
    current_model = get_current_model()
    kb_config = load_knowledge_config()
    kb_count = len([kb for kb in kb_config.get('knowledge_bases', []) if kb.get('status') == 'active'])
    
    return render_template("test.html", 
                         agents=agents,
                         current_model=current_model,
                         kb_count=kb_count)

@app.route("/agents", methods=["GET", "POST"])
@login_required
def agents():
    # Clean up any orphaned knowledge base references
    cleanup_orphaned_kb_references()
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "create":
            # Get selected knowledge bases
            selected_kbs = request.form.getlist("knowledge_bases")
            
            # Get provider selection
            provider = request.form.get("provider", "openai")
            provider_model = request.form.get("provider_model", "gpt-5.2")
            
            # Get model parameters (with defaults)
            model = request.form.get("model", "gpt-5.2")
            temperature = float(request.form.get("temperature", 0.9))
            frequency_penalty = float(request.form.get("frequency_penalty", 0.7))
            presence_penalty = float(request.form.get("presence_penalty", 0.5))
            max_tokens = int(request.form.get("max_tokens", 1000))
            top_p_str = request.form.get("top_p", "")
            top_p = float(top_p_str) if top_p_str else None
            
            # Get model-specific parameters
            max_completion_tokens_str = request.form.get("max_completion_tokens", "")
            max_completion_tokens = int(max_completion_tokens_str) if max_completion_tokens_str else None
            
            max_output_tokens_str = request.form.get("max_output_tokens", "")
            max_output_tokens = int(max_output_tokens_str) if max_output_tokens_str else None
            
            reasoning_effort = request.form.get("reasoning_effort", "")
            reasoning_effort = reasoning_effort if reasoning_effort else None
            
            verbosity = request.form.get("verbosity", "")
            verbosity = verbosity if verbosity else None
            
            stop_str = request.form.get("stop", "")
            stop = stop_str.split(",") if stop_str else None
            
            # Get knowledge base search parameters
            max_knowledge_chunks_str = request.form.get("max_knowledge_chunks", "7")
            max_knowledge_chunks = int(max_knowledge_chunks_str) if max_knowledge_chunks_str else 7
            
            min_similarity_threshold_str = request.form.get("min_similarity_threshold", "1.0")
            min_similarity_threshold = float(min_similarity_threshold_str) if min_similarity_threshold_str else 1.0
            
            conversation_history_tokens_str = request.form.get("conversation_history_tokens", "1000")
            conversation_history_tokens = int(conversation_history_tokens_str) if conversation_history_tokens_str else 1000
            
            # Get post-processing rules from form
            post_processing_rules = {}
            if request.form.get("trim_preamble") == "on":
                post_processing_rules["trim_preamble"] = True
            if request.form.get("trim_signoff") == "on":
                post_processing_rules["trim_signoff"] = True
            if request.form.get("remove_disclaimers") == "on":
                post_processing_rules["remove_disclaimers"] = True
            if request.form.get("strip_markdown") == "on":
                post_processing_rules["strip_markdown"] = True
            
            enforce_format = request.form.get("enforce_format", "")
            if enforce_format:
                post_processing_rules["enforce_format"] = enforce_format
            
            validation = request.form.get("validation", "")
            if validation:
                post_processing_rules["validation"] = validation
            
            max_sentences_str = request.form.get("max_sentences", "")
            if max_sentences_str:
                try:
                    post_processing_rules["max_sentences"] = int(max_sentences_str)
                except ValueError:
                    pass
            
            # Get semantic detection settings
            enable_semantic = request.form.get("enable_semantic_detection") == "on"
            semantic_threshold_str = request.form.get("semantic_similarity_threshold", "0.90")
            semantic_depth_str = request.form.get("semantic_history_depth", "5")
            
            # Get exam profile settings
            exam_profile_id = request.form.get("exam_profile_id", "").strip()
            exam_profile_id = exam_profile_id if exam_profile_id and exam_profile_id != "none" else None
            blueprint_depth_str = request.form.get("blueprint_history_depth", "8")
            blueprint_depth = int(blueprint_depth_str) if blueprint_depth_str else 8
            
            # Create new agent
            result = AgentAPI.create_agent(
                name=request.form.get("name", "").strip(),
                personality=request.form.get("personality", "").strip(),
                style=request.form.get("style", "").strip(),
                prompt=request.form.get("prompt", "").strip(),
                formatting=request.form.get("formatting", "").strip(),
                knowledge_bases=selected_kbs,
                provider=provider,
                provider_model=provider_model,
                model=model,
                temperature=temperature,
                frequency_penalty=frequency_penalty,
                presence_penalty=presence_penalty,
                max_tokens=max_tokens,
                top_p=top_p,
                max_completion_tokens=max_completion_tokens,
                max_output_tokens=max_output_tokens,
                reasoning_effort=reasoning_effort,
                verbosity=verbosity,
                stop=stop,
                max_knowledge_chunks=max_knowledge_chunks,
                min_similarity_threshold=min_similarity_threshold,
                conversation_history_tokens=conversation_history_tokens,
                post_processing_rules=post_processing_rules,
                enable_semantic_detection=enable_semantic,
                semantic_similarity_threshold=float(semantic_threshold_str) if semantic_threshold_str else 0.90,
                semantic_history_depth=int(semantic_depth_str) if semantic_depth_str else 5,
                exam_profile_id=exam_profile_id,
                blueprint_history_depth=blueprint_depth
            )
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "update":
            # Get selected knowledge bases
            selected_kbs = request.form.getlist("knowledge_bases")
            
            # Get provider selection
            provider = request.form.get("provider", "")
            provider_model = request.form.get("provider_model", "")
            
            # Get model parameters
            model = request.form.get("model", "")
            temperature_str = request.form.get("temperature", "")
            frequency_penalty_str = request.form.get("frequency_penalty", "")
            presence_penalty_str = request.form.get("presence_penalty", "")
            max_tokens_str = request.form.get("max_tokens", "")
            top_p_str = request.form.get("top_p", "")
            
            # Get model-specific parameters
            max_completion_tokens_str = request.form.get("max_completion_tokens", "")
            max_output_tokens_str = request.form.get("max_output_tokens", "")
            reasoning_effort = request.form.get("reasoning_effort", "")
            verbosity = request.form.get("verbosity", "")
            stop_str = request.form.get("stop", "")
            
            # Get knowledge base search parameters
            max_knowledge_chunks_str = request.form.get("max_knowledge_chunks", "")
            min_similarity_threshold_str = request.form.get("min_similarity_threshold", "")
            conversation_history_tokens_str = request.form.get("conversation_history_tokens", "")
            
            # Get post-processing rules from form
            post_processing_rules = {}
            if request.form.get("trim_preamble") == "on":
                post_processing_rules["trim_preamble"] = True
            if request.form.get("trim_signoff") == "on":
                post_processing_rules["trim_signoff"] = True
            if request.form.get("remove_disclaimers") == "on":
                post_processing_rules["remove_disclaimers"] = True
            if request.form.get("strip_markdown") == "on":
                post_processing_rules["strip_markdown"] = True
            
            enforce_format = request.form.get("enforce_format", "")
            if enforce_format:
                post_processing_rules["enforce_format"] = enforce_format
            
            validation = request.form.get("validation", "")
            if validation:
                post_processing_rules["validation"] = validation
            
            max_sentences_str = request.form.get("max_sentences", "")
            if max_sentences_str:
                try:
                    post_processing_rules["max_sentences"] = int(max_sentences_str)
                except ValueError:
                    pass
            
            # Get semantic detection settings
            enable_semantic = request.form.get("enable_semantic_detection") == "on"
            semantic_threshold_str = request.form.get("semantic_similarity_threshold", "")
            semantic_depth_str = request.form.get("semantic_history_depth", "")
            
            # Get exam profile settings
            exam_profile_id = request.form.get("exam_profile_id", "").strip()
            exam_profile_id = exam_profile_id if exam_profile_id and exam_profile_id != "none" else None
            blueprint_depth_str = request.form.get("blueprint_history_depth", "")
            
            # Convert to appropriate types (explicitly handle empty values as None)
            update_params = {
                "name": request.form.get("name", "").strip(),
                "personality": request.form.get("personality", "").strip(),
                "style": request.form.get("style", "").strip(),
                "prompt": request.form.get("prompt", "").strip(),
                "formatting": request.form.get("formatting", "").strip(),
                "status": request.form.get("status"),
                "knowledge_bases": selected_kbs,
                # Provider selection
                "provider": provider if provider else None,
                "provider_model": provider_model if provider_model else None,
                # Model parameters - all explicitly set to allow clearing (except model which is required)
                "temperature": float(temperature_str) if temperature_str else None,
                "frequency_penalty": float(frequency_penalty_str) if frequency_penalty_str else None,
                "presence_penalty": float(presence_penalty_str) if presence_penalty_str else None,
                "max_tokens": int(max_tokens_str) if max_tokens_str else None,
                "top_p": float(top_p_str) if top_p_str else None,
                # Model-specific parameters
                "max_completion_tokens": int(max_completion_tokens_str) if max_completion_tokens_str else None,
                "max_output_tokens": int(max_output_tokens_str) if max_output_tokens_str else None,
                "reasoning_effort": reasoning_effort if reasoning_effort else None,
                "verbosity": verbosity if verbosity else None,
                "stop": stop_str.split(",") if stop_str else None,
                # Knowledge base search parameters
                "max_knowledge_chunks": int(max_knowledge_chunks_str) if max_knowledge_chunks_str else None,
                "min_similarity_threshold": float(min_similarity_threshold_str) if min_similarity_threshold_str else None,
                "conversation_history_tokens": int(conversation_history_tokens_str) if conversation_history_tokens_str else None,
                # Post-processing rules
                "post_processing_rules": post_processing_rules if post_processing_rules else None,
                # Semantic detection
                "enable_semantic_detection": enable_semantic,
                "semantic_similarity_threshold": float(semantic_threshold_str) if semantic_threshold_str else None,
                "semantic_history_depth": int(semantic_depth_str) if semantic_depth_str else None,
                # Exam profile settings
                "exam_profile_id": exam_profile_id,
                "blueprint_history_depth": int(blueprint_depth_str) if blueprint_depth_str else None
            }
            
            # Add model only if specified (required field, shouldn't be cleared)
            if model:
                update_params["model"] = model
            
            # Update existing agent
            agent_id = request.form.get("agent_id")
            result = AgentAPI.update_agent(agent_id, **update_params)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "delete":
            # Delete agent
            agent_id = request.form.get("agent_id")
            result = AgentAPI.delete_agent(agent_id)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "clone":
            # Clone agent
            agent_id = request.form.get("agent_id")
            new_name = request.form.get("new_name", "").strip()
            result = AgentAPI.clone_agent(agent_id, new_name)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        return redirect(url_for('agents'))
    
    # GET request - show agents
    result = AgentAPI.get_all_agents()
    agents_data = result.get("agents", []) if result["success"] else []
    
    # Get knowledge bases for the interface
    knowledge_bases = get_active_knowledge_bases()
    
    # Get exam profiles for the interface
    from app.config.exam_profile_config import get_all_profiles
    exam_profiles = get_all_profiles()
    
    return render_template("agents.html", agents=agents_data, knowledge_bases=knowledge_bases, exam_profiles=exam_profiles)





@app.route("/knowledge_bases", methods=["GET", "POST"])
@login_required
def knowledge_bases():
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload or URL source
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            access_type = request.form.get('access_type', 'shared')
            source_type = request.form.get('source_type', 'file')
            
            # Get exam profile and metadata
            exam_profile_ids = request.form.getlist('exam_profile_ids')  # Get multiple profile IDs
            exam_profile_ids = [pid.strip() for pid in exam_profile_ids if pid.strip()]  # Clean up
            cissp_type = request.form.get('cissp_type', '').strip() or None
            cissp_domain = request.form.get('cissp_domain', '').strip() or None
            is_priority_kb = request.form.get('is_priority_kb') == 'on'
            
            # Get embedding provider
            embedding_provider = request.form.get('embedding_provider', 'openai')
            
            if not title:
                flash('Title is required', 'error')
                return redirect(request.url)
            
            try:
                if source_type == 'url':
                    # Handle URL source
                    source_url = request.form.get('source_url', '').strip()
                    if not source_url:
                        flash('Source URL is required', 'error')
                        return redirect(request.url)
                    
                    # Add to knowledge base configuration
                    kb_id = add_knowledge_base(
                        title=title,
                        description=description,
                        kb_type="url",
                        source=source_url,
                        access_type=access_type,
                        category="general",
                        exam_profile_ids=exam_profile_ids,
                        profile_type=cissp_type,
                        profile_domain=cissp_domain,
                        is_priority_kb=is_priority_kb,
                        embedding_provider=embedding_provider
                    )
                    
                    # Process the knowledge base
                    from app.utils.knowledge_processor import process_knowledge_base
                    update_embedding_status(kb_id, "processing")
                    
                    # Generate AI summary if description is empty
                    generate_summary = not description.strip()
                    success, ai_summary = process_knowledge_base(kb_id, "url", source_url, generate_summary=generate_summary, 
                                                                 embedding_provider=embedding_provider)
                    
                    if success:
                        update_embedding_status(kb_id, "completed")
                        
                        # Update description with AI summary if generated
                        if ai_summary and generate_summary:
                            config = load_knowledge_config()
                            for kb in config.get('knowledge_bases', []):
                                if kb.get('id') == kb_id:
                                    kb['description'] = ai_summary
                                    break
                            save_knowledge_config(config)
                        
                        flash(f'Knowledge base "{title}" added and processed successfully!', 'success')
                    else:
                        update_embedding_status(kb_id, "failed")
                        flash(f'Knowledge base "{title}" added but processing failed', 'warning')
                    
                else:
                    # Handle file upload
                    if 'file' not in request.files:
                        flash('No file selected', 'error')
                        return redirect(request.url)
                    
                    file = request.files['file']
                    if file.filename == '':
                        flash('No file selected', 'error')
                        return redirect(request.url)
                    
                    # Save uploaded file
                    filename = secure_filename(file.filename)
                    upload_path = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases", filename)
                    os.makedirs(os.path.dirname(upload_path), exist_ok=True)
                    file.save(upload_path)
                    
                    # Add to knowledge base
                    kb_id = add_knowledge_base(
                        title=title,
                        description=description,
                        kb_type="document",
                        source=upload_path,
                        access_type=access_type,
                        category="general",
                        exam_profile_ids=exam_profile_ids,
                        profile_type=cissp_type,
                        profile_domain=cissp_domain,
                        is_priority_kb=is_priority_kb,
                        embedding_provider=embedding_provider
                    )
                    
                    # Process the knowledge base
                    from app.utils.knowledge_processor import process_knowledge_base
                    update_embedding_status(kb_id, "processing")
                    
                    # Generate AI summary if description is empty
                    generate_summary = not description.strip()
                    success, ai_summary = process_knowledge_base(kb_id, "file", upload_path, generate_summary=generate_summary,
                                                                 embedding_provider=embedding_provider)
                    
                    if success:
                        update_embedding_status(kb_id, "completed")
                        
                        # Update description with AI summary if generated
                        if ai_summary and generate_summary:
                            config = load_knowledge_config()
                            for kb in config.get('knowledge_bases', []):
                                if kb.get('id') == kb_id:
                                    kb['description'] = ai_summary
                                    break
                            save_knowledge_config(config)
                        
                        flash(f'Knowledge base "{title}" uploaded and processed successfully!', 'success')
                    else:
                        update_embedding_status(kb_id, "failed")
                        flash(f'Knowledge base "{title}" uploaded but processing failed', 'warning')
                    
            except Exception as e:
                flash(f'Error processing knowledge base: {str(e)}', 'error')
        
        elif action == "edit":
            # Handle knowledge base edit
            kb_id = request.form.get('kb_id')
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            access_type = request.form.get('access_type', 'shared')
            new_embedding_provider = request.form.get('embedding_provider', 'openai')
            
            # Get updated profile assignments
            exam_profile_ids = request.form.getlist('exam_profile_ids')
            exam_profile_ids = [pid.strip() for pid in exam_profile_ids if pid.strip()]
            
            if kb_id and title:
                # Update knowledge base properties
                config = load_knowledge_config()
                kb_found = False
                for kb in config.get('knowledge_bases', []):
                    if kb.get('id') == kb_id:
                        old_embedding_provider = kb.get('embedding_provider', 'openai')
                        
                        update_data = {
                            'title': title,
                            'description': description,
                            'category': 'general',  # Fixed default
                            'access_type': access_type,
                            'embedding_provider': new_embedding_provider,
                            'exam_profile_ids': exam_profile_ids
                        }
                        
                        kb.update(update_data)
                        kb_found = True
                        
                        # If embedding provider changed, trigger reprocess
                        if new_embedding_provider != old_embedding_provider:
                            save_knowledge_config(config)
                            flash(f'Embedding provider changed to {new_embedding_provider}. Reprocessing knowledge base...', 'info')
                            # Trigger reprocess with new provider
                            from app.utils.knowledge_processor import process_knowledge_base
                            try:
                                process_knowledge_base(
                                    kb_id=kb_id,
                                    kb_type=kb.get('type'),
                                    source=kb.get('source'),
                                    embedding_provider=new_embedding_provider
                                )
                                flash('Knowledge base reprocessed successfully', 'success')
                            except Exception as e:
                                flash(f'Reprocessing failed: {str(e)}', 'error')
                        
                        break
                
                if kb_found:
                    save_knowledge_config(config)
                    if new_embedding_provider == old_embedding_provider:
                        flash(f'Knowledge base "{title}" updated successfully!', 'success')
                else:
                    flash('Knowledge base not found', 'error')
            else:
                flash('Title is required', 'error')
        
        elif action == "delete":
            # Handle knowledge base deletion
            kb_id = request.form.get('kb_id')
            if kb_id:
                if remove_knowledge_base(kb_id):
                    flash('Knowledge base deleted successfully!', 'success')
                else:
                    flash('Failed to delete knowledge base', 'error')
        
        elif action == "reprocess":
            # Handle knowledge base reprocessing
            kb_id = request.form.get('kb_id')
            if kb_id:
                config = load_knowledge_config()
                kb_info = None
                for kb in config.get('knowledge_bases', []):
                    if kb.get('id') == kb_id:
                        kb_info = kb
                        break
                
                if kb_info:
                    try:
                        from app.utils.knowledge_processor import process_knowledge_base
                        kb_type = kb_info.get('type', 'document')
                        # Convert 'document' to 'file' for the processor
                        processor_type = "file" if kb_type == "document" else kb_type
                        success, _ = process_knowledge_base(kb_id, processor_type, kb_info['source'])
                        if success:
                            flash('Knowledge base reprocessed successfully!', 'success')
                        else:
                            flash('Knowledge base reprocessing failed!', 'error')
                    except Exception as e:
                        flash(f'Error reprocessing knowledge base: {str(e)}', 'error')
                else:
                    flash('Knowledge base not found', 'error')
        
        return redirect(url_for('knowledge_bases'))
    
    # GET request - show knowledge bases
    from app.models.agent import agent_manager
    
    # Get all knowledge bases with enhanced info
    knowledge_bases = []
    config = load_knowledge_config()
    
    for kb_info in config.get('knowledge_bases', []):
        kb_id = kb_info.get('id')
        
        # Get assigned agents for this KB
        assigned_agents = []
        for agent in agent_manager.get_all_agents():
            if kb_id in agent.knowledge_bases:
                assigned_agents.append(agent.name)
        
        # Count chunks if available
        chunks_count = None
        base_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases", kb_id)
        chunks_path = os.path.join(base_dir, "chunks.pkl.gz")
        if not os.path.exists(chunks_path):
            chunks_path = os.path.join(base_dir, "chunks.pkl")
        if os.path.exists(chunks_path):
            try:
                import pickle
                import gzip
                if chunks_path.endswith(".gz"):
                    with gzip.open(chunks_path, 'rb') as f:
                        chunks = pickle.load(f)
                else:
                    with open(chunks_path, 'rb') as f:
                        chunks = pickle.load(f)
                    chunks_count = len(chunks)
            except:
                pass
        
        # Get profile names from IDs
        exam_profile_ids = kb_info.get('exam_profile_ids', [])
        # Backward compatibility: check for old exam_profile_id field
        if not exam_profile_ids and kb_info.get('exam_profile_id'):
            exam_profile_ids = [kb_info.get('exam_profile_id')]
        
        knowledge_bases.append({
            'id': kb_id,
            'title': kb_info.get('title', 'Untitled'),
            'description': kb_info.get('description', ''),
            'access_type': kb_info.get('access_type', 'shared'),
            'status': kb_info.get('status', 'active'),
            'kb_type': kb_info.get('type', 'document'),  # Note: 'type' not 'kb_type' in the config
            'created_at': kb_info.get('created_at', ''),
            'assigned_agents': assigned_agents,
            'chunks_count': chunks_count,
            'cissp_type': kb_info.get('cissp_type'),
            'cissp_domain': kb_info.get('cissp_domain'),
            'profile_type': kb_info.get('profile_type'),
            'profile_domain': kb_info.get('profile_domain'),
            'is_priority_kb': kb_info.get('is_priority_kb', False),
            'embedding_provider': kb_info.get('embedding_provider', 'openai'),
            'exam_profile_ids': exam_profile_ids
        })
    
    # Sort by creation date (newest first)
    knowledge_bases.sort(key=lambda x: x['created_at'], reverse=True)
    
    
    # Get exam profiles for the dropdown
    from app.config.exam_profile_config import get_all_profiles
    exam_profiles = get_all_profiles()
    
    return render_template("knowledge_bases.html", 
                         knowledge_bases=knowledge_bases,
                         exam_profiles=exam_profiles)

@app.route("/api/knowledge_bases/<kb_id>/export", methods=["GET"])
@login_required
def export_kb_api(kb_id):
    """Export knowledge base as downloadable ZIP"""
    from app.config.knowledge_config import export_knowledge_base
    from flask import Response
    
    # Get include_embeddings from query param
    include_embeddings = request.args.get('include_embeddings', 'true').lower() == 'true'
    
    success, message, zip_bytes = export_knowledge_base(kb_id, include_embeddings)
    
    if not success:
        return jsonify({"error": message}), 404
    
    # Get KB title for filename
    config = load_knowledge_config()
    kb_title = "knowledge_base"
    for kb in config.get("knowledge_bases", []):
        if kb.get("id") == kb_id:
            kb_title = kb.get("title", "knowledge_base")
            break
    
    # Sanitize filename
    safe_name = "".join(c for c in kb_title if c.isalnum() or c in (' ', '_', '-')).strip()
    safe_name = safe_name.replace(' ', '_').lower()
    
    response = Response(zip_bytes, mimetype='application/zip')
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_name}_kb.zip"'
    
    return response

@app.route("/api/knowledge_bases/import", methods=["POST"])
@login_required
def import_kb_api():
    """Import knowledge base from ZIP package"""
    from app.config.knowledge_config import import_knowledge_base
    
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.zip'):
        return jsonify({"error": "File must be a ZIP file"}), 400
    
    # Get user's current embedding provider from settings or default to openai
    user_provider = "openai"  # Default, will be enhanced later with user preference detection
    
    success, message, warnings, new_kb_id = import_knowledge_base(file, user_provider)
    
    if success:
        return jsonify({
            "success": True,
            "message": message,
            "warnings": warnings,
            "kb_id": new_kb_id
        })
    else:
        return jsonify({"error": message}), 400

@app.route("/api/agents/<agent_id>/export", methods=["GET"])
@login_required
def export_agent_api(agent_id):
    """Export an agent as downloadable JSON"""
    from app.models.agent import agent_manager
    
    success, message, agent_data = agent_manager.export_agent(agent_id)
    
    if not success:
        return jsonify({"error": message}), 404
    
    # Use agent name for filename (sanitize)
    agent_name = agent_data.get("name", "agent").replace(" ", "_").lower()
    safe_name = "".join(c for c in agent_name if c.isalnum() or c == "_")
    
    response = jsonify(agent_data)
    response.headers['Content-Disposition'] = f'attachment; filename="{safe_name}.json"'
    response.headers['Content-Type'] = 'application/json'
    
    return response

@app.route("/api/agents/import", methods=["POST"])
@login_required
def import_agent_api():
    """Import an agent from uploaded JSON file"""
    from app.models.agent import agent_manager
    import json
    
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    if not file.filename.endswith('.json'):
        return jsonify({"error": "File must be a JSON file"}), 400
    
    try:
        agent_data = json.load(file)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON format: {str(e)}"}), 400
    
    success, message, warnings = agent_manager.import_agent(agent_data)
    
    if success:
        return jsonify({
            "success": True,
            "message": message,
            "warnings": warnings
        })
    else:
        return jsonify({"error": message}), 400

@app.route("/exam_profiles", methods=["GET", "POST"])
@login_required
@roles_required('admin')
def exam_profiles():
    from app.config.exam_profile_config import (
        get_all_profiles, get_profile, save_profile, delete_profile, 
        get_profile_usage, profile_exists
    )
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "create" or action == "update":
            # Build profile data from form
            profile_data = {
                "profile_id": request.form.get("profile_id", "").strip(),
                "name": request.form.get("name", "").strip(),
                "description": request.form.get("description", "").strip(),
                "guidance_suffix": request.form.get("guidance_suffix", "").strip(),
                "question_types": [],
                "domains": [],
                "reasoning_modes": [],
                "kb_structure": {
                    "priority_kb_flag": request.form.get("priority_kb_flag", "is_priority_kb").strip(),
                    "outline_type": request.form.get("outline_type", "outline").strip(),
                    "domain_type": request.form.get("domain_type", "cbk").strip()
                }
            }
            
            # Parse question types (JSON array from frontend)
            qt_json = request.form.get("question_types_json", "[]")
            try:
                profile_data["question_types"] = json.loads(qt_json)
            except:
                flash("Invalid question types data", "error")
                return redirect(url_for('exam_profiles'))
            
            # Parse domains (JSON array from frontend)
            domains_json = request.form.get("domains_json", "[]")
            try:
                profile_data["domains"] = json.loads(domains_json)
            except:
                flash("Invalid domains data", "error")
                return redirect(url_for('exam_profiles'))
            
            # Parse reasoning modes (JSON array from frontend)
            modes_json = request.form.get("reasoning_modes_json", "[]")
            try:
                profile_data["reasoning_modes"] = json.loads(modes_json)
            except:
                flash("Invalid reasoning modes data", "error")
                return redirect(url_for('exam_profiles'))
            
            # Check for ID uniqueness on create
            if action == "create" and profile_exists(profile_data["profile_id"]):
                flash("Profile ID already exists", "error")
                return redirect(url_for('exam_profiles'))
            
            # Preserve existing difficulty_profile when updating
            # (difficulty_profile is managed via separate API endpoint)
            if action == "update":
                existing_profile = get_profile(profile_data["profile_id"])
                if existing_profile and "difficulty_profile" in existing_profile:
                    profile_data["difficulty_profile"] = existing_profile["difficulty_profile"]
            
            # Save profile
            success, message = save_profile(profile_data)
            if success:
                flash(message, "success")
            else:
                flash(message, "error")
        
        elif action == "delete":
            profile_id = request.form.get("profile_id", "").strip()
            
            # Check usage
            usage = get_profile_usage(profile_id)
            if usage["agents_count"] > 0 or usage["kb_count"] > 0:
                flash(
                    f"Cannot delete profile. Used by {usage['agents_count']} agent(s) and {usage['kb_count']} KB(s)", 
                    "error"
                )
            else:
                success, message = delete_profile(profile_id)
                if success:
                    flash(message, "success")
                else:
                    flash(message, "error")
        
        return redirect(url_for('exam_profiles'))
    
    # GET request - show profiles with usage stats
    profiles = get_all_profiles()
    
    # Add usage stats to each profile
    for profile in profiles:
        usage = get_profile_usage(profile["profile_id"])
        profile["usage"] = usage
    
    return render_template("exam_profiles.html", profiles=profiles)

@app.route("/api/exam_profiles/<profile_id>", methods=["GET"])
@login_required
def get_exam_profile_api(profile_id):
    """API endpoint to get a specific exam profile"""
    from app.config.exam_profile_config import get_profile
    
    profile = get_profile(profile_id)
    if profile:
        return jsonify({"success": True, "profile": profile})
    else:
        return jsonify({"success": False, "error": "Profile not found"}), 404

@app.route("/api/exam_profiles/<profile_id>/export", methods=["GET"])
@login_required
@roles_required('admin')
def export_exam_profile(profile_id):
    """Export an exam profile as downloadable JSON"""
    from app.config.exam_profile_config import export_profile
    
    success, message, profile_data = export_profile(profile_id)
    
    if not success:
        return jsonify({"error": message}), 404
    
    # Create a JSON response with download headers
    response = jsonify(profile_data)
    response.headers['Content-Disposition'] = f'attachment; filename="{profile_id}.json"'
    response.headers['Content-Type'] = 'application/json'
    
    return response

@app.route("/api/exam_profiles/import", methods=["POST"])
@login_required
@roles_required('admin')
def import_exam_profile():
    """Import an exam profile from uploaded JSON file"""
    from app.config.exam_profile_config import import_profile
    import json
    
    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    # Validate file extension
    if not file.filename.endswith('.json'):
        return jsonify({"error": "File must be a JSON file"}), 400
    
    try:
        # Parse JSON from uploaded file
        profile_data = json.load(file)
    except json.JSONDecodeError as e:
        return jsonify({"error": f"Invalid JSON format: {str(e)}"}), 400
    
    # Get overwrite flag from form data
    overwrite = request.form.get('overwrite', 'false').lower() == 'true'
    
    # Import the profile
    success, message = import_profile(profile_data, overwrite)
    
    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"error": message}), 400

@app.route("/api/exam_profiles/<profile_id>/difficulty_settings", methods=["GET"])
@login_required
@roles_required('admin')
def get_difficulty_settings_api(profile_id):
    """Get difficulty profile settings (weights, enabled levels, display names)"""
    from app.config.exam_profile_config import get_difficulty_profile
    settings = get_difficulty_profile(profile_id)
    return jsonify({"success": True, "settings": settings})

@app.route("/api/exam_profiles/<profile_id>/difficulty_settings", methods=["PUT"])
@login_required
@roles_required('admin')
def update_difficulty_settings_api(profile_id):
    """Update difficulty profile settings"""
    data = request.get_json()
    from app.config.exam_profile_config import update_difficulty_profile
    success, message = update_difficulty_profile(profile_id, data)
    
    if success:
        return jsonify({"success": True, "message": message})
    else:
        return jsonify({"success": False, "error": message}), 400

@app.route("/api/global_difficulty_levels", methods=["GET"])
def get_global_difficulty_levels_api():
    """Get canonical global difficulty level definitions"""
    from app.config.difficulty_config import get_global_levels
    levels = get_global_levels()
    # Convert OrderedDict to list for JSON serialization
    levels_list = list(levels.values())
    return jsonify({"success": True, "levels": levels_list})

@app.route("/knowledge", methods=["GET", "POST"])
@login_required
def knowledge():
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "add_file":
            # Handle file upload
            if 'file' not in request.files:
                flash('No file selected', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            
            if file.filename == '':
                flash('No file selected', 'error')
                return redirect(request.url)
            
            if not title:
                flash('Title is required', 'error')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                # Add to knowledge base configuration
                kb_id = add_knowledge_base(title, description, "file", filepath)
                
                # Process the knowledge base
                update_embedding_status(kb_id, "processing")
                success, _ = process_knowledge_base(kb_id, "file", filepath)
                if success:
                    update_embedding_status(kb_id, "completed")
                    flash(f'Knowledge base "{title}" added and processed successfully!', 'success')
                else:
                    update_embedding_status(kb_id, "failed")
                    flash(f'Knowledge base "{title}" added but processing failed.', 'error')
            else:
                flash('Invalid file type. Only PDF and DOCX files are allowed.', 'error')
        
        elif action == "add_url":
            # Handle URL addition
            url = request.form.get('url', '').strip()
            title = request.form.get('url_title', '').strip()
            description = request.form.get('url_description', '').strip()
            
            if not url or not title:
                flash('URL and title are required', 'error')
                return redirect(request.url)
            
            # Add to knowledge base configuration
            kb_id = add_knowledge_base(title, description, "url", url)
            
            # Process the knowledge base
            update_embedding_status(kb_id, "processing")
            success, _ = process_knowledge_base(kb_id, "url", url)
            if success:
                update_embedding_status(kb_id, "completed")
                flash(f'Knowledge base "{title}" added and processed successfully!', 'success')
            else:
                update_embedding_status(kb_id, "failed")
                flash(f'Knowledge base "{title}" added but processing failed.', 'error')
        
        elif action == "remove":
            # Handle knowledge base removal
            kb_id = request.form.get('kb_id')
            if kb_id:
                remove_knowledge_base(kb_id)
                flash('Knowledge base removed successfully!', 'success')
        
        return redirect(url_for('knowledge'))
    
    # GET request - show knowledge bases
    knowledge_bases = get_active_knowledge_bases()
    return render_template("knowledge.html", knowledge_bases=knowledge_bases)

@app.route("/settings", methods=["GET", "POST"])
@roles_required('admin')
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "update_model":
            chat_model = request.form.get("chat_model", "gpt-5")
            temperature = float(request.form.get("temperature", 0.5))
            
            # Update the model configuration
            try:
                from app.config.model_config import update_model_settings
                if update_model_settings(chat_model=chat_model, temperature=temperature):
                    flash(f'Model updated to {chat_model} with temperature {temperature}!', 'success')
                else:
                    flash('Error updating model configuration', 'error')
            except Exception as e:
                flash(f'Error updating model: {str(e)}', 'error')
        
        elif action == "cleanup_knowledge_bases":
            try:
                from app.config.knowledge_config import full_knowledge_base_cleanup
                if full_knowledge_base_cleanup():
                    flash('Knowledge base cleanup completed! Orphaned data has been removed.', 'success')
                else:
                    flash('Knowledge base cleanup completed - no orphaned data found.', 'info')
            except Exception as e:
                flash(f'Error during cleanup: {str(e)}', 'error')
        
        elif action == "update_api_key":
            api_key = request.form.get("api_key", "").strip()
            if not api_key:
                flash('API key is required', 'error')
            elif not api_key.startswith('sk-'):
                flash('Invalid API key format. OpenAI keys start with "sk-"', 'error')
            else:
                try:
                    from app.config.api_config import set_openai_api_key
                    if set_openai_api_key(api_key):
                        flash('API key updated successfully!', 'success')
                    else:
                        flash('Error saving API key', 'error')
                except Exception as e:
                    flash(f'Error updating API key: {str(e)}', 'error')
        
        elif action == "update_gemini_key":
            gemini_key = request.form.get("gemini_api_key", "").strip()
            if gemini_key and gemini_key != "••••••••":
                try:
                    from app.config.provider_config import set_provider_api_key
                    set_provider_api_key("gemini", gemini_key)
                    flash('Gemini API key updated successfully!', 'success')
                except Exception as e:
                    flash(f'Error updating Gemini API key: {str(e)}', 'error')
            elif not gemini_key:
                flash('Gemini API key is required', 'error')
        
        elif action == "test_api_key":
            api_key = request.form.get("api_key", "").strip()
            try:
                from app.config.api_config import test_openai_api_key
                result = test_openai_api_key(api_key if api_key else None)
                return jsonify(result)
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        
        elif action == "delete_api_key":
            try:
                from app.config.api_config import delete_openai_api_key
                if delete_openai_api_key():
                    flash('API key deleted successfully!', 'success')
                else:
                    flash('Error deleting API key', 'error')
            except Exception as e:
                flash(f'Error deleting API key: {str(e)}', 'error')
        
        return redirect(url_for('settings'))
    
    # GET request - show settings
    try:
        from app.config.model_config import get_current_model, get_current_temperature
        current_model = get_current_model()
        current_temperature = get_current_temperature()
    except:
        current_model = "gpt-5"
        current_temperature = 0.5
    
    # Get usage statistics
    from app.models.agent import agent_manager
    from app.config.knowledge_config import load_knowledge_config
    from app.config.api_config import get_api_key_info
    
    stats = {
        'total_emails': 0,  # Could be tracked in future
        'active_agents': len(agent_manager.get_all_agents()),
        'knowledge_bases': len(load_knowledge_config().get('knowledge_bases', []))
    }
    
    # Get API key information
    api_info = get_api_key_info()
    
    # Get Gemini API key info
    from app.config.provider_config import get_provider_api_key
    gemini_key = get_provider_api_key("gemini")
    gemini_key_masked = "••••••••" if gemini_key else ""
    
    return render_template("settings.html", 
                         current_model=current_model,
                         current_temperature=current_temperature,
                         stats=stats,
                         api_key_preview=api_info.get('preview'),
                         api_key_updated=api_info.get('last_updated'),
                         api_key_status=api_info.get('test_status'),
                         api_key_source=api_info.get('source'),
                         gemini_key_masked=gemini_key_masked)

# Chat API endpoints for chatbot functionality
@app.route("/api/chat/session", methods=["POST"])
@login_required
def create_chat_session():
    """Create a new chat session"""
    try:
        data = request.get_json()
        agent_id = data.get("agent_id", "").strip()
        
        if not agent_id:
            return jsonify({"success": False, "error": "Agent ID is required"})
        
        # Verify the agent exists
        agent_result = AgentAPI.get_agent(agent_id)
        if not agent_result["success"]:
            return jsonify({"success": False, "error": "Agent not found"})
        
        # Create new session
        session = chat_session_manager.create_session(agent_id)
        
        return jsonify({
            "success": True,
            "session_id": session.session_id,
            "agent_id": agent_id,
            "created_at": session.created_at
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/chat/<agent_id>", methods=["POST"])
@login_required
def chat_with_agent(agent_id):
    """Handle chat messages with a specific agent"""
    try:
        data = request.get_json()
        message = data.get("message", "").strip()
        session_id = data.get("session_id", "").strip()
        enabled_levels = data.get("enabled_levels", None)  # NEW: Array of level_ids
        hot_topics_mode = data.get("hot_topics_mode", None)
        valid_hot_topics_modes = {"disabled", "assistive", "priority"}
        
        if not message:
            return jsonify({"success": False, "error": "Message is required"})

        if hot_topics_mode is not None and hot_topics_mode not in valid_hot_topics_modes:
            return jsonify({
                "success": False,
                "error": "hot_topics_mode must be one of: disabled, assistive, priority"
            })
        
        # Get the agent
        agent_result = AgentAPI.get_agent(agent_id)
        if not agent_result["success"]:
            return jsonify({"success": False, "error": "Agent not found"})
        
        # Convert dictionary to Agent object for generate_reply function
        from app.models.agent import Agent
        agent = Agent.from_dict(agent_result["agent"])
        
        # Get chat history if session exists
        history = []
        if session_id:
            history = chat_session_manager.get_chat_history(session_id, limit=10)
        
        # Set thread_id in request context for semantic cache
        g.thread_id = session_id if session_id else 'default'
        
        # Store enabled difficulty levels in request context for blueprint selection
        if enabled_levels:
            g.enabled_difficulty_levels = enabled_levels

        # Optional request-level override for hot topics retrieval behavior
        if hot_topics_mode is not None:
            g.request_hot_topics_mode = hot_topics_mode
        
        # Generate response using existing agent logic
        response = generate_reply(message, history=history, agent=agent)
        
        # Store the conversation if session exists
        if session_id:
            chat_session_manager.add_message(session_id, "user", message)
            chat_session_manager.add_message(session_id, "assistant", response)
        
        # Get comprehensive difficulty metadata from blueprint if available
        difficulty_metadata = None
        try:
            blueprint = getattr(g, 'current_blueprint', None)
            if blueprint and 'question_type' in blueprint:
                question_type = blueprint['question_type']
                
                # NEW: Extract comprehensive metadata
                if isinstance(question_type, dict):
                    difficulty_level_id = question_type.get('difficulty_level')
                    
                    if difficulty_level_id:
                        from app.config.difficulty_config import get_level_by_id
                        from app.config.exam_profile_config import get_profile
                        
                        global_level = get_level_by_id(difficulty_level_id)
                        
                        if global_level:
                            # Get profile's custom display name
                            display_name = global_level['name']  # Default
                            if hasattr(agent, 'exam_profile_id') and agent.exam_profile_id:
                                profile = get_profile(agent.exam_profile_id)
                                if profile:
                                    display_names = profile.get('difficulty_profile', {}).get('display_names', {})
                                    display_name = display_names.get(difficulty_level_id, global_level['name'])
                            
                            difficulty_metadata = {
                                'question_type_id': question_type.get('id'),
                                'question_type_phrase': question_type.get('phrase'),
                                'difficulty_level_id': difficulty_level_id,
                                'difficulty_level_display_name': display_name,
                                'difficulty_level_global_name': global_level['name']
                            }
        except (RuntimeError, AttributeError):
            pass
        
        return jsonify({
            "success": True,
            "response": response,
            "agent_name": agent.name,
            "session_id": session_id,
            "difficulty": difficulty_metadata,
            "hot_topics_mode_effective": getattr(g, 'hot_topics_mode_effective', None),
            "hot_topics_used": getattr(g, 'hot_topics_used', None),
            "retrieval_path": getattr(g, 'retrieval_path', None)
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/embed/<agent_id>")
def get_embed_code(agent_id):
    """Get embed code for a specific agent"""
    try:
        agent_result = AgentAPI.get_agent(agent_id)
        if not agent_result["success"]:
            return "Agent not found", 404
        
        agent = agent_result["agent"]
        
        return render_template("chat_widget.html", 
                             agent=agent,
                             agent_id=agent_id)
        
    except Exception as e:
        return str(e), 500

@app.route("/embed-code/<agent_id>")
@login_required
def embed_code_generator(agent_id):
    """Generate embed code for a specific agent"""
    try:
        agent_result = AgentAPI.get_agent(agent_id)
        if not agent_result["success"]:
            return "Agent not found", 404
        
        agent = agent_result["agent"]
        
        # Generate different embed code options
        base_url = request.host_url.rstrip('/')
        
        embed_codes = {
            "iframe": f'<iframe src="{base_url}/embed/{agent_id}" width="400" height="600" frameborder="0"></iframe>',
            "javascript": f'''<script>
// Add this to your HTML head section
(function() {{
    var script = document.createElement('script');
    script.src = '{base_url}/embed/{agent_id}';
    script.async = true;
    document.head.appendChild(script);
}})();
</script>''',
            "direct_link": f'{base_url}/embed/{agent_id}'
        }
        
        return render_template("embed_generator.html", 
                             agent=agent,
                             agent_id=agent_id,
                             embed_codes=embed_codes,
                             base_url=base_url)
        
    except Exception as e:
        return str(e), 500

@app.route("/quiz/<agent_id>")
def quiz_widget(agent_id):
    """Render quiz widget for a specific agent"""
    try:
        from app.models.agent import agent_manager
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            return "Agent not found", 404
        
        return render_template("quiz_widget.html", 
                             agent=agent,
                             agent_id=agent_id)
        
    except Exception as e:
        return str(e), 500

@app.route("/quiz-code/<agent_id>")
@login_required
def quiz_embed_code_generator(agent_id):
    """Generate embed code for quiz widget"""
    try:
        from app.models.agent import agent_manager
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            return "Agent not found", 404
        
        # Generate different embed code options
        base_url = request.host_url.rstrip('/')
        
        embed_codes = {
            "iframe": f'<iframe src="{base_url}/quiz/{agent_id}" width="450" height="650" frameborder="0"></iframe>',
            "javascript": f'''<script>
// Add this to your HTML body section
(function() {{
    var iframe = document.createElement('iframe');
    iframe.src = '{base_url}/quiz/{agent_id}';
    iframe.width = '450';
    iframe.height = '650';
    iframe.frameBorder = '0';
    iframe.style.border = 'none';
    iframe.style.borderRadius = '10px';
    iframe.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
    document.body.appendChild(iframe);
}})();
</script>''',
            "direct_link": f'{base_url}/quiz/{agent_id}'
        }
        
        return render_template("quiz_embed_generator.html", 
                             agent=agent,
                             agent_id=agent_id,
                             embed_codes=embed_codes,
                             base_url=base_url)
        
    except Exception as e:
        return str(e), 500

@app.route("/api/quiz/<agent_id>/generate", methods=["POST"])
def generate_quiz_questions(agent_id):
    """Generate quiz questions using the agent"""
    try:
        data = request.json or {}
        count = data.get("count", 5)
        session_id = data.get("session_id")
        
        # Get agent object directly from agent_manager
        from app.models.agent import agent_manager
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            return jsonify({"success": False, "error": "Agent not found"})
        
        from app.agents.agent import generate_quiz_questions_for_agent
        
        questions = generate_quiz_questions_for_agent(agent, count)
        
        return jsonify({
            "success": True,
            "questions": questions,
            "session_id": session_id
        })
        
    except Exception as e:
        print(f"[ERROR] Error generating quiz questions: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})

# User Management Routes
@app.route("/users")
@roles_required('admin')
def users():
    """User management page (admin only)"""
    all_users = User.query.all()
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(50).all()
    return render_template("users.html", users=all_users, audit_logs=recent_logs)

@app.route("/users/add", methods=["POST"])
@roles_required('admin')
def add_user():
    """Add a new user (admin only)"""
    try:
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role", "user")
        
        if user_datastore.find_user(email=email):
            flash("User with this email already exists", "error")
            return redirect(url_for("users"))
        
        user_datastore.create_user(
            email=email,
            password=password,
            active=True,
            roles=[role],
            fs_uniquifier=secrets.token_urlsafe(32)
        )
        db.session.commit()
        
        # Log the action
        AuditLog.log_action(
            admin_email=current_user.email,
            action_type="user_created",
            target_email=email,
            ip_address=request.remote_addr,
            role=role
        )
        
        flash(f"User {email} created successfully", "success")
        return redirect(url_for("users"))
        
    except Exception as e:
        flash(f"Error creating user: {str(e)}", "error")
        return redirect(url_for("users"))

@app.route("/users/reset-password", methods=["POST"])
@roles_required('admin')
def reset_user_password():
    """Reset a user's password (admin only)"""
    try:
        data = request.json
        email = data.get("email")
        
        user = user_datastore.find_user(email=email)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        
        # Generate new password
        new_password = secrets.token_urlsafe(16)
        user.password = hash_password(new_password)
        db.session.commit()
        
        # Log the action
        AuditLog.log_action(
            admin_email=current_user.email,
            action_type="password_reset",
            target_email=email,
            ip_address=request.remote_addr
        )
        
        return jsonify({"success": True, "password": new_password})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/users/edit-email", methods=["POST"])
@roles_required('admin')
def edit_user_email():
    """Edit a user's email address (admin only)"""
    try:
        data = request.json
        old_email = data.get("old_email")
        new_email = data.get("new_email")
        
        # Validate inputs
        if not old_email or not new_email:
            return jsonify({"success": False, "error": "Both old and new email are required"})
        
        if old_email == new_email:
            return jsonify({"success": False, "error": "New email must be different from current email"})
        
        # Find user by old email
        user = user_datastore.find_user(email=old_email)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        
        # Check if new email is already taken
        existing_user = user_datastore.find_user(email=new_email)
        if existing_user:
            return jsonify({"success": False, "error": "Email address already in use"})
        
        # Update email
        user.email = new_email
        db.session.commit()
        
        # Log the action
        AuditLog.log_action(
            admin_email=current_user.email,
            action_type="email_changed",
            target_email=new_email,
            ip_address=request.remote_addr,
            old_email=old_email
        )
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/users/toggle-status", methods=["POST"])
@roles_required('admin')
def toggle_user_status():
    """Activate or deactivate a user (admin only)"""
    try:
        data = request.json
        email = data.get("email")
        active = data.get("active")
        
        user = user_datastore.find_user(email=email)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        
        if email == current_user.email:
            return jsonify({"success": False, "error": "Cannot deactivate your own account"})
        
        user_datastore.activate_user(user) if active else user_datastore.deactivate_user(user)
        db.session.commit()
        
        # Log the action
        AuditLog.log_action(
            admin_email=current_user.email,
            action_type="user_activated" if active else "user_deactivated",
            target_email=email,
            ip_address=request.remote_addr
        )
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/users/delete", methods=["POST"])
@roles_required('admin')
def delete_user():
    """Delete a user (admin only)"""
    try:
        data = request.json
        email = data.get("email")
        
        user = user_datastore.find_user(email=email)
        if not user:
            return jsonify({"success": False, "error": "User not found"})
        
        if email == current_user.email:
            return jsonify({"success": False, "error": "Cannot delete your own account"})
        
        # Log the action before deletion
        AuditLog.log_action(
            admin_email=current_user.email,
            action_type="user_deleted",
            target_email=email,
            ip_address=request.remote_addr
        )
        
        user_datastore.delete_user(user)
        db.session.commit()
        
        return jsonify({"success": True})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    try:
        # Use environment variables or default to 0.0.0.0 for network access
        host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        port = int(os.environ.get('FLASK_RUN_PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
        app.run(debug=debug, host=host, port=port)
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
