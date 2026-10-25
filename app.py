import os
import re
import sqlite3
import uuid
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:
    cloudinary = None

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.getenv("DATABASE_PATH", "instance/digital_udaan.sqlite3"))
if not DATABASE.is_absolute():
    DATABASE = BASE_DIR / DATABASE
UPLOAD_FOLDER = Path(os.getenv("UPLOAD_FOLDER", "static/uploads"))
if not UPLOAD_FOLDER.is_absolute():
    UPLOAD_FOLDER = BASE_DIR / UPLOAD_FOLDER
ALLOWED_IMAGE = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_VIDEO = {"mp4", "webm"}
ALLOWED_FAVICON = {"png", "ico", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev-only-change-this-secret-before-deployment"),
    MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", "52428800")),
    UPLOAD_FOLDER=str(UPLOAD_FOLDER),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("FLASK_DEBUG", "1") == "0",
)
CSRFProtect(app)
DATABASE.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

def store_upload(upload, filename, resource_type="image"):
    if cloudinary and os.getenv("CLOUDINARY_URL"):
        result = cloudinary.uploader.upload(upload, folder="digital-udaan", resource_type=resource_type, public_id=Path(filename).stem, overwrite=True)
        return result["secure_url"]
    upload.save(UPLOAD_FOLDER / filename)
    return "/static/uploads/" + filename

COURSE_SEEDS = [
    ("Digital Marketing Foundations", "Build a clear digital marketing plan for a small business.", "Strategy", "Beginner", 90, "Learn the channels, customer journey and a simple weekly plan.", "chart"),
    ("Instagram for Small Business", "Turn your Instagram profile into a useful customer touchpoint.", "Social Media", "Beginner", 120, "Plan content, improve your profile and measure meaningful results.", "instagram"),
    ("WhatsApp Business Essentials", "Use WhatsApp Business to serve customers and manage enquiries.", "Customer Growth", "Beginner", 75, "Set up your catalogue, quick replies and customer-friendly workflows.", "message"),
    ("SEO Basics", "Help customers discover your website through search.", "Search", "Beginner", 150, "Understand keywords, on-page SEO and local search fundamentals.", "search"),
    ("Google Business Profile", "Improve your local business presence on Google Search and Maps.", "Local Marketing", "Beginner", 60, "Create a trustworthy profile and maintain accurate business details.", "pin"),
    ("Canva Content Studio", "Design consistent marketing assets without a design team.", "Creative", "Beginner", 90, "Build reusable designs for posts, stories and promotions.", "palette"),
    ("Reels & Short-Form Video", "Plan, shoot and edit useful short videos.", "Content", "Intermediate", 120, "Create a repeatable workflow from hook to call to action.", "video"),
    ("Social Ads Fundamentals", "Understand paid social campaign structure and testing.", "Advertising", "Intermediate", 150, "Learn objectives, audiences, creative tests and budget discipline.", "target"),
    ("Marketing Analytics", "Measure results and make better marketing decisions.", "Analytics", "Beginner", 90, "Track goals, interpret simple metrics and report outcomes.", "analytics"),
    ("Build Your Online Brand", "Create a consistent, trustworthy brand presence online.", "Branding", "Beginner", 75, "Clarify your audience, message, visual system and brand voice.", "spark"),
]

