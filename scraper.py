import sys
import json
import time
import requests
import urllib3
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from line_bot import push_announcements, push_error_alert

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("Python:", sys.version)
print("Starting...")

BASE_URL = "https://mops.twse.com.tw"
DATA_FILE = "data.json"
SEEN_IDS_FILE = "data/seen_ids.json"
KEEP_MONTHS = 3

# 兩組關鍵字
KEYWORDS = {
    "unsecured": "無擔保轉換公司債",
    "secured":   "有擔保可轉換公司債",
}


def get_roc_year():
    return datetime.now().year - 1911


def roc_date_to_datetime(roc_str):
    try:
        parts = roc_str.strip().split("/")
        if len(parts) == 3:
            year = int(parts[0]) + 1911
            return datetime(year, int(parts[1]), int(parts[2]))
    except Exception:
        pass
    return None


def roc_date_to_iso(roc_str):
    try:
        parts = roc_str.strip().split("/")
        if len(parts) == 3:
            year = int(parts[0]) + 1911
            return f"{year}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
    except Exception:
        pass
    return roc_str


def decode_response(resp):
    for enc in ["utf-8", "big5", "cp950"]:
        try:
            return resp.content.decode(enc)
        except Exception:
            continue
    return resp.text


def search_market(keyword, market_type, year):
    kind = "L" if market_type == "sii" else "O"
    market_label = "上市" if market_type == "sii" else "上櫃"
    print(f"  Searching: {market_label} year:{year} [{keyword}]")

    api_url = BASE_URL + "/mops/api/redirectToOld"
    payload = {
        "apiName": "ajax_t51sb10",
        "parameters": {
            "r1": "1",
            "keyWord": keyword,
            "keyWord2": "",
            "year": str(year),
            "Orderby": "1",
            "KIND": kind,
            "CODE": "",
            "Condition2": "1",
            "month1": "0",
            "begin_day": "",
            "end_day": "",
            "encodeURIComponent": 1,
            "step": "1",
            "Stp": 4,
            "firstin": True,
            "off": 1,
            "go": False,
        }
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Referer": BASE_URL + "/mops/",
        "Origin": BASE_URL,
    }

    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=30, verify=False)
        data = resp.json()
        print("    Step1 HTTP:", resp.status_code, "message:", data.get("message", ""))
    except Exception as e:
        print("    Step1 ERROR:", e)
        return []

    if data.get("code") != 200:
        print("    Step1 failed:", data)
        return []

    old_url = data.get("result", {}).get("url", "")
    if not old_url:
        print("    No redirect URL")
        return []

    try:
        resp2 = requests.get(old_url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": BASE_URL + "/mops/",
        }, timeout=30, verify=False)
        text = decode_response(resp2)
        print("    Step2 HTTP:", resp2.status_code, "length:", len(text))
    except Exception as e:
        print("    Step2 ERROR:", e)
        return []

    if "查無資料" in text:
        print("    No data found")
        return []

    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table", {"class": "hasBorder"}) or soup.find("table")
    if not table:
        return []

    results = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        code     = cells[0].get_text(strip=True)
        name     = cells[1].get_text(strip=True)
        date_str = cells[2].get_text(strip=True)
        seq      = cells[3].get_text(strip=True)
        subject  = cells[4].get_text(strip=True)
        link_tag = cells[4].find("a")
        href = ""
        if link_tag and link_tag.get("href"):
            h = link_tag["href"]
            href = h if h.startswith("http") else BASE_URL + h

        results.append({
            "股票代碼": code,
            "公司名稱": name,
            "市場別": market_label,
            "公告日期": date_str,
            "序號": seq,
            "公告主旨": subject,
            "公告連結": href,
        })

    print(f"    -> {len(results)} records")
    return results


def search_all(keyword, year):
    records = []
    for market in ["sii", "otc"]:
        records += search_market(keyword, market, year)
        time.sleep(2)
    if datetime.now().month <= 3:
        print("  Also fetching previous year...")
        for market in ["sii", "otc"]:
            records += search_market(keyword, market, year - 1)
            time.sleep(2)
    return records


def load_existing():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("records", [])
    except Exception:
        return []


def merge_and_dedupe(old_records, new_records):
    seen = set()
    merged = []
    for r in new_records + old_records:
        key = (r.get("type", ""), r.get("股票代碼", ""),
               r.get("公告日期", ""), r.get("公告主旨", "")[:20])
        if key not in seen:
            seen.add(key)
            merged.append(r)
    return merged


def filter_last_n_months(records, months=3):
    cutoff = datetime.now() - timedelta(days=months * 31)
    kept = []
    for r in records:
        d = roc_date_to_datetime(r.get("公告日期", ""))
        if d is None or d >= cutoff:
            kept.append(r)
    return kept


def load_seen_ids() -> set:
    try:
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen_ids(ids: set):
    import os
    os.makedirs("data", exist_ok=True)
    with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=2)


def make_ann_id(r: dict) -> str:
    return f"{r.get('type','')}__{r.get('股票代碼','')}_{r.get('公告日期','')}_{r.get('公告主旨','')[:20]}"


def to_line_format(r: dict) -> dict:
    return {
        "stock_id": r.get("股票代碼", ""),
        "company":  r.get("公司名稱", ""),
        "market":   r.get("市場別", ""),
        "date":     roc_date_to_iso(r.get("公告日期", "")),
        "title":    r.get("公告主旨", ""),
        "doc_url":  r.get("公告連結", "") or "https://mops.twse.com.tw/",
    }


def main():
    year = get_roc_year()
    print("ROC Year:", year)

    try:
        # 抓取兩組關鍵字
        all_new = []
        new_by_type = {}
        for ktype, kw in KEYWORDS.items():
            print(f"\n=== [{ktype}] {kw} ===")
            records = search_all(kw, year)
            for r in records:
                r["type"] = ktype
            new_by_type[ktype] = records
            all_new += records

        # 合併舊資料
        print("\nMerging with existing records...")
        old_records = load_existing()
        print("  Existing:", len(old_records))
        merged = merge_and_dedupe(old_records, all_new)
        filtered = filter_last_n_months(merged, KEEP_MONTHS)
        filtered.sort(key=lambda r: r.get("公告日期", ""), reverse=True)
        print("  After filter:", len(filtered))

        # 寫入 data.json
        output = {
            "year": year,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M UTC+8"),
            "keywords": KEYWORDS,
            "keep_months": KEEP_MONTHS,
            "total": len(filtered),
            "records": filtered,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(filtered)} records -> {DATA_FILE}")

        # LINE 推送：比對 seen_ids，找出新增的
        seen_ids = load_seen_ids()

        for ktype, kw in KEYWORDS.items():
            new_recs = new_by_type.get(ktype, [])
            new_to_push = [r for r in new_recs if make_ann_id(r) not in seen_ids]
            print(f"\nLINE [{ktype}] 新增 {len(new_to_push)} 筆")
            push_announcements(
                announcements=[to_line_format(r) for r in new_to_push],
                keyword_label=kw,
                keyword_type=ktype,
            )

        # 更新 seen_ids
        all_ids = seen_ids | {make_ann_id(r) for r in all_new}
        save_seen_ids(all_ids)

    except Exception as e:
        import traceback
        print("ERROR:", traceback.format_exc())
        push_error_alert(str(e))
        raise


main()
