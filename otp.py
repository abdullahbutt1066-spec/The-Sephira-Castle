import os
import secrets
from datetime import datetime, timedelta
from db import get_connection

OTP_EXPIRY_MINUTES = 10


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


def create_otp(codename):
    code = generate_otp()
    expires_at = (datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE otp_codes SET used = TRUE WHERE codename = %s AND used = FALSE",
                (codename,)
            )
            cur.execute(
                "INSERT INTO otp_codes (codename, code, expires_at, used) VALUES (%s, %s, %s, FALSE)",
                (codename, code, expires_at)
            )
        conn.commit()
    return code


def verify_otp(codename, code):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, expires_at FROM otp_codes
                WHERE codename = %s AND code = %s AND used = FALSE
                ORDER BY id DESC LIMIT 1
            """, (codename, code))
            row = cur.fetchone()
            if not row:
                return False

            otp_id, expires_at_str = row
            try:
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return False

            if datetime.now() > expires_at:
                return False

            cur.execute("UPDATE otp_codes SET used = TRUE WHERE id = %s", (otp_id,))
        conn.commit()
    return True


def send_otp_email(to_email, code):
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        print("WARNING: RESEND_API_KEY not set. Email not sent.")
        return False

    try:
        import resend
        resend.api_key = api_key

        params = {
            "from": "Tarot Club <onboarding@resend.dev>",
            "to": [to_email],
            "subject": "Your Recovery Code — Tarot Club",
            "html": f"""
                <div style="font-family: Georgia, serif; padding: 30px; background: #14121a; color: #d8d4e0;">
                    <h1 style="color: #c4a8ff;">The Sephiroth Castle</h1>
                    <p>You have requested to reset your recovery password.</p>
                    <p>Your one-time code is:</p>
                    <p style="font-size: 32px; letter-spacing: 8px; color: #c4a8ff; font-weight: bold;">{code}</p>
                    <p style="color: #8a7fb0; font-size: 0.9em;">This code expires in {OTP_EXPIRY_MINUTES} minutes.</p>
                    <p style="color: #8a7fb0; font-size: 0.9em;">If you did not request this, ignore this message.</p>
                </div>
            """
        }
        resend.Emails.send(params)
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False
