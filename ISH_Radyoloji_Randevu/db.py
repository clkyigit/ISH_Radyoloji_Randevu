import sqlite3
import json
import os
import sys
from pathlib import Path

def _app_base_dir() -> Path:
    # EXE/paket/script hepsinde kök klasörü güvenle bul
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR = _app_base_dir()

# ---- DB dizinini belirle ----
# Öncelik: Ortam değişkeni DB_DIR (Render için önerilen)
db_dir_env = os.environ.get("DB_DIR")
if db_dir_env:
    INSTANCE_DIR = Path(db_dir_env)
# Render çalışma ortamında güvenli varsayılan (yazılabilir)
elif os.environ.get("RENDER", "") or os.environ.get("RENDER_SERVICE_ID", ""):
    INSTANCE_DIR = Path("/var/tmp/ir_randevu_instance")
# Geliştirme/Windows için yerel "instance/" klasörü
else:
    INSTANCE_DIR = BASE_DIR / "instance"

INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = INSTANCE_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT,
  pin TEXT
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
  procedure_type_id INTEGER NOT NULL,
  duration_min INTEGER NOT NULL,
  date TEXT NOT NULL,                         -- YYYY-MM-DD
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
  ("Karotis stent", 90,  {"checklist": ["DAPT (ASA + Klopidogrel)", "GFR/kontrast notu", "Son 7 günde plaket/lab"]}),
  ("TACE", 120,          {"checklist": ["GFR/Cr", "Bilirubin/INR", "Antiko/antiagregan gözden geçirme"]}),
  ("EVAR", 180,          {"checklist": ["DAPT/antiagregan", "GFR/kontrast", "Anestezi onayı"]}),
  ("BT akciğer biyopsisi", 60, {"checklist": ["DOAC 48–72h kesim", "INR ≤1.5, Plt ≥50k"]}),
  ("US karaciğer biyopsisi", 45, {"checklist": ["INR ≤1.5, Plt ≥50k", "Antiko/antiagregan kontrol"]}),
  ("US tiroid biyopsisi", 30, {"checklist": ["Antiagregan gözden geçirme"]}),
  ("Nefrostomi", 60,     {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("PTK", 60,            {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("Drenaj", 45,         {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("RFA/MWA", 90,        {"checklist": ["INR/Plt", "Antiko/antiagregan", "Sedasyon/Anestezi"]}),
  ("Port kateter", 45,   {"checklist": ["Antiagregan/antikoagülan kontrol"]}),
  ("Biliyer drenaj", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Sepsis riski notu"]}),
  ("SVK", 90, {"checklist": ["Antiko/antiagregan kontrol", "Giriş yolu hazırlığı"]}),
  ("Anevrizma Onarım", 180, {"checklist": ["Nöro-anestezi onayı", "Antiko/antiagregan yönetimi", "Kontrast/renal"]}),
  ("PTA Alt Ekstremite", 120, {"checklist": ["Antiko/antiagregan kontrol", "Distal nabız/segment planı"]}),
  ("Serebral Anjiografi", 90, {"checklist": ["INR/Plt", "GFR", "Giriş planı (radial/femoral)"]}),
  ("TARE", 150, {"checklist": ["Radyasyon planlama", "Karaciğer fonksiyonları", "Arteriyel haritalama"]}),
  ("TARE MAA", 150, {"checklist": ["MAA haritalama", "Radyasyon güvenliği"]}),
  ("Lenfanjiogram", 75, {"checklist": ["Kontrast alerji sorgusu", "Antibiyotik (kurum tercihi)"]}),
  ("Diğer (serbest giriş)", 60, {"checklist": ["Serbest not alanını doldurun"]}),
]

def get_conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _migrate_add_custom_proc_name(con: sqlite3.Connection):
    cols = [r["name"] for r in con.execute("PRAGMA table_info(appointments)").fetchall()]
    if "custom_proc_name" not in cols:
        con.execute("ALTER TABLE appointments ADD COLUMN custom_proc_name TEXT")
        con.commit()

def init_db():
    with get_conn() as con:
        con.executescript(SCHEMA)
        _migrate_add_custom_proc_name(con)

def seed_procedures():
    with get_conn() as con:
        for name, dur, req in SEED_PROCS:
            con.execute(
                "INSERT OR IGNORE INTO procedure_types(name, default_duration_min, requirements_json) VALUES (?,?,?)",
                (name, dur, json.dumps(req, ensure_ascii=False))
            )
        con.commit()
