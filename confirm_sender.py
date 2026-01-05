# confirm_sender.py
import requests

def send_to_confirm_engine(payload: dict, url: str):
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()
