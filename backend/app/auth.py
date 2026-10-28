"""
Business Reporting Dashboard — Authentication & Authorization (Milestone 5)

Features:
- Argon2id password hashing and verification (argon2-cffi)
- Cryptographically secure server-managed session tokens (SHA-256 hashed in DB)
- HTTP-only session cookies with configurable lifetime and security flags
- Double-submit and header-based CSRF protection with Origin validation
- Rate limiting for authentication endpoints
- Workspace-based Role-Based Access Control (RBAC: admin, editor, viewer)
- Production startup guard against single-user bypass
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import os
import re
import secrets
import uuid
from typing import Any, Callable, Dict, List, Optional

import argon2
from dotenv import load_dotenv
from fastapi import Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.db.models import Dashboard, Dataset, Template, Upload, User, Workspace, WorkspaceMember
from app.db.repositories import (
    DashboardRepository,
    DatasetRepository,
    SessionRepository,
    TemplateRepository,
    UploadRepository,
    UserRepository,
    WorkspaceRepository,
)
from app.db.session import get_db
from app.rate_limiter import rate_limiter

load_dotenv()
logger = logging.getLogger("auth_service")

# Argon2id password hasher with secure production defaults
_hasher = argon2.PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    type=argon2.Type.ID,
)

security_bearer = HTTPBearer(auto_error=False)

# Role hierarchy: admin (3) > editor (2) > viewer (1)
ROLE_HIERARCHY: Dict[str, int] = {
    "viewer": 1,
    "editor": 2,
    "admin": 3,
}

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Cryptographic & Password Helpers
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """Hash plaintext password using Argon2id."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against Argon2id hash with timing safety."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except argon2.exceptions.VerificationError:
        return False
    except Exception as exc:
        logger.warning(f"Unexpected error during password verification: {exc}")
        return False


def validate_password_strength(password: str) -> Optional[str]:
    """
    Validate password length and character complexity.
    Returns error message if invalid, or None if valid.
    """
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isalpha() for c in password):
        return "Password must contain at least one letter."
    if not any(c.isdigit() or not c.isalnum() for c in password):
        return "Password must contain at least one number or special character."
    return None


def generate_session_token() -> str:
    """Generate cryptographically secure opaque session token (256 bits entropy)."""
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    """Hash session token using SHA-256 before storing or querying the database."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate random CSRF token."""
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Cookie & Session Configuration
# ---------------------------------------------------------------------------

def get_session_lifetime_seconds() -> int:
    try:
        return int(os.getenv("SESSION_LIFETIME_SECONDS", str(7 * 24 * 3600)))
    except ValueError:
        return 7 * 24 * 3600


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").lower() == "production"


def get_cookie_domain() -> Optional[str]:
    domain = os.getenv("COOKIE_DOMAIN", "").strip()
    return domain if domain else None


def set_auth_cookies(
    response: Response,
    session_token: str,
    csrf_token: Optional[str] = None,
) -> None:
    """Set HTTP-only session cookie and client-readable CSRF token cookie."""
    max_age = get_session_lifetime_seconds()
    prod = is_production()
    domain = get_cookie_domain()

    response.set_cookie(
        key="session_token",
        value=session_token,
        max_age=max_age,
        expires=max_age,
        path="/",
        domain=domain,
        secure=prod,
        httponly=True,
        samesite="lax",
    )

    if csrf_token:
        response.set_cookie(
            key="csrf_token",
            value=csrf_token,
            max_age=max_age,
            expires=max_age,
            path="/",
            domain=domain,
            secure=prod,
            httponly=False,  # Client JS must read this to include in X-CSRF-Token header
            samesite="lax",
        )


def clear_auth_cookies(response: Response) -> None:
    """Clear session and CSRF cookies on logout."""
    domain = get_cookie_domain()
    response.delete_cookie(key="session_token", path="/", domain=domain)
    response.delete_cookie(key="csrf_token", path="/", domain=domain)


# ---------------------------------------------------------------------------
# CSRF and Origin Protection
# ---------------------------------------------------------------------------

