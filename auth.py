import hashlib
import secrets
import json
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

IP_LIMIT = 3
DEVICE_LIMIT = 2


def load_members():
    members = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT codename, salt, password, gender,
                       is_fool, recovery_hash, device_tokens, ip
                FROM members
            """)
            for row in cur.fetchall():
                codename, salt, password, gender, is_fool, recovery_hash, device_tokens, ip = row
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
                }
    return members


def save_members(members):
    with get_connection() as conn:
        with conn.cursor() as cur:
            for codename, info in members.items():
                cur.execute("""
                    INSERT INTO members
                        (codename, salt, password, gender, is_fool, recovery_hash, device_tokens, ip)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codename) DO UPDATE SET
                        salt = EXCLUDED.salt,
                        password = EXCLUDED.password,
                        gender = EXCLUDED.gender,
                        is_fool = EXCLUDED.is_fool,
                        recovery_hash = EXCLUDED.recovery_hash,
                        device_tokens = EXCLUDED.device_tokens,
                        ip = EXCLUDED.ip
                """, (
                    codename,
                    info["salt"],
                    info["password"],
                    info["gender"],
                    info.get("is_fool", False),
                    info.get("recovery_hash"),
                    json.dumps(info.get("device_tokens", [])),
                    info.get("ip"),
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
    """Recovery hash is stored as 'hash:salt'. Verify the input against it."""
    if not recovery_hash:
        return False
    try:
        stored_hash, salt = recovery_hash.split(":", 1)
    except ValueError:
        return False
    return hash_password(recovery_input, salt) == stored_hash


def make_device_token():
    return secrets.token_hex(24)
