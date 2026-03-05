from flask import Blueprint, flash, redirect, render_template, request, url_for, session
from controllers.dashboard import login_required, get_current_user
from models.db import User, UserRole, Group, Stream, db
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


def _is_htmx():
    return request.headers.get('HX-Request') == 'true'


# ── SETTINGS SHELL ───────────────────────────────────────────────────────────

@admin_bp.route('/admin/settings')
@login_required
@admin_required
def settings():
    """Admin settings shell — renders layout; partials fill the panel."""
    tab = request.args.get('tab', 'reviewers')
    return render_template('admin_settings.html', active_tab=tab)


# ── PARTIALS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/admin/partials/reviewers')
@login_required
@admin_required
def partial_reviewers():
    reviewers = User.query.filter_by(role=UserRole.REVIEWER)\
        .order_by(User.created_at.desc()).all()
    return render_template('partials/settings_reviewers.html', reviewers=reviewers)


@admin_bp.route('/admin/partials/supervisors')
@login_required
@admin_required
def partial_supervisors():
    supervisors = User.query.filter_by(role=UserRole.SUPERVISOR)\
        .order_by(User.created_at.desc()).all()
    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    return render_template('partials/settings_supervisors.html',
                           supervisors=supervisors, streams=streams)


@admin_bp.route('/admin/partials/users')
@login_required
@admin_required
def partial_users():
    search      = request.args.get('search', '').strip()
    role_filter = request.args.get('role', '').strip()
    current_user = get_current_user()

    query = User.query
    if search:
        query = query.filter(
            (User.email.ilike(f'%{search}%')) |
            (User.full_name.ilike(f'%{search}%'))
        )
    if role_filter:
        try:
            query = query.filter_by(role=UserRole(role_filter))
        except ValueError:
            pass

    users = query.order_by(User.created_at.desc()).all()
    return render_template(
        'partials/settings_users.html',
        users=users,
        search=search,
        role_filter=role_filter,
        current_user=current_user,
        roles=UserRole,
    )


@admin_bp.route('/admin/partials/change-password', methods=['GET', 'POST'])
@login_required
def partial_change_password():
    user = get_current_user()

    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
        elif len(new_pw) < 8:
            flash('New password must be at least 8 characters.', 'danger')
        elif new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
        else:
            user.set_password(new_pw)
            db.session.commit()
            flash('Password changed successfully!', 'success')

    return render_template('partials/settings_change_password.html', user=user)


# ── REVIEWER ACTIONS (all return the reviewers partial) ──────────────────────

@admin_bp.route('/admin/reviewers/create', methods=['POST'])
@login_required
@admin_required
def create_reviewer():
    full_name = request.form.get('full_name', '').strip()
    email     = request.form.get('email', '').strip().lower()

    if not full_name or not email:
        flash('Full name and email are required.', 'danger')
    elif User.query.filter_by(email=email).first():
        flash(f'An account with the email "{email}" already exists.', 'danger')
    else:
        temp_password = generate_temp_password()
        reviewer = User(
            full_name=full_name,
            email=email,
            role=UserRole.REVIEWER,
            is_active=True,
            is_verified=True,
        )
        reviewer.set_password(temp_password)
        db.session.add(reviewer)
        db.session.commit()
        flash(
            f'Reviewer account created for {full_name}. '
            f'Temporary password: {temp_password} — share this securely.',
            'success'
        )

    reviewers = User.query.filter_by(role=UserRole.REVIEWER)\
        .order_by(User.created_at.desc()).all()
    return render_template('partials/settings_reviewers.html', reviewers=reviewers)


