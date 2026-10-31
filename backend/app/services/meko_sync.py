"""Background jobs that mirror AdPilot activity into Meko and record the outcome on the brand.

They run after the HTTP response is sent (FastAPI BackgroundTasks), so Meko latency never
slows the UI. Results land in brand.integrations["meko"] for the frontend to display.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session

from ..db import engine
from ..models import Brand
from . import meko_memory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save(session: Session, brand: Brand, **fields) -> None:
    meko = dict((brand.integrations or {}).get("meko", {}))
    meko.update(fields)
    brand.integrations = {**(brand.integrations or {}), "meko": meko}
    session.add(brand)
    session.commit()


def datapack_for(brand: Brand) -> str | None:
    return ((brand.integrations or {}).get("meko") or {}).get("datapack_id")


def sync_brand_job(brand_id: int) -> None:
    with Session(engine) as session:
        brand = session.get(Brand, brand_id)
        if brand is None:
            return
        if not meko_memory.configured():
            _save(session, brand, status="not_configured")
            return
        dp = meko_memory.ensure_datapack(brand.name, brand.id, datapack_for(brand))
        if not dp:
            _save(session, brand, status="failed", error=meko_memory.status()["last_error"], checked_at=_now())
            return
        res = meko_memory.sync_brand(dp, brand.profile)
        if res is None:
            _save(session, brand, datapack_id=dp, status="failed", error=meko_memory.status()["last_error"],
                  checked_at=_now())
        else:
            _save(session, brand, datapack_id=dp, status="synced", synced_at=_now(), error="",
                  memories_added=res.get("memories_added", 0))


def log_generation_job(brand_id: int, conversation_id: str | None, campaign_name: str, request: str, summary: str,
                       plan: list[str]) -> None:
    with Session(engine) as session:
        brand = session.get(Brand, brand_id)
        dp = datapack_for(brand) if brand else None
        if not brand or not dp:
            return
        res = meko_memory.log_generation(dp, conversation_id, campaign_name, request, summary, plan)
        if res:
            convs = list(((brand.integrations or {}).get("meko") or {}).get("conversations", []))
            convs.append({"conversation_id": res.get("conversation_id"), "title": campaign_name, "at": _now()})
            _save(session, brand, conversations=convs[-20:])


def save_learnings_job(brand_id: int, learnings: list[str]) -> None:
    with Session(engine) as session:
        brand = session.get(Brand, brand_id)
        dp = datapack_for(brand) if brand else None
        if not brand or not dp:
            return
        res = meko_memory.save_learnings(dp, learnings, brand=brand.name)
        if res:
            _save(session, brand, learnings_saved=((brand.integrations.get("meko") or {}).get("learnings_saved", 0)
                                                   + res.get("memories_added", 0)), last_learning_at=_now())


def save_posting_insights_job(brand_id: int) -> None:
    """Write the brand's posting patterns (best times, what content works) to Meko, only when they changed."""
    from ..models import Campaign, Concept, SocialPost
    from sqlmodel import select
    from . import posting_insights as pi

    with Session(engine) as session:
        brand = session.get(Brand, brand_id)
        dp = datapack_for(brand) if brand else None
        if not brand or not dp:
            return
        insights = analyze_brand_posts(session, brand_id)
        prefs = insights.get("preferences", [])
        meko = (brand.integrations or {}).get("meko") or {}
        h = pi.digest(insights)
        if not prefs or meko.get("posting_hash") == h:
            return
        synthetic = "synthetic_history" in insights.get("sources", [])
        tag = " (synthetic demo history)" if synthetic else ""
        res = meko_memory.save_learnings(dp, [p + tag for p in prefs], kind="posting_pattern", title=f"Posting patterns · {brand.name}", brand=brand.name)
        if res:
            _save(session, brand, posting_hash=h, posting_patterns_saved=len(prefs), last_posting_learning_at=_now())


def analyze_brand_posts(session: Session, brand_id: int) -> dict:
    from sqlmodel import select
    from ..models import Campaign, Concept, SocialPost
    from . import posting_insights as pi

    rows = session.exec(select(SocialPost, Concept.concept_type).join(Concept, Concept.id == SocialPost.concept_id)
                        .join(Campaign, Campaign.id == SocialPost.campaign_id)
                        .where(Campaign.brand_id == brand_id, SocialPost.status == "published")).all()
    posts = [{"platform": p.platform, "published_at": p.published_at, "text": p.text, "concept_type": ct,
              "metrics": p.metrics or {}, "metrics_source": p.metrics_source} for p, ct in rows]
    return pi.analyze(posts)
