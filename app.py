from flask import Flask, render_template, request, redirect, url_for, send_file
import requests
import cloudscraper  # EKLENDİ: Site engelini aşmak için
from bs4 import BeautifulSoup
import pandas as pd
from io import BytesIO
from datetime import datetime

app = Flask(__name__)

# ----------------------------------------
# 1) CrossRef: Makale adından dergi + ISSN bul
# ----------------------------------------
def get_journal_info(title):
    # Crossref genelde engellemez ama yine de header ekleyelim
    url = f"https://api.crossref.org/works?query={title}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return None, None, None

        data = r.json()
        items = data["message"].get("items", [])

        if not items:
            return None, None, None

        item = items[0]
        journal = item.get("container-title", ["Bilinmiyor"])[0]
        issn_list = item.get("ISSN", [])
        issn = issn_list[0] if issn_list else None
        
        # Yıl bilgisini al
        published_date = item.get("published", {}).get("date-parts", [[None]])[0]
        year = published_date[0] if published_date and len(published_date) > 0 else None

        return journal, issn, year
    except:
        return None, None, None

# ----------------------------------------
# 2) SCImago: ISSN ile Quartile bul (Cloudscraper ile)
# ----------------------------------------
def get_quartile_from_sjr(issn):
    if not issn:
        return None, [], [], None

    scimago_url = f"https://www.scimagojr.com/journalsearch.php?q={issn}&tip=sid"
    print(f"SCImago aranıyor: {issn} - URL: {scimago_url}")
    
    # Cloudscraper kullanımı (Engel aşmak için kritik nokta)
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(scimago_url, timeout=20)
        print(f"SCImago response status: {r.status_code}")
        print(f"SCImago final URL: {r.url}")
        
        # Eğer direkt dergi sayfasına yönlendirmezse arama sonuçlarından bulmaya çalış
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Dergi detay sayfasında mıyız kontrol et
        if "journalsearch.php" in r.url and "tip=sid" not in r.url:
             # Arama sayfasındayız, ilk sonuca tıklamamız lazım
             print("Arama sayfasında, dergi linki aranıyor...")
             search_results = soup.find('div', class_='search_results')
             if search_results:
                 link = search_results.find('a', href=True)
                 if link:
                     journal_url = "https://www.scimagojr.com/" + link['href']
                     print(f"Dergi linki bulundu: {journal_url}")
                     r = scraper.get(journal_url)
                     soup = BeautifulSoup(r.text, "html.parser")
                     print(f"Dergi sayfasına gidildi: {r.url}")
             else:
                 print("Arama sonuçları bulunamadı")

        # Quartile Tablosunu Bul
        categories_info = []
        quartiles_table = None
        
        # Sitedeki tablo yapısını dinamik arama
        tables = soup.find_all('table')
        print(f"Toplam {len(tables)} tablo bulundu")
        
        for i, table in enumerate(tables):
            table_text = table.get_text()[:100]  # İlk 100 karakter
            print(f"Tablo {i}: {table_text}")
            if "Quartile" in table_text or "Category" in table_text:
                quartiles_table = table
                print(f"Quartile tablosu bulundu: Tablo {i}")
                break
        
        if quartiles_table:
            rows = quartiles_table.find_all('tr')
            print(f"Quartile tablosunda {len(rows)} satır bulundu")
            
            for row in rows[1:]:
                cells = row.find_all('td')
                if len(cells) >= 3:
                    try:
                        cat = cells[0].text.strip()
                        yr = int(cells[1].text.strip())
                        q = cells[2].text.strip()
                        if q in ['Q1', 'Q2', 'Q3', 'Q4']:
                            categories_info.append({'category': cat, 'year': yr, 'quartile': q})
                            print(f"Bulunan veri: {cat} - {yr} - {q}")
                    except Exception as e:
                        print(f"Satır işleme hatası: {e}")
                        continue
        
        # Veri bulundu mu?
        if categories_info:
            latest_entry = max(categories_info, key=lambda x: x['year'])
            latest_quartile = latest_entry['quartile']
            years_list = sorted(list(set(c['year'] for c in categories_info)))
            print(f"Başarılı! {len(categories_info)} veri bulundu. Son quartile: {latest_quartile}")
            return latest_quartile, categories_info, years_list, r.url
        else:
            print("Hiç quartile verisi bulunamadı!")
            
        return None, [], [], r.url

    except Exception as e:
        print(f"SCImago genel hata: {e}")
        return None, [], [], scimago_url

