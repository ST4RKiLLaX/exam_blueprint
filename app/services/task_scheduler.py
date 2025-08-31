import time
import threading
import logging
from datetime import datetime
from typing import Dict, Any, Callable
from app.models.task import task_manager, TaskType
from app.models.agent import agent_manager
from app.models.email_account import email_account_manager
from app.email.email_reader import fetch_unread_emails, mark_emails_as_read
from app.email.email_sender import send_email
from app.agents.email_agent import generate_reply
from app.email.thread_store import add_inbound, add_outbound, get_history
from app.config.knowledge_config import get_knowledge_bases_due_for_refresh, mark_knowledge_base_refreshed
from app.utils.knowledge_processor import process_knowledge_base

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TaskExecutor:
    """Executes different types of tasks"""
    
    def __init__(self):
        self.task_handlers = {
            TaskType.EMAIL_CHECK.value: self._execute_email_check,
            TaskType.GENERATE_REPORT.value: self._execute_generate_report,
            TaskType.CLEANUP.value: self._execute_cleanup,
            TaskType.SYNC.value: self._execute_sync,
            "url_refresh": self._execute_url_refresh,
        }
    
    def execute_task(self, task) -> Dict[str, Any]:
        """Execute a task and return result"""
        try:
            logger.info(f"Executing task: {task.name} ({task.task_type})")
            
            handler = self.task_handlers.get(task.task_type)
            if not handler:
                raise ValueError(f"Unknown task type: {task.task_type}")
            
            result = handler(task)
            logger.info(f"Task {task.name} completed successfully")
            return {"success": True, "result": result}
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task {task.name} failed: {error_msg}")
            return {"success": False, "error": error_msg}
    
    def _execute_email_check(self, task) -> Dict[str, Any]:
        """Execute email checking task"""
        # Get agent and email account (reload to ensure fresh data)
        agent_manager.load_agents()  # Force reload of agent data
        agent = agent_manager.get_agent(task.agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {task.agent_id}")
        

        
        email_account = email_account_manager.get_account(task.email_account_id)
        if not email_account:
            raise ValueError(f"Email account not found: {task.email_account_id}")
        
        # Fetch unread emails
        try:
            emails = fetch_unread_emails(
                email_account.imap_host,
                email_account.username,
                email_account.password,
                limit=10,  # Fetch up to 10 unread emails per check
                port=email_account.imap_port,
                use_ssl=email_account.imap_ssl
            )
            logger.info(f"Fetched {len(emails)} unread emails from {email_account.email_address}")
        except Exception as e:
            raise Exception(f"Failed to fetch emails: {str(e)}")
        
        processed_count = 0
        sent_count = 0
        errors = []
        processed_uids = []  # Track UIDs of successfully processed emails
        
        if not emails:
            logger.info("No unread emails found to process")
        
        for email in emails:
            try:
                logger.info(f"Processing email from {email.get('from', 'Unknown')} - {email.get('subject', 'No Subject')}")
                
                # Add to thread store
                thread_key = add_inbound(email)
                history = get_history(thread_key, limit=10)
                
                # Generate reply using the assigned agent
                logger.info(f"Generating reply using agent: {agent.name}")
                reply = generate_reply(email["body"], history=history, agent=agent)
                logger.info(f"Generated reply length: {len(reply) if reply else 0} characters")
                
                # Send reply
                in_reply_to = email.get("message_id")
                references = list(set((email.get("references") or []) + ([in_reply_to] if in_reply_to else [])))
                
                logger.info(f"Sending reply to {email['from']} via SMTP {email_account.smtp_host}:{email_account.smtp_port}")
                sent_id = send_email(
                    email_account.smtp_host,
                    email_account.username,
                    email_account.password,
                    email["from"],
                    f"Re: {email['subject']}" if not email['subject'].startswith('Re:') else email['subject'],
                    reply,
                    port=email_account.smtp_port,
                    use_ssl=email_account.smtp_ssl,
                    in_reply_to=in_reply_to,
                    references=references
                )
                logger.info(f"Email sent successfully with ID: {sent_id}")
                
                # Add outbound to thread store
                add_outbound(
                    thread_key,
                    email["from"],
                    email["subject"],
                    reply,
                    sent_id,
                    in_reply_to=in_reply_to,
                    references=references
                )
                
                processed_count += 1
                sent_count += 1
                processed_uids.append(email.get('uid'))  # Track successful processing
                logger.info(f"Successfully processed and replied to email from {email.get('from')}")
                
            except Exception as e:
                error_msg = f"Error processing email from {email.get('from', 'Unknown')}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                processed_count += 1
        
        # Mark successfully processed emails as read
        if processed_uids:
            try:
                mark_success = mark_emails_as_read(
                    email_account.imap_host,
                    email_account.username,
                    email_account.password,
                    processed_uids,
                    port=email_account.imap_port,
                    use_ssl=email_account.imap_ssl
                )
                if mark_success:
                    logger.info(f"Marked {len(processed_uids)} emails as read")
                else:
                    logger.warning("Failed to mark some emails as read")
            except Exception as e:
                logger.error(f"Error marking emails as read: {str(e)}")
        
        result = {
            "emails_found": len(emails),
            "emails_processed": processed_count,
            "replies_sent": sent_count,
            "emails_marked_read": len(processed_uids),
            "errors": errors,
            "agent_name": agent.name,
            "email_account": email_account.email_address
        }
        
        return result
    
    def _execute_generate_report(self, task) -> Dict[str, Any]:
        """Execute report generation task"""
        # Placeholder for report generation
        logger.info("Generating report (placeholder)")
        return {"report_type": "daily_summary", "status": "generated"}
    
    def _execute_cleanup(self, task) -> Dict[str, Any]:
        """Execute cleanup task"""
        # Placeholder for cleanup operations
        logger.info("Running cleanup (placeholder)")
        return {"cleaned_items": 0, "status": "completed"}
    
    def _execute_sync(self, task) -> Dict[str, Any]:
        """Execute sync task"""
        # Placeholder for sync operations
        logger.info("Running sync (placeholder)")
        return {"synced_items": 0, "status": "completed"}
    
    def _execute_url_refresh(self, task) -> Dict[str, Any]:
        """Execute URL knowledge base refresh task"""
        refreshed_count = 0
        failed_count = 0
        
        try:
            # Get knowledge bases that are due for refresh
            due_kbs = get_knowledge_bases_due_for_refresh()
            logger.info(f"Found {len(due_kbs)} knowledge bases due for refresh")
            
            for kb in due_kbs:
                try:
                    kb_id = kb['id']
                    kb_title = kb['title']
                    source_url = kb['source']
                    
                    logger.info(f"Refreshing knowledge base: {kb_title} ({kb_id})")
                    
                    # Reprocess the knowledge base with fresh content
                    success, _ = process_knowledge_base(kb_id, "url", source_url)
                    if success:
                        # Mark as refreshed and calculate next refresh time
                        mark_knowledge_base_refreshed(kb_id)
                        refreshed_count += 1
                        logger.info(f"Successfully refreshed: {kb_title}")
                    else:
                        failed_count += 1
                        logger.error(f"Failed to refresh: {kb_title}")
                        
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error refreshing knowledge base {kb.get('title', 'Unknown')}: {e}")
            
            return {
                "refreshed_count": refreshed_count,
                "failed_count": failed_count,
                "total_checked": len(due_kbs),
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error in URL refresh task: {e}")
            return {
                "refreshed_count": refreshed_count,
                "failed_count": failed_count,
                "error": str(e),
                "status": "failed"
            }


class TaskScheduler:
    """Background task scheduler"""
    
    def __init__(self, check_interval: int = 60):
        self.check_interval = check_interval  # seconds
        self.executor = TaskExecutor()
        self.running = False
        self.thread = None
    
    def start(self):
        """Start the task scheduler"""
        if self.running:
            logger.warning("Task scheduler is already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info("Task scheduler started")
    
    def stop(self):
        """Stop the task scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Task scheduler stopped")
    
    def _run_scheduler(self):
        """Main scheduler loop"""
        while self.running:
            try:
                self._check_and_run_tasks()
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}")
            
            # Sleep for check interval
            time.sleep(self.check_interval)
    
    def _check_and_run_tasks(self):
        """Check for due tasks and execute them"""
        due_tasks = task_manager.get_due_tasks()
        
        # Also check for URL refresh tasks
        self._check_url_refresh_tasks()
        
        if not due_tasks:
            return
        
        logger.info(f"Found {len(due_tasks)} due tasks")
        
        for task in due_tasks:
            try:
                # Execute task
                result = self.executor.execute_task(task)
                
                # Update task after execution
                task.update_after_run(
                    success=result["success"],
                    error_message=result.get("error", "")
                )
                
                # Save updated task
                task_manager.save_tasks()
                
                logger.info(f"Task {task.name} execution completed")
                
            except Exception as e:
                error_msg = f"Failed to execute task {task.name}: {str(e)}"
                logger.error(error_msg)
                
                # Update task with error
                task.update_after_run(success=False, error_message=error_msg)
                task_manager.save_tasks()
    
    def run_task_now(self, task_id: str) -> Dict[str, Any]:
        """Run a specific task immediately"""
        task = task_manager.get_task(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}
        
        try:
            result = self.executor.execute_task(task)
            
            # Update task after execution
            task.update_after_run(
                success=result["success"],
                error_message=result.get("error", "")
            )
            task_manager.save_tasks()
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            task.update_after_run(success=False, error_message=error_msg)
            task_manager.save_tasks()
            return {"success": False, "error": error_msg}
    
    def _check_url_refresh_tasks(self):
        """Check for URL knowledge bases that need refreshing"""
        try:
            due_kbs = get_knowledge_bases_due_for_refresh()
            
            if due_kbs:
                logger.info(f"Found {len(due_kbs)} knowledge bases due for refresh")
                
                # Create a temporary task for URL refresh
                from app.models.task import Task
                refresh_task = Task(
                    task_id="system_url_refresh",
                    name="System URL Refresh",
                    task_type="url_refresh",
                    agent_id="system",
                    email_account_id="system",
                    schedule_type="system",
                    schedule_interval=0,
                    is_active=True
                )
                
                # Execute the refresh task
                result = self.executor.execute_task(refresh_task)
                logger.info(f"URL refresh completed: {result}")
                
        except Exception as e:
            logger.error(f"Error checking URL refresh tasks: {e}")


# Global task scheduler instance
task_scheduler = TaskScheduler()
