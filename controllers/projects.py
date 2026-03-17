from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from controllers.dashboard import login_required, get_current_user
from datetime import datetime
from dotenv import load_dotenv
from .similarity import find_similar_projects          # ← OpenAI-powered

load_dotenv()

from models.db import Comment, Notification, Project, ProjectStatus, ProjectCategory, Stream, Group, db, UserRole, SimilarityRecord

projects_bp = Blueprint('projects', __name__)

PROGRAMS = ['ISE', 'IIT', 'ICS', 'ISA', 'SPT', 'SFP', 'SBT',
            'EPT', 'EIM', 'EEE', 'ECP', 'BFA', 'BFE', 'BEC']


def _get_programs():
    """Return the canonical list of programmes."""
    return PROGRAMS


def _get_stream_map(active_only=False):
    """Return a dict of {'YEAR PROG': stream_id} for JS lookups."""
    q = Stream.query
    if active_only:
        q = q.filter_by(is_active=True)
    return {s.name: s.id for s in q.all()}


def _get_user_groups(user):
    """Return groups the student belongs to (for HIT200 group selection)."""
    if user.role == UserRole.STUDENT:
        return user.groups   # via group_members backref
    return []


def create_notification(user_id, title, message, notification_type, related_project_id=None):
    """Create a notification for a user."""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notification_type=notification_type,
        related_project_id=related_project_id
    )
    db.session.add(notification)
    db.session.commit()


# ── ROUTES ────────────────────────────────────────────────────────────────────

@projects_bp.route('/projects')
@login_required
def projects():
    """All projects page."""
    program       = request.args.get('program', '').strip()
    year_filter   = request.args.get('year', '').strip()
    status_filter = request.args.get('status')
    search        = request.args.get('search', '')
    page          = request.args.get('page', 1, type=int)

    query = Project.query

    # Filter by program and/or year via stream name
    if program or year_filter:
        stream_query = Stream.query
        if program:
            stream_query = stream_query.filter(Stream.name.ilike(f'% {program}'))
        if year_filter:
            try:
                stream_query = stream_query.filter_by(year=int(year_filter))
            except ValueError:
                pass
        matching_ids = [s.id for s in stream_query.all()]
        if matching_ids:
            query = query.filter(Project.stream_id.in_(matching_ids))
        else:
            query = query.filter(db.false())

    if status_filter:
        try:
            status_enum = ProjectStatus[status_filter.upper()]
            query = query.filter_by(status=status_enum)
        except KeyError:
            pass

    if search:
        search_term = f'%{search}%'
        query = query.filter(
            db.or_(
                Project.title.ilike(search_term),
                Project.description.ilike(search_term)
            )
        )

    query = query.order_by(Project.submitted_at.desc())
    pagination = query.paginate(page=page, per_page=20, error_out=False)

    programs = _get_programs()

    return render_template('projects.html',
        projects=pagination.items,
        pagination=pagination,
        programs=programs,
        current_program=program,
        current_year=year_filter,
        current_status=status_filter,
        search_query=search
    )


