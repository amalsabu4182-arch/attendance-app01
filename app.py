# app.py
import sqlite3
import datetime
import calendar
import csv
from io import StringIO, BytesIO
from flask import Flask, render_template, request, jsonify, g, send_file, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pytz

# --- Basic Flask App Setup ---
app = Flask(__name__)

# --- TEMPORARY CODE TO INITIALIZE DATABASE ---
with app.app_context():
    init_db()
# -------------------------------------------

app.config['SECRET_KEY'] = 'your-very-secret-key-change-this'
DATABASE = 'attendance.db'

# --- Timezone Helper ---
def get_ist_today():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.datetime.now(ist).date()

# --- Database Functions ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        
        # Create a default admin user if one doesn't exist
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if cursor.fetchone() is None:
            hashed_password = generate_password_hash('adminpass')
            cursor.execute(
                'INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, ?)',
                ('admin', hashed_password, 'Administrator', 'admin')
            )
            print("Admin user created with username 'admin' and password 'adminpass'.")
        
        # Create a default class if none exist
        cursor.execute("SELECT * FROM classes")
        if cursor.fetchone() is None:
            cursor.execute("INSERT INTO classes (name) VALUES (?)", ('Default Class',))
            print("Created 'Default Class'.")

        db.commit()
        print("Database initialized.")

@app.cli.command('initdb')
def initdb_command():
    init_db()

# --- Auth Decorators & User Helpers ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "Authentication required."}), 401
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if session.get('role') != role:
                return jsonify({"success": False, "message": "Permission denied."}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- API Routes ---
@app.route("/")
def index():
    return render_template('index.html')

@app.route("/api/register/teacher", methods=["POST"])
def register_teacher():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    full_name = data.get('full_name')
    class_id = data.get('class_id')

    if not all([username, password, full_name, class_id]):
        return jsonify({"success": False, "message": "All fields are required."}), 400

    db = get_db()
    try:
        hashed_password = generate_password_hash(password)
        db.execute(
            'INSERT INTO users (username, password, full_name, role, class_id, teacher_status) VALUES (?, ?, ?, ?, ?, ?)',
            (username, hashed_password, full_name, 'teacher', class_id, 'pending')
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username already exists."}), 409
    
    return jsonify({"success": True, "message": "Registration successful. Please wait for admin approval."})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    db = get_db()
    
    user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    
    if user and check_password_hash(user['password'], password):
        if user['role'] == 'teacher' and user['teacher_status'] != 'approved':
            return jsonify({"success": False, "message": "Your account is pending approval."}), 403
        
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['full_name'] = user['full_name']
        session['role'] = user['role']
        session['class_id'] = user['class_id']
        
        return jsonify({
            "success": True, 
            "user": {
                "name": user['full_name'],
                "role": user['role']
            }
        })
    
    return jsonify({"success": False, "message": "Invalid username or password"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully."})

@app.route("/api/session", methods=["GET"])
@login_required
def get_session():
    return jsonify({
        "success": True,
        "user": {
            "name": session['full_name'],
            "role": session['role']
        }
    })

# --- Admin Routes ---
@app.route("/api/admin/pending_teachers", methods=["GET"])
@role_required('admin')
def get_pending_teachers():
    db = get_db()
    teachers = db.execute("""
        SELECT u.id, u.full_name, u.username, c.name as class_name
        FROM users u JOIN classes c ON u.class_id = c.id
        WHERE u.role = 'teacher' AND u.teacher_status = 'pending'
    """).fetchall()
    return jsonify([dict(row) for row in teachers])

@app.route("/api/admin/approve_teacher/<int:user_id>", methods=["POST"])
@role_required('admin')
def approve_teacher(user_id):
    db = get_db()
    db.execute("UPDATE users SET teacher_status = 'approved' WHERE id = ? AND role = 'teacher'", (user_id,))
    db.commit()
    return jsonify({"success": True, "message": "Teacher approved."})

@app.route("/api/admin/classes", methods=["GET", "POST"])
def manage_classes():
    db = get_db()
    if request.method == "POST":
        # For adding a new class, we must ensure the user is an admin
        if session.get('role') != 'admin':
            return jsonify({"success": False, "message": "Permission denied."}), 403
            
        name = request.json.get('name')
        if not name:
            return jsonify({"success": False, "message": "Class name is required."}), 400
        try:
            db.execute("INSERT INTO classes (name) VALUES (?)", (name,))
            db.commit()
            return jsonify({"success": True, "message": "Class added."})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "Class name already exists."}), 409

    # For viewing classes (GET request), no login is required.
    classes = db.execute("SELECT * FROM classes").fetchall()
    return jsonify([dict(c) for c in classes])

# --- Teacher Routes ---
@app.route("/api/teacher/students", methods=["GET", "POST"])
@role_required('teacher')
def manage_teacher_students():
    db = get_db()
    teacher_class_id = session.get('class_id')
    
    if request.method == "POST":
        name = request.json.get('name')
        username = request.json.get('username')
        password = request.json.get('password', 'studentpass') # Default password

        if not all([name, username]):
            return jsonify({"success": False, "message": "Name and username required."}), 400
        
        try:
            hashed_password = generate_password_hash(password)
            db.execute(
                'INSERT INTO users (username, password, full_name, role, class_id) VALUES (?, ?, ?, ?, ?)',
                (username, hashed_password, name, 'student', teacher_class_id)
            )
            db.commit()
            return jsonify({"success": True, "message": "Student added."})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "Username already exists."}), 409

    students = db.execute("SELECT id, full_name FROM users WHERE role = 'student' AND class_id = ?", (teacher_class_id,)).fetchall()
    return jsonify({"students": [dict(s) for s in students]})

