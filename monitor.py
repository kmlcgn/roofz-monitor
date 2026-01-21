import json
import os
import re
import time
from pathlib import Path
from datetime import datetime
import requests

STATE_FILE = os.environ.get("STATE_FILE", "/data/roofz_listings.json")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    from playwright.sync_api import sync_playwright
    
    listing_ids = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()
            
            log("Loading page...")
            page.goto("https://roofz.eu/availability", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(5000)
            
            # Scroll to load all content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(2000)
            
            html = page.content()
            browser.close()
            
            # Extract UUIDs near "property" context (this was finding 10 listings)
            listing_ids = list(set(re.findall(
                r'property[^>]*?([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})',
                html,
                re.IGNORECASE
            )))
            
            log(f"Found {len(listing_ids)} listings")
            
    except Exception as e:
        log(f"Error: {e}")
    
    return {lid: {"id": lid} for lid in listing_ids}


def send_email(new_listing_ids):
    try:
        body = f"{len(new_listing_ids)} new listing(s) on Roofz.eu!\n\n"
        for lid in new_listing_ids:
            body += f"* https://roofz.eu/listing/{lid}\n\n"
        body += "View all: https://roofz.eu/availability"

        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
            json={
                "from": "Roofz Monitor <onboarding@resend.dev>",
                "to": os.environ["EMAIL_TO"],
                "subject": f"Roofz: {len(new_listing_ids)} New Listing(s)!",
                "text": body,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            log("Email sent!")
        else:
            log(f"Email failed: {resp.text}")
    except Exception as e:
        log(f"Email error: {e}")


def check_for_new():
    current = get_listings()
    current_ids = set(current.keys())
    
    Path("/data").mkdir(exist_ok=True)
    state_path = Path(STATE_FILE)

    if not current_ids:
        log("No listings found - will retry")
        return

    previous_ids = set()
    if state_path.exists():
        try:
            previous_ids = set(json.loads(state_path.read_text()))
        except:
            previous_ids = set()

    new_ids = current_ids - previous_ids

    if new_ids and previous_ids:
        log(f"NEW LISTINGS: {len(new_ids)}")
        send_email(list(new_ids))
    elif not previous_ids:
        log(f"First run - tracking {len(current_ids)} listings")
    else:
        log("No new listings")

    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor (every {CHECK_INTERVAL}s)")
    
    while True:
        try:
            check_for_new()
        except Exception as e:
            log(f"Error: {e}")
        
        log(f"Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopped")
    except Exception as e:
        log(f"Fatal: {e}")
        time.sleep(60)
        raise
