from datetime import datetime
from db import get_connection


def load_messages(include_deleted=False):
    """
    Return list of {id, from, text, time, deleted, deleted_by, deleted_at}.
    Non-admin: only non-deleted messages.
    Admin: all messages, including ones marked as deleted.
    """
    messages = []
    where_clause = "" if include_deleted else "WHERE deleted = FALSE"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, sender, text, time, deleted, deleted_by, deleted_at
                FROM messages
                {where_clause}
                ORDER BY id ASC
            """)
            for row in cur.fetchall():
                mid, sender, text, time, deleted, deleted_by, deleted_at = row
                messages.append({
                    "id": mid,
                    "from": sender,
                    "text": text,
                    "time": time,
                    "deleted": bool(deleted),
                    "deleted_by": deleted_by,
                    "deleted_at": deleted_at,
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


def soft_delete_message(message_id, deleted_by):
    """Mark a message as deleted. It stays in the DB but is hidden from non-admins."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE messages
                SET deleted = TRUE, deleted_by = %s, deleted_at = %s
                WHERE id = %s
            """, (deleted_by, now, message_id))
        conn.commit()


def tombstone_messages_from(sender):
    """
    Replace all messages from a given member with a tombstone note.
    The text becomes '— expelled —', so it's clear they were removed.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE messages
                SET text = %s, deleted = TRUE, deleted_by = %s, deleted_at = %s
                WHERE sender = %s
            """, (
                "— expelled —",
                "The Fool",
                now,
                sender,
            ))
        conn.commit()
