from flask import Blueprint, flash, redirect, render_template, request, url_for, session
from controllers.dashboard import login_required, get_current_user
from models.db import User, UserRole, Group, Stream, db

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


def _is_htmx():
    return request.headers.get('HX-Request') == 'true'


# ── SETTINGS SHELL ───────────────────────────────────────────────────────────

@admin_bp.route('/admin/settings')
@login_required
@admin_required
def settings():
    """Admin settings shell — renders layout; partials fill the panel."""
    tab = request.args.get('tab', 'supervisors')
    return render_template('admin_settings.html', active_tab=tab)


# ── PARTIALS ─────────────────────────────────────────────────────────────────

@admin_bp.route('/settings/partial/supervisors')
@login_required
@admin_required
def partial_supervisors():
    from models.db import User, UserRole
    supervisors = User.query.filter_by(
        role=UserRole.SUPERVISOR, is_active=True
    ).order_by(User.full_name).all()
 
    # All active students
    all_students = User.query.filter_by(
        role=UserRole.STUDENT, is_active=True
    ).order_by(User.full_name).all()
 
    assigned_students   = [s for s in all_students if s.supervisor_id]
    unassigned_students = [s for s in all_students if not s.supervisor_id]
 
    return render_template(
        'partials/settings_supervisors.html',
        supervisors=supervisors,
        assigned_students=assigned_students,
        unassigned_students=unassigned_students,
    )

@admin_bp.route('/settings/assign-supervisor', methods=['POST'])
@login_required
@admin_required
def assign_supervisor():
    from models.db import User, UserRole, db
    student_id    = request.form.get('student_id', type=int)
    supervisor_id = request.form.get('supervisor_id', type=int)  # None = remove
 
    student = User.query.get_or_404(student_id)
    if student.role != UserRole.STUDENT:
        flash('Only students can be assigned a supervisor.', 'danger')
        return redirect(url_for('admin_bp.settings') + '?tab=supervisors')
 
    if supervisor_id:
        sup = User.query.get_or_404(supervisor_id)
        if sup.role != UserRole.SUPERVISOR:
            flash('Selected user is not a supervisor.', 'danger')
            return redirect(url_for('admin_bp.settings') + '?tab=supervisors')
        student.supervisor_id = supervisor_id
        flash(f'{student.full_name} assigned to {sup.full_name}.', 'success')
    else:
        student.supervisor_id = None
        flash(f'Supervisor removed from {student.full_name}.', 'success')
 
    db.session.commit()
 
    # Re-render the supervisors partial via HTMX
    return redirect(url_for('admin_bp.partial_supervisors'))

@admin_bp.route('/admin/partials/users')
@login_required
@admin_required
def partial_users():
    search       = request.args.get('search', '').strip()
    role_filter  = request.args.get('role', '').strip()
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
            new_role    = UserRole(new_role_value)
            old_role    = target.role.value
            target.role = new_role
            db.session.commit()
            flash(
                f"{target.full_name}'s role changed from {old_role} to {new_role.value}.",
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
        supervisor = User(
            full_name=full_name,
            email=email,
            role=UserRole.SUPERVISOR,
            is_active=True,
            is_verified=True,
        )
        db.session.add(supervisor)
        db.session.commit()
        flash(
            f'Supervisor account created for {full_name}. '
            f'They can now sign in with their Google account.',
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