LESSON_TEMPLATES = [
    ("Start with the goal", "Start by defining one customer problem and one measurable business outcome. Choose a goal such as qualified enquiries, bookings or repeat purchases.", "Write one sentence describing your target customer and the problem you solve.", "Keep the first experiment small enough to measure in a week.", "Avoid trying every platform at once.", "https://www.youtube.com/results?search_query=digital+marketing+for+small+business+beginners"),
    ("Build a simple action plan", "Pick one primary channel, create a realistic weekly publishing rhythm and give every piece of content a purpose. Record what you publish and what response it receives.", "Draft a seven-day plan with three useful posts and one customer follow-up.", "Consistency beats an ambitious plan you cannot maintain.", "Do not judge performance from one post alone.", "https://www.youtube.com/results?search_query=small+business+content+marketing+strategy"),
    ("Measure and improve", "Review the results against the goal you chose. Look for patterns, keep what works and change one variable at a time so you can learn from the outcome.", "Create a tiny report with goal, activity, result and next experiment.", "Track meaningful outcomes, not just vanity metrics.", "Do not assume correlation proves what caused a result.", "https://www.youtube.com/results?search_query=digital+marketing+analytics+beginners"),
]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
      email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'student', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS courses (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
      slug TEXT NOT NULL UNIQUE, description TEXT NOT NULL, category TEXT NOT NULL,
      level TEXT NOT NULL DEFAULT 'Beginner', duration INTEGER NOT NULL DEFAULT 60,
      outcomes TEXT NOT NULL DEFAULT '', thumbnail TEXT NOT NULL DEFAULT '',
      published INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS lessons (
      id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
      title TEXT NOT NULL, body TEXT NOT NULL, tips TEXT NOT NULL DEFAULT '',
      notes TEXT NOT NULL DEFAULT '', assignment TEXT NOT NULL DEFAULT '',
      video_url TEXT NOT NULL DEFAULT '', sort_order INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS progress (
      id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      lesson_id INTEGER NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
      completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, lesson_id)
    );
    CREATE TABLE IF NOT EXISTS feedback (
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '',
      message TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS settings (
      key TEXT PRIMARY KEY, value TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS daily_tips (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, body TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT 'Marketing', published INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS resources (
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
      url TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Templates', published INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    count = db.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    if count == 0:
        for title, desc, category, level, duration, outcomes, icon in COURSE_SEEDS:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            cur = db.execute("""INSERT INTO courses
                (title,slug,description,category,level,duration,outcomes,thumbnail)
                VALUES (?,?,?,?,?,?,?,?)""",
                (title, slug, desc, category, level, duration, outcomes, f"/static/img/course-{icon}.svg"))
            cid = cur.lastrowid
            for idx, lesson in enumerate(LESSON_TEMPLATES, 1):
                lt, body, assignment, tips, notes, video = lesson
                db.execute("""INSERT INTO lessons
                    (course_id,title,body,tips,notes,assignment,video_url,sort_order)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (cid, f"{idx}. {lt}", body, tips, notes, assignment, video, idx))
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('site_name','Digital Udaan')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('tagline','Practical digital skills for growing businesses')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('logo_path','/static/img/logo.svg')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('favicon_path','/static/img/favicon.svg')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('hero_title','Make your next digital move count.')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('hero_text','Clear, practical lessons to help you reach customers, create better content and grow your business online — one step at a time.')")
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('hero_image','')")
    if db.execute("SELECT COUNT(*) FROM daily_tips").fetchone()[0] == 0:
        for title, body, category in [
            ('Fix your Instagram bio', 'Say who you help, what result you provide and what the visitor should do next. Add one clear contact or order link.', 'Social Media'),
            ('Make every post useful', 'Before publishing, ask: will this teach, inspire, reassure or help a customer decide? Give every post one job.', 'Content'),
            ('Reply like a real person', 'Use saved replies for speed, but personalise the first line and answer the actual question. Trust grows through helpful conversations.', 'Customer Experience'),
            ('Track enquiries, not just likes', 'Record how many genuine enquiries, bookings or orders came from a campaign. Reach is useful, but business outcomes matter too.', 'Analytics'),
            ('Show proof, with permission', 'Use real customer feedback, product demonstrations and behind-the-scenes details. Never invent reviews or results.', 'Brand Trust'),
        ]:
            db.execute('INSERT INTO daily_tips(title,body,category) VALUES(?,?,?)', (title,body,category))
    # Optional Render admin bootstrap. Set ADMIN_EMAIL and ADMIN_PASSWORD in the
    # service Environment; init-db will create/promote that account.
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    admin_name = os.getenv("ADMIN_NAME", "Digital Udaan Admin").strip() or "Digital Udaan Admin"
    if admin_email and len(admin_password) >= 12:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", admin_email):
            raise ValueError("ADMIN_EMAIL must be a valid email address")
        existing = db.execute("SELECT id FROM users WHERE email=?", (admin_email,)).fetchone()
        hashed = generate_password_hash(admin_password)
        if existing:
            db.execute("UPDATE users SET name=?, password_hash=?, role='admin' WHERE email=?",
                       (admin_name, hashed, admin_email))
        else:
            db.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?, 'admin')",
                       (admin_name, admin_email, hashed))

    db.commit()

@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database ready.")

@app.cli.command("create-admin")
def create_admin_command():
    init_db()
    db = get_db()
    username = input("Admin name: ").strip()
    email = input("Admin email: ").strip().lower()
    password = input("Admin password (minimum 12 characters): ")
    if not username or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise SystemExit("Please provide a name and valid email.")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    try:
        db.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')",
                   (username, email, generate_password_hash(password)))
        db.commit()
    except sqlite3.IntegrityError:
        raise SystemExit("That email already exists. Use a different email.")
    print("Admin account created.")

@app.context_processor
def inject_globals():
    return {"current_user": get_current_user(), "site_name": get_setting("site_name", "Digital Udaan"),
            "site_logo": get_setting("logo_path", "/static/img/logo.svg"),
            "site_favicon": get_setting("favicon_path", "/static/img/favicon.svg"),
            "site_tagline": get_setting("tagline", "Practical digital skills for growing businesses")}

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT id,name,email,role FROM users WHERE id=?", (uid,)).fetchone()

def get_setting(key, default=""):
    try:
        row = get_db().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    except sqlite3.OperationalError:
        return default

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_current_user():
            flash("Please sign in to continue.", "info")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user or user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

def safe_video_url(value):
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {
        "youtube.com", "www.youtube.com", "youtu.be", "www.youtube-nocookie.com"
    }:
        raise ValueError("Video URL must be a valid HTTPS YouTube link.")
    return value

@app.route("/")
def index():
    courses = get_db().execute("SELECT * FROM courses WHERE published=1 ORDER BY id LIMIT 6").fetchall()
    tips = get_db().execute("SELECT * FROM daily_tips WHERE published=1 ORDER BY RANDOM() LIMIT 1").fetchone()
    resources = get_db().execute("SELECT * FROM resources WHERE published=1 ORDER BY id DESC LIMIT 3").fetchall()
    return render_template("index.html", courses=courses, tips=tips, resources=resources, hero_title=get_setting("hero_title", "Make your next digital move count."), hero_text=get_setting("hero_text", "Clear, practical lessons to help you reach customers, create better content and grow your business online — one step at a time."), hero_image=get_setting("hero_image", ""))

@app.route("/resources")
def public_resources():
    resources = get_db().execute("SELECT * FROM resources WHERE published=1 ORDER BY id DESC").fetchall()
    return render_template("resources.html", resources=resources)

@app.route("/courses")
def courses():
    category = request.args.get("category", "").strip()
    q = request.args.get("q", "").strip()
    sql = "SELECT * FROM courses WHERE published=1"
    args = []
    if category:
        sql += " AND category=?"; args.append(category)
    if q:
        sql += " AND (title LIKE ? OR description LIKE ?)"; args.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY title"
    items = get_db().execute(sql, args).fetchall()
    categories = get_db().execute("SELECT DISTINCT category FROM courses WHERE published=1 ORDER BY category").fetchall()
    return render_template("courses.html", courses=items, categories=categories, selected=category, q=q)

@app.route("/courses/<slug>")
def course_detail(slug):
    course = get_db().execute("SELECT * FROM courses WHERE slug=? AND published=1", (slug,)).fetchone()
    if not course: abort(404)
    lessons = get_db().execute("SELECT * FROM lessons WHERE course_id=? ORDER BY sort_order,id", (course["id"],)).fetchall()
    completed = set()
    user = get_current_user()
    if user:
        completed = {r["lesson_id"] for r in get_db().execute(
            "SELECT p.lesson_id FROM progress p JOIN lessons l ON l.id=p.lesson_id WHERE p.user_id=? AND l.course_id=?",
            (user["id"], course["id"])).fetchall()}
    return render_template("course.html", course=course, lessons=lessons, completed=completed)

@app.route("/lesson/<int:lesson_id>")
def lesson_detail(lesson_id):
    lesson = get_db().execute("""SELECT l.*,c.title course_title,c.slug course_slug,c.id course_id
        FROM lessons l JOIN courses c ON c.id=l.course_id WHERE l.id=? AND c.published=1""", (lesson_id,)).fetchone()
    if not lesson: abort(404)
    user = get_current_user()
    completed = False
    if user:
        completed = bool(get_db().execute("SELECT 1 FROM progress WHERE user_id=? AND lesson_id=?", (user["id"], lesson_id)).fetchone())
    return render_template("lesson.html", lesson=lesson, completed=completed)

@app.post("/lesson/<int:lesson_id>/complete")
@login_required
def complete_lesson(lesson_id):
    db = get_db()
    exists = db.execute("SELECT id FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not exists: abort(404)
    db.execute("INSERT OR IGNORE INTO progress(user_id,lesson_id) VALUES(?,?)", (get_current_user()["id"], lesson_id))
    db.commit()
    flash("Lesson marked complete.", "success")
    return redirect(url_for("lesson_detail", lesson_id=lesson_id))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(name) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(password) < 10:
            flash("Enter a name, valid email and password of at least 10 characters.", "error")
        else:
            try:
                cur = get_db().execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                    (name, email, generate_password_hash(password)))
                get_db().commit()
                session.clear(); session["user_id"] = cur.lastrowid
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("An account with that email already exists.", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear(); session["user_id"] = user["id"]
            return redirect(url_for("admin_dashboard") if user["role"] == "admin" else url_for("dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.post("/logout")
def logout():
    session.clear()
    flash("You have signed out.", "success")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_current_user()
    progress_rows = get_db().execute("""SELECT c.id,c.title,c.slug,COUNT(l.id) total,
      SUM(CASE WHEN p.lesson_id IS NOT NULL THEN 1 ELSE 0 END) done
      FROM courses c LEFT JOIN lessons l ON l.course_id=c.id
      LEFT JOIN progress p ON p.lesson_id=l.id AND p.user_id=?
      WHERE c.published=1 GROUP BY c.id ORDER BY c.title""", (user["id"],)).fetchall()
    return render_template("dashboard.html", progress_rows=progress_rows)

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        if len(name) < 2 or len(message) < 10:
            flash("Please provide your name and a message of at least 10 characters.", "error")
        else:
            get_db().execute("INSERT INTO feedback(name,email,message) VALUES(?,?,?)", (name,email,message))
            get_db().commit()
            flash("Thanks for your feedback.", "success")
            return redirect(url_for("contact"))
    return render_template("contact.html")

@app.route("/admin/login")
def admin_login():
    return redirect(url_for("login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    stats = {
        "courses": db.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "lessons": db.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
        "students": db.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        "feedback": db.execute("SELECT COUNT(*) FROM feedback").fetchone()[0],
    }
    courses = db.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
    return render_template("admin.html", stats=stats, courses=courses)

@app.route("/admin/courses/new", methods=["GET", "POST"])
@app.route("/admin/courses/<int:course_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_course_form(course_id=None):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone() if course_id else None
    if course_id and not course: abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        level = request.form.get("level", "Beginner")
        try: duration = max(1, min(10000, int(request.form.get("duration", "60"))))
        except ValueError: duration = 60
        thumbnail = course["thumbnail"] if course else "/static/img/course-chart.svg"
        image = request.files.get("thumbnail")
        if image and image.filename:
            ext = image.filename.rsplit(".", 1)[-1].lower() if "." in image.filename else ""
            if ext not in ALLOWED_IMAGE:
                flash("Thumbnail must be PNG, JPG, WEBP or GIF.", "error")
                return render_template("admin_course_form.html", course=course)
            filename = f"course-{uuid.uuid4().hex}.{ext}"
            thumbnail = store_upload(image, filename)
        if len(title) < 3 or len(description) < 10 or not category:
            flash("Title, description (10+ characters) and category are required.", "error")
        else:
            slug_base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "course"
            slug = slug_base
            suffix = 2
            while db.execute("SELECT id FROM courses WHERE slug=? AND id!=?", (slug, course_id or 0)).fetchone():
                slug = f"{slug_base}-{suffix}"; suffix += 1
            outcomes = request.form.get("outcomes", "Practical skills and action steps").strip()[:500]
            published = 1 if request.form.get("published") == "on" else 0
            if course:
                db.execute("""UPDATE courses SET title=?,slug=?,description=?,category=?,level=?,duration=?,outcomes=?,thumbnail=?,published=? WHERE id=?""",
                           (title,slug,description,category,level,duration,outcomes,thumbnail,published,course_id))
                cid = course_id
            else:
                cur = db.execute("""INSERT INTO courses(title,slug,description,category,level,duration,outcomes,thumbnail,published)
                    VALUES(?,?,?,?,?,?,?,?,?)""", (title,slug,description,category,level,duration,outcomes,thumbnail,published))
                cid = cur.lastrowid
            db.commit()
            flash("Course saved. Add a practical lesson next!", "success")
            return redirect(url_for("admin_lessons", course_id=cid))
    return render_template("admin_course_form.html", course=course)

@app.route("/admin/courses/<int:course_id>/delete", methods=["POST"])
@admin_required
def admin_course_delete(course_id):
    db = get_db()
    db.execute("DELETE FROM courses WHERE id=?", (course_id,))
    db.commit()
    flash("Course deleted.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/courses/<int:course_id>/lessons", methods=["GET", "POST"])
@app.route("/admin/courses/<int:course_id>/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_lessons(course_id, lesson_id=None):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
    if not course: abort(404)
    lesson = db.execute("SELECT * FROM lessons WHERE id=? AND course_id=?", (lesson_id, course_id)).fetchone() if lesson_id else None
    if lesson_id and not lesson: abort(404)
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        tips = request.form.get("tips", "").strip()
        notes = request.form.get("notes", "").strip()
        assignment = request.form.get("assignment", "").strip()
        video_url = request.form.get("video_url", "").strip()
        video_path = lesson["video_url"] if lesson else ""
        upload = request.files.get("video_file")
        if upload and upload.filename:
            ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
            if ext not in ALLOWED_VIDEO:
                flash("Video must be MP4 or WEBM.", "error")
                return redirect(request.url)
            filename = f"lesson-{uuid.uuid4().hex}.{ext}"
            video_path = store_upload(upload, filename, resource_type="video")
        try:
            video_url = safe_video_url(video_url) if video_url else ""
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(request.url)
        if len(title) < 3 or len(body) < 20:
            flash("Lesson title and explanation (20+ characters) are required.", "error")
        else:
            video_value = video_path or video_url
            if lesson:
                db.execute("UPDATE lessons SET title=?,body=?,tips=?,notes=?,assignment=?,video_url=? WHERE id=?",
                           (title,body,tips,notes,assignment,video_value,lesson_id))
                flash("Lesson updated successfully.", "success")
            else:
                order = db.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM lessons WHERE course_id=?", (course_id,)).fetchone()[0]
                db.execute("INSERT INTO lessons(course_id,title,body,tips,notes,assignment,video_url,sort_order) VALUES(?,?,?,?,?,?,?,?)",
                           (course_id,title,body,tips,notes,assignment,video_value,order))
                flash("Lesson added. Give learners a task they can finish today!", "success")
            db.commit()
            return redirect(url_for("admin_lessons", course_id=course_id))
    lessons = db.execute("SELECT * FROM lessons WHERE course_id=? ORDER BY sort_order,id", (course_id,)).fetchall()
    return render_template("admin_lessons.html", course=course, lessons=lessons, lesson=lesson)

@app.post("/admin/lessons/<int:lesson_id>/delete")
@admin_required
def admin_lesson_delete(lesson_id):
    db = get_db()
    lesson = db.execute("SELECT course_id FROM lessons WHERE id=?", (lesson_id,)).fetchone()
    if not lesson: abort(404)
    course_id = lesson["course_id"]
    db.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))
    db.commit()
    flash("Lesson deleted.", "success")
    return redirect(url_for("admin_lessons", course_id=course_id))

@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    db = get_db()
    if request.method == "POST":
        fields = ("site_name", "tagline", "hero_title", "hero_text")
        for key in fields:
            value = request.form.get(key, "").strip()[:1000]
            if value:
                db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key,value))
        hero_image_url = request.form.get("hero_image_url", "").strip()
        if hero_image_url:
            parsed_hero_url = urlparse(hero_image_url)
            if parsed_hero_url.scheme != "https" or parsed_hero_url.netloc != "res.cloudinary.com":
                flash("Hero image URL must be a valid HTTPS Cloudinary URL.", "error")
                return redirect(url_for("admin_settings"))
            db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", ("hero_image", hero_image_url))
        for field, setting_key, allowed in (("logo", "logo_path", ALLOWED_IMAGE), ("favicon", "favicon_path", ALLOWED_FAVICON), ("hero_image", "hero_image", ALLOWED_IMAGE)):
            upload = request.files.get(field)
            if upload and upload.filename:
                ext = upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""
                if ext not in allowed:
                    flash(f"{field.title()} file type is not supported.", "error")
                    return redirect(url_for("admin_settings"))
                filename = f"{field}-{uuid.uuid4().hex}.{ext}"
                stored_path = store_upload(upload, filename)
                db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (setting_key, stored_path))
        db.commit()
        flash("Brand settings saved. Refresh the site to see the changes.", "success")
        return redirect(url_for("admin_settings"))
    return render_template("admin_settings.html", site_name=get_setting("site_name","Digital Udaan"),
        tagline=get_setting("tagline","Practical digital skills for growing businesses"),
        hero_title=get_setting("hero_title", "Make your next digital move count."),
        hero_text=get_setting("hero_text", "Clear, practical lessons to help you reach customers, create better content and grow your business online — one step at a time."),
        site_logo=get_setting("logo_path", "/static/img/logo.svg"),
        site_favicon=get_setting("favicon_path", "/static/img/favicon.svg"),
        hero_image=get_setting("hero_image", ""))

@app.route("/admin/tips", methods=["GET", "POST"])
@admin_required
def admin_tips():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        category = request.form.get("category", "Marketing").strip() or "Marketing"
        if len(title) < 3 or len(body) < 15:
            flash("Tip title must be 3+ characters and tip text at least 15 characters.", "error")
        else:
            db.execute("INSERT INTO daily_tips(title,body,category) VALUES(?,?,?)", (title,body,category))
            db.commit(); flash("Tip published to your tip library.", "success")
        return redirect(url_for("admin_tips"))
    tips = db.execute("SELECT * FROM daily_tips ORDER BY id DESC").fetchall()
    return render_template("admin_tips.html", tips=tips)

@app.post("/admin/tips/<int:tip_id>/toggle")
@admin_required
def admin_tip_toggle(tip_id):
    db = get_db(); tip = db.execute("SELECT published FROM daily_tips WHERE id=?", (tip_id,)).fetchone()
    if not tip: abort(404)
    db.execute("UPDATE daily_tips SET published=? WHERE id=?", (0 if tip["published"] else 1, tip_id)); db.commit()
    flash("Tip visibility updated.", "success"); return redirect(url_for("admin_tips"))

@app.post("/admin/tips/<int:tip_id>/delete")
@admin_required
def admin_tip_delete(tip_id):
    db = get_db(); db.execute("DELETE FROM daily_tips WHERE id=?", (tip_id,)); db.commit()
    flash("Tip deleted.", "success"); return redirect(url_for("admin_tips"))

@app.route("/admin/resources", methods=["GET", "POST"])
@admin_required
def admin_resources():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip(); description = request.form.get("description", "").strip()
        url = request.form.get("url", "").strip(); category = request.form.get("category", "Templates").strip() or "Templates"
        parsed = urlparse(url)
        if len(title) < 3 or parsed.scheme not in {"https", "http"} or not parsed.netloc:
            flash("Enter a title and a valid http/https resource URL.", "error")
        else:
            db.execute("INSERT INTO resources(title,description,url,category) VALUES(?,?,?,?)", (title,description,url,category)); db.commit()
            flash("Resource added to the learning library.", "success")
        return redirect(url_for("admin_resources"))
    resources = db.execute("SELECT * FROM resources ORDER BY id DESC").fetchall()
    return render_template("admin_resources.html", resources=resources)

@app.post("/admin/resources/<int:resource_id>/toggle")
@admin_required
def admin_resource_toggle(resource_id):
    db = get_db(); item = db.execute("SELECT published FROM resources WHERE id=?", (resource_id,)).fetchone()
    if not item: abort(404)
    db.execute("UPDATE resources SET published=? WHERE id=?", (0 if item["published"] else 1, resource_id)); db.commit()
    flash("Resource visibility updated.", "success"); return redirect(url_for("admin_resources"))

@app.post("/admin/resources/<int:resource_id>/delete")
@admin_required
def admin_resource_delete(resource_id):
    db = get_db(); db.execute("DELETE FROM resources WHERE id=?", (resource_id,)); db.commit()
    flash("Resource deleted.", "success"); return redirect(url_for("admin_resources"))

@app.route("/about")
def about():
    return render_template("simple_page.html", title="About Digital Udaan", body="Digital Udaan helps small businesses build practical digital marketing skills through short lessons, actionable notes and real-world exercises.")

@app.route("/privacy")
def privacy():
    return render_template(
        "simple_page.html",
        title=get_setting("privacy_title", "Privacy Policy"),
        body=get_setting("privacy_body", "This privacy policy should be reviewed and customized by the site owner before public launch.")
    )

@app.route("/terms")
def terms():
    return render_template(
        "simple_page.html",
        title=get_setting("terms_title", "Terms & Conditions"),
        body=get_setting("terms_body", "These terms and conditions should be reviewed and customized by the site owner before public launch.")
    )

@app.route("/admin/feedback")
@admin_required
def admin_feedback():
    messages = get_db().execute(
        "SELECT id, name, email, message, created_at FROM feedback ORDER BY id DESC"
    ).fetchall()
    return render_template("admin_feedback.html", messages=messages)

@app.route("/admin/legal", methods=["GET", "POST"])
@admin_required
def admin_legal():
    db = get_db()
    defaults = {
        "privacy_title": "Privacy Policy",
        "privacy_body": "Add your privacy policy here.",
        "terms_title": "Terms & Conditions",
        "terms_body": "Add your terms and conditions here.",
    }
    if request.method == "POST":
        values = {key: request.form.get(key, "").strip() for key in defaults}
        if any(not value for value in values.values()):
            flash("Please fill in all four fields.", "error")
        elif any(len(value) > 30000 for value in values.values()):
            flash("Policy text is too long (maximum 30,000 characters per field).", "error")
        else:
            for key, value in values.items():
                db.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, value),
                )
            db.commit()
            flash("Privacy Policy and Terms & Conditions saved.", "success")
            return redirect(url_for("admin_legal"))
    values = {key: get_setting(key, default) for key, default in defaults.items()}
    if request.method == "POST" and any(not request.form.get(key, "").strip() for key in defaults):
        values = {key: request.form.get(key, "") for key in defaults}
    return render_template("admin_legal.html", **values)

@app.errorhandler(403)
def forbidden(_error):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403

@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", code=404, message="We could not find that page."), 404

@app.errorhandler(413)
def too_large(_error):
    return render_template("error.html", code=413, message="That upload is too large."), 413

if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(debug=debug)