# ----------------------------------------
# Flask Rotaları
# ----------------------------------------
@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        title = request.form["title"]
        
        # 1. Adım: CrossRef
        journal, issn, year = get_journal_info(title)
        
        # 2. Adım: SCImago
        quartile, categories, years, url = get_quartile_from_sjr(issn)
        
        # Yıla göre eşleştirme mantığı
        year_categories = []
        has_exact = False
        
        if year and categories:
            # Tam yıl eşleşmesi ara
            matches = [c for c in categories if c['year'] == year]
            if matches:
                year_categories = matches
                has_exact = True
            else:
                # Yoksa en yakın yılı bul
                # Kategorileri tekilleştir
                unique_cats = list(set(c['category'] for c in categories))
                for cat_name in unique_cats:
                    cat_entries = [c for c in categories if c['category'] == cat_name]
                    if cat_entries:
                        closest = min(cat_entries, key=lambda x: abs(x['year'] - year))
                        year_categories.append(closest)

        result = {
            "title": title,
            "journal": journal or "Bulunamadı",
            "issn": issn or "Bulunamadı",
            "year": year or "Bulunamadı",
            "quartile": quartile or "Bulunamadı",
            "categories": categories,
            "years": years,
            "scimago_url": url,
            "year_categories": year_categories,
            "has_exact_year": has_exact
        }
    
    return render_template("index.html", result=result)

@app.route('/excel-upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        if file and file.filename.endswith(('.xlsx', '.xls')):
            try:
                # Orijinal Excel'i oku
                df = pd.read_excel(file, engine='openpyxl')
                
                # Yeni sütunlar için boş listeler
                new_data = {
                    'Bulunan Dergi': [],
                    'Bulunan ISSN': [],
                    'Yayın Yılı': [],
                    'Genel Son Quartile': [],
                    'Makale Yılı Quartile': [],
                    'Kaynak URL': []
                }
                
                # Her satırı işle
                for index, row in df.iterrows():
                    title = str(row.iloc[0]) # İlk sütunu başlık varsayıyoruz
                    
                    if not title or title.lower() == 'nan':
                        # Boş satırsa boş geç
                        for key in new_data: new_data[key].append("")
                        continue
                        
                    # Verileri Çek
                    journal, issn, year = get_journal_info(title)
                    quartile, categories, _, url = get_quartile_from_sjr(issn)
                    
                    # Makale yılındaki quartile'ı hesapla
                    article_year_q = "Bulunamadı"
                    if year and categories:
                        matches = [c['quartile'] for c in categories if c['year'] == year]
                        if matches:
                            article_year_q = ", ".join(list(set(matches)))
                        else:
                            # En yakını bul
                            closest = min(categories, key=lambda x: abs(x['year'] - year))
                            article_year_q = f"{closest['quartile']} (En yakın yıl: {closest['year']})"
                    
                    # Listelere ekle
                    new_data['Bulunan Dergi'].append(journal or "Bulunamadı")
                    new_data['Bulunan ISSN'].append(issn or "Bulunamadı")
                    new_data['Yayın Yılı'].append(year or "Bulunamadı")
                    new_data['Genel Son Quartile'].append(quartile or "Bulunamadı")
                    new_data['Makale Yılı Quartile'].append(article_year_q)
                    new_data['Kaynak URL'].append(url or "")

                # Yeni verileri DataFrame'e ekle
                for key, value in new_data.items():
                    df[key] = value
                
                # Excel oluştur
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                output.seek(0)
                
                filename = f'analiz_sonuc_{datetime.now().strftime("%H%M%S")}.xlsx'
                return send_file(output, download_name=filename, as_attachment=True)
                
            except Exception as e:
                return f"Hata oluştu: {str(e)}"
                
    return render_template("index.html") # Basitlik için ana sayfaya yönlendiriyoruz veya ayrı sayfa yapılabilir

if __name__ == "__main__":
    app.run(debug=False)