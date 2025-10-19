from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, date, timedelta
import sqlite3, json
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "instance" / "app.db"

app = Flask(__name__)
app.secret_key = "dev-secret"           # prod’da env’den okuyun

# ---------------------- DB helpers ----------------------
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with get_conn() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY,
          username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'doctor',   -- doctor | nurse | tech | admin
          is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS procedure_types(
          id INTEGER PRIMARY KEY,
          name TEXT UNIQUE NOT NULL,
          default_duration_min INTEGER NOT NULL DEFAULT 60,
          requirements_json TEXT,
          active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS appointments(
          id INTEGER PRIMARY KEY,
          tc_no TEXT,
          patient_name TEXT NOT NULL,
          procedure_type_id INTEGER NOT NULL,
          custom_proc_name TEXT,
          duration_min INTEGER NOT NULL DEFAULT 60,
          day_iso TEXT NOT NULL,                 -- YYYY-MM-DD (saat yok)
          anticoagulant INTEGER NOT NULL DEFAULT 0,
          antiplatelet INTEGER NOT NULL DEFAULT 0,
          anesthesia INTEGER NOT NULL DEFAULT 0,
          med_note TEXT,
          prep_json TEXT,                        -- lab/ hazırlık hatırlatmaları (opsiyonel)
          doctor_username TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_appt_day ON appointments(day_iso);
        """)
        con.commit()

def ensure_first_admin():
    """Kullanıcı yoksa otomatik admin ekle."""
    with get_conn() as con:
        n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if n == 0:
            con.execute(
                "INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                ("admin", generate_password_hash("admin123"), "admin")
            )
            con.commit()

def list_procedures():
    with get_conn() as con:
        rows = con.execute(
            "SELECT id, name, default_duration_min, requirements_json FROM procedure_types WHERE active=1 ORDER BY name"
        ).fetchall()
    return rows

def load_day(day_iso:str):
    with get_conn() as con:
        rows = con.execute("""
          SELECT a.*, pt.name AS proc_name
          FROM appointments a
          JOIN procedure_types pt ON pt.id = a.procedure_type_id
          WHERE a.day_iso = ?
          ORDER BY a.id DESC
        """, (day_iso,)).fetchall()
    return rows

# ---------------------- boot ----------------------
init_db()
ensure_first_admin()

# ---------------------- auth helpers ----------------------
def login_required(view):
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper

def role_required(*roles):
    def decorator(view):
        def wrapper(*args, **kwargs):
            u = session.get("user")
            r = session.get("role")
            if not u:
                return redirect(url_for("login"))
            if roles and r not in roles:
                flash("Bu sayfa için yetkiniz yok.", "warning")
                return redirect(url_for("agenda"))
            return view(*args, **kwargs)
        wrapper.__name__ = view.__name__
        return wrapper
    return decorator

# ---------------------- filters ----------------------
@app.template_filter("tr_date")
def tr_date(iso_yyyy_mm_dd: str) -> str:
    try:
        d = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d")
        return d.strftime("%d.%m.%Y")
    except Exception:
        return iso_yyyy_mm_dd

# ---------------------- routes: auth ----------------------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        with get_conn() as con:
            row = con.execute("SELECT * FROM users WHERE username=? AND is_active=1", (u,)).fetchone()
        if row and check_password_hash(row["password_hash"], p):
            session["user"] = row["username"]
            session["role"] = row["role"]
            return redirect(url_for("agenda"))
        flash("Hatalı kullanıcı adı/şifre.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------- routes: calendar ----------------------
@app.route("/")
def root():
    return redirect(url_for("month"))

@app.route("/month")
@login_required
def month():
    """Ay görünümü: YYYY-MM param veya bugünün ayı."""
    ym = request.args.get("month")  # "YYYY-MM"
    today = date.today()
    if ym:
        year, mon = map(int, ym.split("-"))
        first = date(year, mon, 1)
    else:
        first = date(today.year, today.month, 1)

    # ayın günleri + baş/son doldurma
    start_wd = (first.weekday() + 1) % 7  # pzt=0 -> pazar=0 dönüşümü
    days_in_month = (date(first.year + first.month//12, (first.month % 12)+1, 1) - timedelta(days=1)).day
    grid = []
    cur = first - timedelta(days=start_wd)
    for _ in range(6):  # 6 hafta satırı
        week = []
        for _ in range(7):
            week.append(cur)
            cur += timedelta(days=1)
        grid.append(week)

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (date(first.year + first.month//12, (first.month % 12)+1, 1))

    return render_template("month.html",
                           first=first, grid=grid, today=today,
                           prev_month=prev_month.strftime("%Y-%m"),
                           next_month=next_month.strftime("%Y-%m"))

@app.route("/agenda")
@login_required
def agenda():
    day_iso = request.args.get("date") or date.today().strftime("%Y-%m-%d")
    appts = load_day(day_iso)
    return render_template("agenda.html", day_iso=day_iso, appts=appts, user=session.get("user",""))

# ---------------------- routes: search ----------------------
@app.route("/search")
@login_required
def search():
    q = request.args.get("q","").strip()
    rows = []
    if q:
        with get_conn() as con:
            rows = con.execute("""
              SELECT a.*, pt.name AS proc_name
              FROM appointments a
              JOIN procedure_types pt ON pt.id = a.procedure_type_id
              WHERE a.tc_no LIKE ? OR a.patient_name LIKE ?
              ORDER BY a.day_iso DESC, a.id DESC
            """, (f"%{q}%", f"%{q}%")).fetchall()
    return render_template("search.html", q=q, rows=rows)

# ---------------------- routes: new / delete ----------------------
@app.route("/new", methods=["GET","POST"])
@login_required
def new():
    day_iso = request.args.get("date") or date.today().strftime("%Y-%m-%d")
    procs = list_procedures()

    if request.method == "POST":
        f = request.form
        patient = f.get("patient_name","").strip()
        tc_no  = f.get("tc_no","").strip()
        proc_id = int(f.get("procedure_type_id"))
        duration = int(f.get("duration_min") or 60)
        antico = 1 if f.get("anticoagulant")=="on" else 0
        antiag = 1 if f.get("antiplatelet")=="on" else 0
        anes   = 1 if f.get("anesthesia")=="on" else 0
        med_note = f.get("med_note","").strip()
        custom_proc = (f.get("custom_proc_name","") or "").strip()

        # opsiyonel hazırlık/lab notlarını tek json alanında saklayalım
        prep = {
            "lab": f.get("prep_lab","").strip(),
            "hazirlik": f.get("prep_prep","").strip()
        }

        with get_conn() as con:
            con.execute("""
              INSERT INTO appointments
              (tc_no, patient_name, procedure_type_id, custom_proc_name, duration_min, day_iso,
               anticoagulant, antiplatelet, anesthesia, med_note, prep_json, doctor_username, created_at)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (tc_no, patient, proc_id, custom_proc, duration, day_iso,
                  antico, antiag, anes, med_note, json.dumps(prep, ensure_ascii=False),
                  session["user"], datetime.now().isoformat(timespec="seconds")))
            con.commit()
        flash("Randevu kaydedildi.", "success")
        return redirect(url_for("agenda", date=day_iso))

    return render_template("new.html", day_iso=day_iso, procs=procs, user=session.get("user",""))

@app.route("/delete/<int:appt_id>", methods=["POST"])
@login_required
def delete_appt(appt_id:int):
    """Form-POST ile sil. Ajanda’dan çalışır."""
    day_iso = request.form.get("day_iso") or date.today().strftime("%Y-%m-%d")
    with get_conn() as con:
        con.execute("DELETE FROM appointments WHERE id=?", (appt_id,))
        con.commit()
    flash("Randevu silindi.", "success")
    return redirect(url_for("agenda", date=day_iso))

# ---------------------- routes: admin ----------------------
@app.route("/admin", methods=["GET","POST"])
@role_required("admin")
def admin_panel():
    """Kullanıcı yönetimi (listele/ekle/şifre sıfırla/aktiflik/rol)."""
    msg = None
    if request.method == "POST":
        action = request.form.get("action")
        with get_conn() as con:
            if action == "add":
                u = request.form["username"].strip()
                p = request.form["password"].strip()
                r = request.form.get("role","doctor")
                if not u or not p:
                    flash("Kullanıcı adı ve şifre zorunlu.", "warning")
                else:
                    try:
                        con.execute("INSERT INTO users(username,password_hash,role) VALUES (?,?,?)",
                                    (u, generate_password_hash(p), r))
                        con.commit(); flash("Kullanıcı eklendi.","success")
                    except sqlite3.IntegrityError:
                        flash("Bu kullanıcı zaten var.","danger")
            elif action == "reset":
                uid = int(request.form["id"])
                np = request.form["new_password"].strip()
                con.execute("UPDATE users SET password_hash=? WHERE id=?",
                            (generate_password_hash(np), uid))
                con.commit(); flash("Şifre güncellendi.","success")
            elif action == "role":
                uid = int(request.form["id"])
                r = request.form.get("role","doctor")
                con.execute("UPDATE users SET role=? WHERE id=?", (r, uid))
                con.commit(); flash("Rol güncellendi.","success")
            elif action == "toggle":
                uid = int(request.form["id"])
                con.execute("UPDATE users SET is_active=1-is_active WHERE id=?", (uid,))
                con.commit(); flash("Aktiflik değiştirildi.","success")

    with get_conn() as con:
        users = con.execute("SELECT id,username,role,is_active FROM users ORDER BY username").fetchall()
    return render_template("admin_panel.html", users=users)

# ---------------------- run (yerel geliştirme için) ----------------------
if __name__ == "__main__":
    app.run(debug=True, port=5001)
