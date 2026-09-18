import os
import re
import json
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://airrsv.net/second-studium/calendar"
TARGET_DATES = ["2026-11-13", "2026-11-14"]
STATE_FILE = Path("state.json")

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
HEADLESS = True

def notify(message: str):
    r = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": "Airリザーブ 空きが出ました",
            "Priority": "high",
            "Tags": "calendar",
        },
        timeout=20,
    )
    r.raise_for_status()

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"notified": {}}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))

def normalize(s):
    return re.sub(r"\s+", " ", s).strip()

def get_visible_text(page):
    return normalize(page.locator("body").inner_text(timeout=15000))

def click_date(page, date_iso):
    dt = datetime.fromisoformat(date_iso)
    # Airリザーブの画面実装が変更されても対応しやすいよう、
    # ISO日付、和暦風表記、数字だけの表記を順番に試します。
    candidates = [
        date_iso,
        f"{dt.year}/{dt.month}/{dt.day}",
        f"{dt.year}年{dt.month}月{dt.day}日",
        f"{dt.month}月{dt.day}日",
        f"{dt.month}/{dt.day}",
    ]

    # input[type=date] があれば直接設定
    date_inputs = page.locator('input[type="date"]')
    for i in range(date_inputs.count()):
        el = date_inputs.nth(i)
        try:
            el.fill(date_iso)
            el.press("Enter")
            page.wait_for_timeout(700)
            return True
        except Exception:
            pass

    # ボタン/リンク/要素のテキストを探す
    for text in candidates:
        loc = page.get_by_text(text, exact=True)
        if loc.count():
            try:
                loc.first.click()
                page.wait_for_timeout(700)
                return True
            except Exception:
                pass

    # aria-label/title に日付が入っているケース
    for attr in ["aria-label", "title", "data-date"]:
        loc = page.locator(f'[{attr}*="{date_iso}"]')
        if loc.count():
            try:
                loc.first.click()
                page.wait_for_timeout(700)
                return True
            except Exception:
                pass

    return False

def extract_available_times(page):
    # 「予約可能な時間があります」「残りわずか」等の表示を基準に、
    # 同じ画面に存在する時刻表記を拾います。
    body = page.locator("body").inner_text()
    if "予約可能な時間があります" not in body and "残りわずか" not in body:
        return []

    # 例: 9:00 / 09:30 / 14時00分 / 14:00〜15:00
    patterns = [
        r'(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?:\s*[〜～-]\s*(?:[01]?\d|2[0-3]):[0-5]\d)?',
        r'(?<!\d)(?:[01]?\d|2[0-3])時(?:[0-5]\d分)?(?:\s*[〜～-]\s*(?:[01]?\d|2[0-3])時(?:[0-5]\d分)?)?',
    ]
    found = []
    for p in patterns:
        found.extend(re.findall(p, body))
    return sorted(set(found))

def check_date(page, date_iso):
    if not click_date(page, date_iso):
        return {"date": date_iso, "times": [], "error": "date_not_found"}

    page.wait_for_timeout(500)
    times = extract_available_times(page)
    return {"date": date_iso, "times": times}

def main():
    state = load_state()
    notifications = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        page = browser.new_page(viewport={"width": 1440, "height": 1200}, locale="ja-JP")
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)

        results = []
        for date_iso in TARGET_DATES:
            results.append(check_date(page, date_iso))

        browser.close()

    for result in results:
        if not result["times"]:
            continue

        date_iso = result["date"]
        times = result["times"]
        key = f"{date_iso}:{','.join(times)}"

        # 同じ空き状態を繰り返し通知しない
        if state["notified"].get(date_iso) == key:
            continue

        msg = (
            f"Airリザーブに空きが出ています。\n"
            f"日付: {date_iso}\n"
            f"時間: {', '.join(times)}\n\n"
            f"{URL}"
        )
        notify(msg)
        state["notified"][date_iso] = key
        notifications.append(msg)

    save_state(state)
    print("checked:", [r["date"] for r in results])
    print("notifications:", len(notifications))

if __name__ == "__main__":
    main()
