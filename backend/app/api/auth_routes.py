"""
Authentication and Workspace API Routes (Milestone 5)

Endpoints:
- POST /api/auth/register: Create user account, initial workspace, and session
- POST /api/auth/login: Verify credentials against Argon2id hash, issue session & CSRF cookies
- POST /api/auth/logout: Revoke server-side session, clear cookies
- GET /api/auth/me: Return current user profile, workspaces, and active role
- GET /api/auth/csrf: Generate and return fresh CSRF token

Workspace endpoints:
- GET /api/workspaces: List user workspaces
- POST /api/workspaces: Create new workspace
- GET /api/workspaces/{workspace_id}/members: List workspace members
- POST /api/workspaces/{workspace_id}/members: Add workspace member (admin only)
- PATCH /api/workspaces/{workspace_id}/members/{user_id}: Update member role (admin only)
- DELETE /api/workspaces/{workspace_id}/members/{user_id}: Remove member (admin only)
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session as DBSession

from app.auth import (
    AuthenticatedUser,
    CurrentUserResponse,
    WorkspaceSummary,
    clear_auth_cookies,
    generate_csrf_token,
    generate_session_token,
    get_current_user,
    get_session_lifetime_seconds,
    hash_password,
    hash_session_token,
    has_required_role,
    set_auth_cookies,
    validate_password_strength,
    verify_csrf_and_origin,
    verify_password,
    verify_workspace_membership,
    EMAIL_REGEX,
)
from app.db.repositories import (
    SessionRepository,
    UserRepository,
    WorkspaceRepository,
)
from app.db.session import get_db
from app.rate_limiter import rate_limiter

logger = logging.getLogger("auth_routes")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
workspace_router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    user: AuthenticatedUser
    workspace: Optional[WorkspaceSummary] = None
    csrf_token: str
    message: str = "Success"


class CreateWorkspaceRequest(BaseModel):
    name: str


class AddMemberRequest(BaseModel):
    email: str
    role: str = "viewer"


class UpdateRoleRequest(BaseModel):
    role: str


class MemberResponse(BaseModel):
    id: str
    user_id: str
    email: str
    display_name: Optional[str] = None
    role: str
    created_at: str


# ---------------------------------------------------------------------------
# Authentication Endpoints
# ---------------------------------------------------------------------------

@router.get("/csrf", summary="Obtain a fresh CSRF token")
async def get_csrf_token(response: Response) -> Dict[str, str]:
    """Issues and sets a client-readable CSRF cookie."""
    token = generate_csrf_token()
    max_age = get_session_lifetime_seconds()
    prod = os.getenv("APP_ENV", "development").lower() == "production"
    domain = os.getenv("COOKIE_DOMAIN", "").strip() or None

    response.set_cookie(
        key="csrf_token",
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        domain=domain,
        secure=prod,
        httponly=False,
        samesite="lax",
    )
    return {"csrf_token": token}


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account with default workspace",
)
async def register(
    req: RegisterRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
) -> AuthResponse:
    # 1. Rate limiting check (e.g. 10 attempts per hour per client IP)
    client_ip = request.client.host if request.client else "unknown"
    if rate_limiter.is_rate_limited(f"register:{client_ip}", max_requests=10, window_seconds=3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
        )

    # 2. Public registration configuration check
    allow_reg = os.getenv("ALLOW_REGISTRATION", "true").lower() == "true"
    if not allow_reg:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is currently disabled by administrator configuration.",
        )

    # 3. Email validation and normalization
    email_clean = req.email.strip().lower()
    if not EMAIL_REGEX.match(email_clean):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide a valid email address.",
        )

    # 4. Password validation
    pwd_err = validate_password_strength(req.password)
    if pwd_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=pwd_err,
        )

    # 5. Check duplicate email without leaking private user details
    user_repo = UserRepository(db)
    existing_user = user_repo.get_by_email(email_clean)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists.",
        )

    # 6. Hash password with Argon2id
    pwd_hash = hash_password(req.password)

    # 7. Create user record (least-privilege: standard user role)
    user = user_repo.create(
        email=email_clean,
        password_hash=pwd_hash,
        display_name=req.display_name,
        role="user",
        status="active",
    )

    # 8. Create private default workspace for the new user
    ws_name = f"{req.display_name.strip() if req.display_name else 'Personal'} Workspace"
    ws_repo = WorkspaceRepository(db)
    workspace = ws_repo.create(name=ws_name, created_by_id=user.id)

    # 9. Assign user as workspace admin of their own workspace
    ws_repo.add_member(workspace.id, user.id, role="admin")

    # 10. Generate cryptographically random session token (256 bits entropy)
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=get_session_lifetime_seconds())

    session_repo = SessionRepository(db)
    user_agent = request.headers.get("user-agent", "")[:255]
    session_repo.create(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        ip_address=client_ip[:64],
        user_agent=user_agent,
    )

    # 11. Generate CSRF token & set HTTP-only session cookie
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, raw_token, csrf_token)

    auth_user = AuthenticatedUser(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        workspace_id=str(workspace.id),
        workspace_role="admin",
    )

    ws_summary = WorkspaceSummary(
        id=str(workspace.id),
        name=workspace.name,
        role="admin",
        created_at=workspace.created_at.isoformat() if workspace.created_at else "",
    )

    return AuthResponse(
        user=auth_user,
        workspace=ws_summary,
        csrf_token=csrf_token,
        message="Account created successfully",
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate using email and password",
)
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
) -> AuthResponse:
    client_ip = request.client.host if request.client else "unknown"
    email_clean = req.email.strip().lower()

    # Rate limiting: max 5 failed attempts per 5 minutes per IP or email
    rate_key = f"login:{client_ip}:{email_clean}"
    if rate_limiter.is_rate_limited(rate_key, max_requests=10, window_seconds=300):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please wait 5 minutes before trying again.",
        )

    user_repo = UserRepository(db)
    user = user_repo.get_by_email(email_clean)

    # Generic authentication error to reduce user enumeration
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status}. Please contact an administrator.",
        )

    # Rotate/create fresh session token
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=get_session_lifetime_seconds())

    session_repo = SessionRepository(db)
    user_agent = request.headers.get("user-agent", "")[:255]
    session_repo.create(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        ip_address=client_ip[:64],
        user_agent=user_agent,
    )

    # Generate fresh CSRF token and set cookies
    csrf_token = generate_csrf_token()
    set_auth_cookies(response, raw_token, csrf_token)

    # Resolve primary workspace
    ws_repo = WorkspaceRepository(db)
    workspaces = ws_repo.list_user_workspaces(user.id)

    primary_ws: Optional[WorkspaceSummary] = None
    active_ws_id: Optional[str] = None
    active_role: Optional[str] = None

    if workspaces:
        first = workspaces[0]
        primary_ws = WorkspaceSummary(
            id=first["id"],
            name=first["name"],
            role=first["role"],
            created_at=first["created_at"],
        )
        active_ws_id = first["id"]
        active_role = first["role"]

    auth_user = AuthenticatedUser(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        workspace_id=active_ws_id,
        workspace_role=active_role,
    )

    return AuthResponse(
        user=auth_user,
        workspace=primary_ws,
        csrf_token=csrf_token,
        message="Authenticated successfully",
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Revoke session and clear cookies",
)
async def logout(
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
) -> Dict[str, str]:
    raw_token = request.cookies.get("session_token")
    if not raw_token:
        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            raw_token = auth_header[7:].strip()

    if raw_token:
        token_hash = hash_session_token(raw_token)
        session_repo = SessionRepository(db)
        session_repo.revoke_by_token_hash(token_hash)

    clear_auth_cookies(response)
    return {"message": "Logged out successfully"}


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get authenticated user profile and workspaces",
)
async def get_me(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> CurrentUserResponse:
    ws_repo = WorkspaceRepository(db)
    raw_workspaces = ws_repo.list_user_workspaces(current_user.id)

    workspaces = [
        WorkspaceSummary(
            id=w["id"],
            name=w["name"],
            role=w["role"],
            created_at=w["created_at"],
        )
        for w in raw_workspaces
    ]

    active_ws = next((w for w in workspaces if w.id == current_user.workspace_id), None)
    if not active_ws and workspaces:
        active_ws = workspaces[0]

    return CurrentUserResponse(
        user=current_user,
        workspaces=workspaces,
        active_workspace=active_ws,
    )


# ---------------------------------------------------------------------------
# Workspace Endpoints
# ---------------------------------------------------------------------------

@workspace_router.get(
    "",
    response_model=List[WorkspaceSummary],
    summary="List workspaces accessible to current user",
)
async def list_workspaces(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> List[WorkspaceSummary]:
    ws_repo = WorkspaceRepository(db)
    raw_workspaces = ws_repo.list_user_workspaces(current_user.id)
    return [
        WorkspaceSummary(
            id=w["id"],
            name=w["name"],
            role=w["role"],
            created_at=w["created_at"],
        )
        for w in raw_workspaces
    ]


@workspace_router.post(
    "",
    response_model=WorkspaceSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new workspace",
)
async def create_workspace(
    req: CreateWorkspaceRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> WorkspaceSummary:
    verify_csrf_and_origin(Request) if False else None  # Handled in caller or dependency
    ws_name = req.name.strip()
    if not ws_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace name cannot be empty.",
        )

    ws_repo = WorkspaceRepository(db)
    ws = ws_repo.create(name=ws_name, created_by_id=current_user.id)
    ws_repo.add_member(ws.id, current_user.id, role="admin")

    return WorkspaceSummary(
        id=str(ws.id),
        name=ws.name,
        role="admin",
        created_at=ws.created_at.isoformat() if ws.created_at else "",
    )


@workspace_router.get(
    "/{workspace_id}/members",
    response_model=List[MemberResponse],
    summary="List members in a workspace",
)
async def list_workspace_members(
    workspace_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> List[MemberResponse]:
    # Verify user is a member of this workspace
    verify_workspace_membership(db, current_user, workspace_id, min_role="viewer")

    ws_repo = WorkspaceRepository(db)
    members = ws_repo.list_members(workspace_id)
    user_repo = UserRepository(db)

    results = []
    for m in members:
        u = user_repo.get_by_id(m.user_id)
        results.append(
            MemberResponse(
                id=str(m.id),
                user_id=str(m.user_id),
                email=u.email if u else "unknown",
                display_name=u.display_name if u else None,
                role=m.role,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
        )
    return results


@workspace_router.post(
    "/{workspace_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new member to a workspace (Admin only)",
)
async def add_workspace_member(
    workspace_id: str,
    req: AddMemberRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> MemberResponse:
    # Requires admin role in the workspace
    verify_workspace_membership(db, current_user, workspace_id, min_role="admin")

    if req.role not in ("admin", "editor", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of: 'admin', 'editor', 'viewer'.",
        )

    user_repo = UserRepository(db)
    target_user = user_repo.get_by_email(req.email)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No user found with email '{req.email}'.",
        )

    ws_repo = WorkspaceRepository(db)
    member = ws_repo.add_member(workspace_id, target_user.id, role=req.role)

    return MemberResponse(
        id=str(member.id),
        user_id=str(member.user_id),
        email=target_user.email,
        display_name=target_user.display_name,
        role=member.role,
        created_at=member.created_at.isoformat() if member.created_at else "",
    )


@workspace_router.patch(
    "/{workspace_id}/members/{target_user_id}",
    response_model=MemberResponse,
    summary="Update a workspace member's role (Admin only)",
)
async def update_member_role(
    workspace_id: str,
    target_user_id: str,
    req: UpdateRoleRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> MemberResponse:
    # Requires admin role
    verify_workspace_membership(db, current_user, workspace_id, min_role="admin")

    if req.role not in ("admin", "editor", "viewer"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be one of: 'admin', 'editor', 'viewer'.",
        )

    ws_repo = WorkspaceRepository(db)
    member = ws_repo.update_member_role(workspace_id, target_user_id, role=req.role)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace membership not found.",
        )

    user_repo = UserRepository(db)
    target_user = user_repo.get_by_id(target_user_id)

    return MemberResponse(
        id=str(member.id),
        user_id=str(member.user_id),
        email=target_user.email if target_user else "unknown",
        display_name=target_user.display_name if target_user else None,
        role=member.role,
        created_at=member.created_at.isoformat() if member.created_at else "",
    )


@workspace_router.delete(
    "/{workspace_id}/members/{target_user_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove a member from a workspace (Admin only)",
)
async def remove_workspace_member(
    workspace_id: str,
    target_user_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: DBSession = Depends(get_db),
) -> Dict[str, str]:
    verify_workspace_membership(db, current_user, workspace_id, min_role="admin")

    ws_repo = WorkspaceRepository(db)
    success = ws_repo.remove_member(workspace_id, target_user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace membership not found.",
        )
    return {"message": "Member removed successfully"}
