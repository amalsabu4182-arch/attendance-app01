# app.py
import sqlite3
import datetime
import calendar
import csv
from io import StringIO, BytesIO
from flask import Flask, render_template, request, jsonify, g, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os

# --- Basic Flask App Setup ---
app = Flask(__name__)


# --- Database Functions (Defined Early) ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        # Vercel's ephemeral filesystem requires the path to be in /tmp
        db_path = os.path.join('/tmp', 'attendance.db')
        db = g._database = sqlite3.connect(db_path)
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
        schema = """
            DROP TABLE IF EXISTS attendance;
            DROP TABLE IF EXISTS students;
            DROP TABLE IF EXISTS holidays;
            DROP TABLE IF EXISTS teachers;
            DROP TABLE IF EXISTS classes;

            CREATE TABLE classes (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE teachers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              email TEXT NOT NULL UNIQUE,
              password TEXT NOT NULL,
              class_id INTEGER,
              approved INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY (class_id) REFERENCES classes (id)
            );

            CREATE TABLE students (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              password TEXT,
              class_id INTEGER NOT NULL,
              UNIQUE(name, class_id),
              FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE
            );

            CREATE TABLE attendance (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              student_id INTEGER NOT NULL,
              date TEXT NOT NULL,
              status TEXT NOT NULL,
              remarks TEXT,
              UNIQUE(student_id, date),
              FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            );

            CREATE TABLE holidays (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              date TEXT NOT NULL UNIQUE
            );
        """
        db.cursor().executescript(schema)
        db.commit()

        cursor = db.cursor()
        admin_pass_hash = generate_password_hash('adminpass')
        try:
            cursor.execute('INSERT INTO teachers (name, email, password, approved) VALUES (?, ?, ?, ?)',
                           ('admin', 'admin@example.com', admin_pass_hash, 1))
            db.commit()
            print("Admin user created.")
        except sqlite3.IntegrityError:
            print("Admin user already exists.")

        print("Database has been initialized on Vercel.")


# --- TEMPORARY CODE TO INITIALIZE DATABASE ---
with app.app_context():
    init_db()


# -------------------------------------------

@app.cli.command('initdb')
def initdb_command():
    init_db()
    print('Initialized the database.')


# --- Main App Route ---
@app.route("/")
def index():
    return render_template('index.html')


# --- API Routes & Logic ---

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    db = get_db()

    teacher = db.execute('SELECT * FROM teachers WHERE email = ?', (email,)).fetchone()
    if teacher:
        if teacher['approved'] == 0:
            return jsonify({"success": False, "message": "Your account is pending admin approval."}), 403
        if check_password_hash(teacher['password'], password):
            role = 'admin' if teacher['name'] == 'admin' else 'teacher'
            return jsonify({
                "success": True, "role": role, "name": teacher['name'], "class_id": teacher['class_id']
            })

    student = db.execute(
        'SELECT s.*, c.name as class_name FROM students s JOIN classes c ON s.class_id = c.id WHERE s.name = ?',
        (email,)).fetchone()
    if student:
        student_pass = student['password'] if student['password'] else 'studentpass'
        if password == student_pass:
            return jsonify({
                "success": True, "role": "student", "name": student['name'], "class_name": student['class_name']
            })

    return jsonify({"success": False, "message": "Invalid credentials or account not found."}), 401


@app.route("/api/register/teacher", methods=["POST"])
def register_teacher():
    data = request.json
    name, email, password, class_id = data.get('name'), data.get('email'), data.get('password'), data.get('class_id')
    if not all([name, email, password, class_id]):
        return jsonify({"success": False, "message": "All fields are required."}), 400

    password_hash = generate_password_hash(password)
    db = get_db()
    try:
        db.execute('INSERT INTO teachers (name, email, password, class_id) VALUES (?, ?, ?, ?)',
                   (name, email, password_hash, class_id))
        db.commit()
        return jsonify({"success": True, "message": "Registration successful! Please wait for admin approval."})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "An account with this email already exists."}), 409


@app.route("/api/admin/pending_teachers", methods=["GET"])
def get_pending_teachers():
    db = get_db()
    cursor = db.execute(
        'SELECT t.id, t.name, t.email, c.name as class_name FROM teachers t JOIN classes c ON t.class_id = c.id WHERE t.approved = 0')
    pending = [dict(row) for row in cursor.fetchall()]
    return jsonify({"pending_teachers": pending})


@app.route("/api/admin/approve_teacher/<int:teacher_id>", methods=["POST"])
def approve_teacher(teacher_id):
    db = get_db()
    db.execute('UPDATE teachers SET approved = 1 WHERE id = ?', (teacher_id,))
    db.commit()
    return jsonify({"success": True, "message": "Teacher approved."})


