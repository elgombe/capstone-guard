"""
chapters.py — Chapter-by-chapter submission workflow
=====================================================
Register in your app factory:
    from controllers.chapters import chapters_bp
    app.register_blueprint(chapters_bp)
"""

from datetime import datetime
from flask import (Blueprint, abort, flash, redirect,
                   render_template, request, session, url_for)
from controllers.dashboard import login_required, get_current_user
from models.db import (
    db, Project, ProjectCategory, UserRole, Group,
    Chapter, ChapterReview, ChapterStatus, Notification,
    CHAPTER_DEFINITIONS, create_chapters_for_project, unlock_next_chapter
)

chapters_bp = Blueprint('chapters_bp', __name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _can_access_project(user, project):
    """
    True if user may view/interact with project chapters.
    - author (HIT400 or HIT200)
    - any group member (HIT200)
    - assigned supervisor (HIT200) or any supervisor (HIT400)
    - admin / reviewer (always)
    """
    if user.role in [UserRole.ADMIN, UserRole.REVIEWER]:
        return True
    if project.user_id == user.id:
        return True
    if project.category == ProjectCategory.HIT200 and project.group:
        if user in project.group.members:
            return True
        if project.group.supervisor_id == user.id:
            return True
    if project.category != ProjectCategory.HIT200 and user.role == UserRole.SUPERVISOR:
        return True
    return False


def _can_submit_chapter(user, project):
    """
    Students / group members may submit chapters.
    Supervisors and reviewers may NOT submit (they review).
    """
    if user.role == UserRole.ADMIN:
        return True
    if project.category == ProjectCategory.HIT400:
        return project.user_id == user.id
    # HIT200 — any group member may submit
    return user in project.group.members if project.group else False


def _can_review_chapter(user, project):
    """
    Supervisors, reviewers, and admins may review.
    - HIT400: any supervisor, reviewer, or admin can review
    - HIT200: only the assigned group supervisor (or admin/reviewer) can review
    """
    if user.role in [UserRole.ADMIN, UserRole.REVIEWER]:
        return True
    if user.role == UserRole.SUPERVISOR:
        if project.category == ProjectCategory.HIT200:
            # Only the assigned supervisor for this group
            return (project.group and project.group.supervisor_id == user.id)
        else:
            # HIT400: any supervisor can review
            return True
    return False


def _notify_users(project, title, message, ntype):
    """Notify project author + all HIT200 group members."""
    recipients = {project.user_id}
    if project.category == ProjectCategory.HIT200 and project.group:
        for m in project.group.members:
            recipients.add(m.id)
    for uid in recipients:
        n = Notification(user_id=uid, title=title, message=message,
                         notification_type=ntype,
                         related_project_id=project.id)
        db.session.add(n)


def _notify_supervisor(project, title, message, ntype):
    """Notify the HIT200 supervisor (or any reviewer/admin for HIT400)."""
    if (project.category == ProjectCategory.HIT200 and
            project.group and project.group.supervisor_id):
        n = Notification(user_id=project.group.supervisor_id,
                         title=title, message=message,
                         notification_type=ntype,
                         related_project_id=project.id)
        db.session.add(n)


# ── CHAPTER OVERVIEW ─────────────────────────────────────────────────────────

@chapters_bp.route('/projects/<int:project_id>/chapters')
@login_required
def chapter_overview(project_id):
    """
    Renders the chapter progress tracker for a project.
    This is the main landing page after a project passes AI check.
    """
    project = Project.query.get_or_404(project_id)
    user    = get_current_user()

    if not _can_access_project(user, project):
        flash('You do not have access to this project.', 'danger')
        return redirect(url_for('dashboard.dash'))

    # Build chapter list with metadata
    chapters = project.chapters.order_by(Chapter.order).all()

    # Compute overall progress
    approved_count = sum(1 for c in chapters if c.status == ChapterStatus.APPROVED)
    total          = len(chapters)
    progress_pct   = int((approved_count / total) * 100) if total else 0
    all_approved   = approved_count == total

    # Group members (for HIT200)
    group_members = []
    if project.category == ProjectCategory.HIT200 and project.group:
        group_members = project.group.members

    can_submit = _can_submit_chapter(user, project)
    can_review = _can_review_chapter(user, project)

    return render_template('chapters/overview.html',
        project=project,
        chapters=chapters,
        user=user,
        approved_count=approved_count,
        progress_pct=progress_pct,
        all_approved=all_approved,
        group_members=group_members,
        can_submit=can_submit,
        can_review=can_review,
        ChapterStatus=ChapterStatus,
    )


# ── CHAPTER DETAIL / SUBMIT ───────────────────────────────────────────────────

@chapters_bp.route('/projects/<int:project_id>/chapters/<int:chapter_order>',
                   methods=['GET', 'POST'])
@login_required
def chapter_detail(project_id, chapter_order):
    """
    View / submit a specific chapter.
    POST = student submitting chapter content.
    """
    project = Project.query.get_or_404(project_id)
    user    = get_current_user()

    if not _can_access_project(user, project):
        abort(403)

    chapter = Chapter.query.filter_by(
        project_id=project_id, order=chapter_order
    ).first_or_404()

    reviews  = chapter.reviews.order_by(ChapterReview.created_at.desc()).all()
    can_submit = _can_submit_chapter(user, project)
    can_review = _can_review_chapter(user, project)

    if request.method == 'POST':
        action = request.form.get('action')

        # ── Student submitting chapter content ────────────────────────────
        if action == 'submit_chapter' and can_submit:
            if chapter.status == ChapterStatus.LOCKED:
                flash('This chapter is not yet unlocked.', 'danger')
                return redirect(url_for('chapters_bp.chapter_detail',
                                        project_id=project_id,
                                        chapter_order=chapter_order))

            content = request.form.get('content', '').strip()
            if not content:
                flash('Chapter content cannot be empty.', 'danger')
                return redirect(request.url)

            chapter.content        = content
            chapter.submitted_by_id= user.id
            chapter.submitted_at   = datetime.utcnow()
            chapter.status         = ChapterStatus.SUBMITTED
            chapter.updated_at     = datetime.utcnow()
            db.session.commit()

            _notify_supervisor(
                project,
                title=f'Chapter {chapter.order} Submitted',
                message=(f'"{chapter.title}" for project "{project.title}" '
                         f'has been submitted by {user.full_name}.'),
                ntype='chapter_submitted'
            )
            db.session.commit()
            flash(f'{chapter.title} submitted for review!', 'success')
            return redirect(url_for('chapters_bp.chapter_detail',
                                    project_id=project_id,
                                    chapter_order=chapter_order))

        # ── Supervisor reviewing chapter ───────────────────────────────────
        elif action == 'review_chapter' and can_review:
            decision = request.form.get('decision')  # 'approved' | 'needs_revision'
            feedback = request.form.get('feedback', '').strip()

            if decision not in ('approved', 'needs_revision'):
                flash('Invalid review decision.', 'danger')
                return redirect(request.url)
            if not feedback:
                flash('Please provide feedback / review notes.', 'danger')
                return redirect(request.url)

            # Determine round number
            last_round = chapter.reviews.order_by(
                ChapterReview.round_num.desc()).first()
            round_num = (last_round.round_num + 1) if last_round else 1

            review = ChapterReview(
                chapter_id=chapter.id,
                reviewer_id=user.id,
                decision=decision,
                feedback=feedback,
                round_num=round_num,
            )
            db.session.add(review)

            if decision == 'approved':
                chapter.status        = ChapterStatus.APPROVED
                chapter.approved_at   = datetime.utcnow()
                chapter.approved_by_id= user.id

                # Unlock the next chapter
                next_ch = unlock_next_chapter(project_id, chapter_order)

                _notify_users(
                    project,
                    title=f'Chapter {chapter.order} Approved!',
                    message=(
                        f'"{chapter.title}" has been approved by {user.full_name}. '
                        + (f'"{next_ch.title}" is now unlocked.'
                           if next_ch else 'All chapters submitted — project complete!')
                    ),
                    ntype='chapter_approved'
                )

                # If all chapters approved → mark project approved
                remaining_locked = Chapter.query.filter_by(
                    project_id=project_id
                ).filter(
                    Chapter.status != ChapterStatus.APPROVED
                ).count()
                if remaining_locked == 0:
                    from models.db import ProjectStatus
                    project.status = ProjectStatus.APPROVED
                    _notify_users(
                        project,
                        title='Project Fully Approved!',
                        message=(f'All chapters for "{project.title}" have been approved. '
                                 f'Congratulations!'),
                        ntype='project_approved'
                    )

            else:  # needs_revision
                chapter.status = ChapterStatus.NEEDS_REVISION
                _notify_users(
                    project,
                    title=f'Chapter {chapter.order} Needs Revision',
                    message=(f'"{chapter.title}" requires revision. '
                             f'Feedback: {feedback[:120]}…' if len(feedback) > 120
                             else f'Feedback: {feedback}'),
                    ntype='chapter_revision'
                )

            db.session.commit()
            flash(
                'Chapter approved and next chapter unlocked!'
                if decision == 'approved'
                else 'Revision requested — student notified.',
                'success'
            )
            return redirect(url_for('chapters_bp.chapter_detail',
                                    project_id=project_id,
                                    chapter_order=chapter_order))

    # Hints for the chapter
    hints = {d[1]: d[3] for d in CHAPTER_DEFINITIONS}
    hint  = hints.get(chapter.slug, '')

    return render_template('chapters/detail.html',
        project=project,
        chapter=chapter,
        reviews=reviews,
        user=user,
        hint=hint,
        can_submit=can_submit,
        can_review=can_review,
        ChapterStatus=ChapterStatus,
    )


# ── MARK AS UNDER REVIEW (supervisor) ────────────────────────────────────────

@chapters_bp.route('/projects/<int:project_id>/chapters/<int:chapter_order>/start-review',
                   methods=['POST'])
@login_required
def start_review(project_id, chapter_order):
    """Supervisor marks a submitted chapter as 'under review'."""
    project = Project.query.get_or_404(project_id)
    user    = get_current_user()

    if not _can_review_chapter(user, project):
        abort(403)

    chapter = Chapter.query.filter_by(
        project_id=project_id, order=chapter_order
    ).first_or_404()

    if chapter.status == ChapterStatus.SUBMITTED:
        chapter.status = ChapterStatus.UNDER_REVIEW
        db.session.commit()
        _notify_users(
            project,
            title=f'Chapter {chapter.order} Under Review',
            message=f'"{chapter.title}" is now being reviewed by {user.full_name}.',
            ntype='chapter_under_review'
        )
        db.session.commit()
        flash('Marked as under review.', 'success')

    return redirect(url_for('chapters_bp.chapter_detail',
                            project_id=project_id,
                            chapter_order=chapter_order))
