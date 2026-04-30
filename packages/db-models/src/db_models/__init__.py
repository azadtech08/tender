"""GeM Tender SaaS — Shared Database Models."""

from .admin_audit_log import (
    ACTION_DEVICE_REVOKE,
    ACTION_KEY_ROTATE,
    ACTION_LICENSE_CREATE,
    ACTION_LICENSE_EXTEND,
    ACTION_LICENSE_REACTIVATE,
    ACTION_LICENSE_REVOKE,
    ACTION_LICENSE_SUSPEND,
    VALID_ADMIN_ACTIONS,
    AdminAuditLog,
)
from .alert import Alert, AlertDelivery
from .api_key import ApiKey
from .base import Base, TimestampMixin
from .job import Job
from .job_event import JobEvent
from .license import (
    STATUS_ACTIVE,
    STATUS_EXPIRED,
    STATUS_REVOKED,
    STATUS_SUSPENDED,
    VALID_LICENSE_STATUSES,
    License,
)
from .license_activation import (
    EVENT_ACTIVATE,
    EVENT_DEACTIVATE,
    EVENT_DENIED,
    EVENT_HEARTBEAT,
    EVENT_REVOKED,
    REASON_DEVICE_LIMIT,
    REASON_FINGERPRINT_MISMATCH,
    REASON_INVALID_KEY,
    REASON_KEY_EXPIRED,
    REASON_KEY_REVOKED,
    REASON_KEY_SUSPENDED,
    REASON_RATE_LIMITED,
    REASON_UNKNOWN_FINGERPRINT,
    VALID_ACTIVATION_EVENTS,
    LicenseActivation,
)
from .license_device import LicenseDevice
from .license_usage_counter import (
    COUNTER_AI_SUMMARIES,
    COUNTER_API_CALLS,
    COUNTER_RUNS,
    COUNTER_TENDERS_EXPORTED,
    LicenseUsageCounter,
)
from .outbound_webhook import OutboundWebhook, WebhookDelivery
from .phonepe_transaction import (
    PHONEPE_PLAN_AMOUNTS,
    PHONEPE_STATUS_CANCELLED,
    PHONEPE_STATUS_FAILED,
    PHONEPE_STATUS_PENDING,
    PHONEPE_STATUS_SUCCESS,
    VALID_PHONEPE_STATUSES,
    PhonePeTransaction,
)
from .schedule import Schedule
from .subscription import (
    PLAN_BUSINESS,
    PLAN_ENTERPRISE,
    PLAN_FREE,
    PLAN_PRO,
    PLAN_RUN_LIMITS,
    PLAN_STARTER,
    Subscription,
)
from .tender import Tender
from .usage_event import EVENT_AI_SUMMARY, EVENT_RUN, EVENT_TENDER, UsageEvent
from .user import User

__all__ = [
    # Core
    "Base",
    "TimestampMixin",
    "User",
    "Job",
    "JobEvent",
    "Tender",
    "Schedule",
    # Billing
    "Subscription",
    "PLAN_FREE",
    "PLAN_STARTER",
    "PLAN_PRO",
    "PLAN_BUSINESS",
    "PLAN_ENTERPRISE",
    "PLAN_RUN_LIMITS",
    "UsageEvent",
    "EVENT_RUN",
    "EVENT_TENDER",
    "EVENT_AI_SUMMARY",
    # PhonePe payments
    "PhonePeTransaction",
    "PHONEPE_STATUS_PENDING",
    "PHONEPE_STATUS_SUCCESS",
    "PHONEPE_STATUS_FAILED",
    "PHONEPE_STATUS_CANCELLED",
    "VALID_PHONEPE_STATUSES",
    "PHONEPE_PLAN_AMOUNTS",
    # Phase 3
    "Alert",
    "AlertDelivery",
    "ApiKey",
    "OutboundWebhook",
    "WebhookDelivery",
    # Licensing (Phase 2)
    "License",
    "STATUS_ACTIVE",
    "STATUS_SUSPENDED",
    "STATUS_REVOKED",
    "STATUS_EXPIRED",
    "VALID_LICENSE_STATUSES",
    "LicenseDevice",
    "LicenseActivation",
    "EVENT_ACTIVATE",
    "EVENT_HEARTBEAT",
    "EVENT_DEACTIVATE",
    "EVENT_DENIED",
    "EVENT_REVOKED",
    "VALID_ACTIVATION_EVENTS",
    "REASON_INVALID_KEY",
    "REASON_KEY_EXPIRED",
    "REASON_KEY_REVOKED",
    "REASON_KEY_SUSPENDED",
    "REASON_DEVICE_LIMIT",
    "REASON_RATE_LIMITED",
    "REASON_UNKNOWN_FINGERPRINT",
    "REASON_FINGERPRINT_MISMATCH",
    "LicenseUsageCounter",
    "COUNTER_RUNS",
    "COUNTER_TENDERS_EXPORTED",
    "COUNTER_AI_SUMMARIES",
    "COUNTER_API_CALLS",
    "AdminAuditLog",
    "ACTION_LICENSE_CREATE",
    "ACTION_LICENSE_REVOKE",
    "ACTION_LICENSE_SUSPEND",
    "ACTION_LICENSE_REACTIVATE",
    "ACTION_LICENSE_EXTEND",
    "ACTION_DEVICE_REVOKE",
    "ACTION_KEY_ROTATE",
    "VALID_ADMIN_ACTIONS",
]