@app.route("/api/teacher/students/<int:student_id>", methods=["PUT", "DELETE"])
@role_required('teacher')
def update_teacher_student(student_id):
    db = get_db()
    teacher_class_id = session.get('class_id')
    
    # Verify student is in teacher's class
    student = db.execute("SELECT id FROM users WHERE id = ? AND class_id = ?", (student_id, teacher_class_id)).fetchone()
    if not student:
        return jsonify({"success": False, "message": "Student not found in your class."}), 404

    if request.method == "PUT":
        name = request.json.get('name')
        if not name:
            return jsonify({"success": False, "message": "Name is required."}), 400
        db.execute("UPDATE users SET full_name = ? WHERE id = ?", (name, student_id))
        db.commit()
        return jsonify({"success": True, "message": "Student updated."})
    
    if request.method == "DELETE":
        db.execute("DELETE FROM users WHERE id = ?", (student_id,))
        db.commit()
        return jsonify({"success": True, "message": "Student and their records deleted."})

@app.route("/api/teacher/mark", methods=["POST"])
@role_required('teacher')
def mark_attendance():
    data = request.json
    student_id = data.get('student_id')
    status = data.get('status')
    remarks = data.get('remarks', '')
    today = get_ist_today().isoformat()
    db = get_db()

    # Check if student belongs to teacher's class
    teacher_class_id = session.get('class_id')
    student = db.execute("SELECT id FROM users WHERE id = ? AND role = 'student' AND class_id = ?", (student_id, teacher_class_id)).fetchone()
    if not student:
        return jsonify({"success": False, "message": "This student is not in your class."}), 403

    existing = db.execute('SELECT id FROM attendance WHERE student_user_id = ? AND date = ?', (student_id, today)).fetchone()
    if existing:
        db.execute('UPDATE attendance SET status = ?, remarks = ? WHERE id = ?', (status, remarks, existing['id']))
    else:
        db.execute('INSERT INTO attendance (student_user_id, date, status, remarks) VALUES (?, ?, ?, ?)', (student_id, today, status, remarks))
    db.commit()
    return jsonify({"success": True, "message": "Attendance marked."})

@app.route("/api/teacher/mark_all", methods=["POST"])
@role_required('teacher')
def mark_all():
    status = request.json.get('status')
    today = get_ist_today().isoformat()
    teacher_class_id = session.get('class_id')
    db = get_db()

    students = db.execute("SELECT id FROM users WHERE role = 'student' AND class_id = ?", (teacher_class_id,)).fetchall()
    student_ids = [row['id'] for row in students]
    
    for student_id in student_ids:
        existing = db.execute('SELECT id FROM attendance WHERE student_user_id = ? AND date = ?', (student_id, today)).fetchone()
        if existing:
            db.execute('UPDATE attendance SET status = ? WHERE id = ?', (status, existing['id']))
        else:
            db.execute('INSERT INTO attendance (student_user_id, date, status) VALUES (?, ?, ?)', (student_id, today, status))
    db.commit()
    return jsonify({"success": True, "message": f"All students marked as {status}."})

@app.route("/api/teacher/monthly_report")
@role_required('teacher')
def get_monthly_report():
    month_str = request.args.get('month')
    year, month = map(int, month_str.split('-'))
    num_days = calendar.monthrange(year, month)[1]
    days_in_month = [f"{month_str}-{day:02d}" for day in range(1, num_days + 1)]
    teacher_class_id = session.get('class_id')
    
    db = get_db()
    students_cursor = db.execute("SELECT id, full_name FROM users WHERE role = 'student' AND class_id = ? ORDER BY full_name ASC", (teacher_class_id,))
    students = [dict(row) for row in students_cursor.fetchall()]

    holidays_cursor = db.execute("SELECT date FROM holidays WHERE date LIKE ?", (f"{month_str}-%",))
    holidays = [row['date'] for row in holidays_cursor.fetchall()]

    report = {s['id']: {} for s in students}
    summary = {s['id']: {'present': 0.0, 'absent': 0} for s in students}

    for student in students:
        student_id = student['id']
        records_cursor = db.execute("SELECT date, status, remarks FROM attendance WHERE student_user_id = ? AND date LIKE ?", (student_id, f"{month_str}-%"))
        student_records = {row['date']: {'status': row['status'], 'remarks': row['remarks']} for row in records_cursor.fetchall()}
        
        for day_str in days_in_month:
            status = student_records.get(day_str, {}).get('status')
            if day_str in holidays: status = 'Holiday'
            
            report[student_id][day_str] = {'status': status, 'remarks': student_records.get(day_str, {}).get('remarks')}
            
            if status == 'Full Day': summary[student_id]['present'] += 1.0
            elif status == 'Half Day': summary[student_id]['present'] += 0.5
            elif status == 'Absent': summary[student_id]['absent'] += 1
            
    return jsonify({
        "students": students, "report": report, "summary": summary,
        "days_in_month": [d.split('-')[2] for d in days_in_month],
        "holidays": [d.split('-')[2] for d in holidays]
    })


