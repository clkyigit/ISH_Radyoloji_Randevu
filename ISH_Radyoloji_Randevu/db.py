# ISH_Radyoloji_Randevu/db.py
import os, sqlite3, json, shutil
from pathlib import Path

# 1) Kalıcı dizin: ENV > /var/data/ir_randevu_instance > ./instance
DB_DIR = os.environ.get("DB_DIR") or "/var/data/ir_randevu_instance"
INSTANCE_DIR = Path(DB_DIR)
LEGACY_INSTANCE_DIR = Path(__file__).resolve().parent / "instance"  # eski konum

INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = INSTANCE_DIR / "app.db"

# 2) İlk açılışta eski dosyayı kalıcı diske taşı (varsa)
def _maybe_migrate_legacy_db():
    legacy_db = LEGACY_INSTANCE_DIR / "app.db"
    if legacy_db.exists() and not DB_PATH.exists():
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(legacy_db, DB_PATH)
        except Exception:
            # taşıma başarısızsa, yeni db zaten oluşturulacak
            pass

_maybe_migrate_legacy_db()

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
  custom_proc_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON appointments(date);
"""

SEED_PROCS = [
  ("Karotis stent", 90,  {"checklist": ["DAPT (ASA + Klopidogrel)", "GFR/kontrast notu", "Son 7 günde antitrombosit/antiko gözden geçirme"]}),
  ("SVK", 45, {"checklist": ["Antiko/antiagregan kontrol", "US eşliğinde giriş planı", "Alerji/antibiyotik profilaksisi"]}),
  ("Anevrizma Onarım", 180, {"checklist": ["Nöro anestezi onayı", "Antiko/antiagregan yönetimi", "Kontrast/renal fonksiyon"]}),
  ("PTA Alt Ekstremite", 120, {"checklist": ["Antiko/antiagregan kontrol", "Distal nabız/segment planı", "Giriş yolu ve hemostaz planı"]}),
  ("Serebral Anjiografi", 90, {"checklist": ["INR/Plt", "GFR/kontrast", "Alerji sorgusu", "Giriş planı (radial/femoral)"]}),
  ("TARE", 150, {"checklist": ["Radyasyon planlama", "Karaciğer fonksiyonları", "Arteriyel haritalama", "Non-target emboli önlemleri"]}),
  ("TARE MAA", 150, {"checklist": ["MAA haritalama", "Radyasyon güvenliği", "Karaciğer fonksiyonları"]}),
  ("Lenfanjiogram", 75, {"checklist": ["Kontrast alerji sorgusu", "Antibiyotik profilaksisi (kurum tercihi)", "Giriş noktası planı"]}),
  ("BT Akciğer Biyopsisi", 60, {"checklist": ["Koag (INR ≤1.5, Plt ≥50k öneri)", "Antitrombotik ilaçlar", "Pnömotoraks bilgilendirme"]}),
  ("US Karaciğer Biyopsisi", 45, {"checklist": ["INR ≤1.5, Plt ≥50k", "Antiko/antiagregan kontrol", "Post-bx kanama izlemi planı"]}),
  ("US Tiroid Biyopsisi", 30, {"checklist": ["Antitrombotik durum", "US oda/iğne planı", "Kanama riski bilgilendirme"]}),
  ("Nefrostomi", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Sepsis riski", "Sedasyon planı"]}),
  ("PTK", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Dilatasyon/stent planı"]}),
  ("Drenaj", 45, {"checklist": ["INR/Plt", "Antibiyotik", "Sıvı analizi planı"]}),
  ("RFA/MWA", 90, {"checklist": ["INR/Plt", "Antiko/antiagregan", "Sedasyon/Anestezi", "Güvenlik zonu"]}),
  ("Port Kateter", 45, {"checklist": ["Antitrombotik kontrol", "US eşliğinde giriş", "Alerji/antibiyotik", "Bakım eğitimi"]}),
  ("Biliyer Drenaj", 60, {"checklist": ["INR/Plt", "Antibiyotik", "Sepsis/kolanjit riski", "GFR/kontrast"]}),
  ("TACE", 120, {"checklist": ["Karaciğer fonksiyonları", "GFR/kontrast", "Antiko/antiagregan", "Arteriyel harita"]}),
  ("EVAR", 180, {"checklist": ["Anestezi onayı", "DAPT/antiplatelet", "GFR/kontrast", "Greft ölçü/malzeme planı"]}),
  ("Diğer (serbest giriş)", 60, {"checklist": ["Serbest not alanını doldurun"]}),
]

def get_conn():
    # check_same_thread=False: çoklu thread’lerde güvenli kullanım için
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
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
