from datetime import datetime
from db import get_connection


def load_messages():
    """Return list of {from, text, time} in chronological order."""
    messages = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT sender, text, time FROM messages ORDER BY id ASC")
            for sender, text, time in cur.fetchall():
                messages.append({
                    "from": sender,
                    "text": text,
                    "time": time,
                })
    return messages


def add_message(sender, text):
    """Insert a new message with the current timestamp."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (sender, text, time) VALUES (%s, %s, %s)",
                (sender, text, now)
            )
        conn.commit()
