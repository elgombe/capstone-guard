from flask import Blueprint, jsonify, render_template
from controllers.dashboard import login_required, get_current_user

from models.db import Notification

notifications_bp = Blueprint('notifications_bp', __name__)

@notifications_bp.route('/notifications')
@login_required
def notifications():
    """Notifications page"""
    user = get_current_user()
    
    all_notifications = Notification.query.filter_by(user_id=user.id)\
        .order_by(Notification.created_at.desc())\
        .limit(50)\
        .all()
    
    return render_template('notifications.html', notifications=all_notifications)


@notifications_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark notification as read"""
    notification = Notification.query.get_or_404(notification_id)
    user = get_current_user()
    
    if notification.user_id != user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    notification.mark_as_read()
    
    return jsonify({'success': True})