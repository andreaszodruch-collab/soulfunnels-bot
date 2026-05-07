import os
import time
import requests
import schedule
from datetime import datetime

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
APIFY_TOKEN      = os.environ.get("APIFY_TOKEN")
CLAUDE_API_KEY   = os.environ.get("CLAUDE_API_KEY", "")

ACCOUNTS = [
    "amyporterfield",
    "manychat",
    "diefunnelarchitektinnen",
    "zeitsparqueen",
]

SEND_TIME = "06:00"

def scrape_account(username):
    run_url = "https://api.apify.com/v2/acts/apify~instagram-scraper/runs"
    payload = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts",
        "resultsLimit": 3,
    }
    r = requests.post(run_url, json=payload, params={"token": APIFY_TOKEN}, timeout=30)
    run_id = r.json().get("data", {}).get("id")
    if not run_id:
        return []

    for _ in range(36):
        time.sleep(5)
        status_r = requests.get(
            f"https://api.apify.com/v2/acts/apify~instagram-scraper/runs/{run_id}",
            params={"token": APIFY_TOKEN}, timeout=15
        )
        status = status_r.json().get("data", {}).get("status", "")
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            return []

    dataset_id = status_r.json().get("data", {}).get("defaultDatasetId", "")
    items_r = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        params={"token": APIFY_TOKEN}, timeout=15
    )
    return items_r.json() if isinstance(items_r.json(), list) else []

def analyse_mit_claude(posts_zusammenfassung):
    try:
        headers = {
            "x-api-key": CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": "claude-opus-4-5",
            "max_tokens": 1500,
            "messages": [{
                "role": "user",
                "content": f"""Du bist Content-Stratege fuer Andrea (SoulFunnels).
UEBER ANDREA:
- Funnel Strategin fuer Fitness & Health Coaches
- Nische: ManyChat-Automation + digitale Produkte
- Stil: weiblich-direkt, kein Bro-Marketing, du-Form
- Keywords: FORMEL | FREIHEIT | SYSTEM CHECK | YOGA | MANYCHAT

HEUTIGE POSTS:
{posts_zusammenfassung}

Erstelle auf Deutsch:

WAS WURDE HEUTE GEPOSTET?
(2-3 Saetze Zusammenfassung)

DEINE 3 CONTENT-IDEEN:
1. [Titel] - Format: Reel - CTA: KEYWORD
2. [Titel] - Format: Carousel - CTA: KEYWORD
3. [Titel] - Format: Post - CTA: KEYWORD

HEUTIGER HOOK FUER ANDREA:
[Fertiger Hook-Satz]"""
            }]
        }
        r = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=body, timeout=30)
        return r.json()["content"][0]["text"]
    except Exception as e:
        print(f"Claude-Fehler: {e}")
        return None

def format_ohne_ai(posts_data):
    text = ""
    for account, posts in posts_data.items():
        text += f"\n@{account}\n"
        if not posts:
            text += "   Keine neuen Posts.\n"
            continue
        for i, post in enumerate(posts[:2], 1):
            caption = (post.get("caption") or "Kein Text")[:250]
            post_type = post.get("type", "post").upper()
            url = post.get("url", "")
            text += f"   {i}. [{post_type}] {caption}...\n"
            if url:
                text += f"   Link: {url}\n"
    return text

def sende_telegram(nachricht):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": nachricht}
    r = requests.post(url, json=data, timeout=15)
    if r.json().get("ok"):
        print("Telegram-Nachricht gesendet!")
    else:
        print(f"Telegram-Fehler: {r.json()}")

def taegliche_analyse():
    print(f"Analyse gestartet: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    posts_data = {}
    posts_zusammenfassung = ""

    for account in ACCOUNTS:
        try:
            print(f"Scrape @{account}...")
            posts = scrape_account(account)
            posts_data[account] = posts
            for post in posts[:2]:
                caption = (post.get("caption") or "")[:300]
                post_type = post.get("type", "post")
                posts_zusammenfassung += f"\n@{account} [{post_type}]:\n{caption}\n"
            print(f"OK: {len(posts)} Posts")
        except Exception as e:
            print(f"Fehler bei @{account}: {e}")
            posts_data[account] = []

    analyse = None
    if CLAUDE_API_KEY:
        analyse = analyse_mit_claude(posts_zusammenfassung)
    if not analyse:
        analyse = format_ohne_ai(posts_data)

    heute = datetime.now().strftime("%d.%m.%Y")
    nachricht = f"Content-Inspiration {heute}\n\n{analyse}\n\n-- SoulFunnels Bot"
    sende_telegram(nachricht)

if __name__ == "__main__":
    print("SoulFunnels Bot gestartet!")
    taegliche_analyse()
    schedule.every().day.at(SEND_TIME).do(taegliche_analyse)
    while True:
        schedule.run_pending()
        time.sleep(60)
