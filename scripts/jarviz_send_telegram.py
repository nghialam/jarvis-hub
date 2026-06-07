#!/usr/bin/env python3
"""Send Jarvis briefing to Telegram."""
import json, urllib.request

with open("/tmp/jarvis_telegram_payload.json") as f:
    payload = json.load(f)

url = "https://api.telegram.org/bot8733142640:AAHuz7TKMi6DycjpNao9XomKJRCOyHaikHo/sendMessage"
data = json.dumps({
    "chat_id": payload["chat_id"],
    "text": payload["text"],
    "parse_mode": "Markdown"
}).encode("utf-8")

req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
try:
    resp = urllib.request.urlopen(req, timeout=15)
    result = json.loads(resp.read())
    print(f"Status: {result.get('ok')} | Message ID: {result.get('result', {}).get('message_id')}")
except Exception as e:
    print(f"Error: {e}")
