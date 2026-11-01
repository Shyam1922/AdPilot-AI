"""Creative Studio endpoints: generate concepts, edit / approve / reject, regenerate one field."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..models import Campaign, Concept
from ..schemas.concept import ConceptUpdate
from ..serializers import concept_out, latest_videos
from ..services import ad_generator, ai_prompt, meko_memory
from ..services.meko_sync import datapack_for, log_generation_job
from .common import audit, brand_context, get_or_404, guardrail_list, touch

router = APIRouter(tags=["concepts"])

CONCEPT_FIELDS = ["concept_type", "target_segment", "angle", "hook", "primary_text", "headline", "cta",
                  "visual_brief", "platform_copy", "video_script", "claim_sources", "risk_flags", "rationale"]


class GenerateRequest(BaseModel):
    count: int = 5
    language: Literal["en", "hi", "hinglish"] = "en"


def _concept_dict(c: Concept) -> dict:
    return {k: getattr(c, k) for k in CONCEPT_FIELDS}


@router.post("/campaigns/{campaign_id}/concepts/generate")
def generate_concepts(campaign_id: int, background: BackgroundTasks, req: GenerateRequest = GenerateRequest(),
                      session: Session = Depends(get_session)) -> list[dict]:
    camp = get_or_404(session, Campaign, campaign_id)
    brand, profile, strategy = brand_context(session, camp)
    # Shared agent memory: pull past learnings / brand facts from Meko (empty string if unavailable).
    dp = datapack_for(brand)
    memory_context, meko_cid = meko_memory.context_for_generation(
        dp, f"{camp.objective} campaign for {camp.product_focus}: what worked, audience, tone, claims",
        title=f"Concepts · {camp.name}", brand=brand.name) if dp else ("", None)
    items, mode, warnings = ad_generator.generate(profile, strategy, camp.product_focus, guardrail_list(brand),
                                                  brand.sources, req.language, memory_context=memory_context)
    created = []
    for d in items[: max(1, min(req.count, 5))]:
        c = Concept(campaign_id=camp.id, **{k: d[k] for k in CONCEPT_FIELDS if k in d},
                    generation_mode=d["generation_mode"], prompt_version=d["prompt_version"])
        session.add(c)
        created.append(c)
    camp.status = "generated" if camp.status == "draft" else camp.status
    touch(camp)
    session.commit()
    for c in created:
        session.refresh(c)
    audit(session, "campaign", camp.id, "concepts_generated", count=len(created), mode=mode, warnings=warnings,
          meko_context_used=bool(memory_context))
    session.commit()
    if dp:
        background.add_task(
            log_generation_job, brand.id, meko_cid, camp.name,
            f"Generate {len(created)} concepts · objective {camp.objective} · product {camp.product_focus}",
            "\n".join(f"[{c.concept_type}] {c.hook} / {c.headline} / {c.cta}" for c in created),
            ["read Brand Memory", "search Meko context", "write 5 angles", "run claim guard", "adapt per platform"])
    return [concept_out(c) for c in created]


@router.patch("/concepts/{concept_id}")
def update_concept(concept_id: int, body: ConceptUpdate, session: Session = Depends(get_session)) -> dict:
    c = get_or_404(session, Concept, concept_id)
    camp = get_or_404(session, Campaign, c.campaign_id)
    copy_fields = {k: v for k, v in body.model_dump(exclude={"status"}).items() if v is not None}
    if copy_fields:
        for k, v in copy_fields.items():
            setattr(c, k, v)
        c.edited = True
        brand, profile, strategy = brand_context(session, camp)
        d = ad_generator.refresh_derived(_concept_dict(c), profile, strategy, camp.product_focus,
                                         guardrail_list(brand), brand.sources)
        c.risk_flags, c.platform_copy = d["risk_flags"], d["platform_copy"]
        audit(session, "concept", c.id, "edited", fields=list(copy_fields))
    if body.status is not None:
        blocking = [f for f in c.risk_flags if f.get("severity") == "block"]
        if body.status == "approved" and blocking:
            raise HTTPException(409, "This concept has blocking risk flags: "
                                + "; ".join(f["message"] for f in blocking) + " Edit the copy first.")
        c.status = body.status
        audit(session, "concept", c.id, f"status_{body.status}")
    touch(c)
    session.add(c)
    session.commit()
    session.refresh(c)
    return concept_out(c, latest_videos(session, camp.id).get(c.id))


class RegenerateRequest(BaseModel):
    field: Literal["hook", "headline", "cta", "primary_text"]


@router.post("/concepts/{concept_id}/regenerate")
def regenerate_field(concept_id: int, req: RegenerateRequest, session: Session = Depends(get_session)) -> dict:
    c = get_or_404(session, Concept, concept_id)
    camp = get_or_404(session, Campaign, c.campaign_id)
    brand, profile, strategy = brand_context(session, camp)
    d, mode = ad_generator.regenerate_field(_concept_dict(c), req.field, profile, strategy, camp.product_focus,
                                            guardrail_list(brand), brand.sources)
    for k in (req.field, "video_script", "risk_flags", "platform_copy"):
        setattr(c, k, d[k])
    c.status = "generated"   # changed copy needs a fresh approval
    c.generation_mode = mode
    touch(c)
    audit(session, "concept", c.id, "regenerated", field=req.field, mode=mode)
    session.add(c)
    session.commit()
    session.refresh(c)
    return concept_out(c, latest_videos(session, camp.id).get(c.id))


@router.get("/concepts/{concept_id}")
def get_concept(concept_id: int, session: Session = Depends(get_session)) -> dict:
    c = get_or_404(session, Concept, concept_id)
    return concept_out(c, latest_videos(session, c.campaign_id).get(c.id))


class VideoRequest(BaseModel):
    format: Literal["9:16", "1:1", "4:5"] = "9:16"
    # "motion" = our own animated template (default, always available).
    # "ai_clip" = play the AI-generated clip attached to this concept in the product + benefit scenes.
    mode: Literal["motion", "ai_clip"] = "motion"


@router.post("/concepts/{concept_id}/video", status_code=202)
def create_video(concept_id: int, background: BackgroundTasks, req: VideoRequest = VideoRequest(),
                 session: Session = Depends(get_session)) -> dict:
    """Start rendering an MP4 for this concept. Poll GET /api/assets/{id} until status is ready or failed."""
    import shutil

    from ..models import Asset
    from ..serializers import asset_out
    from ..services.video_jobs import render_job

    c = get_or_404(session, Concept, concept_id)
    camp = get_or_404(session, Campaign, c.campaign_id)
    from ..services.video_jobs import latest_ai_clip
    from ..services.video_service import ffmpeg_path
    if not ffmpeg_path():
        raise HTTPException(503, "FFmpeg is not installed on the server, so videos can't be rendered.")
    if req.mode == "ai_clip" and latest_ai_clip(session, c.id) is None:
        raise HTTPException(409, "No AI clip is attached to this concept yet. Upload one (POST /concepts/{id}/ai-clip) "
                                 "or render with mode 'motion'.")
    asset = Asset(campaign_id=camp.id, concept_id=c.id, brand_id=camp.brand_id, kind="video", fmt=req.format,
                  status="queued", generation_mode="template", meta={"progress": 0.0, "mode": req.mode})
    session.add(asset)
    session.commit()
    session.refresh(asset)
    audit(session, "concept", c.id, "video_requested", asset_id=asset.id, format=req.format, mode=req.mode)
    session.commit()
    background.add_task(render_job, asset.id)
    return asset_out(asset)


# --------------------------------------------------------------------------- optional AI clip (switchable)
AI_CLIP_EXT = {".mp4", ".mov", ".webm", ".m4v"}
AI_CLIP_MAX_BYTES = 80 * 1024 * 1024
AI_CLIP_MAX_SECONDS = 30


@router.get("/concepts/{concept_id}/video-options")
def video_options(concept_id: int, session: Session = Depends(get_session)) -> dict:
    """What the UI can offer for this concept: the standard motion ad, and the Pro AI-clip ad."""
    from ..services.video_jobs import latest_ai_clip
    if session.get(Concept, concept_id) is None:
        raise HTTPException(404, "Concept not found")
    clip = latest_ai_clip(session, concept_id)
    return {"modes": [
        {"mode": "motion", "label": "Standard", "tier": "standard", "available": True,
         "description": "Animated product ad built from your Brand Memory, product photos and verified claims."},
        {"mode": "ai_clip", "label": "Pro - AI video", "tier": "pro", "available": clip is not None,
         "has_clip": clip is not None,
         "description": "Same verified copy and price/CTA overlays, on top of a cinematic AI-generated clip of the product.",
         "needs": None if clip else "Upload an AI clip (POST /api/concepts/{id}/ai-clip)"}]}


@router.get("/concepts/{concept_id}/ai-prompt")
def ai_clip_prompt(concept_id: int, session: Session = Depends(get_session)) -> dict:
    """A ready-to-paste prompt for an AI video tool (Veo in Flow, Higgsfield, Runway, ...). Uses the concept's own
    visual brief, and tells the tool to keep the product exact and to render no text, so our verified copy stays on top."""
    c = get_or_404(session, Concept, concept_id)
    camp = get_or_404(session, Campaign, c.campaign_id)
    brand, profile, _ = brand_context(session, camp)
    product = camp.product_focus or profile.product_name
    vi = getattr(profile, "visual_identity", None)
    colours = [x for x in (getattr(vi, "primary", ""), getattr(vi, "secondary", "")) if x] if vi else []
    prods = list(getattr(profile, "products", []) or [])
    feats = list(getattr(prods[0], "features", []) or []) if prods else []
    out = ai_prompt.build(c.concept_type, brand.name, product, profile.product_category, c.target_segment,
                          list(profile.brand_tone or []), colours, feats[0] if feats else "",
                          hook=c.hook, angle=c.angle, scene=str((c.visual_brief or {}).get("scene", "")))
    prompt = out["prompt"]
    return {"concept_id": c.id, "prompt": prompt, "duration_s": out["duration_s"], "aspect_ratio": out["aspect_ratio"],
            "directed_by": out["directed_by"]}


@router.post("/concepts/{concept_id}/ai-clip")
async def attach_ai_clip(concept_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    """Attach an AI-generated clip (made in any tool) to this concept. Render with mode 'ai_clip' to use it."""
    import time
    from pathlib import Path

    from ..config import settings
    from ..models import Asset
    from ..serializers import asset_out
    from ..services.video_service import probe_clip

    c = get_or_404(session, Concept, concept_id)
    camp = get_or_404(session, Campaign, c.campaign_id)
    ext = Path(file.filename or "clip.mp4").suffix.lower()
    if ext not in AI_CLIP_EXT:
        raise HTTPException(422, f"Use a video file ({', '.join(sorted(AI_CLIP_EXT))}).")
    data = await file.read()
    if len(data) > AI_CLIP_MAX_BYTES:
        raise HTTPException(413, f"Clip is too large (max {AI_CLIP_MAX_BYTES // (1024 * 1024)} MB).")
    d = settings.storage_dir / f"brand_{camp.brand_id}" / "ai_clips"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"concept_{c.id}_{int(time.time())}{ext}"
    path.write_bytes(data)
    dur = probe_clip(path)
    if dur is None or dur > AI_CLIP_MAX_SECONDS:
        path.unlink(missing_ok=True)
        raise HTTPException(422, "That file isn't a readable video, or it is longer than "
                                 f"{AI_CLIP_MAX_SECONDS} seconds.")
    asset = Asset(campaign_id=camp.id, concept_id=c.id, brand_id=camp.brand_id, kind="ai_clip", fmt="9:16",
                  path=str(path), status="ready", generation_mode="external_ai",
                  meta={"duration_s": round(dur, 2), "original_name": file.filename, "source": "user_attached"})
    session.add(asset)
    audit(session, "concept", c.id, "ai_clip_attached", filename=file.filename, duration_s=round(dur, 2))
    session.commit()
    session.refresh(asset)
    return asset_out(asset)


@router.delete("/concepts/{concept_id}/ai-clip", status_code=204)
def remove_ai_clips(concept_id: int, session: Session = Depends(get_session)) -> None:
    """Detach the AI clip(s) from this concept. Already-rendered videos are kept."""
    from pathlib import Path

    from sqlmodel import select

    from ..models import Asset
    get_or_404(session, Concept, concept_id)
    for a in session.exec(select(Asset).where(Asset.concept_id == concept_id, Asset.kind == "ai_clip")).all():
        if a.path:
            Path(a.path).unlink(missing_ok=True)
        session.delete(a)
    audit(session, "concept", concept_id, "ai_clip_removed")
    session.commit()
