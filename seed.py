"""Create or repair the first DigiDara administrator account.

Default local-development usage:
    python seed.py

This creates/repairs:
    email: digidaratech@gmail.com
    password: DIgiDARA@123

Non-interactive usage (PowerShell):
    $env:ADMIN_NAME="DigiDara Admin"
    $env:ADMIN_EMAIL="admin@digidara.com"
    $env:ADMIN_PASSWORD="use-a-strong-password"
    python seed.py --non-interactive

The script is idempotent. If the email already exists, it updates that account's
name, password, role and active status instead of inserting a duplicate.
"""

import argparse
import os
import re
import sys

from app.services.auth_service import hash_password, verify_password


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def seed_admin(non_interactive: bool = False) -> int:
    # Requested zero-input local seed. Environment values can override these
    # defaults for another machine without modifying this file.
    name = (os.getenv("ADMIN_NAME") or "DigiDara Admin").strip()
    email = (os.getenv("ADMIN_EMAIL") or "digidaratech@gmail.com").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or "DigiDARA@123"
    print("\nDigiDara administrator seed")
    print("----------------------------")
    print(f"Administrator: {name} <{email}>")

    if len(name) < 2:
        print("Administrator name must contain at least 2 characters.", file=sys.stderr)
        return 2
    if not EMAIL_RE.fullmatch(email):
        print("Enter a valid administrator email address.", file=sys.stderr)
        return 2
    if len(password) < 10:
        print("Password must contain at least 10 characters.", file=sys.stderr)
        return 2

    try:
        from app.database.db import get_db_connection, init_db
    except ModuleNotFoundError as exc:
        print(
            f"Missing Python dependency: {exc.name}. Activate the backend virtual environment "
            "and run: pip install -r app/requirements.txt",
            file=sys.stderr,
        )
        return 3

    # Creates the configured database and applies all current schema migrations.
    init_db()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM app_users WHERE organization_id=1 AND email=%s LIMIT 1",
            (email,),
        )
        existing = cursor.fetchone()
        encoded = hash_password(password)
        if existing:
            user_id = existing["id"]
            cursor.execute(
                """UPDATE app_users SET full_name=%s,password_hash=%s,
                   role_code='admin',is_active=TRUE,failed_login_attempts=0,
                   locked_until=NULL WHERE id=%s""",
                (name, encoded, user_id),
            )
            action = "updated"
        else:
            cursor.execute(
                """INSERT INTO app_users
                   (organization_id,email,password_hash,full_name,role_code,is_active)
                   VALUES (1,%s,%s,%s,'admin',TRUE)""",
                (email, encoded, name),
            )
            user_id = cursor.lastrowid
            action = "created"

        cursor.execute(
            """INSERT INTO audit_logs
               (organization_id,actor_user_id,action,resource_type,resource_id,result)
               VALUES (1,%s,'admin_seeded','app_user',%s,'success')""",
            (user_id, str(user_id)),
        )
        conn.commit()

        cursor.execute("SELECT password_hash FROM app_users WHERE id=%s", (user_id,))
        saved = cursor.fetchone() or {}
        if not verify_password(password, saved.get("password_hash") or ""):
            raise RuntimeError("Saved password verification failed")

        print(f"\nAdministrator {action} successfully.")
        print(f"Login email: {email}")
        print("Local login password: DigiDARA@123" if not os.getenv("ADMIN_PASSWORD") else "Login with the ADMIN_PASSWORD environment value.")
        print("Open http://localhost:5173/login and sign in with these credentials.")
        print("ADMIN_BOOTSTRAP_KEY is not required for seeded login.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the first DigiDara administrator")
    parser.add_argument("--non-interactive", action="store_true", help="Compatibility option; seed.py is already non-interactive")
    args = parser.parse_args()
    raise SystemExit(seed_admin(non_interactive=args.non_interactive))