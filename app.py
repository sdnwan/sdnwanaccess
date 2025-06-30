from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from datetime import timedelta
import os
from config import Config

# Initialize Flask application
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_active = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# --- Helper Functions ---
def send_reset_email(user_email, reset_url):
    msg = Message('Password Reset Request',
                  sender=app.config['MAIL_DEFAULT_SENDER'],
                  recipients=[user_email])
    msg.body = f'''To reset your password, visit the following link:
{reset_url}

If you did not make this request, please ignore this email.
'''
    mail.send(msg)

from functools import wraps
from flask import abort

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Route Definitions ---

from flask import request

def role_required(role_prefix):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            username = session.get('username', '').lower()
            if not username.startswith(role_prefix):
                flash('Access denied: insufficient permissions.', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/upload_announcement', methods=['POST'])
@login_required
@role_required('t')
def upload_announcement():
    course_id = request.form.get('course_id')
    title = request.form.get('announcement_title')
    content = request.form.get('announcement_content')

    if not course_id or not title or not content:
        flash('All fields are required for announcements.', 'danger')
        return redirect(url_for('course_detail', course_id=course_id))

    announcements_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id, 'announcements')
    os.makedirs(announcements_dir, exist_ok=True)

    # Save announcement as a text file with timestamp
    import datetime
    timestamp = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    filename = f"{timestamp}_{secure_filename(title)}.txt"
    filepath = os.path.join(announcements_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Title: {title}\n\n{content}")

    flash('Announcement uploaded successfully.', 'success')
    return redirect(url_for('course_detail', course_id=course_id))

@app.context_processor
def inject_announcements():
    def get_announcements(course_id):
        announcements_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id, 'announcements')
        announcements = []
        if os.path.exists(announcements_dir):
            files = sorted(os.listdir(announcements_dir), reverse=True)
            for file in files:
                filepath = os.path.join(announcements_dir, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                announcements.append(content)
        return announcements
    return dict(get_announcements=get_announcements)

import os
from werkzeug.utils import secure_filename
from flask import send_from_directory

UPLOAD_FOLDER = 'uploads/lectures'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'ppt', 'pptx', 'txt'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload_course_lecture', methods=['GET', 'POST'])
@login_required
@role_required('t')
def upload_course_lecture():
    if request.method == 'POST':
        course_id = request.form.get('course_id')
        lecture_notes = request.form.get('lecture_notes')
        file = request.files.get('lecture_file')

        if not course_id:
            flash('Course ID is required.', 'danger')
            return redirect(request.url)

        # Create directory for course if not exists
        course_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id)
        os.makedirs(course_dir, exist_ok=True)

        filename = None
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(course_dir, filename))
        elif file:
            flash('File type not allowed.', 'danger')
            return redirect(request.url)

        # Save lecture notes to a text file
        if lecture_notes:
            notes_path = os.path.join(course_dir, 'lecture_notes.txt')
            with open(notes_path, 'w', encoding='utf-8') as f:
                f.write(lecture_notes)

        flash('Course lecture uploaded/modified successfully.', 'success')
        return redirect(url_for('course_detail', course_id=course_id))

    return render_template('upload_course_lecture.html')

@app.route('/course/<course_id>')
@login_required
def course_detail(course_id):
    course_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id)
    lecture_files = []
    lecture_notes = ''

    if os.path.exists(course_dir):
        for filename in os.listdir(course_dir):
            # Exclude lecture notes file and announcements directory
            if filename != 'lecture_notes.txt' and filename != 'announcements':
                lecture_files.append(filename)
        notes_path = os.path.join(course_dir, 'lecture_notes.txt')
        if os.path.exists(notes_path):
            with open(notes_path, 'r', encoding='utf-8') as f:
                lecture_notes = f.read()

    return render_template('course_detail.html', course_id=course_id, lecture_files=lecture_files, lecture_notes=lecture_notes)

@app.route('/uploads/lectures/<course_id>/<filename>')
@login_required
def uploaded_file(course_id, filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], course_id), filename)

