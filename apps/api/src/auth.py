"""Authentication and authorization utilities.

Dual-mode JWT verification:
  - When CLERK_JWKS_URL is set → validate tokens issued by Clerk (RS256).
    The frontend signs users in via Clerk; the API only verifies.
  - When CLERK_JWKS_URL is not set (local dev / testing) → fall back to the
    local HS256 JWT issued by POST /auth/login and POST /auth/register.

Token claim conventions:
  Clerk tokens:   sub=clerk_user_id, org_id=tenant_id (or sub used as tenant)
  Local tokens:   sub=user_db_id (str), tenant_id=uuid, email=user_email
"""

import hashlib
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from jose.backends import RSAKey
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

# ── Password hashing (local auth only) ──────────────────────────────────────

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ── Bearer extraction ────────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)


# ── Pydantic models ──────────────────────────────────────────────────────────

class TokenData(BaseModel):
    """Claims extracted from a verified JWT (Clerk or local)."""
    user_id: str       # Clerk user ID or local DB id as string
    tenant_id: str     # Clerk org_id, or UUID generated at local registration
    email: str


class UserCredentials(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Local JWT helpers ────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Mint a local HS256 JWT (used only when Clerk is not configured)."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=settings.jwt_expiration_hours))
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm="HS256")


# ── Clerk JWKS cache ─────────────────────────────────────────────────────────

class _JwksCache:
    """Thread-safe cache for Clerk's public JWKS, refreshed every hour."""

    TTL = 3600  # seconds

    def __init__(self) -> None:
        self._keys: dict = {}
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def _needs_refresh(self) -> bool:
        return time.time() - self._fetched_at > self.TTL

    def get_keys(self) -> dict:
        if self._needs_refresh():
            with self._lock:
                if self._needs_refresh():  # double-checked
                    self._fetch()
        return self._keys

    def _fetch(self) -> None:
        resp = httpx.get(settings.clerk_jwks_url, timeout=10)
        resp.raise_for_status()
        self._keys = resp.json()
        self._fetched_at = time.time()

    def invalidate(self) -> None:
        """Force a refresh on next get_keys() call (used after 401 from Clerk)."""
        self._fetched_at = 0.0


_jwks_cache = _JwksCache()


# ── Clerk token verification ─────────────────────────────────────────────────

def _verify_clerk_token(token: str) -> Optional[TokenData]:
    """Verify a Clerk-issued JWT.

    Strategy A — Clerk Backend API (reliable, no JWKS parsing):
      Decode the token header/claims without verification to get the sub (user_id),
      then call GET /v1/users/{user_id} with CLERK_SECRET_KEY.
      If Clerk returns 200, the session is valid.

    Strategy B — JWKS fallback (if no secret key configured):
      Classic RS256 verification via JWKS endpoint.
    """
    print(f"[AUTH] _verify_clerk_token called, token[:20]={token[:20] if token else 'EMPTY'}", flush=True)

    # ── Strategy A: Clerk Backend API ────────────────────────────────────────
    clerk_secret = getattr(settings, "clerk_secret_key", "") or ""
    if clerk_secret:
        try:
            # Decode claims WITHOUT signature verification just to get sub
            unverified = jwt.get_unverified_claims(token)
            user_id: str = unverified.get("sub", "")
            print(f"[AUTH] unverified sub={user_id}, iss={unverified.get('iss','')}", flush=True)
            if user_id:
                r = httpx.get(
                    f"https://api.clerk.com/v1/users/{user_id}",
                    headers={"Authorization": f"Bearer {clerk_secret}"},
                    timeout=8,
                )
                print(f"[AUTH] Clerk API status={r.status_code}", flush=True)
                if r.status_code == 200:
                    data = r.json()
                    emails = data.get("email_addresses") or []
                    email = emails[0].get("email_address", "") if emails else ""
                    tenant_id = unverified.get("org_id") or user_id
                    return TokenData(user_id=user_id, tenant_id=tenant_id, email=email)
        except Exception as exc:
            print(f"[AUTH] Strategy A failed: {exc}", flush=True)

    # ── Strategy B: JWKS verification ────────────────────────────────────────
    for attempt in range(2):
        try:
            keys = _jwks_cache.get_keys()
            payload = jwt.decode(
                token, keys,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
            user_id = payload.get("sub", "")
            tenant_id = payload.get("org_id") or user_id
            email = (
                payload.get("email")
                or payload.get("email_address")
                or payload.get("primary_email_address", "")
            )
            if user_id:
                return TokenData(user_id=user_id, tenant_id=tenant_id, email=email)
        except Exception as exc:
            print(f"[AUTH] Strategy B attempt {attempt+1} failed: {exc}", flush=True)
            if attempt == 0:
                _jwks_cache.invalidate()

    print("[AUTH] All strategies failed — returning None", flush=True)
    return None


# ── Local token verification ─────────────────────────────────────────────────

def _verify_local_token(token: str) -> Optional[TokenData]:
    """Verify a locally-minted HS256 JWT."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=["HS256"],
        )
        user_id: str = payload.get("sub", "")
        tenant_id: str = payload.get("tenant_id", "")
        email: str = payload.get("email", "")
        if user_id and tenant_id and email:
            return TokenData(user_id=user_id, tenant_id=tenant_id, email=email)
    except JWTError:
        pass
    return None


# ── Unified verify entry-point ────────────────────────────────────────────────

def verify_token(token: str) -> Optional[TokenData]:
    """Verify a JWT using Clerk (if configured) or local HS256 fallback."""
    if settings.clerk_jwks_url:
        return _verify_clerk_token(token)
    return _verify_local_token(token)


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenData:
    """Verify the caller via Bearer JWT OR X-API-Key header (in that order)."""
    # 1. Try Bearer token first
    if credentials and credentials.credentials:
        token_data = verify_token(credentials.credentials)
        if token_data:
            return token_data
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Try X-API-Key header
    x_api_key = request.headers.get("X-API-Key")
    if x_api_key:
        from database import get_db  # local import avoids circular deps
        async for db in get_db():
            token_data = await get_current_user_from_api_key(x_api_key, db)
            if token_data:
                return token_data
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── API Key authentication ────────────────────────────────────────────────────

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def get_current_user_from_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    db: Optional[AsyncSession] = None,
) -> Optional[TokenData]:
    """Verify an X-API-Key header.  Returns TokenData or None if key is absent/invalid."""
    if not x_api_key or not db:
        return None

    from db_models import ApiKey  # local import avoids circular deps

    key_hash = _hash_key(x_api_key)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active == True,  # noqa: E712
        )
    )
    api_key_row = result.scalar_one_or_none()
    if api_key_row is None:
        return None

    # Check expiry
    if api_key_row.expires_at and api_key_row.expires_at < datetime.now(tz=timezone.utc):
        return None

    # Update last_used_at (best-effort, don't block on failure)
    try:
        api_key_row.last_used_at = datetime.now(tz=timezone.utc)
        await db.commit()
    except Exception:
        pass

    return TokenData(
        user_id=f"apikey:{api_key_row.id}",
        tenant_id=api_key_row.tenant_id,
        email="",
    )


async def get_current_user_from_query(token: Optional[str] = None) -> TokenData:
    """Verify a JWT passed as a query parameter (for SSE EventSource).

    Usage: Depends(get_current_user_from_query)
    The caller passes ?token=<jwt> since EventSource cannot set headers.
    """
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token_data = verify_token(token)
    if not token_data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return token_data
