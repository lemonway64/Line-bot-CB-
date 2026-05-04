"""
scraper.py
----------
MOPS 無擔保可轉債公告爬蟲 + LINE Bot 通知整合版

流程：
  1. 呼叫 MOPS 兩步 API 抓取當年度公告（Big5 解碼）
  2. 比對 seen_ids.json（已推送過的公告 ID），排除重複
  3. 將新公告寫回 data/announcements.json（供 GitHub Pages 前端使用）
  4. 更新 seen_ids.json
  5. 透過 line_bot.push_announcements() 推送 LINE 群組
"""

import json
import os
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests

from line_bot import push_announcements, push_error_alert

# ── 設定 ──────────────────────────────────────
MOPS_BASE = "https://mops.twse.com.tw/mops/web"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://mops.twse.com.tw/mops/web/t05st01",
}

# 搜尋關鍵字（符合原本網站邏輯）
KEYWORD = "代收股款行庫及存儲專戶行庫"

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "announcements.json"
SEEN_IDS_FILE = DATA_DIR / "seen_ids.json"

# ────────────────────────────────────────────
# MOPS 爬蟲
# ────────────────────────────────────────────

def mops_session_init():
    """Step 1：初始化 MOPS session，取得必要 cookie"""
    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(f"{MOPS_BASE}/t05st01", timeout=15)
    except Exception:
        pass
    return session


def fetch_mops_page(session: requests.Session, market: str, year: int, page: int = 1) -> list[dict]:
    """
    Step 2：呼叫 MOPS 重大訊息查詢 API
    market: "sii"=上市, "otc"=上櫃
    回傳 list of dict（原始欄位）
    """
    # MOPS 民國年
    roc_year = year - 1911

    payload = {
        "encodeURIComponent": "1",
        "step": "1",
        "firstin": "1",
        "off": "1",
        "keyword4": "",
        "code1": "",
        "TYPEK2": "",
        "checkbtn": "",
        "queryName": "co_id",
        "TYPEK": market,
        "thisCRSY": str(roc_year),
        "keyword": KEYWORD,
        "currentPage": str(page),
        "t05st01_1_pagingType": "10",
    }

    try:
        resp = session.post(
            f"{MOPS_BASE}/t05st01",
            data=payload,
            timeout=20,
        )
        # MOPS 有時回 Big5，嘗試解碼
        try:
            text = resp.content.decode("big5", errors="replace")
        except Exception:
            text = resp.text

        return _parse_mops_html(text, market)

    except Exception as e:
        print(f"[scraper] fetch_mops_page 失敗 market={market} page={page}: {e}")
        return []


def _parse_mops_html(html: str, market: str) -> list[dict]:
    """從 MOPS HTML table 解析公告資料（BeautifulSoup）"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("請安裝 beautifulsoup4: pip install beautifulsoup4")

    soup = BeautifulSoup(html, "html.parser")
    results = []

    table = soup.find("table", class_="hasBorder")
    if not table:
        return results

    rows = table.find_all("tr")[1:]  # 跳過 header
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue
        try:
            # 欄位順序依 MOPS t05st01 實際格式調整
            date_str = cols[0].get_text(strip=True)   # 公告日期 (民國)
            stock_id = cols[1].get_text(strip=True)   # 股票代號
            company  = cols[2].get_text(strip=True)   # 公司名稱
            title    = cols[3].get_text(strip=True)   # 主旨

            # 連結
            a_tag = cols[3].find("a")
            doc_url = ""
            if a_tag and a_tag.get("href"):
                href = a_tag["href"]
                doc_url = href if href.startswith("http") else f"https://mops.twse.com.tw{href}"

            # 民國轉西元日期
            try:
                parts = date_str.replace("/", "-").split("-")
                if len(parts) == 3:
                    ad_year = int(parts[0]) + 1911
                    date_iso = f"{ad_year}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                else:
                    date_iso = date_str
            except Exception:
                date_iso = date_str

            ann_id = f"{stock_id}_{date_iso}_{title[:20]}"  # 簡易唯一 ID

            results.append({
                "id": ann_id,
                "stock_id": stock_id,
                "company": company,
                "market": "上市" if market == "sii" else "上櫃",
                "date": date_iso,
                "title": title,
                "doc_url": doc_url,
            })
        except Exception:
            continue

    return results


def fetch_all_announcements(year: int) -> list[dict]:
    """抓取上市 + 上櫃全部公告（多頁）"""
    session = mops_session_init()
    all_anns = []

    for market in ["sii", "otc"]:
        page = 1
        while True:
            anns = fetch_mops_page(session, market, year, page)
            if not anns:
                break
            all_anns.extend(anns)
            print(f"[scraper] {market} page {page}: {len(anns)} 筆")
            page += 1
            time.sleep(1.2)  # 避免 MOPS 封鎖

    return all_anns


# ────────────────────────────────────────────
# 去重邏輯
# ────────────────────────────────────────────

def load_seen_ids() -> set:
    if SEEN_IDS_FILE.exists():
        try:
            return set(json.loads(SEEN_IDS_FILE.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_seen_ids(ids: set):
    SEEN_IDS_FILE.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def filter_new(announcements: list[dict], seen_ids: set) -> list[dict]:
    return [a for a in announcements if a["id"] not in seen_ids]


# ────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────

def main():
    DATA_DIR.mkdir(exist_ok=True)

    year = datetime.now().year
    print(f"[scraper] 開始掃描 {year} 年度公告...")

    try:
        all_anns = fetch_all_announcements(year)
        print(f"[scraper] 共抓到 {len(all_anns)} 筆公告")

        # 去重
        seen_ids = load_seen_ids()
        new_anns = filter_new(all_anns, seen_ids)
        print(f"[scraper] 新公告（未推送）：{len(new_anns)} 筆")

        # 更新 data/announcements.json（前端用，保存全部）
        # 合併舊資料與新資料（避免 GitHub Pages 前端失去歷史）
        existing = []
        if OUTPUT_FILE.exists():
            try:
                existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = []

        existing_ids = {a["id"] for a in existing}
        merged = existing + [a for a in all_anns if a["id"] not in existing_ids]
        merged.sort(key=lambda x: x.get("date", ""), reverse=True)

        OUTPUT_FILE.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[scraper] 寫入 {OUTPUT_FILE}，共 {len(merged)} 筆")

        # 更新已推送 ID
        new_ids = {a["id"] for a in new_anns}
        save_seen_ids(seen_ids | new_ids)

        # 推送 LINE
        push_announcements(new_anns)

    except Exception as e:
        err_msg = traceback.format_exc()
        print(f"[scraper] 執行錯誤：\n{err_msg}")
        push_error_alert(str(e))
        raise


if __name__ == "__main__":
    main()
