import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# --- GÜNCELLENMİŞ MERKEZİ VERİ YAPISI ---
PROCEDURE_METADATA = {
    # Skopi Gerektirmeyen
    "Tiroid FNA Biyopsi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 20, "hazirlik_listesi": ["Antikoagülan durumu sorgulandı.", "Lokal anestezi onayı alındı."]},
    "Karaciğer Parankim Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli (INR, aPTT, Trombosit) mevcut."]},
    "Böbrek Parankim Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve Kreatinin mevcut."]},
    "Akciğer Kitle Biyopsisi": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 40, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "İşlem sonrası pnömotoraks riski hakkında bilgi verildi."]},
    "Apse/Kist Drenaj Kateteri Takılması": {"kategori": "Skopi Gerektirmeyen", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma ve enfeksiyon belirteçleri mevcut."]},

    # Skopi Gerektiren
    "Tanısal Serebral Anjiyografi (DSA)": {"kategori": "Skopi Gerektiren", "sure_dk": 45, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel Kreatinin değeri mevcut."]},
    "Akut İnme (Mekanik Trombektomi)": {"kategori": "Skopi Gerektiren", "sure_dk": 90, "hazirlik_listesi": ["ACİL DURUM! Zaman kritiktir.", "Nöroloji ve Anestezi ekibi bilgilendirildi.", "Hasta onamı (mümkünse) alındı."]},
    "Anevrizma Koilleme / Embolizasyon": {"kategori": "Skopi Gerektiren", "sure_dk": 120, "hazirlik_listesi": ["Hasta en az 8 saat aç.", "Genel anestezi onayı alındı.", "Antikoagülan hekim planına göre yönetildi."]},
    "Karotis Stentleme": {"kategori": "Skopi Gerektiren", "sure_dk": 75, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Nörolojik muayene yapıldı.", "Antikoagülan/Antiplatelet planı yapıldı.", "Genel/Lokal anestezi onayı alındı."]},
    "TACE / TARE (Onkolojik Embolizasyon)": {"kategori": "Skopi Gerektiren", "sure_dk": 90, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Onkoloji onayı mevcut.", "Karaciğer fonksiyon testleri güncel."]},
    "Nefrostomi Kateteri Takılması": {"kategori": "Skopi Gerektiren", "sure_dk": 30, "hazirlik_listesi": ["Hasta en az 4 saat aç.", "Antikoagülan hekim planına göre yönetildi.", "Güncel pıhtılaşma paneli ve Kreatinin mevcut."]},
    "Biliyer Drenaj (PTK)": {"kategori": "Skopi Gerektiren", "sure_dk": 45, "hazirlik_listesi": ["Hasta en az 6 saat aç.", "Geniş spektrumlu antibiyotik başlandı.", "Güncel pıhtılaşma ve KFT mevcut."]}
}
SKOPI_GEREKTIREN_ISLEMLER = sorted([islem for islem, detay in PROCEDURE_METADATA.items() if detay["kategori"] == "Skopi Gerektiren"])
SKOPI_GEREKTIRMEYEN_ISLEMLER = sorted([islem for islem, detay in PROCEDURE_METADATA.items() if detay["kategori"] == "Skopi Gerektirmeyen"])

db = SQLAlchemy()

# YENİ VERİTABANI MODELİ
class Islem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hasta_adi = db.Column(db.String(100), nullable=False)
    islem_adi = db.Column(db.String(100), nullable=False)
    islem_tarihi = db.Column(db.String(10), nullable=False)
    anestezi_tipi = db.Column(db.String(50), default="Anestezi Yok", nullable=False)
    hazirlik_durumu = db.Column(db.Text, nullable=True)

    def to_dict(self):
        ANESTEZI_RENKLERI = {
            "Genel Anestezi": "#d9534f", # Kırmızı
            "Sedasyon/MAC": "#f0ad4e",  # Turuncu
            "Lokal Anestezi": "#5bc0de", # Mavi
            "Anestezi Yok": "#5cb85c"   # Yeşil
        }
        sure = PROCEDURE_METADATA.get(self.islem_adi, {}).get("sure_dk", 30)
        return {'title': f"{self.hasta_adi} ({sure} dk)", 'start': self.islem_tarihi, 'color': ANESTEZI_RENKLERI.get(self.anestezi_tipi, '#777'), 'allDay': True}

app = Flask(__name__)
# ... (app.config ve db.init_app kodları aynı)
db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'randevu.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
with app.app_context():
    db.create_all()

@app.route('/')
def ana_sayfa():
    bugun_str = datetime.today().strftime('%Y-%m-%d')
    bugunun_islemleri = Islem.query.filter_by(islem_tarihi=bugun_str).all()
    return render_template('index.html', bugunun_islemleri=bugunun_islemleri)

# ... (yeni_islem_sayfasi, islem_ekle, api_islemler, islem_detay rotaları)
@app.route('/yeni')
def yeni_islem_sayfasi():
    return render_template('yeni_islem.html', skopi_gerektiren=SKOPI_GEREKTIREN_ISLEMLER, skopi_gerektirmeyen=SKOPI_GEREKTIRMEYEN_ISLEMLER)

@app.route('/islem_ekle', methods=['POST'])
def islem_ekle():
    islem_adi_secimi = request.form.get('islem_adi_skopi_gerektiren') or request.form.get('islem_adi_skopi_gerektirmeyen')
    kategori_secimi = "Skopi Gerektiren" if request.form.get('islem_adi_skopi_gerektiren') else "Skopi Gerektirmeyen"
    hazirlik_listesi = PROCEDURE_METADATA.get(islem_adi_secimi, {}).get("hazirlik_listesi", [])
    tiklenen_maddeler = request.form.getlist('hazirlik_maddesi')
    hazirlik_durumu_dict = {madde: (madde in tiklenen_maddeler) for madde in hazirlik_listesi}
    yeni_islem = Islem(
        hasta_adi=request.form['hasta_adi'],
        islem_adi=islem_adi_secimi,
        islem_tarihi=request.form['islem_tarihi'],
        anestezi_tipi=request.form['anestezi_tipi'],
        hazirlik_durumu=json.dumps(hazirlik_durumu_dict)
    )
    db.session.add(yeni_islem)
    db.session.commit()
    return redirect(url_for('ana_sayfa'))

@app.route('/api/islemler')
def api_islemler():
    tum_islemler = Islem.query.all()
    return jsonify([islem.to_dict() for islem in tum_islemler])

@app.route('/api/islem_detay/<path:islem_adi>')
def islem_detay(islem_adi):
    detaylar = PROCEDURE_METADATA.get(islem_adi)
    if detaylar: return jsonify(detaylar)
    return jsonify({"hata": "İşlem bulunamadı"}), 404

# YENİ ROTALAR
@app.route('/gun/<tarih>')
def gun_detay(tarih):
    try:
        datetime.strptime(tarih, '%Y-%m-%d')
    except ValueError:
        return "Geçersiz tarih formatı.", 400
    
    gunun_islemleri = Islem.query.filter_by(islem_tarihi=tarih).all()
    toplam_sure = 0
    for islem in gunun_islemleri:
        toplam_sure += PROCEDURE_METADATA.get(islem.islem_adi, {}).get("sure_dk", 0)
    
    return render_template('gun.html', islemler=gunun_islemleri, tarih=tarih, toplam_sure=toplam_sure)

@app.route('/arama')
def arama():
    sorgu = request.args.get('q', '')
    # Yeni eklenen: Hangi tipte arama yapılacağını formdan al (varsayılan: hasta_adi)
    search_type = request.args.get('search_type', 'hasta_adi')
    
    if not sorgu:
        return redirect(url_for('ana_sayfa'))
    
    if search_type == 'islem_adi':
        # Eğer "İşlem Adı" seçildiyse, islem_adi sütununda ara
        sonuclar = Islem.query.filter(Islem.islem_adi.ilike(f'%{sorgu}%')).order_by(Islem.islem_tarihi.desc()).all()
        arama_tipi_str = "İşlem Adına Göre"
    else:
        # Varsayılan olarak "Hasta Adı" sütununda ara
        sonuclar = Islem.query.filter(Islem.hasta_adi.ilike(f'%{sorgu}%')).order_by(Islem.islem_tarihi.desc()).all()
        arama_tipi_str = "Hasta Adına Göre"
        
    return render_template('arama_sonuclari.html', sonuclar=sonuclar, sorgu=sorgu, arama_tipi=arama_tipi_str)

if __name__ == '__main__':
    app.run(debug=True)