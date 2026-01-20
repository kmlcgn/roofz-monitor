import requests
import json
import os
import time
from pathlib import Path
from datetime import datetime

API_URL = "https://roofz.eu/api/properties?filter[status]=available&sort=-created_at&page[number]=1&page[size]=100"
STATE_FILE = "/tmp/roofz_listings.json"
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 30))


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    resp = requests.get(API_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    listings = {}
    for item in resp.json().get("data", []):
        lid = item["id"]
        attrs = item.get("attributes", {})
        listings[lid] = {
            "title": attrs.get("title", ""),
            "price": attrs.get("price", 0),
            "city": attrs.get("city", ""),
            "bedrooms": attrs.get("bedrooms", 0),
            "surface": attrs.get("surface", 0),
        }
    return listings


def send_email(new_listings):
    body = f"{len(new_listings)} new listing(s) on Roofz.eu!\n\n"
    for lid, info in new_listings.items():
        body += f"* {info['title']} - EUR {info['price']}/mo\n"
        body += f"  {info['city']} | {info['bedrooms']} bed | {info['surface']}m2\n"
        body += f"  https://roofz.eu/listing/{lid}\n\n"

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
        log(f"Email sent for {len(new_listings)} new listing(s)")
    else:
        log(f"Email failed: {resp.text}")


def check_for_new():
    current = get_listings()
    current_ids = set(current.keys())
    state_path = Path(STATE_FILE)

    previous_ids = set()
    if state_path.exists():
        previous_ids = set(json.loads(state_path.read_text()))

    new_ids = current_ids - previous_ids

    if new_ids and previous_ids:
        log(f"Found {len(new_ids)} new listing(s)!")
        new_listings = {lid: current[lid] for lid in new_ids}
        send_email(new_listings)
    elif not previous_ids:
        log(f"First run - now tracking {len(current_ids)} listings")
    else:
        log(f"No new listings (tracking {len(current_ids)})")

    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor (checking every {CHECK_INTERVAL}s)")
    while True:
        try:
            check_for_new()
        except Exception as e:
            log(f"Error: {e}")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
