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
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

STORE_ID = "413"  # שופרסל אונליין
LIST_URL = f"https://prices.shufersal.co.il/FileObject/UpdateCategory?catID=2&storeId={STORE_ID}"
OUT_FILE = "shufersal.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def download_latest() -> bytes:
    """טוען את עמוד הרשימה, מוצא את הלינק העדכני ל-PriceFull של הסניף ומוריד אותו."""
    req = urllib.request.Request(LIST_URL, headers=HEADERS)
    page = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")

    links = re.findall(r'href="([^"]+)"', page)
    pattern = re.compile(rf"PriceFull\d+-\d+-{STORE_ID}-(\d{{8}}-\d{{6}})")
    candidates = []
    for link in links:
        link = html.unescape(link)
        m = pattern.search(link)
        if m:
            candidates.append((m.group(1), link))
    if not candidates:
        raise RuntimeError("לא נמצא קובץ PriceFull לסניף " + STORE_ID + " בעמוד הרשימה")

    candidates.sort()               # לפי תאריך-שעה שבשם הקובץ
    url = candidates[-1][1]         # העדכני ביותר
    print("מוריד:", url.split("?")[0])
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=120).read()


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
    else:
        gz_bytes = download_latest()

    prices = parse(gz_bytes)
    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "store": STORE_ID,
        "prices": prices,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"), ensure_ascii=False)
    print("נכתב", OUT_FILE)


if __name__ == "__main__":
    main()
