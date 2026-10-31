"""Persistent entities. JSON columns keep the MVP schema flexible while the product evolves.

Brand          -> the Brand Memory (profile, guardrails, learnings)
Campaign       -> objective, channels, strategy, status
Concept        -> one ad idea (copy + visual brief + lineage)
Asset          -> rendered image / video files (async job status)
MetricSnapshot -> performance rows, always tagged with source_type
Iteration      -> each optimisation round (signals used, limitations)
AuditLog       -> important actions (approve, export, generate)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def now() -> datetime:
    return datetime.now(timezone.utc)


def _json(default_factory=dict):
    return Field(default_factory=default_factory, sa_column=Column(JSON))


class Brand(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    website: str = ""
    profile: dict[str, Any] = _json()          # BrandProfile JSON
    manual_inputs: dict[str, Any] = _json()    # what the user typed
    guardrails: dict[str, Any] = _json()       # claims_to_avoid, words_to_avoid, notes
    learnings: list[Any] = _json(list)         # memory of what worked (from iterations)
    sources: list[Any] = _json(list)           # source urls + snippets
    warnings: list[Any] = _json(list)
    logo_path: str = ""
    product_images: list[Any] = _json(list)  # local paths of downloaded / uploaded product images
    integrations: dict[str, Any] = _json()     # e.g. {"meko": {"datapack_id", "status", "synced_at", ...}}
    generation_mode: str = "offline"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Campaign(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="brand.id", index=True)
    name: str
    objective: str = "sales"
    channels: list[Any] = _json(list)
    product_focus: str = ""
    audience_note: str = ""
    budget_note: str = ""
    status: str = "draft"   # draft | generated | approved | scheduled | published | failed
    strategy: dict[str, Any] = _json()
    generation_mode: str = "offline"
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Concept(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    iteration_id: Optional[int] = Field(default=None, index=True)
    parent_concept_id: Optional[int] = None
    concept_type: str
    target_segment: str = ""
    angle: str = ""
    hook: str = ""
    primary_text: str = ""
    headline: str = ""
    cta: str = ""
    visual_brief: dict[str, Any] = _json()
    platform_copy: dict[str, Any] = _json()
    video_script: list[Any] = _json(list)
    claim_sources: list[Any] = _json(list)
    risk_flags: list[Any] = _json(list)
    changed_variables: list[Any] = _json(list)
    rationale: str = ""
    is_exploration: bool = False
    status: str = "generated"   # generated | approved | rejected
    edited: bool = False
    generation_mode: str = "offline"
    prompt_version: str = ""
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class SocialPost(SQLModel, table=True):
    """A draft post for LinkedIn / Instagram / X. Never published automatically."""
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    concept_id: int = Field(index=True)
    platform: str            # linkedin | instagram | x
    hook: str = ""
    text: str = ""
    hashtags: list[Any] = _json(list)
    thread: list[Any] = _json(list)
    visual_idea: str = ""
    cta: str = ""
    risk_flags: list[Any] = _json(list)
    status: str = "generated"   # generated | approved | rejected | scheduled | published
    edited: bool = False
    generation_mode: str = "offline"
    prompt_version: str = ""
    scheduled_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    publish_mode: str = ""      # manual_share (user pressed Post on the platform) | simulated | synthetic_history
    external_url: str = ""
    metrics: dict[str, Any] = _json()      # impressions, likes, comments, shares, clicks
    metrics_source: str = ""    # manual | simulated | synthetic_history
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class Asset(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaign.id", index=True)
    concept_id: Optional[int] = Field(default=None, index=True)
    brand_id: Optional[int] = Field(default=None, index=True)
    kind: str            # image | video | upload
    fmt: str = ""        # e.g. 1080x1350 feed, 1080x1920 reel
    path: str = ""       # relative to storage dir
    status: str = "queued"  # queued | rendering | ready | failed
    generation_mode: str = "template"   # template (Pillow/FFmpeg) | external provider name
    error: str = ""
    meta: dict[str, Any] = _json()
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class MetricSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    concept_id: int = Field(index=True)
    platform: str = "meta"
    day: str = ""  # ISO date
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend: float = 0.0
    revenue: Optional[float] = None
    source_type: str = "simulated"   # simulated | imported_csv | api:<provider>
    captured_at: datetime = Field(default_factory=now)


class Iteration(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaign.id", index=True)
    objective_metric: str = ""
    insight_summary: str = ""
    ranking: list[Any] = _json(list)
    selected_signals: list[Any] = _json(list)
    limitations: list[Any] = _json(list)
    data_sources: list[Any] = _json(list)
    generation_mode: str = "offline"
    created_at: datetime = Field(default_factory=now)


class AuditLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    entity: str
    entity_id: int
    action: str
    detail: dict[str, Any] = _json()
    created_at: datetime = Field(default_factory=now)
