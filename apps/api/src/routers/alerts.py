"""Alerts router — saved search rules that trigger daily email/Slack digests.

Endpoints:
  GET    /api/alerts            — list tenant's alerts
  POST   /api/alerts            — create alert
  GET    /api/alerts/{id}       — get alert
  PATCH  /api/alerts/{id}       — update alert
  DELETE /api/alerts/{id}       — delete alert
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData, get_current_user
from database import get_db
from db_models import Alert

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    keywords: Optional[str] = Field(
        default=None,
        description="Comma-separated keywords to match (omit = any keyword)",
    )
    min_value: Optional[float] = Field(default=None, ge=0)
    state_filter: Optional[str] = Field(default=None, max_length=100)
    email_to: Optional[str] = Field(
        default=None,
        description="Comma-separated recipient emails",
    )
    slack_webhook_url: Optional[str] = None
    is_active: bool = True


class AlertUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    keywords: Optional[str] = None
    min_value: Optional[float] = Field(default=None, ge=0)
    state_filter: Optional[str] = None
    email_to: Optional[str] = None
    slack_webhook_url: Optional[str] = None
    is_active: Optional[bool] = None


class AlertResponse(BaseModel):
    id: int
    tenant_id: str
    name: str
    keywords: Optional[str]
    min_value: Optional[float]
    state_filter: Optional[str]
    email_to: Optional[str]
    slack_webhook_url: Optional[str]
    is_active: bool
    last_triggered_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_alert(db: AsyncSession, alert_id: int, tenant_id: str) -> Alert:
    result = await db.execute(
        select(Alert).where(Alert.id == alert_id, Alert.tenant_id == tenant_id)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return alert


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[AlertResponse])
async def list_alerts(
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AlertResponse]:
    result = await db.execute(
        select(Alert)
        .where(Alert.tenant_id == current_user.tenant_id)
        .order_by(Alert.created_at.desc())
    )
    return [AlertResponse.model_validate(a) for a in result.scalars().all()]


@router.post("", response_model=AlertResponse, status_code=status.HTTP_201_CREATED)
async def create_alert(
    body: AlertCreate,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertResponse:
    if not body.email_to and not body.slack_webhook_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of email_to or slack_webhook_url is required",
        )
    alert = Alert(
        tenant_id=current_user.tenant_id,
        **body.model_dump(),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertResponse:
    alert = await _get_alert(db, alert_id, current_user.tenant_id)
    return AlertResponse.model_validate(alert)


@router.patch("/{alert_id}", response_model=AlertResponse)
async def update_alert(
    alert_id: int,
    body: AlertUpdate,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AlertResponse:
    alert = await _get_alert(db, alert_id, current_user.tenant_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(alert, field, value)
    alert.updated_at = datetime.now(tz=timezone.utc)
    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: int,
    current_user: Annotated[TokenData, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    alert = await _get_alert(db, alert_id, current_user.tenant_id)
    await db.delete(alert)
    await db.commit()
