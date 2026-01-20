import requests
import json
import os
import re
import time
from pathlib import Path
from datetime import datetime

PAGE_URL = "https://roofz.eu/availability"
# Use /app directory which persists, or environment variable
STATE_FILE = os.environ.get("STATE_FILE", "/app/roofz_listings.json")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 120))
TIMEOUT = 60

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,nl;q=0.8",
}


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    session = requests.Session()
    resp = session.get(PAGE_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    html = resp.text
    
    listing_ids = set(re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', html))
    return {lid: {"id": lid} for lid in listing_ids}


def send_email(new_listings):
    body = f"{len(new_listings)} new listing(s) on Roofz.eu!\n\n"
    for lid in new_listings:
        body += f"* https://roofz.eu/listing/{lid}\n\n"
    body += "View all: https://roofz.eu/availability"

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": "Roofz Monitor <onboarding@resend.dev>",
            "to": os.environ["EMAIL_TO"],
            "subject": f"Roofz: {len(new_listings)} New Listing(s)!",
            "text": body,
        },
    )
    if resp.status_code == 200:
        log("Email sent!")
    else:
        log(f"Email failed: {resp.text}")


def check_for_new():
    current = get_listings()
    current_ids = set(current.keys())
    state_path = Path(STATE_FILE)

    log(f"Found {len(current_ids)} listings")

    previous_ids = set()
    if state_path.exists():
        previous_ids = set(json.loads(state_path.read_text()))

    new_ids = current_ids - previous_ids

    # Only alert if we had previous state AND found few new ones (avoid restart spam)
    if new_ids and previous_ids and len(new_ids) <= 10:
        log(f"NEW LISTINGS: {len(new_ids)}")
        send_email(new_ids)
    elif new_ids and len(new_ids) > 10:
        log(f"Skipping alert - too many 'new' listings ({len(new_ids)}), likely a restart")
    elif not previous_ids:
        log(f"First run - tracking {len(current_ids)} listings")
    else:
        log("No new listings")

    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor (every {CHECK_INTERVAL}s)")
    errors = 0
    
    while True:
        try:
            check_for_new()
            errors = 0
        except Exception as e:
            errors += 1
            log(f"Error: {e}")
            if errors >= 3:
                wait = min(errors * 120, 600)
                log(f"Backing off {wait}s...")
                time.sleep(wait)
        
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
