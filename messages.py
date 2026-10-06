from datetime import datetime
from db import get_connection


# ---------- Public chat messages ----------

def load_messages(include_deleted=False):
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (sender, text, time) VALUES (%s, %s, %s)",
                (sender, text, now)
            )
        conn.commit()


def soft_delete_message(message_id, deleted_by):
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
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE messages
                SET text = %s, deleted = TRUE, deleted_by = %s, deleted_at = %s
                WHERE sender = %s
            """, ("— expelled —", "The Fool", now, sender))
        conn.commit()


# ---------- Direct messages ----------

def create_thread(member_codenames, created_by="The Fool"):
    """
    Create a new DM thread with The Fool + the given member codenames.
    Returns the new thread_id.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    participants = set(member_codenames)
    participants.add("The Fool")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dm_threads (created_at, created_by) VALUES (%s, %s) RETURNING id",
                (now, created_by)
            )
            thread_id = cur.fetchone()[0]
            for name in participants:
                cur.execute(
                    "INSERT INTO dm_members (thread_id, codename) VALUES (%s, %s)",
                    (thread_id, name)
                )
        conn.commit()
    return thread_id


def load_threads_for(codename):
    """
    Return list of threads the codename is in, each with:
    {id, title, participants, last_time, last_preview, unread}
    Newest activity first.
    """
    threads = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT t.id, t.created_at
                FROM dm_threads t
                JOIN dm_members m ON m.thread_id = t.id
                WHERE m.codename = %s
            """, (codename,))
            rows = cur.fetchall()

            for thread_id, created_at in rows:
                # Get participants
                cur.execute(
                    "SELECT codename FROM dm_members WHERE thread_id = %s",
                    (thread_id,)
                )
                participants = [r[0] for r in cur.fetchall()]

                # Other members (excluding self) for title generation
                others = [p for p in participants if p != codename]
                if len(others) == 1:
                    title = others[0]
                elif others:
                    title = ", ".join(others)
                else:
                    title = "(empty)"

                # Last message + time
                cur.execute("""
                    SELECT text, time, id FROM direct_messages
                    WHERE thread_id = %s AND deleted = FALSE
                    ORDER BY id DESC LIMIT 1
                """, (thread_id,))
                last = cur.fetchone()
                last_preview = last[0][:60] if last else "(no messages yet)"
                last_time = last[1] if last else ""
                newest_id = last[2] if last else 0

                # Unread count
                cur.execute("""
                    SELECT last_read_message_id FROM dm_reads
                    WHERE thread_id = %s AND codename = %s
                """, (thread_id, codename))
                read_row = cur.fetchone()
                last_read = read_row[0] if read_row else 0

                cur.execute("""
                    SELECT COUNT(*) FROM direct_messages
                    WHERE thread_id = %s AND id > %s
                      AND sender != %s AND deleted = FALSE
                """, (thread_id, last_read, codename))
                unread = cur.fetchone()[0]

                threads.append({
                    "id": thread_id,
                    "title": title,
                    "participants": participants,
                    "last_preview": last_preview,
                    "last_time": last_time,
                    "unread": unread,
                    "newest_id": newest_id,
                    "created_at": created_at,
                })

    # Sort by newest message time, falling back to created_at
    threads.sort(key=lambda t: t["last_time"] or t["created_at"], reverse=True)
    return threads


def load_thread(thread_id):
    """Return thread info + participants."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, created_at, created_by FROM dm_threads WHERE id = %s", (thread_id,))
            row = cur.fetchone()
            if not row:
                return None
            cur.execute("SELECT codename FROM dm_members WHERE thread_id = %s", (thread_id,))
            participants = [r[0] for r in cur.fetchall()]
            return {
                "id": row[0],
                "created_at": row[1],
                "created_by": row[2],
                "participants": participants,
            }


def load_dm_messages(thread_id, include_deleted=False):
    """Return messages in a thread, oldest first."""
    messages = []
    where_clause = "" if include_deleted else "AND deleted = FALSE"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, sender, text, time, deleted, deleted_by, deleted_at
                FROM direct_messages
                WHERE thread_id = %s {where_clause}
                ORDER BY id ASC
            """, (thread_id,))
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


def add_dm_message(thread_id, sender, text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO direct_messages (thread_id, sender, text, time)
                VALUES (%s, %s, %s, %s)
            """, (thread_id, sender, text, now))
        conn.commit()


def soft_delete_dm_message(message_id, deleted_by):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE direct_messages
                SET deleted = TRUE, deleted_by = %s, deleted_at = %s
                WHERE id = %s
            """, (deleted_by, now, message_id))
        conn.commit()


def is_member_of_thread(thread_id, codename):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM dm_members WHERE thread_id = %s AND codename = %s",
                (thread_id, codename)
            )
            return cur.fetchone() is not None


def mark_thread_read(thread_id, codename, up_to_id):
    """Update the read pointer for this user in this thread."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO dm_reads (thread_id, codename, last_read_message_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (thread_id, codename) DO UPDATE
                SET last_read_message_id = GREATEST(dm_reads.last_read_message_id, EXCLUDED.last_read_message_id)
            """, (thread_id, codename, up_to_id))
        conn.commit()


def total_unread_for(codename):
    """Total unread DM count across all threads — for the nav badge."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM direct_messages dm
                JOIN dm_members mem ON mem.thread_id = dm.thread_id
                LEFT JOIN dm_reads r
                    ON r.thread_id = dm.thread_id AND r.codename = mem.codename
                WHERE mem.codename = %s
                  AND dm.sender != %s
                  AND dm.deleted = FALSE
                  AND dm.id > COALESCE(r.last_read_message_id, 0)
            """, (codename, codename))
            return cur.fetchone()[0]
