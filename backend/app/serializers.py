"""DB rows -> API JSON shapes from docs/API_CONTRACT.md."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from .config import settings
from .models import Asset, Brand, Campaign, Concept, Iteration


def file_url(path: str) -> str | None:
    if not path:
        return None
    p = Path(path)
    try:
        rel = p.resolve().relative_to(settings.storage_dir.resolve())
    except ValueError:
        return None
    return "/files/" + rel.as_posix()


def _ts(d) -> str:
    return d.isoformat() if d else ""


def brand_out(b: Brand) -> dict[str, Any]:
    return {
        "id": b.id, "name": b.name, "website": b.website,
        "profile": b.profile, "guardrails": b.guardrails, "learnings": b.learnings,
        "sources": b.sources, "warnings": b.warnings,
        "logo_url": file_url(b.logo_path),
        "product_image_urls": [u for u in (file_url(p) for p in b.product_images) if u],
        "generation_mode": b.generation_mode,
        "integrations": b.integrations or {},
        "created_at": _ts(b.created_at), "updated_at": _ts(b.updated_at),
    }


def asset_out(a: Asset) -> dict[str, Any]:
    return {
        "id": a.id, "campaign_id": a.campaign_id, "concept_id": a.concept_id, "brand_id": a.brand_id,
        "kind": a.kind, "fmt": a.fmt,
        "url": file_url(a.path) if a.status == "ready" else None,
        "status": a.status, "progress": float(a.meta.get("progress", 1.0 if a.status == "ready" else 0.0)),
        "generation_mode": a.generation_mode, "error": a.error,
        "meta": {k: v for k, v in a.meta.items() if k != "progress"},
        "created_at": _ts(a.created_at), "updated_at": _ts(a.updated_at),
    }


def concept_out(c: Concept, latest_video: Asset | None = None) -> dict[str, Any]:
    return {
        "id": c.id, "campaign_id": c.campaign_id, "iteration_id": c.iteration_id,
        "parent_concept_id": c.parent_concept_id, "concept_type": c.concept_type,
        "target_segment": c.target_segment, "angle": c.angle, "hook": c.hook,
        "primary_text": c.primary_text, "headline": c.headline, "cta": c.cta,
        "visual_brief": c.visual_brief, "platform_copy": c.platform_copy, "video_script": c.video_script,
        "claim_sources": c.claim_sources, "risk_flags": c.risk_flags,
        "changed_variables": c.changed_variables, "rationale": c.rationale, "is_exploration": c.is_exploration,
        "status": c.status, "edited": c.edited, "generation_mode": c.generation_mode,
        "prompt_version": c.prompt_version,
        "latest_video": asset_out(latest_video) if latest_video else None,
        "created_at": _ts(c.created_at), "updated_at": _ts(c.updated_at),
    }


def latest_videos(session: Session, campaign_id: int) -> dict[int, Asset]:
    rows = session.exec(select(Asset).where(Asset.campaign_id == campaign_id, Asset.kind == "video")
                        .order_by(Asset.id)).all()
    return {a.concept_id: a for a in rows if a.concept_id is not None}


def _clean_strategy(c: Campaign) -> dict[str, Any]:
    from .services.strategist import normalize_strategy
    return normalize_strategy(c.strategy, c.channels) if c.strategy else c.strategy


def campaign_out(session: Session, c: Campaign) -> dict[str, Any]:
    concepts = session.exec(select(Concept).where(Concept.campaign_id == c.id)).all()
    vids = latest_videos(session, c.id)
    return {
        "id": c.id, "brand_id": c.brand_id, "name": c.name, "objective": c.objective, "channels": c.channels,
        "product_focus": c.product_focus, "audience_note": c.audience_note, "budget_note": c.budget_note,
        "status": c.status, "strategy": _clean_strategy(c), "generation_mode": c.generation_mode,
        "counts": {"concepts": len(concepts), "approved": sum(x.status == "approved" for x in concepts),
                   "videos_ready": sum(v.status == "ready" for v in vids.values())},
        "created_at": _ts(c.created_at), "updated_at": _ts(c.updated_at),
    }


def iteration_out(session: Session, it: Iteration) -> dict[str, Any]:
    variants = session.exec(select(Concept).where(Concept.iteration_id == it.id)).all()
    vids = latest_videos(session, it.campaign_id)
    return {
        "id": it.id, "campaign_id": it.campaign_id, "objective_metric": it.objective_metric,
        "insight_summary": it.insight_summary, "ranking": it.ranking, "selected_signals": it.selected_signals,
        "limitations": it.limitations, "data_sources": it.data_sources,
        "variants": [concept_out(v, vids.get(v.id)) for v in variants],
        "generation_mode": it.generation_mode, "created_at": _ts(it.created_at),
    }


def post_out(p) -> dict[str, Any]:
    limit = {"linkedin": 3000, "instagram": 2200, "x": 280}.get(p.platform, 3000)
    import re
    chars = len(re.sub(r"https?://\S+", "x" * 23, p.text)) if p.platform == "x" else len(p.text)
    return {"id": p.id, "campaign_id": p.campaign_id, "concept_id": p.concept_id, "platform": p.platform,
            "hook": p.hook, "text": p.text, "hashtags": p.hashtags, "thread": p.thread,
            "visual_idea": p.visual_idea, "cta": p.cta, "risk_flags": p.risk_flags, "status": p.status,
            "edited": p.edited, "generation_mode": p.generation_mode, "char_count": chars, "char_limit": limit,
            "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "publish_mode": p.publish_mode or "", "external_url": p.external_url or "",
            "metrics": p.metrics or {}, "metrics_source": p.metrics_source or "",
            "engagement_rate": _eng_rate(p.metrics or {}),
            "created_at": _ts(p.created_at), "updated_at": _ts(p.updated_at)}


def _eng_rate(m: dict) -> float | None:
    imp = int(m.get("impressions", 0) or 0)
    if not imp:
        return None
    eng = int(m.get("likes", 0)) + 2 * int(m.get("comments", 0)) + 3 * int(m.get("shares", 0)) + int(m.get("clicks", 0))
    return round(eng / imp, 4)
