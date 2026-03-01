from datetime import datetime
from flask import Flask, render_template
from models.db import db, init_db
from controllers.auth import auth_bp
from controllers.index import index_bp
from controllers.notifications import notifications_bp
from controllers.projects import projects_bp
from controllers.dashboard import dashboard
from controllers.htmx import htmx_bp

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

app.register_blueprint(index_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(dashboard)
app.register_blueprint(projects_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(htmx_bp)

init_db(app)


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