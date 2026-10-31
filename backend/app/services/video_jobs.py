"""Background video job: Asset(queued) -> rendering (progress) -> ready | failed. Never left stuck."""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from sqlmodel import Session

from ..config import settings
from ..db import engine
from ..models import Asset, Brand, Campaign, Concept, now
from .text_utils import short_claim
from .video_service import VideoInput, render

log = logging.getLogger("adpilot.video")

FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def _pick_product_image(brand: Brand, profile: dict, product_focus: str) -> Path | None:
    paths = [Path(p) for p in brand.product_images if Path(p).exists()]
    uploads = [p for p in paths if p.name.startswith("upload_")]
    if uploads:
        return uploads[0]
    names = [p.get("name", "").lower() for p in profile.get("products", [])]
    focus = (product_focus or "").lower()
    idx = next((i for i, n in enumerate(names) if n and (n == focus or focus in n or n in focus)), 0)
    want = f"product_{idx + 1}"
    return next((p for p in paths if p.stem == want), paths[0] if paths else None)


def build_input(session: Session, concept: Concept) -> VideoInput:
    camp = session.get(Campaign, concept.campaign_id)
    brand = session.get(Brand, camp.brand_id)
    profile = brand.profile or {}
    focus = camp.product_focus or profile.get("product_name", "")
    prod = next((p for p in profile.get("products", []) if p.get("name", "").lower() == focus.lower()), None)
    beats = concept.video_script or []
    benefit_text = next((b.get("on_screen_text", "") for b in beats if b.get("beat") == "benefit"), "")
    benefits = [b.strip() for b in re.split(r"\s·\s", benefit_text) if b.strip()] or \
               [short_claim(c["claim"]) for c in profile.get("approved_claims", [])[:3]]
    hook = next((b.get("on_screen_text") for b in beats if b.get("beat") == "hook"), None) or concept.hook
    return VideoInput(
        brand_name=profile.get("brand_name") or brand.name,
        product_name=focus or brand.name,
        hook=hook, headline=concept.headline, cta=concept.cta, benefits=benefits[:3],
        price=(prod or {}).get("price"), website=brand.website,
        product_image=_pick_product_image(brand, profile, focus),
        logo=Path(brand.logo_path) if brand.logo_path else None,
        colors=profile.get("visual_identity", {}), beats=beats,
    )


def render_job(asset_id: int) -> None:
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            return
        try:
            concept = session.get(Concept, asset.concept_id)
            v = build_input(session, concept)
            w, h = FORMATS.get(asset.fmt, FORMATS["9:16"])
            camp = session.get(Campaign, concept.campaign_id)
            out = settings.storage_dir / f"brand_{camp.brand_id}" / "videos" / f"concept_{concept.id}_v{asset.id}.mp4"
            asset.status, asset.meta = "rendering", {**asset.meta, "progress": 0.0}
            session.add(asset)
            session.commit()
            last = [0.0, time.time()]

            def progress(frac: float) -> None:
                if frac - last[0] >= 0.1 or frac >= 1.0:   # throttle DB writes to ~10 per video
                    last[0] = frac
                    asset.meta = {**asset.meta, "progress": round(frac, 2)}
                    session.add(asset)
                    session.commit()

            meta = render(v, out, w, h, progress=progress)
            asset.path = str(out)
            asset.status = "ready"
            asset.meta = {**asset.meta, **meta, "progress": 1.0,
                          "product_image": v.product_image.name if v.product_image else None}
            asset.error = ""
        except Exception as exc:  # any failure is reported on the asset, never hidden
            log.exception("video render failed for asset %s", asset_id)
            asset.status = "failed"
            asset.error = str(exc)[:500]
        asset.updated_at = now()
        session.add(asset)
        session.commit()
