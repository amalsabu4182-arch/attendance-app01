// --- App State & UI Elements ---
const views = {
    login: document.getElementById('login-view'),
    signup: document.getElementById('signup-view'),
    admin: document.getElementById('admin-view'),
    teacher: document.getElementById('teacher-view'),
    student: document.getElementById('student-view'),
};

// --- API Helper ---
async function apiCall(endpoint, method = 'GET', body = null) {
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) options.body = JSON.stringify(body);
    const response = await fetch(endpoint, options);
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.message || `HTTP error! status: ${response.status}`);
    }
    return data;
}

// --- View Management ---
function switchView(viewName) {
    Object.values(views).forEach(view => view.classList.remove('active-view'));
    if (views[viewName]) {
        views[viewName].classList.add('active-view');
    }
}

function updateUserInfo(user) {
    const userInfo = document.getElementById('user-info');
    const logoutButton = document.getElementById('logout-button');
    if (user) {
        userInfo.textContent = `${user.role.charAt(0).toUpperCase() + user.role.slice(1)}: ${user.name}`;
        userInfo.classList.remove('hidden');
        logoutButton.classList.remove('hidden');
    } else {
        userInfo.classList.add('hidden');
        logoutButton.classList.add('hidden');
    }
}

// --- Auth Functions ---
async function handleLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value.trim();
    const errorEl = document.getElementById('login-error');
    errorEl.textContent = '';
    try {
        const data = await apiCall('/api/login', 'POST', { username, password });
        showDashboard(data.user);
    } catch (error) {
        errorEl.textContent = error.message;
    }
}

async function handleSignup() {
    const full_name = document.getElementById('signup-fullname').value.trim();
    const username = document.getElementById('signup-username').value.trim();
    const password = document.getElementById('signup-password').value.trim();
    const class_id = document.getElementById('signup-class-select').value;
    const messageEl = document.getElementById('signup-message');
    messageEl.textContent = '';
    try {
        const data = await apiCall('/api/register/teacher', 'POST', { full_name, username, password, class_id });
        messageEl.textContent = data.message;
        messageEl.className = 'text-green-500 text-center mt-4';
    } catch (error) {
        messageEl.textContent = error.message;
        messageEl.className = 'text-red-500 text-center mt-4';
    }
}

async function handleLogout() {
    await apiCall('/api/logout', 'POST');
    updateUserInfo(null);
    switchView('login');
}

// --- Dashboard Rendering ---
function showDashboard(user) {
    updateUserInfo(user);
    switch (user.role) {
        case 'admin':
            switchView('admin');
            loadAdminDashboard();
            break;
        case 'teacher':
            switchView('teacher');
            loadTeacherDashboard();
            break;
        case 'student':
            switchView('student');
            loadStudentDashboard();
            break;
        default:
            switchView('login');
    }
}

// --- Admin Dashboard ---
async function loadAdminDashboard() {
    await fetchPendingTeachers();
    await fetchClasses();
    switchAdminSection('admin-approve-section');
}

async function fetchPendingTeachers() {
    const listEl = document.getElementById('pending-teachers-list');
    try {
        const teachers = await apiCall('/api/admin/pending_teachers');
        listEl.innerHTML = '';
        if (teachers.length === 0) {
            listEl.innerHTML = '<p class="text-slate-500">No pending approvals.</p>';
            return;
        }
        teachers.forEach(t => {
            const div = document.createElement('div');
            div.className = 'flex justify-between items-center bg-slate-50 p-3 rounded-lg';
            div.innerHTML = `
                <div>
                    <p class="font-semibold">${t.full_name} (@${t.username})</p>
                    <p class="text-sm text-slate-600">Class: ${t.class_name}</p>
                </div>
                <button onclick="approveTeacher(${t.id})" class="bg-green-500 text-white py-1 px-3 rounded-lg hover:bg-green-600">Approve</button>
            `;
            listEl.appendChild(div);
        });
    } catch (error) {
        listEl.innerHTML = `<p class="text-red-500">Error: ${error.message}</p>`;
    }
}

async function approveTeacher(id) {
    if (!confirm('Are you sure you want to approve this teacher?')) return;
    try {
        await apiCall(`/api/admin/approve_teacher/${id}`, 'POST');
        await fetchPendingTeachers();
    } catch (error) {
        alert('Failed to approve teacher: ' + error.message);
    }
}

