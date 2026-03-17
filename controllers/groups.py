from flask import Blueprint, flash, redirect, render_template, request, url_for, session
from controllers.dashboard import login_required, get_current_user
from models.db import db, User, UserRole, Group, Stream, group_members

groups_bp = Blueprint('groups_bp', __name__)


def supervisor_required(f):
    """Decorator: allows supervisors and admins only."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user or user.role not in [UserRole.SUPERVISOR, UserRole.ADMIN]:
            flash('Access denied. Supervisors only.', 'danger')
            return redirect(url_for('dashboard.dash'))
        return f(*args, **kwargs)
    return decorated


# ── SUPERVISOR: MY GROUPS ─────────────────────────────────────────────────────

@groups_bp.route('/groups')
@login_required
@supervisor_required
def my_groups():
    """Supervisor's group management page."""
    user = get_current_user()
    if user.role == UserRole.ADMIN:
        groups = Group.query.order_by(Group.created_at.desc()).all()
    else:
        groups = Group.query.filter_by(supervisor_id=user.id)\
            .order_by(Group.created_at.desc()).all()

    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    students = User.query.filter_by(role=UserRole.STUDENT, is_active=True)\
        .order_by(User.full_name).all()
    return render_template('groups.html',
                           groups=groups, streams=streams, students=students, user=user)


@groups_bp.route('/groups/create', methods=['POST'])
@login_required
@supervisor_required
def create_group():
    """Create a new HIT200 group."""
    user      = get_current_user()
    name      = request.form.get('name', '').strip()
    stream_id = request.form.get('stream_id', type=int)

    if not name or not stream_id:
        flash('Group name and stream are required.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    # Admins can create for any supervisor; supervisors create for themselves
    supervisor_id = user.id
    if user.role == UserRole.ADMIN:
        supervisor_id = request.form.get('supervisor_id', type=int) or user.id

    group = Group(name=name, supervisor_id=supervisor_id, stream_id=stream_id)
    db.session.add(group)
    db.session.commit()
    flash(f'Group "{name}" created successfully.', 'success')
    return redirect(url_for('groups_bp.my_groups'))


@groups_bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
@supervisor_required
def delete_group(group_id):
    """Delete a group (only if no projects submitted under it)."""
    user  = get_current_user()
    group = Group.query.get_or_404(group_id)

    if user.role != UserRole.ADMIN and group.supervisor_id != user.id:
        flash('You can only delete your own groups.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    if group.projects.count() > 0:
        flash('Cannot delete a group that has submitted projects.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    db.session.delete(group)
    db.session.commit()
    flash(f'Group "{group.name}" deleted.', 'success')
    return redirect(url_for('groups_bp.my_groups'))


# ── MEMBER MANAGEMENT ─────────────────────────────────────────────────────────

@groups_bp.route('/groups/<int:group_id>/members/add', methods=['POST'])
@login_required
@supervisor_required
def add_member(group_id):
    """Add a student to a group."""
    user       = get_current_user()
    group      = Group.query.get_or_404(group_id)
    student_id = request.form.get('student_id', type=int)

    if user.role != UserRole.ADMIN and group.supervisor_id != user.id:
        flash('You can only manage your own groups.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    if len(group.members) >= 5:
        flash('A HIT200 group can have at most 5 members.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    student = User.query.get_or_404(student_id)
    if student.role != UserRole.STUDENT:
        flash('Only students can be added to groups.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    if student in group.members:
        flash(f'{student.full_name} is already in this group.', 'warning')
        return redirect(url_for('groups_bp.my_groups'))

    group.members.append(student)
    db.session.commit()
    flash(f'{student.full_name} added to "{group.name}".', 'success')
    return redirect(url_for('groups_bp.my_groups'))


@groups_bp.route('/groups/<int:group_id>/members/<int:student_id>/remove', methods=['POST'])
@login_required
@supervisor_required
def remove_member(group_id, student_id):
    """Remove a student from a group."""
    user    = get_current_user()
    group   = Group.query.get_or_404(group_id)
    student = User.query.get_or_404(student_id)

    if user.role != UserRole.ADMIN and group.supervisor_id != user.id:
        flash('You can only manage your own groups.', 'danger')
        return redirect(url_for('groups_bp.my_groups'))

    if student in group.members:
        group.members.remove(student)
        db.session.commit()
        flash(f'{student.full_name} removed from "{group.name}".', 'success')
    return redirect(url_for('groups_bp.my_groups'))


# ── API: students not yet in a group (for dropdown) ──────────────────────────

@groups_bp.route('/groups/<int:group_id>/available-students')
@login_required
@supervisor_required
def available_students(group_id):
    """HTMX: return students not yet in this group, optionally filtered by name/email."""
    from flask import jsonify
    group = Group.query.get_or_404(group_id)
    existing_ids = [m.id for m in group.members]

    query = User.query.filter(
        User.role == UserRole.STUDENT,
        User.is_active == True,
        ~User.id.in_(existing_ids) if existing_ids else db.true()
    )

    search = request.args.get('stxt-' + str(group_id), '').strip()
    if not search:
        # Also try generic 'search' param
        search = request.args.get('search', '').strip()

    if search:
        query = query.filter(
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    students = query.order_by(User.full_name).all()

    # Always return JSON for the autocomplete widget
    return jsonify([
        {'id': s.id, 'name': s.full_name, 'email': s.email}
        for s in students
    ])