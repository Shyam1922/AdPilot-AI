"""Analytics + Optimization endpoints: metrics in (simulated or CSV), analysis out, next variants created."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, delete, select

from ..db import get_session
from ..models import Campaign, Concept, Iteration, MetricSnapshot
from ..serializers import iteration_out
from ..services import ad_generator, concept_ranker, iteration_policy, metrics_calculator, trend_model
from ..services.meko_sync import save_learnings_job
from .common import audit, brand_context, get_or_404, guardrail_list, touch

router = APIRouter(tags=["analytics"])


class SimulateRequest(BaseModel):
    days: int = 7
    seed: int = 42


def _concepts(session: Session, campaign_id: int) -> list[Concept]:
    return session.exec(select(Concept).where(Concept.campaign_id == campaign_id).order_by(Concept.id)).all()


@router.post("/campaigns/{campaign_id}/metrics/simulate")
def simulate_metrics(campaign_id: int, req: SimulateRequest = SimulateRequest(),
                     session: Session = Depends(get_session)) -> dict:
    camp = get_or_404(session, Campaign, campaign_id)
    brand, profile, _ = brand_context(session, camp)
    concepts = _concepts(session, camp.id)
    if not concepts:
        raise HTTPException(409, "Generate concepts before adding metrics.")
    prod = next((p for p in profile.products if p.name.lower() == (camp.product_focus or "").lower()), None)
    rows = metrics_calculator.simulate(concepts, max(1, min(req.days, 30)), req.seed,
                                       aov=metrics_calculator.parse_price(prod.price if prod else None))
    session.exec(delete(MetricSnapshot).where(MetricSnapshot.campaign_id == camp.id,
                                              MetricSnapshot.source_type == "simulated"))
    for r in rows:
        session.add(MetricSnapshot(campaign_id=camp.id, **r))
    audit(session, "campaign", camp.id, "metrics_simulated", rows=len(rows))
    session.commit()
    return {"rows_saved": len(rows), "source_type": "simulated"}


@router.post("/campaigns/{campaign_id}/metrics")
async def import_metrics(campaign_id: int, file: UploadFile = File(...),
                         session: Session = Depends(get_session)) -> dict:
    camp = get_or_404(session, Campaign, campaign_id)
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "CSV is larger than 5 MB.")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "Upload a UTF-8 CSV file.")
    ids = {c.id for c in _concepts(session, camp.id)}
    rows, errors = metrics_calculator.parse_csv(text, ids)
    for r in rows:
        session.add(MetricSnapshot(campaign_id=camp.id, **r))
    audit(session, "campaign", camp.id, "metrics_imported", rows=len(rows), errors=len(errors))
    session.commit()
    return {"rows_saved": len(rows), "source_type": "imported_csv", "errors": errors[:50]}


def _analysis(session: Session, camp: Campaign):
    rows = session.exec(select(MetricSnapshot).where(MetricSnapshot.campaign_id == camp.id)).all()
    concepts = {c.id: c for c in _concepts(session, camp.id)}
    per = metrics_calculator.aggregate(rows)
    metric = concept_ranker.OBJECTIVE_METRIC.get(camp.objective, "ctr")
    ranked = concept_ranker.rank(per, metric)
    sources = sorted({r.source_type for r in rows})
    return rows, concepts, per, metric, ranked, sources


@router.get("/campaigns/{campaign_id}/analytics")
def analytics(campaign_id: int, session: Session = Depends(get_session)) -> dict:
    camp = get_or_404(session, Campaign, campaign_id)
    rows, concepts, per, metric, ranked, sources = _analysis(session, camp)
    by_rank = {r["concept_id"]: r for r in ranked}
    by_concept = []
    for cid, a in per.items():
        c, r = concepts.get(cid), by_rank.get(cid, {})
        if c is None:
            continue
        by_concept.append({
            "concept_id": cid, "label": f"#{cid} {c.concept_type}", "concept_type": c.concept_type,
            "is_exploration": c.is_exploration, "parent_concept_id": c.parent_concept_id, "hook": c.hook,
            **{k: a[k] for k in ("impressions", "clicks", "conversions", "spend", "revenue",
                                 "ctr", "cvr", "cpc", "cpa", "roas")},
            "primary_value": r.get("primary_value"), "ci_low": r.get("ci_low"), "ci_high": r.get("ci_high"),
            "sample_status": r.get("sample_status"), "p_best": r.get("p_best"), "rank": r.get("rank"),
        })
    by_concept.sort(key=lambda x: x["rank"] or 999)
    warnings = []
    if "simulated" in sources:
        warnings.append("SIMULATED DATA: sample numbers for the demo, not real campaign results.")
    if not rows:
        warnings.append("No metrics yet. Load simulated data or upload a CSV.")
    note = concept_ranker.METRIC_NOTE[metric] + (" " + concept_ranker.AWARENESS_NOTE if camp.objective == "awareness" else "")
    return {
        "campaign_id": camp.id, "objective": camp.objective, "objective_metric": metric, "objective_metric_note": note,
        "is_simulated": "simulated" in sources, "data_sources": sources,
        "totals": metrics_calculator.totals(per), "by_concept": by_concept,
        "daily": metrics_calculator.daily(rows), "clear_winner": concept_ranker.clear_winner(ranked),
        "model": trend_model.analyse(per, rows, concepts, metric) if rows else None,
        "warnings": warnings,
    }


class IterateRequest(BaseModel):
    batch_size: int = 4


@router.post("/campaigns/{campaign_id}/iterate")
def iterate(campaign_id: int, background: BackgroundTasks, req: IterateRequest = IterateRequest(),
            session: Session = Depends(get_session)) -> dict:
    camp = get_or_404(session, Campaign, campaign_id)
    rows, concepts, per, metric, ranked, sources = _analysis(session, camp)
    if not rows:
        raise HTTPException(409, "No metrics yet. Load simulated data or upload a CSV first.")
    brand, profile, strategy = brand_context(session, camp)
    specs = iteration_policy.plan(ranked, concepts, metric, req.batch_size)
    insight, signals = iteration_policy.summary(ranked, concepts, metric, camp.objective)
    limits = iteration_policy.limitations(sources, ranked, metric)

    it = Iteration(campaign_id=camp.id, objective_metric=metric, insight_summary=insight,
                   ranking=[{k: r[k] for k in ("concept_id", "rank", "primary_value", "ci_low", "ci_high",
                                               "p_best", "sample_status", "trials")} for r in ranked],
                   selected_signals=signals, limitations=limits, data_sources=sources, generation_mode="rules")
    session.add(it)
    session.commit()
    session.refresh(it)

    model = trend_model.analyse(per, rows, concepts, metric)       # what the data says about layouts and audiences
    segments = [s.name for s in strategy.segments] or [concepts[next(iter(concepts))].target_segment]
    modes = set()
    for spec in specs:
        parent = concepts[spec["parent_id"]]
        d = {k: getattr(parent, k) for k in ("concept_type", "target_segment", "angle", "hook", "primary_text",
                                             "headline", "cta", "visual_brief", "platform_copy", "video_script",
                                             "claim_sources", "risk_flags", "rationale")}
        for change in spec["changes"]:
            if change in ("hook", "headline", "cta", "primary_text"):
                d, mode = ad_generator.regenerate_field(d, change, profile, strategy, camp.product_focus,
                                                        guardrail_list(brand), brand.sources)
                modes.add(mode)
            elif change == "layout":
                cur = d["visual_brief"].get("layout", "hero")
                learned = trend_model.best_value(model["effects"], "layout", exclude=cur)
                d["visual_brief"] = {**d["visual_brief"], "layout": learned or iteration_policy.next_layout(cur)}
            elif change == "segment":
                others = [s for s in segments if s != d["target_segment"]]
                learned = trend_model.best_value(model["effects"], "audience", exclude=d["target_segment"])
                if learned in others:
                    d["target_segment"] = learned
                elif others:
                    d["target_segment"] = others[0]
        session.add(Concept(
            campaign_id=camp.id, iteration_id=it.id, parent_concept_id=parent.id,
            **{k: d[k] for k in ("concept_type", "target_segment", "angle", "hook", "primary_text", "headline",
                                 "cta", "visual_brief", "platform_copy", "video_script", "claim_sources", "risk_flags")},
            changed_variables=spec["changes"], rationale=spec["rationale"], is_exploration=spec["is_exploration"],
            status="generated", generation_mode=d.get("generation_mode", "offline"),
            prompt_version=ad_generator.PROMPT_VERSION))
    ai_modes = sorted(m for m in modes if m != "offline")
    it.generation_mode = "rules+" + (ai_modes[0] if ai_modes else "offline")
    session.add(it)

    # Brand Memory learns (locally, and in Meko via the analyst agent).
    new_learnings = iteration_policy.learnings(ranked, concepts, metric, sources) + [
        f"{n} ({'simulated' if 'simulated' in sources else 'imported'} data, association only)" for n in model["notes"][:2]
        if not n.startswith("No trait")]
    stamp = datetime.now(timezone.utc).isoformat()
    brand.learnings = [*brand.learnings, *[{"text": t, "iteration_id": it.id, "data_source": sources[0] if sources else "",
                                           "created_at": stamp} for t in new_learnings]][-30:]
    touch(brand)
    session.add(brand)
    audit(session, "campaign", camp.id, "iterated", iteration_id=it.id, variants=len(specs), metric=metric)
    session.commit()
    session.refresh(it)
    if new_learnings:
        background.add_task(save_learnings_job, brand.id, new_learnings)
    return iteration_out(session, it)
