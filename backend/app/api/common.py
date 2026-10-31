"""Shared helpers for routers: loading rows or 404, audit logging, brand context."""
from __future__ import annotations

from typing import TypeVar

from fastapi import HTTPException
from sqlmodel import Session, SQLModel

from ..models import AuditLog, Brand, Campaign, now
from ..schemas.brand import BrandProfile
from ..schemas.concept import CampaignStrategy

T = TypeVar("T", bound=SQLModel)


def get_or_404(session: Session, model: type[T], id_: int) -> T:
    obj = session.get(model, id_)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} {id_} not found.")
    return obj


def audit(session: Session, entity: str, entity_id: int, action: str, **detail) -> None:
    session.add(AuditLog(entity=entity, entity_id=entity_id, action=action, detail=detail))


def touch(obj) -> None:
    obj.updated_at = now()


def brand_context(session: Session, campaign: Campaign) -> tuple[Brand, BrandProfile, CampaignStrategy]:
    brand = get_or_404(session, Brand, campaign.brand_id)
    return brand, BrandProfile.model_validate(brand.profile), CampaignStrategy.model_validate(campaign.strategy)


def guardrail_list(brand: Brand) -> list[str]:
    g = brand.guardrails or {}
    return [*g.get("claims_to_avoid", []), *g.get("words_to_avoid", [])]
