import os

import requests

SMS_GATEWAY_URL = os.environ.get("SMS_GATEWAY_URL", "http://localhost:9500")


def send_sms(phone: str, text: str) -> None:
    try:
        requests.post(f"{SMS_GATEWAY_URL}/send", json={"phone": phone, "text": text}, timeout=5)
    except requests.RequestException as exc:
        print(f"[sms] delivery failed: {exc}")
