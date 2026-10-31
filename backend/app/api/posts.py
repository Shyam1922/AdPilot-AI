"""Social posts: draft LinkedIn / Instagram / X posts from a concept. Drafts only, nothing is published."""
from __future__ import annotations

from typing import Literal

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import Brand, Campaign, Concept, SocialPost, now
from ..serializers import post_out
from ..services import meko_memory, posting_insights as pi, social_posts
from ..services.meko_sync import analyze_brand_posts, datapack_for, save_posting_insights_job
from ..services.output_validation import claim_guard
from .common import audit, brand_context, get_or_404, guardrail_list, touch

router = APIRouter(tags=["posts"])

CONCEPT_FIELDS = ["concept_type", "target_segment", "angle", "hook", "primary_text", "headline", "cta"]


class PostGenerateRequest(BaseModel):
    platforms: list[Literal["linkedin", "instagram", "x"]] = ["linkedin", "instagram", "x"]
    language: Literal["en", "hi", "hinglish"] = "en"


class PostUpdate(BaseModel):
    text: str | None = None
    status: Literal["generated", "approved", "rejected"] | None = None


class ScheduleBody(BaseModel):
    scheduled_at: datetime


class PublishBody(BaseModel):
    # manual_share: the user pressed Post on the platform (we opened it with the text filled in).
    # simulated: a labelled demo publish; nothing leaves the app.
    mode: Literal["manual_share", "simulated"] = "manual_share"
    external_url: str = ""


class MetricsBody(BaseModel):
    impressions: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    clicks: int = 0


def _concept_dict(c: Concept) -> dict:
    return {k: getattr(c, k) for k in CONCEPT_FIELDS}


def _source_text(brand, profile) -> str:
    return " ".join(s.get("text", "") for s in brand.sources)


@router.post("/concepts/{concept_id}/posts/generate")
def generate_posts(concept_id: int, req: PostGenerateRequest = PostGenerateRequest(),
                   session: Session = Depends(get_session)) -> list[dict]:
    c = get_or_404(session, Concept, concept_id)
    camp = get_or_404(session, Campaign, c.campaign_id)
    brand, profile, strategy = brand_context(session, camp)
    dp = datapack_for(brand)
    memory, _ = meko_memory.context_for_generation(
        dp, f"social posts for {camp.product_focus}: tone, what resonated, audience", title=f"Posts · {camp.name}", brand=brand.name) \
        if dp else ("", None)
    insights = analyze_brand_posts(session, brand.id)
    ctx = "\n".join(x for x in (pi.prompt_context(insights), memory) if x)
    posts, mode, warnings = social_posts.generate(_concept_dict(c), profile, strategy, camp.product_focus,
                                                  guardrail_list(brand), brand.sources, brand.website,
                                                  req.platforms, req.language, memory_context=ctx)
    out = []
    for d in posts:
        # a fresh draft replaces an older un-approved draft for the same concept + platform
        for old in session.exec(select(SocialPost).where(SocialPost.concept_id == c.id,
                                                         SocialPost.platform == d["platform"],
                                                         SocialPost.status.in_(["generated", "rejected"]))).all():
            session.delete(old)
        row = SocialPost(campaign_id=camp.id, concept_id=c.id, platform=d["platform"], hook=d["hook"],
                         text=d["text"], hashtags=d["hashtags"], thread=d["thread"], visual_idea=d["visual_idea"],
                         cta=d["cta"], risk_flags=d["risk_flags"], generation_mode=mode,
                         prompt_version=social_posts.POST_PROMPT_VERSION)
        session.add(row)
        out.append(row)
    session.commit()
    for r in out:
        session.refresh(r)
    audit(session, "concept", c.id, "posts_generated", platforms=req.platforms, mode=mode, warnings=warnings)
    session.commit()
    return [_with_suggestion(r, insights) for r in out]


def _with_suggestion(p: SocialPost, insights: dict) -> dict:
    d = post_out(p)
    slot = (insights.get("next_slots") or {}).get(p.platform)
    d["suggested"] = {**slot, "basis": insights.get("basis", "default")} if slot else None
    return d


@router.get("/campaigns/{campaign_id}/posts")
def list_posts(campaign_id: int, session: Session = Depends(get_session)) -> list[dict]:
    camp = get_or_404(session, Campaign, campaign_id)
    insights = analyze_brand_posts(session, camp.brand_id)
    rows = session.exec(select(SocialPost).where(SocialPost.campaign_id == campaign_id)
                        .order_by(SocialPost.concept_id, SocialPost.id)).all()
    return [_with_suggestion(r, insights) for r in rows]


