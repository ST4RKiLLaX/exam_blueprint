from flask import Flask, render_template, request, redirect, flash, url_for, jsonify
import os
from werkzeug.utils import secure_filename
from app.agents.email_agent import generate_reply
from app.email.thread_store import load_store, get_history, add_inbound, add_outbound
from email.utils import make_msgid

from app.config.knowledge_config import (
    load_knowledge_config, add_knowledge_base, remove_knowledge_base, 
    get_active_knowledge_bases, update_embedding_status, get_knowledge_bases_by_category,
    save_knowledge_config, cleanup_orphaned_kb_references
)
from app.utils.knowledge_processor import process_knowledge_base
from app.models.event_category import load_event_categories, add_event_category, remove_event_category
from app.api.agent_api import AgentAPI
from app.api.email_account_api import EmailAccountAPI
from app.api.task_api import TaskAPI
from app.services.task_scheduler import task_scheduler

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'app/knowledge_bases'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

ALLOWED_EXTENSIONS = {'pdf', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    # Ensure task scheduler is started
    ensure_scheduler_started()
    
    # Get dynamic stats for dashboard
    from app.config.model_config import get_current_model
    from app.config.knowledge_config import load_knowledge_config
    from app.models.event_category import load_event_categories
    
    # Get current model
    current_model = get_current_model()
    
    # Count knowledge bases
    kb_config = load_knowledge_config()
    kb_count = len([kb for kb in kb_config.get('knowledge_bases', []) if kb.get('status') == 'active'])
    
    # Count event categories
    event_categories = load_event_categories()
    event_count = len([cat for cat in event_categories if cat.is_event])
    
    return render_template("dashboard.html", 
                         current_model=current_model,
                         kb_count=kb_count,
                         event_count=event_count)

@app.route("/agents", methods=["GET", "POST"])
def agents():
    # Clean up any orphaned knowledge base references
    cleanup_orphaned_kb_references()
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "create":
            # Get selected knowledge bases
            selected_kbs = request.form.getlist("knowledge_bases")
            
            # Create new agent
            result = AgentAPI.create_agent(
                name=request.form.get("name", "").strip(),
                personality=request.form.get("personality", "").strip(),
                style=request.form.get("style", "").strip(),
                prompt=request.form.get("prompt", "").strip(),
                knowledge_bases=selected_kbs
            )
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "update":
            # Get selected knowledge bases
            selected_kbs = request.form.getlist("knowledge_bases")
            
            # Update existing agent
            agent_id = request.form.get("agent_id")
            result = AgentAPI.update_agent(
                agent_id,
                name=request.form.get("name", "").strip(),
                personality=request.form.get("personality", "").strip(),
                style=request.form.get("style", "").strip(),
                prompt=request.form.get("prompt", "").strip(),
                status=request.form.get("status"),
                knowledge_bases=selected_kbs
            )
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

@app.route("/api/threads", methods=["GET"])
def get_threads():
    """Get all email threads"""
    from app.email.thread_store import load_store
    
    store = load_store()
    threads = store.get("threads", {})
    
    # Format threads for display
    thread_list = []
    for thread_key, thread_data in threads.items():
        messages = thread_data.get("messages", [])
        if messages:
            # Get the latest message for preview
            latest_msg = messages[-1]
            first_msg = messages[0]
            
            thread_list.append({
                "thread_key": thread_key,
                "participant": first_msg.get("from", "Unknown"),
                "subject": first_msg.get("subject", "No Subject"),
                "message_count": len(messages),
                "last_activity": latest_msg.get("content", "")[:100] + "..." if len(latest_msg.get("content", "")) > 100 else latest_msg.get("content", ""),
                "last_role": latest_msg.get("role", "unknown")
            })
    
    # Sort by message count (most active first)
    thread_list.sort(key=lambda x: x["message_count"], reverse=True)
    
    return jsonify({"success": True, "threads": thread_list})

@app.route("/api/threads/<thread_key>", methods=["GET"])
def get_thread_details(thread_key):
    """Get detailed view of a specific thread"""
    from app.email.thread_store import load_store
    
    store = load_store()
    thread = store.get("threads", {}).get(thread_key)
    
    if not thread:
        return jsonify({"success": False, "error": "Thread not found"}), 404
    
    return jsonify({"success": True, "thread": thread})

@app.route("/api/threads/<thread_key>", methods=["DELETE"])
def delete_thread(thread_key):
    """Delete a specific thread"""
    from app.email.thread_store import load_store, save_store
    
    store = load_store()
    threads = store.get("threads", {})
    msg_index = store.get("message_index", {})
    
    if thread_key not in threads:
        return jsonify({"success": False, "error": "Thread not found"}), 404
    
    # Remove thread
    thread_data = threads.pop(thread_key)
    
    # Remove message IDs from index
    for message in thread_data.get("messages", []):
        msg_id = message.get("message_id")
        if msg_id and msg_id in msg_index:
            del msg_index[msg_id]
    
    save_store(store)
    
    return jsonify({"success": True, "message": "Thread deleted successfully"})

@app.route("/api/threads", methods=["DELETE"])
def clear_all_threads():
    """Clear all email threads"""
    from app.email.thread_store import load_store, save_store
    
    store = load_store()
    thread_count = len(store.get("threads", {}))
    
    # Clear all threads and message index
    store["threads"] = {}
    store["message_index"] = {}
    
    save_store(store)
    
    return jsonify({"success": True, "message": f"Cleared {thread_count} threads successfully"})

@app.route("/email_accounts", methods=["GET", "POST"])
def email_accounts():
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "create":
            # Create new email account
            result = EmailAccountAPI.create_account(
                name=request.form.get("name", "").strip(),
                email_address=request.form.get("email_address", "").strip(),
                imap_host=request.form.get("imap_host", "").strip(),
                imap_port=int(request.form.get("imap_port", 993)),
                smtp_host=request.form.get("smtp_host", "").strip(),
                smtp_port=int(request.form.get("smtp_port", 587)),
                username=request.form.get("username", "").strip(),
                password=request.form.get("password", "").strip(),
                imap_ssl="on" in request.form.getlist("imap_ssl"),
                smtp_ssl="on" in request.form.getlist("smtp_ssl")
            )
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "update":
            # Update existing email account
            account_id = request.form.get("account_id")
            result = EmailAccountAPI.update_account(
                account_id,
                name=request.form.get("name", "").strip(),
                email_address=request.form.get("email_address", "").strip(),
                imap_host=request.form.get("imap_host", "").strip(),
                imap_port=int(request.form.get("imap_port", 993)),
                smtp_host=request.form.get("smtp_host", "").strip(),
                smtp_port=int(request.form.get("smtp_port", 587)),
                username=request.form.get("username", "").strip(),
                password=request.form.get("password", "").strip() if request.form.get("password", "").strip() else None,
                imap_ssl="on" in request.form.getlist("imap_ssl"),
                smtp_ssl="on" in request.form.getlist("smtp_ssl"),
                status=request.form.get("status")
            )
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "delete":
            # Delete email account
            account_id = request.form.get("account_id")
            result = EmailAccountAPI.delete_account(account_id)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "test_connection":
            # Test email account connection
            account_id = request.form.get("account_id")
            result = EmailAccountAPI.test_connection(account_id)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(f"Connection failed: {result['error']}", "error")
        
        return redirect(url_for('email_accounts'))
    
    # GET request - show email accounts
    accounts_result = EmailAccountAPI.get_accounts_with_agent_info()
    accounts_data = accounts_result.get("accounts", []) if accounts_result["success"] else []
    
    agents_result = AgentAPI.get_all_agents()
    agents_data = agents_result.get("agents", []) if agents_result["success"] else []
    
    return render_template("email_accounts.html", accounts=accounts_data, agents=agents_data)

@app.route("/tasks", methods=["GET", "POST"])
def tasks():
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "create":
            # Create new task
            result = TaskAPI.create_task(
                name=request.form.get("name", "").strip(),
                task_type=request.form.get("task_type", ""),
                description=request.form.get("description", "").strip(),
                agent_id=request.form.get("agent_id", ""),
                email_account_id=request.form.get("email_account_id", ""),
                schedule_type=request.form.get("schedule_type", "minutes"),
                schedule_interval=int(request.form.get("schedule_interval", 15)),
                schedule_time=request.form.get("schedule_time", "").strip(),
                business_hours_only=request.form.get("business_hours_only") == "on"
            )
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "update":
            # Update existing task
            task_id = request.form.get("task_id")
            result = TaskAPI.update_task(
                task_id,
                name=request.form.get("name", "").strip(),
                description=request.form.get("description", "").strip(),
                agent_id=request.form.get("agent_id", ""),
                email_account_id=request.form.get("email_account_id", ""),
                schedule_type=request.form.get("schedule_type", "minutes"),
                schedule_interval=int(request.form.get("schedule_interval", 15)),
                schedule_time=request.form.get("schedule_time", "").strip(),
                business_hours_only=request.form.get("business_hours_only") == "on",
                status=request.form.get("status")
            )
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "delete":
            # Delete task
            task_id = request.form.get("task_id")
            result = TaskAPI.delete_task(task_id)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "pause":
            # Pause task
            task_id = request.form.get("task_id")
            result = TaskAPI.pause_task(task_id)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "resume":
            # Resume task
            task_id = request.form.get("task_id")
            result = TaskAPI.resume_task(task_id)
            if result["success"]:
                flash(result["message"], "success")
            else:
                flash(result["error"], "error")
        
        elif action == "run_now":
            # Run task immediately
            task_id = request.form.get("task_id")
            result = TaskAPI.run_task_now(task_id)
            if result["success"]:
                flash(f"Task executed successfully", "success")
            else:
                flash(f"Task execution failed: {result['error']}", "error")
        
        return redirect(url_for('tasks'))
    
    # GET request - show tasks
    tasks_result = TaskAPI.get_all_tasks()
    tasks_data = tasks_result.get("tasks", []) if tasks_result["success"] else []
    
    agents_result = AgentAPI.get_all_agents()
    agents_data = agents_result.get("agents", []) if agents_result["success"] else []
    
    accounts_result = EmailAccountAPI.get_all_accounts()
    accounts_data = accounts_result.get("accounts", []) if accounts_result["success"] else []
    
    task_types_result = TaskAPI.get_task_types()
    task_types_data = task_types_result.get("task_types", []) if task_types_result["success"] else []
    
    schedule_types_result = TaskAPI.get_schedule_types()
    schedule_types_data = schedule_types_result.get("schedule_types", []) if schedule_types_result["success"] else []
    
    return render_template("tasks.html", 
                         tasks=tasks_data, 
                         agents=agents_data, 
                         accounts=accounts_data,
                         task_types=task_types_data,
                         schedule_types=schedule_types_data)

@app.route("/test", methods=["GET", "POST"])
def test():
    email_input = ""
    reply_output = ""
    selected_thread_key = None
    history_preview = []

    # Load existing threads for selection
    store = load_store()
    threads = []
    for key, thread in (store.get("threads", {}) or {}).items():
        messages = thread.get("messages", [])
        label = key
        if messages:
            first = messages[0]
            subj = first.get("subject") or ""
            frm = first.get("from") or first.get("to") or ""
            if subj or frm:
                label = f"{subj} — {frm}"
        threads.append({"key": key, "label": label})

    if request.method == "POST":
        email_input = request.form["email_body"]
        use_thread = request.form.get("use_thread") == "on"
        selected_thread_key = request.form.get("thread_key") or None
        test_subject = (request.form.get("test_subject") or "").strip()
        test_from = (request.form.get("test_from") or "").strip() or "test@example.com"

        history = []
        if use_thread:
            # Prepare a synthetic inbound email to persist in the thread store
            in_reply_to = None
            references = []
            # If an existing thread is selected, reference its latest message-id to attach
            if selected_thread_key:
                sel_thread = (store.get("threads", {}) or {}).get(selected_thread_key)
                if sel_thread and sel_thread.get("messages"):
                    last_msg = sel_thread["messages"][-1]
                    last_mid = last_msg.get("message_id")
                    if last_mid:
                        in_reply_to = last_mid
                        references = [last_mid]
            # Fallback subject from email body
            fallback_subject = (email_input[:60] + "…") if len(email_input) > 60 else email_input
            email_obj = {
                "subject": test_subject or fallback_subject or "Test Thread",
                "from": test_from,
                "body": email_input,
                "message_id": make_msgid(),
                "in_reply_to": in_reply_to,
                "references": references,
            }
            # Add inbound; this computes/returns the effective thread key (existing or new)
            thread_key = add_inbound(email_obj)
            selected_thread_key = thread_key
            history = get_history(thread_key, limit=10)
            history_preview = history
            # Generate reply with history and persist outbound to the same thread
            reply_output = generate_reply(email_input, history=history)
            synthetic_sent_id = make_msgid()
            add_outbound(thread_key, test_from, email_obj["subject"], reply_output, synthetic_sent_id, in_reply_to=email_obj.get("message_id"), references=[email_obj.get("message_id")])
            # Reload store and threads for updated dropdown
            store = load_store()
            threads = []
            for key, thread in (store.get("threads", {}) or {}).items():
                messages = thread.get("messages", [])
                label = key
                if messages:
                    first = messages[0]
                    subj = first.get("subject") or ""
                    frm = first.get("from") or first.get("to") or ""
                    if subj or frm:
                        label = f"{subj} — {frm}"
                threads.append({"key": key, "label": label})
        else:
            reply_output = generate_reply(email_input, history=[])

    return render_template(
        "test.html",
        email_input=email_input,
        reply_output=reply_output,
        threads=threads,
        selected_thread_key=selected_thread_key,
        history_preview=history_preview,
    )





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
                        event_category=category if is_events else None,
                        refresh_schedule=refresh_schedule
                    )
                    
                    # Process the knowledge base
                    from app.utils.knowledge_processor import process_knowledge_base
                    update_embedding_status(kb_id, "processing")
                    
                    # Generate AI summary if description is empty
                    generate_summary = not description.strip()
                    success, ai_summary = process_knowledge_base(kb_id, "url", source_url, generate_summary=generate_summary)
                    
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
                        event_category=category if is_events else None,
                        refresh_schedule="manual"  # Files don't have refresh schedules
                    )
                    
                    # Process the knowledge base
                    from app.utils.knowledge_processor import process_knowledge_base
                    update_embedding_status(kb_id, "processing")
                    
                    # Generate AI summary if description is empty
                    generate_summary = not description.strip()
                    success, ai_summary = process_knowledge_base(kb_id, "file", upload_path, generate_summary=generate_summary)
                    
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
                            'event_category': category if is_events else None
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
        
        elif action == "discover_locations":
            # Handle location discovery for event knowledge bases
            kb_id = request.form.get('kb_id')
            if kb_id:
                try:
                    from app.utils.knowledge_processor import discover_locations_for_event_kb
                    
                    success = discover_locations_for_event_kb(kb_id)
                    
                    if success:
                        return jsonify({
                            "success": True,
                            "message": "Location discovery completed! Knowledge base description updated with nearby areas."
                        })
                    else:
                        return jsonify({
                            "success": False,
                            "error": "Failed to discover locations. Check if this is an event knowledge base with valid location data."
                        })
                        
                except Exception as e:
                    return jsonify({
                        "success": False,
                        "error": f"Error during location discovery: {str(e)}"
                    })
            else:
                return jsonify({
                    "success": False,
                    "error": "Knowledge base ID not provided"
                })
        
        elif action == "add_category":
            # Handle adding new category
            from app.models.event_category import add_event_category
            category_name = request.form.get('category_name', '').strip()
            category_description = request.form.get('category_description', '').strip()
            is_event = request.form.get('is_event') == 'on'
            
            if not category_name:
                flash('Category name is required', 'error')
                return redirect(request.url)
            
            category_id = add_event_category(category_name, category_description, is_event)
            event_type = "Event category" if is_event else "Category"
            flash(f'{event_type} "{category_name}" added successfully!', 'success')
        
        elif action == "remove_category":
            # Handle removing category
            from app.models.event_category import remove_event_category
            category_id = request.form.get('category_id')
            if category_id:
                if remove_event_category(category_id):
                    flash('Category removed successfully!', 'success')
                else:
                    flash('Failed to remove category', 'error')
        
        return redirect(url_for('knowledge_bases'))
    
    # GET request - show knowledge bases
    from app.models.event_category import load_event_categories
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
        chunks_path = os.path.join(os.path.dirname(__file__), "..", "knowledge_bases", kb_id, "chunks.pkl")
        if os.path.exists(chunks_path):
            try:
                import pickle
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
    
    categories = load_event_categories()
    
    return render_template("knowledge_bases.html", 
                         knowledge_bases=knowledge_bases, 
                         categories=categories)

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
                event_category = request.form.get('event_category', '').strip() if is_events else None
                
                # Add to knowledge base configuration
                kb_id = add_knowledge_base(title, description, "file", filepath, 
                                         event_category=event_category, is_events=is_events)
                
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
            event_category = request.form.get('event_category', '').strip() if is_events else None
            
            if not url or not title:
                flash('URL and title are required', 'error')
                return redirect(request.url)
            
            if is_events and not event_category:
                flash('Event category is required for event sources', 'error')
                return redirect(request.url)
            
            # Add to knowledge base configuration
            kb_id = add_knowledge_base(title, description, "url", url, 
                                     event_category=event_category, is_events=is_events)
            
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
    event_categories = load_event_categories()
    return render_template("knowledge.html", knowledge_bases=knowledge_bases, event_categories=event_categories)

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
        
        elif action == "test_api_key":
            api_key = request.form.get("api_key", "").strip()
            try:
                from app.config.api_config import test_openai_api_key
                result = test_openai_api_key(api_key if api_key else None)
                return jsonify(result)
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        
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
    
    return render_template("settings.html", 
                         current_model=current_model,
                         current_temperature=current_temperature,
                         stats=stats,
                         api_key_preview=api_info.get('preview'),
                         api_key_updated=api_info.get('last_updated'),
                         api_key_status=api_info.get('test_status'),
                         api_key_source=api_info.get('source'))

