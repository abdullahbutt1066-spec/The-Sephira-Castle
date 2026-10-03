import hashlib
import secrets
from db import get_connection


def load_members():
    """Return dict of {codename: {salt, password, gender}}."""
    members = {}
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT codename, salt, password, gender FROM members")
            for codename, salt, password, gender in cur.fetchall():
                members[codename] = {
                    "salt": salt,
                    "password": password,
                    "gender": gender,
                }
    return members


def save_members(members):
    """Upsert all members. Used for full-sync saves."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for codename, info in members.items():
                cur.execute("""
                    INSERT INTO members (codename, salt, password, gender)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (codename) DO UPDATE SET
                        salt = EXCLUDED.salt,
                        password = EXCLUDED.password,
                        gender = EXCLUDED.gender
                """, (codename, info["salt"], info["password"], info["gender"]))
        conn.commit()


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