@router.get("/brands/{brand_id}/posting-insights")
def posting_insights(brand_id: int, session: Session = Depends(get_session)) -> dict:
    """Best times to post and what content works, learned from this brand's published posts."""
    get_or_404(session, Brand, brand_id)
    return analyze_brand_posts(session, brand_id)


@router.get("/brands/{brand_id}/posts")
def brand_posts(brand_id: int, status: str | None = None, session: Session = Depends(get_session)) -> list[dict]:
    """Every post across the brand's campaigns (newest first). Used by the history views."""
    get_or_404(session, Brand, brand_id)
    q = select(SocialPost).join(Campaign, Campaign.id == SocialPost.campaign_id).where(Campaign.brand_id == brand_id)
    if status:
        q = q.where(SocialPost.status == status)
    rows = session.exec(q.order_by(SocialPost.id.desc())).all()
    return [post_out(r) for r in rows]


@router.get("/brands/{brand_id}/memory")
def brand_memory_view(brand_id: int, recall: bool = False, session: Session = Depends(get_session)) -> dict:
    """What Meko remembers for this brand (live context search) plus the local record of what was written."""
    brand = get_or_404(session, Brand, brand_id)
    dp = datapack_for(brand)
    meko = (brand.integrations or {}).get("meko") or {}
    out = {"configured": meko_memory.configured(), "datapack_id": dp, "status": meko.get("status", "not_configured"),
           "written": {"brand_facts": meko.get("memories_added", 0), "learnings": meko.get("learnings_saved", 0),
                       "posting_patterns": meko.get("posting_patterns_saved", 0),
                       "conversations": len(meko.get("conversations", []))},
           "synthetic_history": (brand.integrations or {}).get("synthetic_history"),
           "recalled": {}, "local_learnings": brand.learnings}
    if recall and dp and meko_memory.configured():     # a live search takes a few seconds, so only on request
        out["recalled"] = meko_memory.read_memory(dp, [
            "When and where does this brand's audience engage most with posts?",
            "What ad angles and hooks have worked best for this brand?",
            "What does this brand like to post and what tone should posts use?"], title=f"Memory view · {brand.name}", brand=brand.name)
    return out


@router.patch("/posts/{post_id}")
def update_post(post_id: int, body: PostUpdate, session: Session = Depends(get_session)) -> dict:
    p = get_or_404(session, SocialPost, post_id)
    camp = get_or_404(session, Campaign, p.campaign_id)
    brand, profile, _ = brand_context(session, camp)
    if p.status == "published":
        raise HTTPException(409, "This post is already published. Create a new draft instead of editing it.")
    if body.text is not None and body.text != p.text:
        p.text, p.edited = body.text.strip(), True
        src = _source_text(brand, profile)
        p.risk_flags = claim_guard({"post": p.text}, src, guardrail_list(brand), "")
        if p.platform == "x" and post_out(p)["char_count"] > 280:
            p.risk_flags.append({"code": "too_long", "severity": "block", "field": "post",
                                 "message": "Over X's 280-character limit. Shorten it before approving."})
        audit(session, "post", p.id, "edited")
    if body.status is not None:
        blocking = [f for f in p.risk_flags if f.get("severity") == "block"]
        if body.status == "approved" and blocking:
            raise HTTPException(409, "This post has blocking risk flags: "
                                + "; ".join(f["message"] for f in blocking) + " Edit the text first.")
        p.status = body.status
        audit(session, "post", p.id, f"status_{body.status}")
    touch(p)
    session.add(p)
    session.commit()
    session.refresh(p)
    return post_out(p)


@router.post("/posts/{post_id}/regenerate")
def regenerate_post(post_id: int, session: Session = Depends(get_session)) -> dict:
    p = get_or_404(session, SocialPost, post_id)
    c = get_or_404(session, Concept, p.concept_id)
    camp = get_or_404(session, Campaign, p.campaign_id)
    brand, profile, strategy = brand_context(session, camp)
    n = session.exec(select(SocialPost).where(SocialPost.concept_id == c.id,
                                              SocialPost.platform == p.platform)).all()
    posts, mode, _ = social_posts.generate(_concept_dict(c), profile, strategy, camp.product_focus,
                                           guardrail_list(brand), brand.sources, brand.website, [p.platform],
                                           variant=p.id % 3 + 1)
    d = posts[0]
    for k in ("hook", "text", "hashtags", "thread", "visual_idea", "cta", "risk_flags"):
        setattr(p, k, d[k])
    p.status, p.edited, p.generation_mode = "generated", False, mode
    touch(p)
    audit(session, "post", p.id, "regenerated", mode=mode)
    session.add(p)
    session.commit()
    session.refresh(p)
    return post_out(p)


