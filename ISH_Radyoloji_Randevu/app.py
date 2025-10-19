# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import json
from db import get_conn, init_db_and_seed

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "dev-secret"

# DB şema + seed (proje açılır açılmaz güvenli)
init_db_and_seed()

# Basit kullanıcılar (şimdilik bellek içi)
VALID_USERS = {
    "admin":  {"password": "admin",  "role": "admin"},
    "dr":     {"password": "1234",   "role": "doktor"},
    "hemsire":{"password": "1234",   "role": "goruntule"},
    "teknik": {"password": "1234",   "role": "goruntule"},
}

def login_required(view):
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper

@app.template_filter("tr_date")
def tr_date(iso_yyyy_mm_dd: str) -> str:
    try:
        d = datetime.strptime(iso_yyyy_mm_dd, "%Y-%m-%d")
        return d.strftime("%d.%m.%Y")
    except Exception:
        return iso_yyyy_mm_dd

def list_procedures():
    with get_conn() as con:
        return con.execute(
            "SELECT id, name, default_duration_min, requirements_json "
            "FROM procedure_types WHERE active=1 ORDER BY name"
        ).fetchall()

def list_day_appointments(day_str):
    with get_conn() as con:
        return con.execute("""
            SELECT a.id, a.patient_name, a.tc_kimlik, a.date, a.duration_min,
                   a.anticoagulant, a.antiplatelet, a.anesthesia, a.med_note,
                   a.custom_proc_name,
                   pt.name AS proc_name
            FROM appointments a
            JOIN procedure_types pt ON pt.id = a.procedure_type_id
            WHERE a.date = ?
            ORDER BY a.id DESC
        """, (day_str,)).fetchall()

@app.route("/")
def root():
    return redirect(url_for("agenda"))

# ---------- Auth ----------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        if u in VALID_USERS and VALID_USERS[u]["password"] == p:
            session["user"] = u
            session["role"] = VALID_USERS[u]["role"]
            flash("Giriş başarılı", "success")
            return redirect(url_for("agenda"))
        flash("Hatalı kullanıcı adı/şifre", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- Randevu Görüntüleme ----------
@app.route("/agenda")
@login_required
def agenda():
    day_iso = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    appts = list_day_appointments(day_iso)
    return render_template("agenda.html", day_iso=day_iso, appts=appts, user=session.get("user",""))

# Basit arama (TC veya isim içeren)
@app.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    rows = []
    if q:
        like = f"%{q}%"
        with get_conn() as con:
            rows = con.execute("""
                SELECT a.id, a.patient_name, a.tc_kimlik, a.date, a.duration_min,
                       pt.name AS proc_name
                FROM appointments a
                JOIN procedure_types pt ON pt.id = a.procedure_type_id
                WHERE a.patient_name LIKE ? OR a.tc_kimlik LIKE ?
                ORDER BY a.date DESC, a.id DESC
            """, (like, like)).fetchall()
    return render_template("search.html", q=q, rows=rows)

# ---------- Yeni Randevu ----------
@app.route("/new", methods=["GET","POST"])
@login_required
def new():
    day_iso = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    procs = list_procedures()
    if request.method == "POST":
        patient = request.form.get("patient_name","").strip()
        tcno    = (request.form.get("tc_kimlik","") or "").strip()
        proc_id = int(request.form.get("procedure_type_id"))
        duration = int(request.form.get("duration_min"))
        antico = 1 if request.form.get("anticoagulant") == "on" else 0
        antip  = 1 if request.form.get("antiplatelet") == "on" else 0
        anes   = 1 if request.form.get("anesthesia") == "on" else 0
        med_note = request.form.get("med_note","").strip()
        custom_proc_name = (request.form.get("custom_proc_name","") or "").strip()

        checked = request.form.getlist("req_checked")
        req_json = json.dumps({"checked": checked}, ensure_ascii=False)

        if not patient:
            flash("Hasta adı zorunludur.", "warning")
            return redirect(url_for("new", date=day_iso))

        with get_conn() as con:
            con.execute("""
                INSERT INTO appointments
                 (patient_name, tc_kimlik, procedure_type_id, duration_min, date,
                  anticoagulant, antiplatelet, anesthesia, med_note, req_checks_json,
                  doctor_username, custom_proc_name)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (patient, tcno, proc_id, duration, day_iso,
                  antico, antip, anes, med_note, req_json,
                  session["user"], custom_proc_name if custom_proc_name else None))
            con.commit()

        flash("Randevu kaydedildi.", "success")
        return redirect(url_for("agenda", date=day_iso))

    return render_template("new.html", day_iso=day_iso, procs=procs, user=session.get("user",""))

# ---------- Silme ----------
@app.route("/delete/<int:appt_id>", methods=["POST"])
@login_required
def delete_appt(appt_id: int):
    # goruntule rolü silemesin
    if session.get("role") == "goruntule":
        flash("Bu kullanıcı randevu silemez.", "warning")
        return redirect(url_for("agenda"))

    day_iso = request.form.get("day_iso") or datetime.now().strftime("%Y-%m-%d")
    with get_conn() as con:
        con.execute("DELETE FROM appointments WHERE id = ?", (appt_id,))
        con.commit()
    flash("Randevu silindi.", "success")
    return redirect(url_for("agenda", date=day_iso))

# ---------- Admin Paneli (çok basit görüntüleme) ----------
@app.route("/admin")
@login_required
def admin_panel():
    if session.get("role") != "admin":
        flash("Admin yetkisi gerekli.", "danger")
        return redirect(url_for("agenda"))

    with get_conn() as con:
        users = []
        procs = con.execute("SELECT id,name,default_duration_min,active FROM procedure_types ORDER BY name").fetchall()
    return render_template("admin_panel.html", procs=procs, users=users)
