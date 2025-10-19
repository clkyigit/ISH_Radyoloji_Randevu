from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import json, os

# db.py dosyanız aynı dizinde olmalı
from db import get_conn, init_db, seed_procedures

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# Veritabanını hazırla
init_db()
seed_procedures()

# Basit kullanıcılar (opsiyon: users.json ile override)
VALID_USERS = {"dr": {"password": "1234"}}
try:
    with open(os.path.join(os.path.dirname(__file__), "users.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict) and data:
            VALID_USERS = data
except FileNotFoundError:
    pass

# ---- Jinja yardımcıları
@app.context_processor
def inject_session_user():
    return {"session_user": session.get("user")}

@app.template_filter("tr_date")
def tr_date(iso_yyyy_mm_dd: str) -> str:
    try:
        d = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d")
        return d.strftime("%d.%m.%Y")
    except Exception:
        return iso_yyyy_mm_dd

# ---- Auth
def login_required(view):
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        if u in VALID_USERS and VALID_USERS[u].get("password") == p:
            session["user"] = u
            return redirect(url_for("agenda"))
        flash("Hatalı kullanıcı adı/şifre", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---- Yardımcı sorgular
def list_procedures():
    with get_conn() as con:
        rows = con.execute(
            "SELECT id, name, default_duration_min, requirements_json "
            "FROM procedure_types WHERE active=1 ORDER BY name"
        ).fetchall()
    return rows

def list_day_appointments(day_str: str):
    with get_conn() as con:
        rows = con.execute("""
            SELECT a.id, a.patient_name, a.date, a.duration_min,
                   a.anticoagulant, a.antiplatelet, a.anesthesia, a.med_note,
                   a.custom_proc_name,
                   pt.name AS proc_name
            FROM appointments a
            JOIN procedure_types pt ON pt.id = a.procedure_type_id
            WHERE a.date = ?
            ORDER BY a.id DESC
        """, (day_str,)).fetchall()
    return rows

# ---- Rotalar
@app.route("/")
def root():
    return redirect(url_for("agenda"))

@app.route("/agenda")
@login_required
def agenda():
    day_iso = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    appts = list_day_appointments(day_iso)
    return render_template("agenda.html", day_iso=day_iso, appts=appts, user=session.get("user", ""))

@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    day_iso = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    procs = list_procedures()

    if request.method == "POST":
        patient = (request.form.get("patient_name") or "").strip()
        proc_id = int(request.form.get("procedure_type_id"))
        duration = int(request.form.get("duration_min"))
        antico = 1 if request.form.get("anticoagulant") == "on" else 0
        antip  = 1 if request.form.get("antiplatelet") == "on" else 0
        anes   = 1 if request.form.get("anesthesia") == "on" else 0
        med_note = (request.form.get("med_note") or "").strip()
        custom_proc_name = (request.form.get("custom_proc_name") or "").strip()

        checked = request.form.getlist("req_checked")
        req_json = json.dumps({"checked": checked}, ensure_ascii=False)

        if not patient:
            flash("Hasta adı zorunludur.", "warning")
            return redirect(url_for("new", date=day_iso))

        with get_conn() as con:
            con.execute("""
                INSERT INTO appointments
                  (patient_name, procedure_type_id, duration_min, date,
                   anticoagulant, antiplatelet, anesthesia, med_note,
                   req_checks_json, doctor_username, custom_proc_name)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                patient, proc_id, duration, day_iso,
                antico, antip, anes, med_note,
                req_json, session.get("user", ""),
                custom_proc_name if custom_proc_name else None
            ))
            con.commit()

        flash("Randevu kaydedildi.", "success")
        return redirect(url_for("agenda", date=day_iso))

    return render_template("new.html", day_iso=day_iso, procs=procs, user=session.get("user", ""))

@app.route("/delete/<int:appt_id>", methods=["POST"])
@login_required
def delete_appt(appt_id: int):
    day_iso = request.form.get("day_iso")
    with get_conn() as con:
        con.execute("DELETE FROM appointments WHERE id = ?", (appt_id,))
        con.commit()
    flash("Randevu silindi.", "success")
    return redirect(url_for("agenda", date=day_iso or datetime.now().strftime("%Y-%m-%d")))

# ---- ARAMA (HASTA ADINA GÖRE)
@app.route("/search", methods=["GET"])
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    results = []
    if q:
        with get_conn() as con:
            results = con.execute("""
                SELECT a.id, a.patient_name, a.date, a.duration_min,
                       a.anticoagulant, a.antiplatelet, a.anesthesia, a.med_note,
                       a.custom_proc_name,
                       pt.name AS proc_name
                FROM appointments a
                JOIN procedure_types pt ON pt.id = a.procedure_type_id
                WHERE a.patient_name LIKE ?
                ORDER BY a.date DESC, a.id DESC
            """, (f"%{q}%",)).fetchall()
    return render_template("search.html", q=q, results=results, user=session.get("user", ""))

# ---- Sağlık/Teşhis uçları
@app.route("/healthz")
def healthz():
    try:
        with get_conn() as con:
            con.execute("SELECT 1")
        return {"ok": True}, 200
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500

@app.route("/diag")
def diag():
    from db import DB_PATH, INSTANCE_DIR
    try:
        info = {
            "pwd": os.getcwd(),
            "app_root_path": app.root_path,
            "db_dir": str(INSTANCE_DIR),
            "db_path": str(DB_PATH),
            "db_exists": os.path.exists(DB_PATH),
            "templates_dir": os.path.join(app.root_path, "templates"),
            "static_dir": os.path.join(app.root_path, "static"),
            "has_login_html": os.path.exists(os.path.join(app.root_path, "templates", "login.html")),
            "has_agenda_html": os.path.exists(os.path.join(app.root_path, "templates", "agenda.html")),
            "has_search_html": os.path.exists(os.path.join(app.root_path, "templates", "search.html")),
            "session_user": session.get("user"),
        }
        with get_conn() as con:
            con.execute("SELECT 1").fetchone()
        info["db_ok"] = True
        return info, 200
    except Exception as e:
        return {"error": str(e)}, 500