@router.delete("/posts/{post_id}", status_code=204)
def delete_post(post_id: int, session: Session = Depends(get_session)) -> None:
    p = get_or_404(session, SocialPost, post_id)
    session.delete(p)
    session.commit()


def _can_publish(p: SocialPost) -> None:
    if p.status not in ("approved", "scheduled"):
        raise HTTPException(409, "Approve the post before scheduling or publishing it.")
    if any(f.get("severity") == "block" for f in p.risk_flags or []):
        raise HTTPException(409, "This post has blocking risk flags. Edit it first.")


@router.post("/posts/{post_id}/schedule")
def schedule_post(post_id: int, body: ScheduleBody, session: Session = Depends(get_session)) -> dict:
    p = get_or_404(session, SocialPost, post_id)
    _can_publish(p)
    p.scheduled_at, p.status = body.scheduled_at, "scheduled"
    touch(p)
    audit(session, "post", p.id, "scheduled", at=body.scheduled_at.isoformat(), platform=p.platform)
    session.add(p)
    session.commit()
    session.refresh(p)
    return post_out(p)


@router.delete("/posts/{post_id}/schedule")
def unschedule_post(post_id: int, session: Session = Depends(get_session)) -> dict:
    p = get_or_404(session, SocialPost, post_id)
    if p.status != "scheduled":
        raise HTTPException(409, "This post isn't scheduled.")
    p.scheduled_at, p.status = None, "approved"
    touch(p)
    session.add(p)
    session.commit()
    session.refresh(p)
    return post_out(p)


@router.post("/posts/{post_id}/publish")
def publish_post(post_id: int, body: PublishBody, background: BackgroundTasks,
                 session: Session = Depends(get_session)) -> dict:
    """Record that the post went out. AdPilot never posts for you: in manual_share the user pressed Post on the
    platform; in simulated mode nothing leaves the app and the post is labelled as simulated everywhere."""
    p = get_or_404(session, SocialPost, post_id)
    _can_publish(p)
    p.status, p.published_at, p.publish_mode = "published", now(), body.mode
    p.external_url = body.external_url.strip()
    touch(p)
    camp = get_or_404(session, Campaign, p.campaign_id)
    audit(session, "post", p.id, "published", platform=p.platform, mode=body.mode)
    session.add(p)
    session.commit()
    session.refresh(p)
    background.add_task(save_posting_insights_job, camp.brand_id)
    return post_out(p)


@router.post("/posts/{post_id}/metrics")
def set_post_metrics(post_id: int, body: MetricsBody, background: BackgroundTasks,
                     session: Session = Depends(get_session)) -> dict:
    """Enter the real numbers from the platform (labelled manual)."""
    p = get_or_404(session, SocialPost, post_id)
    if p.status != "published":
        raise HTTPException(409, "Publish the post before adding results.")
    p.metrics, p.metrics_source = body.model_dump(), "manual"
    touch(p)
    camp = get_or_404(session, Campaign, p.campaign_id)
    session.add(p)
    session.commit()
    session.refresh(p)
    background.add_task(save_posting_insights_job, camp.brand_id)
    return post_out(p)


@router.post("/campaigns/{campaign_id}/posts/simulate-engagement")
def simulate_engagement(campaign_id: int, background: BackgroundTasks, session: Session = Depends(get_session)) -> dict:
    """Demo helper: give published posts without results some SIMULATED engagement. Always labelled simulated."""
    import random
    camp = get_or_404(session, Campaign, campaign_id)
    rows = session.exec(select(SocialPost).where(SocialPost.campaign_id == campaign_id,
                                                  SocialPost.status == "published")).all()
    n = 0
    for p in rows:
        if p.metrics:
            continue
        rng = random.Random(p.id * 7919)
        imp = rng.randint(*{"instagram": (1800, 6000), "linkedin": (600, 2400), "x": (300, 1800)}[p.platform])
        r = rng.uniform(0.02, 0.07)
        eng = int(imp * r)
        p.metrics = {"impressions": imp, "likes": int(eng * .7), "comments": int(eng * .08),
                     "shares": int(eng * .05), "clicks": int(eng * .17)}
        p.metrics_source = "simulated"
        session.add(p)
        n += 1
    audit(session, "campaign", camp.id, "post_engagement_simulated", posts=n)
    session.commit()
    background.add_task(save_posting_insights_job, camp.brand_id)
    return {"posts_updated": n, "source": "simulated"}
