"""
Database Models
Using Flask-SQLAlchemy ORM
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import enum

db = SQLAlchemy()


# Enums for Status Fields
class ProjectStatus(enum.Enum):
    """Project submission status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    UNDER_REVIEW = "under_review"


class UserRole(enum.Enum):
    """User roles in the system"""
    STUDENT = "student"
    ADMIN = "admin"
    REVIEWER = "reviewer"


# Models
class User(db.Model):
    """
    User model for authentication and profile management
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)  # Nullable for OAuth users
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.Enum(UserRole), default=UserRole.STUDENT, nullable=False)
    
    # OAuth fields
    github_id = db.Column(db.String(100), unique=True, nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    
    # Profile information
    profile_picture = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Account status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    projects = db.relationship('Project', foreign_keys='Project.user_id', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    reviewed_projects = db.relationship('Project', foreign_keys='Project.reviewed_by_id', backref='reviewer', lazy='dynamic')
    comments = db.relationship('Comment', backref='author', lazy='dynamic', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set user password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password against hash"""
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary"""
        return {
            'id': self.id,
            'email': self.email,
            'full_name': self.full_name,
            'role': self.role.value,
            'profile_picture': self.profile_picture,
            'bio': self.bio,
            'created_at': self.created_at.isoformat(),
            'is_active': self.is_active,
            'is_verified': self.is_verified
        }
    
    def __repr__(self):
        return f'<User {self.email}>'


class Stream(db.Model):
    """
    Academic stream/cohort model
    """
    __tablename__ = 'streams'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.String(20), nullable=True)  # e.g., "Fall", "Spring"
    
    # Stream details
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    projects = db.relationship('Project', backref='stream', lazy='dynamic')
    
    def to_dict(self):
        """Convert stream to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'year': self.year,
            'semester': self.semester,
            'description': self.description,
            'is_active': self.is_active,
            'project_count': self.projects.count()
        }
    
    def __repr__(self):
        return f'<Stream {self.name}>'