@app.route("/api/admin/classes", methods=["GET", "POST"])
def manage_classes():
    db = get_db()
    if request.method == "POST":
        data = request.json
        name = data.get('name')
        if not name:
            return jsonify({"success": False, "message": "Class name is required."}), 400
        try:
            db.execute('INSERT INTO classes (name) VALUES (?)', (name,))
            db.commit()
            return jsonify({"success": True, "message": f"Class '{name}' added."})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": "Class with this name already exists."}), 409
    cursor = db.execute('SELECT * FROM classes ORDER BY name ASC')
    classes = [dict(row) for row in cursor.fetchall()]
    return jsonify({"classes": classes})


@app.route("/api/teacher/students", methods=["GET"])
def get_students():
    class_id = request.args.get('class_id')
    db = get_db()
    cursor = db.execute('SELECT * FROM students WHERE class_id = ? ORDER BY name ASC', (class_id,))
    students = [dict(row) for row in cursor.fetchall()]
    return jsonify({"students": students})


@app.route("/api/teacher/students", methods=["POST"])
def add_student():
    data = request.json
    name, class_id, password = data.get('name'), data.get('class_id'), data.get('password')
    if not name or not class_id:
        return jsonify({"success": False, "message": "Name and class are required."}), 400
    db = get_db()
    try:
        db.execute('INSERT INTO students (name, class_id, password) VALUES (?, ?, ?)', (name, class_id, password))
        db.commit()
        return jsonify({"success": True, "message": f"Student '{name}' added."})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": f"Student '{name}' already exists in this class."}), 409