async function fetchClasses() {
    const classListEl = document.getElementById('class-list');
    try {
        const classes = await apiCall('/api/admin/classes');
        classListEl.innerHTML = '';
        classes.forEach(c => {
            const div = document.createElement('div');
            div.className = 'p-3 bg-slate-100 rounded';
            div.textContent = c.name;
            classListEl.appendChild(div);
        });
    } catch (error) {
        classListEl.innerHTML = `<p class="text-red-500">Could not load classes: ${error.message}</p>`;
    }
}

async function addClass() {
    const name = document.getElementById('new-class-name').value.trim();
    if (!name) return alert('Please enter a class name.');
    try {
        await apiCall('/api/admin/classes', 'POST', { name });
        document.getElementById('new-class-name').value = '';
        await fetchClasses();
    } catch (error) {
        alert('Error adding class: ' + error.message);
    }
}

function switchAdminSection(sectionId) {
    document.querySelectorAll('.admin-section').forEach(s => s.classList.add('hidden'));
    document.getElementById(sectionId).classList.remove('hidden');
    document.querySelectorAll('.admin-nav-button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.section === sectionId);
    });
}

// --- Teacher Dashboard ---
async function loadTeacherDashboard() {
    document.getElementById('month-picker').value = new Date().toISOString().substring(0, 7);
    await fetchTeacherStudents();
    await getMonthlyReport();
    switchTeacherSection('mark-attendance-section');
}

async function fetchTeacherStudents(management = false) {
    try {
        const data = await apiCall('/api/teacher/students');
        const students = data.students;
        // For attendance marking
        const studentSelect = document.getElementById('student-select');
        studentSelect.innerHTML = '<option value="">Select a student...</option>';
        students.forEach(s => studentSelect.add(new Option(s.full_name, s.id)));
        
        // For management list
        const tableBody = document.getElementById('student-list-table');
        tableBody.innerHTML = '';
        students.forEach(s => {
            tableBody.innerHTML += `
                <tr id="student-row-${s.id}">
                    <td class="p-3">${s.full_name}</td>
                    <td class="p-3 space-x-2">
                        <button onclick="editStudent(${s.id}, '${s.full_name}')" class="bg-blue-500 hover:bg-blue-600 text-white py-1 px-2 rounded-lg text-sm">Edit</button>
                        <button onclick="deleteStudent(${s.id})" class="bg-red-500 hover:bg-red-600 text-white py-1 px-2 rounded-lg text-sm">Delete</button>
                    </td>
                </tr>`;
        });
    } catch (error) {
        alert('Could not load students: ' + error.message);
    }
}

async function addStudent() {
    const name = document.getElementById('new-student-name').value.trim();
    const username = document.getElementById('new-student-username').value.trim();
    const password = document.getElementById('new-student-password').value.trim() || 'studentpass';
    if (!name || !username) return alert('Student name and username are required.');

    try {
        await apiCall('/api/teacher/students', 'POST', { name, username, password });
        document.getElementById('new-student-name').value = '';
        document.getElementById('new-student-username').value = '';
        document.getElementById('new-student-password').value = '';
        await fetchTeacherStudents();
    } catch (error) {
        alert('Failed to add student: ' + error.message);
    }
}

async function editStudent(id, currentName) {
    const newName = prompt(`Enter new name for ${currentName}:`, currentName);
    if (newName && newName.trim() !== '') {
        try {
            await apiCall(`/api/teacher/students/${id}`, 'PUT', { name: newName.trim() });
            await fetchTeacherStudents();
        } catch (error) {
            alert('Failed to edit student: ' + error.message);
        }
    }
}

async function deleteStudent(id) {
    if (confirm("Are you sure? This will delete the student and all their attendance records.")) {
        try {
            await apiCall(`/api/teacher/students/${id}`, 'DELETE');
            await fetchTeacherStudents();
        } catch (error) {
            alert('Failed to delete student: ' + error.message);
        }
    }
}


async function markAttendance(status) {
    const student_id = document.getElementById('student-select').value;
    const remarks = document.getElementById('remarks-input').value.trim();
    if (!student_id) return alert("Please select a student.");
    try {
        await apiCall('/api/teacher/mark', 'POST', { student_id, status, remarks });
        alert(`Marked as ${status}.`);
        document.getElementById('student-select').value = "";
        document.getElementById('remarks-input').value = "";
        await getMonthlyReport();
    } catch (error) {
        alert('Failed to mark attendance: ' + error.message);
    }
}

