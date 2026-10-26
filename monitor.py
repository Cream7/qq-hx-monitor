#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ华夏 充值活动监控
- 源1：Playwright 渲染主页 main.shtml，抓 #roll_adbtn 轮播区真实链接
- 源2：官网新闻列表页（服务端渲染）
发现新充值活动 → 推送通知。
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse
from datetime import datetime

# ---------- 配置 ----------
BASE = "http://qqhx.qq.com"
NEWS_URL = f"{BASE}/webplat/info/news_version3/607/1262/m1099/list_1.shtml"
MAIN_URL = f"{BASE}/main.shtml"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

# 排除词（命中即不通知）：账号处罚/封禁类
EXCLUDE = [
    "处罚", "封禁", "封号", "违规", "第三方软件", "外挂",
    "打击", "线下交易", "防骗", "安全公告",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": BASE + "/",
}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


# ---------- 源1：Playwright 渲染主页轮播 ----------
def grab_roll_ad():
    """用 Playwright 打开 main.shtml，等 #roll_adbtn 渲染完，抓所有 a 链接。"""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(user_agent=HEADERS["User-Agent"])
        page.goto(MAIN_URL, timeout=30000, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#roll_adbtn a", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(2000)  # 等 JS 灌数据
        items = page.eval_on_selector_all(
            "#roll_adbtn a",
            "els => els.map(a => ({text: (a.textContent||'').trim(), href: a.href}))"
        )
        browser.close()
    return items


# ---------- 源2：新闻列表 ----------
def parse_news(html: str):
    items = []
    pat = re.compile(
        r'<a[^>]+href="([^"]+)"[^>]*class="link"[^>]*>([^<]{4,100})</a>'
        r'[^<]*<span[^>]*class="time"[^>]*>(\d{4}-\d{2}-\d{2})',
        re.S,
    )
    for m in pat.finditer(html):
        href, title, date = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        title = re.sub(r"\s+", " ", title)
        if href.startswith("/"):
            href = BASE + href
        items.append({"title": title, "url": href, "date": date})
    seen, uniq = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    return uniq


def is_interesting(title: str) -> bool:
    """除了处罚/封禁类，其他新动态都通知。"""
    if not title or len(title.strip()) < 2:
        return False
    return not any(w in title for w in EXCLUDE)


# ---------- 推送渠道 ----------
def push_serverchan(title, desp):
    key = os.environ.get("SERVERCHAN_KEY", "").strip()
    if not key: return
    url = f"https://sctapi.ftqq.com/{key}.send"
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode()
    urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=10)


def push_wecom(title, desp):
    wh = os.environ.get("WECOM_WEBHOOK", "").strip()
    if not wh: return
    payload = json.dumps({
        "msgtype": "markdown",
        "markdown": {"content": f"**{title}**\n\n{desp}"},
    }).encode("utf-8")
    req = urllib.request.Request(wh, data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=10)


def push_telegram(title, desp):
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat_id: return
    data = urllib.parse.urlencode({
        "chat_id": chat_id, "text": f"*{title}*\n\n{desp}",
        "parse_mode": "Markdown",
    }).encode()
    urllib.request.urlopen(
        urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                               data=data, method="POST"), timeout=10)


def notify(title, desp):
    channels = [("Server酱", push_serverchan), ("企业微信", push_wecom),
                ("Telegram", push_telegram)]
    hit = False
    for name, fn in channels:
        try:
            fn(title, desp); print(f"[推送成功] {name}"); hit = True
        except Exception as e:
            print(f"[推送失败] {name}: {e}")
    if not hit:
        print("[警告] 未配置推送渠道，通知仅打印在日志中。")


# ---------- 主流程 ----------
def main():
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    # 源1：轮播
    roll_items = []
    try:
        roll_items = grab_roll_ad()
        print(f"轮播链接 {len(roll_items)} 条：")
        for it in roll_items:
            print(f"  - {it['text']}  ->  {it['href']}")
    except Exception as e:
        print(f"[轮播抓取失败] {e}")

    # 源2：新闻列表
    news = parse_news(fetch(NEWS_URL))
    print(f"新闻 {len(news)} 条")

    # 合并候选：轮播 + 新闻，排除处罚类
    candidates = []
    for it in roll_items:
        if is_interesting(it["text"]):
            candidates.append({"title": it["text"], "url": it["href"], "source": "轮播"})
    for n in news:
        if is_interesting(n["title"]):
            candidates.append({"title": n["title"], "url": n["url"],
                               "source": f"新闻·{n['date']}"})

    print(f"\n候选新动态 {len(candidates)} 条：")
    for c in candidates:
        print(f"  - [{c['source']}] {c['title']}  ->  {c['url']}")

    state = load_state()
    seen = set(state.get("seen", []))
    first_run = not state.get("initialized", False)

    if first_run:
        print("首次运行，记录基线，不推送。")
        state["initialized"] = True
        state["seen"] = [c["title"] for c in candidates]
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    new_ones = [c for c in candidates if c["title"] not in seen]
    if not new_ones:
        print("无新增。")
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    print(f"发现 {len(new_ones)} 条新动态！")
    lines = [f"- [{c['source']}] [{c['title']}]({c['url']})" for c in new_ones]
    desp = "QQ华夏官网有新动态：\n\n" + "\n".join(lines)
    notify("【QQ华夏】官网新动态", desp)

    state["seen"] = list((seen | {c["title"] for c in candidates}))[-200:]
    state["last_run"] = datetime.now().isoformat()
    save_state(state)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[错误] {e}", file=sys.stderr)
        sys.exit(1)
