"""
מוריד את קובץ PriceFull של שופרסל אונליין (סניף 413) מאתר השקיפות,
ושומר shufersal.json קטן: ברקוד -> מחיר רגיל.
מוצרים שנמכרים לפי משקל מסוננים.

הרצה רגילה (מוריד מהאינטרנט):   python fetch_prices.py
הרצה על קובץ מקומי (לבדיקה):     python fetch_prices.py PriceFull...gz
"""
import gzip
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

STORE_ID = "413"  # שופרסל אונליין
LIST_URL = f"https://prices.shufersal.co.il/FileObject/UpdateCategory?catID=2&storeId={STORE_ID}"
OUT_FILE = "shufersal.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
}
FILE_RE = re.compile(rf"PriceFull\d+-\d+-{STORE_ID}-(\d{{8}}-\d{{6}})")


BLOB_BASE = "https://pricesprodpublic.blob.core.windows.net/pricefull"
BLOB_LIST = BLOB_BASE + f"?restype=container&comp=list&prefix=PriceFull7290027600007-002-{STORE_ID}-"


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


def probe(label: str, url: str):
    """בדיקת אבחון: האם השרת עונה בכלל (כל תשובה, גם שגיאה, = השרת נגיש)."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        r = urllib.request.urlopen(req, timeout=20)
        print(f"[אבחון] {label}: עונה (קוד {r.status})")
    except urllib.error.HTTPError as e:
        print(f"[אבחון] {label}: עונה (קוד {e.code})")
    except Exception as e:
        print(f"[אבחון] {label}: לא עונה ({e!r})")


def file_time(name: str) -> str:
    """מחלץ את זמן הפרסום משם הקובץ: 20260927-034000 -> 2026-09-27T03:40:00"""
    m = FILE_RE.search(name)
    if not m:
        return ""
    d, t = m.group(1).split("-")
    return f"{d[:4]}-{d[4:6]}-{d[6:]}T{t[:2]}:{t[2:4]}:{t[4:]}"


def via_list_page() -> tuple:
    """דרך א: עמוד הרשימה של אתר השקיפות."""
    page = fetch(LIST_URL, timeout=60, attempts=2).decode("utf-8", "ignore")
    candidates = []
    for link in re.findall(r'href="([^"]+)"', page):
        link = html.unescape(link)
        m = FILE_RE.search(link)
        if m:
            candidates.append((m.group(1), link))
    if not candidates:
        raise RuntimeError("לא נמצא קובץ PriceFull לסניף " + STORE_ID + " בעמוד הרשימה")
    candidates.sort()
    url = candidates[-1][1]
    name = url.split("?")[0]
    print("מוריד:", name)
    return fetch(url, timeout=180), file_time(name)


def via_blob() -> tuple:
    """דרך ב: ישירות משרת הקבצים (עובד רק אם הרשימה שם פתוחה לציבור)."""
    xml_text = fetch(BLOB_LIST, timeout=60, attempts=2).decode("utf-8", "ignore")
    names = sorted(re.findall(r"<Name>([^<]+)</Name>", xml_text), key=file_time)
    if not names:
        raise RuntimeError("שרת הקבצים ענה, אבל בלי קבצים של סניף " + STORE_ID)
    name = names[-1]
    print("מוריד:", name)
    return fetch(f"{BLOB_BASE}/{name}", timeout=180), file_time(name)


def download_latest() -> tuple:
    probe("אתר השקיפות", "https://prices.shufersal.co.il/")
    probe("שרת הקבצים", BLOB_BASE + "?restype=container")
    probe("האתר הראשי של שופרסל", "https://www.shufersal.co.il/")
    probe("אתר ביקורת (Google)", "https://www.google.com/")

    print("דרך א: עמוד הרשימה")
    try:
        return via_list_page()
    except Exception as e:
        print("דרך א נכשלה:", repr(e))
    print("דרך ב: ישירות משרת הקבצים")
    return via_blob()


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
    print(f"נשמרו {len(prices)} מוצרים, סוננו {skipped_weighted} מוצרים לפי משקל")
    if len(prices) < 1000:
        # הגנה: אם משהו השתבש, לא לדרוס את הקובץ הקיים בקובץ כמעט ריק
        raise RuntimeError(f"רק {len(prices)} מוצרים — נראה שמשהו השתבש, לא שומר")
    return prices


def main():
    if len(sys.argv) > 1:
        gz_bytes = open(sys.argv[1], "rb").read()
        published = file_time(sys.argv[1])
    else:
        gz_bytes, published = download_latest()

    prices = parse(gz_bytes)
    out = {
        # מתי שופרסל פרסמו את הקובץ (שעון ישראל), לא מתי הסקריפט רץ
        "updated": published,
        "store": STORE_ID,
        "prices": prices,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    print("נכתב", OUT_FILE)


if __name__ == "__main__":
    main()
