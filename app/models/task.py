import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

class TaskType(Enum):
    EMAIL_CHECK = "email_check"
    GENERATE_REPORT = "generate_report"
    CLEANUP = "cleanup"
    SYNC = "sync"

class TaskStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"

class ScheduleType(Enum):
    MINUTES = "minutes"
    HOURLY = "hourly"
    DAILY = "daily"
    BUSINESS_HOURS = "business_hours"

class Task:
    """Represents a scheduled task"""
    
    def __init__(self, task_id: str = None, name: str = "", task_type: str = TaskType.EMAIL_CHECK.value,
                 description: str = "", agent_id: str = "", email_account_id: str = "",
                 schedule_type: str = ScheduleType.MINUTES.value, schedule_interval: int = 15,
                 schedule_time: str = "", business_hours_only: bool = True,
                 status: str = TaskStatus.ACTIVE.value, created_at: str = None,
                 updated_at: str = None, last_run: str = None, next_run: str = None,
                 run_count: int = 0, success_count: int = 0, error_count: int = 0,
                 last_error: str = "", config: Dict = None):
        self.task_id = task_id or str(uuid.uuid4())
        self.name = name
        self.task_type = task_type
        self.description = description
        self.agent_id = agent_id
        self.email_account_id = email_account_id
        self.schedule_type = schedule_type
        self.schedule_interval = schedule_interval
        self.schedule_time = schedule_time  # For daily tasks: "09:00"
        self.business_hours_only = business_hours_only
        self.status = status
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.last_run = last_run
        self.next_run = next_run or self._calculate_next_run()
        self.run_count = run_count
        self.success_count = success_count
        self.error_count = error_count
        self.last_error = last_error
        self.config = config or {}
    
    def _calculate_next_run(self) -> str:
        """Calculate the next run time based on schedule"""
        now = datetime.now()
        
        if self.schedule_type == ScheduleType.MINUTES.value:
            next_run = now + timedelta(minutes=self.schedule_interval)
        elif self.schedule_type == ScheduleType.HOURLY.value:
            # Run at specific minutes past the hour
            next_hour = now.replace(minute=self.schedule_interval, second=0, microsecond=0)
            if next_hour <= now:
                next_hour += timedelta(hours=1)
            next_run = next_hour
        elif self.schedule_type == ScheduleType.DAILY.value:
            # Run at specific time daily
            if self.schedule_time:
                hour, minute = map(int, self.schedule_time.split(':'))
                next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)
            else:
                next_run = now + timedelta(days=1)
        else:
            next_run = now + timedelta(minutes=self.schedule_interval)
        
        # If business hours only, adjust to next business day if needed
        if self.business_hours_only:
            while next_run.weekday() >= 5:  # Skip weekends
                next_run += timedelta(days=1)
            
            # Ensure within business hours (9 AM - 5 PM)
            if next_run.hour < 9:
                next_run = next_run.replace(hour=9, minute=0)
            elif next_run.hour >= 17:
                next_run = next_run.replace(hour=9, minute=0) + timedelta(days=1)
                while next_run.weekday() >= 5:
                    next_run += timedelta(days=1)
        
        return next_run.isoformat()
    
    def is_due(self) -> bool:
        """Check if task is due to run"""
        if self.status != TaskStatus.ACTIVE.value:
            return False
        
        if not self.next_run:
            return True
        
        return datetime.now() >= datetime.fromisoformat(self.next_run)
    
    def update_after_run(self, success: bool, error_message: str = ""):
        """Update task statistics after execution"""
        self.last_run = datetime.now().isoformat()
        self.run_count += 1
        self.updated_at = datetime.now().isoformat()
        
        if success:
            self.success_count += 1
            self.last_error = ""
            self.status = TaskStatus.ACTIVE.value
        else:
            self.error_count += 1
            self.last_error = error_message
            # Don't automatically disable on error, just log it
        
        self.next_run = self._calculate_next_run()
    
    def to_dict(self) -> Dict:
        """Convert task to dictionary for JSON serialization"""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "task_type": self.task_type,
            "description": self.description,
            "agent_id": self.agent_id,
            "email_account_id": self.email_account_id,
            "schedule_type": self.schedule_type,
            "schedule_interval": self.schedule_interval,
            "schedule_time": self.schedule_time,
            "business_hours_only": self.business_hours_only,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "config": self.config
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        """Create task from dictionary"""
        return cls(**data)
    
    def update(self, **kwargs):
        """Update task properties and set updated_at timestamp"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()
        # Recalculate next run if schedule changed
        if any(key in kwargs for key in ['schedule_type', 'schedule_interval', 'schedule_time', 'business_hours_only']):
            self.next_run = self._calculate_next_run()


class TaskManager:
    """Manages scheduled tasks"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.path.join(
            os.path.dirname(__file__), "..", "config", "tasks.json"
        )
        self._tasks = {}
        self.load_tasks()
    
    def load_tasks(self):
        """Load tasks from storage"""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._tasks = {
                        task_id: Task.from_dict(task_data) 
                        for task_id, task_data in data.get("tasks", {}).items()
                    }
            except (json.JSONDecodeError, FileNotFoundError):
                self._tasks = {}
    
    def save_tasks(self):
        """Save tasks to storage"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        data = {
            "tasks": {
                task_id: task.to_dict() 
                for task_id, task in self._tasks.items()
            }
        }
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_task(self, name: str, task_type: str, description: str = "",
                   agent_id: str = "", email_account_id: str = "",
                   schedule_type: str = ScheduleType.MINUTES.value,
                   schedule_interval: int = 15, **kwargs) -> Task:
        """Create a new task"""
        task = Task(
            name=name,
            task_type=task_type,
            description=description,
            agent_id=agent_id,
            email_account_id=email_account_id,
            schedule_type=schedule_type,
            schedule_interval=schedule_interval,
            **kwargs
        )
        self._tasks[task.task_id] = task
        self.save_tasks()
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        return self._tasks.get(task_id)
    
    def get_all_tasks(self) -> List[Task]:
        """Get all tasks"""
        return list(self._tasks.values())
    
    def get_active_tasks(self) -> List[Task]:
        """Get all active tasks"""
        return [task for task in self._tasks.values() if task.status == TaskStatus.ACTIVE.value]
    
    def get_due_tasks(self) -> List[Task]:
        """Get all tasks that are due to run"""
        return [task for task in self.get_active_tasks() if task.is_due()]
    
    def get_tasks_by_type(self, task_type: str) -> List[Task]:
        """Get tasks by type"""
        return [task for task in self._tasks.values() if task.task_type == task_type]
    
    def get_tasks_by_agent(self, agent_id: str) -> List[Task]:
        """Get tasks assigned to specific agent"""
        return [task for task in self._tasks.values() if task.agent_id == agent_id]
    
    def update_task(self, task_id: str, **kwargs) -> bool:
        """Update a task"""
        task = self._tasks.get(task_id)
        if task:
            task.update(**kwargs)
            self.save_tasks()
            return True
        return False
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            self.save_tasks()
            return True
        return False
    
    def pause_task(self, task_id: str) -> bool:
        """Pause a task"""
        return self.update_task(task_id, status=TaskStatus.PAUSED.value)
    
    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task"""
        task = self._tasks.get(task_id)
        if task and task.status == TaskStatus.PAUSED.value:
            return self.update_task(task_id, status=TaskStatus.ACTIVE.value, next_run=task._calculate_next_run())
        return False
    
    def run_task_now(self, task_id: str) -> bool:
        """Mark task to run immediately"""
        return self.update_task(task_id, next_run=datetime.now().isoformat())


# Global task manager instance
task_manager = TaskManager()
