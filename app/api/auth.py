import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from app.database.db import get_db
from app.services.rate_limiter import (
    get_auth_rate_limit,
    get_bootstrap_rate_limit,
    limiter,
)
from app.services.auth_service import (
    AccountLockedError,
    GoogleTokenError,
    InvalidCredentialsError,
    WorkspaceRequiredError,
    authenticate_user,
    decode_token,
    hash_password,
    issue_token,
    verify_google_id_token,
)
from app.services import workspace_service

router = APIRouter(tags=["Authentication"])

class AdminInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=190)
    password: str = Field(min_length=10, max_length=128)
    bootstrap_key: str | None = None

class LoginInput(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=190)
    password: str
    workspace_slug: str | None = Field(
        default=None,
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    )


class GoogleAuthInput(BaseModel):
    credential: str = Field(min_length=10)


class OrganizationUpdateInput(BaseModel):
    name: str = Field(min_length=2, max_length=180)


class WorkspaceInput(BaseModel):
    organization_name: str = Field(min_length=2, max_length=180)
    workspace_slug: str = Field(
        min_length=3,
        max_length=100,
        pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$",
    )
    full_name: str = Field(min_length=2, max_length=150)
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=190)
    password: str = Field(min_length=10, max_length=128)


def _require_bootstrap_key(value: str | None) -> None:
    expected = os.getenv("ADMIN_BOOTSTRAP_KEY", "")
    if (
        len(expected) < 12
        or not value
        or not secrets.compare_digest(value, expected)
    ):
        raise HTTPException(403, "Invalid bootstrap key")

def current_admin(authorization: str | None = Header(default=None), db=Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Sign in as an administrator")
    try: claims = decode_token(authorization[7:])
    except Exception: raise HTTPException(401, "Session is invalid or expired")
    cur=db.cursor(); cur.execute("SELECT u.id,u.organization_id,u.email,u.full_name,u.role_code,u.is_active,o.name AS organization_name,o.slug AS workspace_slug FROM app_users u JOIN organizations o ON o.id=u.organization_id AND o.status='active' WHERE u.id=%s", (claims["sub"],)); user=cur.fetchone()
    if not user or not user["is_active"] or user["role_code"] != "admin": raise HTTPException(403, "Administrator access required")
    if int(claims.get("organization_id") or 0) != int(user["organization_id"]):
        raise HTTPException(401, "Session is invalid or expired")
    return user

@router.get("/auth/status")
def auth_status(db=Depends(get_db)):
    cur=db.cursor(); cur.execute("SELECT COUNT(*) total FROM app_users WHERE role_code='admin' AND password_hash IS NOT NULL")
    return {"needs_admin_onboarding": int((cur.fetchone() or {}).get("total") or 0) == 0}

@router.post("/auth/bootstrap-admin")
def bootstrap_admin(*args, **kwargs):
    request = next((a for a in args if isinstance(a, Request)), kwargs.get("request"))
    data = next((a for a in args if isinstance(a, AdminInput)), kwargs.get("data"))
    db = next((a for a in args if not isinstance(a, (Request, AdminInput))), kwargs.get("db"))
    if request:
        limiter.enforce(request, "bootstrap_admin", limit=get_bootstrap_rate_limit())
    cur=db.cursor(); cur.execute("SELECT COUNT(*) total FROM app_users WHERE role_code='admin' AND password_hash IS NOT NULL")
    if int((cur.fetchone() or {}).get("total") or 0) != 0: raise HTTPException(409, "Administrator already exists")
    _require_bootstrap_key(data.bootstrap_key)
    cur.execute("SELECT id FROM organizations WHERE status='active' ORDER BY id LIMIT 1")
    organization = cur.fetchone()
    if not organization: raise HTTPException(503, "No active organization is configured")
    organization_id = int(organization["id"])
    cur.execute("INSERT INTO app_users (organization_id,email,password_hash,full_name,role_code) VALUES (%s,%s,%s,%s,'admin')", (organization_id,data.email.lower(),hash_password(data.password),data.full_name.strip()))
    db.commit(); cur.execute("SELECT id,organization_id,email,full_name,role_code FROM app_users WHERE id=%s",(cur.lastrowid,)); user=cur.fetchone()
    return {"token":issue_token(user),"user":user}


@router.post("/auth/workspaces", status_code=201)
def create_workspace(*args, **kwargs):
    """Register a workspace and its first administrator."""
    request = next((a for a in args if isinstance(a, Request)), kwargs.get("request"))
    data = next((a for a in args if isinstance(a, WorkspaceInput)), kwargs.get("data"))
    db = next((a for a in args if not isinstance(a, (Request, WorkspaceInput))), kwargs.get("db"))
    if request:
        limiter.enforce(request, "create_workspace", limit=get_auth_rate_limit())
    try:
        user = workspace_service.create_workspace_with_admin(
            db,
            organization_name=data.organization_name,
            workspace_slug=data.workspace_slug,
            admin_name=data.full_name,
            admin_email=data.email,
            admin_password=data.password,
        )
    except workspace_service.WorkspaceConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"token": issue_token(user), "user": user}

