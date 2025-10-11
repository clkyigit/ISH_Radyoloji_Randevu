import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from dotenv import load_dotenv
load_dotenv()

# ... (PROCEDURE_METADATA ve listeler aynı kalıyor) ...
PROCEDURE_METADATA = { "Tiroid FNA Biyopsi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 20, "hazirlik_listesi": ["Antikoagülan durumu sorgulandı.", "Lokal anestezi onayı alındı."]}, "Karaciğer Parankim Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli (INR, aPTT, Trombosit) mevcut."]}, "Böbrek Parankim Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve Kreatinin mevcut."]}, "Akciğer Kitle Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 40, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "İşlem sonrası pnömotoraks riski hakkında bilgi verildi."]}, "Apse/Kist Drenaj Kateteri Takılması": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma ve enfeksiyon belirteçleri mevcut."]}, "Tanısal Serebral Anjiyografi (DSA)": {"kategori": "Skopi Gerektiren", "sure_dk": 45, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel Kreatinin değeri mevcut."]}, "Akut İnme (Mekanik Trombektomi)": {"kategori": "Skopi Gerektiren", "sure_dk": 90, "hazirlik_listesi": ["ACİL DURUM! Zaman kritiktir.", "Nöroloji ve Anestezi ekibi bilgilendirildi.", "Hasta onamı (mümkünse) alındı."]}, "Anevrizma Koilleme / Embolizasyon": {"kategori": "Skopi Gerektiren", "sure_dk": 120, "hazirlik_listesi": ["Hasta en az 8 saat aç.", "Genel anestezi onayı alındı.", "Antikoagülan hekim planına göre yönetildi."]}, "Karotis Stentleme": {"kategori": "Skopi Gerektiren", "sure_dk": 75, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Nörolojik muayene yapıldı.", "Antikoagülan/Antiplatelet planı yapıldı."]}, "TACE / TARE (Onkolojik Embolizasyon)": {"kategori": "Skopi Gerektiren", "sure_dk": 90, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Onkoloji onayı mevcut.", "Karaciğer fonksiyon testleri güncel."]}, "Nefrostomi Kateteri Takılması": {"kategori": "Skopi Gerektiren", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 4 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve Kreatinin mevcut."]}, "Biliyer Drenaj (PTK)": {"kategori": "Skopi Gerektiren", "sure_dk": 45, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Geniş spektrumlu antibiyotik başlandı.", "Güncel pıhtılaşma ve KFT mevcut."]} }
SKOPI_GEREKTIREN_ISLEMLER = sorted([islem for islem, detay in PROCEDURE_METADATA.items() if detay["kategori"] == "Skopi Gerektiren"])
SKOPI_GEREKTIRMEYEN_ISLEMLER = sorted([islem for islem, detay in PROCEDURE_METADATA.items() if detay["kategori"] == "Skopi Gerektirmeyen"])

db = SQLAlchemy()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bu-bir-varsayilan-anahtardir-degistir')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), 'randevu.db')}").replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

#... (Islem ve User modelleri, login_manager, role_required decorator'ı aynı)
class Islem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hasta_adi = db.Column(db.String(100), nullable=False)
    islem_adi = db.Column(db.String(100), nullable=False)
    islem_tarihi = db.Column(db.String(10), nullable=False)
    anestezi_tipi = db.Column(db.String(50), default="Anestezi Yok", nullable=False)
    hazirlik_durumu = db.Column(db.Text, nullable=True)
    notlar = db.Column(db.Text, nullable=True)
    def to_dict(self):
        ANESTEZI_RENKLERI = {"Genel Anestezi": "#d9534f", "Sedasyon/MAC": "#f0ad4e", "Lokal Anestezi": "#5bc0de", "Anestezi Yok": "#5cb85c"}
        sure = PROCEDURE_METADATA.get(self.islem_adi, {}).get("sure_dk", 30)
        return {'title': f"{self.hasta_adi} ({sure} dk)", 'start': self.islem_tarihi, 'color': ANESTEZI_RENKLERI.get(self.anestezi_tipi, '#777'), 'allDay': True}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(80), nullable=False, default='teknisyen')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Bu sayfayı görüntülemek için lütfen giriş yapın."
login_manager.login_message_category = "warning"
@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))
def role_required(role_names):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in role_names:
                flash("Bu sayfaya erişim yetkiniz yok.", "danger")
                return redirect(url_for('ana_sayfa'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


with app.app_context():
    db.create_all()
    if User.query.count() == 0:
        admin_user = User(username='admin', role='admin')
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("Varsayılan admin kullanıcısı oluşturuldu: admin / admin123")

# ... (tüm diğer rotalarınız aynı kalıyor, en alta yeni rotayı ekleyeceğiz)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('ana_sayfa'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user, remember=True)
            return redirect(url_for('ana_sayfa'))
        flash('Geçersiz kullanıcı adı veya şifre.', 'danger')
    return render_template('login.html')

# (Burada /logout, /yeni, /islem_ekle, /gun, /arama, /admin vb. tüm diğer rotalarınız var...)

# --- YENİ GİZLİ VERİTABANI SIFIRLAMA ROTASI ---
@app.route('/GEÇİCİ_VERİTABANI_SIFIRLAMA_ADRESİ_12345')
@login_required
@role_required(['admin'])
def reset_database():
    try:
        # Önce tüm tabloları sil
        db.drop_all()
        # Sonra en güncel şemayla yeniden oluştur
        db.create_all()
        # Varsayılan admin kullanıcısını tekrar oluştur ki sisteme girebilelim
        if User.query.count() == 0:
            admin_user = User(username='admin', role='admin')
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
        flash('Veritabanı başarıyla sıfırlandı ve tablolar yeniden oluşturuldu! Lütfen tekrar giriş yapın.', 'success')
        return redirect(url_for('logout'))
    except Exception as e:
        flash(f'Veritabanı sıfırlanırken bir hata oluştu: {e}', 'danger')
        return redirect(url_for('ana_sayfa'))


# En alttaki if __name__ == '__main__': bloğu aynı kalıyor.
if __name__ == '__main__':
    app.run(debug=True)