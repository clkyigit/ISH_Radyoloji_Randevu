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

# --- 1. MERKEZİ VERİ YAPISI ---
PROCEDURE_METADATA = {
    # --- Skopi Gerektirmeyen İşlemler ---
    "Tiroid FNA Biyopsi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 20, "hazirlik_listesi": ["Antikoagülan durumu sorgulandı.", "Lokal anestezi onayı alındı.", "İlgili kan testleri kontrol edildi."]},
    "Karaciğer Parankim Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli (INR, aPTT, Trombosit) mevcut.", "Sedasyon/Anestezi onayı alındı."]},
    "Böbrek Parankim Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve Kreatinin mevcut.", "Sedasyon/Anestezi onayı alındı."]},
    "Akciğer Kitle Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 40, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli mevcut.", "İşlem sonrası pnömotoraks riski hakkında bilgi verildi."]},
    "Apse/Kist Drenaj Kateteri Takılması": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve enfeksiyon belirteçleri mevcut.", "Sedasyon/Anestezi onayı alındı."]},
    "Lenf Nodu Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 25, "hazirlik_listesi": ["Antikoagülan durumu sorgulandı.", "Lokal anestezi/sedasyon onayı alındı."]},
    "Port Kateteri Takılması": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Antikoagülan durumu sorgulandı.", "Güncel pıhtılaşma paneli mevcut.", "Lokal anestezi onayı alındı."]},
    
    # --- Skopi Gerektiren İşlemler ---
    "Tanısal Serebral Anjiyografi (DSA)": {"kategori": "Skopi Gerektiren", "sure_dk": 45, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel Kreatinin değeri mevcut.", "Kasıık traşı yapıldı.", "Nörolojik muayene yapıldı."]},
    "Akut İnme (Mekanik Trombektomi)": {"kategori": "Skopi Gerektiren", "sure_dk": 90, "hazirlik_listesi": ["ACİL DURUM! Zaman kritiktir.", "Nöroloji ve Anestezi ekibi bilgilendirildi.", "Hasta onamı (mümkünse) alındı.", "Antikoagülan durumu biliniyor."]},
    "Anevrizma Koilleme / Embolizasyon": {"kategori": "Skopi Gerektiren", "sure_dk": 120, "hazirlik_listesi": ["Hasta en az 8 saat aç.", "Genel anestezi onayı alındı.", "Antikoagülan hekim planına göre yönetildi.", "Gerekli kan testleri (tam kan, pıhtılaşma, biyokimya) tamamlandı."]},
    "Karotis Stentleme": {"kategori": "Skopi Gerektiren", "sure_dk": 75, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Nörolojik muayene yapıldı.", "Antikoagülan/Antiplatelet planı yapıldı.", "Genel/Lokal anestezi onayı alındı."]},
    "TACE / TARE (Onkolojik Embolizasyon)": {"kategori": "Skopi Gerektiren", "sure_dk": 90, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Onkoloji onayı mevcut.", "Karaciğer fonksiyon testleri güncel.", "Antikoagülan hekim planına göre yönetildi.", "Sedasyon/Anestezi onayı alındı."]},
    "Nefrostomi Kateteri Takılması": {"kategori": "Skopi Gerektiren", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 4 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve Kreatinin mevcut.", "Sedasyon/Anestezi onayı alındı."]},
    "Biliyer Drenaj (PTK)": {"kategori": "Skopi Gerektiren", "sure_dk": 45, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Geniş spektrumlu antibiyotik başlandı.", "Güncel pıhtılaşma ve KFT mevcut."]},
    "Periferik Arter Anjiyoplasti/Stentleme": {"kategori": "Skopi Gerektiren", "sure_dk": 60, "hazirlik_listesi": ["Hasta en az 4 saat aç.", "Antikoagülan/Antiplatelet planı yapıldı.", "Güncel Kreatinin ve pıhtılaşma paneli mevcut."]}
}
SKOPI_GEREKTIREN_ISLEMLER = sorted([islem for islem, detay in PROCEDURE_METADATA.items() if detay["kategori"] == "Skopi Gerektiren"])
SKOPI_GEREKTIRMEYEN_ISLEMLER = sorted([islem for islem, detay in PROCEDURE_METADATA.items() if detay["kategori"] == "Skopi Gerektirmeyen"])

# --- 2. UYGULAMA VE VERİTABANI KURULUMU ---
db = SQLAlchemy()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'bu-bir-varsayilan-anahtardir-degistir')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f"sqlite:///{os.path.join(os.path.abspath(os.path.dirname(__file__)), 'randevu.db')}").replace("postgres://", "postgresql://")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- 3. VERİTABANI MODELLERİ ---
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
        anestezi_isareti = f" ({self.anestezi_tipi})" if self.anestezi_tipi != "Anestezi Yok" else ""
        return {'title': f"{self.hasta_adi}{anestezi_isareti}", 'start': self.islem_tarihi, 'color': ANESTEZI_RENKLERI.get(self.anestezi_tipi, '#777'), 'allDay': True}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(80), nullable=False, default='teknisyen')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

db.init_app(app)

# --- 4. YETKİLENDİRME SİSTEMİ ---
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

# --- 5. İLK ÇALIŞTIRMA ---
with app.app_context():
    db.create_all()
    if User.query.count() == 0:
        admin_user = User(username='admin', role='admin')
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("Varsayılan admin kullanıcısı oluşturuldu: admin / admin123")

# --- 6. ROTALAR (SAYFALAR) ---
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

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def ana_sayfa():
    bugun_str = datetime.today().strftime('%Y-%m-%d')
    bugunun_islemleri = Islem.query.filter_by(islem_tarihi=bugun_str).all()
    return render_template('index.html', bugunun_islemleri=bugunun_islemleri, bugun_str=bugun_str)

@app.route('/yeni')
@login_required
@role_required(['admin', 'doktor'])
def yeni_islem_sayfasi():
    return render_template('yeni_islem.html', skopi_gerektiren=SKOPI_GEREKTIREN_ISLEMLER, skopi_gerektirmeyen=SKOPI_GEREKTIRMEYEN_ISLEMLER)

@app.route('/islem_ekle', methods=['POST'])
@login_required
@role_required(['admin', 'doktor'])
def islem_ekle():
    islem_adi_secimi = request.form.get('islem_adi_skopi_gerektiren') or request.form.get('islem_adi_skopi_gerektirmeyen')
    kategori_secimi = PROCEDURE_METADATA.get(islem_adi_secimi, {}).get("kategori", "Bilinmeyen")
    hazirlik_listesi = PROCEDURE_METADATA.get(islem_adi_secimi, {}).get("hazirlik_listesi", [])
    tiklenen_maddeler = request.form.getlist('hazirlik_maddesi')
    hazirlik_durumu_dict = {madde: (madde in tiklenen_maddeler) for madde in hazirlik_listesi}
    yeni_islem = Islem(
        hasta_adi=request.form['hasta_adi'], islem_adi=islem_adi_secimi, islem_tarihi=request.form['islem_tarihi'],
        anestezi_tipi=request.form['anestezi_tipi'], hazirlik_durumu=json.dumps(hazirlik_durumu_dict), notlar=request.form.get('notlar')
    )
    db.session.add(yeni_islem)
    db.session.commit()
    flash(f"'{yeni_islem.hasta_adi}' için randevu başarıyla oluşturuldu.", "success")
    return redirect(url_for('gun_detay', tarih=yeni_islem.islem_tarihi))

@app.route('/duzenle/<int:islem_id>', methods=['GET', 'POST'])
@login_required
@role_required(['admin', 'doktor'])
def duzenle(islem_id):
    islem = db.session.get(Islem, islem_id)
    if not islem: return "İşlem bulunamadı", 404
    if request.method == 'POST':
        islem.hasta_adi = request.form['hasta_adi']
        islem.islem_tarihi = request.form['islem_tarihi']
        islem.islem_adi = request.form.get('islem_adi_skopi_gerektiren') or request.form.get('islem_adi_skopi_gerektirmeyen')
        islem.anestezi_tipi = request.form['anestezi_tipi']
        islem.notlar = request.form.get('notlar')
        hazirlik_listesi = PROCEDURE_METADATA.get(islem.islem_adi, {}).get("hazirlik_listesi", [])
        tiklenen_maddeler = request.form.getlist('hazirlik_maddesi')
        islem.hazirlik_durumu = json.dumps({madde: (madde in tiklenen_maddeler) for madde in hazirlik_listesi})
        db.session.commit()
        flash("Randevu başarıyla güncellendi.", "success")
        return redirect(url_for('gun_detay', tarih=islem.islem_tarihi))
    hazirlik_durumu_dict = json.loads(islem.hazirlik_durumu) if islem.hazirlik_durumu else {}
    return render_template('duzenle.html', islem=islem, hazirlik_durumu=hazirlik_durumu_dict, skopi_gerektiren=SKOPI_GEREKTIREN_ISLEMLER, skopi_gerektirmeyen=SKOPI_GEREKTIRMEYEN_ISLEMLER)

@app.route('/sil/<int:islem_id>', methods=['POST'])
@login_required
@role_required(['admin', 'doktor'])
def sil(islem_id):
    islem = db.session.get(Islem, islem_id)
    if islem:
        tarih = islem.islem_tarihi
        db.session.delete(islem)
        db.session.commit()
        flash("Randevu başarıyla silindi.", "info")
        return redirect(url_for('gun_detay', tarih=tarih))
    return "İşlem bulunamadı", 404

@app.route('/gun/<tarih>')
@login_required
def gun_detay(tarih):
    gunun_islemleri = Islem.query.filter_by(islem_tarihi=tarih).all()
    toplam_sure = sum(PROCEDURE_METADATA.get(islem.islem_adi, {}).get("sure_dk", 0) for islem in gunun_islemleri)
    return render_template('gun.html', islemler=gunun_islemleri, tarih=tarih, toplam_sure=toplam_sure)

@app.route('/arama')
@login_required
def arama():
    sorgu = request.args.get('q', '')
    search_type = request.args.get('search_type', 'hasta_adi')
    if not sorgu: return redirect(url_for('ana_sayfa'))
    if search_type == 'islem_adi':
        sonuclar = Islem.query.filter(Islem.islem_adi.ilike(f'%{sorgu}%')).order_by(Islem.islem_tarihi.desc()).all()
        arama_tipi_str = "İşlem Adına Göre"
    else:
        sonuclar = Islem.query.filter(Islem.hasta_adi.ilike(f'%{sorgu}%')).order_by(Islem.islem_tarihi.desc()).all()
        arama_tipi_str = "Hasta Adına Göre"
    return render_template('arama_sonuclari.html', sonuclar=sonuclar, sorgu=sorgu, arama_tipi=arama_tipi_str)

@app.route('/admin')
@login_required
@role_required(['admin'])
def admin_panel():
    users = User.query.all()
    return render_template('admin_panel.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
@login_required
@role_required(['admin'])
def add_user():
    username = request.form['username']
    password = request.form['password']
    role = request.form['role']
    if User.query.filter_by(username=username).first():
        flash(f"'{username}' kullanıcı adı zaten mevcut.", "danger")
    else:
        new_user = User(username=username, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash(f"'{username}' kullanıcısı başarıyla oluşturuldu.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@role_required(['admin'])
def delete_user(user_id):
    user_to_delete = db.session.get(User, user_id)
    if user_to_delete:
        if user_to_delete.id == current_user.id:
            flash("Admin kendi hesabını silemez.", "danger")
        else:
            db.session.delete(user_to_delete)
            db.session.commit()
            flash(f"'{user_to_delete.username}' kullanıcısı silindi.", "success")
    return redirect(url_for('admin_panel'))

@app.route('/api/islemler')
@login_required
def api_islemler():
    tum_islemler = Islem.query.all()
    return jsonify([islem.to_dict() for islem in tum_islemler])

@app.route('/api/islem_detay/<path:islem_adi>')
@login_required
def islem_detay(islem_adi):
    detaylar = PROCEDURE_METADATA.get(islem_adi)
    if detaylar: return jsonify(detaylar)
    return jsonify({"hata": "İşlem bulunamadı"}), 404

# --- 7. GEÇİCİ VERİTABANI SIFIRLAMA ROTASI (GÜVENLİK İÇİN SONRA KALDIRILACAK) ---
# Korumaları hala kapalı. Veritabanını sıfırladıktan sonra bu fonksiyonu SİLİN veya korumalarını AÇIN.
#@login_required
#@role_required(['admin'])
@app.route('/GEÇİCİ_VERİTABANI_SIFIRLAMA_ADRESİ_12345')
def reset_database():
    try:
        print("--- VERİTABANI SIFIRLAMA BAŞLATILDI ---")
        db.drop_all()
        print("--- ESKİ TABLOLAR SİLİNDİ (DROP ALL) ---")
        db.create_all()
        print("--- YENİ TABLOLAR OLUŞTURULDU (CREATE ALL) ---")
        admin_user = User(username='admin', role='admin')
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print("--- VARSAYILAN ADMİN OLUŞTURULDU ---")
        return "Veritabanı başarıyla sıfırlandı. LÜTFEN ŞİMDİ BU KODU app.py'den SİLİN VE GÜVENLİK KORUMALARINI GERİ GETİRİN. Ardından login sayfasına gidin."
    except Exception as e:
        print(f"!!! SIFIRLAMA SIRASINDA KRİTİK HATA: {e} !!!")
        return f"Veritabanı sıfırlanırken bir hata oluştu: <br>{e}", 500

# --- 8. UYGULAMAYI BAŞLATMA ---
if __name__ == '__main__':
    app.run(debug=True)