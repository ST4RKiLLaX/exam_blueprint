from typing import List, Optional, Dict
from app.models.task import Task, task_manager, TaskType, TaskStatus, ScheduleType
from app.models.agent import agent_manager
from app.models.email_account import email_account_manager
from app.services.task_scheduler import task_scheduler


class TaskAPI:
    """API layer for task management operations"""
    
    @staticmethod
    def create_task(name: str, task_type: str, description: str = "",
                   agent_id: str = "", email_account_id: str = "",
                   schedule_type: str = ScheduleType.MINUTES.value,
                   schedule_interval: int = 15, schedule_time: str = "",
                   business_hours_only: bool = True, **kwargs) -> Dict:
        """Create a new task and return result"""
        try:
            if not name.strip():
                return {"success": False, "error": "Task name is required"}
            
            # Validate task type
            valid_types = [t.value for t in TaskType]
            if task_type not in valid_types:
                return {"success": False, "error": f"Invalid task type. Must be one of: {', '.join(valid_types)}"}
            
            # For email check tasks, validate agent and email account
            if task_type == TaskType.EMAIL_CHECK.value:
                if not agent_id:
                    return {"success": False, "error": "Agent is required for email check tasks"}
                if not email_account_id:
                    return {"success": False, "error": "Email account is required for email check tasks"}
                
                # Verify agent exists
                agent = agent_manager.get_agent(agent_id)
                if not agent:
                    return {"success": False, "error": "Selected agent not found"}
                
                # Verify email account exists
                email_account = email_account_manager.get_account(email_account_id)
                if not email_account:
                    return {"success": False, "error": "Selected email account not found"}
                
                # Check if email account is already assigned to another task
                existing_tasks = task_manager.get_all_tasks()
                for existing_task in existing_tasks:
                    if (existing_task.task_type == TaskType.EMAIL_CHECK.value and 
                        existing_task.email_account_id == email_account_id and
                        existing_task.status == TaskStatus.ACTIVE.value):
                        return {"success": False, "error": f"Email account is already being monitored by task '{existing_task.name}'"}
            
            # Validate schedule
            if schedule_type == ScheduleType.MINUTES.value:
                if not (1 <= schedule_interval <= 1440):  # 1 minute to 24 hours
                    return {"success": False, "error": "Schedule interval must be between 1 and 1440 minutes"}
            elif schedule_type == ScheduleType.HOURLY.value:
                if not (0 <= schedule_interval <= 59):
                    return {"success": False, "error": "For hourly tasks, interval must be between 0 and 59 (minutes past hour)"}
            elif schedule_type == ScheduleType.DAILY.value:
                if schedule_time:
                    try:
                        hour, minute = map(int, schedule_time.split(':'))
                        if not (0 <= hour <= 23 and 0 <= minute <= 59):
                            raise ValueError()
                    except:
                        return {"success": False, "error": "Daily schedule time must be in HH:MM format"}
            
            task = task_manager.create_task(
                name=name.strip(),
                task_type=task_type,
                description=description.strip(),
                agent_id=agent_id,
                email_account_id=email_account_id,
                schedule_type=schedule_type,
                schedule_interval=schedule_interval,
                schedule_time=schedule_time,
                business_hours_only=business_hours_only,
                **kwargs
            )
            
            return {
                "success": True, 
                "task": task.to_dict(),
                "message": f"Task '{name}' created successfully"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_task(task_id: str) -> Dict:
        """Get task by ID"""
        try:
            task = task_manager.get_task(task_id)
            if task:
                task_dict = task.to_dict()
                # Add agent and email account names for display
                if task.agent_id:
                    agent = agent_manager.get_agent(task.agent_id)
                    task_dict["agent_name"] = agent.name if agent else "Unknown Agent"
                if task.email_account_id:
                    email_account = email_account_manager.get_account(task.email_account_id)
                    task_dict["email_account_name"] = email_account.email_address if email_account else "Unknown Account"
                
                return {"success": True, "task": task_dict}
            else:
                return {"success": False, "error": "Task not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_all_tasks() -> Dict:
        """Get all tasks with additional info"""
        try:
            tasks = task_manager.get_all_tasks()
            tasks_with_info = []
            
            for task in tasks:
                task_dict = task.to_dict()
                
                # Add agent name
                if task.agent_id:
                    agent = agent_manager.get_agent(task.agent_id)
                    task_dict["agent_name"] = agent.name if agent else "Unknown Agent"
                
                # Add email account name
                if task.email_account_id:
                    email_account = email_account_manager.get_account(task.email_account_id)
                    task_dict["email_account_name"] = email_account.email_address if email_account else "Unknown Account"
                
                # Add schedule description
                task_dict["schedule_description"] = TaskAPI._get_schedule_description(task)
                
                # Add status indicators
                task_dict["is_due"] = task.is_due()
                task_dict["success_rate"] = (task.success_count / max(task.run_count, 1)) * 100 if task.run_count > 0 else 0
                
                tasks_with_info.append(task_dict)
            
            return {
                "success": True, 
                "tasks": tasks_with_info,
                "count": len(tasks_with_info)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _get_schedule_description(task: Task) -> str:
        """Generate human-readable schedule description"""
        if task.schedule_type == ScheduleType.MINUTES.value:
            desc = f"Every {task.schedule_interval} minute{'s' if task.schedule_interval != 1 else ''}"
        elif task.schedule_type == ScheduleType.HOURLY.value:
            desc = f"Hourly at :{task.schedule_interval:02d}"
        elif task.schedule_type == ScheduleType.DAILY.value:
            time_str = task.schedule_time or "midnight"
            desc = f"Daily at {time_str}"
        else:
            desc = "Custom schedule"
        
        if task.business_hours_only:
            desc += " (business hours only)"
        
        return desc
    
    @staticmethod
    def update_task(task_id: str, **kwargs) -> Dict:
        """Update a task"""
        try:
            # Remove empty values and clean up data
            update_data = {k: v for k, v in kwargs.items() if v is not None}
            if "name" in update_data and not update_data["name"].strip():
                return {"success": False, "error": "Task name cannot be empty"}
            
            success = task_manager.update_task(task_id, **update_data)
            if success:
                task = task_manager.get_task(task_id)
                return {
                    "success": True, 
                    "task": task.to_dict(),
                    "message": "Task updated successfully"
                }
            else:
                return {"success": False, "error": "Task not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def delete_task(task_id: str) -> Dict:
        """Delete a task"""
        try:
            task = task_manager.get_task(task_id)
            if not task:
                return {"success": False, "error": "Task not found"}
            
            success = task_manager.delete_task(task_id)
            if success:
                return {
                    "success": True, 
                    "message": f"Task '{task.name}' deleted successfully"
                }
            else:
                return {"success": False, "error": "Failed to delete task"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def pause_task(task_id: str) -> Dict:
        """Pause a task"""
        try:
            success = task_manager.pause_task(task_id)
            if success:
                return {"success": True, "message": "Task paused successfully"}
            else:
                return {"success": False, "error": "Task not found or already paused"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def resume_task(task_id: str) -> Dict:
        """Resume a paused task"""
        try:
            success = task_manager.resume_task(task_id)
            if success:
                return {"success": True, "message": "Task resumed successfully"}
            else:
                return {"success": False, "error": "Task not found or not paused"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def run_task_now(task_id: str) -> Dict:
        """Run a task immediately"""
        try:
            result = task_scheduler.run_task_now(task_id)
            if result["success"]:
                return {
                    "success": True,
                    "message": "Task executed successfully",
                    "result": result.get("result", {})
                }
            else:
                return {
                    "success": False,
                    "error": f"Task execution failed: {result.get('error', 'Unknown error')}"
                }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_task_types() -> Dict:
        """Get available task types"""
        return {
            "success": True,
            "task_types": [
                {
                    "value": TaskType.EMAIL_CHECK.value,
                    "label": "Email Check",
                    "description": "Monitor email inbox and auto-reply"
                },
                {
                    "value": TaskType.GENERATE_REPORT.value,
                    "label": "Generate Report",
                    "description": "Generate periodic reports"
                },
                {
                    "value": TaskType.CLEANUP.value,
                    "label": "Cleanup",
                    "description": "Clean up old files and data"
                },
                {
                    "value": TaskType.SYNC.value,
                    "label": "Sync",
                    "description": "Synchronize data with external sources"
                }
            ]
        }
    
    @staticmethod
    def get_schedule_types() -> Dict:
        """Get available schedule types"""
        return {
            "success": True,
            "schedule_types": [
                {
                    "value": ScheduleType.MINUTES.value,
                    "label": "Every X Minutes",
                    "description": "Run every specified number of minutes"
                },
                {
                    "value": ScheduleType.HOURLY.value,
                    "label": "Hourly",
                    "description": "Run at specified minutes past each hour"
                },
                {
                    "value": ScheduleType.DAILY.value,
                    "label": "Daily",
                    "description": "Run once per day at specified time"
                }
            ]
        }
