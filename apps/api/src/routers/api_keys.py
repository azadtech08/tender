"""API keys router — generate and revoke long-lived access tokens.

Endpoints:
  GET    /api/api-keys          — list keys (shows prefix only, never raw key)
  POST   /api/api-keys          — generate new key (raw key shown once)
  DELETE /api/api-keys/{id}     — revoke key

Authentication: keys are sent as  X-API-Key: gem_live_<random>
The verify logic lives in auth.py (verify_api_key).
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db
from db_models import ApiKey

router = APIRouter()

_PREFIX = "gem_live_"


# ── Schemas ───────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    expires_at: Optional[datetime] = None


class ApiKeyCreatedResponse(BaseModel):
    """Returned once on creation — includes the raw key."""
    id: int
    name: str
    key_prefix: str
    raw_key: str                    # shown once, never stored
    created_at: datetime


class ApiKeyResponse(BaseModel):
    """Safe representation — never includes raw key."""
    id: int
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeyResponse]:
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.tenant_id == current_user.tenant_id)
        .order_by(ApiKey.created_at.desc())
    )
    return [ApiKeyResponse.model_validate(k) for k in result.scalars().all()]


@router.post("", response_model=ApiKeyCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiKeyCreatedResponse:
    # Generate: gem_live_<32 random hex chars>
    random_part = secrets.token_hex(32)
    raw_key     = f"{_PREFIX}{random_part}"
    key_prefix  = raw_key[:12]      # "gem_live_xxx" — 12 chars shown in UI
    key_hash    = _hash_key(raw_key)

    api_key = ApiKey(
        tenant_id  = current_user.tenant_id,
        name       = body.name,
        key_prefix = key_prefix,
        key_hash   = key_hash,
        is_active  = True,
        expires_at = body.expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreatedResponse(
        id         = api_key.id,
        name       = api_key.name,
        key_prefix = api_key.key_prefix,
        raw_key    = raw_key,
        created_at = api_key.created_at,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.tenant_id == current_user.tenant_id,
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await db.delete(key)
    await db.commit()
