"""Brand Intelligence endpoints: analyze a URL / manual facts into Brand Memory, edit it, upload assets."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from sqlmodel import Session, delete, select

from ..config import settings
from ..db import get_session
from ..models import Asset, Brand, Campaign, Concept, Iteration, MetricSnapshot, SocialPost
from ..schemas.brand import AnalyzeBrandRequest, BrandProfile, BrandUpdate
from ..serializers import brand_out
from ..services import brand_analyzer
from ..services.meko_sync import sync_brand_job
from ..services.extractor import ExtractionError, extract
from .common import audit, get_or_404, touch

router = APIRouter(tags=["brands"])


def brand_dir(brand_id: int) -> Path:
    return settings.storage_dir / f"brand_{brand_id}"


@router.post("/brands/analyze")
def analyze_brand(req: AnalyzeBrandRequest, background: BackgroundTasks,
                  session: Session = Depends(get_session)) -> dict:
    manual = req.manual
    if not req.url and not manual.brand_name:
        raise HTTPException(400, "Give a website URL, or at least a brand name in the manual details.")

    ext, warnings = None, []
    if req.url:
        try:
            ext = extract(str(req.url))
        except ExtractionError as exc:
            if not manual.brand_name:
                raise HTTPException(400, f"Couldn't read that site: {exc} Add details manually and try again.")
            warnings.append(f"Couldn't read the website ({exc}); used your manual details only.")

    brand = Brand(name=manual.brand_name or "Analyzing…", website=str(req.url or ""),
                  manual_inputs=manual.model_dump(),
                  guardrails={"claims_to_avoid": manual.claims_to_avoid, "words_to_avoid": [], "notes": ""})
    session.add(brand)
    session.commit()
    session.refresh(brand)

    try:
        result = brand_analyzer.analyze(ext, manual, brand_dir(brand.id))
    except Exception:
        session.delete(brand)
        session.commit()
        raise

    brand.name = result.profile.brand_name
    brand.profile = result.profile.model_dump()
    brand.sources = result.sources
    brand.warnings = warnings + result.warnings
    brand.logo_path = result.logo_path
    brand.product_images = result.product_image_paths
    brand.generation_mode = result.mode
    touch(brand)
    audit(session, "brand", brand.id, "analyzed", url=brand.website, mode=result.mode)
    brand.integrations = {"meko": {"status": "syncing"}}
    session.add(brand)
    session.commit()
    session.refresh(brand)
    background.add_task(sync_brand_job, brand.id)   # mirror Brand Memory into Meko after responding
    return brand_out(brand)


@router.get("/brands")
def list_brands(session: Session = Depends(get_session)) -> list[dict]:
    return [brand_out(b) for b in session.exec(select(Brand).order_by(Brand.id.desc())).all()]


@router.get("/brands/{brand_id}")
def get_brand(brand_id: int, session: Session = Depends(get_session)) -> dict:
    return brand_out(get_or_404(session, Brand, brand_id))


@router.patch("/brands/{brand_id}")
def update_brand(brand_id: int, body: BrandUpdate, background: BackgroundTasks,
                 session: Session = Depends(get_session)) -> dict:
    brand = get_or_404(session, Brand, brand_id)
    if body.name is not None:
        brand.name = body.name
    if body.profile is not None:
        brand.profile = BrandProfile.model_validate(body.profile).model_dump()
    if body.guardrails is not None:
        brand.guardrails = {**brand.guardrails, **body.guardrails}
    touch(brand)
    audit(session, "brand", brand.id, "edited", fields=[k for k, v in body.model_dump().items() if v is not None])
    session.add(brand)
    session.commit()
    session.refresh(brand)
    if body.profile is not None:
        background.add_task(sync_brand_job, brand.id)
    return brand_out(brand)


@router.delete("/brands/{brand_id}", status_code=204)
def delete_brand(brand_id: int, session: Session = Depends(get_session)) -> Response:
    """Remove a brand and everything under it: campaigns, concepts, posts, assets, metrics, files.

    The Meko datapack is left alone (Meko has no delete over MCP); it is simply no longer referenced.
    """
    brand = get_or_404(session, Brand, brand_id)
    camp_ids = [c for c in session.exec(select(Campaign.id).where(Campaign.brand_id == brand.id)).all()]
    if camp_ids:
        for model in (MetricSnapshot, SocialPost, Iteration, Concept, Asset):
            session.exec(delete(model).where(model.campaign_id.in_(camp_ids)))
        session.exec(delete(Campaign).where(Campaign.id.in_(camp_ids)))
    session.exec(delete(Asset).where(Asset.brand_id == brand.id))
    name = brand.name
    session.delete(brand)
    audit(session, "brand", brand_id, "deleted", name=name, campaigns=len(camp_ids))
    session.commit()
    shutil.rmtree(brand_dir(brand_id), ignore_errors=True)
    return Response(status_code=204)


ALLOWED = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


@router.post("/brands/{brand_id}/uploads")
async def upload_brand_asset(brand_id: int, file: UploadFile = File(...), role: str = Form("product"),
                             session: Session = Depends(get_session)) -> dict:
    brand = get_or_404(session, Brand, brand_id)
    if role not in {"logo", "product"}:
        raise HTTPException(422, "role must be 'logo' or 'product'.")
    ext = ALLOWED.get((file.content_type or "").lower())
    if not ext:
        raise HTTPException(415, "Upload a PNG, JPG or WebP image.")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File is larger than {settings.max_upload_bytes // (1024 * 1024)} MB.")
    d = brand_dir(brand.id)
    d.mkdir(parents=True, exist_ok=True)
    n = len(brand.product_images) + 1
    path = d / (f"logo_upload{ext}" if role == "logo" else f"upload_{n}{ext}")
    path.write_bytes(data)
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
    except Exception:
        path.unlink(missing_ok=True)
        raise HTTPException(415, "That file isn't a valid image.")
    if role == "logo":
        brand.logo_path = str(path)
    else:
        brand.product_images = [str(path), *brand.product_images]  # uploads take priority in videos
    touch(brand)
    audit(session, "brand", brand.id, "uploaded", role=role, filename=file.filename)
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return brand_out(brand)