async function markAll(status) {
    if (!confirm(`Are you sure you want to mark all students as ${status}?`)) return;
    try {
        await apiCall('/api/teacher/mark_all', 'POST', { status });
        alert(`All students marked as ${status}.`);
        await getMonthlyReport();
    } catch (error) {
        alert('Failed to mark all: ' + error.message);
    }
}

async function getMonthlyReport() {
    const monthValue = document.getElementById('month-picker').value;
    if (!monthValue) return;
    const container = document.getElementById('monthly-report-container');
    container.innerHTML = `<p class="text-center">Loading report...</p>`;
    try {
        const data = await apiCall(`/api/teacher/monthly_report?month=${monthValue}`);
        renderMonthlyReportTable(data);
    } catch (error) {
        container.innerHTML = `<p class="text-center text-red-500">Could not load report: ${error.message}</p>`;
    }
}

function renderMonthlyReportTable(data) {
    const { students, report, summary, days_in_month, holidays } = data;
    let tableHTML = `<table class="w-full text-sm border-collapse report-table"><thead><tr><th class="sticky-col font-semibold p-2">Student Name</th>`;
    days_in_month.forEach(day => { 
        tableHTML += `<th class="${holidays.includes(day) ? 'bg-orange-200' : ''}">${day}</th>`; 
    });
    tableHTML += `<th class="bg-green-100">Present</th><th class="bg-orange-100">Absent</th></tr></thead><tbody>`;
    
    students.forEach(student => {
        tableHTML += `<tr><td class="sticky-col font-semibold text-left p-2">${student.full_name}</td>`;
        const studentReport = report[student.id];
        const month = document.getElementById('month-picker').value;
        days_in_month.forEach(day => {
            const dateStr = `${month}-${day.padStart(2, '0')}`;
            const dailyData = studentReport[dateStr];
            let cellContent = '&nbsp;', cellClass = '', title = dailyData?.remarks || '';
            if (dailyData?.status === 'Full Day') { cellContent = 'F'; cellClass = 'bg-green-100'; }
            else if (dailyData?.status === 'Half Day') { cellContent = 'H'; cellClass = 'bg-yellow-100'; }
            else if (dailyData?.status === 'Absent') { cellContent = 'A'; cellClass = 'bg-red-100'; }
            else if (dailyData?.status === 'Holiday') { cellContent = 'HLY'; cellClass = 'bg-gray-200'; }
            tableHTML += `<td class="${cellClass}" title="${title}">${cellContent}</td>`;
        });
        const studentSummary = summary[student.id];
        tableHTML += `<td class="font-bold bg-green-50">${studentSummary.present.toFixed(1)}</td>`;
        tableHTML += `<td class="font-bold bg-orange-50">${studentSummary.absent}</td></tr>`;
    });
    tableHTML += `</tbody></table>`;
    document.getElementById('monthly-report-container').innerHTML = tableHTML;
}

function exportReport() {
    const monthValue = document.getElementById('month-picker').value;
    if (!monthValue) return alert("Please select a month first.");
    window.location.href = `/api/teacher/monthly_report/export?month=${monthValue}`;
}

async function fetchHolidays() {
    const tableBody = document.getElementById('holiday-list-table');
    try {
        const data = await apiCall('/api/holidays');
        tableBody.innerHTML = '';
        data.holidays.forEach(date => {
            tableBody.innerHTML += `
                <tr>
                    <td class="p-3">${date}</td>
                    <td class="p-3">
                        <button onclick="deleteHoliday('${date}')" class="bg-red-500 hover:bg-red-600 text-white py-1 px-2 rounded-lg text-sm">Delete</button>
                    </td>
                </tr>`;
        });
    } catch (error) {
        alert('Failed to load holidays: ' + error.message);
    }
}

async function addHoliday() {
    const date = document.getElementById('new-holiday-date').value;
    if (!date) return alert("Please select a date.");
    try {
        await apiCall('/api/holidays', 'POST', { date });
        document.getElementById('new-holiday-date').value = '';
        await fetchHolidays();
    } catch (error) {
        alert('Failed to add holiday: ' + error.message);
    }
}

