"""Admin audit logging — write a row to admin_audit_log per mutation.

Resolves the local users.id when an authenticated admin's email matches a
local User row; otherwise admin_id stays NULL and admin_subject (always set)
carries the auth-provider identifier.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import TokenData
from db_models import AdminAuditLog, User


async def write_admin_audit(
    db: AsyncSession,
    admin: TokenData,
    action: str,
    *,
    target_tenant_id: Optional[str] = None,
    target_license_id: Optional[int] = None,
    payload: Optional[dict] = None,
    ip: Optional[str] = None,
) -> AdminAuditLog:
    """Append an admin_audit_log row. Caller is responsible for the commit."""
    admin_db_id: Optional[int] = None
    if admin.email:
        result = await db.execute(
            select(User.id).where(User.email == admin.email)
        )
        admin_db_id = result.scalar_one_or_none()

    log = AdminAuditLog(
        admin_id=admin_db_id,
        admin_subject=admin.user_id,
        admin_email=admin.email or None,
        action=action,
        target_tenant_id=target_tenant_id,
        target_license_id=target_license_id,
        payload=payload or {},
        ip=ip,
    )
    db.add(log)
    return log
