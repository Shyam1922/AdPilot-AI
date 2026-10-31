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
from .video_service import VideoInput, render, split_sentences

log = logging.getLogger("adpilot.video")

FORMATS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}


def _ordered_images(brand: Brand, profile: dict, product_focus: str) -> list[Path]:
    """Uploads first, then the focus product's image, then the rest. Tiny images are skipped."""
    paths = [Path(p) for p in brand.product_images if Path(p).exists()]
    uploads = [p for p in paths if p.name.startswith("upload_")]
    names = [p.get("name", "").lower() for p in profile.get("products", [])]
    focus = (product_focus or "").lower()
    idx = next((i for i, n in enumerate(names) if n and (n == focus or focus in n or n in focus)), 0)
    want = f"product_{idx + 1}"
    focus_img = [p for p in paths if p.stem == want]
    rest = [p for p in paths if p not in uploads and p not in focus_img]
    return list(dict.fromkeys(uploads + focus_img + rest))


def _pick_product_image(brand: Brand, profile: dict, product_focus: str) -> Path | None:
    imgs = _ordered_images(brand, profile, product_focus)
    return imgs[0] if imgs else None


def _clean_benefits(raw: list[str], brand: str, product: str, profile: dict, primary_text: str) -> list[str]:
    """3 distinct, meaningful benefit lines: never the brand name alone, never duplicates."""
    from .text_utils import jaccard
    out: list[str] = []

    def add(t: str) -> None:
        t = t.strip(" .·-")
        if len(t) < 12 or len(t.split()) < 2:
            return
        if jaccard(t, brand) > 0.5 or jaccard(t, product) > 0.7:
            return
        if any(jaccard(t, o) > 0.6 for o in out):
            return
        out.append(short_claim(t, 70))

    for b in raw:
        add(b)
    for c in profile.get("approved_claims", []):
        add(c["claim"])
    for v in profile.get("value_propositions", []):
        add(v)
    for sent in split_sentences(primary_text, 4, 80):
        add(sent)
    return out[:3]


def _story_text(text: str) -> str:
    """Drop internal notes (e.g. '(Dramatization)', 'Replace with a real review...') from on-screen story text."""
    text = re.sub(r"\(\s*dramati[sz]ation\s*\)\s*", "", text, flags=re.I)
    parts = [x for x in re.split(r"(?<=[.!?…])\s+", text) if x and not re.search(r"replace with|before launch|placeholder", x, re.I)]
    return " ".join(parts)


def latest_ai_clip(session: Session, concept_id: int) -> Asset | None:
    from sqlmodel import select
    return session.exec(select(Asset).where(Asset.concept_id == concept_id, Asset.kind == "ai_clip",
                                            Asset.status == "ready").order_by(Asset.id.desc())).first()


def build_input(session: Session, concept: Concept, mode: str = "motion") -> VideoInput:
    camp = session.get(Campaign, concept.campaign_id)
    brand = session.get(Brand, camp.brand_id)
    profile = brand.profile or {}
    focus = camp.product_focus or profile.get("product_name", "")
    prod = next((p for p in profile.get("products", []) if p.get("name", "").lower() == focus.lower()), None)
    beats = concept.video_script or []
    benefit_text = next((b.get("on_screen_text", "") for b in beats if b.get("beat") == "benefit"), "")
    raw = [b.strip() for b in re.split(r"\s·\s", benefit_text) if b.strip()]
    brand_name = profile.get("brand_name") or brand.name
    benefits = _clean_benefits(raw, brand_name, focus or brand_name, profile, _story_text(concept.primary_text))
    hook = next((b.get("on_screen_text") for b in beats if b.get("beat") == "hook"), None) or concept.hook
    imgs = _ordered_images(brand, profile, focus)
    clip = latest_ai_clip(session, concept.id) if mode == "ai_clip" else None
    return VideoInput(
        brand_name=brand_name,
        product_name=focus or brand.name,
        hook=hook, headline=concept.headline, cta=concept.cta, benefits=benefits,
        price=(prod or {}).get("price"), website=brand.website,
        product_image=imgs[0] if imgs else None, images=imgs[1:3],
        logo=Path(brand.logo_path) if brand.logo_path else None,
        colors=profile.get("visual_identity", {}), beats=beats,
        concept_type=concept.concept_type,
        story_lines=split_sentences(_story_text(concept.primary_text), 3, 90),
        ai_clip=Path(clip.path) if clip and Path(clip.path).exists() else None,
    )


def render_job(asset_id: int) -> None:
    with Session(engine) as session:
        asset = session.get(Asset, asset_id)
        if asset is None:
            return
        try:
            concept = session.get(Concept, asset.concept_id)
            mode = asset.meta.get("mode", "motion")
            v = build_input(session, concept, mode)
            if mode == "ai_clip" and v.ai_clip is None:
                raise RuntimeError("No AI clip is attached to this concept (or the file is missing). Attach one, or render in motion mode.")
            w, h = FORMATS.get(asset.fmt, FORMATS["9:16"])
            camp = session.get(Campaign, concept.campaign_id)
            out = settings.storage_dir / f"brand_{camp.brand_id}" / "videos" / f"concept_{concept.id}_v{asset.id}{'_ai' if mode == 'ai_clip' else ''}.mp4"
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
            if meta.get("ai_clip"):
                asset.generation_mode = "template+ai_broll"
            asset.meta = {**asset.meta, **meta, "progress": 1.0,
                          "product_image": v.product_image.name if v.product_image else None,
                          "needs_product_image": v.product_image is None,
                          "style": v.concept_type}
            asset.error = ""
        except Exception as exc:  # any failure is reported on the asset, never hidden
            log.exception("video render failed for asset %s", asset_id)
            asset.status = "failed"
            asset.error = str(exc)[:500]
        asset.updated_at = now()
        session.add(asset)
        session.commit()
