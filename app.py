from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from datetime import timedelta
import os
from config import Config
import logging 

# Set up logging
logging.basicConfig(level=logging.DEBUG)

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
        logging.debug(f"[User.set_password] Plain password: {password}")
        logging.debug(f"[User.set_password] Hashed password: {self.password_hash}")

    def check_password(self, password):
        logging.debug(f"[User.check_password] Stored hash for user '{self.username}': {self.password_hash}")
        result = check_password_hash(self.password_hash, password)
        logging.debug(f"[User.check_password] Checking password for user '{self.username}': {result}")
        return result

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

# Data structure for faculties and courses
faculties = [
    {
        'name': 'Arts & Humanities',
        'icon': 'fas fa-paint-brush',
        'description': 'Explore literature, history, philosophy, languages, and creative arts.',
        'courses': {
            'Undergraduate': [
                {
                    'code': 'BA101',
                    'name': 'Bachelor of Arts',
                    'description': 'Comprehensive study in arts including literature, history, and philosophy.',
                    'credits': 144,
                    'prerequisites': 'High School Diploma or equivalent',
                    'learning_outcomes': [
                        'Develop critical thinking and analytical skills.',
                        'Understand cultural and historical contexts.',
                        'Communicate effectively in written and oral forms.'
                    ],
                    'assessment_methods': [
                        'Essays',
                        'Presentations',
                        'Exams',
                        'Research Projects'
                    ],
                    'course_structure': [
                        {'name': 'Foundations of Art History', 'overview': 'Introduction to the history and development of art from ancient to modern times.'},
                        {'name': 'Prehistoric and Ancient Art', 'overview': 'Study of art from prehistoric periods through ancient civilizations.'},
                        {'name': 'Medieval Art and Architecture', 'overview': 'Exploration of art and architecture during the medieval period.'},
                        {'name': 'Renaissance Art and Culture', 'overview': 'Examination of Renaissance art, culture, and its impact.'},
                        {'name': 'Baroque and Rococo Art', 'overview': 'Analysis of Baroque and Rococo artistic movements.'},
                        {'name': 'Neoclassical Art', 'overview': 'Study of Neoclassical art and its principles.'},
                        {'name': 'Romanticism and Realism', 'overview': 'Exploration of Romantic and Realist art styles.'},
                        {'name': 'Impressionism and Post-Impressionism', 'overview': 'Study of Impressionist and Post-Impressionist artists and techniques.'},
                        {'name': 'Modern Art Movements', 'overview': 'Overview of major modern art movements and their characteristics.'},
                        {'name': 'Contemporary Art Practices', 'overview': 'Examination of contemporary art and current practices.'},
                        {'name': 'Art Criticism and Theory', 'overview': 'Introduction to art criticism and theoretical frameworks.'},
                        {'name': 'Museum and Gallery Studies', 'overview': 'Study of museum and gallery management and curation.'},
                        {'name': 'Digital Media in Art', 'overview': 'Exploration of digital technologies in art creation and presentation.'},
                        {'name': 'Photography Techniques', 'overview': 'Fundamentals of photography and visual storytelling.'},
                        {'name': 'Sculpture and Installation Art', 'overview': 'Study of three-dimensional art forms and installations.'},
                        {'name': 'Printmaking Processes', 'overview': 'Techniques and history of printmaking.'},
                        {'name': 'Visual Culture Studies', 'overview': 'Analysis of visual culture and media.'},
                        {'name': 'Conservation and Restoration', 'overview': 'Principles and practices of art conservation.'},
                        {'name': 'Art History Research Methods', 'overview': 'Research methodologies specific to art history.'},
                        {'name': 'Seminar in Art History', 'overview': 'Advanced discussions on specialized art history topics.'},
                        {'name': 'Special Topics in Art History', 'overview': 'Exploration of selected topics in art history.'},
                        {'name': 'Independent Research Project', 'overview': 'Conducting independent research in art history.'},
                        {'name': 'Capstone Project in Art History', 'overview': 'Comprehensive project demonstrating mastery in art history.'},
                        {'name': 'Professional Practice in Art', 'overview': 'Preparation for professional careers in the art field.'}
                    ]
                },
                {
                    'code': 'BA202',
                    'name': 'Bachelor of Literature',
                    'description': 'In-depth study of world literature and critical analysis.',
                    'credits': 144,
                    'prerequisites': 'High School Diploma or equivalent',
                    'learning_outcomes': [
                        'Identify key literary genres and themes.',
                        'Interpret texts from multiple cultural perspectives.',
                        'Enhance analytical writing skills.'
                    ],
                    'assessment_methods': [
                        'Critical essays',
                        'Class discussions',
                        'Midterm and final exams'
                    ],
                    'course_structure': [
                        'Classical Literature',
                        'Medieval Literature',
                        'Modern Literature',
                        'Postmodern Literature',
                        'Contemporary Global Literature'
                    ]
                },
                {
                    'code': 'BA105',
                    'name': 'Bachelor of History',
                    'description': 'Comprehensive study of modern history from the 18th century to present.',
                    'credits': 144,
                    'prerequisites': 'High School Diploma or equivalent',
                    'learning_outcomes': [
                        'Understand major historical events and trends.',
                        'Analyze causes and effects of global conflicts.',
                        'Develop research skills in history.'
                    ],
                    'assessment_methods': [
                        'Research papers',
                        'Examinations',
                        'Group projects'
                    ],
                    'course_structure': [
                        'Enlightenment and Revolutions',
                        'Industrialization and Imperialism',
                        'World Wars',
                        'Contemporary History'
                    ]
                }
            ],
            'Postgraduate Coursework': [
                {
                    'code': 'MA303',
                    'name': 'Master of Arts in Ethics and Philosophy',
                    'description': 'Advanced examination of major ethical theories and philosophical ideas.',
                    'credits': 48,
                    'prerequisites': 'Bachelor of Arts or equivalent',
                    'learning_outcomes': [
                        'Critically analyze ethical theories.',
                        'Develop advanced philosophical arguments.',
                        'Conduct independent research.'
                    ],
                    'assessment_methods': [
                        'Essays',
                        'Seminars',
                        'Thesis'
                    ],
                    'course_structure': [
                        {'name': 'Ethical Theory', 'overview': 'An in-depth study of fundamental ethical principles, moral philosophy, and their application to contemporary issues, enabling students to critically evaluate moral arguments and develop their own ethical viewpoints.'},
                        {'name': 'Philosophy of Mind', 'overview': 'Explores the nature of consciousness, mental states, and the mind-body problem, including theories of perception, cognition, and personal identity.'},
                        {'name': 'Political Philosophy', 'overview': 'Analyzes political systems, concepts of justice, rights, liberty, and the role of the state, with a focus on classical and contemporary political theories.'},
                        {'name': 'Philosophy of Science', 'overview': 'Investigates the foundations, methods, and implications of science, including the nature of scientific explanation, theory change, and scientific realism.'},
                        {'name': 'Research Methods in Philosophy', 'overview': 'Provides training in philosophical research techniques, critical analysis, argumentation, and academic writing necessary for advanced scholarship.'},
                        {'name': 'Advanced Logic', 'overview': 'Studies formal logical systems, symbolic logic, and reasoning techniques, emphasizing their application in philosophical argumentation and problem-solving.'},
                        {'name': 'Metaphysics', 'overview': 'Explores fundamental questions about existence, reality, causality, time, and space, examining various metaphysical theories and debates.'},
                        {'name': 'Philosophy of Language', 'overview': 'Examines the nature of language, meaning, reference, and communication, including theories of semantics and pragmatics.'},
                        {'name': 'Philosophy of Religion', 'overview': 'Critically evaluates religious beliefs, arguments for and against the existence of God, and the problem of evil, among other topics.'},
                        {'name': 'Contemporary Moral Issues', 'overview': 'Engages with current ethical dilemmas such as bioethics, environmental ethics, and social justice, encouraging applied ethical reasoning.'},
                        {'name': 'Philosophy of Art', 'overview': 'Analyzes aesthetic theory, the nature of art, interpretation, and criticism, exploring various art forms and their cultural significance.'},
                        {'name': 'Philosophy of History', 'overview': 'Studies the nature of historical knowledge, interpretation, and the philosophy of historiography.'},
                        {'name': 'Philosophy of Education', 'overview': 'Examines educational theories, the aims of education, and the ethical and political issues in education.'},
                        {'name': 'Philosophy of Law', 'overview': 'Explores legal systems, jurisprudence, the nature of law, and the relationship between law and morality.'},
                        {'name': 'Philosophy of Science Seminar', 'overview': 'Advanced seminar discussions on contemporary topics and debates in the philosophy of science.'}
                        ],
                },
                {
                    'code': 'MLIT401',
                    'name': 'Master of Literature in Contemporary Literary Theory',
                    'description': 'Advanced study of literary criticism and theory.',
                    'credits': 48,
                    'prerequisites': 'Bachelor of Literature or equivalent',
                    'learning_outcomes': [
                        'Apply contemporary literary theories.',
                        'Conduct critical literary analysis.',
                        'Produce scholarly research.'
                    ],
                    'assessment_methods': [
                        'Research papers',
                        'Presentations',
                        'Thesis'
                    ],
                    'course_structure': [
                        'Critical Theory',
                        'Postcolonial Literature',
                        'Feminist Literary Criticism',
                        'Narrative Theory',
                        'Research Methods in Literature',
                        'Modernist Literature',
                        'Postmodern Literature',
                        'Literature and Philosophy',
                        'Literature and Psychology',
                        'Literature and Gender Studies',
                        'Comparative Literature',
                        'Literary Theory Seminar',
                        'Digital Humanities',
                        'Thesis Preparation',
                        'Independent Research',
                        'Advanced Literary Criticism'
                    ]
                }
            ],
            'Research Degrees': [
                {
                    'code': 'PhD501',
                    'name': 'PhD in Art History',
                    'description': 'Doctoral research in art history methodologies.',
                    'credits': 72,
                    'prerequisites': 'Master’s degree in Art History or related field',
                    'learning_outcomes': [
                        'Conduct original research.',
                        'Publish academic papers.',
                        'Contribute to art history scholarship.'
                    ],
                    'assessment_methods': [
                        'Dissertation',
                        'Oral defense'
                    ],
                    'course_structure': [
                        'Research Project',
                        'Academic Writing',
                        'Teaching Practicum'
                    ]
                }
            ],
            'Diploma': [
                {
                    'code': 'DIP101',
                    'name': 'Diploma in Creative Writing',
                    'description': 'Comprehensive diploma program focusing on creative writing skills development.',
                    'credits': 24,
                    'prerequisites': 'High School Diploma or equivalent',
                    'learning_outcomes': [
                        'Develop creative writing techniques.',
                        'Understand narrative structures.',
                        'Produce original written works.'
                    ],
                    'assessment_methods': [
                        'Writing assignments',
                        'Workshops',
                        'Portfolio submission'
                    ],
                    'course_structure': [
                        'Introduction to Creative Writing',
                        'Poetry and Prose',
                        'Narrative Techniques',
                        'Writing Workshops',
                        'Literary Analysis',
                        'Final Portfolio'
                    ]
                }
            ]
        }
    },
    {
        'name': 'Science & Engineering',
        'icon': 'fas fa-atom',
        'description': 'Delve into physics, biology, chemistry, computer science, and various engineering disciplines.',
        'courses': {
            'Undergraduate': [
                {
                    'code': 'PHY101',
                    'name': 'General Physics',
                    'description': 'Fundamentals of mechanics, thermodynamics, and electromagnetism.',
                    'credits': 12,
                    'prerequisites': 'High School Physics',
                    'learning_outcomes': [
                        'Understand basic principles of physics.',
                        'Apply physics concepts to real-world problems.',
                        'Develop laboratory skills.'
                    ],
                    'assessment_methods': [
                        'Lab reports',
                        'Midterm exams',
                        'Final exams'
                    ],
                    'course_structure': [
                        'Week 1-4: Mechanics',
                        'Week 5-8: Thermodynamics',
                        'Week 9-12: Electromagnetism'
                    ]
                },
                {
                    'code': 'CS201',
                    'name': 'Data Structures and Algorithms',
                    'description': 'Core concepts in computer science and programming.',
                    'credits': 12,
                    'prerequisites': 'Introduction to Programming',
                    'learning_outcomes': [
                        'Implement common data structures.',
                        'Analyze algorithm efficiency.',
                        'Solve computational problems.'
                    ],
                    'assessment_methods': [
                        'Programming assignments',
                        'Quizzes',
                        'Exams'
                    ],
                    'course_structure': [
                        'Week 1-3: Arrays and Linked Lists',
                        'Week 4-6: Trees and Graphs',
                        'Week 7-9: Sorting and Searching Algorithms',
                        'Week 10-12: Algorithm Analysis'
                    ]
                },
                {
                    'code': 'BIO110',
                    'name': 'Introduction to Biology',
                    'description': 'Basic principles of biology and life sciences.',
                    'credits': 12,
                    'prerequisites': 'None',
                    'learning_outcomes': [
                        'Understand cell structure and function.',
                        'Explain genetics and evolution.',
                        'Describe ecological systems.'
                    ],
                    'assessment_methods': [
                        'Lab practicals',
                        'Written exams',
                        'Research projects'
                    ],
                    'course_structure': [
                        'Week 1-4: Cell Biology',
                        'Week 5-8: Genetics',
                        'Week 9-12: Ecology'
                    ]
                }
            ],
            'Postgraduate Coursework': [
                {
                    'code': 'CHEM302',
                    'name': 'Organic Chemistry',
                    'description': 'Advanced study of carbon-based compounds and reactions.',
                    'credits': 12,
                    'prerequisites': 'General Chemistry',
                    'learning_outcomes': [
                        'Understand organic reaction mechanisms.',
                        'Synthesize organic compounds.',
                        'Analyze spectroscopic data.'
                    ],
                    'assessment_methods': [
                        'Lab reports',
                        'Exams',
                        'Research presentations'
                    ],
                    'course_structure': [
                        'Week 1-4: Structure and Bonding',
                        'Week 5-8: Reaction Mechanisms',
                        'Week 9-12: Spectroscopy'
                    ]
                },
                {
                    'code': 'ENG401',
                    'name': 'Advanced Thermodynamics',
                    'description': 'In-depth study of thermodynamic systems and applications.',
                    'credits': 12,
                    'prerequisites': 'Thermodynamics I',
                    'learning_outcomes': [
                        'Analyze thermodynamic cycles.',
                        'Apply thermodynamics to engineering problems.',
                        'Conduct experimental measurements.'
                    ],
                    'assessment_methods': [
                        'Problem sets',
                        'Exams',
                        'Project work'
                    ],
                    'course_structure': [
                        'Week 1-4: Thermodynamic Laws',
                        'Week 5-8: Power Cycles',
                        'Week 9-12: Refrigeration Cycles'
                    ]
                }
            ],
            'Research Degrees': [
                {
                    'code': 'CS501',
                    'name': 'Artificial Intelligence Research',
                    'description': 'Research in AI algorithms and applications.',
                    'credits': 24,
                    'prerequisites': 'Machine Learning',
                    'learning_outcomes': [
                        'Conduct original AI research.',
                        'Publish research findings.',
                        'Develop AI applications.'
                    ],
                    'assessment_methods': [
                        'Research thesis',
                        'Seminar presentations'
                    ],
                    'course_structure': [
                        'Research project over two semesters.'
                    ]
                }
            ],
            'Short Courses & Professional Development': [
                {
                    'code': 'PHY105',
                    'name': 'Physics for Engineers',
                    'description': 'Short course on physics principles relevant to engineering.',
                    'credits': 6,
                    'prerequisites': 'None',
                    'learning_outcomes': [
                        'Apply physics concepts to engineering.',
                        'Solve engineering problems.',
                        'Understand material properties.'
                    ],
                    'assessment_methods': [
                        'Quizzes',
                        'Assignments'
                    ],
                    'course_structure': [
                        'Week 1-3: Mechanics',
                        'Week 4-6: Materials Science'
                    ]
                }
            ]
        }
    },
    {
        'name': 'Business & Economics',
        'icon': 'fas fa-briefcase',
        'description': 'Study management, marketing, finance, accounting, and economic principles.',
        'courses': {
            'Undergraduate': [
                {
                    'code': 'BUS101',
                    'name': 'Principles of Management',
                    'description': 'Introduction to management theories and practices.',
                    'credits': 12,
                    'prerequisites': 'None',
                    'learning_outcomes': [
                        'Understand fundamental management principles.',
                        'Develop leadership and organizational skills.',
                        'Apply management theories to real-world scenarios.'
                    ],
                    'assessment_methods': [
                        'Case studies',
                        'Group projects',
                        'Examinations'
                    ],
                    'course_structure': [
                        'Week 1-4: Introduction to Management',
                        'Week 5-8: Organizational Behavior',
                        'Week 9-12: Strategic Management'
                    ]
                },
                {
                    'code': 'ACC110',
                    'name': 'Financial Accounting',
                    'description': 'Basics of accounting and financial statements.',
                    'credits': 12,
                    'prerequisites': 'Introduction to Business',
                    'learning_outcomes': [
                        'Prepare and interpret financial statements.',
                        'Understand accounting principles and standards.',
                        'Analyze financial data for decision making.'
                    ],
                    'assessment_methods': [
                        'Problem sets',
                        'Exams',
                        'Projects'
                    ],
                    'course_structure': [
                        'Week 1-3: Accounting Basics',
                        'Week 4-6: Financial Statements',
                        'Week 7-9: Accounting Standards',
                        'Week 10-12: Financial Analysis'
                    ]
                }
            ],
            'Postgraduate Coursework': [
                {
                    'code': 'MKT202',
                    'name': 'Marketing Strategies',
                    'description': 'Techniques and strategies in modern marketing.',
                    'credits': 12,
                    'prerequisites': 'Marketing Principles',
                    'learning_outcomes': [
                        'Develop marketing plans and strategies.',
                        'Analyze market trends and consumer behavior.',
                        'Implement digital marketing techniques.'
                    ],
                    'assessment_methods': [
                        'Marketing plan project',
                        'Presentations',
                        'Exams'
                    ],
                    'course_structure': [
                        'Week 1-4: Market Analysis',
                        'Week 5-8: Marketing Mix',
                        'Week 9-12: Digital Marketing'
                    ]
                },
                {
                    'code': 'ECO303',
                    'name': 'Macroeconomics',
                    'description': 'Study of economic systems and policies at the national level.',
                    'credits': 12,
                    'prerequisites': 'Microeconomics',
                    'learning_outcomes': [
                        'Understand macroeconomic theories and models.',
                        'Analyze fiscal and monetary policies.',
                        'Evaluate economic indicators.'
                    ],
                    'assessment_methods': [
                        'Essays',
                        'Exams',
                        'Research papers'
                    ],
                    'course_structure': [
                        'Week 1-4: Economic Growth',
                        'Week 5-8: Inflation and Unemployment',
                        'Week 9-12: Fiscal and Monetary Policy'
                    ]
                }
            ],
            'Research Degrees': [
                {
                    'code': 'BUS501',
                    'name': 'Business Research Methods',
                    'description': 'Research techniques in business and economics.',
                    'credits': 24,
                    'prerequisites': 'Research Methodology',
                    'learning_outcomes': [
                        'Design and conduct business research.',
                        'Analyze quantitative and qualitative data.',
                        'Present research findings effectively.'
                    ],
                    'assessment_methods': [
                        'Research thesis',
                        'Seminar presentations'
                    ],
                    'course_structure': [
                        'Research project over two semesters.'
                    ]
                }
            ],
            'Short Courses & Professional Development': [
                {
                    'code': 'ENT101',
                    'name': 'Entrepreneurship Basics',
                    'description': 'Short course on starting and managing a business.',
                    'credits': 6,
                    'prerequisites': 'None',
                    'learning_outcomes': [
                        'Understand entrepreneurial processes.',
                        'Develop business plans.',
                        'Identify funding sources.'
                    ],
                    'assessment_methods': [
                        'Business plan',
                        'Presentations'
                    ],
                    'course_structure': [
                        'Week 1-3: Introduction to Entrepreneurship',
                        'Week 4-6: Business Planning'
                    ]
                }
            ]
        }
    },
    {
        'name': 'Health Sciences',
        'icon': 'fas fa-heartbeat',
        'description': 'Explore nursing, public health, physiotherapy, and other health-related fields.',
        'courses': {
            'Undergraduate': [
                {
                    'code': 'NUR101',
                    'name': 'Fundamentals of Nursing',
                    'description': 'Basic nursing skills and patient care.'
                },
                {
                    'code': 'BIO210',
                    'name': 'Human Anatomy',
                    'description': 'Study of the human body structure.'
                }
            ],
            'Postgraduate Coursework': [
                {
                    'code': 'PHH202',
                    'name': 'Public Health Principles',
                    'description': 'Study of health promotion and disease prevention.'
                },
                {
                    'code': 'PHY303',
                    'name': 'Physiotherapy Techniques',
                    'description': 'Advanced physiotherapy methods and practices.'
                }
            ],
            'Research Degrees': [
                {
                    'code': 'NUR501',
                    'name': 'Nursing Research',
                    'description': 'Research methodologies in nursing.'
                }
            ],
            'Short Courses & Professional Development': [
                {
                    'code': 'HLT101',
                    'name': 'Health and Wellness',
                    'description': 'Short course on maintaining health and wellness.'
                },
                {
                    'code': 'PHM102',
                    'name': 'Pharmacology Basics',
                    'description': 'Introduction to pharmacology for healthcare professionals.'
                }
            ]
        }
    }
]