@projects_bp.route('/projects/new', methods=['GET', 'POST'])
@login_required
def new_project():
    """Submit a new project."""
    if request.method == 'POST':
        user = get_current_user()

        title        = request.form.get('title', '').strip()
        description  = request.form.get('description', '').strip()
        stream_id    = request.form.get('stream_id', type=int)
        technologies = request.form.get('technologies', '').strip()
        github_url   = request.form.get('github_url', '').strip()
        demo_url     = request.form.get('demo_url', '').strip()
        category_val = request.form.get('category', 'hit400')
        group_id     = request.form.get('group_id', type=int)

        try:
            category = ProjectCategory(category_val)
        except ValueError:
            category = ProjectCategory.HIT400

        # Validate stream was resolved
        if not stream_id:
            program = request.form.get('program', '').strip()
            year    = request.form.get('intake_year', '').strip()
            flash(f'Stream "{year} {program}" not found. Please contact the administrator.', 'danger')
            programs   = _get_programs()
            stream_map = _get_stream_map()
            groups     = _get_user_groups(user)
            return render_template('new_project.html', programs=programs,
                                   stream_map=stream_map, groups=groups,
                                   user_in_group=len(groups) > 0)

        # HIT200 requires a group
        if category == ProjectCategory.HIT200 and not group_id:
            flash('HIT200 projects must be linked to a group.', 'danger')
            programs   = _get_programs()
            stream_map = _get_stream_map()
            groups     = _get_user_groups(user)
            return render_template('new_project.html', programs=programs,
                                   stream_map=stream_map, groups=groups,
                                   user_in_group=len(groups) > 0)

        project = Project(
            title=title,
            description=description,
            user_id=user.id,
            stream_id=stream_id,
            category=category,
            group_id=group_id if category == ProjectCategory.HIT200 else None,
            technologies=technologies or None,
            github_url=github_url or None,
            demo_url=demo_url or None,
        )
        db.session.add(project)
        db.session.commit()

        # ── OpenAI-powered duplicate check ────────────────────────────────
        similar_projects = find_similar_projects(
            title, description, exclude_id=project.id
        )

        if similar_projects:
            project.is_flagged_duplicate = True

            for similar in similar_projects[:5]:
                record = SimilarityRecord(
                    project_id=project.id,
                    similar_project_id=similar['project'].id,
                    title_similarity=similar['title_similarity'],
                    description_similarity=similar['description_similarity'],
                    overall_similarity=similar['overall_similarity'],
                )
                db.session.add(record)

            create_notification(
                user_id=user.id,
                title='Similar Projects Found',
                message=(
                    f'We found {len(similar_projects)} project(s) similar to '
                    f'"{project.title}". Please review them before proceeding.'
                ),
                notification_type='duplicate_warning',
                related_project_id=project.id,
            )

            db.session.commit()
            flash(
                f'Project submitted! Warning: {len(similar_projects)} similar '
                f'project(s) were found — please review them.',
                'warning'
            )
        else:
            db.session.commit()
            flash('Project submitted successfully!', 'success')

        return redirect(url_for('projects.project_detail', project_id=project.id))

    # GET
    user       = get_current_user()
    programs   = _get_programs()
    stream_map = _get_stream_map()
    groups     = _get_user_groups(user)
    user_in_group = len(groups) > 0
    return render_template('new_project.html', programs=programs,
                           stream_map=stream_map, groups=groups,
                           user_in_group=user_in_group)


