import requests

url = "https://www.scimagojr.com/journalsearch.php?q=2169-3536&tip=sid"
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/'
}

try:
    print(f"Requesting {url} with simple requests...")
    r = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {r.status_code}")
    print(f"URL: {r.url}")
    print(f"Content length: {len(r.text)}")
    if r.status_code == 200:
        with open("dump.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        if "Quartile" in r.text or "Category" in r.text:
            print("SUCCESS: Found potential content.")
        else:
            print("WARNING: 200 OK but content might be blocked/captcha. Saved to dump.html")

except Exception as e:
    print(f"Error: {e}")