# Initialize task scheduler when module is imported
# This ensures it starts regardless of how the Flask app is run
import atexit
import os

def start_scheduler():
    """Start the task scheduler if not already running"""
    # Only start scheduler in the main process (not in Flask's reloader process)
    # In debug mode, only start in the reloaded process (WERKZEUG_RUN_MAIN=true)
    should_start = (
        not app.debug or  # Always start in production
        os.environ.get('WERKZEUG_RUN_MAIN') == 'true'  # Only in main process in debug mode
    )
    
    if should_start and not task_scheduler.running:
        task_scheduler.start()
        print("🚀 Task scheduler started - automated tasks are now running!")
        return True
    return False

def stop_scheduler():
    """Stop the task scheduler"""
    if task_scheduler.running:
        task_scheduler.stop()
        print("✅ Task scheduler stopped")

# Register cleanup function
atexit.register(stop_scheduler)

# Initialize scheduler after app setup
# Use a flag to ensure it only starts once
_scheduler_initialized = False

def ensure_scheduler_started():
    """Ensure the task scheduler is started (call this from routes)"""
    global _scheduler_initialized
    if not _scheduler_initialized:
        start_scheduler()
        _scheduler_initialized = True

# Start scheduler immediately when not in debug mode
if not app.debug:
    start_scheduler()
    _scheduler_initialized = True

@app.route("/api/scheduler/status")
def scheduler_status():
    """Get scheduler status for debugging"""
    return jsonify({
        "running": task_scheduler.running,
        "thread_alive": task_scheduler.thread.is_alive() if task_scheduler.thread else False,
        "check_interval": task_scheduler.check_interval,
        "werkzeug_run_main": os.environ.get('WERKZEUG_RUN_MAIN'),
        "debug_mode": app.debug
    })


if __name__ == "__main__":
    try:
        app.run(debug=True)
    except KeyboardInterrupt:
        print("\n⏹️ Shutting down...")
        stop_scheduler()
