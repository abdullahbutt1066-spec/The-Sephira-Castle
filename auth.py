import hashlib
import secrets
import json
from datetime import datetime
from db import get_connection

CARDS = [
    "The Fool", "The Magician", "The High Priestess", "The Empress",
    "The Emperor", "The Hierophant", "The Lovers", "The Chariot",
    "Strength", "The Hermit", "Wheel of Fortune", "Justice",
    "The Hanged Man", "Death", "Temperance", "The Devil",
    "The Tower", "The Star", "The Moon", "The Sun",
    "Judgement", "The World",
]

CARD_SYMBOLS = {
    "The Fool": "⚉", "The Magician": "✦", "The High Priestess": "☾",
    "The Empress": "❀", "The Emperor": "⛨", "The Hierophant": "✟",
    "The Lovers": "♡", "The Chariot": "⚔", "Strength": "⚜",
    "The Hermit": "✧", "Wheel of Fortune": "♾", "Justice": "⚖",
    "The Hanged Man": "✝", "Death": "☠", "Temperance": "⚗",
    "The Devil": "⛧", "The Tower": "♜", "The Star": "★",
    "The Moon": "☽", "The Sun": "☀", "Judgement": "⚒",
    "The World": "⊕",
}

CARD_COLORS = {
    "The Fool": "#7e83d6", "The Magician": "#e84848",
    "The High Priestess": "#5a70c8", "The Empress": "#cc3f83",
    "The Emperor": "#fff200", "The Hierophant": "#b8b8b8",
    "The Lovers": "#a878d8", "The Chariot": "#6090d8",
    "Strength": "#a8a8a8", "The Hermit": "#8a8a95",
    "Wheel of Fortune": "#42dbc9", "Justice": "#c8a04a",
    "The Hanged Man": "#5a7ab0", "Death": "#3e4141",
    "Temperance": "#d8d4c8", "The Devil": "#a82838",
    "The Tower": "#c87848", "The Star": "#78b8e8",
    "The Moon": "#6a80b8", "The Sun": "#f0c040",
    "Judgement": "#8898b8", "The World": "#662121",
}

IP_LIMIT = 3
DEVICE_LIMIT = 2
ONLINE_WINDOW_MINUTES = 5


def load_members():
    members = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT codename, salt, password, gender,
                       is_fool, recovery_hash, device_tokens, ip,
                       symbol, color, email, last_seen
                FROM members
            """)
            for row in cur.fetchall():
                (codename, salt, password, gender, is_fool, recovery_hash,
                 device_tokens, ip, symbol, color, email, last_seen) = row
                try:
                    tokens = json.loads(device_tokens) if device_tokens else []
                except (json.JSONDecodeError, TypeError):
                    tokens = []
                members[codename] = {
                    "salt": salt, "password": password, "gender": gender,
                    "is_fool": bool(is_fool), "recovery_hash": recovery_hash,
                    "device_tokens": tokens, "ip": ip, "symbol": symbol,
                    "color": color, "email": email, "last_seen": last_seen,
                }
    return members


def save_members(members):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for codename, info in members.items():
                cur.execute("""
                    INSERT INTO members
                        (codename, salt, password, gender, is_fool, recovery_hash,
                         device_tokens, ip, symbol, color, email, last_seen)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codename) DO UPDATE SET
                        salt = EXCLUDED.salt,
                        password = EXCLUDED.password,
                        gender = EXCLUDED.gender,
                        is_fool = EXCLUDED.is_fool,
                        recovery_hash = EXCLUDED.recovery_hash,
                        device_tokens = EXCLUDED.device_tokens,
                        ip = EXCLUDED.ip,
                        symbol = EXCLUDED.symbol,
                        color = EXCLUDED.color,
                        email = EXCLUDED.email,
                        last_seen = EXCLUDED.last_seen
                """, (
                    codename, info["salt"], info["password"], info["gender"],
                    info.get("is_fool", False), info.get("recovery_hash"),
                    json.dumps(info.get("device_tokens", [])), info.get("ip"),
                    info.get("symbol"), info.get("color"), info.get("email"),
                    info.get("last_seen"),
                ))
        conn.commit()


def touch_last_seen(codename):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE members SET last_seen = %s WHERE codename = %s", (now, codename))
        conn.commit()


def is_online(last_seen_str):
    if not last_seen_str:
        return False
    try:
        last = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return (datetime.now() - last).total_seconds() < (ONLINE_WINDOW_MINUTES * 60)


def status_text(last_seen_str):
    if not last_seen_str:
        return "Never"
    try:
        last = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "Never"
    seconds = (datetime.now() - last).total_seconds()
    if seconds < 0 or seconds < ONLINE_WINDOW_MINUTES * 60:
        return "Online now"
    elif seconds < 3600:
        return f"Last seen {int(seconds // 60)} min ago"
    elif seconds < 86400:
        return f"Last seen {int(seconds // 3600)} h ago"
    elif seconds < 604800:
        return f"Last seen {int(seconds // 86400)} d ago"
    else:
        return f"Last seen {last.strftime('%b %d')}"


def set_member_password(codename, new_password):
    """Generate a fresh salt, hash the new password, and update."""
    new_salt = make_salt()
    new_hash = hash_password(new_password, new_salt)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE members SET salt = %s, password = %s WHERE codename = %s",
                (new_salt, new_hash, codename)
            )
        conn.commit()


def set_member_gender(codename, new_gender):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE members SET gender = %s WHERE codename = %s", (new_gender, codename))
        conn.commit()


def count_registrations_from_ip(ip):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM members WHERE ip = %s", (ip,))
            return cur.fetchone()[0]


def make_salt():
    return secrets.token_hex(16)


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


def title_for(gender):
    return "Mr" if gender == "male" else "Ms"


def display_name(codename):
    if codename.lower().startswith("the "):
        return codename[4:]
    return codename


def verify_recovery(recovery_input, recovery_hash):
    if not recovery_hash:
        return False
    try:
        stored_hash, salt = recovery_hash.split(":", 1)
    except ValueError:
        return False
    return hash_password(recovery_input, salt) == stored_hash


def make_device_token():
    return secrets.token_hex(24)


def is_expelled(codename):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM expelled_names WHERE codename = %s", (codename,))
            return cur.fetchone() is not None


def remove_member(codename):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM members WHERE codename = %s", (codename,))
        conn.commit()


def record_expulsion(codename, expelled_by):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO expulsions (codename, expelled_by, expelled_at) VALUES (%s, %s, %s)",
                (codename, expelled_by, now)
            )
            cur.execute("""
                INSERT INTO expelled_names (codename, expelled_at)
                VALUES (%s, %s)
                ON CONFLICT (codename) DO NOTHING
            """, (codename, now))
        conn.commit()


def load_expulsions():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT codename, expelled_by, expelled_at FROM expulsions ORDER BY id DESC")
            return [
                {"codename": r[0], "expelled_by": r[1], "expelled_at": r[2]}
                for r in cur.fetchall()
            ]


def get_fool():
    members = load_members()
    for name, info in members.items():
        if info.get("is_fool"):
            return {"codename": name, **info}
    return None


def get_card_decorations(codename):
    return CARD_SYMBOLS.get(codename, "·"), CARD_COLORS.get(codename, "#b8b0c8")


def all_card_symbols():
    return [CARD_SYMBOLS[c] for c in CARDS]
