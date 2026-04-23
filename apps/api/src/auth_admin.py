"""Admin authentication and authorization.

Wraps the standard `get_current_user` dependency with three additional checks
(Phase 0 §3.7 LOCKED):

1. Source IP must be in `ADMIN_IP_ALLOWLIST` (CIDR list) — when configured
2. Caller must have admin role:
     - Clerk mode: `public_metadata.role == 'tenzo_admin'` (verified via
       Clerk Backend API)
     - Local mode: caller's `user_id` must appear in `LOCAL_ADMIN_USER_IDS`
3. (Optional, Clerk only) 2FA enforced — `two_factor_enabled` must be true.
   Disabled by default; flip `ADMIN_REQUIRE_2FA=true` to enforce.

If `ADMIN_IP_ALLOWLIST` is empty, the IP check is skipped (dev convenience).
"""

from __future__ import annotations

import ipaddress
from typing import Annotated, Optional

import httpx
from fastapi import Depends, HTTPException, Request, status

from auth import TokenData, get_current_user
from config import settings


def get_client_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _ip_in_allowlist(ip: str, cidrs: list[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in cidrs:
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


def _fetch_clerk_user(user_id: str) -> Optional[dict]:
    if not settings.clerk_secret_key:
        return None
    try:
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=8,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def _user_has_admin_role(user: TokenData) -> bool:
    # Local-dev / test bypass — env var allowlist of user IDs (str compare).
    if settings.local_admin_user_ids:
        if user.user_id in settings.local_admin_user_ids:
            return True

    # Clerk mode — read public_metadata.role from Backend API.
    if user.user_id.startswith("user_"):
        data = _fetch_clerk_user(user.user_id)
        if data is not None:
            role = (data.get("public_metadata") or {}).get("role")
            return role == "tenzo_admin"

    return False


def _user_has_2fa(user: TokenData) -> bool:
    if user.user_id.startswith("user_"):
        data = _fetch_clerk_user(user.user_id)
        if data is not None:
            return bool(data.get("two_factor_enabled"))
    return False


async def get_admin_user(
    request: Request,
    user: Annotated[TokenData, Depends(get_current_user)],
) -> TokenData:
    """FastAPI dependency for admin-only endpoints. Raises 403 on failure."""
    if settings.admin_ip_allowlist:
        client_ip = get_client_ip(request)
        if not _ip_in_allowlist(client_ip, settings.admin_ip_allowlist):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access blocked from this IP",
            )

    if not _user_has_admin_role(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    if settings.admin_require_2fa and not _user_has_2fa(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="2FA must be enabled on your account to access admin endpoints",
        )

    return user
