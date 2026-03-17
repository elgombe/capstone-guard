"""
Database Models
Using Flask-SQLAlchemy ORM
"""

import os

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
    SUPERVISOR = "supervisor"


class ProjectCategory(enum.Enum):
    """Project category — determines workflow"""
    HIT200 = "hit200"   # Team project (up to 5), requires a supervisor group
    HIT400 = "hit400"   # Solo project, no group needed


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
    semester = db.Column(db.String(20), nullable=True)  # e.g., "August"
    
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


# Association table: which students belong to which HIT200 group
group_members = db.Table(
    'group_members',
    db.Column('group_id',  db.Integer, db.ForeignKey('groups.id'),  primary_key=True),
    db.Column('student_id', db.Integer, db.ForeignKey('users.id'),   primary_key=True),
)


class Group(db.Model):
    """
    HIT200 project group — supervised team of up to 5 students.
    A supervisor can manage multiple groups.
    """
    __tablename__ = 'groups'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    stream_id     = db.Column(db.Integer, db.ForeignKey('streams.id'), nullable=False, index=True)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    supervisor = db.relationship('User', foreign_keys=[supervisor_id], backref='supervised_groups')
    stream     = db.relationship('Stream', backref='groups')
    members    = db.relationship('User', secondary=group_members, backref='groups')
    projects   = db.relationship('Project', foreign_keys='Project.group_id', backref='group', lazy='dynamic')

    def __repr__(self):
        return f'<Group {self.name}>'


class Project(db.Model):
    """
    Project submission model - core entity
    """
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Project details
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)

    # Category: HIT200 (team) or HIT400 (solo)
    category  = db.Column(db.Enum(ProjectCategory), default=ProjectCategory.HIT400, nullable=False, index=True)

    # For HIT200 projects — which group submitted this
    group_id  = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True, index=True)

    # Foreign keys
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
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
    
# ── STEP 1 & 2  ──────────────────────────────────────────────────────────────
# Paste inside your db.py after ProjectCategory enum

import enum

class ChapterStatus(enum.Enum):
    """Lifecycle of a single chapter submission"""
    LOCKED        = "locked"        # not yet unlocked
    UNLOCKED      = "unlocked"      # student may submit
    SUBMITTED     = "submitted"     # student has submitted, awaiting review
    UNDER_REVIEW  = "under_review"  # supervisor actively reviewing
    NEEDS_REVISION= "needs_revision"# supervisor returned feedback
    APPROVED      = "approved"      # supervisor approved → next unlocked


# ── STEP 3  ──────────────────────────────────────────────────────────────────
# Chapters meta-table (one row per chapter slot per project)

CHAPTER_DEFINITIONS = [
    # (order, slug, display_name, description_hint)
    (1, "introduction",          "Chapter 1 – Introduction",           "Background, problem statement, objectives, scope and significance."),
    (2, "requirements_analysis", "Chapter 2 – Requirements Analysis",  "Functional / non-functional requirements, use-case diagrams, stakeholder analysis."),
    (3, "design",                "Chapter 3 – System Design",          "Architecture, ER diagrams, UI wireframes, technology justification."),
    (4, "implementation",        "Chapter 4 – Implementation",         "Code walk-through, screenshots, key algorithms, deployment details."),
    (5, "system_testing",        "Chapter 5 – System Testing",         "Test plan, test cases, results, bug tracking, user acceptance."),
    (6, "conclusion",            "Chapter 6 – Conclusion",             "Summary, achievements, limitations, future work, recommendations."),
]


class Chapter(db.Model):
    """
    One chapter slot per project.  Created automatically when a
    project passes the AI similarity check (step 0).

    Chapter 1 starts UNLOCKED; chapters 2-6 start LOCKED.
    Each chapter is unlocked when its predecessor is APPROVED.
    """
    __tablename__ = 'chapters'

    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'),
                           nullable=False, index=True)

    # Which chapter (1-6)
    order      = db.Column(db.Integer, nullable=False)           # 1..6
    slug       = db.Column(db.String(50), nullable=False)        # e.g. 'introduction'
    title      = db.Column(db.String(120), nullable=False)       # display name

    # Current state
    status     = db.Column(db.Enum(ChapterStatus),
                           default=ChapterStatus.LOCKED,
                           nullable=False, index=True)

    # Student's latest submission text / content
    content    = db.Column(db.Text, nullable=True)

    # Optional file attachment (PDF, DOCX, etc.)
    file_url   = db.Column(db.String(500), nullable=True)
    file_name  = db.Column(db.String(255), nullable=True)

    # Who submitted / when
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                                nullable=True)
    submitted_at    = db.Column(db.DateTime, nullable=True)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow, nullable=False)

    # When the chapter was approved (for audit)
    approved_at     = db.Column(db.DateTime, nullable=True)
    approved_by_id  = db.Column(db.Integer, db.ForeignKey('users.id'),
                                nullable=True)

    # Relationships
    project      = db.relationship('Project',  foreign_keys=[project_id],
                                   backref=db.backref('chapters',
                                                       order_by='Chapter.order',
                                                       lazy='dynamic'))
    submitter    = db.relationship('User', foreign_keys=[submitted_by_id])
    approver     = db.relationship('User', foreign_keys=[approved_by_id])
    reviews      = db.relationship('ChapterReview',
                                   backref='chapter',
                                   lazy='dynamic',
                                   cascade='all, delete-orphan',
                                   order_by='ChapterReview.created_at.desc()')

    __table_args__ = (
        db.UniqueConstraint('project_id', 'order', name='uq_chapter_project_order'),
    )

    @property
    def is_editable_by(self):
        """Returns True if the chapter can be edited (not locked / approved)."""
        return self.status in (ChapterStatus.UNLOCKED,
                               ChapterStatus.NEEDS_REVISION)

    def __repr__(self):
        return f'<Chapter {self.order} [{self.status.value}] for Project {self.project_id}>'


