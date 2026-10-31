"""Campaign Strategist + Campaign Manager endpoints."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Asset, Brand, Campaign, Concept, Iteration, MetricSnapshot
from ..schemas.brand import BrandProfile
from ..schemas.concept import CampaignStrategy, CreateCampaignRequest
from ..serializers import asset_out, campaign_out, concept_out, iteration_out, latest_videos
from ..services import strategist
from .common import audit, get_or_404, touch

router = APIRouter(tags=["campaigns"])

OBJECTIVE_NAMES = {"awareness": "Awareness", "traffic": "Traffic", "leads": "Leads", "sales": "Sales",
                   "engagement": "Engagement", "launch": "Launch"}


@router.post("/campaigns")
def create_campaign(req: CreateCampaignRequest, session: Session = Depends(get_session)) -> dict:
    brand = get_or_404(session, Brand, req.brand_id)
    profile = BrandProfile.model_validate(brand.profile)
    focus = req.product_focus or profile.product_name
    res = strategist.generate(profile, req.objective, req.channels, focus, req.audience_note or "", req.budget_note or "")
    camp = Campaign(
        brand_id=brand.id,
        name=req.name or f"{OBJECTIVE_NAMES[req.objective]} · {focus or brand.name}",
        objective=req.objective, channels=req.channels, product_focus=focus or "",
        audience_note=req.audience_note or "", budget_note=req.budget_note or "",
        status="generated", strategy=res.data.model_dump(), generation_mode=res.mode,
    )
    session.add(camp)
    session.commit()
    session.refresh(camp)
    audit(session, "campaign", camp.id, "strategy_generated", mode=res.mode, warnings=res.warnings)
    session.commit()
    return campaign_out(session, camp)


@router.get("/campaigns")
def list_campaigns(brand_id: Optional[int] = None, session: Session = Depends(get_session)) -> list[dict]:
    q = select(Campaign).order_by(Campaign.id.desc())
    if brand_id is not None:
        q = q.where(Campaign.brand_id == brand_id)
    return [campaign_out(session, c) for c in session.exec(q).all()]


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: int, session: Session = Depends(get_session)) -> dict:
    camp = get_or_404(session, Campaign, campaign_id)
    concepts = session.exec(select(Concept).where(Concept.campaign_id == camp.id).order_by(Concept.id)).all()
    vids = latest_videos(session, camp.id)
    assets = session.exec(select(Asset).where(Asset.campaign_id == camp.id).order_by(Asset.id.desc())).all()
    its = session.exec(select(Iteration).where(Iteration.campaign_id == camp.id).order_by(Iteration.id.desc())).all()
    has_metrics = session.exec(select(MetricSnapshot.id).where(MetricSnapshot.campaign_id == camp.id)).first() is not None
    return {
        "campaign": campaign_out(session, camp),
        "concepts": [concept_out(c, vids.get(c.id)) for c in concepts],
        "assets": [asset_out(a) for a in assets],
        "iterations": [iteration_out(session, i) for i in its],
        "has_metrics": has_metrics,
    }


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    strategy: Optional[CampaignStrategy] = None
    status: Optional[Literal["approved", "scheduled", "generated"]] = None


@router.patch("/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, body: CampaignUpdate, session: Session = Depends(get_session)) -> dict:
    camp = get_or_404(session, Campaign, campaign_id)
    if body.name is not None:
        camp.name = body.name
    if body.strategy is not None:
        camp.strategy = body.strategy.model_dump()
    if body.status is not None:
        if body.status in {"approved", "scheduled"}:
            approved = session.exec(select(Concept).where(Concept.campaign_id == camp.id,
                                                          Concept.status == "approved")).all()
            if not approved:
                raise HTTPException(409, "Approve at least one concept before approving the campaign.")
        if body.status == "scheduled" and camp.status != "approved":
            raise HTTPException(409, "Approve the campaign before scheduling it.")
        camp.status = body.status
        audit(session, "campaign", camp.id, f"status_{body.status}")
    touch(camp)
    session.add(camp)
    session.commit()
    session.refresh(camp)
    return campaign_out(session, camp)


@router.get("/campaigns/{campaign_id}/export")
def export_campaign(campaign_id: int, session: Session = Depends(get_session)):
    """ZIP of approved concepts: copy CSV, strategy, concepts JSON and rendered videos. Nothing is published."""
    from fastapi.responses import Response

    from ..services.export_service import build_zip

    camp = get_or_404(session, Campaign, campaign_id)
    brand = get_or_404(session, Brand, camp.brand_id)
    concepts = session.exec(select(Concept).where(Concept.campaign_id == camp.id).order_by(Concept.id)).all()
    if not any(c.status == "approved" for c in concepts):
        raise HTTPException(409, "Approve at least one concept before exporting.")
    data, filename = build_zip(brand, camp, concepts, latest_videos(session, camp.id))
    audit(session, "campaign", camp.id, "exported", approved=sum(c.status == "approved" for c in concepts),
          bytes=len(data))
    session.commit()
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
