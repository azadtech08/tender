"""Tender Pydantic schemas."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class TenderResponse(BaseModel):
    id: int
    job_id: int
    tenant_id: str
    keyword: str
    tender_ref_no: str
    tender_type: Optional[str]
    published_date: Optional[date]
    bid_end_date: Optional[datetime]
    title: Optional[str]
    description: Optional[str]
    cleaned_boq: Optional[str]
    organisation: Optional[str]
    ministry: Optional[str]
    tender_value: Optional[float]
    emd: Optional[float]
    state: Optional[str]
    pincode: Optional[str]
    delivery_period: Optional[str]
    product_type: Optional[str]
    exemption: Optional[str]
    email: Optional[str]
    it_relevant: Optional[str]
    quantity: Optional[str]
    link: Optional[str]
    scraped_date: Optional[date]
    pdf_s3_key: Optional[str]
    gem_position: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class TenderListResponse(BaseModel):
    items: list[TenderResponse]
    total: int
    page: int
    per_page: int
