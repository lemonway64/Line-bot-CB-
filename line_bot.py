"""
line_bot.py - LINE Messaging API 推送模組
支援兩組關鍵字（無擔保 / 有擔保）分別推送 Flex Message
"""

import os
import json
import requests
from datetime import datetime

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_GROUP_ID = os.environ.get("LINE_GROUP_ID", "")

PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 兩組顏色主題
THEME = {
    "unsecured1": {"color": "#00897B", "emoji": "🔵", "label": "無擔保轉換公司債"},
    "unsecured2": {"color": "#0277BD", "emoji": "🔷", "label": "無擔保可轉換公司債"},
    "secured1":   {"color": "#6A1B9A", "emoji": "🟣", "label": "有擔保轉換公司債"},
    "secured2":   {"color": "#1565C0", "emoji": "🟢", "label": "有擔保可轉換公司債"},
}


def _headers():
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }


def build_announcement_card(ann: dict, keyword_type: str) -> dict:
    theme = THEME.get(keyword_type, THEME["secured1"])
    market_color = "#00897B" if ann.get("market") == "上市" else "#1565C0"
    doc_url = ann.get("doc_url", "") or "https://mops.twse.com.tw/mops/web/t51sb10"
    short_title = ann.get("title", "無主旨")
    if len(short_title) > 45:
        short_title = short_title[:45] + "…"

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
                    "contents": [{"type": "text", "text": ann.get("market", ""), "color": "#FFFFFF", "size": "xxs", "weight": "bold"}],
                    "backgroundColor": market_color,
                    "paddingAll": "4px",
                    "cornerRadius": "4px",
                    "width": "36px",
                },
                {
                    "type": "text",
                    "text": f"{ann.get('stock_id','')}　{ann.get('company','')}",
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
                {"type": "text", "text": short_title, "size": "sm", "color": "#333333", "wrap": True},
                {"type": "separator", "margin": "md", "color": "#E0E0E0"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "📅 公告日期", "size": "xs", "color": "#888888", "flex": 1},
                        {"type": "text", "text": ann.get("date", ""), "size": "xs", "color": "#555555", "align": "end"},
                    ],
                    "margin": "md",
                },
            ],
            "paddingAll": "12px",
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [{
                "type": "button",
                "action": {"type": "uri", "label": "查看公告", "uri": doc_url},
                "style": "primary",
                "color": theme["color"],
                "height": "sm",
            }],
            "paddingAll": "10px",
        },
        "styles": {"footer": {"separator": True, "separatorColor": "#E0E0E0"}},
    }


def build_summary_header(count: int, date_str: str, keyword_label: str, keyword_type: str) -> dict:
    theme = THEME.get(keyword_type, THEME["secured1"])
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"{theme['emoji']} {keyword_label}", "weight": "bold", "size": "md", "color": "#111111"},
                {"type": "text", "text": f"掃描日期：{date_str}", "size": "xs", "color": "#888888", "margin": "sm"},
                {"type": "separator", "margin": "md", "color": "#E0E0E0"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "今日新增", "size": "sm", "color": "#555555", "flex": 1},
                        {"type": "text", "text": f"{count} 筆", "weight": "bold", "size": "lg", "color": theme["color"], "align": "end"},
                    ],
                    "margin": "md",
                },
            ],
            "paddingAll": "16px",
        },
        "styles": {"body": {"backgroundColor": "#FAFAFA"}},
    }


def build_no_news_bubble(date_str: str, keyword_label: str, keyword_type: str) -> dict:
    theme = THEME.get(keyword_type, THEME["secured1"])
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": f"{theme['emoji']} {keyword_label}", "weight": "bold", "size": "md", "color": "#111111"},
                {"type": "text", "text": f"{date_str}", "size": "xs", "color": "#888888", "margin": "sm"},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "今日無新增公告", "size": "sm", "color": "#666666", "margin": "md", "wrap": True},
            ],
            "paddingAll": "16px",
        },
    }


def push_announcements(announcements: list, keyword_label: str = "", keyword_type: str = "unsecured"):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_GROUP_ID:
        print("[LINE] 缺少憑證，跳過推送")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    messages = []

    if not announcements:
        messages.append({
            "type": "flex",
            "altText": f"【CB掃描】{keyword_label} {today} 今日無新增",
            "contents": build_no_news_bubble(today, keyword_label, keyword_type),
        })
    else:
        # 第一批：摘要 header + 前 11 筆
        first_cards = [build_summary_header(len(announcements), today, keyword_label, keyword_type)]
        for ann in announcements[:11]:
            first_cards.append(build_announcement_card(ann, keyword_type))
        messages.append({
            "type": "flex",
            "altText": f"【CB掃描】{keyword_label} {today} 新增 {len(announcements)} 筆",
            "contents": {"type": "carousel", "contents": first_cards},
        })

        # 超過 11 筆則分批（LINE 單次 push 最多 5 則 messages）
        remaining = announcements[11:]
        for i in range(0, min(len(remaining), 48), 12):
            if len(messages) >= 5:
                break
            batch = remaining[i:i+12]
            messages.append({
                "type": "flex",
                "altText": f"【CB掃描】{keyword_label} 續...",
                "contents": {"type": "carousel", "contents": [build_announcement_card(a, keyword_type) for a in batch]},
            })

    payload = {"to": LINE_GROUP_ID, "messages": messages}
    resp = requests.post(PUSH_URL, headers=_headers(), json=payload, timeout=15)

    if resp.status_code == 200:
        print(f"[LINE] ✅ {keyword_label} 推送成功（{len(announcements)} 筆）")
    else:
        print(f"[LINE] ❌ {keyword_label} 推送失敗 {resp.status_code}: {resp.text}")
        resp.raise_for_status()


def push_error_alert(error_msg: str):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_GROUP_ID:
        return
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
                    {"type": "text", "text": "⚠️ 掃描執行錯誤", "weight": "bold", "size": "md", "color": "#D32F2F"},
                    {"type": "text", "text": today, "size": "xs", "color": "#888888", "margin": "sm"},
                    {"type": "separator", "margin": "md"},
                    {"type": "text", "text": str(error_msg)[:200], "size": "xs", "color": "#555555", "wrap": True, "margin": "md"},
                ],
                "paddingAll": "16px",
            },
        },
    }
    payload = {"to": LINE_GROUP_ID, "messages": [flex_msg]}
    requests.post(PUSH_URL, headers=_headers(), json=payload, timeout=15)
