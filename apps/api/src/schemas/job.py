"""Job Pydantic schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


_VALID_SORT_PREFS = {"bid_end_latest", "bid_end_oldest", "bid_start_latest", "bid_start_oldest"}


class JobCreate(BaseModel):
    keywords: list[str]
    cards_per_kw: int = 3
    min_value: Optional[float] = None
    sort_preference: str = "bid_end_latest"

    @field_validator("sort_preference")
    @classmethod
    def sort_pref_valid(cls, v: str) -> str:
        if v not in _VALID_SORT_PREFS:
            raise ValueError(f"sort_preference must be one of {_VALID_SORT_PREFS}")
        return v

    @field_validator("keywords")
    @classmethod
    def keywords_not_empty(cls, v: list[str]) -> list[str]:
        v = [kw.strip() for kw in v if kw.strip()]
        if not v:
            raise ValueError("At least one keyword is required")
        return v

    @field_validator("cards_per_kw")
    @classmethod
    def cards_range(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError("cards_per_kw must be between 1 and 100")
        return v


class JobResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    tenant_id: str
    keywords: list[str]
    cards_per_kw: int
    min_value: Optional[float]
    status: str
    sort_preference: Optional[str]
    celery_task_id: Optional[str]
    total_keywords: Optional[int]
    done_keywords: Optional[int]
    total_tenders: Optional[int]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int
    page: int
    per_page: int