@projects_bp.route('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    """Project detail page."""
    project = Project.query.get_or_404(project_id)
    user    = get_current_user()

    similar_projects = []
    if project.is_flagged_duplicate:
        for record in SimilarityRecord.query.filter_by(project_id=project_id).all():
            similar_projects.append({
                'project': record.similar_project,
                'title_similarity':       round(record.title_similarity * 100, 1),
                'description_similarity': round(record.description_similarity * 100, 1),
                'overall_similarity':     round(record.overall_similarity * 100, 1),
            })

    comments = Comment.query.filter_by(
        project_id=project_id,
        parent_id=None,
        is_deleted=False,
    ).order_by(Comment.created_at.desc()).all()

    # Who can see the chapter workflow button
    is_group_member = (
        project.category == ProjectCategory.HIT200
        and project.group
        and user in project.group.members
    )
    is_group_supervisor = (
        project.category == ProjectCategory.HIT200
        and project.group
        and project.group.supervisor_id == user.id
    )
    can_access_chapters = (
        user.id == project.user_id
        or is_group_member
        or is_group_supervisor
        or user.role in [UserRole.ADMIN, UserRole.REVIEWER]
    )

    # Count chapters directly — avoids dependency on ai_check_passed column
    from models.db import Chapter
    chapter_count = Chapter.query.filter_by(project_id=project_id).count()

    return render_template('project_detail.html',
        project=project,
        similar_projects=similar_projects,
        comments=comments,
        can_edit=(user.id == project.user_id or user.role in [UserRole.ADMIN, UserRole.REVIEWER]),
        can_access_chapters=can_access_chapters,
        chapter_count=chapter_count,
    )


@projects_bp.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    """Edit an existing project."""
    project = Project.query.get_or_404(project_id)
    user    = get_current_user()

    if user.id != project.user_id and user.role not in [UserRole.ADMIN, UserRole.REVIEWER]:
        flash('You do not have permission to edit this project.', 'danger')
        return redirect(url_for('projects.project_detail', project_id=project_id))

    if request.method == 'POST':
        project.title        = request.form.get('title', '').strip()
        project.description  = request.form.get('description', '').strip()
        project.technologies = request.form.get('technologies', '').strip() or None
        project.github_url   = request.form.get('github_url', '').strip() or None
        project.demo_url     = request.form.get('demo_url', '').strip() or None
        project.updated_at   = datetime.utcnow()
        new_stream_id = request.form.get('stream_id', type=int)
        if new_stream_id:
            project.stream_id = new_stream_id
        db.session.commit()

        flash('Project updated successfully!', 'success')
        return redirect(url_for('projects.project_detail', project_id=project.id))

    programs   = _get_programs()
    stream_map = _get_stream_map()
    # Pre-populate program and year from current stream name ("2024 IIT" -> year=2024, prog="IIT")
    current_program = ''
    current_year    = ''
    if project.stream:
        parts = project.stream.name.split(' ', 1)
        if len(parts) == 2:
            current_year, current_program = parts[0], parts[1]
    return render_template('edit_project.html',
        project=project,
        programs=programs,
        stream_map=stream_map,
        current_program=current_program,
        current_year=current_year
    )


@projects_bp.route('/projects/<int:project_id>/status', methods=['POST'])
@login_required
def update_project_status(project_id):
    """Update project status (supervisor / admin / reviewer only)."""
    user = get_current_user()

    if user.role not in [UserRole.ADMIN, UserRole.REVIEWER, UserRole.SUPERVISOR]:
        return jsonify({'error': 'Unauthorized'}), 403

    project      = Project.query.get_or_404(project_id)
    new_status   = request.form.get('status', '')
    review_notes = request.form.get('review_notes', '')

    # Supervisors may only update projects in their group (HIT200)
    # or any project (HIT400) — admins/reviewers can update anything
    if user.role == UserRole.SUPERVISOR:
        if project.category == ProjectCategory.HIT200:
            if not project.group or project.group.supervisor_id != user.id:
                flash('You can only review projects assigned to your group.', 'danger')
                return redirect(url_for('projects.project_detail', project_id=project_id))

    try:
        status_enum = ProjectStatus[new_status.upper()]
        project.status         = status_enum
        project.reviewed_by_id = user.id
        project.reviewed_at    = datetime.utcnow()
        project.review_notes   = review_notes
        db.session.commit()

        # ── When approved: create chapters if they don't exist yet ────────
        if status_enum == ProjectStatus.APPROVED:
            from models.db import Chapter, create_chapters_for_project
            existing = Chapter.query.filter_by(project_id=project.id).count()
            if existing == 0:
                create_chapters_for_project(project.id)

            # Notify author + all group members
            recipients = {project.user_id}
            if project.category == ProjectCategory.HIT200 and project.group:
                for m in project.group.members:
                    recipients.add(m.id)

            for uid in recipients:
                create_notification(
                    user_id=uid,
                    title='Project Approved — Chapters Unlocked!',
                    message=(
                        f'Your project "{project.title}" has been approved by '
                        f'{user.full_name}. You can now begin submitting chapters.'
                    ),
                    notification_type='project_approved',
                    related_project_id=project.id,
                )

        elif status_enum == ProjectStatus.REJECTED:
            create_notification(
                user_id=project.user_id,
                title='Project Not Approved',
                message=(
                    f'Your project "{project.title}" was not approved. '
                    f'Feedback: {review_notes}' if review_notes
                    else f'Your project "{project.title}" was not approved. Please review the feedback.'
                ),
                notification_type='project_rejected',
                related_project_id=project.id,
            )

        elif status_enum == ProjectStatus.UNDER_REVIEW:
            create_notification(
                user_id=project.user_id,
                title='Project Under Review',
                message=f'Your project "{project.title}" is currently under review.',
                notification_type='project_under_review',
                related_project_id=project.id,
            )

        db.session.commit()
        flash('Project status updated successfully!', 'success')

    except KeyError:
        flash('Invalid status value.', 'danger')

    return redirect(url_for('projects.project_detail', project_id=project_id))

@projects_bp.route('/projects/<int:project_id>/comments', methods=['POST'])
@login_required
def add_comment(project_id):
    """Post a comment on a project."""
    project   = Project.query.get_or_404(project_id)
    user      = get_current_user()
    content   = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id', type=int)

    if not content:
        flash('Comment cannot be empty.', 'danger')
        return redirect(url_for('projects.project_detail', project_id=project_id))

    comment = Comment(
        project_id=project_id,
        user_id=user.id,
        parent_id=parent_id,
        content=content,
    )
    db.session.add(comment)
    db.session.commit()

    if user.id != project.user_id:
        create_notification(
            user_id=project.user_id,
            title='New Comment on Your Project',
            message=f'{user.full_name} commented on "{project.title}".',
            notification_type='new_comment',
            related_project_id=project.id,
        )

    flash('Comment added successfully!', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id))