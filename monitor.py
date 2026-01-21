import json
import os
import time
from pathlib import Path
from datetime import datetime
import requests

STATE_FILE = os.environ.get("STATE_FILE", "/data/roofz_listings.json")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", 300))
API_URL = "https://roofz.eu/api/properties?filter[status]=available&sort=-created_at&page[number]=1&page[size]=100"


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_listings():
    from playwright.sync_api import sync_playwright
    
    listings = {}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # Load page to get session/cookies
            log("Loading page...")
            page.goto("https://roofz.eu/availability", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(3000)
            
            # Get cookies
            cookies = context.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            
            browser.close()
        
        # Call API directly with session cookies
        log("Calling API...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://roofz.eu/availability",
            "Cookie": cookie_str,
        }
        
        resp = requests.get(API_URL, headers=headers, timeout=30)
        
        if resp.status_code == 200:
            try:
                data = resp.json()
                for item in data.get("data", []):
                    lid = item.get("id")
                    if lid:
                        attrs = item.get("attributes", {})
                        listings[lid] = {
                            "id": lid,
                            "title": attrs.get("title", "New listing"),
                            "price": attrs.get("price", 0),
                            "city": attrs.get("city", ""),
                        }
                log(f"API returned {len(listings)} listings")
            except Exception as e:
                log(f"Failed to parse API response: {e}")
        else:
            log(f"API returned status {resp.status_code}")
            
    except Exception as e:
        log(f"Error getting listings: {e}")
    
    return listings


def send_email(new_listings):
    try:
        body = f"{len(new_listings)} new listing(s) on Roofz.eu!\n\n"
        for lid, info in new_listings.items():
            title = info.get("title", "New listing")
            price = info.get("price", "")
            city = info.get("city", "")
            body += f"* {title}"
            if price:
                body += f" - EUR {price}/mo"
            if city:
                body += f" ({city})"
            body += f"\n  https://roofz.eu/listing/{lid}\n\n"
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
    
    # Ensure data directory exists
    Path("/data").mkdir(exist_ok=True)
    state_path = Path(STATE_FILE)

    if not current_ids:
        log("No listings found - will retry next cycle")
        return

    log(f"Found {len(current_ids)} listings")

    previous_ids = set()
    if state_path.exists():
        try:
            previous_ids = set(json.loads(state_path.read_text()))
        except:
            previous_ids = set()

    new_ids = current_ids - previous_ids

    if new_ids and previous_ids:
        log(f"NEW LISTINGS: {len(new_ids)}")
        new_listings = {lid: current[lid] for lid in new_ids}
        send_email(new_listings)
    elif not previous_ids:
        log(f"First run - tracking {len(current_ids)} listings")
    else:
        log("No new listings")

    # Save current state
    state_path.write_text(json.dumps(list(current_ids)))


def main():
    log(f"Starting Roofz monitor")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log(f"State file: {STATE_FILE}")
    
    while True:
        try:
            check_for_new()
        except Exception as e:
            log(f"Error in check cycle: {e}")
        
        log(f"Sleeping {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Stopped by user")
    except Exception as e:
        log(f"Fatal error: {e}")
        # Sleep before exit so Railway sees the error
        time.sleep(60)
        raise
