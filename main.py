import os
import time
import json
import requests
import schedule
from datetime import datetime
from apify_client import ApifyClient

# ============================================================
#  KONFIGURATION — wird über Railway-Umgebungsvariablen gesetzt
# ============================================================
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
APIFY_TOKEN      = os.environ.get("APIFY_TOKEN")
CLAUDE_API_KEY   = os.environ.get("CLAUDE_API_KEY", "")  # optional

# Instagram-Accounts die täglich beobachtet werden
ACCOUNTS = [
    "amyporterfield",
    "manychat",
    "diefunnelarchitektinnen",
    "zeitsparqueen",
]

SEND_TIME = "06:00"   # 07:00 Uhr deutsche Zeit = 06:00 UTC (Railway läuft auf UTC)


# ============================================================
#  SCHRITT 1: Instagram scrapen via Apify
# ============================================================
def scrape_account(username: str) -> list:
    """Holt die letzten 3 Posts eines öffentlichen Instagram-Accounts."""
    client = ApifyClient(APIFY_TOKEN)
    run_input = {
        "directUrls": [f"https://www.instagram.com/{username}/"],
        "resultsType": "posts",
        "resultsLimit": 3,
    }
    run    = client.actor("apify/instagram-scraper").call(run_input=run_input)
    items  = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    return items


# ============================================================
#  SCHRITT 2a: Ideen mit Claude AI generieren (wenn API-Key da)
# ============================================================
def analyse_mit_claude(posts_zusammenfassung: str) -> str:
    """Analysiert den Content und liefert maßgeschneiderte Ideen für Andrea."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": f"""Du bist Content-Stratege für Andrea (@FitnessYoggiAndrea / SoulFunnels).

ÜBER ANDREA:
- Funnel Strategin & Online Business Mentorin für Fitness & Health Coaches
- Nische: ManyChat-Automation + digitale Produkte für Coaches
- Stil: weiblich-direkt, kein Bro-Marketing, authentisch, du-Form
- Aktive Keywords: FORMEL | FREIHEIT | SYSTEM CHECK | YOGA | MANYCHAT
- Story: „Von der ausgelaugten Personal Trainerin zur digitalen Unternehmerin"

HEUTIGE MITBEWERBER-POSTS:
{posts_zusammenfassung}

Erstelle jetzt eine kompakte Analyse auf Deutsch:

📊 *WAS WURDE HEUTE GEPOSTET?*
(2-3 Sätze — was ist der rote Faden der Mitbewerber heute?)

💡 *DEINE 3 CONTENT-IDEEN:*
1. [Titel] → Format: Reel | CTA: KEYWORD
2. [Titel] → Format: Carousel | CTA: KEYWORD
3. [Titel] → Format: Post | CTA: KEYWORD

🎯 *HEUTIGER STÄRKSTER HOOK FÜR ANDREA:*
[Einen konkreten, fertigen Hook-Satz der zu ihrer Story passt]

Schreib direkt, praxisnah, ohne Floskeln."""
            }]
        )
        return response.content[0].text
    except Exception as e:
        print(f"Claude-Fehler: {e}")
        return None


# ============================================================
#  SCHRITT 2b: Einfache Formatierung ohne AI
# ============================================================
def format_ohne_ai(posts_data: dict) -> str:
    """Fallback: Zeigt die rohen Post-Captions übersichtlich an."""
    text = ""
    for account, posts in posts_data.items():
        text += f"\n📱 @{account}\n"
        if not posts:
            text += "   Keine neuen Posts gefunden.\n"
            continue
        for i, post in enumerate(posts[:2], 1):
            caption   = (post.get("caption") or "Kein Text")[:250]
            post_type = post.get("type", "post").upper()
            url       = post.get("url", "")
            text += f"   {i}. [{post_type}] {caption}…\n"
            if url:
                text += f"      🔗 {url}\n"
    return text


# ============================================================
#  SCHRITT 3: Telegram-Nachricht senden
# ============================================================
def sende_telegram(nachricht: str, chat_id: str = None):
    ziel = chat_id or TELEGRAM_CHAT_ID
    if not ziel:
        print("❌ Keine Chat-ID gesetzt!")
        return False

    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id":    ziel,
        "text":       nachricht,
        "parse_mode": "Markdown",
    }
    r = requests.post(url, json=data, timeout=15)
    result = r.json()
    if result.get("ok"):
        print("✅ Telegram-Nachricht gesendet!")
        return True
    else:
        print(f"❌ Telegram-Fehler: {result}")
        return False


# ============================================================
#  CHAT-ID ERMITTELN (einmalig beim ersten Start)
# ============================================================
def hole_chat_id() -> str:
    """Liest die Chat-ID aus den letzten Telegram-Updates."""
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    r    = requests.get(url, timeout=10)
    data = r.json()
    updates = data.get("result", [])
    for update in reversed(updates):
        chat = update.get("message", {}).get("chat", {})
        if chat.get("id"):
            return str(chat["id"])
    return ""


# ============================================================
#  HAUPT-FUNKTION: Täglich ausgeführt
# ============================================================
def taegliche_analyse():
    print(f"\n{'='*50}")
    print(f"🔍 Analyse gestartet: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print(f"{'='*50}")

    # Chat-ID prüfen
    chat_id = TELEGRAM_CHAT_ID
    if not chat_id:
        print("Suche Chat-ID automatisch...")
        chat_id = hole_chat_id()
        if chat_id:
            print(f"✅ Chat-ID gefunden: {chat_id}")
            print(f"👉 Trage diese ID als TELEGRAM_CHAT_ID in Railway ein!")
        else:
            print("❌ Chat-ID nicht gefunden. Schick /start an deinen Bot und starte neu.")
            return

    # Instagram scrapen
    posts_data        = {}
    posts_zusammenfassung = ""

    for account in ACCOUNTS:
        try:
            print(f"   Scrape @{account}...")
            posts = scrape_account(account)
            posts_data[account] = posts

            for post in posts[:2]:
                caption   = (post.get("caption") or "")[:300]
                post_type = post.get("type", "post")
                posts_zusammenfassung += f"\n@{account} [{post_type}]:\n{caption}\n"

            print(f"   ✅ {len(posts)} Posts gefunden")
        except Exception as e:
            print(f"   ❌ Fehler bei @{account}: {e}")
            posts_data[account] = []

    # Analyse
    analyse = None
    if CLAUDE_API_KEY:
        print("\n🤖 Analysiere mit Claude AI...")
        analyse = analyse_mit_claude(posts_zusammenfassung)

    if not analyse:
        print("📋 Nutze einfache Formatierung...")
        analyse = format_ohne_ai(posts_data)

    # Nachricht zusammenbauen
    heute = datetime.now().strftime("%d.%m.%Y")
    nachricht = f"""🌅 *Content-Inspiration — {heute}*

{analyse}

━━━━━━━━━━━━━━━━━━
_SoulFunnels Watcher Bot 🤖_"""

    sende_telegram(nachricht, chat_id)


# ============================================================
#  START
# ============================================================
if __name__ == "__main__":
    print("🤖 SoulFunnels Watcher Bot gestartet!")
    print(f"📅 Sendet täglich um {SEND_TIME} Uhr\n")

    # Sofort einmal ausführen (zum Testen)
    taegliche_analyse()

    # Dann täglich planen
    schedule.every().day.at(SEND_TIME).do(taegliche_analyse)
    while True:
        schedule.run_pending()
        time.sleep(60)
