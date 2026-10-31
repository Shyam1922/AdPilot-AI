from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class AudienceHypothesis(BaseModel):
    segment: str
    need: str
    evidence: str = Field(description="What on the page or in user input suggests this; 'assumption' if none")
    confidence: Literal["low", "medium", "high"] = "low"


class ApprovedClaim(BaseModel):
    claim: str
    source: str = Field(description="URL, 'page:<snippet id>' or 'user-provided'")


class ProductInfo(BaseModel):
    name: str
    description: str = ""
    price: Optional[str] = None
    image_url: Optional[str] = None
    features: list[str] = []


class BrandProfile(BaseModel):
    brand_name: str
    product_name: str = ""
    product_category: str = ""
    description: str = ""
    products: list[ProductInfo] = []
    value_propositions: list[str] = []
    features: list[str] = []
    audience_hypotheses: list[AudienceHypothesis] = []
    brand_tone: list[str] = []
    differentiators: list[str] = []
    approved_claims: list[ApprovedClaim] = []
    unknowns_to_confirm: list[str] = []
    visual_identity: dict = Field(default_factory=dict, description="primary/secondary/accent hex colors, style words")
    source_urls: list[str] = []


class ManualBrandInput(BaseModel):
    brand_name: Optional[str] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    target_audience: Optional[str] = None
    price_range: Optional[str] = None
    tone: Optional[str] = None
    key_features: list[str] = []
    claims_to_avoid: list[str] = []


class AnalyzeBrandRequest(BaseModel):
    url: Optional[HttpUrl] = None
    manual: ManualBrandInput = ManualBrandInput()


class BrandUpdate(BaseModel):
    """Edits to Brand Memory. Any field left None is unchanged."""
    name: Optional[str] = None
    profile: Optional[BrandProfile] = None
    guardrails: Optional[dict] = None
