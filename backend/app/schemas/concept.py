from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ConceptType = Literal["problem", "demo", "storytelling", "offer", "testimonial-style"]
CONCEPT_TYPES: list[str] = ["problem", "demo", "storytelling", "offer", "testimonial-style"]
Objective = Literal["awareness", "traffic", "leads", "sales", "engagement", "launch"]


class VisualBrief(BaseModel):
    scene: str
    composition: str
    product_placement: str
    text_safe_area: str = "top 30% for hook, bottom 20% for CTA"
    style: str = ""
    layout: Literal["hero", "split", "minimal", "bold"] = "hero"


class VideoBeat(BaseModel):
    beat: Literal["hook", "product", "benefit", "cta"]
    seconds: float
    on_screen_text: str
    voiceover: str = ""


class AdConcept(BaseModel):
    concept_type: ConceptType
    target_segment: str
    angle: str
    hook: str = Field(max_length=120)
    primary_text: str
    headline: str = Field(max_length=60)
    cta: str = Field(max_length=30)
    visual_brief: VisualBrief
    video_script: list[VideoBeat] = []
    claim_sources: list[str] = Field(default_factory=list, description="approved claim indices or 'user-provided'")
    rationale: str = ""


class ConceptBatch(BaseModel):
    concepts: list[AdConcept]


class StrategySegment(BaseModel):
    name: str
    pain_points: list[str]
    message: str


class CalendarItem(BaseModel):
    day: int
    channel: str
    content: str
    concept_type: str = ""


class CampaignStrategy(BaseModel):
    objective: str
    positioning_statement: str
    primary_kpi: str
    segments: list[StrategySegment]
    campaign_themes: list[str]
    creative_angles: list[str]
    channel_plan: list[dict] = Field(default_factory=list, description="[{channel, role, formats}]")
    ctas: list[str]
    content_calendar: list[CalendarItem] = []
    assumptions: list[str] = []
    not_claimed: list[str] = Field(default_factory=list, description="What we deliberately do not claim")


class CreateCampaignRequest(BaseModel):
    brand_id: int
    name: Optional[str] = None
    objective: Objective = "sales"
    channels: list[str] = ["instagram", "meta_ads", "google_ads"]
    product_focus: Optional[str] = None
    audience_note: Optional[str] = None
    budget_note: Optional[str] = None


class ConceptUpdate(BaseModel):
    status: Optional[Literal["generated", "approved", "rejected"]] = None
    hook: Optional[str] = None
    primary_text: Optional[str] = None
    headline: Optional[str] = None
    cta: Optional[str] = None
    target_segment: Optional[str] = None