@app.route("/api/teacher/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):
    db = get_db()
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('DELETE FROM students WHERE id = ?', (student_id,))
    db.commit()
    return jsonify({"success": True, "message": "Student deleted."})


@app.route("/api/teacher/mark", methods=["POST"])
def mark_attendance():
    data = request.json
    student_id, status, remarks = data.get('student_id'), data.get('status'), data.get('remarks', '')
    date = datetime.date.today().isoformat()
    db = get_db()
    existing = db.execute('SELECT id FROM attendance WHERE student_id = ? AND date = ?', (student_id, date)).fetchone()
    if existing:
        db.execute('UPDATE attendance SET status = ?, remarks = ? WHERE id = ?', (status, remarks, existing['id']))
    else:
        db.execute('INSERT INTO attendance (student_id, date, status, remarks) VALUES (?, ?, ?, ?)',
                   (student_id, date, status, remarks))
    db.commit()
    return jsonify({"success": True, "message": "Attendance marked."})


@app.route("/api/teacher/mark_all", methods=["POST"])
def mark_all():
    data = request.json
    status, class_id = data.get('status'), data.get('class_id')
    date = datetime.date.today().isoformat()
    db = get_db()
    cursor = db.execute('SELECT id FROM students WHERE class_id = ?', (class_id,))
    student_ids = [row['id'] for row in cursor.fetchall()]
    for student_id in student_ids:
        existing = db.execute('SELECT id FROM attendance WHERE student_id = ? AND date = ?',
                              (student_id, date)).fetchone()
        if existing:
            db.execute('UPDATE attendance SET status = ?, remarks = ? WHERE id = ?', (status, '', existing['id']))
        else:
            db.execute('INSERT INTO attendance (student_id, date, status) VALUES (?, ?, ?)', (student_id, date, status))
    db.commit()
    return jsonify({"success": True, "message": f"All students marked as {status}."})


@app.route("/api/teacher/monthly_report")
def get_monthly_report():
    month_str, class_id = request.args.get('month'), request.args.get('class_id')
    if not month_str or not class_id:
        return jsonify({"error": "Month and class_id parameters are required."}), 400
    try:
        year, month = map(int, month_str.split('-'))
        days_in_month = [f"{month_str}-{day:02d}" for day in range(1, calendar.monthrange(year, month)[1] + 1)]
    except ValueError:
        return jsonify({"error": "Invalid month format. Use YYYY-MM."}), 400
    db = get_db()
    cursor = db.execute('SELECT id, name FROM students WHERE class_id = ? ORDER BY name ASC', (class_id,))
    students = [dict(row) for row in cursor.fetchall()]
    cursor = db.execute("SELECT date FROM holidays WHERE date LIKE ?", (f"{month_str}-%",))
    holidays = [row['date'] for row in cursor.fetchall()]
    report, summary = {}, {}
    for student in students:
        sid = student['id']
        summary[sid] = {'present': 0.0, 'absent': 0}
        report[sid] = {}
        cursor = db.execute("SELECT date, status, remarks FROM attendance WHERE student_id = ? AND date LIKE ?",
                            (sid, f"{month_str}-%"))
        records = {row['date']: {'status': row['status'], 'remarks': row['remarks']} for row in cursor.fetchall()}
        for day in days_in_month:
            status = records.get(day, {}).get('status')
            remarks = records.get(day, {}).get('remarks')
            if day in holidays: status = 'Holiday'
            report[sid][day] = {'status': status, 'remarks': remarks}
            if status == 'Full Day':
                summary[sid]['present'] += 1.0
            elif status == 'Half Day':
                summary[sid]['present'] += 0.5
            elif status == 'Absent':
                summary[sid]['absent'] += 1
    return jsonify({
        "students": students, "report": report, "summary": summary,
        "days_in_month": [d.split('-')[2] for d in days_in_month],
        "holidays": [d.split('-')[2] for d in holidays]
    })


@app.route("/api/holidays", methods=["GET", "POST"])
def manage_holidays():
    db = get_db()
    if request.method == "POST":
        data = request.json
        date = data.get('date')
        if not date: return jsonify({"success": False, "message": "Date is required."}), 400
        try:
            db.execute('INSERT INTO holidays (date) VALUES (?)', (date,))
            db.commit()
            return jsonify({"success": True, "message": f"Holiday on '{date}' added."})
        except sqlite3.IntegrityError:
            return jsonify({"success": False, "message": f"Holiday on '{date}' already exists."}), 409
    cursor = db.execute('SELECT date FROM holidays ORDER BY date ASC')
    holidays = [row['date'] for row in cursor.fetchall()]
    return jsonify({"holidays": holidays})


@app.route("/api/holidays/<string:date_str>", methods=["DELETE"])
def delete_holiday(date_str):
    db = get_db()
    result = db.execute('DELETE FROM holidays WHERE date = ?', (date_str,))
    db.commit()
    if result.rowcount == 0:
        return jsonify({"success": False, "message": "Holiday not found."}), 404
    return jsonify({"success": True, "message": "Holiday deleted."})


@app.route("/api/student/data", methods=["GET"])
def get_student_data():
    student_name = request.args.get('name')
    db = get_db()
    student = db.execute('SELECT id FROM students WHERE name = ?', (student_name,)).fetchone()
    if not student: return jsonify({"error": "Student not found"}), 404
    sid = student['id']
    cursor = db.execute('SELECT date, status, remarks FROM attendance WHERE student_id = ? ORDER BY date DESC', (sid,))
    records = [dict(row) for row in cursor.fetchall()]
    present, absent, total = 0.0, 0, 0
    for r in records:
        if r['status'] in ['Full Day', 'Half Day', 'Absent']:
            total += 1
            if r['status'] == 'Full Day':
                present += 1.0
            elif r['status'] == 'Half Day':
                present += 0.5
            elif r['status'] == 'Absent':
                absent += 1
    percentage = (present / total * 100) if total > 0 else 0
    return jsonify({
        "records": records, "present_days": f"{present:.1f}", "absent_days": absent, "percentage": round(percentage)
    })


@app.route("/api/teacher/monthly_report/export", methods=["GET"])
def export_monthly_report():
    month_str, class_id = request.args.get('month'), request.args.get('class_id')
    if not month_str or not class_id: return "Month and class_id are required.", 400
    try:
        year, month = map(int, month_str.split('-'))
        days_in_month = [f"{month_str}-{day:02d}" for day in range(1, calendar.monthrange(year, month)[1] + 1)]
    except ValueError:
        return "Invalid month format. Use YYYY-MM.", 400
    db = get_db()
    cursor = db.execute('SELECT id, name FROM students WHERE class_id = ? ORDER BY name ASC', (class_id,))
    students = [dict(row) for row in cursor.fetchall()]
    cursor = db.execute("SELECT date FROM holidays WHERE date LIKE ?", (f"{month_str}-%",))
    holidays = [row['date'] for row in cursor.fetchall()]
    report_data = []
    for student in students:
        sid = student['id']
        cursor = db.execute("SELECT date, status FROM attendance WHERE student_id = ? AND date LIKE ?",
                            (sid, f"{month_str}-%"))
        records = {row['date']: row['status'] for row in cursor.fetchall()}
        row_data = [student['name']]
        present, absent = 0.0, 0
        for day in days_in_month:
            status = records.get(day)
            if day in holidays: status = 'Holiday'
            cell = ''
            if status == 'Full Day':
                cell, present = 'F', present + 1.0
            elif status == 'Half Day':
                cell, present = 'H', present + 0.5
            elif status == 'Absent':
                cell, absent = 'A', absent + 1
            elif status == 'Holiday':
                cell = 'HLY'
            row_data.append(cell)
        row_data.extend([f"{present:.1f}", absent])
        report_data.append(row_data)
    headers = ['Student Name'] + [d.split('-')[2] for d in days_in_month] + ['Present (Days)', 'Absent (Days)']
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(report_data)
    output_bytes = BytesIO(output.getvalue().encode('utf-8'))
    output_bytes.seek(0)
    return send_file(
        output_bytes, mimetype='text/csv', as_attachment=True,
        download_name=f'attendance_report_{month_str}.csv'
    )