async function deleteHoliday(date) {
    if (confirm(`Are you sure you want to delete the holiday on ${date}?`)) {
        try {
            await apiCall(`/api/holidays/${date}`, 'DELETE');
            await fetchHolidays();
            if (views.teacher.classList.contains('active-view')) await getMonthlyReport();
        } catch (error) {
            alert('Failed to delete holiday: ' + error.message);
        }
    }
}

function switchTeacherSection(sectionId) {
    document.querySelectorAll('.teacher-section').forEach(s => s.classList.add('hidden'));
    document.getElementById(sectionId).classList.remove('hidden');
    document.querySelectorAll('.teacher-nav-button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.section === sectionId);
    });
    // Load data if switching to a new section
    if (sectionId === 'student-management-section') fetchTeacherStudents(true);
    if (sectionId === 'holiday-management-section') fetchHolidays();
}

// --- Student Dashboard ---
async function loadStudentDashboard() {
    try {
        const data = await apiCall('/api/student/data');
        document.getElementById('days-present').textContent = data.present_days;
        document.getElementById('days-absent').textContent = data.absent_days;
        document.getElementById('attendance-percentage').textContent = `${data.percentage}%`;

        const tableBody = document.getElementById('student-log-table');
        tableBody.innerHTML = '';
        if (data.records.length === 0) {
            tableBody.innerHTML = `<tr><td colspan="3" class="p-4 text-center text-slate-500">No records found.</td></tr>`;
        } else {
            data.records.forEach(entry => {
                tableBody.innerHTML += `<tr><td class="p-3">${entry.date}</td><td class="p-3 font-medium">${entry.status}</td><td class="p-3 text-sm text-slate-600">${entry.remarks || '—'}</td></tr>`;
            });
        }
    } catch (error) {
        alert('Could not load your data: ' + error.message);
    }
}

// --- Initialization ---
async function initSignupForm() {
    const select = document.getElementById('signup-class-select');
    select.innerHTML = '<option value="">Loading classes...</option>';
    try {
        const classes = await apiCall('/api/admin/classes');
        select.innerHTML = '<option value="">Select a class to manage</option>';
        classes.forEach(c => select.add(new Option(c.name, c.id)));
    } catch (error) {
        select.innerHTML = '<option value="">Could not load classes</option>';
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    // Auth view switching
    document.getElementById('show-signup-link').addEventListener('click', (e) => { e.preventDefault(); switchView('signup'); initSignupForm(); });
    document.getElementById('show-login-link').addEventListener('click', (e) => { e.preventDefault(); switchView('login'); });

    // Buttons
    document.getElementById('login-button').addEventListener('click', handleLogin);
    document.getElementById('signup-button').addEventListener('click', handleSignup);
    document.getElementById('logout-button').addEventListener('click', handleLogout);

    // Admin buttons
    document.getElementById('add-class-button').addEventListener('click', addClass);
    document.querySelectorAll('.admin-nav-button').forEach(btn => btn.addEventListener('click', () => switchAdminSection(btn.dataset.section)));

    // Teacher buttons
    document.getElementById('mark-full-day-button').addEventListener('click', () => markAttendance('Full Day'));
    document.getElementById('mark-half-day-button').addEventListener('click', () => markAttendance('Half Day'));
    document.getElementById('mark-absent-button').addEventListener('click', () => markAttendance('Absent'));
    document.getElementById('mark-all-full-day-button').addEventListener('click', () => markAll('Full Day'));
    document.getElementById('mark-all-half-day-button').addEventListener('click', () => markAll('Half Day'));
    document.getElementById('mark-all-absent-button').addEventListener('click', () => markAll('Absent'));
    document.getElementById('add-student-button').addEventListener('click', addStudent);
    document.getElementById('add-holiday-button').addEventListener('click', addHoliday);
    document.getElementById('view-monthly-report-button').addEventListener('click', getMonthlyReport);
    document.getElementById('export-csv-button').addEventListener('click', exportReport);
    document.querySelectorAll('.teacher-nav-button').forEach(btn => btn.addEventListener('click', () => switchTeacherSection(btn.dataset.section)));

    // Check for existing session
    try {
        const data = await apiCall('/api/session');
        showDashboard(data.user);
    } catch (error) {
        switchView('login');
    }
});
