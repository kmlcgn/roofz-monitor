import requests
import os

def test_email():
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": "Roofz Monitor <onboarding@resend.dev>",
            "to": os.environ["EMAIL_TO"],
            "subject": "Roofz Monitor - Test Email",
            "text": "If you receive this, your Roofz monitor is set up correctly!\n\nhttps://roofz.eu/availability",
        },
    )
    
    if resp.status_code == 200:
        print("Success! Check your inbox.")
    else:
        print(f"Failed: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    test_email()
