"""Plan -> feature flag mapping.

Per Phase 0 §2 Q4 working assumption (reuse existing plans), each Stripe plan
maps to a default feature set. License rows can override specific keys via
``licenses.features`` jsonb — overrides win over plan defaults.

Counter ceilings live alongside boolean features: a key like
``max_runs_per_month`` carries an int, ``None`` means unlimited.
"""

from __future__ import annotations

from typing import Any, Optional

from db_models import (
    PLAN_BUSINESS,
    PLAN_ENTERPRISE,
    PLAN_FREE,
    PLAN_PRO,
    PLAN_STARTER,
)

# Standard feature keys — use these constants so route code and PLAN_FEATURES
# agree. License-row overrides may use any key.
FEATURE_CREATE_JOBS = "create_jobs"
FEATURE_EXPORT_XLSX = "export_xlsx"
FEATURE_SCHEDULE_JOBS = "schedule_jobs"
FEATURE_AI_SUMMARIES = "ai_summaries"
FEATURE_API_ACCESS = "api_access"
FEATURE_WEBHOOKS = "webhooks"

# Counter ceiling keys (read by check_and_increment).
LIMIT_RUNS_PER_MONTH = "max_runs_per_month"
LIMIT_TENDERS_EXPORTED_PER_MONTH = "max_tenders_exported_per_month"
LIMIT_AI_SUMMARIES_PER_MONTH = "max_ai_summaries_per_month"
LIMIT_API_CALLS_PER_DAY = "max_api_calls_per_day"

PLAN_FEATURES: dict[str, dict[str, Any]] = {
    PLAN_FREE: {
        FEATURE_CREATE_JOBS: True,
        FEATURE_EXPORT_XLSX: False,
        FEATURE_SCHEDULE_JOBS: False,
        FEATURE_AI_SUMMARIES: False,
        FEATURE_API_ACCESS: False,
        FEATURE_WEBHOOKS: False,
        LIMIT_RUNS_PER_MONTH: 3,
        LIMIT_TENDERS_EXPORTED_PER_MONTH: 0,
        LIMIT_AI_SUMMARIES_PER_MONTH: 0,
        LIMIT_API_CALLS_PER_DAY: 0,
    },
    PLAN_STARTER: {
        FEATURE_CREATE_JOBS: True,
        FEATURE_EXPORT_XLSX: True,
        FEATURE_SCHEDULE_JOBS: False,
        FEATURE_AI_SUMMARIES: False,
        FEATURE_API_ACCESS: False,
        FEATURE_WEBHOOKS: False,
        LIMIT_RUNS_PER_MONTH: 30,
        LIMIT_TENDERS_EXPORTED_PER_MONTH: 500,
        LIMIT_AI_SUMMARIES_PER_MONTH: 0,
        LIMIT_API_CALLS_PER_DAY: 0,
    },
    PLAN_PRO: {
        FEATURE_CREATE_JOBS: True,
        FEATURE_EXPORT_XLSX: True,
        FEATURE_SCHEDULE_JOBS: True,
        FEATURE_AI_SUMMARIES: True,
        FEATURE_API_ACCESS: True,
        FEATURE_WEBHOOKS: False,
        LIMIT_RUNS_PER_MONTH: 150,
        LIMIT_TENDERS_EXPORTED_PER_MONTH: 5_000,
        LIMIT_AI_SUMMARIES_PER_MONTH: 500,
        LIMIT_API_CALLS_PER_DAY: 1_000,
    },
    PLAN_BUSINESS: {
        FEATURE_CREATE_JOBS: True,
        FEATURE_EXPORT_XLSX: True,
        FEATURE_SCHEDULE_JOBS: True,
        FEATURE_AI_SUMMARIES: True,
        FEATURE_API_ACCESS: True,
        FEATURE_WEBHOOKS: True,
        LIMIT_RUNS_PER_MONTH: 600,
        LIMIT_TENDERS_EXPORTED_PER_MONTH: 50_000,
        LIMIT_AI_SUMMARIES_PER_MONTH: 5_000,
        LIMIT_API_CALLS_PER_DAY: 10_000,
    },
    PLAN_ENTERPRISE: {
        FEATURE_CREATE_JOBS: True,
        FEATURE_EXPORT_XLSX: True,
        FEATURE_SCHEDULE_JOBS: True,
        FEATURE_AI_SUMMARIES: True,
        FEATURE_API_ACCESS: True,
        FEATURE_WEBHOOKS: True,
        LIMIT_RUNS_PER_MONTH: None,
        LIMIT_TENDERS_EXPORTED_PER_MONTH: None,
        LIMIT_AI_SUMMARIES_PER_MONTH: None,
        LIMIT_API_CALLS_PER_DAY: None,
    },
}


def features_for_plan(plan: str) -> dict[str, Any]:
    """Return a (defensive) copy of the feature dict for the given plan.

    Unknown plans get the FREE feature set — fail-closed for unrecognised plans.
    """
    return dict(PLAN_FEATURES.get(plan, PLAN_FEATURES[PLAN_FREE]))


def merge_features(plan: str, overrides: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Plan defaults + per-license overrides. Overrides win."""
    base = features_for_plan(plan)
    if overrides:
        base.update(overrides)
    return base
