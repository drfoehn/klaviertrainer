"""
Klaviertrainer – Flask Backend
SQLite + file-based PDF storage, per-user auth & favorites
Admin-only user management, public registration disabled
"""

import os, sqlite3, hashlib, secrets
from pathlib import Path
from functools import wraps
from flask import (Flask, request, jsonify, session, send_file,
                   render_template, redirect, url_for, abort, flash)
from werkzeug.utils import secure_filename

# ── Config ───────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DB_PATH    = BASE_DIR / "klaviertrainer.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_PDF_MB  = 30
ALLOWED_EXT = {".pdf"}

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["MAX_CONTENT_LENGTH"] = MAX_PDF_MB * 1024 * 1024


# ── Database ──────────────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT    UNIQUE NOT NULL,
            pw_hash   TEXT    NOT NULL,
            pw_salt   TEXT    NOT NULL,
            is_admin  INTEGER DEFAULT 0,
            created   INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS favorites (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title      TEXT    NOT NULL,
            has_pdf    INTEGER DEFAULT 0,
            pdf_name   TEXT,
            added      INTEGER DEFAULT (strftime('%s','now')),
            UNIQUE(user_id, title)
        );

        CREATE TABLE IF NOT EXISTS pdfs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            fav_id     INTEGER REFERENCES favorites(id) ON DELETE SET NULL,
            filename   TEXT    NOT NULL,
            orig_name  TEXT    NOT NULL,
            size_bytes INTEGER,
            uploaded   INTEGER DEFAULT (strftime('%s','now'))
        );
        """)


# ── Auth helpers ──────────────────────────────────────────────────────
def hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000).hex()


def create_user(username: str, password: str, is_admin: bool = False) -> bool:
    """Create a user. Returns True on success, False if username taken."""
    if len(username) < 3 or len(password) < 6:
        raise ValueError("Username min 3 chars, password min 6 chars")
    salt = secrets.token_hex(16)
    pw_hash = hash_pw(password, salt)
    try:
        with get_db() as db:
            db.execute(
                "INSERT INTO users (username, pw_hash, pw_salt, is_admin) VALUES (?,?,?,?)",
                (username, pw_hash, salt, 1 if is_admin else 0)
            )
        return True
    except sqlite3.IntegrityError:
        return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            if request.is_json:
                return jsonify({"error": "Nicht eingeloggt"}), 401
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login_page"))
        if not session.get("is_admin"):
            abort(403)
        return f(*args, **kwargs)
    return decorated


def current_user():
    return session.get("user_id"), session.get("username")


# ── CLI helper: create first admin ───────────────────────────────────
def cli_create_admin(username: str, password: str):
    """Called from command line to bootstrap first admin user."""
    init_db()
    try:
        ok = create_user(username, password, is_admin=True)
        if ok:
            print(f"✓ Admin '{username}' erstellt.")
        else:
            print(f"✗ Benutzername '{username}' bereits vergeben.")
    except ValueError as e:
        print(f"✗ Fehler: {e}")


# ── Pages ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    return render_template("index.html", username=session.get("username"),
                           is_admin=session.get("is_admin", False))


@app.route("/login")
def login_page():
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("login.html")


# ── Admin Panel ───────────────────────────────────────────────────────
@app.route("/admin")
@admin_required
def admin_panel():
    with get_db() as db:
        users = db.execute(
            "SELECT u.id, u.username, u.is_admin, u.created, "
            "COUNT(DISTINCT f.id) as fav_count, "
            "COUNT(DISTINCT p.id) as pdf_count "
            "FROM users u "
            "LEFT JOIN favorites f ON f.user_id=u.id "
            "LEFT JOIN pdfs p ON p.user_id=u.id "
            "GROUP BY u.id ORDER BY u.created DESC"
        ).fetchall()
    return render_template("admin.html",
                           users=[dict(u) for u in users],
                           current_user_id=session["user_id"])


@app.route("/admin/create", methods=["POST"])
@admin_required
def admin_create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    is_admin = bool(request.form.get("is_admin"))
    error = None

    if len(username) < 3:
        error = "Benutzername muss mindestens 3 Zeichen haben."
    elif len(password) < 6:
        error = "Passwort muss mindestens 6 Zeichen haben."
    else:
        ok = create_user(username, password, is_admin)
        if not ok:
            error = f"Benutzername '{username}' ist bereits vergeben."

    if error:
        flash(error, "error")
    else:
        flash(f"✓ User '{username}' erstellt.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/delete/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session["user_id"]:
        flash("Du kannst dich nicht selbst löschen.", "error")
        return redirect(url_for("admin_panel"))

    # Delete uploaded PDF files
    user_dir = UPLOAD_DIR / str(user_id)
    if user_dir.exists():
        import shutil
        shutil.rmtree(user_dir)

    with get_db() as db:
        db.execute("DELETE FROM users WHERE id=?", (user_id,))

    flash("User gelöscht.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reset-password/<int:user_id>", methods=["POST"])
@admin_required
def admin_reset_password(user_id):
    new_password = request.form.get("password", "")
    if len(new_password) < 6:
        flash("Passwort muss mindestens 6 Zeichen haben.", "error")
        return redirect(url_for("admin_panel"))

    salt = secrets.token_hex(16)
    pw_hash = hash_pw(new_password, salt)
    with get_db() as db:
        db.execute("UPDATE users SET pw_hash=?, pw_salt=? WHERE id=?",
                   (pw_hash, salt, user_id))
    flash("Passwort zurückgesetzt.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/toggle-admin/<int:user_id>", methods=["POST"])
@admin_required
def admin_toggle_admin(user_id):
    if user_id == session["user_id"]:
        flash("Du kannst deinen eigenen Admin-Status nicht ändern.", "error")
        return redirect(url_for("admin_panel"))
    with get_db() as db:
        db.execute("UPDATE users SET is_admin = 1 - is_admin WHERE id=?", (user_id,))
    flash("Admin-Status geändert.", "success")
    return redirect(url_for("admin_panel"))


# ── Auth API ──────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    # Public registration disabled – admin only
    return jsonify({"error": "Registrierung deaktiviert. Bitte Admin kontaktieren."}), 403


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    with get_db() as db:
        row = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()

    if not row or hash_pw(password, row["pw_salt"]) != row["pw_hash"]:
        return jsonify({"error": "Ungültige Anmeldedaten"}), 401

    session.permanent = True
    session["user_id"]  = row["id"]
    session["username"] = row["username"]
    session["is_admin"] = bool(row["is_admin"])
    return jsonify({"ok": True, "username": row["username"],
                    "is_admin": bool(row["is_admin"])})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/me")
def me():
    if "user_id" not in session:
        return jsonify({"loggedIn": False})
    return jsonify({"loggedIn": True, "username": session["username"],
                    "is_admin": session.get("is_admin", False)})


# ── Favorites API ─────────────────────────────────────────────────────
@app.route("/api/favorites", methods=["GET"])
@login_required
def get_favorites():
    uid, _ = current_user()
    with get_db() as db:
        rows = db.execute(
            "SELECT id, title, has_pdf, pdf_name, added FROM favorites "
            "WHERE user_id=? ORDER BY added DESC", (uid,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/favorites", methods=["POST"])
@login_required
def add_favorite():
    uid, _ = current_user()
    data  = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Kein Titel"}), 400
    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM favorites WHERE user_id=? AND title=?", (uid, title)
        ).fetchone()
        if existing:
            return jsonify({"ok": True, "id": existing["id"], "existing": True})
        cur = db.execute(
            "INSERT INTO favorites (user_id, title) VALUES (?,?)", (uid, title)
        )
    return jsonify({"ok": True, "id": cur.lastrowid})


@app.route("/api/favorites/<int:fav_id>", methods=["DELETE"])
@login_required
def delete_favorite(fav_id):
    uid, _ = current_user()
    with get_db() as db:
        row = db.execute("SELECT pdf_name FROM favorites WHERE id=? AND user_id=?",
                         (fav_id, uid)).fetchone()
        if not row:
            return jsonify({"error": "Nicht gefunden"}), 404
        if row["pdf_name"]:
            pdf_path = UPLOAD_DIR / str(uid) / row["pdf_name"]
            if pdf_path.exists():
                pdf_path.unlink()
        db.execute("DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, uid))
    return jsonify({"ok": True})


# ── PDF API ───────────────────────────────────────────────────────────
@app.route("/api/pdf/upload", methods=["POST"])
@login_required
def upload_pdf():
    uid, _ = current_user()
    title  = request.form.get("title", "").strip()

    if "file" not in request.files:
        return jsonify({"error": "Keine Datei"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Kein Dateiname"}), 400
    if Path(f.filename).suffix.lower() not in ALLOWED_EXT:
        return jsonify({"error": "Nur PDF erlaubt"}), 400

    user_dir = UPLOAD_DIR / str(uid)
    user_dir.mkdir(exist_ok=True)
    safe_name   = secure_filename(f.filename)
    unique_name = f"{secrets.token_hex(6)}_{safe_name}"
    dest = user_dir / unique_name
    f.save(dest)
    size = dest.stat().st_size

    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM favorites WHERE user_id=? AND title=?",
            (uid, title or safe_name)
        ).fetchone()
        if existing:
            fav_id = existing["id"]
            old = db.execute("SELECT pdf_name FROM favorites WHERE id=?",
                             (fav_id,)).fetchone()
            if old and old["pdf_name"] and old["pdf_name"] != unique_name:
                old_path = user_dir / old["pdf_name"]
                if old_path.exists():
                    old_path.unlink()
            db.execute("UPDATE favorites SET has_pdf=1, pdf_name=? WHERE id=?",
                       (unique_name, fav_id))
        else:
            cur = db.execute(
                "INSERT INTO favorites (user_id, title, has_pdf, pdf_name) VALUES (?,?,1,?)",
                (uid, title or safe_name, unique_name)
            )
            fav_id = cur.lastrowid

        db.execute(
            "INSERT INTO pdfs (user_id, fav_id, filename, orig_name, size_bytes) "
            "VALUES (?,?,?,?,?)",
            (uid, fav_id, unique_name, f.filename, size)
        )
    return jsonify({"ok": True, "fav_id": fav_id, "filename": unique_name})


@app.route("/api/pdf/<filename>")
@login_required
def serve_pdf(filename):
    uid, _ = current_user()
    safe = secure_filename(filename)
    pdf_path = UPLOAD_DIR / str(uid) / safe
    with get_db() as db:
        row = db.execute(
            "SELECT filename FROM pdfs WHERE user_id=? AND filename=?", (uid, safe)
        ).fetchone()
    if not row or not pdf_path.exists():
        abort(404)
    return send_file(pdf_path, mimetype="application/pdf")


# ── Run ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) == 4 and sys.argv[1] == "create-admin":
        cli_create_admin(sys.argv[2], sys.argv[3])
    else:
        init_db()
        port  = int(os.environ.get("PORT", 8080))
        debug = os.environ.get("FLASK_DEBUG", "0") == "1"
        app.run(host="0.0.0.0", port=port, debug=debug)
