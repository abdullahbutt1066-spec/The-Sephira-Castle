import os
import psycopg
from dotenv import load_dotenv

# Load .env locally (no effect in production where env vars are set directly)
load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")


def get_connection():
    """Return a new connection to the Neon Postgres database."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set. Check your .env file.")
    return psycopg.connect(DATABASE_URL)


def init_db():
    """Create tables if they don't exist. Safe to run every startup."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    codename TEXT PRIMARY KEY,
                    salt TEXT NOT NULL,
                    password TEXT NOT NULL,
                    gender TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    time TEXT NOT NULL
                )
            """)
        conn.commit()
