from .db import get_conn, init_db, seed_procedures
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import json
from .db import get_conn, init_db, seed_procedures

app = Flask(__name__, template_folder="../templates", static_folder="../static")
app.secret_key = "dev-secret"

init_db()
seed_procedures()

VALID_USERS = {"dr": {"password": "1234"}}

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

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username","").strip()
        p = request.form.get("password","").strip()
        if u in VALID_USERS and VALID_USERS[u]["password"] == p:
            session["user"] = u
            return redirect(url_for("agenda"))
        flash("Hatalı kullanıcı adı/şifre", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

def list_procedures():
    with get_conn() as con:
        rows = con.execute(
            "SELECT id, name, default_duration_min, requirements_json "
            "FROM procedure_types WHERE active=1 ORDER BY name"
        ).fetchall()
    return rows

def list_day_appointments(day_str):
    with get_conn() as con:
        rows = con.execute("""
            SELECT a.id, a.patient_name, a.patient_tc, a.date, a.duration_min,
                   a.anticoagulant, a.antiplatelet, a.anesthesia,
                   a.med_note, a.lab_notes, a.prep_notes,
                   a.custom_proc_name,
                   pt.name AS proc_name
            FROM appointments a
            JOIN procedure_types pt ON pt.id = a.procedure_type_id
            WHERE a.date = ?
            ORDER BY a.id DESC
        """, (day_str,)).fetchall()
    return rows

@app.route("/")
def root():
    return redirect(url_for("agenda"))

@app.route("/agenda")
@login_required
def agenda():
    day_iso = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    appts = list_day_appointments(day_iso)
    return render_template("agenda.html", day_iso=day_iso, appts=appts, user=session["user"])

@app.route("/new", methods=["GET","POST"])
@login_required
def new():
    day_iso = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")
    procs = list_procedures()
    if request.method == "POST":
        patient = request.form.get("patient_name","").strip()
        patient_tc = (request.form.get("patient_tc","") or "").strip()
        proc_id = int(request.form.get("procedure_type_id"))
        duration = int(request.form.get("duration_min"))
        antico = 1 if request.form.get("anticoagulant") == "on" else 0
        antip  = 1 if request.form.get("antiplatelet") == "on" else 0
        anes   = 1 if request.form.get("anesthesia") == "on" else 0
        med_note = request.form.get("med_note","").strip()
        lab_notes = request.form.get("lab_notes","").strip()
        prep_notes = request.form.get("prep_notes","").strip()
        custom_proc_name = (request.form.get("custom_proc_name","") or "").strip()

        checked = request.form.getlist("req_checked")
        req_json = json.dumps({"checked": checked}, ensure_ascii=False)

        if not patient or not proc_id or not duration:
            flash("Hasta adı, işlem türü ve süre zorunludur.", "warning")
            return redirect(url_for("new", date=day_iso))

        with get_conn() as con:
            con.execute("""
                INSERT INTO appointments
                  (patient_name, patient_tc, procedure_type_id, duration_min, date,
                   anticoagulant, antiplatelet, anesthesia, med_note,
                   lab_notes, prep_notes, req_checks_json, doctor_username, custom_proc_name)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (patient, patient_tc, proc_id, duration, day_iso,
                  antico, antip, anes, med_note,
                  lab_notes or None, prep_notes or None, req_json, session["user"], custom_proc_name or None))
            con.commit()

        flash("Randevu kaydedildi.", "success")
        return redirect(url_for("agenda", date=day_iso))

    return render_template("new.html", day_iso=day_iso, procs=procs, user=session["user"])

@app.route("/delete/<int:appt_id>", methods=["POST"])
@login_required
def delete_appt(appt_id: int):
    day_iso = request.form.get("day_iso")
    with get_conn() as con:
        con.execute("DELETE FROM appointments WHERE id = ?", (appt_id,))
        con.commit()
    flash("Randevu silindi.", "success")
    return redirect(url_for("agenda", date=day_iso or datetime.now().strftime("%Y-%m-%d")))

# --- TC ile arama ---
@app.route("/search")
@login_required
def search():
    tc = (request.args.get("tc","") or "").strip()
    results = []
    if tc:
        with get_conn() as con:
            results = con.execute("""
                SELECT a.id, a.patient_name, a.patient_tc, a.date,
                       pt.name AS proc_name, a.custom_proc_name, a.anesthesia
                FROM appointments a
                JOIN procedure_types pt ON pt.id = a.procedure_type_id
                WHERE a.patient_tc LIKE ?
                ORDER BY a.date DESC, a.id DESC
            """, (f"%{tc}%",)).fetchall()
    return render_template("search.html", tc=tc, results=results, user=session["user"])

# --- Randevu detayını modal için JSON döndür ---
@app.route("/api/appt/<int:appt_id>")
@login_required
def appt_detail(appt_id: int):
    with get_conn() as con:
        row = con.execute("""
            SELECT a.id, a.patient_name, a.patient_tc, a.date, a.duration_min,
                   a.anticoagulant, a.antiplatelet, a.anesthesia, a.med_note,
                   a.lab_notes, a.prep_notes, a.req_checks_json,
                   a.custom_proc_name, pt.name AS proc_name
            FROM appointments a
            JOIN procedure_types pt ON pt.id = a.procedure_type_id
            WHERE a.id = ?
        """, (appt_id,)).fetchone()
    if not row:
        return jsonify({"error":"not found"}), 404
    data = dict(row)
    # req_checks_json normalize
    try:
        parsed = json.loads(data.get("req_checks_json") or "{}")
    except Exception:
        parsed = {}
    data["req_checks"] = parsed.get("checked", [])
    return jsonify(data)
