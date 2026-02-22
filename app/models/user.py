from flask_sqlalchemy import SQLAlchemy
from flask_security import UserMixin, RoleMixin
from datetime import datetime

db = SQLAlchemy()

# Association table for many-to-many relationship between users and roles
roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('user.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('role.id'))
)


class Role(db.Model, RoleMixin):
    """Role model for user permissions"""
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    
    def __repr__(self):
        return f'<Role {self.name}>'


class User(db.Model, UserMixin):
    """User model with authentication and lockout features"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean(), default=True)
    fs_uniquifier = db.Column(db.String(64), unique=True, nullable=False)
    
    # Trackable fields
    current_login_at = db.Column(db.DateTime())
    last_login_at = db.Column(db.DateTime())
    current_login_ip = db.Column(db.String(100))
    last_login_ip = db.Column(db.String(100))
    login_count = db.Column(db.Integer, default=0)
    
    # Account lockout fields
    failed_login_count = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime(), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime(), default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    roles = db.relationship('Role', secondary=roles_users,
                          backref=db.backref('users', lazy='dynamic'))
    
    def __repr__(self):
        return f'<User {self.email}>'
    
    def is_locked(self):
        """Check if account is currently locked"""
        if self.locked_until is None:
            return False
        return datetime.utcnow() < self.locked_until
    
    def increment_failed_login(self):
        """Increment failed login counter and lock if threshold reached"""
        self.failed_login_count += 1
        if self.failed_login_count >= 5:
            from datetime import timedelta
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
    
    def reset_failed_login(self):
        """Reset failed login counter on successful login"""
        self.failed_login_count = 0
        self.locked_until = None
