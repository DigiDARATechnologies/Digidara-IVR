"""Controlled organization provisioning and first-administrator assignment."""

from __future__ import annotations

import re

import pymysql

from app.services.auth_service import WorkspaceRequiredError, hash_password


class WorkspaceConflictError(Exception):
    """A requested workspace identifier or administrator already exists."""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:90] or "workspace"


_PUBLIC_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "protonmail.com", "aol.com", "live.com",
}


def _default_workspace_name(email: str, full_name: str) -> str:
    domain = email.split("@")[-1].lower()
    if domain and domain not in _PUBLIC_EMAIL_DOMAINS:
        return domain.split(".")[0].capitalize()
    first_name = (full_name or email.split("@")[0]).split(" ")[0]
    return f"{first_name}'s Workspace"


def _unique_slug(cursor, base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 1
    while True:
        cursor.execute("SELECT 1 FROM organizations WHERE slug=%s", (candidate,))
        if not cursor.fetchone():
            return candidate
        suffix += 1
        candidate = f"{slug}-{suffix}"


def create_workspace_with_admin(
    db,
    *,
    organization_name: str,
    workspace_slug: str,
    admin_name: str,
    admin_email: str,
    admin_password: str,
) -> dict:
    """Create or claim an empty workspace and atomically add its first admin."""
    cursor = db.cursor()
    slug = workspace_slug.strip().lower()
    email = admin_email.strip().lower()
    try:
        cursor.execute(
            "SELECT id FROM organizations WHERE slug=%s FOR UPDATE",
            (slug,),
        )
        existing = cursor.fetchone()
        if existing:
            organization_id = int(existing["id"])
            cursor.execute(
                "SELECT COUNT(*) total FROM app_users WHERE organization_id=%s",
                (organization_id,),
            )
            if int((cursor.fetchone() or {}).get("total") or 0) != 0:
                raise WorkspaceConflictError("That workspace ID is already registered")
            cursor.execute(
                "UPDATE organizations SET name=%s,status='active' WHERE id=%s",
                (organization_name.strip(), organization_id),
            )
        else:
            cursor.execute(
                "INSERT INTO organizations (name,slug,status) VALUES (%s,%s,'active')",
                (organization_name.strip(), slug),
            )
            organization_id = int(cursor.lastrowid)

        cursor.execute(
            """INSERT INTO app_users
               (organization_id,email,password_hash,full_name,role_code,is_active)
               VALUES (%s,%s,%s,%s,'admin',TRUE)""",
            (
                organization_id,
                email,
                hash_password(admin_password),
                admin_name.strip(),
            ),
        )
        user_id = int(cursor.lastrowid)
        cursor.execute(
            """INSERT INTO audit_logs
               (organization_id,actor_user_id,action,resource_type,resource_id,result)
               VALUES (%s,%s,'workspace_created','organization',%s,'success')""",
            (organization_id, user_id, str(organization_id)),
        )
        db.commit()
    except WorkspaceConflictError:
        db.rollback()
        raise
    except pymysql.IntegrityError as exc:
        db.rollback()
        raise WorkspaceConflictError(
            "That workspace ID or administrator email is already registered"
        ) from exc
    except Exception:
        db.rollback()
        raise

    return {
        "id": user_id,
        "organization_id": organization_id,
        "organization_name": organization_name.strip(),
        "workspace_slug": slug,
        "email": email,
        "full_name": admin_name.strip(),
        "role_code": "admin",
    }


def find_or_create_user_via_google(db, *, email: str, full_name: str) -> dict:
    """Resolve a verified Google identity to an app_users row.

    - Exactly one active-organization match: signs that user in.
    - No match: auto-provisions a brand-new workspace and admin account with
      no password (Google is that account's only sign-in method).
    - More than one match: the email is registered under multiple
      workspaces; Google sign-in has no workspace picker, so this fails
      closed and the caller should use password + workspace-ID sign-in
      instead, matching the same guardrail password login already applies.
    """
    email = email.strip().lower()
    cursor = db.cursor()
    cursor.execute(
        """SELECT u.id,u.organization_id,u.email,u.full_name,u.role_code,u.is_active,
                  o.slug AS workspace_slug,o.name AS organization_name,
                  COUNT(*) OVER() AS matching_accounts
           FROM app_users u
           JOIN organizations o ON o.id=u.organization_id AND o.status='active'
           WHERE u.email=%s
           ORDER BY u.id LIMIT 1""",
        (email,),
    )
    existing = cursor.fetchone()
    if existing:
        if int(existing.get("matching_accounts") or 1) != 1:
            raise WorkspaceRequiredError()
        if not existing.get("is_active"):
            raise WorkspaceRequiredError()
        cursor.execute(
            "UPDATE app_users SET last_login_at=CURRENT_TIMESTAMP WHERE id=%s",
            (existing["id"],),
        )
        db.commit()
        return existing

    organization_name = _default_workspace_name(email, full_name)
    try:
        slug = _unique_slug(cursor, organization_name)
        cursor.execute(
            "INSERT INTO organizations (name,slug,status) VALUES (%s,%s,'active')",
            (organization_name, slug),
        )
        organization_id = int(cursor.lastrowid)
        cursor.execute(
            """INSERT INTO app_users
               (organization_id,email,password_hash,full_name,role_code,is_active,last_login_at)
               VALUES (%s,%s,NULL,%s,'admin',TRUE,CURRENT_TIMESTAMP)""",
            (organization_id, email, (full_name or email.split("@")[0]).strip()),
        )
        user_id = int(cursor.lastrowid)
        cursor.execute(
            """INSERT INTO audit_logs
               (organization_id,actor_user_id,action,resource_type,resource_id,result)
               VALUES (%s,%s,'workspace_created_via_google','organization',%s,'success')""",
            (organization_id, user_id, str(organization_id)),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "id": user_id,
        "organization_id": organization_id,
        "organization_name": organization_name,
        "workspace_slug": slug,
        "email": email,
        "full_name": (full_name or email.split("@")[0]).strip(),
        "role_code": "admin",
    }