@router.post("/auth/login")
def login(*args, **kwargs):
    request = next((a for a in args if isinstance(a, Request)), kwargs.get("request"))
    data = next((a for a in args if isinstance(a, LoginInput)), kwargs.get("data"))
    db = next((a for a in args if not isinstance(a, (Request, LoginInput))), kwargs.get("db"))
    if request:
        limiter.enforce(request, "login", limit=get_auth_rate_limit())
    try:
        user = authenticate_user(
            db, data.email, data.password, data.workspace_slug
        )
    except WorkspaceRequiredError:
        raise HTTPException(
            401,
            {
                "code": "workspace_required",
                "message": "Enter your workspace ID to continue",
            },
        )
    except AccountLockedError as exc:
        raise HTTPException(
            429,
            {
                "code": "account_locked",
                "message": "Sign-in temporarily unavailable. Try again later",
                "retry_after_seconds": exc.retry_after_seconds,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )
    except InvalidCredentialsError as exc:
        detail = {
            "code": "invalid_credentials",
            "message": "Invalid email or password",
        }
        if exc.attempts_remaining is not None:
            detail["attempts_remaining"] = exc.attempts_remaining
        raise HTTPException(401, detail)
    return {"token":issue_token(user),"user":{k:user[k] for k in ("id","organization_id","organization_name","workspace_slug","email","full_name","role_code")}}

@router.post("/auth/google")
def google_login(*args, **kwargs):
    request = next((a for a in args if isinstance(a, Request)), kwargs.get("request"))
    data = next((a for a in args if isinstance(a, GoogleAuthInput)), kwargs.get("data"))
    db = next((a for a in args if not isinstance(a, (Request, GoogleAuthInput))), kwargs.get("db"))
    if request:
        limiter.enforce(request, "google_login", limit=get_auth_rate_limit())
    try:
        claims = verify_google_id_token(data.credential)
    except GoogleTokenError as exc:
        raise HTTPException(401, {"code": "invalid_google_credential", "message": str(exc)})
    try:
        user = workspace_service.find_or_create_user_via_google(
            db, email=claims["email"], full_name=claims["full_name"],
        )
    except WorkspaceRequiredError:
        raise HTTPException(
            401,
            {
                "code": "workspace_required",
                "message": "This email is registered under multiple workspaces. "
                "Sign in with your workspace ID and password instead.",
            },
        )
    return {"token": issue_token(user), "user": {
        k: user[k] for k in
        ("id", "organization_id", "organization_name", "workspace_slug", "email", "full_name", "role_code")
    }}


@router.patch("/organizations/me")
def update_organization(data: OrganizationUpdateInput, admin=Depends(current_admin), db=Depends(get_db)):
    """Renames the caller's own organization. This name is what the AI
    introduces itself as on every live call (see build_greeting_instruction
    in conversation_policy_service.py), so a change here takes effect on
    the very next call — no redeploy needed."""
    name = data.name.strip()
    cur = db.cursor()
    cur.execute("UPDATE organizations SET name=%s WHERE id=%s", (name, admin["organization_id"]))
    cur.execute(
        "INSERT INTO audit_logs (organization_id,actor_user_id,action,resource_type,resource_id,result) "
        "VALUES (%s,%s,'organization_renamed','organization',%s,'success')",
        (admin["organization_id"], admin["id"], str(admin["organization_id"])),
    )
    db.commit()
    return {"organization_name": name}


@router.post("/admin/users")
def create_admin(data: AdminInput, admin=Depends(current_admin), db=Depends(get_db)):
    cur=db.cursor()
    try: cur.execute("INSERT INTO app_users (organization_id,email,password_hash,full_name,role_code) VALUES (%s,%s,%s,%s,'admin')",(admin["organization_id"],data.email.lower(),hash_password(data.password),data.full_name.strip())); db.commit()
    except Exception: db.rollback(); raise HTTPException(409,"That email is already registered")
    new_id=cur.lastrowid
    cur.execute("INSERT INTO audit_logs (organization_id,actor_user_id,action,resource_type,resource_id,result) VALUES (%s,%s,'admin_user_created','app_user',%s,'success')",(admin["organization_id"],admin["id"],str(new_id))); db.commit()
    return {"message":"Administrator created"}