# --- Holiday and Export Routes (Can be accessed by Teacher/Admin) ---
@app.route("/api/holidays", methods=["GET", "POST"])
@login_required
def manage_holidays():
    if session['role'] not in ['admin', 'teacher']:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    db = get_db()
    if request.method == "POST":
        date = request.json.get('date')
        if not date: return jsonify({"success": False, "message": "Date is required."}), 400
        try:
            db.execute('INSERT INTO holidays (date) VALUES (?)', (date,))
            db.commit()
            return jsonify({"success": True, "message": "Holiday added."})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "Holiday already exists."}), 409
    
    holidays_cursor = db.execute('SELECT date FROM holidays ORDER BY date ASC')
    return jsonify({"holidays": [row['date'] for row in holidays_cursor.fetchall()]})

@app.route("/api/holidays/<string:date_str>", methods=["DELETE"])
@login_required
def delete_holiday(date_str):
    if session['role'] not in ['admin', 'teacher']:
        return jsonify({"success": False, "message": "Permission denied."}), 403
    db = get_db()
    db.execute('DELETE FROM holidays WHERE date = ?', (date_str,))
    db.commit()
    return jsonify({"success": True, "message": "Holiday deleted."})

@app.route("/api/teacher/monthly_report/export")
@role_required('teacher')
def export_monthly_report():
    month_str = request.args.get('month')
    teacher_class_id = session.get('class_id')
    year, month = map(int, month_str.split('-'))
    num_days = calendar.monthrange(year, month)[1]
    days_in_month = [f"{month_str}-{day:02d}" for day in range(1, num_days + 1)]
    
    db = get_db()
    students = db.execute("SELECT id, full_name FROM users WHERE role = 'student' AND class_id = ? ORDER BY full_name ASC", (teacher_class_id,)).fetchall()
    holidays = [r['date'] for r in db.execute("SELECT date FROM holidays WHERE date LIKE ?", (f"{month_str}-%",)).fetchall()]
    
    report_data = []
    for student in students:
        records = {r['date']: r['status'] for r in db.execute("SELECT date, status FROM attendance WHERE student_user_id = ? AND date LIKE ?", (student['id'], f"{month_str}-%")).fetchall()}
        row_data = [student['full_name']]
        present, absent = 0.0, 0
        for day in days_in_month:
            status = records.get(day)
            if day in holidays: status = 'Holiday'
            
            if status == 'Full Day': row_data.append('F'); present += 1.0
            elif status == 'Half Day': row_data.append('H'); present += 0.5
            elif status == 'Absent': row_data.append('A'); absent += 1
            elif status == 'Holiday': row_data.append('HLY')
            else: row_data.append('')
        row_data.extend([f"{present:.1f}", absent])
        report_data.append(row_data)

    headers = ['Student Name'] + [d.split('-')[2] for d in days_in_month] + ['Present (Days)', 'Absent (Days)']
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(report_data)
    
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f'report_{month_str}.csv')

# --- Student Routes ---
@app.route("/api/student/data", methods=["GET"])
@role_required('student')
def get_student_data():
    student_id = session.get('user_id')
    db = get_db()
    records_cursor = db.execute('SELECT date, status, remarks FROM attendance WHERE student_user_id = ? ORDER BY date DESC', (student_id,))
    records = [dict(row) for row in records_cursor.fetchall()]

    present_days, absent_days, total_days = 0.0, 0, 0
    for r in records:
        if r['status'] in ['Full Day', 'Half Day', 'Absent']:
            total_days += 1
            if r['status'] == 'Full Day': present_days += 1.0
            elif r['status'] == 'Half Day': present_days += 0.5
            elif r['status'] == 'Absent': absent_days += 1

    percentage = (present_days / total_days * 100) if total_days > 0 else 0
    
    return jsonify({
        "records": records,
        "present_days": f"{present_days:.1f}",
        "absent_days": absent_days,
        "percentage": round(percentage)
    })

if __name__ == '__main__':
    app.run(debug=True)
