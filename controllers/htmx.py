from flask import Blueprint, render_template, request
from controllers.dashboard import login_required
from .similarity import find_similar_projects          # ← OpenAI-powered

from models.db import Project, ProjectStatus, db

htmx_bp = Blueprint('htmx_bp', __name__)


@htmx_bp.route('/htmx/check-duplicate', methods=['POST'])
@login_required
def htmx_check_duplicate():
    """HTMX endpoint — live duplicate check while user types."""
    title       = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()

    # Don't bother until there's enough text to be meaningful
    if len(title) < 10 or len(description) < 50:
        return ''

    similar_projects = find_similar_projects(title, description)

    if similar_projects:
        return render_template('partials/duplicate_warning.html',
            similar_count=len(similar_projects),
            similar_projects=similar_projects[:3]
        )

    return '''
        <div style="display:flex;align-items:center;gap:8px;margin-top:1rem;
                    padding:0.75rem 1rem;background:#dcfce7;border:1px solid #bbf7d0;
                    border-radius:9px;font-size:0.88rem;color:#166534;">
            <i class="bi bi-check-circle-fill"></i>
            No similar projects found — looks original!
        </div>
    '''


@htmx_bp.route('/htmx/projects')
@login_required
def htmx_projects():
    """HTMX endpoint for paginated/filtered project list."""
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

    return render_template('partials/project_list.html',
        projects=pagination.items,
        pagination=pagination
    )