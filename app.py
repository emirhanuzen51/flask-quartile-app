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
# ----------------------------------------
# 2) SCImago: ISSN ile Quartile bul (Cloudscraper ile)
# ----------------------------------------
# ----------------------------------------
# 2) SCImago: ISSN ile Quartile bul
# ----------------------------------------
def fetch_page(url):
    """
    Sayfayı önce standart requests ile (referer ekleyerek),
    olmazsa cloudscraper ile çekmeye çalışır.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }

    try:
        # 1. Yöntem: Standart Requests (Genelde daha hızlı ve Referer ile çalışıyor)
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code == 200:
            return r
        
        # 403 veya başka hata aldıysak devam et
        print(f"Requests {r.status_code} döndü, Cloudscraper deneniyor...")

    except Exception as e:
        print(f"Requests hatası: {e}, Cloudscraper deneniyor...")

    # 2. Yöntem: Cloudscraper
    try:
        scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
        )
        r = scraper.get(url, timeout=25)
        return r
    except Exception as e:
        print(f"Cloudscraper hatası: {e}")
        return None

def get_quartile_from_sjr(issn):
    if not issn:
        return None, [], [], None

    # ISSN temizliği
    issn = issn.replace(' ', '').replace('-', '')
    clean_issn = f"{issn[:4]}-{issn[4:]}" if len(issn) == 8 else issn

    scimago_url = f"https://www.scimagojr.com/journalsearch.php?q={clean_issn}&tip=sid"
    print(f"SCImago Aranıyor: {clean_issn} - URL: {scimago_url}")
    
    # Sayfayı çek
    r = fetch_page(scimago_url)
    
    if not r or r.status_code != 200:
        print("SCImago sitesine erişilemedi.")
        return None, [], [], scimago_url
    
    print(f"URL Erişim Başarılı: {r.url}")

    try:
        soup = BeautifulSoup(r.text, "html.parser")
        
        # Arama sayfası kontrolü
        is_search_page = "journalsearch.php" in r.url and "tip=sid" in r.url
        final_journal_url = r.url

        if is_search_page:
            print("Arama sonuç sayfasındayız...")
            search_results = soup.select('.search_results a')
            
            if search_results:
                # İlk sonuç
                first_link = search_results[0]['href']
                
                # Bazen href full url olabilir, bazen relative
                if not first_link.startswith('http'):
                    final_journal_url = f"https://www.scimagojr.com/{first_link}"
                else:
                    final_journal_url = first_link
                    
                print(f"Dergi detayı bulundu: {final_journal_url}")
                
                # Detay sayfasına git
                r_detail = fetch_page(final_journal_url)
                if r_detail and r_detail.status_code == 200:
                    soup = BeautifulSoup(r_detail.text, "html.parser")
                else:
                    print("Dergi detay sayfası açılamadı.")
                    return None, [], [], final_journal_url
            else:
                print("Arama sonuçlarında hiçbir dergi bulunamadı.")
                return None, [], [], scimago_url
        
        # --- Tablo Arama ---
        categories_info = []
        quartiles_table = None
        
        tables = soup.find_all('table')
        for tbl in tables:
            # Tablo içinde 'Quartile' yazısı arıyoruz
            if 'Quartile' in tbl.get_text():
                quartiles_table = tbl
                print("Quartile veri tablosu bulundu.")
                break
        
        if quartiles_table:
            rows = quartiles_table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 3:
                    try:
                        texts = [c.get_text(strip=True) for c in cols]
                        year = None
                        quartile = None
                        category = texts[0]
                        
                        for t in texts:
                             if t.isdigit() and len(t) == 4:
                                 year = int(t)
                             elif t in ['Q1', 'Q2', 'Q3', 'Q4']:
                                 quartile = t
                        
                        if year and quartile:
                            categories_info.append({
                                'category': category,
                                'year': year,
                                'quartile': quartile
                            })
                    except Exception:
                        continue
        else:
            print("Tablo bulunamadı.")
            # Grid yapısı kontrol eklenebilir ama şimdilik tablo yeterli
            pass

        if categories_info:
            latest_entry = max(categories_info, key=lambda x: x['year'])
            latest_quartile = latest_entry['quartile']
            years_list = sorted(list(set(c['year'] for c in categories_info)))
            
            print(f"Başarılı: En güncel {latest_entry['year']} - {latest_quartile}")
            return latest_quartile, categories_info, years_list, final_journal_url
            
        print("Veri çekilemedi.")
        return None, [], [], final_journal_url

    except Exception as e:
        print(f"Ayrıştırma hatası: {e}")
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
        
        # Her kategori için o yıla ait (veya en yakın) bilgiyi hazırla
        detailed_categories = []
        
        if categories:
            # Kategorileri grupla
            from collections import defaultdict
            cat_map = defaultdict(list)
            for entry in categories:
                cat_map[entry['category']].append(entry)
            
            # Her kategori için en uygun yılı bul
            for cat_name, entries in cat_map.items():
                # Yıla göre sırala
                sorted_entries = sorted(entries, key=lambda x: x['year'])
                
                best_match = None
                is_exact = False
                
                if year:
                    # Tam eşleşme ara
                    exact = next((e for e in sorted_entries if e['year'] == year), None)
                    if exact:
                        best_match = exact
                        is_exact = True
                    else:
                        # En yakını bul
                        best_match = min(sorted_entries, key=lambda x: abs(x['year'] - year))
                        is_exact = False
                else:
                    # Yıl yoksa en günceli al
                    best_match = sorted_entries[-1]
                    is_exact = False # Aslında 'current' ama exact değil
                
                detailed_categories.append({
                    'category': cat_name,
                    'quartile': best_match['quartile'],
                    'year': best_match['year'],
                    'diff': abs(best_match['year'] - year) if year else 0,
                    'is_exact': is_exact
                })
        
        # 3. Adım: Genel Kategorileri Sırala (Kategori İsmi ASC, Yıl DESC)
        # Kullanıcı isteği: Kategoriler alt alta gelsin, karışık olmasın.
        if categories:
            categories.sort(key=lambda x: (x['category'], -x['year']))

        result = {
            "title": title,
            "journal": journal or "Bulunamadı",
            "issn": issn or "Bulunamadı",
            "year": year or "Bulunamadı",
            "quartile": quartile or "Bulunamadı",
            "categories": categories,
            "years": years,
            "scimago_url": url,
            "detailed_categories": detailed_categories
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
                
                # Yeni yapı için liste
                all_output_rows = []
                
                # Her satırı işle
                for index, row in df.iterrows():
                    title = str(row.iloc[0]) # İlk sütunu başlık varsayıyoruz
                    
                    if not title or title.lower() == 'nan':
                        continue
                        
                    # Verileri Çek
                    journal, issn, year = get_journal_info(title)
                    quartile, categories_data, _, url = get_quartile_from_sjr(issn)
                    
                    # Eğer hiç kategori verisi yoksa (Bulunamadıysa)
                    if not categories_data:
                        all_output_rows.append({
                            'Makale Başlığı': title,
                            'Dergi': journal or "Bulunamadı",
                            'ISSN': issn or "Bulunamadı",
                            'Yayın Yılı': year or "Bulunamadı",
                            'Kategori': "Bulunamadı",
                            'Kategori İlk Yıl': "",
                            'Kategori Son Yıl': "",
                            'Kategori İlk Q': "",
                            'Kategori Son Q': "",
                            'Makale Yılı Q': "Bulunamadı",
                            'Genel Son Q': "Bulunamadı",
                            'Kaynak URL': url or ""
                        })
                        continue

                    # Kategorileri grupla
                    # categories_data listesi [{'category': 'X', 'year': 2020, 'quartile': 'Q1'}, ...] şeklindedir
                    # Bunu { 'X': [list of entries], 'Y': [...] } şekline getirelim
                    from collections import defaultdict
                    cat_map = defaultdict(list)
                    for entry in categories_data:
                        cat_map[entry['category']].append(entry)
                    
                    # Her kategori için bir satır oluştur
                    for cat_name, entries in cat_map.items():
                        # Yıla göre sırala
                        sorted_entries = sorted(entries, key=lambda x: x['year'])
                        
                        start_entry = sorted_entries[0]
                        end_entry = sorted_entries[-1]
                        
                        # Makale yılındaki Q değerini bul
                        article_q = "Bulunamadı"
                        if year:
                            # Tam yıl eşleşmesi
                            exact_match = next((e for e in sorted_entries if e['year'] == year), None)
                            if exact_match:
                                article_q = exact_match['quartile']
                            else:
                                # En yakın yıl
                                closest = min(sorted_entries, key=lambda x: abs(x['year'] - year))
                                article_q = f"{closest['quartile']} (En yakın: {closest['year']})"
                        
                        all_output_rows.append({
                            'Makale Başlığı': title,
                            'Dergi': journal,
                            'ISSN': issn,
                            'Yayın Yılı': year,
                            'Kategori': cat_name,
                            'Kategori İlk Yıl': start_entry['year'],
                            'Kategori Son Yıl': end_entry['year'],
                            'Kategori İlk Q': start_entry['quartile'],
                            'Kategori Son Q': end_entry['quartile'],
                            'Makale Yılı Q': article_q,
                            'Genel Son Q': quartile, # Bu derginin genel son durumu
                            'Kaynak URL': url
                        })

                # DataFrame oluştur
                result_df = pd.DataFrame(all_output_rows)
                
                # Excel oluştur
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    result_df.to_excel(writer, index=False)
                output.seek(0)
                
                filename = f'analiz_sonuc_{datetime.now().strftime("%H%M%S")}.xlsx'
                return send_file(output, download_name=filename, as_attachment=True)
                
            except Exception as e:
                return f"Hata oluştu: {str(e)}"
                
    return render_template("index.html", show_upload=True)


if __name__ == "__main__":
    # host='0.0.0.0' yaparak ağdaki diğer cihazların (telefon, diğer pc) erişimine açıyoruz.
    app.run(host='0.0.0.0', port=5000, debug=False)