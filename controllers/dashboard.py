from flask import Blueprint, render_template
from flask_jwt_extended import get_current_user
from flask_jwt_extended import get_current_user
from flask_login import login_required
from models.db import Project, Stream, Notification, UserRole, ProjectStatus

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/')
@login_required
def dashboard():
    """Dashboard page"""
    user = get_current_user()
    
    # Get statistics
    total_projects = Project.query.count()
    approved_projects = Project.query.filter_by(status=ProjectStatus.APPROVED).count()
    pending_projects = Project.query.filter_by(status=ProjectStatus.PENDING).count()
    total_streams = Stream.query.count()
    
    # Get user's projects
    user_projects = Project.query.filter_by(user_id=user.id)\
        .order_by(Project.submitted_at.desc())\
        .limit(5)\
        .all()
    
    # Get recent projects for admin/reviewer
    if user.role in [UserRole.ADMIN, UserRole.REVIEWER]:
        recent_projects = Project.query\
            .order_by(Project.submitted_at.desc())\
            .limit(10)\
            .all()
    else:
        recent_projects = []
    
    # Get unread notifications
    unread_notifications = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()
    
    return render_template('dashboard.html',
        user=user,
        total_projects=total_projects,
        approved_projects=approved_projects,
        pending_projects=pending_projects,
        total_streams=total_streams,
        user_projects=user_projects,
        recent_projects=recent_projects,
        unread_notifications=unread_notifications
    )

