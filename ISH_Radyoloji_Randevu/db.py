# ISH_Radyoloji_Randevu/db.py
import os, sqlite3, json, shutil, time
from pathlib import Path
from werkzeug.security import generate_password_hash

DB_DIR = os.environ.get("DB_DIR") or "/var/data/ir_randevu_instance"
INSTANCE_DIR = Path(DB_DIR)
LEGACY_INSTANCE_DIR = Path(__file__).resolve().parent / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = INSTANCE_DIR / "app.db"

def _maybe_migrate_legacy_db():
    legacy_db = LEGACY_INSTANCE_DIR / "app.db"
    if legacy_db.exists() and not DB_PATH.exists():
        try: shutil.copy2(legacy_db, DB_PATH)
        except Exception: pass

_maybe_migrate_legacy_db()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT,
  pin TEXT,
  role TEXT NOT NULL DEFAULT 'doctor',
  active INTEGER NOT NULL DEFAULT 1
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
  custom_proc_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
"""

SEED_PROCS = [
  ("Karotis stent", 90,  {"checklist": ["DAPT (ASA+Klopidogrel)", "GFR/kontrast", "Antitrombotik gözden geçirme"]}),
  ("SVK", 45, {"checklist": ["Antiko/antiagregan", "US eşliğinde giriş", "Alerji/antibiyotik"]}),
  ("Anevrizma Onarım", 180, {"checklist": ["Nöro anestezi", "Antiko/antiagregan", "Kontrast/GFR"]}),
  ("PTA Alt Ekstremite", 120, {"checklist": ["Antitrombotik", "Distal nabız/segment", "Hemostaz"]}),
  ("Serebral Anjiografi", 90, {"checklist": ["INR/Plt", "GFR/kontrast", "Alerji", "Giriş planı"]}),
  ("TARE", 150, {"checklist": ["Radyasyon planlama", "Karaciğer fonk.", "Arteriyel harita"]}),
  ("TARE MAA", 150, {"checklist": ["MAA haritalama", "Güvenlik", "Karaciğer fonk."]}),
  ("Lenfanjiogram", 75, {"checklist": ["Alerji", "Antibiyotik", "Giriş noktası"]}),
  ("BT Akc. Biyopsi", 60, {"checklist": ["Koag", "Antitrombotik", "Pnömotoraks bilgilendirme"]}),
  ("US Karac. Biyopsi", 45, {"checklist": ["INR≤1.5, Plt≥50k", "Antitrombotik", "Kanama izlemi"]}),
  ("US Tiroid Biyopsi", 30, {"checklist": ["Antitrombotik", "US oda/iğne", "Kanama riski"]}),
  ("Nefrostomi", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Sepsis riski"]}),
  ("PTK", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Dilatasyon/stent"]}),
  ("Drenaj", 45, {"checklist": ["INR/Plt", "Antibiyotik", "Sıvı analizi"]}),
  ("RFA/MWA", 90, {"checklist": ["Koag", "Antitrombotik", "Sedasyon/Anestezi"]}),
  ("Port Kateter", 45, {"checklist": ["Antitrombotik", "US giriş", "Antibiyotik"]}),
  ("Biliyer Drenaj", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Sepsis/kolanjit riski"]}),
  ("TACE", 120, {"checklist": ["Karaciğer fonk.", "GFR/kontrast", "Antitrombotik", "Arteriyel harita"]}),
  ("EVAR", 180, {"checklist": ["Anestezi", "DAPT", "GFR/kontrast", "Greft planı"]}),
  ("Diğer (serbest giriş)", 60, {"checklist": ["Serbest not"]}),
]

def _configure_conn(con: sqlite3.Connection):
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.execute("PRAGMA busy_timeout=5000;")
    cur.close()

def get_conn():
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    _configure_conn(con)
    return con

def _migrate(con: sqlite3.Connection):
    cols = [r["name"] for r in con.execute("PRAGMA table_info(users)").fetchall()]
    if "role" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'doctor'")
    if "active" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN active INTEGER NOT NULL DEFAULT 1")
    cols_ap = [r["name"] for r in con.execute("PRAGMA table_info(appointments)").fetchall()]
    if "custom_proc_name" not in cols_ap:
        con.execute("ALTER TABLE appointments ADD COLUMN custom_proc_name TEXT")
    con.commit()

def init_db():
    with get_conn() as con:
        con.executescript(SCHEMA)
        _migrate(con)
        # default admin varsa geç
        cnt = con.execute("SELECT COUNT(*) as c FROM users WHERE username='admin'").fetchone()["c"]
        if cnt == 0:
            con.execute(
                "INSERT INTO users(username, password_hash, role, active) VALUES (?,?,?,1)",
                ("admin", generate_password_hash("admin123"), "admin")
            )
            con.commit()

def seed_procedures():
    with get_conn() as con:
        for name, dur, req in SEED_PROCS:
            con.execute(
                "INSERT OR IGNORE INTO procedure_types(name, default_duration_min, requirements_json) VALUES (?,?,?)",
                (name, dur, json.dumps(req, ensure_ascii=False))
            )
        con.commit()

# --- Kullanıcı işlemleri ---
def create_user(username: str, password_hash: str, role: str):
    with get_conn() as con:
        con.execute(
            "INSERT INTO users(username, password_hash, role, active) VALUES (?,?,?,1)",
            (username, password_hash, role)
        )
        con.commit()

def list_users():
    with get_conn() as con:
        return con.execute("SELECT id, username, role, active FROM users ORDER BY username").fetchall()

def set_user_active(uid: int, active: int):
    with get_conn() as con:
        con.execute("UPDATE users SET active=? WHERE id=?", (active, uid))
        con.commit()

def reset_user_password(uid: int, password_hash: str):
    with get_conn() as con:
        con.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid))
        con.commit()

def get_user_by_username(username: str):
    with get_conn() as con:
        return con.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
