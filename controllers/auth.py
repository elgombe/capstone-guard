from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from models.db import db, User, UserRole
from datetime import datetime
import re
import os
from authlib.integrations.flask_client import OAuth

auth_bp = Blueprint('auth_bp', __name__)

# ── OAuth setup ──────────────────────────────────────────────────────────────
oauth = OAuth()

def init_oauth(app):
    """Call this once in your app factory after creating the Flask app."""
    oauth.init_app(app)
    oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID'),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

# ─────────────────────────────────────────────────────────────────────────────


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.full_name
            session['user_role'] = user.role.value
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(url_for('dashboard.dash'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')


# Password: min 8 chars, uppercase, lowercase, digit, special char
PASSWORD_RE = re.compile(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_.#^()\-])[A-Za-z\d@$!%*?&_.#^()\-]{8,}$')
# Email: standard format
EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page"""
    if request.method == 'POST':
        email     = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password  = request.form.get('password', '')

        # ── Validation ──────────────────────────────────────────
        if not EMAIL_RE.match(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        if not full_name or len(full_name) < 2:
            flash('Full name must be at least 2 characters.', 'danger')
            return render_template('register.html')

        if not PASSWORD_RE.match(password):
            flash(
                'Password must be at least 8 characters and include '
                'an uppercase letter, lowercase letter, number, and special character.',
                'danger'
            )
            return render_template('register.html')
        # ────────────────────────────────────────────────────────

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('register.html')

        user = User(email=email, full_name=full_name, role=UserRole.STUDENT)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth_bp.login'))

    return render_template('register.html')


@auth_bp.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index_bp.index'))


# ── Google OAuth routes ───────────────────────────────────────────────────────

@auth_bp.route('/login/google')
def google_login():
    """Redirect to Google's OAuth consent screen."""
    redirect_uri = url_for('auth_bp.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/login/google/callback')
def google_callback():
    """Handle the callback from Google."""
    try:
        token = oauth.google.authorize_access_token()
    except Exception:
        flash('Google sign-in was cancelled or failed. Please try again.', 'danger')
        return redirect(url_for('auth_bp.login'))

    userinfo = token.get('userinfo')
    if not userinfo:
        flash('Could not retrieve your Google account information.', 'danger')
        return redirect(url_for('auth_bp.login'))

    google_id   = userinfo['sub']
    email       = userinfo.get('email', '')
    full_name   = userinfo.get('name', '')
    picture_url = userinfo.get('picture', '')

    # 1. Already linked to this Google account?
    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        # 2. Email already registered (password account) — link it
        user = User.query.filter_by(email=email).first()
        if user:
            user.google_id = google_id
            if picture_url and not user.profile_picture:
                user.profile_picture = picture_url
        else:
            # 3. Brand-new user — create one
            user = User(
                email=email,
                full_name=full_name,
                role=UserRole.STUDENT,
                google_id=google_id,
                profile_picture=picture_url,
                is_verified=True,   # Google already verified the email
            )
            db.session.add(user)

    user.last_login = datetime.utcnow()
    db.session.commit()

    session['user_id']   = user.id
    session['user_name'] = user.full_name
    session['user_role'] = user.role.value

    flash(f'Welcome, {user.full_name}!', 'success')
    return redirect(url_for('dashboard.dash'))