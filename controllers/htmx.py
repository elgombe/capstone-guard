from flask import Blueprint, render_template, request
from controllers.dashboard import login_required
import os
from dotenv import load_dotenv
from difflib import SequenceMatcher

load_dotenv()

from models.db import Project, ProjectStatus, db

def calculate_similarity(text1, text2):
    """Calculate similarity between two texts"""
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def find_similar_projects(title, description, threshold=None, exclude_id=None):
    """Find similar projects"""
    if threshold is None:
        threshold = float(os.environ.get('SIMILARITY_THRESHOLD', 0.7))
    
    similar_projects = []
    query = Project.query.filter_by(status=ProjectStatus.APPROVED)
    
    if exclude_id:
        query = query.filter(Project.id != exclude_id)
    
    all_projects = query.all()
    
    for project in all_projects:
        title_sim = calculate_similarity(title, project.title)
        desc_sim = calculate_similarity(description, project.description)
        
        overall_sim = (
            float(os.environ.get('TITLE_SIMILARITY_WEIGHT', 0.5)) * title_sim +
            float(os.environ.get('DESCRIPTION_SIMILARITY_WEIGHT', 0.5)) * desc_sim
        )
        
        if overall_sim >= threshold:
            similar_projects.append({
                'project': project,
                'title_similarity': title_sim,
                'description_similarity': desc_sim,
                'overall_similarity': overall_sim
            })
    
    similar_projects.sort(key=lambda x: x['overall_similarity'], reverse=True)
    return similar_projects



htmx_bp = Blueprint('htmx_bp', __name__)

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
