from flask import Flask, render_template, request, redirect, flash, url_for, jsonify, g
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from app.agents.agent import generate_reply

from app.config.knowledge_config import (
    load_knowledge_config, add_knowledge_base, remove_knowledge_base, 
    get_active_knowledge_bases, update_embedding_status, get_knowledge_bases_by_category,
    save_knowledge_config, cleanup_orphaned_kb_references
)
from app.utils.knowledge_processor import process_knowledge_base
from app.api.agent_api import AgentAPI
from app.models.chat_session import chat_session_manager

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'app/knowledge_bases'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Enable CORS for external embedding
CORS(app, resources={
    r"/api/chat/*": {"origins": "*"},
    r"/embed/*": {"origins": "*"}
})

# Global template context processor to check API key status
@app.context_processor
def inject_api_key_status():
    """Inject API key status into all templates"""
    try:
        from app.config.api_config import get_api_key_info
        api_info = get_api_key_info()
        return {
            'api_key_has_key': api_info.get('has_key', False),
            'api_key_status': api_info.get('test_status', 'unknown')
        }
    except:
        return {
            'api_key_has_key': False,
            'api_key_status': 'unknown'
        }

ALLOWED_EXTENSIONS = {'pdf', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    # Load agents for chat interface
    from app.api.agent_api import AgentAPI
    from app.config.model_config import get_current_model
    from app.config.knowledge_config import load_knowledge_config
    
    agents_result = AgentAPI.get_all_agents()
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
            
            # Get CISSP settings
            enable_cissp = request.form.get("enable_cissp_mode") == "on"
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
                enable_cissp_mode=enable_cissp,
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
            
            # Get CISSP settings
            enable_cissp = request.form.get("enable_cissp_mode") == "on"
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
                # CISSP settings
                "enable_cissp_mode": enable_cissp,
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
    
    return render_template("agents.html", agents=agents_data, knowledge_bases=knowledge_bases)





@app.route("/knowledge_bases", methods=["GET", "POST"])
def knowledge_bases():
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload or URL source
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            category = request.form.get('category', 'general')
            access_type = request.form.get('access_type', 'shared')
            source_type = request.form.get('source_type', 'file')
            is_events = request.form.get('is_events') == 'on'  # Checkbox value
            
            # Get CISSP metadata
            cissp_type = request.form.get('cissp_type', '').strip()
            cissp_domain = request.form.get('cissp_domain', '').strip()
            
            # Get embedding provider
            embedding_provider = request.form.get('embedding_provider', 'openai')
            
            if not title:
                flash('Title is required', 'error')
                return redirect(request.url)
            
            try:
                if source_type == 'url':
                    # Handle URL source
                    source_url = request.form.get('source_url', '').strip()
                    refresh_schedule = request.form.get('refresh_schedule', 'manual')
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
                        category=category,
                        is_events=is_events,
                        refresh_schedule=refresh_schedule,
                        cissp_type=cissp_type if cissp_type else None,
                        cissp_domain=cissp_domain if cissp_domain else None,
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
                        category=category,
                        is_events=is_events,
                        refresh_schedule="manual",  # Files don't have refresh schedules
                        cissp_type=cissp_type if cissp_type else None,
                        cissp_domain=cissp_domain if cissp_domain else None,
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
            category = request.form.get('category', 'general')
            access_type = request.form.get('access_type', 'shared')
            is_events = request.form.get('is_events') == 'on'  # Checkbox value
            refresh_schedule = request.form.get('refresh_schedule', 'manual')
            
            if kb_id and title:
                # Update knowledge base properties
                config = load_knowledge_config()
                kb_found = False
                for kb in config.get('knowledge_bases', []):
                    if kb.get('id') == kb_id:
                        # Only update refresh_schedule for URL knowledge bases
                        update_data = {
                            'title': title,
                            'description': description,
                            'category': category,
                            'access_type': access_type,
                            'is_events': is_events,
                        }
                        
                        # Add refresh schedule for URL knowledge bases
                        if kb.get('type') == 'url':
                            from app.config.knowledge_config import calculate_next_refresh
                            update_data['refresh_schedule'] = refresh_schedule
                            update_data['next_refresh'] = calculate_next_refresh(refresh_schedule, kb.get('last_refreshed'))
                        
                        kb.update(update_data)
                        kb_found = True
                        break
                
                if kb_found:
                    save_knowledge_config(config)
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
        
        elif action == "refresh":
            # Handle URL knowledge base refresh
            kb_id = request.form.get('kb_id')
            if kb_id:
                config = load_knowledge_config()
                kb_info = None
                for kb in config.get('knowledge_bases', []):
                    if kb.get('id') == kb_id:
                        kb_info = kb
                        break
                
                if kb_info and kb_info.get('type') == 'url':
                    try:
                        from app.utils.knowledge_processor import process_knowledge_base
                        from app.config.knowledge_config import mark_knowledge_base_refreshed
                        
                        # Refresh the URL knowledge base
                        update_embedding_status(kb_id, "processing")
                        success, _ = process_knowledge_base(kb_id, "url", kb_info['source'])
                        if success:
                            # Mark as refreshed and update next refresh time
                            mark_knowledge_base_refreshed(kb_id)
                            update_embedding_status(kb_id, "completed")
                            flash(f'Knowledge base "{kb_info["title"]}" refreshed successfully!', 'success')
                        else:
                            update_embedding_status(kb_id, "failed")
                            flash(f'Failed to refresh knowledge base "{kb_info["title"]}"', 'error')
                    except Exception as e:
                        update_embedding_status(kb_id, "failed")
                        flash(f'Error refreshing knowledge base: {str(e)}', 'error')
                elif kb_info:
                    flash('Only URL knowledge bases can be refreshed', 'error')
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
        
        knowledge_bases.append({
            'id': kb_id,
            'title': kb_info.get('title', 'Untitled'),
            'description': kb_info.get('description', ''),
            'category': kb_info.get('category', 'general'),
            'access_type': kb_info.get('access_type', 'shared'),
            'status': kb_info.get('status', 'active'),
            'kb_type': kb_info.get('type', 'document'),  # Note: 'type' not 'kb_type' in the config
            'created_at': kb_info.get('created_at', ''),
            'refresh_schedule': kb_info.get('refresh_schedule', 'manual'),
            'last_refreshed': kb_info.get('last_refreshed'),
            'next_refresh': kb_info.get('next_refresh'),
            'assigned_agents': assigned_agents,
            'chunks_count': chunks_count,
            'is_events': kb_info.get('is_events', False)
        })
    
    # Sort by creation date (newest first)
    knowledge_bases.sort(key=lambda x: x['created_at'], reverse=True)
    
    
    return render_template("knowledge_bases.html", 
                         knowledge_bases=knowledge_bases)

@app.route("/knowledge", methods=["GET", "POST"])
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
                
                # Check if this is an event source
                is_events = request.form.get('is_events') == 'true'
                
                # Add to knowledge base configuration
                kb_id = add_knowledge_base(title, description, "file", filepath, 
                                         is_events=is_events)
                
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
            is_events = request.form.get('is_events') == 'true'
            
            if not url or not title:
                flash('URL and title are required', 'error')
                return redirect(request.url)
            
            # Add to knowledge base configuration
            kb_id = add_knowledge_base(title, description, "url", url, 
                                     is_events=is_events)
            
            # For event URLs, we don't need to process embeddings
            if is_events:
                update_embedding_status(kb_id, "completed")
                flash(f'Event source "{title}" added successfully!', 'success')
            else:
                # Process the knowledge base for non-event URLs
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
def chat_with_agent(agent_id):
    """Handle chat messages with a specific agent"""
    try:
        data = request.get_json()
        message = data.get("message", "").strip()
        session_id = data.get("session_id", "").strip()
        
        if not message:
            return jsonify({"success": False, "error": "Message is required"})
        
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
        
        # Generate response using existing agent logic
        response = generate_reply(message, history=history, agent=agent)
        
        # Store the conversation if session exists
        if session_id:
            chat_session_manager.add_message(session_id, "user", message)
            chat_session_manager.add_message(session_id, "assistant", response)
        
        return jsonify({
            "success": True,
            "response": response,
            "agent_name": agent.name,
            "session_id": session_id
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

if __name__ == "__main__":
    try:
        # Use environment variables or default to 0.0.0.0 for network access
        host = os.environ.get('FLASK_RUN_HOST', '0.0.0.0')
        port = int(os.environ.get('FLASK_RUN_PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
        app.run(debug=debug, host=host, port=port)
    except KeyboardInterrupt:
        print("\n⏹️ Shutting down...")
