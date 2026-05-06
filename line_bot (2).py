"""
line_bot.py
-----------
LINE Messaging API 推送模組（Push Message 到群組）
支援 Flex Message 卡片格式，用於可轉債公告通知
"""

import os
import json
import requests
from datetime import datetime

# ── 從環境變數讀取（存在 GitHub Secrets）──
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_GROUP_ID = os.environ.get("LINE_GROUP_ID", "")  # C 開頭的群組 ID

PUSH_URL = "https://api.line.me/v2/bot/message/push"


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }


# ────────────────────────────────────────────
# Flex Message 卡片建構
# ────────────────────────────────────────────

def build_announcement_card(ann: dict) -> dict:
    """
    單筆公告 → Flex Message bubble card

    ann 欄位預期：
      - stock_id   : str  e.g. "2330"
      - company    : str  e.g. "台積電"
      - market     : str  "上市" | "上櫃"
      - date       : str  e.g. "2025-05-04"
      - title      : str  公告主旨
      - doc_url    : str  MOPS 連結
    """
    market_color = "#00897B" if ann.get("market") == "上市" else "#1565C0"
    market_label = ann.get("market", "上市")
    stock_id = ann.get("stock_id", "----")
    company = ann.get("company", "未知公司")
    date_str = ann.get("date", "")
    title = ann.get("title", "無主旨")
    # 確保 doc_url 不為空（LINE 不接受空字串 URI）
    doc_url = ann.get("doc_url", "") or "https://mops.twse.com.tw/mops/web/t51sb10"

    # 截短標題防止 Flex 爆版
    short_title = title[:45] + "…" if len(title) > 45 else title

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": market_label,
                            "color": "#FFFFFF",
                            "size": "xxs",
                            "weight": "bold",
                        }
                    ],
                    "backgroundColor": market_color,
                    "paddingAll": "4px",
                    "cornerRadius": "4px",
                    "width": "36px",
                },
                {
                    "type": "text",
                    "text": f"{stock_id}　{company}",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#111111",
                    "flex": 1,
                    "margin": "md",
                    "wrap": False,
                },
            ],
            "backgroundColor": "#F5F5F5",
            "paddingAll": "12px",
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": short_title,
                    "size": "sm",
                    "color": "#333333",
                    "wrap": True,
                    "margin": "none",
                },
                {
                    "type": "separator",
                    "margin": "md",
                    "color": "#E0E0E0",
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "📅 公告日期",
                            "size": "xs",
                            "color": "#888888",
                            "flex": 1,
                        },
                        {
                            "type": "text",
                            "text": date_str,
                            "size": "xs",
                            "color": "#555555",
                            "align": "end",
                        },
                    ],
                    "margin": "md",
                },
            ],
            "paddingAll": "12px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "查看公告",
                        "uri": doc_url,
                    },
                    "style": "primary",
                    "color": "#00897B",
                    "height": "sm",
                }
            ],
            "paddingAll": "10px",
        },
        "styles": {
            "footer": {"separator": True, "separatorColor": "#E0E0E0"},
        },
    }


def build_summary_header(count: int, date_str: str) -> dict:
    """掃描摘要標頭 bubble（放在卡片列最前面）"""
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "🔔 可轉債公告掃描",
                    "weight": "bold",
                    "size": "md",
                    "color": "#111111",
                },
                {
                    "type": "text",
                    "text": f"掃描日期：{date_str}",
                    "size": "xs",
                    "color": "#888888",
                    "margin": "sm",
                },
                {
                    "type": "separator",
                    "margin": "md",
                    "color": "#E0E0E0",
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "今日新增",
                            "size": "sm",
                            "color": "#555555",
                            "flex": 1,
                        },
                        {
                            "type": "text",
                            "text": f"{count} 筆",
                            "weight": "bold",
                            "size": "lg",
                            "color": "#00897B",
                            "align": "end",
                        },
                    ],
                    "margin": "md",
                },
            ],
            "paddingAll": "16px",
        },
        "styles": {
            "body": {"backgroundColor": "#FAFAFA"},
        },
    }


