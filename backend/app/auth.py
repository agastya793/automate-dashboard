"""
Business Reporting Dashboard — Authentication Dependency
Phase 5: Supabase Auth Verification

Verifies Bearer access tokens against the Supabase Auth service.
Does not trust client-supplied user IDs or unverified JWT claims.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
import httpx

load_dotenv()

security = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    id: str
    email: str
    role: str = "authenticated"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AuthenticatedUser:
    """
    FastAPI dependency that validates the Bearer access token with Supabase Auth.
    Returns the verified AuthenticatedUser or raises an HTTP 401 / 503 exception.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Missing Bearer access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Bearer access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider is not configured on the server. SUPABASE_URL is missing.",
        )

    auth_endpoint = f"{supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": supabase_key or "",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(auth_endpoint, headers=headers)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication provider service is currently unavailable.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error communicating with authentication service.",
        ) from exc

    if response.status_code == 200:
        data = response.json()
        user_id = data.get("id")
        email = data.get("email", "")
        role = data.get("role", "authenticated")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed: user identifier not found in auth provider response.",
            )

        return AuthenticatedUser(id=str(user_id), email=str(email), role=str(role))

    if response.status_code in (400, 401, 403):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or revoked access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Authentication provider returned unexpected status code: {response.status_code}",
    )
