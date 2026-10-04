"""
מוריד קבצי PriceFull מאתר השקיפות של שופרסל, לכמה סניפים,
ושומר לכל סניף קובץ JSON קטן: ברקוד -> מחיר רגיל (כולל מע"מ).
מוצרים שנמכרים לפי משקל מסוננים.
 
הרצה רגילה (מוריד מהאינטרנט):   python fetch_prices.py
הרצה על קובץ מקומי (לבדיקה):     python fetch_prices.py PriceFull...gz
   (מספר הסניף נלקח משם הקובץ)
"""
import gzip
import html
import json
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
 
# סניף -> קובץ פלט
STORES = {
    "413": "shufersal.json",   # שופרסל אונליין (מחיר לצרכן)
    "161": "hamafitz.json",    # המפיץ סיטונאות אשדוד (מחיר זהה לבאר שבע ולבאר יעקב)
}
 
LIST_URL = "https://prices.shufersal.co.il/FileObject/UpdateCategory?catID=2&storeId={store}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}
# PriceFull<רשת>-<תת-רשת>-<סניף>-<תאריך>-<שעה>
FILE_RE = re.compile(r"PriceFull\d+-\d+-(\d+)-(\d{8}-\d{6})")
 
 
def fetch(url: str, timeout: int, attempts: int = 3) -> bytes:
    """מוריד כתובת, עם כמה ניסיונות והמתנה הולכת וגדלה ביניהם."""
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except Exception as e:
            print(f"  ניסיון {attempt} נכשל: {e!r}")
            if attempt == attempts:
                raise
            time.sleep(15 * attempt)
 
 
def file_info(name: str):
    """משם הקובץ: (מספר סניף, זמן פרסום). 20260927-034000 -> 2026-09-27T03:40:00"""
    m = FILE_RE.search(name)
    if not m:
        return None, ""
    store = m.group(1).lstrip("0")
    d, t = m.group(2).split("-")
    return store, f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}"
 
 
def download_latest(store: str) -> tuple:
    """טוען את עמוד הרשימה של הסניף, מוצא את ה-PriceFull העדכני ומוריד אותו."""
    page = fetch(LIST_URL.format(store=store), timeout=60).decode("utf-8", "ignore")
    candidates = []
    for link in re.findall(r'href="([^"]+)"', page):
        link = html.unescape(link)
        s, published = file_info(link)
        if s == store:
            candidates.append((published, link))
    if not candidates:
        raise RuntimeError(f"לא נמצא קובץ PriceFull לסניף {store} בעמוד הרשימה")
    candidates.sort()
    published, url = candidates[-1]
    print("  מוריד:", url.split("?")[0])
    return fetch(url, timeout=180), published
 
 
def parse(gz_bytes: bytes) -> dict:
    root = ET.fromstring(gzip.decompress(gz_bytes).decode("utf-8-sig"))
    prices = {}
    skipped_weighted = 0
    for item in root.iter("Item"):
        if item.findtext("bIsWeighted") == "1":
            skipped_weighted += 1
            continue
        code = (item.findtext("ItemCode") or "").strip().lstrip("0")
        price = item.findtext("ItemPrice")
        if not code or not price:
            continue
        try:
            prices[code] = round(float(price), 2)
        except ValueError:
            continue
    print(f"  נשמרו {len(prices)} מוצרים, סוננו {skipped_weighted} מוצרים לפי משקל")
    if len(prices) < 1000:
        # הגנה: אם משהו השתבש, לא לדרוס את הקובץ הקיים בקובץ כמעט ריק
        raise RuntimeError(f"רק {len(prices)} מוצרים — נראה שמשהו השתבש, לא שומר")
    return prices
 
 
def save(store: str, published: str, prices: dict):
    out = {
        "updated": published,   # מתי שופרסל פרסמו את הקובץ (שעון ישראל)
        "store": store,
        "prices": prices,
    }
    with open(STORES[store], "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    print("  נכתב", STORES[store])
 
 
def main():
    if len(sys.argv) > 1:
        # מצב בדיקה: קובץ מקומי אחד
        store, published = file_info(sys.argv[1])
        if store not in STORES:
            raise SystemExit(f"סניף {store} לא ברשימת STORES")
        save(store, published, parse(open(sys.argv[1], "rb").read()))
        return
 
    failed = []
    for store in STORES:
        print(f"סניף {store}:")
        try:
            gz_bytes, published = download_latest(store)
            save(store, published, parse(gz_bytes))
        except Exception as e:
            # סניף שנכשל לא עוצר את האחרים; הקובץ הקודם שלו נשאר כמו שהוא
            print(f"  נכשל: {e!r}")
            failed.append(store)
 
    if failed:
        # יציאה עם שגיאה כדי ש-GitHub ישלח מייל, אחרי שכל מה שהצליח כבר נשמר
        sys.exit(f"נכשלו הסניפים: {', '.join(failed)}")
 
 
if __name__ == "__main__":
    main()
 
