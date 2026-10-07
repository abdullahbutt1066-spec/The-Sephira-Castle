import hashlib
import secrets
import json
from datetime import datetime
from db import get_connection

CARDS = [
    "The Fool",
    "The Magician",
    "The High Priestess",
    "The Empress",
    "The Emperor",
    "The Hierophant",
    "The Lovers",
    "The Chariot",
    "Strength",
    "The Hermit",
    "Wheel of Fortune",
    "Justice",
    "The Hanged Man",
    "Death",
    "Temperance",
    "The Devil",
    "The Tower",
    "The Star",
    "The Moon",
    "The Sun",
    "Judgement",
    "The World",
]

CARD_SYMBOLS = {
    "The Fool": "⚉",
    "The Magician": "✦",
    "The High Priestess": "☾",
    "The Empress": "❀",
    "The Emperor": "⛨",
    "The Hierophant": "✟",
    "The Lovers": "♡",
    "The Chariot": "⚔",
    "Strength": "⚜",
    "The Hermit": "✧",
    "Wheel of Fortune": "♾",
    "Justice": "⚖",
    "The Hanged Man": "✝",
    "Death": "☠",
    "Temperance": "⚗",
    "The Devil": "⛧",
    "The Tower": "♜",
    "The Star": "★",
    "The Moon": "☽",
    "The Sun": "☀",
    "Judgement": "⚒",
    "The World": "⊕",
}

CARD_COLORS = {
    "The Fool": "#c4a8ff",
    "The Magician": "#7db8e8",
    "The High Priestess": "#b0a8e0",
    "The Empress": "#e8b0c4",
    "The Emperor": "#e0c48a",
    "The Hierophant": "#d4a0d4",
    "The Lovers": "#f0a0b0",
    "The Chariot": "#90a8e0",
    "Strength": "#e0a870",
    "The Hermit": "#8a9ab0",
    "Wheel of Fortune": "#b8c878",
    "Justice": "#c8d8e8",
    "The Hanged Man": "#88b0a0",
    "Death": "#706070",
    "Temperance": "#a0d8c8",
    "The Devil": "#a86088",
    "The Tower": "#c87878",
    "The Star": "#e8e878",
    "The Moon": "#88a8d0",
    "The Sun": "#f0b850",
    "Judgement": "#d0a0c8",
    "The World": "#88c8a0",
}

IP_LIMIT = 3
DEVICE_LIMIT = 2


def load_members():
    members = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT codename, salt, password, gender,
                       is_fool, recovery_hash, device_tokens, ip,
                       symbol, color, email
                FROM members
            """)
            for row in cur.fetchall():
                (codename, salt, password, gender, is_fool, recovery_hash,
                 device_tokens, ip, symbol, color, email) = row
                try:
                    tokens = json.loads(device_tokens) if device_tokens else []
                except (json.JSONDecodeError, TypeError):
                    tokens = []
                members[codename] = {
                    "salt": salt,
                    "password": password,
                    "gender": gender,
                    "is_fool": bool(is_fool),
                    "recovery_hash": recovery_hash,
                    "device_tokens": tokens,
                    "ip": ip,
                    "symbol": symbol,
                    "color": color,
                    "email": email,
                }
    return members


def save_members(members):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for codename, info in members.items():
                cur.execute("""
                    INSERT INTO members
                        (codename, salt, password, gender, is_fool, recovery_hash,
                         device_tokens, ip, symbol, color, email)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        email = EXCLUDED.email
                """, (
                    codename,
                    info["salt"],
                    info["password"],
                    info["gender"],
                    info.get("is_fool", False),
                    info.get("recovery_hash"),
                    json.dumps(info.get("device_tokens", [])),
                    info.get("ip"),
                    info.get("symbol"),
                    info.get("color"),
                    info.get("email"),
                ))
        conn.commit()


def count_registrations_from_ip(ip):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM members WHERE ip = %s", (ip,))
            return cur.fetchone()[0]


def make_salt():
    return secrets.token_hex(16)


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        100_000
    ).hex()


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
            cur.execute("""
                SELECT codename, expelled_by, expelled_at
                FROM expulsions
                ORDER BY id DESC
            """)
            return [
                {"codename": row[0], "expelled_by": row[1], "expelled_at": row[2]}
                for row in cur.fetchall()
            ]


def get_fool():
    members = load_members()
    for name, info in members.items():
        if info.get("is_fool"):
            return {"codename": name, **info}
    return None


def get_card_decorations(codename):
    symbol = CARD_SYMBOLS.get(codename, "·")
    color = CARD_COLORS.get(codename, "#b8b0c8")
    return symbol, color
