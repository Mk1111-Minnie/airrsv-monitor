import os
import re
import json
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = "https://airrsv.net/second-studium/calendar"

# 監視するメニュー
TARGET_MENU = "お寿司制作体験(3貫)"

# 監視する日
TARGET_DATES = [
    "2026-11-13",
    "2026-11-14",
]

STATE_FILE = Path("state.json")

NTFY_TOPIC = os.environ["NTFY_TOPIC"]


def notify(message):
    response = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": "Airリザーブ 空きが出ました",
            "Priority": "high",
            "Tags": "calendar",
        },
        timeout=20,
    )

    response.raise_for_status()


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(
                STATE_FILE.read_text()
            )
        except Exception:
            pass

    return {"notified": {}}


def save_state(state):
    STATE_FILE.write_text(
        json.dumps(
            state,
            ensure_ascii=False,
            indent=2
        )
    )


def select_menu(page):
    print("")
    print("=" * 60)
    print(f"SELECTING MENU: {TARGET_MENU}")
    print("=" * 60)

    # 通常の <select> を探す
    selects = page.locator("select")

    print(f"select elements found: {selects.count()}")

    for i in range(selects.count()):

        select = selects.nth(i)

        try:
            options = select.locator("option")

            option_texts = []

            for j in range(options.count()):
                option_texts.append(
                    options.nth(j).inner_text().strip()
                )

            print(
                f"select[{i}] options: "
                f"{option_texts}"
            )

            if TARGET_MENU in option_texts:

                select.select_option(
                    label=TARGET_MENU
                )

                page.wait_for_timeout(2000)

                print(
                    f"MENU SELECTED: {TARGET_MENU}"
                )

                return True

        except Exception as e:
            print(
                f"select[{i}] error: {e}"
            )

    # selectでなかった場合は、画面上のメニュー文字を探す
    menu_text = page.get_by_text(
        TARGET_MENU,
        exact=True
    )

    print(
        f"menu text elements found: "
        f"{menu_text.count()}"
    )

    if menu_text.count():

        try:
            menu_text.first.click()

            page.wait_for_timeout(500)

            option = page.get_by_text(
                TARGET_MENU,
                exact=True
            )

            if option.count():
                option.last.click()

                page.wait_for_timeout(2000)

                print(
                    f"MENU SELECTED: {TARGET_MENU}"
                )

                return True

        except Exception as e:
            print(
                f"menu click error: {e}"
            )

    print("ERROR: menu_not_found")

    return False


def find_date_text(page, date_iso):

    dt = datetime.fromisoformat(date_iso)

    # 画面に表示される可能性のある表記
    candidates = [
        f"{dt.month}/{dt.day}",
        f"{dt.month}月{dt.day}日",
        f"{dt.month}月{dt.day}日",
        f"{dt.month}/{dt.day} ({'月'})",
        f"{dt.month}/{dt.day} ({'火'})",
        f"{dt.month}/{dt.day} ({'水'})",
        f"{dt.month}/{dt.day} ({'木'})",
        f"{dt.month}/{dt.day} ({'金'})",
        f"{dt.month}/{dt.day} ({'土'})",
        f"{dt.month}/{dt.day} ({'日'})",
    ]

    for text in candidates:

        loc = page.get_by_text(
            text,
            exact=False
        )

        if loc.count():
            return loc.first

    return None


def move_calendar_until_date_visible(page, date_iso):

    print("")
    print(
        f"Searching calendar for {date_iso}..."
    )

    # まず現在表示されているか確認
    if find_date_text(page, date_iso):
        print(
            f"{date_iso}: already visible"
        )
        return True

    # 「次へ」「翌週」などのボタンを探して最大12回進む
    next_candidates = [
        "次へ",
        "次の週",
        "翌週",
        "＞",
        ">",
        "›",
    ]

    for attempt in range(12):

        clicked = False

        for text in next_candidates:

            loc = page.get_by_text(
                text,
                exact=True
            )

            if loc.count():

                try:
                    loc.last.click()
                    page.wait_for_timeout(700)

                    clicked = True

                    print(
                        f"calendar next: "
                        f"attempt {attempt + 1}"
                    )

                    break

                except Exception:
                    pass

        if not clicked:
            break

        if find_date_text(page, date_iso):

            print(
                f"{date_iso}: found"
            )

            return True

    print(
        f"{date_iso}: ERROR date_not_visible"
    )

    return False