@admin_bp.route('/admin/reviewers/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_reviewer(user_id):
    reviewer = User.query.get_or_404(user_id)

    if reviewer.role != UserRole.REVIEWER:
        flash('You can only manage reviewer accounts here.', 'danger')
    else:
        reviewer.is_active = not reviewer.is_active
        db.session.commit()
        state = 'activated' if reviewer.is_active else 'deactivated'
        flash(f'{reviewer.full_name}\'s account has been {state}.', 'success')

    reviewers = User.query.filter_by(role=UserRole.REVIEWER)\
        .order_by(User.created_at.desc()).all()
    return render_template('partials/settings_reviewers.html', reviewers=reviewers)


@admin_bp.route('/admin/reviewers/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_reviewer_password(user_id):
    reviewer = User.query.get_or_404(user_id)

    if reviewer.role != UserRole.REVIEWER:
        flash('You can only reset passwords for reviewer accounts.', 'danger')
    else:
        temp_password = generate_temp_password()
        reviewer.set_password(temp_password)
        db.session.commit()
        flash(
            f'Password reset for {reviewer.full_name}. '
            f'New temporary password: {temp_password} — share this securely.',
            'success'
        )

    reviewers = User.query.filter_by(role=UserRole.REVIEWER)\
        .order_by(User.created_at.desc()).all()
    return render_template('partials/settings_reviewers.html', reviewers=reviewers)


@admin_bp.route('/admin/reviewers/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_reviewer(user_id):
    reviewer = User.query.get_or_404(user_id)

    if reviewer.role != UserRole.REVIEWER:
        flash('You can only delete reviewer accounts here.', 'danger')
    else:
        name = reviewer.full_name
        db.session.delete(reviewer)
        db.session.commit()
        flash(f'Reviewer account for {name} has been permanently deleted.', 'success')

    reviewers = User.query.filter_by(role=UserRole.REVIEWER)\
        .order_by(User.created_at.desc()).all()
    return render_template('partials/settings_reviewers.html', reviewers=reviewers)


# ── USER ROLE MANAGEMENT ──────────────────────────────────────────────────────

@admin_bp.route('/admin/users/<int:user_id>/change-role', methods=['POST'])
@login_required
@admin_required
def change_user_role(user_id):
    current_user = get_current_user()
    target       = User.query.get_or_404(user_id)

    if target.id == current_user.id:
        flash('You cannot change your own role.', 'danger')
    else:
        new_role_value = request.form.get('role', '').strip()
        try:
            new_role   = UserRole(new_role_value)
            old_role   = target.role.value
            target.role = new_role
            db.session.commit()
            flash(
                f'{target.full_name}\'s role changed from {old_role} to {new_role.value}.',
                'success'
            )
        except ValueError:
            flash('Invalid role selected.', 'danger')

    # Re-render the users partial preserving any active search/filter
    search      = request.form.get('search', '').strip()
    role_filter = request.form.get('role_filter', '').strip()
    query = User.query
    if search:
        query = query.filter(
            (User.email.ilike(f'%{search}%')) |
            (User.full_name.ilike(f'%{search}%'))
        )
    if role_filter:
        try:
            query = query.filter_by(role=UserRole(role_filter))
        except ValueError:
            pass

    users = query.order_by(User.created_at.desc()).all()
    return render_template(
        'partials/settings_users.html',
        users=users,
        search=search,
        role_filter=role_filter,
        current_user=current_user,
        roles=UserRole,
    )


# ── SUPERVISOR ACTIONS ────────────────────────────────────────────────────────

def _render_supervisors():
    supervisors = User.query.filter_by(role=UserRole.SUPERVISOR)\
        .order_by(User.created_at.desc()).all()
    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    return render_template('partials/settings_supervisors.html',
                           supervisors=supervisors, streams=streams)


@admin_bp.route('/admin/supervisors/create', methods=['POST'])
@login_required
@admin_required
def create_supervisor():
    full_name = request.form.get('full_name', '').strip()
    email     = request.form.get('email', '').strip().lower()

    if not full_name or not email:
        flash('Full name and email are required.', 'danger')
    elif User.query.filter_by(email=email).first():
        flash(f'An account with "{email}" already exists.', 'danger')
    else:
        temp_password = generate_temp_password()
        supervisor = User(
            full_name=full_name,
            email=email,
            role=UserRole.SUPERVISOR,
            is_active=True,
            is_verified=True,
        )
        supervisor.set_password(temp_password)
        db.session.add(supervisor)
        db.session.commit()
        flash(
            f'Supervisor account created for {full_name}. '
            f'Temporary password: {temp_password} — share this securely.',
            'success'
        )
    return _render_supervisors()


@admin_bp.route('/admin/supervisors/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_supervisor(user_id):
    supervisor = User.query.get_or_404(user_id)
    if supervisor.role != UserRole.SUPERVISOR:
        flash('Not a supervisor account.', 'danger')
    else:
        supervisor.is_active = not supervisor.is_active
        db.session.commit()
        state = 'activated' if supervisor.is_active else 'deactivated'
        flash(f'{supervisor.full_name} has been {state}.', 'success')
    return _render_supervisors()


@admin_bp.route('/admin/supervisors/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_supervisor_password(user_id):
    supervisor = User.query.get_or_404(user_id)
    if supervisor.role != UserRole.SUPERVISOR:
        flash('Not a supervisor account.', 'danger')
    else:
        temp_password = generate_temp_password()
        supervisor.set_password(temp_password)
        db.session.commit()
        flash(
            f'Password reset for {supervisor.full_name}. '
            f'New temporary password: {temp_password} — share this securely.',
            'success'
        )
    return _render_supervisors()


@admin_bp.route('/admin/supervisors/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_supervisor(user_id):
    supervisor = User.query.get_or_404(user_id)
    if supervisor.role != UserRole.SUPERVISOR:
        flash('Not a supervisor account.', 'danger')
    else:
        name = supervisor.full_name
        db.session.delete(supervisor)
        db.session.commit()
        flash(f'Supervisor account for {name} permanently deleted.', 'success')
    return _render_supervisors()


# ── LEGACY REDIRECT — keeps old direct links working ────────────────────────

@admin_bp.route('/account/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Redirect old direct URL to the settings shell on the password tab."""
    return redirect(url_for('admin_bp.settings') + '?tab=password')
