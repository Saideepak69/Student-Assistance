# app.py — Student Assistance Webapp (pure Python via Streamlit)
# Run:
#   pip install streamlit fpdf
#   streamlit run app.py
# Data is stored locally in SQLite: student_app.db

import sqlite3
from contextlib import closing
from pathlib import Path
import hashlib
import secrets
import datetime as dt

import streamlit as st
from fpdf import FPDF

DB_PATH = Path("student_app.db")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# --------------------------- UTILITIES ---------------------------

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                attachment TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task TEXT NOT NULL,
                due_date TEXT,
                remind_before_hours INTEGER DEFAULT 0,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                questions TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                goal TEXT NOT NULL,
                target_value INTEGER NOT NULL,
                progress INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS timetable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            day TEXT,
            slot TEXT,
            subject TEXT
            );
        """)
        conn.commit()

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# --------------------------- AUTH ---------------------------

def create_user(username: str, password: str) -> tuple[bool, str]:
    username = username.strip().lower()
    if not username or not password:
        return False, "Username and password required."
    salt = secrets.token_hex(16)
    pwd_hash = hash_password(password, salt)
    now = dt.datetime.utcnow().isoformat()
    try:
        with closing(get_conn()) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, salt, password_hash, created_at) VALUES (?,?,?,?)",
                (username, salt, pwd_hash, now),
            )
            conn.commit()
        return True, "Account created."
    except sqlite3.IntegrityError:
        return False, "Username already exists."

def authenticate(username: str, password: str):
    username = username.strip().lower()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, salt, password_hash FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        if not row:
            return None
        uid, salt, ph = row
        if hash_password(password, salt) == ph:
            return uid
    return None

# --------------------------- NOTES + ATTACHMENTS ---------------------------

def add_note(user_id: int, title: str, content: str, attachment_path: str | None):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notes (user_id, title, content, attachment, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (user_id, title, content, attachment_path, now, now),
        )
        conn.commit()

def update_note(note_id: int, title: str, content: str, attachment_path: str | None = None):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        if attachment_path is None:
            cur.execute(
                "UPDATE notes SET title=?, content=?, updated_at=? WHERE id=?",
                (title, content, now, note_id),
            )
        else:
            cur.execute(
                "UPDATE notes SET title=?, content=?, attachment=?, updated_at=? WHERE id=?",
                (title, content, attachment_path, now, note_id),
            )
        conn.commit()

def delete_note(note_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT attachment FROM notes WHERE id=?", (note_id,))
        row = cur.fetchone()
        if row and row[0]:
            try:
                p = Path(row[0])
                if p.exists():
                    p.unlink()
            except Exception:
                pass
        cur.execute("DELETE FROM notes WHERE id=?", (note_id,))
        conn.commit()

def list_notes(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, title, content, attachment, created_at, updated_at FROM notes WHERE user_id=? ORDER BY updated_at DESC",
            (user_id,),
        )
        return cur.fetchall()

# --------------------------- FLASHCARDS ---------------------------

def add_flashcard(user_id, question, answer):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO flashcards (user_id, question, answer, created_at) VALUES (?,?,?,?)",
            (user_id, question, answer, now)
        )
        conn.commit()

def list_flashcards(user_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, question, answer FROM flashcards WHERE user_id=? ORDER BY id DESC", (user_id,))
        return cur.fetchall()

# --------------------------- QUIZZES ---------------------------

def add_quiz(user_id, title, questions_json):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO quizzes (user_id, title, questions, created_at) VALUES (?,?,?,?)",
                    (user_id, title, questions_json, now))
        conn.commit()

def list_quizzes(user_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, title, questions FROM quizzes WHERE user_id=? ORDER BY id DESC", (user_id,))
        return cur.fetchall()

# --------------------------- GOALS ---------------------------

def add_goal(user_id, goal, target_value):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO goals (user_id, goal, target_value, progress, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (user_id, goal, target_value, 0, now, now))
        conn.commit()

def update_goal_progress(goal_id, progress):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE goals SET progress=?, updated_at=? WHERE id=?", (progress, now, goal_id))
        conn.commit()

def list_goals(user_id):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, goal, target_value, progress FROM goals WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
        return cur.fetchall()

# --------------------------- TASKS + REMINDERS ---------------------------

def add_task(user_id: int, task: str, due_date: str | None, remind_before_hours: int | None = 0):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (user_id, task, due_date, remind_before_hours, done, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, task, due_date, remind_before_hours or 0, 0, now, now),
        )
        conn.commit()

def toggle_task(task_id: int, done: bool):
    now = dt.datetime.utcnow().isoformat()
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE tasks SET done=?, updated_at=? WHERE id=?",
            (1 if done else 0, now, task_id),
        )
        conn.commit()

def delete_task(task_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()

def list_tasks(user_id: int):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, task, due_date, remind_before_hours, done, created_at, updated_at FROM tasks WHERE user_id=? ORDER BY done, COALESCE(due_date,''), updated_at DESC",
            (user_id,),
        )
        return cur.fetchall()

# --------------------------- EXPORTS ---------------------------

def notes_to_pdf(notes: list[tuple]) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Arial", size=14)
    pdf.cell(0, 8, "Notes Export", ln=1)
    pdf.set_font("Arial", size=11)
    for _id, title, content, attachment, created_at, updated_at in notes:
        pdf.ln(2)
        pdf.set_font("Arial", 'B', 12)
        pdf.multi_cell(0, 7, f"{title} (updated {updated_at.split('T')[0]})")
        pdf.set_font("Arial", size=11)
        pdf.multi_cell(0, 6, content)
        if attachment:
            pdf.multi_cell(0, 6, f"Attachment: {attachment}")
        pdf.ln(4)
    return pdf.output(dest='S').encode('latin-1')

def tasks_to_ics(tasks: list[tuple]) -> bytes:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//StudentAssistance//EN",
    ]
    for tid, task, due_date, remind, done, created_at, updated_at in tasks:
        if not due_date:
            continue
        try:
            dt_obj = dt.datetime.fromisoformat(due_date)
        except Exception:
            continue
        dtstamp = dt_obj.strftime('%Y%m%dT%H%M%S')
        uid = f"task-{tid}@student-assist"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}Z",
            f"DTSTART:{dtstamp}Z",
            f"SUMMARY:{task}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(lines).encode()

# --------------------------- UI ---------------------------

def show_login():
    st.title("🎓 Student Assistance")
    st.caption("Built with pure Python (Streamlit + SQLite). Now with PDF export, attachments, and reminders (ICS export).")

    tab_login, tab_signup = st.tabs(["Login", "Sign up"])

    with tab_login:
        with st.form("login_form", clear_on_submit=False):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in")
        if submitted:
            uid = authenticate(u, p)
            if uid:
                st.session_state.user_id = uid
                st.session_state.username = u.strip().lower()
                st.success("Welcome back! ✅")
                st.rerun()
            else:
                st.error("Invalid credentials.")

    with tab_signup:
        with st.form("signup_form", clear_on_submit=False):
            u2 = st.text_input("Pick a username")
            p2 = st.text_input("Create a password", type="password")
            ok = st.form_submit_button("Create account")
        if ok:
            success, msg = create_user(u2, p2)
            (st.success if success else st.error)(msg)

def sidebar_nav():
    with st.sidebar:
        st.header(f"Hello, {st.session_state.username} 👋")
        page = st.radio(
            "Go to",
            ["Notes", "Tasks", "GPA Calculator", "Timetable", "Exports", "Flashcards", "Quizzes", "Goals"],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            for k in ["user_id", "username"]:
                st.session_state.pop(k, None)
            st.rerun()
    return page

# --------------------------- PAGES ---------------------------

def page_notes():
    st.subheader("📝 Notes")
    with st.expander("Add a note", expanded=True):
        with st.form("add_note"):
            title = st.text_input("Title")
            content = st.text_area("Content", height=160)
            uploaded = st.file_uploader("Attach a file (optional)", type=None)
            submitted = st.form_submit_button("Save note")
        if submitted and title and content:
            attach_path = None
            if uploaded is not None:
                dest = UPLOAD_DIR / f"{secrets.token_hex(8)}_{uploaded.name}"
                with open(dest, "wb") as f:
                    f.write(uploaded.getbuffer())
                attach_path = str(dest)
            add_note(st.session_state.user_id, title, content, attach_path)
            st.success("Saved!")
            st.rerun()

    notes = list_notes(st.session_state.user_id)
    if not notes:
        st.info("No notes yet. Create your first above.")
        return

    for nid, title, content, attachment, created_at, updated_at in notes:
        with st.container():
            st.markdown(f"**{title}**  ·  _updated {updated_at.split('T')[0]}_")
            edited = st.text_area("Edit content", value=content, key=f"edit_{nid}")
            if attachment:
                st.write(f"Attachment: {Path(attachment).name}")
                if st.button("Download attachment", key=f"dl_{nid}"):
                    with open(attachment, "rb") as f:
                        st.download_button(label="Download", data=f, file_name=Path(attachment).name)
            col1, col2, col3 = st.columns(3)
            if col1.button("Update", key=f"upd_{nid}"):
                update_note(nid, title, edited)
                st.success("Updated.")
                st.rerun()
            if col2.button("Delete", key=f"del_{nid}"):
                delete_note(nid)
                st.warning("Deleted.")
                st.rerun()
            if col3.button("Export this note to PDF", key=f"pdf_{nid}"):
                note_pdf = notes_to_pdf([(nid, title, edited, attachment, created_at, updated_at)])
                st.download_button("Download PDF", data=note_pdf, file_name=f"note_{nid}.pdf")

def page_tasks():
    st.subheader("✅ Tasks & Reminders")
    with st.form("add_task", clear_on_submit=True):
        t = st.text_input("Task")
        due = st.date_input("Due date (optional)", value=None, format="YYYY-MM-DD")
        time_val = st.time_input("Time (if due date set)", value=dt.time(9, 0))
        remind_before = st.number_input("Remind before (hours)", min_value=0, max_value=168, value=0)
        submitted = st.form_submit_button("Add")
    if submitted and t:
        due_str = None
        if due is not None:
            try:
                dt_obj = dt.datetime.combine(due, time_val)
                due_str = dt_obj.isoformat()
            except Exception:
                due_str = due.isoformat()
        add_task(st.session_state.user_id, t, due_str, int(remind_before))
        st.success("Task added.")
        st.rerun()

    tasks = list_tasks(st.session_state.user_id)
    if not tasks:
        st.info("No tasks yet. Add one above.")
        return

    now = dt.datetime.utcnow()
    upcoming = []
    for tid, task, due_date, remind_before, done, created_at, updated_at in tasks:
        cols = st.columns([0.08, 0.6, 0.18, 0.14])
        with cols[0]:
            checked = st.checkbox("", value=bool(done), key=f"chk_{tid}")
        with cols[1]:
            st.write(task)
            if due_date:
                st.caption(f"Due: {due_date}")
        with cols[2]:
            if st.button("Delete", key=f"tdel_{tid}"):
                delete_task(tid)
                st.rerun()
        with cols[3]:
            if bool(done) != checked:
                toggle_task(tid, checked)
        if due_date:
            try:
                dt_obj = dt.datetime.fromisoformat(due_date)
                remind_time = dt_obj - dt.timedelta(hours=remind_before or 0)
                if remind_time > now and (remind_time - now) < dt.timedelta(days=7):
                    upcoming.append((task, dt_obj, remind_time))
            except Exception:
                pass

    if upcoming:
        st.divider()
        st.subheader("🔔 Upcoming reminders (next 7 days)")
        for task, due_dt, remind_dt in upcoming:
            st.write(f"**{task}** — remind at {remind_dt.strftime('%Y-%m-%d %H:%M')}, due {due_dt.strftime('%Y-%m-%d %H:%M')}")
        if st.button("Export reminders to calendar (.ics)"):
            ics = tasks_to_ics(tasks)
            st.download_button("Download ICS", data=ics, file_name="reminders.ics")

def page_gpa():
    st.subheader("📊 GPA Calculator")
    st.caption("Enter grade points (e.g., 10 for A+) and credits.")
    n = st.number_input("# of subjects", min_value=1, max_value=50, value=5)
    grades, credits = [], []
    for i in range(n):
        g, c = st.columns(2)
        grades.append(g.number_input(f"Grade {i+1}", min_value=0.0, max_value=10.0, step=0.1, value=10.0, key=f"g{i}"))
        credits.append(c.number_input(f"Credits {i+1}", min_value=1, max_value=10, value=3, key=f"c{i}"))
    if st.button("Calculate GPA"):
        gpa = sum([grades[i]*credits[i] for i in range(n)]) / sum(credits)
        st.success(f"Your GPA: {gpa:.2f}")

def get_timetable(user_id):
    slots = ["9:00–10:00","10:00–11:00","11:00–12:00","2:00–3:00"]
    days = ["Mon","Tue","Wed","Thu","Fri"]
    table = {day: {slot: "" for slot in slots} for day in days}
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT day, slot, subject FROM timetable WHERE user_id=?", (user_id,))
        for day, slot, subject in cur.fetchall():
            table[day][slot] = subject
    return table

def save_timetable(user_id, table):
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        for day, slots in table.items():
            for slot, subject in slots.items():
                cur.execute("""
                    INSERT INTO timetable(user_id, day, slot, subject) VALUES(?,?,?,?)
                    ON CONFLICT(user_id, day, slot) DO UPDATE SET subject=excluded.subject
                """, (user_id, day, slot, subject))
        conn.commit()

def page_timetable():
    st.subheader("🗓️ Editable Timetable")
    st.caption("Edit your subjects and save.")

    slots = ["9:00–10:00","10:00–11:00","11:00–12:00","2:00–3:00"]
    days = ["Mon","Tue","Wed","Thu","Fri"]

    table = get_timetable(st.session_state.user_id)

    edited_table = {}
    for day in days:
        st.markdown(f"**{day}**")
        edited_table[day] = {}
        for slot in slots:
            edited_table[day][slot] = st.text_input(f"{slot}", value=table[day][slot], key=f"{day}_{slot}")
        st.divider()

    if st.button("Save Timetable"):
        save_timetable(st.session_state.user_id, edited_table)
        st.success("Timetable saved!")

def page_exports():
    st.subheader("📁 Exports (PDF / ICS)")
    st.info("Export options are integrated in Notes & Tasks pages.")

def page_flashcards_ui():
    st.subheader("📚 Flashcards")
    with st.form("add_flashcard"):
        q = st.text_input("Question")
        a = st.text_area("Answer")
        if st.form_submit_button("Add Flashcard"):
            add_flashcard(st.session_state.user_id, q, a)
            st.success("Flashcard added.")
            st.rerun()
    flashcards = list_flashcards(st.session_state.user_id)
    for fid, q, a in flashcards:
        with st.expander(q):
            st.write(a)

def page_quizzes_ui():
    st.subheader("📝 Quizzes")
    with st.form("add_quiz"):
        title = st.text_input("Quiz title")
        questions = st.text_area("Questions (JSON or simple format)")
        if st.form_submit_button("Add Quiz"):
            add_quiz(st.session_state.user_id, title, questions)
            st.success("Quiz added.")
            st.rerun()
    quizzes = list_quizzes(st.session_state.user_id)
    for qid, title, questions in quizzes:
        with st.expander(title):
            st.text(questions)

def page_goals_ui():
    st.subheader("🎯 Goals & Progress")
    with st.form("add_goal"):
        g = st.text_input("Goal description")
        t = st.number_input("Target value", min_value=1, value=10)
        if st.form_submit_button("Add Goal"):
            add_goal(st.session_state.user_id, g, t)
            st.success("Goal added.")
            st.rerun()
    goals = list_goals(st.session_state.user_id)
    for gid, g, t, p in goals:
        st.write(f"{g}: {p}/{t}")
        st.progress(p/t if t else 0)
        new_p = st.number_input("Update progress", min_value=0, max_value=t, value=p, key=f"goal_{gid}")
        if new_p != p:
            update_goal_progress(gid, new_p)
            st.success("Progress updated.")
            st.rerun()

# --------------------------- MAIN ---------------------------

def main():
    init_db()
    if "user_id" not in st.session_state:
        show_login()
        return

    page = sidebar_nav()

    if page == "Notes":
        page_notes()
    elif page == "Tasks":
        page_tasks()
    elif page == "GPA Calculator":
        page_gpa()
    elif page == "Timetable":
        page_timetable()
    elif page == "Exports":
        page_exports()
    elif page == "Flashcards":
        page_flashcards_ui()
    elif page == "Quizzes":
        page_quizzes_ui()
    elif page == "Goals":
        page_goals_ui()

if __name__ == "__main__":
    main()