def inspect_date_cell(page, date_iso):

    date_element = find_date_text(
        page,
        date_iso
    )

    if not date_element:
        return {
            "date": date_iso,
            "status": "ERROR",
            "detail": "date_not_found",
        }

    # 日付要素から親要素をたどって、
    # その日のカレンダー列を取得する
    try:

        result = date_element.evaluate(
            """
            el => {
                let node = el;

                for (let i = 0; i < 6 && node; i++) {
                    const text =
                        node.innerText || "";

                    if (
                        text.includes("9:00") ||
                        text.includes("10:00") ||
                        text.includes("11:00") ||
                        text.includes("12:00")
                    ) {
                        return {
                            text: text,
                            html: node.outerHTML
                        };
                    }

                    node = node.parentElement;
                }

                return {
                    text: el.parentElement
                        ? el.parentElement.innerText
                        : el.innerText,
                    html: el.parentElement
                        ? el.parentElement.outerHTML
                        : el.outerHTML
                };
            }
            """
        )

        text = result.get("text", "")
        html = result.get("html", "")

        print("")
        print(
            f"--- {date_iso} calendar cell ---"
        )
        print(text[:3000])

        # 判定
        if (
            "予約可能" in text
            or "残りわずか" in text
            or "○" in text
            or "〇" in text
            or "△" in text
        ):
            return {
                "date": date_iso,
                "status": "AVAILABLE",
                "detail": text[:3000],
            }

        if (
            "予約できません" in text
            or "×" in text
            or "✕" in text
        ):
            return {
                "date": date_iso,
                "status": "FULL",
                "detail": text[:3000],
            }

        # HTML側の属性も確認
        html_lower = html.lower()

        if (
            "available" in html_lower
            or "vacancy" in html_lower
            or "open" in html_lower
        ):
            return {
                "date": date_iso,
                "status": "AVAILABLE",
                "detail": text[:3000],
            }

        print(
            f"{date_iso}: status could not be determined"
        )

        return {
            "date": date_iso,
            "status": "UNKNOWN",
            "detail": text[:3000],
        }

    except Exception as e:

        print(
            f"{date_iso}: inspection error: {e}"
        )

        return {
            "date": date_iso,
            "status": "ERROR",
            "detail": str(e),
        }


def check_date(page, date_iso):

    print("")
    print("=" * 60)
    print(f"CHECKING: {date_iso}")
    print("=" * 60)

    if not move_calendar_until_date_visible(
        page,
        date_iso
    ):
        return {
            "date": date_iso,
            "status": "ERROR",
            "detail": "date_not_visible",
        }

    result = inspect_date_cell(
        page,
        date_iso
    )

    print(
        f"RESULT {date_iso}: "
        f"{result['status']}"
    )

    return result


def main():

    state = load_state()

    notifications = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="ja-JP",
        )

        print("Opening Airリザーブ...")

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(3000)

        # メニュー選択
        if not select_menu(page):

            print(
                "MENU SELECTION FAILED"
            )

            browser.close()

            raise RuntimeError(
                "Target menu could not be selected"
            )

        # 11/13・11/14を確認
        results = []

        for date_iso in TARGET_DATES:

            result = check_date(
                page,
                date_iso
            )

            results.append(result)

        browser.close()

    print("")
    print("=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    for result in results:

        print(
            f"{result['date']}: "
            f"{result['status']}"
        )

    # 通知
    for result in results:

        if result["status"] != "AVAILABLE":
            continue

        date_iso = result["date"]

        # 状態が変わったときだけ通知
        key = (
            f"{date_iso}:"
            f"{result['status']}"
        )

        if (
            state["notified"].get(date_iso)
            == key
        ):
            continue

        message = (
            "Airリザーブに空きが出ています。\n\n"
            f"メニュー: {TARGET_MENU}\n"
            f"日付: {date_iso}\n"
            f"状態: 予約可能 / 残りわずか\n\n"
            f"{URL}"
        )

        notify(message)

        state["notified"][date_iso] = key

        notifications.append(message)

    save_state(state)

    print("")
    print(
        f"checked: "
        f"{[r['date'] for r in results]}"
    )

    print(
        f"notifications: "
        f"{len(notifications)}"
    )


if __name__ == "__main__":
    main()
