import requests
import os

def test_new_listing():
    # Fake listing data (simulates a new listing)
    fake_listings = {
        "test-123-fake-id": {
            "title": "Kalverstraat 42",
            "price": 1250,
            "city": "Amsterdam",
            "bedrooms": 2,
            "surface": 65,
        },
        "test-456-fake-id": {
            "title": "Witte de Withstraat 88",
            "price": 980,
            "city": "Rotterdam",
            "bedrooms": 1,
            "surface": 45,
        },
    }

    body = f"{len(fake_listings)} new listing(s) on Roofz.eu!\n\n"
    for lid, info in fake_listings.items():
        body += f"* {info['title']} - EUR {info['price']}/mo\n"
        body += f"  {info['city']} | {info['bedrooms']} bed | {info['surface']}m2\n"
        body += f"  https://roofz.eu/listing/{lid}\n\n"
    body += "---\n[TEST] This is a test notification"

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": "Roofz Monitor <onboarding@resend.dev>",
            "to": os.environ["EMAIL_TO"],
            "subject": f"Roofz: {len(fake_listings)} New Listing(s)!",
            "text": body,
        },
    )

    if resp.status_code == 200:
        print("Success! Check your inbox for the fake listing notification.")
    else:
        print(f"Failed: {resp.status_code} - {resp.text}")


if __name__ == "__main__":
    test_new_listing()
