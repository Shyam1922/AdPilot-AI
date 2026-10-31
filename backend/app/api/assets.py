"""Asset Library endpoints (video rendering is added in G2)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from ..db import get_session
from ..models import Asset
from ..serializers import asset_out
from .common import get_or_404

router = APIRouter(tags=["assets"])


@router.get("/assets/{asset_id}")
def get_asset(asset_id: int, session: Session = Depends(get_session)) -> dict:
    return asset_out(get_or_404(session, Asset, asset_id))


@router.get("/assets")
def list_assets(brand_id: Optional[int] = None, kind: Optional[str] = None,
                session: Session = Depends(get_session)) -> list[dict]:
    q = select(Asset).order_by(Asset.id.desc())
    if brand_id is not None:
        q = q.where(Asset.brand_id == brand_id)
    if kind:
        q = q.where(Asset.kind == kind)
    return [asset_out(a) for a in session.exec(q).all()]
