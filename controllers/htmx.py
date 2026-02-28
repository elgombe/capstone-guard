from flask import Blueprint, render_template, request
from flask_login import login_required
from app import find_similar_projects

from models.db import Project, ProjectStatus, db

htmx_bp = Blueprint('htmx', __name__)

@htmx_bp.route('/htmx/check-duplicate', methods=['POST'])
@login_required
def htmx_check_duplicate():
    """HTMX endpoint to check for duplicates"""
    title = request.form.get('title', '')
    description = request.form.get('description', '')
    
    if len(title) < 10 or len(description) < 50:
        return ''
    
    similar_projects = find_similar_projects(title, description)
    
    if similar_projects:
        return render_template('partials/duplicate_warning.html',
            similar_count=len(similar_projects),
            similar_projects=similar_projects[:3]
        )
    
    return '<div class="alert alert-success mt-3">✓ No similar projects found</div>'

@htmx_bp.route('/htmx/projects')
@login_required
def htmx_projects():
    """HTMX endpoint for loading projects"""
    stream_id = request.args.get('stream', type=int)
    status_filter = request.args.get('status')
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    
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
    
    return render_template('partials/project_list.html',
        projects=pagination.items,
        pagination=pagination
    )