# ── STEP 4  ──────────────────────────────────────────────────────────────────

class ChapterReview(db.Model):
    """
    Supervisor feedback on a specific chapter submission.
    Multiple review rounds are stored (full history).
    """
    __tablename__ = 'chapter_reviews'

    id         = db.Column(db.Integer, primary_key=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapters.id'),
                           nullable=False, index=True)
    reviewer_id= db.Column(db.Integer, db.ForeignKey('users.id'),
                           nullable=False, index=True)

    # The decision on this round
    decision   = db.Column(db.String(20), nullable=False)  # 'approved' | 'needs_revision'

    # Feedback text
    feedback   = db.Column(db.Text, nullable=False)

    # Round number (1st review = 1, second = 2, …)
    round_num  = db.Column(db.Integer, default=1, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    reviewer   = db.relationship('User', backref='chapter_reviews')

    def __repr__(self):
        return f'<ChapterReview chapter={self.chapter_id} round={self.round_num} decision={self.decision}>'


# ── STEP 5  ──────────────────────────────────────────────────────────────────
# Add these TWO columns to your existing Project model

"""
    # Chapter-workflow tracking (added fields)
    ai_check_passed   = db.Column(db.Boolean, default=False, nullable=False)
    # True once AI similarity scan passes and chapters are created
    chapters_unlocked = db.Column(db.Boolean, default=False, nullable=False)
"""

# ── STEP 6  ──────────────────────────────────────────────────────────────────
# Update __all__ in db.py:
"""
    'Chapter',
    'ChapterReview',
    'ChapterStatus',
    'CHAPTER_DEFINITIONS',
"""


# ── HELPER  ──────────────────────────────────────────────────────────────────

def create_chapters_for_project(project_id):
    """
    Call this once, right after the AI check passes.
    Creates 6 Chapter rows: ch1 = UNLOCKED, ch2-6 = LOCKED.
    """
    for order, slug, title, _ in CHAPTER_DEFINITIONS:
        status = ChapterStatus.UNLOCKED if order == 1 else ChapterStatus.LOCKED
        ch = Chapter(
            project_id=project_id,
            order=order,
            slug=slug,
            title=title,
            status=status,
        )
        db.session.add(ch)
    db.session.commit()


def unlock_next_chapter(project_id, current_order):
    """
    After chapter `current_order` is approved, unlock chapter `current_order + 1`.
    Returns the next Chapter object or None if this was the last chapter.
    """
    next_ch = Chapter.query.filter_by(
        project_id=project_id,
        order=current_order + 1
    ).first()
    if next_ch and next_ch.status == ChapterStatus.LOCKED:
        next_ch.status = ChapterStatus.UNLOCKED
        db.session.commit()
    return next_ch



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
        admin = User.query.filter_by(email=os.environ.get('ADMIN_EMAIL')).first()
        if not admin:
            admin = User(
                email=os.environ.get('ADMIN_EMAIL'),
                full_name='System Administrator',
                role=UserRole.ADMIN,
                is_active=True,
                is_verified=True
            )
            admin.set_password(os.environ.get('ADMIN_PASSWORD'))  # Change this in production!
            db.session.add(admin)
        
        # Create default streams if not exists
        if Stream.query.count() == 0:
            programs = [
                'ISE', 'IIT', 'ICS', 'ISA', 'SPT', 'SFP', 'SBT',
                'EPT', 'EIM', 'EEE', 'ECP', 'BFA', 'BFE', 'BEC'
            ]
            current_year = datetime.utcnow().year
            years = list(range(2023, current_year + 1))  # 2023 up to current year
            streams = []
            for year in years:
                for program in programs:
                    streams.append(Stream(
                        name=f'{year} {program}',
                        year=year,
                        semester='August',
                        is_active=(year == current_year)  # Only current year is active
                    ))
            db.session.add_all(streams)
        
        db.session.commit()
        print("✅ Database initialized successfully!")


# Export all models
__all__ = [
    'db',
    'User',
    'Stream',
    'Group',
    'group_members',
    'Project',
    'SimilarityRecord',
    'Comment',
    'Attachment',
    'Notification',
    'AuditLog',
    'ProjectStatus',
    'ProjectCategory',
    'UserRole',
    'init_db'
]