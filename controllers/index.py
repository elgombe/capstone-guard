from flask import Blueprint, redirect, render_template, session, url_for

index_bp = Blueprint('index', __name__)

@index_bp.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))
    return render_template('index.html')