def get_allowed_origins() -> List[str]:
    raw_origins = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [o.strip() for o in raw_origins.split(",") if o.strip()]


def verify_csrf_and_origin(
    request: Request,
    csrf_cookie: Optional[str] = Cookie(None, alias="csrf_token"),
    csrf_header: Optional[str] = Header(None, alias="X-CSRF-Token"),
) -> None:
    """
    Validates CSRF tokens and Origin/Referer for state-changing HTTP requests.
    Exempts safe methods: GET, HEAD, OPTIONS.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    # Skip in explicit test mode if configured
    if os.getenv("BYPASS_CSRF_FOR_TESTS", "false").lower() == "true":
        return

    # 1. Origin / Referer validation against allowed origins
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    allowed = get_allowed_origins()

    if origin:
        if origin not in allowed:
            logger.warning(f"CSRF origin mismatch: {origin} not in {allowed}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin request rejected from unapproved origin.",
            )
    elif referer:
        # Check that referer starts with one of the allowed origins
        if not any(referer.startswith(o) for o in allowed):
            logger.warning(f"CSRF referer mismatch: {referer} not in {allowed}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cross-origin request rejected from unapproved referer.",
            )

    # 2. Synchronizer token / Double-submit validation
    # If the request is authenticated via session cookie, CSRF token header is required
    session_cookie = request.cookies.get("session_token")
    if session_cookie or csrf_cookie:
        if not csrf_header:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing CSRF token header (X-CSRF-Token).",
            )
        if not csrf_cookie or not secrets.compare_digest(csrf_header.strip(), csrf_cookie.strip()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or tampered CSRF token.",
            )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AuthenticatedUser(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    role: str = "user"
    workspace_id: Optional[str] = None
    workspace_role: Optional[str] = None


class WorkspaceSummary(BaseModel):
    id: str
    name: str
    role: str
    created_at: str


class CurrentUserResponse(BaseModel):
    user: AuthenticatedUser
    workspaces: List[WorkspaceSummary]
    active_workspace: Optional[WorkspaceSummary] = None


# ---------------------------------------------------------------------------
# Core Current User Dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    request: Request,
    db: DBSession = Depends(get_db),
    bearer_creds: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
) -> AuthenticatedUser:
    """
    FastAPI dependency that extracts and validates the session against PostgreSQL.
    Extracts active workspace and role.
    Rejects unauthenticated requests with HTTP 401.
    """
    app_env = os.getenv("APP_ENV", "development").lower()
    dev_mode = os.getenv("SINGLE_USER_DEV_MODE", "false").lower() == "true"

    # Startup / runtime safety check: Dev mode strictly forbidden in production
    if app_env == "production" and dev_mode:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CRITICAL: SINGLE_USER_DEV_MODE cannot be enabled in production environment.",
        )

    # 1. Resolve raw session token from Cookie or Bearer header
    raw_token = request.cookies.get("session_token")
    if not raw_token and bearer_creds and bearer_creds.credentials:
        raw_token = bearer_creds.credentials.strip()

    # 2. Check local dev mode fallback if explicitly configured in non-production
    if not raw_token and dev_mode and app_env != "production":
        return AuthenticatedUser(
            id="00000000-0000-0000-0000-000000000001",
            email="dev@local.internal",
            display_name="Dev Administrator",
            role="admin",
            workspace_id="00000000-0000-0000-0000-000000000001",
            workspace_role="admin",
        )

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing session cookie or Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Hash session token and validate in PostgreSQL
    token_hash = hash_session_token(raw_token)
    session_repo = SessionRepository(db)
    session = session_repo.get_valid_session(token_hash)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Resolve user record
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with this session no longer exists.",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User account is {user.status}.",
        )

    # Touch session last_used timestamp
    session_repo.touch(session.id)

    # 5. Resolve active workspace and user's role in that workspace
    ws_repo = WorkspaceRepository(db)
    user_workspaces = ws_repo.list_user_workspaces(user.id)

    active_ws_id: Optional[str] = None
    active_role: Optional[str] = None

    # Check client-supplied workspace header
    requested_ws_id = request.headers.get("X-Workspace-ID")
    if requested_ws_id:
        # Verify user is actually a member of this workspace
        for ws in user_workspaces:
            if ws["id"] == requested_ws_id:
                active_ws_id = ws["id"]
                active_role = ws["role"]
                break

    # If no valid requested workspace, pick user's first workspace
    if not active_ws_id and user_workspaces:
        active_ws_id = user_workspaces[0]["id"]
        active_role = user_workspaces[0]["role"]

    return AuthenticatedUser(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        workspace_id=active_ws_id,
        workspace_role=active_role,
    )


# ---------------------------------------------------------------------------
# Workspace RBAC Authorization
# ---------------------------------------------------------------------------

def has_required_role(user_role: Optional[str], min_role: str) -> bool:
    """Check if user_role satisfies min_role based on the role hierarchy."""
    if not user_role:
        return False
    user_level = ROLE_HIERARCHY.get(user_role.lower(), 0)
    min_level = ROLE_HIERARCHY.get(min_role.lower(), 999)
    return user_level >= min_level


def require_role(min_role: str) -> Callable:
    """
    FastAPI dependency factory enforcing a minimum workspace role.
    Usage: Depends(require_role("editor"))
    """
    async def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not current_user.workspace_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation requires membership in an active workspace.",
            )
        if not has_required_role(current_user.workspace_role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires at least '{min_role}' role in this workspace (current role: '{current_user.workspace_role}').",
            )
        return current_user

    return role_checker


# ---------------------------------------------------------------------------
# Object-Level Authorization Helpers
# ---------------------------------------------------------------------------

def verify_workspace_membership(
    db: DBSession,
    user: AuthenticatedUser,
    workspace_id: uuid.UUID | str,
    min_role: str = "viewer",
) -> WorkspaceMember:
    """
    Verify that user is a member of the workspace with at least min_role.
    Raises 403 / 404 on failure.
    """
    ws_repo = WorkspaceRepository(db)
    member = ws_repo.get_member(workspace_id, user.id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or inaccessible.",
        )
    if not has_required_role(member.role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions in workspace. Requires '{min_role}'.",
        )
    return member


def verify_upload_access(
    db: DBSession,
    upload: Upload,
    user: AuthenticatedUser,
    min_role: str = "viewer",
) -> None:
    """
    Enforce ownership or workspace membership on an Upload record.
    Unassigned legacy uploads remain inaccessible to ordinary users.
    """
    if user.workspace_role and not has_required_role(user.workspace_role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions in workspace. Requires at least '{min_role}'.",
        )
    if user.role == "admin":
        return
    if upload.workspace_id:
        verify_workspace_membership(db, user, upload.workspace_id, min_role)
    elif upload.user_id:
        if str(upload.user_id) != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upload not found or inaccessible.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unassigned legacy upload is inaccessible without administrative adoption.",
        )


def verify_dashboard_access(
    db: DBSession,
    dashboard: Dashboard,
    user: AuthenticatedUser,
    min_role: str = "viewer",
) -> None:
    """Enforce ownership or workspace membership on a Dashboard record."""
    if user.workspace_role and not has_required_role(user.workspace_role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions in workspace. Requires at least '{min_role}'.",
        )
    if user.role == "admin":
        return
    if dashboard.workspace_id:
        verify_workspace_membership(db, user, dashboard.workspace_id, min_role)
    elif dashboard.user_id:
        if str(dashboard.user_id) != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard not found or inaccessible.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unassigned legacy dashboard is inaccessible.",
        )


def verify_template_access(
    db: DBSession,
    template: Template,
    user: AuthenticatedUser,
    min_role: str = "viewer",
) -> None:
    """Enforce ownership or workspace membership on a Template record."""
    if user.workspace_role and not has_required_role(user.workspace_role, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions in workspace. Requires at least '{min_role}'.",
        )
    if user.role == "admin":
        return
    if template.workspace_id:
        verify_workspace_membership(db, user, template.workspace_id, min_role)
    elif template.user_id:
        if str(template.user_id) != user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found or inaccessible.",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unassigned legacy template is inaccessible.",
        )
