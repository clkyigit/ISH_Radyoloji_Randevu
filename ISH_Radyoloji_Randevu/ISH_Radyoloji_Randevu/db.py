# C:\IR_Randevu\app\db.py
import sqlite3
from pathlib import Path
import json
import sys

def _app_base_dir() -> Path:
    # PyInstaller ile paketlenince app base, exe'nin klasörü olur
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # Geliştirici modunda: /app klasörünün bir üstü (proje kökü)
    return Path(__file__).resolve().parents[1]

DB_PATH = _app_base_dir() / "instance" / "app.db"

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
  date TEXT NOT NULL,
  anticoagulant INTEGER NOT NULL DEFAULT 0,
  antiplatelet INTEGER NOT NULL DEFAULT 0,
  anesthesia INTEGER NOT NULL DEFAULT 0,
  med_note TEXT,
  req_checks_json TEXT,
  doctor_username TEXT NOT NULL,
  custom_proc_name TEXT,
  patient_tc TEXT,            -- opsiyonel TC
  lab_notes TEXT,             -- opsiyonel lab notu
  prep_notes TEXT             -- opsiyonel hazırlık notu
);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
CREATE INDEX IF NOT EXISTS idx_appointments_tc ON appointments(patient_tc);
"""

# Genişletilmiş işlem listesi (süreler örnek, dilediğinde düzenleyebilirsin)
SEED_PROCS = [
  ("Karotis stent", 90,  {"checklist": ["DAPT (ASA+Klopidogrel)", "GFR/kontrast notu"]}),
  ("Serebral Anjiografi", 90, {"checklist": ["INR/Plt", "Renal fonksiyon", "Giriş planı (radial/femoral)"]}),
  ("Anevrizma Onarım", 180, {"checklist": ["Nöroanestezi onayı", "Antiko/antiagregan yönetimi"]}),
  ("SVK", 90, {"checklist": ["Antiko/antiagregan kontrol", "Giriş yolu hazırlığı"]}),
  ("PTA Alt Ekstremite", 120, {"checklist": ["Antiko/antiagregan kontrol", "Distal nabız/segment planı"]}),
  ("TACE", 120, {"checklist": ["GFR/Cr", "Bilirubin/INR"]}),
  ("TARE", 150, {"checklist": ["Radyasyon planlama", "Karaciğer fonksiyonları"]}),
  ("TARE MAA", 150, {"checklist": ["MAA haritalama", "Radyasyon güvenliği"]}),
  ("Lenfanjiogram", 75, {"checklist": ["Kontrast alerji sorgusu"]}),
  ("BT akciğer biyopsisi", 60, {"checklist": ["DOAC 48–72h kesim", "INR ≤1.5, Plt ≥50k"]}),
  ("US karaciğer biyopsisi", 45, {"checklist": ["INR ≤1.5, Plt ≥50k"]}),
  ("US tiroid biyopsisi", 30, {"checklist": ["Antiagregan gözden geçirme"]}),
  ("Nefrostomi", 60, {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("PTK", 60, {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("Drenaj", 45, {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("RFA/MWA", 90, {"checklist": ["INR/Plt", "Antiko/antiagregan", "Sedasyon/Anestezi"]}),
  ("Port kateter", 45, {"checklist": ["Antiagregan/antikoagülan kontrol"]}),
  ("Biliyer drenaj", 60, {"checklist": ["INR/Plt", "Antibiyotik"]}),
  ("UFE (Uterin Fibroid Embolizasyonu)", 120, {"checklist": ["Gebelik yokluğu", "Hb, INR/Plt"]}),
  ("PAE (Prostat Arter Embolizasyonu)", 120, {"checklist": ["PSA/IDR", "Kontrast/GFR"]}),
  ("TIPS", 150, {"checklist": ["Koagülasyon", "Karaciğer fonksiyonları", "Anestezi"]}),
  ("Renal arter stent/PTA", 90, {"checklist": ["GFR", "HT kontrol"]}),
  ("Diğer (serbest giriş)", 60, {"checklist": ["Serbest not alanını doldurun"]}),
]

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def _migrate_add_columns(con: sqlite3.Connection):
    cols = [r["name"] for r in con.execute("PRAGMA table_info(appointments)").fetchall()]
    def add(col, ddl):
        if col not in cols:
            con.execute(f"ALTER TABLE appointments ADD COLUMN {ddl}")
    # güvenli tekrar çalıştırma
    add("custom_proc_name", "custom_proc_name TEXT")
    add("patient_tc", "patient_tc TEXT")
    add("lab_notes", "lab_notes TEXT")
    add("prep_notes", "prep_notes TEXT")
    con.commit()

def init_db():
    with get_conn() as con:
        con.executescript(SCHEMA)
        _migrate_add_columns(con)

def seed_procedures():
    with get_conn() as con:
        for name, dur, req in SEED_PROCS:
            con.execute(
                "INSERT OR IGNORE INTO procedure_types(name, default_duration_min, requirements_json) VALUES (?,?,?)",
                (name, dur, json.dumps(req, ensure_ascii=False))
            )
        con.commit()
