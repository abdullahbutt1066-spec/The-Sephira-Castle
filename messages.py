import json
import os
from datetime import datetime

MESSAGES_FILE = "messages.json"


def load_messages():
    if os.path.exists(MESSAGES_FILE):
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_messages(messages):
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)


def add_message(sender, text):
    messages = load_messages()
    messages.append({
        "from": sender,
        "text": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_messages(messages)
