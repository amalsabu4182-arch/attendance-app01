# app.py
"""
Complete Single-Department College Attendance Management System
Cleaned & updated single-file Flask app (port 5001)
"""

from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from functools import wraps
import secrets
import io
import csv
import json
import os
from collections import defaultdict
from sqlalchemy import func, case

# ----------------- App setup -----------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URI', 'sqlite:///college_attendance.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=12)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

# ==================== MODELS ====================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, teacher, student
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    failed_attempts = db.Column(db.Integer, default=0)
    login_history = db.relationship('LoginHistory', backref='user', lazy=True, cascade='all, delete-orphan')

class LoginHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(200))
    login_time = db.Column(db.DateTime, default=datetime.utcnow)
    logout_time = db.Column(db.DateTime)

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    type = db.Column(db.String(10), nullable=False)  # UG or PG
    duration = db.Column(db.Integer)  # Number of semesters
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, index=True)
    roll_number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), index=True)
    batch = db.Column(db.String(20))  # e.g., 2024
    division = db.Column(db.String(10))  # A, B, C, etc.
    semester = db.Column(db.Integer)
    photo_url = db.Column(db.String(200))
    parent_contact = db.Column(db.String(20))
    parent_email = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_type = db.Column(db.String(20))  # Major, Minor, Assistant
    contact = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    credits = db.Column(db.Integer)
    subject_type = db.Column(db.String(20))  # Major, Minor, AEC, VAC, MDC, SEC, Lab
    class_type = db.Column(db.String(20))  # Theory, Lab, Seminar
    program_id = db.Column(db.Integer, db.ForeignKey('program.id'), index=True)
    semester = db.Column(db.Integer)
    weekly_hours = db.Column(db.Integer, default=3)

class TeacherSubject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), index=True)
    batch = db.Column(db.String(20))
    division = db.Column(db.String(10))
    semester = db.Column(db.Integer)
    academic_year = db.Column(db.String(20))

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), index=True)
    day = db.Column(db.String(10))  # Monday, Tuesday, etc.
    period = db.Column(db.Integer)  # 1-5 or session (FN/AN)
    session_type = db.Column(db.String(10))  # FN, AN, Period
    room = db.Column(db.String(50))
    batch = db.Column(db.String(20))
    division = db.Column(db.String(10))
    semester = db.Column(db.Integer)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    session_type = db.Column(db.String(10))  # FN, AN, Period
    period = db.Column(db.Integer)  # 1-5 if period-wise, null if session-wise
    status = db.Column(db.String(20))  # Present, Absent, Late, EarlyExit, OD, ML, EL
    remarks = db.Column(db.Text)
    marked_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime)
    edited_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_locked = db.Column(db.Boolean, default=False)

class LeaveRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), index=True)
    from_date = db.Column(db.Date, nullable=False)
    to_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(20))  # Medical, Personal, Emergency
    reason = db.Column(db.Text)
    proof_url = db.Column(db.String(200))
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    action = db.Column(db.String(100))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class SystemSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==================== DECORATORS ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in roles:
                flash('Access denied', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ==================== HELPERS ====================
def log_audit(action, details=''):
    try:
        log = AuditLog(
            user_id=session.get('user_id'),
            action=action,
            details=details,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

def calculate_attendance_percentage(student_id, subject_id=None, from_date=None, to_date=None):
    q = db.session.query(
        func.count(Attendance.id).label('total'),
        func.sum(case([(Attendance.status.in_(['Present', 'Late', 'OD']), 1)], else_=0)).label('present')
    ).filter(Attendance.student_id == student_id)

    if subject_id:
        q = q.filter(Attendance.subject_id == subject_id)
    if from_date:
        q = q.filter(Attendance.date >= from_date)
    if to_date:
        q = q.filter(Attendance.date <= to_date)
    row = q.one_or_none()
    if not row or (row.total or 0) == 0:
        return 0.0
    total = row.total or 0
    present = row.present or 0
    return round((present / total) * 100, 2)

def get_student_subject_attendance(student_id):
    student = Student.query.get(student_id)
    if not student:
        return []
    subjects = Subject.query.filter_by(program_id=student.program_id, semester=student.semester).all()
    result = []
    for subject in subjects:
        agg = db.session.query(
            func.count(Attendance.id).label('total'),
            func.sum(case([(Attendance.status.in_(['Present', 'Late', 'OD']), 1)], else_=0)).label('present')
        ).filter(Attendance.student_id == student_id, Attendance.subject_id == subject.id).one()
        total = agg.total or 0
        present = agg.present or 0
        percentage = round((present / total * 100), 2) if total > 0 else 0.0
        result.append({
            'subject_code': subject.code,
            'subject_name': subject.name,
            'subject_type': subject.subject_type,
            'total': total,
            'present': present,
            'percentage': percentage
        })
    return result

def get_defaulter_students(threshold=75):
    # Aggregate attendance per student in one query (avoid N+1)
    agg_q = db.session.query(
        Attendance.student_id.label('student_id'),
        func.count(Attendance.id).label('total'),
        func.sum(case([(Attendance.status.in_(['Present', 'Late', 'OD']), 1)], else_=0)).label('present')
    ).group_by(Attendance.student_id).subquery()

    joined = db.session.query(
        Student, agg_q.c.total, agg_q.c.present
    ).join(agg_q, Student.id == agg_q.c.student_id).filter(Student.is_active == True)

    defaulters = []
    for student, total, present in joined:
        total = total or 0
        present = present or 0
        perc = round((present / total * 100), 2) if total > 0 else 0.0
        if perc < threshold:
            defaulters.append({'student': student, 'percentage': perc})
    # Also include students with zero records (total 0) as defaulters at 0%
    zero_q = db.session.query(Student).filter(~Student.id.in_(db.session.query(Attendance.student_id)), Student.is_active == True)
    for s in zero_q:
        if 0 < threshold:
            defaulters.append({'student': s, 'percentage': 0.0})
    defaulters.sort(key=lambda x: x['percentage'])
    return defaulters

# ==================== TEMPLATES ====================
# Put base template first so subsequent templates can replace correctly.
BASE_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Attendance System{% endblock %}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #2563eb;
            --primary-dark: #1d4ed8;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --info: #3b82f6;
            --dark: #1f2937;
            --light: #f3f4f6;
            --border: #e5e7eb;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--light);
            line-height: 1.6;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .navbar {
            background: linear-gradient(135deg, var(--primary), var(--primary-dark));
            color: white;
            padding: 15px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .navbar .container { display: flex; justify-content: space-between; align-items: center; }
        .navbar h1 { font-size: 1.5rem; font-weight: 700; }
        .navbar a { color: white; text-decoration: none; margin-left: 18px; transition: opacity 0.2s; font-weight: 500; }
        .navbar a:hover { opacity: 0.8; }
        .card { background: white; border-radius: 12px; padding: 25px; margin: 20px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); transition: box-shadow 0.2s; }
        .card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        .card h3 { margin-bottom: 20px; color: var(--dark); font-size: 1.25rem; border-bottom: 2px solid var(--light); padding-bottom: 10px; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; transition: all 0.2s; display: inline-block; text-decoration: none; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
        .btn-primary { background: var(--primary); color: white; }
        .btn-success { background: var(--success); color: white; }
        .btn-danger { background: var(--danger); color: white; }
        .btn-warning { background: var(--warning); color: white; }
        .btn-info { background: var(--info); color: white; }
        .btn-sm { padding: 6px 12px; font-size: 12px; }
        .form-group { margin: 15px 0; }
        .form-group label { display: block; margin-bottom: 8px; font-weight: 600; color: var(--dark); }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 12px; border: 2px solid var(--border); border-radius: 8px; font-size: 14px; transition: border-color 0.2s; }
        .form-group input:focus, .form-group select:focus, .form-group textarea:focus { outline: none; border-color: var(--primary); }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        .alert { padding: 15px 20px; border-radius: 8px; margin: 15px 0; border-left: 4px solid; }
        .alert-success { background: #d1fae5; color: #065f46; border-color: var(--success); }
        .alert-danger { background: #fee2e2; color: #991b1b; border-color: var(--danger); }
        .alert-warning { background: #fef3c7; color: #92400e; border-color: var(--warning); }
        .alert-info { background: #dbeafe; color: #1e40af; border-color: var(--info); }
        table { width: 100%; border-collapse: collapse; margin: 20px 0; background: white; }
        table th, table td { padding: 14px; text-align: left; border-bottom: 1px solid var(--border); }
        table th { background: var(--light); font-weight: 700; color: var(--dark); text-transform: uppercase; font-size: 12px; letter-spacing: 0.5px; }
        table tr:hover { background: #fafafa; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }
        .stat-card { background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }
        .stat-card h3 { font-size: 2.5rem; margin: 10px 0; border: none; color: white; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: 600; }
        .badge-success { background: #d1fae5; color: #065f46; }
        .badge-danger { background: #fee2e2; color: #991b1b; }
        .badge-warning { background: #fef3c7; color: #92400e; }
        .badge-info { background: #dbeafe; color: #1e40af; }
        @media (max-width: 768px) {
            .container { padding: 10px; }
            .form-row { grid-template-columns: 1fr; }
            .navbar .container { flex-direction: column; text-align: center; }
            .navbar a { margin: 5px 10px; }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="container">
            <h1>🎓 College Attendance System</h1>
            <div>
                {% if session.username %}
                    <span style="margin-right:15px;">{{ session.username }} ({{ session.role|upper }})</span>
                    <a href="{{ url_for('dashboard') }}">📊 Dashboard</a>
                    {% if session.role == 'teacher' %}
                        <a href="{{ url_for('mark_attendance') }}">✓ Mark Attendance</a>
                        <a href="{{ url_for('view_attendance') }}">📋 View Records</a>
                    {% elif session.role == 'student' %}
                        <a href="{{ url_for('view_attendance') }}">📋 My Attendance</a>
                        <a href="{{ url_for('apply_leave') }}">📝 Apply Leave</a>
                    {% elif session.role == 'admin' %}
                        <a href="{{ url_for('reports_page') }}">📊 Reports</a>
                        <a href="{{ url_for('system_settings') }}">⚙️ Settings</a>
                    {% endif %}
                    <a href="{{ url_for('logout') }}">🚪 Logout</a>
                {% else %}
                    <a href="{{ url_for('login') }}">🔐 Login</a>
                {% endif %}
            </div>
        </div>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
'''

# Build smaller templates by replacing the content block
LOGIN_TEMPLATE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<div style="max-width: 450px; margin: 80px auto;">
    <div class="card">
        <h2 style="text-align:center; margin-bottom:30px; color:var(--primary);">🔐 Login to System</h2>
        <form method="POST">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required autofocus>
            </div>
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%; padding: 14px; font-size: 16px;">
                Login
            </button>
        </form>
        <p style="margin-top:20px; text-align:center; color:#6b7280; font-size:13px;">
            Default: admin/admin123 (change password after first login)
        </p>
    </div>
</div>
{% endblock %}
''')

MANAGE_PROGRAMS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Manage Programs</h2>
<div class="card">
    <h3>Add New Program</h3>
    <form method="POST">
        <div class="form-row">
            <div class="form-group">
                <label>Program Name</label>
                <input type="text" name="name" required placeholder="e.g. Bachelor of Computer Applications">
            </div>
            <div class="form-group">
                <label>Program Code</label>
                <input type="text" name="code" required placeholder="e.g. BCA">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Type</label>
                <select name="type" required>
                    <option value="UG">Under Graduate (UG)</option>
                    <option value="PG">Post Graduate (PG)</option>
                </select>
            </div>
            <div class="form-group">
                <label>Duration (Semesters)</label>
                <input type="number" name="duration" min="2" max="12" required placeholder="e.g. 6">
            </div>
        </div>
        <button type="submit" class="btn btn-success">Create Program</button>
    </form>
</div>
<div class="card">
    <h3>Existing Programs</h3>
    <table>
        <thead>
            <tr><th>ID</th><th>Name</th><th>Code</th><th>Type</th><th>Duration</th><th>Created</th></tr>
        </thead>
        <tbody>
            {% for prog in programs %}
            <tr>
                <td>{{ prog.id }}</td>
                <td>{{ prog.name }}</td>
                <td><span class="badge badge-primary">{{ prog.code }}</span></td>
                <td><span class="badge {% if prog.type == 'UG' %}badge-success{% else %}badge-info{% endif %}">{{ prog.type }}</span></td>
                <td>{{ prog.duration }} semesters</td>
                <td>{{ prog.created_at.strftime('%Y-%m-%d') }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
''')

MANAGE_STUDENTS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Manage Students</h2>
<div class="card">
    <h3>Add New Student</h3>
    <form method="POST">
        <div class="form-row">
            <div class="form-group">
                <label>Username</label>
                <input type="text" name="username" required>
            </div>
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Password</label>
                <input type="password" name="password" required>
            </div>
            <div class="form-group">
                <label>Roll Number</label>
                <input type="text" name="roll_number" required>
            </div>
        </div>
        <div class="form-group">
            <label>Full Name</label>
            <input type="text" name="name" required>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Program</label>
                <select name="program_id" required>
                    {% for prog in programs %}
                    <option value="{{ prog.id }}">{{ prog.name }} ({{ prog.code }})</option>
                    {% endfor %}
                </select>
            </div>
            <div class="form-group">
                <label>Batch</label>
                <input type="text" name="batch" placeholder="2024">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Division</label>
                <input type="text" name="division" placeholder="A">
            </div>
            <div class="form-group">
                <label>Semester</label>
                <input type="number" name="semester" min="1" max="12">
            </div>
        </div>
        <div class="form-row">
            <div class="form-group">
                <label>Parent Contact</label>
                <input type="text" name="parent_contact" placeholder="+91-XXXXXXXXXX">
            </div>
            <div class="form-group">
                <label>Parent Email</label>
                <input type="email" name="parent_email" placeholder="parent@example.com">
            </div>
        </div>
        <button type="submit" class="btn btn-success">Add Student</button>
    </form>
</div>

<div class="card">
    <h3>Bulk Upload Students</h3>
    <form method="POST" action="{{ url_for('bulk_upload_students') }}" enctype="multipart/form-data">
        <div class="form-group">
            <label>Upload CSV File</label>
            <input type="file" name="file" accept=".csv" required>
            <small>CSV Format: username,email,password,roll_number,name,program_id,batch,division,semester</small>
        </div>
        <button type="submit" class="btn btn-info">Upload CSV</button>
    </form>
</div>

<div class="card">
    <h3>Student List</h3>
    <table>
        <thead>
            <tr><th>Roll No</th><th>Name</th><th>Program</th><th>Batch</th><th>Division</th><th>Semester</th><th>Status</th></tr>
        </thead>
        <tbody>
            {% for stud, prog, user in students %}
            <tr>
                <td>{{ stud.roll_number }}</td>
                <td>{{ stud.name }}</td>
                <td>{{ prog.code }}</td>
                <td>{{ stud.batch }}</td>
                <td>{{ stud.division }}</td>
                <td>{{ stud.semester }}</td>
                <td>
                    {% if stud.is_active %}
                        <span class="badge badge-success">Active</span>
                    {% else %}
                        <span class="badge badge-danger">Inactive</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
''')

MANAGE_TEACHERS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Manage Teachers</h2>
<div class="card">
    <h3>Add Teacher</h3>
    <form method="POST">
        <div class="form-row">
            <input type="text" name="username" placeholder="Username" required>
            <input type="email" name="email" placeholder="Email" required>
        </div>
        <div class="form-row">
            <input type="password" name="password" placeholder="Password" required>
            <input type="text" name="name" placeholder="Full Name" required>
        </div>
        <div class="form-row">
            <select name="teacher_type"><option value="Major">Major</option><option value="Minor">Minor</option><option value="Assistant">Assistant</option></select>
            <input type="text" name="contact" placeholder="Contact">
        </div>
        <button class="btn btn-success" type="submit">Add Teacher</button>
    </form>
</div>
<div class="card">
    <table>
        <thead><tr><th>Name</th><th>Type</th><th>Email</th><th>Contact</th></tr></thead>
        <tbody>{% for teach, user in teachers %}<tr><td>{{ teach.name }}</td><td>{{ teach.teacher_type }}</td><td>{{ user.email }}</td><td>{{ teach.contact }}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

MANAGE_SUBJECTS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Manage Subjects</h2>
<div class="card">
    <form method="POST">
        <div class="form-row">
            <input name="code" placeholder="Subject Code" required>
            <input name="name" placeholder="Subject Name" required>
        </div>
        <div class="form-row">
            <input name="credits" type="number" placeholder="Credits">
            <select name="subject_type"><option value="Major">Major</option><option value="Minor">Minor</option><option value="AEC">AEC</option><option value="VAC">VAC</option><option value="MDC">MDC</option><option value="SEC">SEC</option><option value="Lab">Lab</option></select>
        </div>
        <div class="form-row">
            <select name="class_type"><option value="Theory">Theory</option><option value="Lab">Lab</option><option value="Seminar">Seminar</option></select>
            <select name="program_id">{% for p in programs %}<option value="{{p.id}}">{{p.name}}</option>{% endfor %}</select>
        </div>
        <div class="form-row">
            <input name="semester" type="number" placeholder="Semester">
            <input name="weekly_hours" type="number" placeholder="Weekly Hours" value="3">
        </div>
        <button class="btn btn-success" type="submit">Add Subject</button>
    </form>
</div>
<div class="card">
    <table>
        <thead><tr><th>Code</th><th>Name</th><th>Type</th><th>Class</th><th>Credits</th></tr></thead>
        <tbody>{% for s, p in subjects %}<tr><td>{{s.code}}</td><td>{{s.name}}</td><td>{{s.subject_type}}</td><td>{{s.class_type}}</td><td>{{s.credits}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

ASSIGN_SUBJECTS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Assign Subjects to Teachers</h2>
<div class="card">
    <form method="POST">
        <div class="form-row">
            <select name="teacher_id">{% for t in teachers %}<option value="{{t.id}}">{{t.name}}</option>{% endfor %}</select>
            <select name="subject_id">{% for s in subjects %}<option value="{{s.id}}">{{s.name}} ({{s.code}})</option>{% endfor %}</select>
        </div>
        <div class="form-row">
            <input name="batch" placeholder="Batch">
            <input name="division" placeholder="Division">
        </div>
        <div class="form-row">
            <input name="semester" type="number" placeholder="Semester">
            <input name="academic_year" placeholder="Academic Year (e.g. 2024-25)">
        </div>
        <button class="btn btn-success" type="submit">Assign</button>
    </form>
</div>
<div class="card">
    <table>
        <thead><tr><th>Teacher</th><th>Subject</th><th>Batch</th><th>Division</th></tr></thead>
        <tbody>{% for ts, t, s in assignments %}<tr><td>{{t.name}}</td><td>{{s.name}}</td><td>{{ts.batch}}</td><td>{{ts.division}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

MANAGE_TIMETABLE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Manage Timetable</h2>
<div class="card">
    <form method="POST">
        <div class="form-row">
            <select name="subject_id">{% for s in subjects %}<option value="{{s.id}}">{{s.name}}</option>{% endfor %}</select>
            <select name="teacher_id">{% for t in teachers %}<option value="{{t.id}}">{{t.name}}</option>{% endfor %}</select>
        </div>
        <div class="form-row">
            <select name="day"><option>Monday</option><option>Tuesday</option><option>Wednesday</option><option>Thursday</option><option>Friday</option><option>Saturday</option></select>
            <input name="period" type="number" placeholder="Period">
        </div>
        <div class="form-row">
            <select name="session_type"><option value="FN">FN</option><option value="AN">AN</option><option value="Period">Period</option></select>
            <input name="room" placeholder="Room">
        </div>
        <div class="form-row">
            <input name="batch" placeholder="Batch">
            <input name="division" placeholder="Division">
        </div>
        <div class="form-row">
            <input name="semester" type="number" placeholder="Semester">
            <div></div>
        </div>
        <button class="btn btn-success" type="submit">Add</button>
    </form>
</div>
<div class="card">
    <table>
        <thead><tr><th>Day</th><th>Period</th><th>Subject</th><th>Teacher</th><th>Room</th></tr></thead>
        <tbody>{% for tt, s, t in timetable %}<tr><td>{{tt.day}}</td><td>{{tt.period}}</td><td>{{s.name}}</td><td>{{t.name}}</td><td>{{tt.room}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

MARK_ATTENDANCE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<script>
let studentsData = [];
function loadStudents() {
    const sel = document.getElementById('subject');
    const opt = sel.options[sel.selectedIndex];
    const batch = opt.getAttribute('data-batch') || document.getElementById('batch').value;
    const div = opt.getAttribute('data-division') || document.getElementById('division').value;
    const sid = sel.value;
    if(!batch || !div) {
        alert('Please set batch & division (or select a subject option that contains them).');
        return;
    }
    fetch(`/attendance/students/${sid}/${batch}/${div}`)
        .then(r => r.json())
        .then(students => {
            studentsData = students;
            let html = '<thead><tr><th>Roll</th><th>Name</th><th>Status</th><th>Remarks</th></tr></thead><tbody>';
            students.forEach(s => {
                html += `<tr><td>${s.roll_number}</td><td>${s.name}</td><td><select class="status-sel" data-id="${s.id}"><option>Present</option><option>Absent</option><option>Late</option><option>EarlyExit</option><option>OD</option><option>ML</option><option>EL</option></select></td><td><input class="remarks-inp" data-id="${s.id}"></td></tr>`;
            });
            document.getElementById('stuTable').innerHTML = html;
            document.getElementById('stuList').style.display = 'block';
        });
}
function markAll(status) {
    document.querySelectorAll('.status-sel').forEach(s => s.value = status);
}
function submitAtt() {
    const att = [];
    document.querySelectorAll('.status-sel').forEach(s => {
        att.push({
            student_id: parseInt(s.getAttribute('data-id')),
            status: s.value,
            remarks: document.querySelector(`.remarks-inp[data-id="${s.getAttribute('data-id')}"]`).value || ''
        });
    });
    fetch('/attendance/mark', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            subject_id: parseInt(document.getElementById('subject').value),
            date: document.getElementById('date').value,
            session_type: document.getElementById('session_type').value,
            period: document.getElementById('period').value ? parseInt(document.getElementById('period').value) : null,
            attendance: att
        })
    }).then(r => r.json()).then(d => { alert(d.message); if(d.success) location.reload(); });
}
document.addEventListener('DOMContentLoaded', function(){
    if(!document.getElementById('date').value) {
        document.getElementById('date').value = new Date().toISOString().slice(0,10);
    }
});
</script>
<div class="card"><h3>Mark Attendance</h3>
<div class="form-row">
<select id="subject">{% for ts, s in teacher_subjects %}<option value="{{s.id}}" data-batch="{{ts.batch}}" data-division="{{ts.division}}">{{s.name}} - {{ts.batch}}-{{ts.division}}</option>{% endfor %}</select>
<input id="batch" placeholder="Batch (if subject option doesn't have one)">
<input id="division" placeholder="Division (if subject option doesn't have one)">
</div>
<div class="form-row">
<input id="date" type="date" value="{{ default_date }}">
<select id="session_type"><option value="FN">FN</option><option value="AN">AN</option><option value="Period">Period</option></select>
<input id="period" type="number" placeholder="Period (1-5)">
</div>
<button class="btn btn-primary" onclick="loadStudents()">Load Students</button></div>

<div class="card" id="stuList" style="display:none"><button class="btn btn-success" onclick="markAll('Present')">All Present</button><button class="btn btn-danger" onclick="markAll('Absent')">All Absent</button><table id="stuTable"></table><button class="btn btn-primary" onclick="submitAtt()">Submit</button></div>
{% endblock %}
''')

VIEW_ATTENDANCE_STUDENT = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>My Attendance</h2>
<div class="card">
    <table>
        <thead><tr><th>Date</th><th>Subject</th><th>Teacher</th><th>Period</th><th>Status</th><th>Remarks</th></tr></thead>
        <tbody>{% for a, s, t in attendance %}<tr><td>{{a.date}}</td><td>{{s.name}}</td><td>{{t.name}}</td><td>{{a.session_type}}{% if a.period %}-{{a.period}}{% endif %}</td><td><span class="badge {% if a.status == "Present" %}badge-success{% else %}badge-danger{% endif %}">{{a.status}}</span></td><td>{{a.remarks}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

VIEW_ATTENDANCE_TEACHER = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Attendance Records</h2>
<div class="card">
    <table>
        <thead><tr><th>Date</th><th>Subject</th><th>Student</th><th>Status</th></tr></thead>
        <tbody>{% for a, s, st in attendance %}<tr><td>{{a.date}}</td><td>{{s.code}}</td><td>{{st.roll_number}}</td><td>{{a.status}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

VIEW_TIMETABLE_TEACHER = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>My Timetable</h2>
<div class="card">
    <table>{% for tt, s in timetable %}<tr><td>{{tt.day}}</td><td>Period {{tt.period}}</td><td>{{s.name}}</td><td>{{tt.room}}</td></tr>{% endfor %}</table>
</div>
{% endblock %}
''')

APPLY_LEAVE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Apply for Leave</h2>
<div class="card">
    <form method="POST">
        <div class="form-row">
            <input name="from_date" type="date" required>
            <input name="to_date" type="date" required>
        </div>
        <div class="form-row">
            <select name="leave_type"><option value="Medical">Medical</option><option value="Personal">Personal</option><option value="Emergency">Emergency</option></select>
            <input type="text" name="dummy" style="display:none;">
        </div>
        <div class="form-group">
            <textarea name="reason" placeholder="Reason" required></textarea>
        </div>
        <button class="btn btn-primary" type="submit">Apply</button>
    </form>
</div>
<div class="card">
    <table>
        <thead><tr><th>From</th><th>To</th><th>Status</th></tr></thead>
        <tbody>{% for l in leaves %}<tr><td>{{l.from_date}}</td><td>{{l.to_date}}</td><td>{{l.status}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

MANAGE_LEAVES = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Manage Leave Requests</h2>
<div class="card">
    <table>
        <thead><tr><th>Student</th><th>From</th><th>To</th><th>Type</th><th>Status</th><th>Action</th></tr></thead>
        <tbody>{% for l, s, p in leaves %}<tr><td>{{s.roll_number}} - {{s.name}}</td><td>{{l.from_date}}</td><td>{{l.to_date}}</td><td>{{l.leave_type}}</td><td>{{l.status}}</td><td>{% if l.status == "pending" %}<a href="{{ url_for('approve_leave', leave_id=l.id) }}" class="btn btn-success btn-sm">Approve</a> <a href="{{ url_for('reject_leave', leave_id=l.id) }}" class="btn btn-danger btn-sm">Reject</a>{% endif %}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

REPORTS_PAGE = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Reports</h2>
<div class="card">
    <a href="{{ url_for("student_wise_report") }}" class="btn btn-primary">Student-wise Report</a>
    <a href="{{ url_for("subject_wise_report") }}" class="btn btn-success">Subject-wise Report</a>
    <a href="{{ url_for("defaulters_report") }}" class="btn btn-danger">Defaulters Report</a>
</div>
{% endblock %}
''')

STUDENT_WISE_REPORT = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Student-wise Report</h2>
<div class="card">
    <table>
        <thead><tr><th>Roll</th><th>Name</th><th>Attendance %</th><th>Status</th></tr></thead>
        <tbody>{% for r in report_data %}<tr><td>{{r.student.roll_number}}</td><td>{{r.student.name}}</td><td>{{r.percentage}}%</td><td>{{r.status}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

SUBJECT_WISE_REPORT = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Subject-wise Report</h2>
<div class="card">
    <form method="GET">
        <select name="subject_id">{% for s in subjects %}<option value="{{s.id}}">{{s.name}}</option>{% endfor %}</select>
        <button class="btn btn-primary" type="submit">View</button>
    </form>
</div>
{% if report_data %}
<div class="card">
    <table>
        <thead><tr><th>Roll</th><th>Name</th><th>Total</th><th>Present</th><th>%</th></tr></thead>
        <tbody>{% for r in report_data %}<tr><td>{{r.student.roll_number}}</td><td>{{r.student.name}}</td><td>{{r.total}}</td><td>{{r.present}}</td><td>{{r.percentage}}%</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endif %}
{% endblock %}
''')

DEFAULTERS_REPORT = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Defaulters (Below {{threshold}}%)</h2>
<div class="card">
    <table>
        <thead><tr><th>Roll</th><th>Name</th><th>%</th></tr></thead>
        <tbody>{% for d in defaulters %}<tr><td>{{d.student.roll_number}}</td><td>{{d.student.name}}</td><td>{{d.percentage}}%</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

SYSTEM_SETTINGS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>System Settings</h2>
<div class="card">
    <form method="POST">
        <div class="form-row">
            <input name="attendance_lock_hours" value="{{settings.get('attendance_lock_hours', 24)}}" placeholder="Lock after X hours">
            <input name="min_attendance_percentage" value="{{settings.get('min_attendance_percentage', 75)}}" placeholder="Min percentage">
        </div>
        <button class="btn btn-success" type="submit">Save</button>
    </form>
</div>
{% endblock %}
''')

AUDIT_LOGS = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Audit Logs</h2>
<div class="card">
    <table>
        <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Details</th></tr></thead>
        <tbody>{% for log in logs.items %}<tr><td>{{log.timestamp}}</td><td>User #{{log.user_id}}</td><td>{{log.action}}</td><td>{{log.details}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

LOGIN_HISTORY = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Login History</h2>
<div class="card">
    <table>
        <thead><tr><th>User</th><th>Login Time</th><th>IP</th></tr></thead>
        <tbody>{% for h, u in history %}<tr><td>{{u.username}}</td><td>{{h.login_time}}</td><td>{{h.ip_address}}</td></tr>{% endfor %}</tbody>
    </table>
</div>
{% endblock %}
''')

TEACHER_DASHBOARD = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Teacher Dashboard - {{ teacher.name }}</h2>
<div class="card">
    <h3>📅 Today's Classes ({{ current_day }})</h3>
    {% if timetable %}
        <table>
            <thead><tr><th>Period</th><th>Subject</th><th>Room</th><th>Batch/Division</th><th>Action</th></tr></thead>
            <tbody>
                {% for tt in timetable %}
                <tr>
                    <td>{{ tt.session_type }} - Period {{ tt.period }}</td>
                    <td>{{ tt.subject_id }}</td>
                    <td>{{ tt.room }}</td>
                    <td>{{ tt.batch }}-{{ tt.division }}</td>
                    <td><a href="{{ url_for('mark_attendance') }}" class="btn btn-success btn-sm">Mark Attendance</a></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>No classes scheduled for today.</p>
    {% endif %}
</div>

{% if pending %}
<div class="card" style="border-left: 4px solid var(--warning);">
    <h3>⚠️ Pending Attendance</h3>
    <p style="color: var(--warning); font-weight: 600;">
        You have {{ pending|length }} pending attendance record(s) to mark.
    </p>
    <ul>
        {% for p in pending %}
            <li>{{ p.subject.name }} - {{ p.timetable.batch }}-{{ p.timetable.division }} (Period {{ p.timetable.period }})</li>
        {% endfor %}
    </ul>
    <a href="{{ url_for('mark_attendance') }}" class="btn btn-warning">Mark Now</a>
</div>
{% endif %}

<div class="card">
    <h3>📚 My Subjects</h3>
    <table>
        <thead><tr><th>Subject Code</th><th>Subject Name</th><th>Type</th><th>Batch</th><th>Division</th></tr></thead>
        <tbody>
            {% for subj, ts in my_subjects %}
            <tr>
                <td>{{ subj.code }}</td>
                <td>{{ subj.name }}</td>
                <td><span class="badge badge-info">{{ subj.subject_type }}</span></td>
                <td>{{ ts.batch }}</td>
                <td>{{ ts.division }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="card">
    <h3>🕒 Recently Marked Attendance</h3>
    {% if recent_attendance %}
        <table>
            <thead><tr><th>Date</th><th>Subject</th><th>Student</th><th>Status</th><th>Marked At</th></tr></thead>
            <tbody>
                {% for att, subj, stud in recent_attendance %}
                <tr>
                    <td>{{ att.date }}</td>
                    <td>{{ subj.code }}</td>
                    <td>{{ stud.roll_number }} - {{ stud.name }}</td>
                    <td>
                        {% if att.status == 'Present' %}
                            <span class="badge badge-success">{{ att.status }}</span>
                        {% elif att.status == 'Absent' %}
                            <span class="badge badge-danger">{{ att.status }}</span>
                        {% else %}
                            <span class="badge badge-warning">{{ att.status }}</span>
                        {% endif %}
                    </td>
                    <td>{{ att.marked_at.strftime('%H:%M') }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>No recent attendance records.</p>
    {% endif %}
</div>

<div class="card">
    <h3>⚡ Quick Actions</h3>
    <a href="{{ url_for('mark_attendance') }}" class="btn btn-primary">✓ Mark Attendance</a>
    <a href="{{ url_for('view_attendance') }}" class="btn btn-info">📋 View Records</a>
    <a href="{{ url_for('view_timetable') }}" class="btn btn-success">📅 My Timetable</a>
    <a href="{{ url_for('manage_leaves') }}" class="btn btn-warning">📝 Manage Leaves</a>
</div>
{% endblock %}
''')

STUDENT_DASHBOARD = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Student Dashboard</h2>
<div class="card">
    <h3>👤 My Profile</h3>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
        <div><strong>Roll Number:</strong> {{ student.roll_number }}</div>
        <div><strong>Name:</strong> {{ student.name }}</div>
        <div><strong>Program:</strong> {{ program.name }} ({{ program.code }})</div>
        <div><strong>Batch:</strong> {{ student.batch }}</div>
        <div><strong>Division:</strong> {{ student.division }}</div>
        <div><strong>Semester:</strong> {{ student.semester }}</div>
    </div>
</div>

<div class="card">
    <h3>📊 My Attendance Overview</h3>
    <div style="text-align: center; margin: 30px 0;">
        <div style="font-size: 4rem; font-weight: bold; 
                    color: {% if overall_percentage >= 75 %}var(--success){% else %}var(--danger){% endif %};">
            {{ overall_percentage }}%
        </div>
        <p style="font-size: 1.2rem; color: #6b7280;">Overall Attendance Percentage</p>
        {% if overall_percentage < 75 %}
            <p style="color: var(--danger); font-weight: 600; margin-top: 10px;">
                ⚠️ Warning: Your attendance is below 75%!
            </p>
        {% endif %}
    </div>
</div>

<div class="card">
    <h3>📚 Subject-wise Attendance</h3>
    <table>
        <thead><tr><th>Subject Code</th><th>Subject Name</th><th>Type</th><th>Total</th><th>Present</th><th>Percentage</th><th>Status</th></tr></thead>
        <tbody>
            {% for sa in subject_attendance %}
            <tr>
                <td>{{ sa.subject_code }}</td>
                <td>{{ sa.subject_name }}</td>
                <td><span class="badge badge-info">{{ sa.subject_type }}</span></td>
                <td>{{ sa.total }}</td>
                <td>{{ sa.present }}</td>
                <td><strong>{{ sa.percentage }}%</strong></td>
                <td>
                    {% if sa.percentage >= 75 %}
                        <span class="badge badge-success">✓ Good</span>
                    {% else %}
                        <span class="badge badge-danger">⚠ Low</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="card">
    <h3>📅 Today's Timetable</h3>
    {% if upcoming_classes %}
        <table>
            <thead><tr><th>Period</th><th>Subject</th><th>Teacher</th><th>Room</th></tr></thead>
            <tbody>
                {% for tt, subj, teach in upcoming_classes %}
                <tr>
                    <td>{{ tt.session_type }} - Period {{ tt.period }}</td>
                    <td>{{ subj.name }} ({{ subj.code }})</td>
                    <td>{{ teach.name }}</td>
                    <td>{{ tt.room }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>No classes scheduled for today.</p>
    {% endif %}
</div>

<div class="card">
    <h3>📝 My Leave Requests</h3>
    {% if leave_requests %}
        <table>
            <thead><tr><th>From</th><th>To</th><th>Type</th><th>Status</th><th>Applied On</th></tr></thead>
            <tbody>
                {% for leave in leave_requests %}
                <tr>
                    <td>{{ leave.from_date }}</td>
                    <td>{{ leave.to_date }}</td>
                    <td>{{ leave.leave_type }}</td>
                    <td>
                        {% if leave.status == 'approved' %}
                            <span class="badge badge-success">APPROVED</span>
                        {% elif leave.status == 'rejected' %}
                            <span class="badge badge-danger">REJECTED</span>
                        {% else %}
                            <span class="badge badge-warning">PENDING</span>
                        {% endif %}
                    </td>
                    <td>{{ leave.created_at.strftime('%Y-%m-%d') }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    {% else %}
        <p>No leave requests found.</p>
    {% endif %}
</div>

<div class="card">
    <h3>⚡ Quick Actions</h3>
    <a href="{{ url_for('view_attendance') }}" class="btn btn-primary">📋 View Detailed Attendance</a>
    <a href="{{ url_for('apply_leave') }}" class="btn btn-success">📝 Apply for Leave</a>
    <a href="{{ url_for('view_timetable') }}" class="btn btn-info">📅 My Timetable</a>
</div>
{% endblock %}
''')

ADMIN_DASHBOARD = BASE_TEMPLATE.replace('{% block content %}{% endblock %}', '''
{% block content %}
<h2>Admin Dashboard</h2>
<div class="stats">
    <div class="stat-card">
        <p>TOTAL STUDENTS</p>
        <h3>{{ stats.total_students }}</h3>
    </div>
    <div class="stat-card success">
        <p>TOTAL TEACHERS</p>
        <h3>{{ stats.total_teachers }}</h3>
    </div>
    <div class="stat-card warning">
        <p>PROGRAMS (UG: {{stats.ug_programs}}, PG: {{stats.pg_programs}})</p>
        <h3>{{ stats.total_programs }}</h3>
    </div>
    <div class="stat-card danger">
        <p>PENDING LEAVES</p>
        <h3>{{ stats.pending_leaves }}</h3>
    </div>
</div>

<div class="card">
    <h3>📋 Quick Actions</h3>
    <a href="{{ url_for('manage_programs') }}" class="btn btn-primary">Manage Programs</a>
    <a href="{{ url_for('manage_students') }}" class="btn btn-success">Manage Students</a>
    <a href="{{ url_for('manage_teachers') }}" class="btn btn-info">Manage Teachers</a>
    <a href="{{ url_for('manage_subjects') }}" class="btn btn-warning">Manage Subjects</a>
    <a href="{{ url_for('assign_subjects') }}" class="btn btn-primary">Assign Subjects</a>
    <a href="{{ url_for('manage_timetable') }}" class="btn btn-success">Manage Timetable</a>
    <a href="{{ url_for('manage_leaves') }}" class="btn btn-info">Manage Leaves</a>
    <a href="{{ url_for('reports_page') }}" class="btn btn-warning">View Reports</a>
</div>

{% if defaulters %}
<div class="card">
    <h3>⚠️ Attendance Defaulters (Below 75%)</h3>
    <table>
        <thead><tr><th>Roll No</th><th>Name</th><th>Batch</th><th>Attendance %</th></tr></thead>
        <tbody>
            {% for d in defaulters %}
            <tr>
                <td>{{ d.student.roll_number }}</td>
                <td>{{ d.student.name }}</td>
                <td>{{ d.student.batch }}-{{ d.student.division }}</td>
                <td><span class="badge badge-danger">{{ d.percentage }}%</span></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endif %}

<div class="card">
    <h3>📜 Recent Activity</h3>
    <table>
        <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Details</th></tr></thead>
        <tbody>
            {% for log in recent_logs %}
            <tr>
                <td>{{ log.timestamp.strftime('%Y-%m-%d %H:%M') }}</td>
                <td>User #{{ log.user_id }}</td>
                <td>{{ log.action }}</td>
                <td>{{ log.details[:50] }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
''')

# ==================== ROUTES ====================

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(username=username).first()
        if user and user.is_active:
            if user.failed_attempts >= 5:
                flash('Account locked due to multiple failed attempts. Contact administrator.', 'danger')
                return redirect(url_for('login'))
            if check_password_hash(user.password, password):
                session.clear()
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role
                session.permanent = True
                user.last_login = datetime.utcnow()
                user.failed_attempts = 0
                login_hist = LoginHistory(
                    user_id=user.id,
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent', '')[:200]
                )
                db.session.add(login_hist)
                db.session.commit()
                log_audit('Login', f'User {username} logged in')
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('dashboard'))
            else:
                user.failed_attempts += 1
                db.session.commit()
                flash('Invalid credentials', 'danger')
        else:
            flash('Invalid credentials or account inactive', 'danger')
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
@login_required
def logout():
    login_hist = LoginHistory.query.filter_by(user_id=session['user_id'], logout_time=None).first()
    if login_hist:
        login_hist.logout_time = datetime.utcnow()
        db.session.commit()
    log_audit('Logout', f'User {session.get("username")} logged out')
    session.clear()
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'admin':
        stats = {
            'total_students': Student.query.filter_by(is_active=True).count(),
            'total_teachers': Teacher.query.filter_by(is_active=True).count(),
            'total_programs': Program.query.count(),
            'total_subjects': Subject.query.count(),
            'pending_leaves': LeaveRequest.query.filter_by(status='pending').count(),
            'ug_programs': Program.query.filter_by(type='UG').count(),
            'pg_programs': Program.query.filter_by(type='PG').count(),
        }
        recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(10).all()
        defaulters = get_defaulter_students(threshold=75)
        return render_template_string(ADMIN_DASHBOARD,
                                      stats=stats,
                                      recent_logs=recent_logs,
                                      defaulters=defaulters[:10])
    elif role == 'teacher':
        teacher = Teacher.query.filter_by(user_id=session['user_id']).first()
        today = date.today()
        current_day = today.strftime('%A')
        timetable = Timetable.query.filter_by(teacher_id=teacher.id, day=current_day).order_by(Timetable.period).all()
        pending = []
        for tt in timetable:
            exists = Attendance.query.filter_by(subject_id=tt.subject_id, teacher_id=teacher.id, date=today).first()
            if not exists:
                subj = Subject.query.get(tt.subject_id)
                pending.append({'timetable': tt, 'subject': subj})
        my_subjects = db.session.query(Subject, TeacherSubject).join(TeacherSubject, Subject.id == TeacherSubject.subject_id).filter(TeacherSubject.teacher_id == teacher.id).all()
        recent_attendance = db.session.query(Attendance, Subject, Student).join(Subject, Attendance.subject_id == Subject.id).join(Student, Attendance.student_id == Student.id).filter(Attendance.teacher_id == teacher.id).order_by(Attendance.marked_at.desc()).limit(10).all()
        return render_template_string(TEACHER_DASHBOARD,
                                      timetable=timetable,
                                      pending=pending,
                                      teacher=teacher,
                                      my_subjects=my_subjects,
                                      recent_attendance=recent_attendance,
                                      today=today,
                                      current_day=current_day)
    elif role == 'student':
        student = Student.query.filter_by(user_id=session['user_id']).first()
        program = Program.query.get(student.program_id)
        overall_percentage = calculate_attendance_percentage(student.id)
        subject_attendance = get_student_subject_attendance(student.id)
        recent_attendance = db.session.query(Attendance, Subject).join(Subject, Attendance.subject_id == Subject.id).filter(Attendance.student_id == student.id).order_by(Attendance.date.desc()).limit(15).all()
        current_day = date.today().strftime('%A')
        upcoming_classes = db.session.query(Timetable, Subject, Teacher).join(Subject, Timetable.subject_id == Subject.id).join(Teacher, Timetable.teacher_id == Teacher.id).filter(Timetable.batch == student.batch, Timetable.division == student.division, Timetable.day == current_day).order_by(Timetable.period).all()
        leave_requests = LeaveRequest.query.filter_by(student_id=student.id).order_by(LeaveRequest.created_at.desc()).limit(5).all()
        return render_template_string(STUDENT_DASHBOARD,
                                      student=student,
                                      program=program,
                                      overall_percentage=overall_percentage,
                                      subject_attendance=subject_attendance,
                                      recent_attendance=recent_attendance,
                                      upcoming_classes=upcoming_classes,
                                      leave_requests=leave_requests)
    return 'Dashboard'

# -------------------- Admin Management --------------------
@app.route('/admin/programs', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_programs():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        type_ = request.form.get('type')
        duration = request.form.get('duration') or None
        if not name or not code:
            flash('Name and code required', 'danger')
            return redirect(url_for('manage_programs'))
        if Program.query.filter_by(code=code).first():
            flash('Program code already exists', 'danger')
            return redirect(url_for('manage_programs'))
        program = Program(name=name, code=code, type=type_, duration=int(duration) if duration else None)
        db.session.add(program)
        db.session.commit()
        log_audit('Create Program', f'Created program: {name}')
        flash('Program created successfully', 'success')
        return redirect(url_for('manage_programs'))
    programs = Program.query.all()
    return render_template_string(MANAGE_PROGRAMS, programs=programs)

@app.route('/admin/students', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'teacher')
def manage_students():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        password = generate_password_hash(request.form.get('password') or 'student123')
        roll_number = (request.form.get('roll_number') or '').strip()
        name = (request.form.get('name') or '').strip()
        program_id = request.form.get('program_id')
        batch = request.form.get('batch')
        division = request.form.get('division')
        semester = request.form.get('semester')
        parent_contact = request.form.get('parent_contact')
        parent_email = request.form.get('parent_email')
        if User.query.filter_by(username=username).first() or Student.query.filter_by(roll_number=roll_number).first():
            flash('Username or roll number already exists', 'danger')
            return redirect(url_for('manage_students'))
        user = User(username=username, email=email, password=password, role='student')
        db.session.add(user)
        db.session.flush()
        student = Student(user_id=user.id, roll_number=roll_number, name=name, program_id=program_id, batch=batch, division=division, semester=semester, parent_contact=parent_contact, parent_email=parent_email)
        db.session.add(student)
        db.session.commit()
        log_audit('Create Student', f'Created student: {name} ({roll_number})')
        flash('Student created successfully', 'success')
        return redirect(url_for('manage_students'))
    students = db.session.query(Student, Program, User).join(Program, Student.program_id == Program.id).join(User, Student.user_id == User.id).all()
    programs = Program.query.all()
    return render_template_string(MANAGE_STUDENTS, students=students, programs=programs)

@app.route('/admin/students/bulk-upload', methods=['POST'])
@login_required
@role_required('admin')
def bulk_upload_students():
    if 'file' not in request.files:
        flash('No file uploaded', 'danger')
        return redirect(url_for('manage_students'))
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'danger')
        return redirect(url_for('manage_students'))
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)
        count = 0
        skipped = 0
        for row in csv_reader:
            username = (row.get('username') or '').strip()
            email = (row.get('email') or '').strip()
            password = generate_password_hash(row.get('password') or 'student123')
            roll_number = (row.get('roll_number') or '').strip()
            name = (row.get('name') or '').strip()
            program_id = row.get('program_id')
            if not username or not roll_number:
                skipped += 1
                continue
            if User.query.filter_by(username=username).first() or Student.query.filter_by(roll_number=roll_number).first():
                skipped += 1
                continue
            user = User(username=username, email=email, password=password, role='student')
            db.session.add(user)
            db.session.flush()
            student = Student(user_id=user.id, roll_number=roll_number, name=name, program_id=program_id, batch=row.get('batch', ''), division=row.get('division', ''), semester=row.get('semester', 1))
            db.session.add(student)
            count += 1
            # commit periodically for large files
            if count % 100 == 0:
                db.session.commit()
        db.session.commit()
        log_audit('Bulk Upload Students', f'Uploaded {count} students, skipped {skipped}')
        flash(f'{count} students uploaded successfully (skipped {skipped})', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error uploading students: {str(e)}', 'danger')
    return redirect(url_for('manage_students'))

@app.route('/admin/teachers', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_teachers():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip()
        password = generate_password_hash(request.form.get('password') or 'teacher123')
        name = (request.form.get('name') or '').strip()
        teacher_type = request.form.get('teacher_type')
        contact = request.form.get('contact')
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('manage_teachers'))
        user = User(username=username, email=email, password=password, role='teacher')
        db.session.add(user)
        db.session.flush()
        teacher = Teacher(user_id=user.id, name=name, teacher_type=teacher_type, contact=contact)
        db.session.add(teacher)
        db.session.commit()
        log_audit('Create Teacher', f'Created teacher: {name}')
        flash('Teacher created successfully', 'success')
        return redirect(url_for('manage_teachers'))
    teachers = db.session.query(Teacher, User).join(User, Teacher.user_id == User.id).all()
    return render_template_string(MANAGE_TEACHERS, teachers=teachers)

@app.route('/admin/subjects', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_subjects():
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        name = (request.form.get('name') or '').strip()
        credits = request.form.get('credits')
        subject_type = request.form.get('subject_type')
        class_type = request.form.get('class_type')
        program_id = request.form.get('program_id')
        semester = request.form.get('semester')
        weekly_hours = request.form.get('weekly_hours', 3)
        if Subject.query.filter_by(code=code).first():
            flash('Subject code already exists', 'danger')
            return redirect(url_for('manage_subjects'))
        subject = Subject(code=code, name=name, credits=int(credits) if credits else None, subject_type=subject_type, class_type=class_type, program_id=program_id, semester=int(semester) if semester else None, weekly_hours=int(weekly_hours))
        db.session.add(subject)
        db.session.commit()
        log_audit('Create Subject', f'Created subject: {name} ({code})')
        flash('Subject created successfully', 'success')
        return redirect(url_for('manage_subjects'))
    subjects = db.session.query(Subject, Program).join(Program, Subject.program_id == Program.id).all()
    programs = Program.query.all()
    return render_template_string(MANAGE_SUBJECTS, subjects=subjects, programs=programs)

@app.route('/admin/assign-subjects', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def assign_subjects():
    if request.method == 'POST':
        teacher_id = request.form.get('teacher_id')
        subject_id = request.form.get('subject_id')
        batch = request.form.get('batch')
        division = request.form.get('division')
        semester = request.form.get('semester')
        academic_year = request.form.get('academic_year')
        assignment = TeacherSubject(teacher_id=teacher_id, subject_id=subject_id, batch=batch, division=division, semester=semester, academic_year=academic_year)
        db.session.add(assignment)
        db.session.commit()
        log_audit('Assign Subject', f'Assigned subject {subject_id} to teacher {teacher_id}')
        flash('Subject assigned successfully', 'success')
        return redirect(url_for('assign_subjects'))
    teachers = Teacher.query.filter_by(is_active=True).all()
    subjects = Subject.query.all()
    assignments = db.session.query(TeacherSubject, Teacher, Subject).join(Teacher, TeacherSubject.teacher_id == Teacher.id).join(Subject, TeacherSubject.subject_id == Subject.id).all()
    return render_template_string(ASSIGN_SUBJECTS, teachers=teachers, subjects=subjects, assignments=assignments)

# -------------------- Timetable --------------------
@app.route('/admin/timetable', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def manage_timetable():
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        teacher_id = request.form.get('teacher_id')
        day = request.form.get('day')
        period = request.form.get('period')
        session_type = request.form.get('session_type')
        room = request.form.get('room')
        batch = request.form.get('batch')
        division = request.form.get('division')
        semester = request.form.get('semester')
        # Check for clashes: room or teacher at same day+period
        clash = Timetable.query.filter_by(day=day, period=period, room=room).first()
        teacher_clash = Timetable.query.filter_by(day=day, period=period, teacher_id=teacher_id).first()
        if clash:
            flash('Room clash detected! Timetable not saved.', 'danger')
            return redirect(url_for('manage_timetable'))
        if teacher_clash:
            flash('Teacher clash detected! Timetable not saved.', 'danger')
            return redirect(url_for('manage_timetable'))
        tt = Timetable(subject_id=subject_id, teacher_id=teacher_id, day=day, period=period, session_type=session_type, room=room, batch=batch, division=division, semester=semester)
        db.session.add(tt)
        db.session.commit()
        log_audit('Create Timetable', f'Created timetable entry for {day} period {period}')
        flash('Timetable entry created successfully', 'success')
        return redirect(url_for('manage_timetable'))
    timetable = db.session.query(Timetable, Subject, Teacher).join(Subject, Timetable.subject_id == Subject.id).join(Teacher, Timetable.teacher_id == Teacher.id).all()
    teachers = Teacher.query.filter_by(is_active=True).all()
    subjects = Subject.query.all()
    return render_template_string(MANAGE_TIMETABLE, timetable=timetable, teachers=teachers, subjects=subjects)

@app.route('/timetable/view')
@login_required
def view_timetable():
    role = session.get('role')
    if role == 'teacher':
        teacher = Teacher.query.filter_by(user_id=session['user_id']).first()
        timetable = db.session.query(Timetable, Subject).join(Subject, Timetable.subject_id == Subject.id).filter(Timetable.teacher_id == teacher.id).all()
        return render_template_string(VIEW_TIMETABLE_TEACHER, timetable=timetable)
    elif role == 'student':
        student = Student.query.filter_by(user_id=session['user_id']).first()
        timetable = db.session.query(Timetable, Subject, Teacher).join(Subject, Timetable.subject_id == Subject.id).join(Teacher, Timetable.teacher_id == Teacher.id).filter(Timetable.batch == student.batch, Timetable.division == student.division).all()
        return render_template_string(VIEW_TIMETABLE_TEACHER, timetable=timetable)
    return 'Access denied'

# -------------------- Attendance --------------------
@app.route('/attendance/mark', methods=['GET', 'POST'])
@login_required
@role_required('teacher')
def mark_attendance():
    teacher = Teacher.query.filter_by(user_id=session['user_id']).first()
    if request.method == 'POST':
        data = request.get_json()
        subject_id = data.get('subject_id')
        date_str = data.get('date')
        try:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except Exception:
            return jsonify({'success': False, 'message': 'Invalid date format'})
        session_type = data.get('session_type')  # FN, AN, Period
        period = data.get('period')
        attendance_data = data.get('attendance') or []
        existing = Attendance.query.filter_by(subject_id=subject_id, teacher_id=teacher.id, date=attendance_date, session_type=session_type, period=period).first()
        if existing and existing.is_locked:
            return jsonify({'success': False, 'message': 'Attendance is locked and cannot be modified'})
        # Delete existing attendance for this session
        Attendance.query.filter_by(subject_id=subject_id, teacher_id=teacher.id, date=attendance_date, session_type=session_type, period=period).delete()
        for item in attendance_data:
            att = Attendance(
                student_id=item['student_id'],
                subject_id=subject_id,
                teacher_id=teacher.id,
                date=attendance_date,
                session_type=session_type,
                period=period,
                status=item['status'],
                remarks=item.get('remarks', '')
            )
            db.session.add(att)
        db.session.commit()
        log_audit('Mark Attendance', f'Marked attendance for subject {subject_id} on {date_str}')
        return jsonify({'success': True, 'message': 'Attendance marked successfully'})
    teacher_subjects = db.session.query(TeacherSubject, Subject).join(Subject, TeacherSubject.subject_id == Subject.id).filter(TeacherSubject.teacher_id == teacher.id).all()
    return render_template_string(MARK_ATTENDANCE, teacher_subjects=teacher_subjects, teacher=teacher, datetime=datetime, default_date=date.today().isoformat())

@app.route('/attendance/students/<int:subject_id>/<batch>/<division>')
@login_required
@role_required('teacher')
def get_students_for_attendance(subject_id, batch, division):
    students = Student.query.filter_by(batch=batch, division=division, is_active=True).order_by(Student.roll_number).all()
    return jsonify([{'id': s.id, 'roll_number': s.roll_number, 'name': s.name} for s in students])

@app.route('/attendance/edit/<int:attendance_id>', methods=['POST'])
@login_required
@role_required('teacher', 'admin')
def edit_attendance(attendance_id):
    att = Attendance.query.get_or_404(attendance_id)
    if att.is_locked:
        return jsonify({'success': False, 'message': 'Attendance is locked'})
    data = request.get_json()
    att.status = data.get('status', att.status)
    att.remarks = data.get('remarks', att.remarks)
    att.edited_at = datetime.utcnow()
    att.edited_by = session['user_id']
    db.session.commit()
    log_audit('Edit Attendance', f'Edited attendance ID {attendance_id}')
    return jsonify({'success': True, 'message': 'Attendance updated'})

@app.route('/attendance/view')
@login_required
def view_attendance():
    role = session.get('role')
    if role == 'student':
        student = Student.query.filter_by(user_id=session['user_id']).first()
        subject_id = request.args.get('subject_id')
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        query = db.session.query(Attendance, Subject, Teacher).join(Subject, Attendance.subject_id == Subject.id).join(Teacher, Attendance.teacher_id == Teacher.id).filter(Attendance.student_id == student.id)
        if subject_id:
            query = query.filter(Attendance.subject_id == subject_id)
        if from_date:
            query = query.filter(Attendance.date >= datetime.strptime(from_date, '%Y-%m-%d').date())
        if to_date:
            query = query.filter(Attendance.date <= datetime.strptime(to_date, '%Y-%m-%d').date())
        attendance = query.order_by(Attendance.date.desc()).limit(100).all()
        subjects = Subject.query.filter_by(program_id=student.program_id, semester=student.semester).all()
        return render_template_string(VIEW_ATTENDANCE_STUDENT, attendance=attendance, subjects=subjects)
    elif role == 'teacher':
        teacher = Teacher.query.filter_by(user_id=session['user_id']).first()
        subject_id = request.args.get('subject_id')
        batch = request.args.get('batch')
        division = request.args.get('division')
        from_date = request.args.get('from_date')
        query = db.session.query(Attendance, Subject, Student).join(Subject, Attendance.subject_id == Subject.id).join(Student, Attendance.student_id == Student.id).filter(Attendance.teacher_id == teacher.id)
        if subject_id:
            query = query.filter(Attendance.subject_id == subject_id)
        if batch:
            query = query.filter(Student.batch == batch)
        if division:
            query = query.filter(Student.division == division)
        if from_date:
            query = query.filter(Attendance.date >= datetime.strptime(from_date, '%Y-%m-%d').date())
        attendance = query.order_by(Attendance.date.desc()).limit(200).all()
        my_subjects = db.session.query(Subject, TeacherSubject).join(TeacherSubject, Subject.id == TeacherSubject.subject_id).filter(TeacherSubject.teacher_id == teacher.id).all()
        return render_template_string(VIEW_ATTENDANCE_TEACHER, attendance=attendance, my_subjects=my_subjects)
    elif role == 'admin':
        subject_id = request.args.get('subject_id')
        batch = request.args.get('batch')
        division = request.args.get('division')
        query = db.session.query(Attendance, Subject, Student, Teacher).join(Subject, Attendance.subject_id == Subject.id).join(Student, Attendance.student_id == Student.id).join(Teacher, Attendance.teacher_id == Teacher.id)
        if subject_id:
            query = query.filter(Attendance.subject_id == subject_id)
        if batch:
            query = query.filter(Student.batch == batch)
        if division:
            query = query.filter(Student.division == division)
        attendance = query.order_by(Attendance.date.desc()).limit(500).all()
        subjects = Subject.query.all()
        return render_template_string(VIEW_ATTENDANCE_TEACHER, attendance=attendance, subjects=subjects)
    return 'Access denied'

# -------------------- Leave Management --------------------
@app.route('/leave/apply', methods=['GET', 'POST'])
@login_required
@role_required('student')
def apply_leave():
    student = Student.query.filter_by(user_id=session['user_id']).first()
    if request.method == 'POST':
        from_date = datetime.strptime(request.form.get('from_date'), '%Y-%m-%d').date()
        to_date = datetime.strptime(request.form.get('to_date'), '%Y-%m-%d').date()
        leave_type = request.form.get('leave_type')
        reason = request.form.get('reason')
        leave = LeaveRequest(student_id=student.id, from_date=from_date, to_date=to_date, leave_type=leave_type, reason=reason)
        db.session.add(leave)
        db.session.commit()
        log_audit('Apply Leave', f'Student {student.name} applied for leave from {from_date} to {to_date}')
        flash('Leave application submitted successfully', 'success')
        return redirect(url_for('apply_leave'))
    leaves = LeaveRequest.query.filter_by(student_id=student.id).order_by(LeaveRequest.created_at.desc()).all()
    return render_template_string(APPLY_LEAVE, leaves=leaves, student=student)

@app.route('/leave/manage')
@login_required
@role_required('teacher', 'admin')
def manage_leaves():
    status_filter = request.args.get('status', 'pending')
    query = db.session.query(LeaveRequest, Student, Program).join(Student, LeaveRequest.student_id == Student.id).join(Program, Student.program_id == Program.id)
    if status_filter != 'all':
        query = query.filter(LeaveRequest.status == status_filter)
    leaves = query.order_by(LeaveRequest.created_at.desc()).all()
    return render_template_string(MANAGE_LEAVES, leaves=leaves, status_filter=status_filter)

@app.route('/leave/approve/<int:leave_id>')
@login_required
@role_required('teacher', 'admin')
def approve_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    leave.status = 'approved'
    leave.approved_by = session['user_id']
    leave.approved_at = datetime.utcnow()
    current_date = leave.from_date
    while current_date <= leave.to_date:
        attendances = Attendance.query.filter_by(student_id=leave.student_id, date=current_date).all()
        for att in attendances:
            att.status = 'OD'
            att.remarks = f'Leave approved: {leave.leave_type}'
        current_date += timedelta(days=1)
    db.session.commit()
    log_audit('Approve Leave', f'Approved leave request {leave_id}')
    flash('Leave approved and attendance updated', 'success')
    return redirect(url_for('manage_leaves'))

@app.route('/leave/reject/<int:leave_id>')
@login_required
@role_required('teacher', 'admin')
def reject_leave(leave_id):
    leave = LeaveRequest.query.get_or_404(leave_id)
    leave.status = 'rejected'
    leave.approved_by = session['user_id']
    leave.approved_at = datetime.utcnow()
    db.session.commit()
    log_audit('Reject Leave', f'Rejected leave request {leave_id}')
    flash('Leave request rejected', 'info')
    return redirect(url_for('manage_leaves'))

# -------------------- Reports --------------------
@app.route('/reports')
@login_required
@role_required('admin', 'teacher')
def reports_page():
    return render_template_string(REPORTS_PAGE)

@app.route('/reports/student-wise')
@login_required
@role_required('admin', 'teacher')
def student_wise_report():
    batch = request.args.get('batch')
    division = request.args.get('division')
    semester = request.args.get('semester')
    query = Student.query.filter_by(is_active=True)
    if batch:
        query = query.filter_by(batch=batch)
    if division:
        query = query.filter_by(division=division)
    if semester:
        query = query.filter_by(semester=semester)
    students = query.all()
    report_data = []
    for student in students:
        percentage = calculate_attendance_percentage(student.id)
        report_data.append({'student': student, 'percentage': percentage, 'status': 'Good' if percentage >= 75 else 'Low'})
    return render_template_string(STUDENT_WISE_REPORT, report_data=report_data)

@app.route('/reports/subject-wise')
@login_required
@role_required('admin', 'teacher')
def subject_wise_report():
    subject_id = request.args.get('subject_id')
    if not subject_id:
        subjects = Subject.query.all()
        return render_template_string(SUBJECT_WISE_REPORT, subjects=subjects, report_data=None)
    subject = Subject.query.get(subject_id)
    students = Student.query.filter_by(program_id=subject.program_id, semester=subject.semester, is_active=True).all()
    report_data = []
    for student in students:
        agg = db.session.query(func.count(Attendance.id).label('total'), func.sum(case([(Attendance.status.in_(['Present','Late','OD']),1)], else_=0)).label('present')).filter(Attendance.student_id == student.id, Attendance.subject_id == subject_id).one()
        total = agg.total or 0
        present = agg.present or 0
        percentage = round((present / total * 100), 2) if total > 0 else 0.0
        report_data.append({'student': student, 'total': total, 'present': present, 'percentage': percentage})
    subjects = Subject.query.all()
    return render_template_string(SUBJECT_WISE_REPORT, subjects=subjects, report_data=report_data, selected_subject=subject)

@app.route('/reports/defaulters')
@login_required
@role_required('admin', 'teacher')
def defaulters_report():
    threshold = int(request.args.get('threshold', 75))
    defaulters = get_defaulter_students(threshold=threshold)
    return render_template_string(DEFAULTERS_REPORT, defaulters=defaulters, threshold=threshold)

@app.route('/reports/export/<report_type>')
@login_required
@role_required('admin', 'teacher')
def export_report(report_type):
    output = io.StringIO()
    writer = csv.writer(output)
    if report_type == 'student-wise':
        writer.writerow(['Roll No', 'Name', 'Program', 'Batch', 'Division', 'Semester', 'Attendance %', 'Status'])
        students = Student.query.filter_by(is_active=True).all()
        for student in students:
            program = Program.query.get(student.program_id)
            percentage = calculate_attendance_percentage(student.id)
            status = 'Good' if percentage >= 75 else 'Low'
            writer.writerow([student.roll_number, student.name, program.name if program else '', student.batch, student.division, student.semester, percentage, status])
    elif report_type == 'defaulters':
        threshold = int(request.args.get('threshold', 75))
        writer.writerow(['Roll No', 'Name', 'Batch', 'Division', 'Attendance %', 'Shortage'])
        defaulters = get_defaulter_students(threshold=threshold)
        for d in defaulters:
            student = d['student']
            percentage = d['percentage']
            shortage = threshold - percentage
            writer.writerow([student.roll_number, student.name, student.batch, student.division, percentage, f'{shortage}%'])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name=f'{report_type}_report.csv')

# -------------------- Settings & Logs --------------------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def system_settings():
    if request.method == 'POST':
        attendance_lock_hours = request.form.get('attendance_lock_hours')
        min_attendance_percentage = request.form.get('min_attendance_percentage')
        setting = SystemSettings.query.filter_by(key='attendance_lock_hours').first()
        if setting:
            setting.value = attendance_lock_hours
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSettings(key='attendance_lock_hours', value=attendance_lock_hours)
            db.session.add(setting)
        setting = SystemSettings.query.filter_by(key='min_attendance_percentage').first()
        if setting:
            setting.value = min_attendance_percentage
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSettings(key='min_attendance_percentage', value=min_attendance_percentage)
            db.session.add(setting)
        db.session.commit()
        log_audit('Update Settings', 'Updated system settings')
        flash('Settings updated successfully', 'success')
        return redirect(url_for('system_settings'))
    settings = SystemSettings.query.all()
    settings_dict = {s.key: s.value for s in settings}
    return render_template_string(SYSTEM_SETTINGS, settings=settings_dict)

@app.route('/audit-logs')
@login_required
@role_required('admin')
def audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template_string(AUDIT_LOGS, logs=logs)

@app.route('/login-history')
@login_required
@role_required('admin')
def login_history():
    history = db.session.query(LoginHistory, User).join(User, LoginHistory.user_id == User.id).order_by(LoginHistory.login_time.desc()).limit(100).all()
    return render_template_string(LOGIN_HISTORY, history=history)

# -------------------- API --------------------
@app.route('/api/attendance/summary/<int:student_id>')
@login_required
def api_attendance_summary(student_id):
    if session['role'] == 'student':
        student = Student.query.filter_by(user_id=session['user_id']).first()
        if student.id != student_id:
            return jsonify({'error': 'Unauthorized'}), 403
    overall = calculate_attendance_percentage(student_id)
    subject_wise = get_student_subject_attendance(student_id)
    return jsonify({'overall_percentage': overall, 'subject_wise': subject_wise})

@app.route('/api/stats/dashboard')
@login_required
@role_required('admin')
def api_dashboard_stats():
    stats = {
        'total_students': Student.query.filter_by(is_active=True).count(),
        'total_teachers': Teacher.query.filter_by(is_active=True).count(),
        'total_programs': Program.query.count(),
        'total_subjects': Subject.query.count(),
        'pending_leaves': LeaveRequest.query.filter_by(status='pending').count(),
        'defaulters_count': len(get_defaulter_students(75))
    }
    return jsonify(stats)

# ==================== INITIALIZE DATABASE ====================
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@college.edu', password=generate_password_hash('admin123'), role='admin', is_active=True)
            db.session.add(admin)
            db.session.commit()
            print("✓ Admin created: admin/admin123")
        if not Program.query.first():
            prog = Program(name='Bachelor of Computer Applications', code='BCA', type='UG', duration=6)
            db.session.add(prog)
            db.session.commit()
            print("✓ Sample program created")

# ==================== RUN ====================
if __name__ == '__main__':
    init_db()
    print("\n" + "="*50)
    print("🎓 College Attendance Management System")
    print("="*50)
    print("Default Login Credentials:")
    print("  Admin: admin / admin123")
    print("\nAccess at: http://127.0.0.1:5001")
    print("="*50 + "\n")
    app.run(debug=True, port=5001)
