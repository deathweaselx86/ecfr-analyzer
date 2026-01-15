"""Pydantic schemas for API request/response models."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class CFRReferenceSchema(BaseModel):
    """CFR Reference response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: int
    chapter: str | None
    part: int | None
    subchapter: str | None


class TitleMetadataSchema(BaseModel):
    """Title metadata response schema."""

    model_config = ConfigDict(from_attributes=True)

    number: int
    name: str
    latest_amended_on: date | None
    latest_issue_date: date | None
    up_to_date_as_of: date | None
    reserved: bool
    created_at: datetime
    updated_at: datetime


class AgencySchema(BaseModel):
    """Agency response schema (without children to avoid circular refs)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    short_name: str | None
    display_name: str
    sortable_name: str
    slug: str
    parent_id: int | None
    created_at: datetime


class AgencyDetailSchema(AgencySchema):
    """Agency detail response schema with relationships."""

    cfr_references: list[CFRReferenceSchema] = []
    children: list[AgencySchema] = []
