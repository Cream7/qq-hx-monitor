#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ华夏 充值活动监控
- 源1：官网新闻列表页（服务端渲染，稳定）
- 源2：主页 main.shtml 全页扫描 /cp/ 活动链接
发现新活动链接或新充值类新闻 → 推送通知。
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

# 充值类新闻关键词（标题命中任一即视为充值活动）
NEWS_KEYWORDS = [
    "充值", "回馈", "限时充", "充返", "返利", "送元宝", "送点券",
    "充值送", "充值得", "充值大", "充值好礼", "福利充", "特惠充",
]
# 排除词
EXCLUDE = ["处罚", "打击", "违规", "维护公告", "合区", "数据互通",
           "问卷", "封号", "防骗", "安全", "线下交易"]

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


# ---------- 源1：新闻列表 ----------
def parse_news(html: str):
    """
    页面实际结构：
      <a href="..." target="_blank" class="link">标题</a><span class="time">2026-10-19</span>
    """
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
    # 去重
    seen, uniq = set(), []
    for it in items:
        if it["title"] not in seen:
            seen.add(it["title"])
            uniq.append(it)
    return uniq


def is_recharge_news(title: str) -> bool:
    if any(w in title for w in EXCLUDE):
        return False
    return any(w in title for w in NEWS_KEYWORDS)


# ---------- 源2：主页 /cp/ 活动链接 ----------
def scan_cp_links(html: str):
    """从主页HTML里提取所有 qqhx.qq.com/cp/ 活动链接。"""
    links = set()
    for u in re.findall(r'href="(https?://qqhx\.qq\.com/cp/[^"#]+)"', html):
        # 去掉查询参数，只留路径部分做指纹
        path = u.split("?")[0].rstrip("/")
        links.add(path)
    return sorted(links)


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


def push_bark(title, desp):
    key = os.environ.get("BARK_KEY", "").strip()
    if not key: return
    t = urllib.parse.quote(title); b = urllib.parse.quote(desp)
    urllib.request.urlopen(f"https://api.day.app/{key}/{t}/{b}", timeout=10)


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
                ("Bark", push_bark), ("Telegram", push_telegram)]
    hit = False
    for name, fn in channels:
        try:
            fn(title, desp); print(f"[推送成功] {name}"); hit = True
        except Exception as e:
            print(f"[推送失败] {name}: {e}")
    if not hit:
        print("[警告] 未配置任何推送渠道，通知仅打印在日志中。")


# ---------- 主流程 ----------
def main():
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")

    # 抓两个源
    news_html = fetch(NEWS_URL)
    main_html = fetch(MAIN_URL)

    news = parse_news(news_html)
    cp_links = scan_cp_links(main_html)
    print(f"新闻 {len(news)} 条；主页 /cp/ 活动链接 {len(cp_links)} 个")

    recharge_news = [n for n in news if is_recharge_news(n["title"])]
    print("命中充值类新闻：")
    for n in recharge_news:
        print(f"  - [{n['date']}] {n['title']}")
    print("当前 /cp/ 活动链接：")
    for u in cp_links:
        print(f"  - {u}")

    state = load_state()
    seen_news = set(state.get("seen_news", []))
    seen_cp = set(state.get("seen_cp", []))
    first_run = not state.get("initialized", False)

    if first_run:
        print("首次运行，记录基线，不推送。")
        state["initialized"] = True
        state["seen_news"] = [n["title"] for n in recharge_news]
        state["seen_cp"] = cp_links
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    # 检测变化
    new_news = [n for n in recharge_news if n["title"] not in seen_news]
    new_cp = [u for u in cp_links if u not in seen_cp]

    if not new_news and not new_cp:
        print("无变化。")
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    print(f"发现新充值新闻 {len(new_news)} 条，新 /cp/ 活动链接 {len(new_cp)} 个")
    lines = []
    for n in new_news:
        lines.append(f"- [新闻·{n['date']}] [{n['title']}]({n['url']})")
    for u in new_cp:
        lines.append(f"- [活动页] {u}")
    desp = "检测到 QQ 华夏官网可能有新的充值/限时活动，快去看看！\n\n" + "\n".join(lines)
    notify("【QQ华夏】发现新充值/活动！", desp)

    # 更新（保留最近 200 条）
    state["seen_news"] = list((seen_news | {n["title"] for n in recharge_news}))[-200:]
    state["seen_cp"] = sorted(seen_cp | set(cp_links))[-200:]
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
