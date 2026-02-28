from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, session, url_for
from difflib import SequenceMatcher
from models.db import Project, User, db, ProjectStatus, Notification, init_db
from controllers.auth import auth_bp
from controllers.index import index_bp
from controllers.dashboard import dashboard_bp

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(index_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)

init_db(app)

def login_required(f):
    """Decorator for routes that require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """Get the currently logged in user"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


def calculate_similarity(text1, text2):
    """Calculate similarity between two texts"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def find_similar_projects(title, description, threshold=None, exclude_id=None):
    """Find similar projects"""
    if threshold is None:
        threshold = app.config['SIMILARITY_THRESHOLD']
    
    similar_projects = []
    query = Project.query.filter_by(status=ProjectStatus.APPROVED)
    
    if exclude_id:
        query = query.filter(Project.id != exclude_id)
    
    all_projects = query.all()
    
    for project in all_projects:
        title_sim = calculate_similarity(title, project.title)
        desc_sim = calculate_similarity(description, project.description)
        
        overall_sim = (
            app.config['TITLE_SIMILARITY_WEIGHT'] * title_sim +
            app.config['DESCRIPTION_SIMILARITY_WEIGHT'] * desc_sim
        )
        
        if overall_sim >= threshold:
            similar_projects.append({
                'project': project,
                'title_similarity': title_sim,
                'description_similarity': desc_sim,
                'overall_similarity': overall_sim
            })
    
    similar_projects.sort(key=lambda x: x['overall_similarity'], reverse=True)
    return similar_projects


def create_notification(user_id, title, message, notification_type, related_project_id=None):
    """Create a notification"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        related_project_id=related_project_id
    )
    db.session.add(notification)
    db.session.commit()



@app.template_filter('status_color')
def status_color(status):
    """Get color class for status"""
    colors = {
        'approved': 'success',
        'pending': 'warning',
        'rejected': 'danger',
        'duplicate': 'danger',
        'under_review': 'info'
    }
    return colors.get(status.value if hasattr(status, 'value') else status, 'secondary')


@app.template_filter('timeago')
def timeago(dt):
    """Convert datetime to relative time"""
    if not dt:
        return ''
    
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 365:
        return f"{diff.days // 365} year{'s' if diff.days // 365 > 1 else ''} ago"
    elif diff.days > 30:
        return f"{diff.days // 30} month{'s' if diff.days // 30 > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hour{'s' if diff.seconds // 3600 > 1 else ''} ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minute{'s' if diff.seconds // 60 > 1 else ''} ago"
    else:
        return "just now"



@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run()