class Project(db.Model):
    """
    Project submission model - core entity
    """
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Project details
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    
    # Foreign keys
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    stream_id = db.Column(db.Integer, db.ForeignKey('streams.id'), nullable=False, index=True)
    
    # Status and workflow
    status = db.Column(db.Enum(ProjectStatus), default=ProjectStatus.PENDING, nullable=False, index=True)
    
    # Additional project information
    technologies = db.Column(db.Text, nullable=True)  # JSON or comma-separated
    github_url = db.Column(db.String(255), nullable=True)
    demo_url = db.Column(db.String(255), nullable=True)
    documentation_url = db.Column(db.String(255), nullable=True)
    
    # Duplicate detection
    is_flagged_duplicate = db.Column(db.Boolean, default=False, nullable=False)
    duplicate_of_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    similarity_score = db.Column(db.Float, nullable=True)  # Overall similarity score
    
    # Review information
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    
    # Timestamps
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    duplicate_of = db.relationship('Project', remote_side=[id], backref='duplicates')
    similarity_records = db.relationship('SimilarityRecord', foreign_keys='SimilarityRecord.project_id', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    attachments = db.relationship('Attachment', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, include_author=True, include_stream=True):
        """Convert project to dictionary"""
        data = {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status.value,
            'technologies': self.technologies,
            'github_url': self.github_url,
            'demo_url': self.demo_url,
            'documentation_url': self.documentation_url,
            'is_flagged_duplicate': self.is_flagged_duplicate,
            'similarity_score': self.similarity_score,
            'submitted_at': self.submitted_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        
        if include_author and self.author:
            data['author'] = {
                'id': self.author.id,
                'name': self.author.full_name,
                'email': self.author.email
            }
        
        if include_stream and self.stream:
            data['stream'] = {
                'id': self.stream.id,
                'name': self.stream.name
            }
        
        if self.reviewer:
            data['reviewer'] = {
                'id': self.reviewer.id,
                'name': self.reviewer.full_name
            }
            data['reviewed_at'] = self.reviewed_at.isoformat() if self.reviewed_at else None
        
        return data
    
    def __repr__(self):
        return f'<Project {self.title}>'


class SimilarityRecord(db.Model):
    """
    Track similarity between projects for duplicate detection
    """
    __tablename__ = 'similarity_records'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Projects being compared
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    similar_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    
    # Similarity scores
    title_similarity = db.Column(db.Float, nullable=False)  # 0.0 to 1.0
    description_similarity = db.Column(db.Float, nullable=False)  # 0.0 to 1.0
    overall_similarity = db.Column(db.Float, nullable=False)  # 0.0 to 1.0
    
    # Algorithm used
    algorithm = db.Column(db.String(50), default='sequence_matcher', nullable=False)
    
    # Timestamp
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    similar_project = db.relationship('Project', foreign_keys=[similar_project_id], backref='similarity_checks')
    
    # Unique constraint to prevent duplicate records
    __table_args__ = (
        db.UniqueConstraint('project_id', 'similar_project_id', name='unique_similarity_pair'),
        db.Index('idx_similarity_score', 'overall_similarity'),
    )
    
    def to_dict(self):
        """Convert similarity record to dictionary"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'similar_project_id': self.similar_project_id,
            'title_similarity': round(self.title_similarity * 100, 2),
            'description_similarity': round(self.description_similarity * 100, 2),
            'overall_similarity': round(self.overall_similarity * 100, 2),
            'algorithm': self.algorithm,
            'calculated_at': self.calculated_at.isoformat()
        }
    
    def __repr__(self):
        return f'<SimilarityRecord P{self.project_id} <-> P{self.similar_project_id}>'


class Comment(db.Model):
    """
    Comments on projects for feedback and discussion
    """
    __tablename__ = 'comments'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign keys
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True)  # For nested comments
    
    # Content
    content = db.Column(db.Text, nullable=False)
    
    # Status
    is_edited = db.Column(db.Boolean, default=False, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    
    def to_dict(self, include_replies=False):
        """Convert comment to dictionary"""
        data = {
            'id': self.id,
            'project_id': self.project_id,
            'content': self.content if not self.is_deleted else '[Deleted]',
            'author': {
                'id': self.author.id,
                'name': self.author.full_name,
                'profile_picture': self.author.profile_picture
            },
            'is_edited': self.is_edited,
            'is_deleted': self.is_deleted,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
        
        if include_replies:
            data['replies'] = [reply.to_dict() for reply in self.replies.filter_by(is_deleted=False).all()]
        
        return data
    
    def __repr__(self):
        return f'<Comment {self.id} on Project {self.project_id}>'


class Attachment(db.Model):
    """
    File attachments for projects
    """
    __tablename__ = 'attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False, index=True)
    
    # File information
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)  # in bytes
    mime_type = db.Column(db.String(100), nullable=False)
    
    # File type category
    file_type = db.Column(db.String(50), nullable=False)  # e.g., 'document', 'image', 'video'
    
    # Uploaded by
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Timestamp
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    uploader = db.relationship('User', backref='uploads')
    
    def to_dict(self):
        """Convert attachment to dictionary"""
        return {
            'id': self.id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'file_type': self.file_type,
            'uploaded_at': self.uploaded_at.isoformat(),
            'uploader': {
                'id': self.uploader.id,
                'name': self.uploader.full_name
            }
        }
    
    def __repr__(self):
        return f'<Attachment {self.original_filename}>'


class Notification(db.Model):
    """
    User notifications for system events
    """
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Notification details
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(50), nullable=False)  # e.g., 'project_approved', 'duplicate_found'
    
    # Related entity (optional)
    related_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    
    # Status
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Relationship
    related_project = db.relationship('Project', backref='notifications')
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()
        db.session.commit()
    
    def to_dict(self):
        """Convert notification to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'notification_type': self.notification_type,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'related_project_id': self.related_project_id
        }
    
    def __repr__(self):
        return f'<Notification {self.id} for User {self.user_id}>'


class AuditLog(db.Model):
    """
    Audit trail for important system actions
    """
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Who performed the action
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    
    # Action details
    action = db.Column(db.String(100), nullable=False, index=True)  # e.g., 'project_created', 'status_changed'
    entity_type = db.Column(db.String(50), nullable=False)  # e.g., 'project', 'user'
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    
    # Change details
    old_value = db.Column(db.Text, nullable=True)  # JSON or text
    new_value = db.Column(db.Text, nullable=True)  # JSON or text
    
    # Additional context
    ip_address = db.Column(db.String(45), nullable=True)  # IPv6 compatible
    user_agent = db.Column(db.String(255), nullable=True)
    
    # Timestamp
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Relationship
    user = db.relationship('User', backref='audit_logs')
    
    def to_dict(self):
        """Convert audit log to dictionary"""
        return {
            'id': self.id,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'old_value': self.old_value,
            'new_value': self.new_value,
            'created_at': self.created_at.isoformat(),
            'user': {
                'id': self.user.id,
                'name': self.user.full_name
            } if self.user else None
        }
    
    def __repr__(self):
        return f'<AuditLog {self.action} on {self.entity_type}#{self.entity_id}>'


# Helper function to initialize the database
def init_db(app):
    """
    Initialize database with app context
    """
    db.init_app(app)
    
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Create default admin user if not exists
        admin = User.query.filter_by(email='admin@binary.com').first()
        if not admin:
            admin = User(
                email='admin@binary.com',
                full_name='System Administrator',
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True
            )
            admin.set_password('admin123')  # Change this in production!
            db.session.add(admin)
        
        # Create default streams if not exists
        if Stream.query.count() == 0:
            streams = [
                Stream(name='2024 Stream A', year=2024, semester='Spring', is_active=True),
                Stream(name='2024 Stream B', year=2024, semester='Fall', is_active=True),
                Stream(name='2023 Stream A', year=2023, semester='Spring', is_active=False),
                Stream(name='2023 Stream B', year=2023, semester='Fall', is_active=False),
            ]
            db.session.add_all(streams)
        
        db.session.commit()
        print("✅ Database initialized successfully!")


# Export all models
__all__ = [
    'db',
    'User',
    'Stream',
    'Project',
    'SimilarityRecord',
    'Comment',
    'Attachment',
    'Notification',
    'AuditLog',
    'ProjectStatus',
    'UserRole',
    'init_db'
]