def build_no_news_message(date_str: str) -> dict:
    """當日無新公告時的簡單 Flex bubble"""
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ 可轉債掃描完成",
                    "weight": "bold",
                    "size": "md",
                    "color": "#111111",
                },
                {
                    "type": "text",
                    "text": f"{date_str}",
                    "size": "xs",
                    "color": "#888888",
                    "margin": "sm",
                },
                {
                    "type": "separator",
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": "今日無新增無擔保可轉債公告",
                    "size": "sm",
                    "color": "#666666",
                    "margin": "md",
                    "wrap": True,
                },
            ],
            "paddingAll": "16px",
        },
    }


# ────────────────────────────────────────────
# 主要推送函式
# ────────────────────────────────────────────

def push_announcements(announcements: list[dict]):
    """
    將公告列表推送到 LINE 群組。
    - 無公告 → 推送「無新增」通知
    - 有公告 → 摘要標頭 + 每筆一張卡片（最多 11 張，LINE 限制 12 bubbles）
    """
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_GROUP_ID:
        print("[LINE] 缺少 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_GROUP_ID，跳過推送")
        return

    today = datetime.now().strftime("%Y-%m-%d")

    if not announcements:
        # 無公告
        messages = [{
            "type": "flex",
            "altText": f"【CB掃描】{today} 今日無新增可轉債公告",
            "contents": build_no_news_message(today),
        }]
    else:
        # LINE carousel 最多 12 個 bubble
        # 第一則訊息：摘要標頭 + 前 11 筆
        # 後續每則訊息：最多 12 筆（分批推送）
        # LINE 單次 push 最多 5 則 messages
        messages = []

        # 第一批：摘要 + 前 11 筆
        first_cards = [build_summary_header(len(announcements), today)]
        for ann in announcements[:11]:
            first_cards.append(build_announcement_card(ann))
        messages.append({
            "type": "flex",
            "altText": f"【CB掃描】{today} 發現 {len(announcements)} 筆新公告",
            "contents": {"type": "carousel", "contents": first_cards},
        })

        # 剩餘的每 12 筆一批，最多再加 4 則（LINE 單次上限 5 則）
        remaining = announcements[11:]
        for i in range(0, min(len(remaining), 48), 12):
            batch = remaining[i:i+12]
            batch_cards = [build_announcement_card(ann) for ann in batch]
            start_num = 12 + i
            messages.append({
                "type": "flex",
                "altText": f"【CB掃描】續（第 {start_num+1}–{start_num+len(batch)} 筆）",
                "contents": {"type": "carousel", "contents": batch_cards},
            })
            if len(messages) >= 5:  # LINE 單次最多 5 則
                break

    payload = {
        "to": LINE_GROUP_ID,
        "messages": messages,
    }

    resp = requests.post(PUSH_URL, headers=_headers(), json=payload, timeout=15)

    if resp.status_code == 200:
        print(f"[LINE] 推送成功（{len(announcements)} 筆公告，{len(messages)} 則訊息）")
    else:
        print(f"[LINE] 推送失敗 {resp.status_code}: {resp.text}")
        resp.raise_for_status()


def push_error_alert(error_msg: str):
    """爬蟲異常時推送錯誤警示"""
    today = datetime.now().strftime("%Y-%m-%d")
    flex_msg = {
        "type": "flex",
        "altText": f"【CB掃描】{today} 執行錯誤",
        "contents": {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "⚠️ 掃描執行錯誤",
                        "weight": "bold",
                        "size": "md",
                        "color": "#D32F2F",
                    },
                    {
                        "type": "text",
                        "text": f"{today}",
                        "size": "xs",
                        "color": "#888888",
                        "margin": "sm",
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                    },
                    {
                        "type": "text",
                        "text": str(error_msg)[:200],
                        "size": "xs",
                        "color": "#555555",
                        "wrap": True,
                        "margin": "md",
                    },
                ],
                "paddingAll": "16px",
            },
        },
    }

    payload = {"to": LINE_GROUP_ID, "messages": [flex_msg]}
    requests.post(PUSH_URL, headers=_headers(), json=payload, timeout=15)
