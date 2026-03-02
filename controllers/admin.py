from flask import Blueprint, flash, redirect, render_template, request, url_for
from controllers.dashboard import login_required, get_current_user
from models.db import User, UserRole, db
import secrets
import string

admin_bp = Blueprint('admin_bp', __name__)


def admin_required(f):
    """Decorator that restricts a route to admins only."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.role != UserRole.ADMIN:
            flash('Access denied. Admins only.', 'danger')
            return redirect(url_for('dashboard.dash'))
        return f(*args, **kwargs)
    return decorated


def generate_temp_password(length=12):
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


# ── SETTINGS / REVIEWER MANAGEMENT ───────────────────────────────────────────

@admin_bp.route('/admin/settings')
@login_required
@admin_required
def settings():
    """Admin settings page — manage reviewer accounts."""
    reviewers = User.query.filter_by(role=UserRole.REVIEWER)\
        .order_by(User.created_at.desc()).all()
    return render_template('admin_settings.html', reviewers=reviewers)


@admin_bp.route('/admin/reviewers/create', methods=['POST'])
@login_required
@admin_required
def create_reviewer():
    """Create a new reviewer (lecturer) account."""
    full_name = request.form.get('full_name', '').strip()
    email     = request.form.get('email', '').strip().lower()

    if not full_name or not email:
        flash('Full name and email are required.', 'danger')
        return redirect(url_for('admin_bp.settings'))

    # Check for duplicate email
    if User.query.filter_by(email=email).first():
        flash(f'An account with the email "{email}" already exists.', 'danger')
        return redirect(url_for('admin_bp.settings'))

    temp_password = generate_temp_password()

    reviewer = User(
        full_name=full_name,
        email=email,
        role=UserRole.REVIEWER,
        is_active=True,
        is_verified=True,          # Admin-created accounts are pre-verified
    )
    reviewer.set_password(temp_password)
    db.session.add(reviewer)
    db.session.commit()

    flash(
        f'Reviewer account created for {full_name}. '
        f'Temporary password: {temp_password} — share this securely.',
        'success'
    )
    return redirect(url_for('admin_bp.settings'))


@admin_bp.route('/admin/reviewers/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_reviewer(user_id):
    """Activate or deactivate a reviewer account."""
    reviewer = User.query.get_or_404(user_id)

    if reviewer.role != UserRole.REVIEWER:
        flash('You can only manage reviewer accounts here.', 'danger')
        return redirect(url_for('admin_bp.settings'))

    reviewer.is_active = not reviewer.is_active
    db.session.commit()

    state = 'activated' if reviewer.is_active else 'deactivated'
    flash(f'{reviewer.full_name}\'s account has been {state}.', 'success')
    return redirect(url_for('admin_bp.settings'))


@admin_bp.route('/admin/reviewers/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_reviewer_password(user_id):
    """Reset a reviewer's password to a new temporary one."""
    reviewer = User.query.get_or_404(user_id)

    if reviewer.role != UserRole.REVIEWER:
        flash('You can only reset passwords for reviewer accounts.', 'danger')
        return redirect(url_for('admin_bp.settings'))

    temp_password = generate_temp_password()
    reviewer.set_password(temp_password)
    db.session.commit()

    flash(
        f'Password reset for {reviewer.full_name}. '
        f'New temporary password: {temp_password} — share this securely.',
        'success'
    )
    return redirect(url_for('admin_bp.settings'))


@admin_bp.route('/admin/reviewers/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_reviewer(user_id):
    """Permanently delete a reviewer account."""
    reviewer = User.query.get_or_404(user_id)

    if reviewer.role != UserRole.REVIEWER:
        flash('You can only delete reviewer accounts here.', 'danger')
        return redirect(url_for('admin_bp.settings'))

    name = reviewer.full_name
    db.session.delete(reviewer)
    db.session.commit()

    flash(f'Reviewer account for {name} has been permanently deleted.', 'success')
    return redirect(url_for('admin_bp.settings'))


# ── CHANGE PASSWORD (available to ALL logged-in users) ───────────────────────

@admin_bp.route('/account/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Allow any logged-in user to change their own password."""
    user = get_current_user()

    if request.method == 'POST':
        current_pw  = request.form.get('current_password', '')
        new_pw      = request.form.get('new_password', '')
        confirm_pw  = request.form.get('confirm_password', '')

        if not user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('admin_bp.change_password'))

        if len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
            return redirect(url_for('admin_bp.change_password'))

        if new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('admin_bp.change_password'))

        user.set_password(new_pw)
        db.session.commit()

        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard.dash'))

    return render_template('change_password.html', user=user)