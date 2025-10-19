# db.py
import sqlite3, json
from pathlib import Path

# instance/app.db (yerelde ve Render'da kalıcı dizin)
DB_PATH = Path(__file__).resolve().parent / "instance" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT,
  role TEXT NOT NULL DEFAULT 'doktor' -- 'admin' | 'doktor' | 'goruntule'
);

CREATE TABLE IF NOT EXISTS procedure_types (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  default_duration_min INTEGER NOT NULL,
  requirements_json TEXT,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS appointments (
  id INTEGER PRIMARY KEY,
  patient_name TEXT NOT NULL,
  tc_kimlik TEXT,
  procedure_type_id INTEGER NOT NULL,
  duration_min INTEGER NOT NULL,
  date TEXT NOT NULL,           -- YYYY-MM-DD
  anticoagulant INTEGER NOT NULL DEFAULT 0,
  antiplatelet INTEGER NOT NULL DEFAULT 0,
  anesthesia INTEGER NOT NULL DEFAULT 0,
  med_note TEXT,
  req_checks_json TEXT,
  doctor_username TEXT NOT NULL,
  custom_proc_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
"""

SEED_PROCS = [
    ("Karotis stent", 90,  {"checklist": ["DAPT (ASA+Klopidogrel)", "GFR/kontrast notu"]}),
    ("TACE", 120,          {"checklist": ["GFR/Cr", "Bilirubin/INR"]}),
    ("EVAR", 180,          {"checklist": ["DAPT/antiagregan", "Anestezi onayı"]}),
    ("BT akciğer biyopsisi", 60, {"checklist": ["DOAC kesim", "INR ≤1.5, Plt ≥50k"]}),
    ("US karaciğer biyopsisi", 45, {"checklist": ["INR ≤1.5, Plt ≥50k"]}),
    ("US tiroid biyopsisi", 30, {"checklist": []}),
    ("Nefrostomi", 60,     {"checklist": ["INR/Plt", "Antibiyotik"]}),
    ("PTK", 60,            {"checklist": ["INR/Plt", "Antibiyotik"]}),
    ("Drenaj", 45,         {"checklist": ["INR/Plt"]}),
    ("RFA/MWA", 90,        {"checklist": ["INR/Plt", "Sedasyon/Anestezi"]}),
    ("Port kateter", 45,   {"checklist": ["Antiagregan/antikoagülan kontrol"]}),
    ("Biliyer drenaj", 60, {"checklist": ["INR/Plt", "Antibiyotik"]}),
    ("SVK", 90, {"checklist": ["Antiko/antiagregan kontrol"]}),
    ("Anevrizma Onarım", 180, {"checklist": ["Nöro anestezi onayı"]}),
    ("PTA Alt Ekstremite", 120, {"checklist": ["Distal nabız/plan"]}),
    ("Serebral Anjiografi", 90, {"checklist": ["GFR", "Giriş planı"]}),
    ("TARE", 150, {"checklist": ["Radyasyon planlama"]}),
    ("TARE MAA", 150, {"checklist": ["MAA haritalama"]}),
    ("Lenfanjiogram", 75, {"checklist": ["Kontrast alerji"]}),
    ("Diğer (serbest giriş)", 60, {"checklist": []}),
]

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db_and_seed():
    with get_conn() as con:
        con.executescript(SCHEMA)
        # Prosedür yoksa seed et
        cur = con.execute("SELECT COUNT(*) FROM procedure_types")
        if int(cur.fetchone()[0]) == 0:
            for name, dur, req in SEED_PROCS:
                con.execute(
                    "INSERT OR IGNORE INTO procedure_types(name, default_duration_min, requirements_json) VALUES (?,?,?)",
                    (name, dur, json.dumps(req, ensure_ascii=False))
                )
        con.commit()
