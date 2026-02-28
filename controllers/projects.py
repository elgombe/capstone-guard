from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_jwt_extended import get_current_user
from flask_login import login_required
from app import create_notification, find_similar_projects
from datetime import datetime

from models.db import Comment, Project, ProjectStatus, Stream, db, UserRole, SimilarityRecord

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/projects')
@login_required
def projects():
    """All projects page"""
    # Get filter parameters
    stream_id = request.args.get('stream', type=int)
    status_filter = request.args.get('status')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Build query
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
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get all streams for filter
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
    """Create new project"""
    if request.method == 'POST':
        user = get_current_user()
        
        title = request.form.get('title')
        description = request.form.get('description')
        stream_id = request.form.get('stream_id', type=int)
        technologies = request.form.get('technologies')
        github_url = request.form.get('github_url')
        demo_url = request.form.get('demo_url')
        
        # Create project
        project = Project(
            title=title,
            description=description,
            user_id=user.id,
            stream_id=stream_id,
            technologies=technologies,
            github_url=github_url,
            demo_url=demo_url
        )
        
        db.session.add(project)
        db.session.commit()
        
        # Check for duplicates
        similar_projects = find_similar_projects(
            project.title,
            project.description,
            exclude_id=project.id
        )
        
        if similar_projects:
            project.is_flagged_duplicate = True
            
            for similar in similar_projects[:5]:
                similarity_record = SimilarityRecord(
                    project_id=project.id,
                    similar_project_id=similar['project'].id,
                    title_similarity=similar['title_similarity'],
                    description_similarity=similar['description_similarity'],
                    overall_similarity=similar['overall_similarity']
                )
                db.session.add(similarity_record)
            
            create_notification(
                user_id=user.id,
                title='Similar Projects Found',
                message=f'We found {len(similar_projects)} similar projects to "{project.title}"',
                notification_type='duplicate_warning',
                related_project_id=project.id
            )
            
            db.session.commit()
            
            flash(f'Project submitted! Warning: We found {len(similar_projects)} similar projects.', 'warning')
        else:
            flash('Project submitted successfully!', 'success')
        
        return redirect(url_for('projects.project_detail', project_id=project.id))
    
    # GET request
    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    return render_template('new_project.html', streams=streams)


@projects_bp.route('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    """Project detail page"""
    project = Project.query.get_or_404(project_id)
    user = get_current_user()
    
    # Get similar projects if flagged
    similar_projects = []
    if project.is_flagged_duplicate:
        similarity_records = SimilarityRecord.query.filter_by(project_id=project_id).all()
        for record in similarity_records:
            similar_projects.projects_bpend({
                'project': record.similar_project,
                'title_similarity': round(record.title_similarity * 100, 2),
                'description_similarity': round(record.description_similarity * 100, 2),
                'overall_similarity': round(record.overall_similarity * 100, 2)
            })
    
    # Get comments
    comments = Comment.query.filter_by(
        project_id=project_id,
        parent_id=None,
        is_deleted=False
    ).order_by(Comment.created_at.desc()).all()
    
    return render_template('project_detail.html',
        project=project,
        similar_projects=similar_projects,
        comments=comments,
        can_edit=(user.id == project.user_id or user.role in [UserRole.ADMIN, UserRole.REVIEWER])
    )


@projects_bp.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    """Edit project"""
    project = Project.query.get_or_404(project_id)
    user = get_current_user()
    
    # Check permissions
    if user.id != project.user_id and user.role not in [UserRole.ADMIN, UserRole.REVIEWER]:
        flash('You do not have permission to edit this project.', 'danger')
        return redirect(url_for('projects.project_detail', project_id=project_id))
    
    if request.method == 'POST':
        project.title = request.form.get('title')
        project.description = request.form.get('description')
        project.technologies = request.form.get('technologies')
        project.github_url = request.form.get('github_url')
        project.demo_url = request.form.get('demo_url')
        project.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        flash('Project updated successfully!', 'success')
        return redirect(url_for('projects.project_detail', project_id=project.id))
    
    streams = Stream.query.filter_by(is_active=True).order_by(Stream.name).all()
    return render_template('edit_project.html', project=project, streams=streams)


@projects_bp.route('/projects/<int:project_id>/status', methods=['POST'])
@login_required
def update_project_status(project_id):
    """Update project status (admin/reviewer only)"""
    user = get_current_user()
    
    if user.role not in [UserRole.ADMIN, UserRole.REVIEWER]:
        return jsonify({'error': 'Unauthorized'}), 403
    
    project = Project.query.get_or_404(project_id)
    new_status = request.form.get('status')
    review_notes = request.form.get('review_notes')
    
    try:
        status_enum = ProjectStatus[new_status.upper()]
        project.status = status_enum
        project.reviewed_by_id = user.id
        project.reviewed_at = datetime.utcnow()
        project.review_notes = review_notes
        
        db.session.commit()
        
        # Create notification
        status_messages = {
            ProjectStatus.projects_bpROVED: 'Your project has been projects_bproved!',
            ProjectStatus.REJECTED: 'Your project needs revisions.',
            ProjectStatus.UNDER_REVIEW: 'Your project is under review.'
        }
        
        if status_enum in status_messages:
            create_notification(
                user_id=project.user_id,
                title=f'Project {status_enum.value.title()}',
                message=status_messages[status_enum],
                notification_type=f'project_{status_enum.value}',
                related_project_id=project.id
            )
        
        flash('Project status updated successfully!', 'success')
    except KeyError:
        flash('Invalid status.', 'danger')
    
    return redirect(url_for('projects.project_detail', project_id=project_id))


@projects_bp.route('/projects/<int:project_id>/comments', methods=['POST'])
@login_required
def add_comment(project_id):
    """Add comment to project"""
    project = Project.query.get_or_404(project_id)
    user = get_current_user()
    
    content = request.form.get('content')
    parent_id = request.form.get('parent_id', type=int)
    
    comment = Comment(
        project_id=project_id,
        user_id=user.id,
        parent_id=parent_id,
        content=content
    )
    
    db.session.add(comment)
    db.session.commit()
    
    # Notify project author if not commenting on own project
    if user.id != project.user_id:
        create_notification(
            user_id=project.user_id,
            title='New Comment',
            message=f'{user.full_name} commented on your project "{project.title}"',
            notification_type='new_comment',
            related_project_id=project.id
        )
    
    flash('Comment added successfully!', 'success')
    return redirect(url_for('projects.project_detail', project_id=project_id))
