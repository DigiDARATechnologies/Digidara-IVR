import base64
import hashlib
import hmac
import json
import os
import secrets
import time


DEFAULT_MAX_FAILED_LOGIN_ATTEMPTS = 3
DEFAULT_ACCOUNT_LOCKOUT_SECONDS = 60


class InvalidCredentialsError(Exception):
    """Authentication failed without revealing which credential was invalid."""

    def __init__(self, attempts_remaining: int | None = None) -> None:
        self.attempts_remaining = attempts_remaining
        super().__init__("Invalid email or password")


class AccountLockedError(Exception):
    """Authentication is temporarily blocked by the account lockout policy."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(int(retry_after_seconds), 1)
        super().__init__("Sign-in temporarily unavailable")


class WorkspaceRequiredError(Exception):
    """An email belongs to multiple workspaces and must be disambiguated."""


class GoogleTokenError(Exception):
    """A Google Sign-In credential could not be verified."""


def verify_google_id_token(credential: str) -> dict:
    """Verify a Google Identity Services credential and return its claims.

    Raises GoogleTokenError for any invalid, expired, wrong-audience, or
    unverified-email token rather than letting a third-party library
    exception leak past this boundary.
    """
    client_id = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    if not client_id:
        raise GoogleTokenError("Google sign-in is not configured")
    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token

        claims = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), client_id,
        )
    except Exception as exc:
        raise GoogleTokenError("Invalid Google credential") from exc
    if not claims.get("email_verified"):
        raise GoogleTokenError("Google account email is not verified")
    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise GoogleTokenError("Google credential did not include an email")
    return {
        "email": email,
        "full_name": (claims.get("name") or email.split("@")[0]).strip(),
        "google_subject": claims.get("sub"),
    }


def _bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    return min(max(value, minimum), maximum)


def account_lockout_policy() -> tuple[int, int]:
    """Return maximum failures and lock duration with operational safety bounds."""
    return (
        _bounded_int_env(
            "AUTH_MAX_FAILED_LOGIN_ATTEMPTS",
            DEFAULT_MAX_FAILED_LOGIN_ATTEMPTS,
            3,
            20,
        ),
        _bounded_int_env(
            "AUTH_ACCOUNT_LOCKOUT_SECONDS",
            DEFAULT_ACCOUNT_LOCKOUT_SECONDS,
            60,
            86400,
        ),
    )

ITERATIONS = 310_000

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt), int(iterations))
        return hmac.compare_digest(actual, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


def authenticate_user(
    db, email: str, password: str, workspace_slug: str | None = None,
) -> dict:
    """Authenticate an active user while enforcing consecutive-failure lockout."""
    maximum_attempts, lockout_seconds = account_lockout_policy()
    cursor = db.cursor()
    select = """SELECT u.id,u.organization_id,u.email,u.password_hash,u.full_name,
                       u.role_code,u.is_active,u.failed_login_attempts,u.locked_until,
                       o.slug AS workspace_slug,o.name AS organization_name,
                       COUNT(*) OVER() AS matching_accounts,
                       (u.locked_until IS NOT NULL AND u.locked_until > CURRENT_TIMESTAMP)
                         AS is_locked,
                       GREATEST(0,TIMESTAMPDIFF(SECOND,CURRENT_TIMESTAMP,u.locked_until))
                         AS retry_after_seconds
                FROM app_users u
                JOIN organizations o
                  ON o.id=u.organization_id AND o.status='active'
                WHERE u.email=%s"""
    normalized_slug = (workspace_slug or "").strip().lower()
    if normalized_slug:
        cursor.execute(
            select + " AND o.slug=%s ORDER BY u.id LIMIT 1",
            (email.strip().lower(), normalized_slug),
        )
    else:
        cursor.execute(
            select + " ORDER BY u.id LIMIT 1",
            (email.strip().lower(),),
        )
    user = cursor.fetchone()
    if not user or not user.get("is_active"):
        raise InvalidCredentialsError()
    if int(user.get("matching_accounts") or 1) != 1:
        raise WorkspaceRequiredError()
    if user.get("is_locked"):
        raise AccountLockedError(user.get("retry_after_seconds") or 1)
    if not verify_password(password, user.get("password_hash") or ""):
        cursor.execute(
            """UPDATE app_users
               SET failed_login_attempts=failed_login_attempts+1,
                   locked_until=CASE
                     WHEN failed_login_attempts+1 >= %s
                     THEN TIMESTAMPADD(SECOND,%s,CURRENT_TIMESTAMP)
                     ELSE locked_until
                   END
               WHERE id=%s""",
            (maximum_attempts, lockout_seconds, user["id"]),
        )
        cursor.execute(
            """SELECT failed_login_attempts,
                      (locked_until IS NOT NULL AND locked_until > CURRENT_TIMESTAMP)
                        AS is_locked,
                      GREATEST(0,TIMESTAMPDIFF(SECOND,CURRENT_TIMESTAMP,locked_until))
                        AS retry_after_seconds
               FROM app_users WHERE id=%s""",
            (user["id"],),
        )
        failure = cursor.fetchone() or {}
        if failure.get("is_locked"):
            cursor.execute(
                """INSERT INTO audit_logs (organization_id,actor_user_id,action,resource_type,resource_id,result,metadata_json)
                   VALUES (%s,%s,'auth_account_locked','app_user',%s,'failure',%s)""",
                (
                    user["organization_id"],
                    user["id"],
                    str(user["id"]),
                    json.dumps({"reason": "max_failed_login_attempts_exceeded", "attempts": failure.get("failed_login_attempts")}),
                ),
            )
            db.commit()
            raise AccountLockedError(failure.get("retry_after_seconds") or lockout_seconds)
        attempts = int(failure.get("failed_login_attempts") or 0)
        cursor.execute(
            """INSERT INTO audit_logs (organization_id,actor_user_id,action,resource_type,resource_id,result,metadata_json)
               VALUES (%s,%s,'auth_login_failed','app_user',%s,'failure',%s)""",
            (
                user["organization_id"],
                user["id"],
                str(user["id"]),
                json.dumps({"attempts_remaining": max(maximum_attempts - attempts, 0)}),
            ),
        )
        db.commit()
        raise InvalidCredentialsError(max(maximum_attempts - attempts, 0))
    cursor.execute(
        """UPDATE app_users
           SET last_login_at=CURRENT_TIMESTAMP,failed_login_attempts=0,locked_until=NULL
           WHERE id=%s""",
        (user["id"],),
    )
    cursor.execute(
        """INSERT INTO audit_logs (organization_id,actor_user_id,action,resource_type,resource_id,result)
           VALUES (%s,%s,'auth_login_success','app_user',%s,'success')""",
        (user["organization_id"], user["id"], str(user["id"])),
    )
    db.commit()
    return user

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")

def issue_token(user: dict) -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32: raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    header = _b64(json.dumps({"alg":"HS256","typ":"JWT"}, separators=(",",":")).encode())
    payload = _b64(json.dumps({"sub":user["id"],"email":user["email"],"role":user["role_code"],"organization_id":user["organization_id"],"exp":int(time.time())+28800}, separators=(",",":")).encode())
    signature = _b64(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"

def decode_token(token: str) -> dict:
    secret = os.getenv("JWT_SECRET", "")
    header, payload, signature = token.split(".")
    expected = _b64(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected): raise ValueError("Invalid token")
    padded = payload + "=" * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(padded))
    if int(data.get("exp", 0)) < time.time(): raise ValueError("Token expired")
    return data