# Route for the Courses Page
@app.route('/courses')
def courses():
    """Renders the courses page with dynamic faculties data."""
    return render_template('courses.html', faculties=faculties)

# Route to show courses by faculty
@app.route('/faculty/<faculty_name>')
def faculty_courses(faculty_name):
    """Renders the courses for a specific faculty."""
    # Convert faculty_name from URL to match data keys
    faculty_key = faculty_name.replace('_', ' ').title()
    selected_faculty = next((f for f in faculties if f['name'].lower() == faculty_key.lower()), None)
    if not selected_faculty:
        # If faculty not found, redirect to courses page or show 404
        return redirect(url_for('courses'))
    return render_template('faculty_courses.html', faculty_name=selected_faculty['name'], courses=selected_faculty['courses'])

# Public route for course detail without login required
@app.route('/public_course/<faculty_name>/<course_code>')
def public_course_detail(faculty_name, course_code):
    faculty_key = faculty_name.replace('_', ' ').title()
    selected_faculty = next((f for f in faculties if f['name'].lower() == faculty_key.lower()), None)
    if not selected_faculty:
        return redirect(url_for('courses'))
    # Search for course in all study levels
    course = None
    study_level = None
    for level, courses_list in selected_faculty['courses'].items():
        for c in courses_list:
            if c['code'].lower() == course_code.lower():
                course = c
                study_level = level
                break
        if course:
            break
    if not course:
        return redirect(url_for('faculty_courses', faculty_name=faculty_name))
    return render_template('public_course_detail.html', faculty_name=selected_faculty['name'], course=course, study_level=study_level)

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

@app.route('/start_mininet', methods=['POST'])
@login_required
@role_required('a')  # Or 't' if teachers should start it
def start_mininet():
    try:
        subprocess.run(['sudo', 'mn', '--topo', 'minimal', '--controller=remote'], check=True)
        flash('Mininet started successfully.', 'success')
    except subprocess.CalledProcessError as e:
        flash(f'Error starting Mininet: {str(e)}', 'danger')
    return redirect(url_for('admin_home'))


@app.route('/stop_mininet', methods=['POST'])
@login_required
@role_required('a')
def stop_mininet():
    subprocess.run(['sudo', 'mn', '-c'])
    flash('Mininet stopped and cleaned.', 'info')
    return redirect(url_for('admin_home'))



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