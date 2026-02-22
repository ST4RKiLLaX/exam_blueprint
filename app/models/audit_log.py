from datetime import datetime
import json
from app.models.user import db


class AuditLog(db.Model):
    """Audit log for tracking admin actions"""
    __tablename__ = 'audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime(), default=datetime.utcnow, nullable=False)
    admin_user = db.Column(db.String(255), nullable=False)  # Email of admin who performed action
    action_type = db.Column(db.String(50), nullable=False)  # user_created, password_reset, etc.
    target_user = db.Column(db.String(255), nullable=False)  # Email of affected user
    ip_address = db.Column(db.String(100))
    details = db.Column(db.Text())  # JSON field for additional context
    
    def __repr__(self):
        return f'<AuditLog {self.action_type} by {self.admin_user} on {self.target_user}>'
    
    @staticmethod
    def log_action(admin_email, action_type, target_email, ip_address=None, **kwargs):
        """
        Log an admin action
        
        Args:
            admin_email: Email of admin performing the action
            action_type: Type of action (user_created, password_reset, role_changed, etc.)
            target_email: Email of user being affected
            ip_address: IP address of admin
            **kwargs: Additional details to store in JSON format
        """
        details_json = json.dumps(kwargs) if kwargs else None
        
        log_entry = AuditLog(
            admin_user=admin_email,
            action_type=action_type,
            target_user=target_email,
            ip_address=ip_address,
            details=details_json
        )
        
        db.session.add(log_entry)
        db.session.commit()
        
        return log_entry
    
    def get_details(self):
        """Parse JSON details field"""
        if self.details:
            try:
                return json.loads(self.details)
            except json.JSONDecodeError:
                return {}
        return {}
