from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from controllers.dashboard import login_required, get_current_user
from datetime import datetime
from dotenv import load_dotenv
from .similarity import find_similar_projects          # ← OpenAI-powered

load_dotenv()

from models.db import Comment, Notification, Project, ProjectStatus, Stream, db, UserRole, SimilarityRecord

projects_bp = Blueprint('projects', __name__)


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
    stream_id     = request.args.get('stream', type=int)
    status_filter = request.args.get('status')
    search        = request.args.get('search', '')
    page          = request.args.get('page', 1, type=int)

    query = Project.query

    if stream_id:
        query = query.filter_by(stream_id=stream_id)

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

    streams = Stream.query.order_by(Stream.name).all()

    return render_template('projects.html',
        projects=pagination.items,
        pagination=pagination,
        streams=streams,
        current_stream=stream_id,
        current_status=status_filter,
        search_query=search
    )


@projects_bp.route('/projects/new', methods=['GET', 'POST'])
@login_required
def new_project():
    """Submit a new project."""
    if request.method == 'POST':
        user = get_current_user()

        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        stream_id   = request.form.get('stream_id', type=int)
        technologies = request.form.get('technologies', '').strip()
        github_url  = request.form.get('github_url', '').strip()
        demo_url    = request.form.get('demo_url', '').strip()

        project = Project(
            title=title,
            description=description,
            user_id=user.id,
            stream_id=stream_id,
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
    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    return render_template('new_project.html', streams=streams)


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

    return render_template('project_detail.html',
        project=project,
        similar_projects=similar_projects,
        comments=comments,
        can_edit=(user.id == project.user_id or user.role in [UserRole.ADMIN, UserRole.REVIEWER]),
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
        db.session.commit()

        flash('Project updated successfully!', 'success')
        return redirect(url_for('projects.project_detail', project_id=project.id))

    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    return render_template('edit_project.html', project=project, streams=streams)


@projects_bp.route('/projects/<int:project_id>/status', methods=['POST'])
@login_required
def update_project_status(project_id):
    """Update project status (admin / reviewer only)."""
    user = get_current_user()

    if user.role not in [UserRole.ADMIN, UserRole.REVIEWER]:
        return jsonify({'error': 'Unauthorized'}), 403

    project      = Project.query.get_or_404(project_id)
    new_status   = request.form.get('status', '')
    review_notes = request.form.get('review_notes', '')

    try:
        status_enum = ProjectStatus[new_status.upper()]
        project.status         = status_enum
        project.reviewed_by_id = user.id
        project.reviewed_at    = datetime.utcnow()
        project.review_notes   = review_notes
        db.session.commit()

        status_messages = {
            ProjectStatus.APPROVED:     'Congratulations! Your project has been approved.',
            ProjectStatus.REJECTED:     'Your project was not approved. Please review the feedback.',
            ProjectStatus.UNDER_REVIEW: 'Your project is currently under review.',
        }

        if status_enum in status_messages:
            create_notification(
                user_id=project.user_id,
                title=f'Project {status_enum.value.replace("_", " ").title()}',
                message=status_messages[status_enum],
                notification_type=f'project_{status_enum.value}',
                related_project_id=project.id,
            )

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