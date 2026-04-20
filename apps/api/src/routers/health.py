"""Health check router."""

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db

router = APIRouter()


@router.get("/")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check with real DB and Redis connectivity tests."""
    db_ok = False
    redis_ok = False

    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    try:
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        redis_ok = True
    except Exception:
        pass

    status = "ok" if (db_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "service": "gem-api",
        "checks": {
            "database": db_ok,
            "redis": redis_ok,
        },
    }


@router.get("/debug-token")
async def debug_token(request: Request):
    """Temporary: decode incoming Bearer token and show the error."""
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer ", "").strip()
    if not token:
        return {"error": "no token provided"}
    try:
        import httpx
        from jose import jwt as jose_jwt
        r = httpx.get(settings.clerk_jwks_url, timeout=10)
        keys = r.json()
        payload = jose_jwt.decode(
            token, keys, algorithms=["RS256"],
            options={"verify_aud": False},
            issuer=settings.clerk_issuer or None,
        )
        return {"ok": True, "claims": payload}
    except Exception as e:
        # Try without issuer check
        try:
            payload = jose_jwt.decode(
                token, keys, algorithms=["RS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
            return {"ok": False, "issuer_error": str(e), "token_iss": payload.get("iss"), "config_issuer": settings.clerk_issuer, "claims_without_issuer_check": payload}
        except Exception as e2:
            return {"ok": False, "error": str(e), "second_error": str(e2)}
