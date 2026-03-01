from flask import Blueprint, flash, redirect, render_template, session, url_for
from models.db import Project, Stream, Notification, UserRole, ProjectStatus, User
from functools import wraps

dashboard = Blueprint('dashboard', __name__)

def login_required(f):
    """Decorator for routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth_bp.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    """Get the currently logged in user"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

@dashboard.route('/dashboard')
@login_required
def dash():
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