# Route for the Homepage
@app.route('/')
def index():
  """Renders the homepage."""
  # Looks for 'index.html' in the 'templates' folder
  return render_template('index.html')

# Route for the Courses Page
@app.route('/courses')
def courses():
  """Renders the courses page."""
  return render_template('courses.html')

# Route for the Admissions Page
@app.route('/admissions')
def admissions():
  """Renders the admissions page."""
  return render_template('admissions.html')

# Route for the About Page
@app.route('/about')
def about():
  """Renders the about page."""
  return render_template('about.html')

# Route for the Contact Page
@app.route('/contact')
def contact():
  """Renders the contact page."""
  return render_template('contact.html')

# Import Flask-WTF at the top with other imports
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Email

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')

class AddUserForm(FlaskForm):
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    address = TextAreaField('Address')
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone Number')
    course_major = StringField('Course Major')
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[('student', 'Student'), ('teacher', 'Teacher'), ('admin', 'Admin')], validators=[DataRequired()])

# Add CSRF protection
app.config['SECRET_KEY'] = 'your-secret-key'  # Ensure this is set in your config.py or environment

# Route for the Login Page
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles user login."""
    form = LoginForm()
    if form.validate_on_submit():
        flash(f"Form submitted with username: {form.username.data}", "info")
        user = User.query.filter_by(username=form.username.data).first()
        if user:
            flash(f"User found: {user.username}", "info")
        else:
            flash("User not found", "warning")
        
        if user and user.check_password(form.password.data):
            flash("Password check passed", "info")
            session['user_id'] = user.id
            session['username'] = user.username  # Store username in session for access control
            if form.remember.data:
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=7)
            flash('Login successful!', 'success')
            # Debug: Show session username
            flash(f"Session username: {session.get('username')}", "info")
            # Redirect based on username starting letter
            if user.username.lower().startswith('s'):
                flash("Redirecting to student_home", "info")
                return redirect(url_for('student_home'))
            elif user.username.lower().startswith('t'):
                flash("Redirecting to teacher_home", "info")
                return redirect(url_for('teacher_home'))
            elif user.username.lower().startswith('admin'):
                flash("Redirecting to admin_home", "info")
                return redirect(url_for('admin_home'))
            else:
                flash("Redirecting to index", "info")
                return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/grades/<course_id>')
@login_required
def grades(course_id):
    # Placeholder: Fetch grades data for the course_id
    grades_data = []  # Replace with actual data fetching logic
    return render_template('grades.html', course_id=course_id, grades=grades_data)

@app.route('/tests/<course_id>')
@login_required
def tests(course_id):
    # Placeholder: Fetch tests data for the course_id
    tests_data = []  # Replace with actual data fetching logic
    return render_template('tests.html', course_id=course_id, tests=tests_data)

@app.route('/assignments/<course_id>')
@login_required
def assignments(course_id):
    # Placeholder: Fetch assignments data for the course_id
    assignments_data = []  # Replace with actual data fetching logic
    return render_template('assignments.html', course_id=course_id, assignments=assignments_data)

@app.route('/add_user', methods=['GET', 'POST'])
@login_required
@role_required('a')
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists. Please choose a different username.', 'danger')
        else:
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                is_active=True
            )
            new_user.set_password(form.password.data)
            db.session.add(new_user)
            db.session.commit()
            flash('New user added successfully!', 'success')
            return redirect(url_for('admin_home'))
    return render_template('add_user.html', form=form)

from functools import wraps
from flask import abort

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role_prefix):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            username = session.get('username', '').lower()
            if not username.startswith(role_prefix):
                abort(403)  # Forbidden
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/student_home')
@login_required
@role_required('s')
def student_home():
    # For demonstration, assuming we have a way to get student's enrolled courses
    # Here, we simulate with a fixed list or fetch from user profile in real app
    enrolled_courses = ['PROG1001', 'ICT2002', 'OP3011', 'DBM2023']

    # Collect announcements for all enrolled courses
    all_announcements = []
    for course_id in enrolled_courses:
        announcements_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id, 'announcements')
        if os.path.exists(announcements_dir):
            files = sorted(os.listdir(announcements_dir), reverse=True)
            for file in files:
                filepath = os.path.join(announcements_dir, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                all_announcements.append({'course_id': course_id, 'content': content})

    return render_template('student_home.html', announcements=all_announcements)

@app.route('/student_course/<course_id>')
@login_required
@role_required('s')
def student_course_detail(course_id):
    course_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id)
    lecture_files = []
    lecture_notes = ''
    grades = []  # Fetch grades for student and course_id
    tests = []   # Fetch tests for student and course_id

    if os.path.exists(course_dir):
        for filename in os.listdir(course_dir):
            if filename != 'lecture_notes.txt' and filename != 'announcements':
                lecture_files.append(filename)
        notes_path = os.path.join(course_dir, 'lecture_notes.txt')
        if os.path.exists(notes_path):
            with open(notes_path, 'r', encoding='utf-8') as f:
                lecture_notes = f.read()

    # Placeholder: Fetch grades and tests data for the student and course_id
    # Replace with actual data fetching logic

    return render_template('student_course_detail.html', course_id=course_id, lecture_files=lecture_files, lecture_notes=lecture_notes, grades=grades, tests=tests)

@app.route('/upload_assignment', methods=['POST'])
@login_required
@role_required('s')
def upload_assignment():
    course_id = request.form.get('course_id')
    file = request.files.get('assignment_file')

    if not course_id or not file:
        flash('Course ID and assignment file are required.', 'danger')
        return redirect(request.referrer or url_for('student_home'))

    assignments_dir = os.path.join(app.config['UPLOAD_FOLDER'], course_id, 'assignments')
    os.makedirs(assignments_dir, exist_ok=True)

    filename = secure_filename(file.filename)
    filepath = os.path.join(assignments_dir, filename)
    file.save(filepath)

    flash('Assignment uploaded successfully.', 'success')
    return redirect(url_for('student_course_detail', course_id=course_id))

@app.route('/teacher_home')
@login_required
@role_required('t')
def teacher_home():
    # Added debug flash message to check access
    flash('Accessed teacher homepage', 'info')
    return render_template('teacher_home.html')

@app.route('/admin_home')
@login_required
@role_required('a')
def admin_home():
    return render_template('admin_home.html')

@app.route('/documents')
@login_required
@role_required('a')
def documents():
    return render_template('documents.html')

@app.route('/list_users')
@login_required
@role_required('a')
def list_users():
    users = User.query.all()
    return render_template('list_users.html', users=users)

@app.route('/logout')
def logout():
    """Handles user logout."""
    session.pop('user_id', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))


# Route for the Forgot Password Page
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handles password reset requests."""
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            token = serializer.dumps(email, salt='password-reset')
            reset_url = url_for('reset_password', token=token, _external=True)
            send_reset_email(email, reset_url)
            flash('Password reset link has been sent to your email', 'info')
        else:
            flash('No account found with that email address', 'danger')
    
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handles password reset confirmation."""
    try:
        email = serializer.loads(token, salt='password-reset', max_age=app.config['RESET_TOKEN_EXPIRATION'])
    except:
        flash('The password reset link is invalid or has expired', 'danger')
        return redirect(url_for('forgot_password'))
    
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Invalid user account', 'danger')
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
        else:
            user.set_password(password)
            db.session.commit()
            flash('Your password has been updated successfully', 'success')
            return redirect(url_for('login'))
    
    return render_template('reset_password.html')

# --- Run the Application ---

# This block ensures the server only runs when the script is executed directly
# (not when imported as a module)
if __name__ == '__main__':
  # Starts the development server
  # debug=True allows for automatic reloading on code changes and detailed error pages
  # IMPORTANT: Set debug=False in a production environment!
  app.run(debug=True)