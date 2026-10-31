"""Iteration policy: turn ranked performance into the next batch of controlled experiments.

Rules (transparent on purpose, no black box):
  * ~75% exploit: children of the best 1-2 concepts, each changing only 1-2 variables
    (hook, CTA+headline, layout, segment) so a difference can be attributed to that change.
  * ~25% explore: the least-tested concept gets a new hook for a different segment, so the
    system doesn't only repeat one idea.
  * Every variant stores parent, changed variables and a rationale citing the numbers.
  * Limitations are always returned: data source, sample size, correlation is not causation.
"""
from __future__ import annotations

from .concept_ranker import AWARENESS_NOTE, METRIC_NOTE, clear_winner

STATUS_WORDS = {"insufficient_data": "insufficient data", "early_signal": "early signal", "directional": "directional"}
LAYOUTS = ["hero", "split", "bold", "minimal"]


def pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.2f}%"


def describe(r: dict, c, metric: str) -> str:
    unit = "impressions" if metric == "ctr" else "clicks"
    return (f"#{c.id} {c.concept_type} at {metric.upper()} {pct(r['primary_value'])} "
            f"(95% CI {pct(r['ci_low'])}–{pct(r['ci_high'])}, n={r['trials']:,} {unit}, "
            f"{STATUS_WORDS[r['sample_status']]})")


def plan(ranked: list[dict], concepts: dict, metric: str, batch_size: int = 4) -> list[dict]:
    measured = [r for r in ranked if r["primary_value"] is not None and r["concept_id"] in concepts]
    if not measured:
        return []
    batch_size = max(2, min(batch_size, 8))
    n_explore = max(1, round(batch_size * 0.25))
    n_exploit = batch_size - n_explore
    top = measured[:2]
    exploit_moves = [(top[0], ["hook"]), (top[0], ["cta", "headline"]),
                     (top[1] if len(top) > 1 else top[0], ["hook"]), (top[0], ["layout"]),
                     (top[1] if len(top) > 1 else top[0], ["cta", "headline"]), (top[0], ["segment"])]
    specs = []
    for r, changes in exploit_moves[:n_exploit]:
        c = concepts[r["concept_id"]]
        specs.append({"parent_id": c.id, "changes": changes, "is_exploration": False,
                      "rationale": f"Builds on {describe(r, c, metric)}. Changes only the {' and '.join(changes)} "
                                   f"so any difference can be attributed to that change."})
    least = sorted(measured, key=lambda r: r["trials"])
    for r in least[:n_explore]:
        c = concepts[r["concept_id"]]
        specs.append({"parent_id": c.id, "changes": ["hook", "segment"], "is_exploration": True,
                      "rationale": f"Exploration: {describe(r, c, metric)} has the least data, so it gets a new "
                                   f"hook for a different audience segment instead of being dropped early."})
    return specs


def summary(ranked: list[dict], concepts: dict, metric: str, objective: str) -> tuple[str, list[dict]]:
    measured = [r for r in ranked if r["primary_value"] is not None and r["concept_id"] in concepts]
    if not measured:
        return "No measurable results yet.", []
    lead, last = measured[0], measured[-1]
    lc, wc = concepts[lead["concept_id"]], concepts[last["concept_id"]]
    parts = [f"Leader on {metric.upper()}: {describe(lead, lc, metric)}."]
    if len(measured) > 1:
        rc = concepts[measured[1]["concept_id"]]
        if clear_winner(measured):
            parts.append(f"Its interval does not overlap the runner-up (#{rc.id} {rc.concept_type}), "
                         f"so the lead holds in this data.")
        else:
            parts.append(f"Its interval overlaps the runner-up (#{rc.id} {rc.concept_type}), "
                         f"so it is not a confirmed winner yet.")
        parts.append(f"Lowest: {describe(last, wc, metric)}.")
    parts.append("The next batch keeps most variants close to what is working and reserves one for exploration.")
    signals = [{"concept_id": r["concept_id"],
                "signal": f"{metric.upper()} {pct(r['primary_value'])}, P(best) {r['p_best'] * 100:.0f}%, "
                          f"{STATUS_WORDS[r['sample_status']]}"} for r in measured]
    if objective == "awareness":
        parts.append(AWARENESS_NOTE)
    return " ".join(parts), signals


def limitations(sources: list[str], ranked: list[dict], metric: str) -> list[str]:
    out = []
    if "simulated" in sources:
        out.append("These metrics are SIMULATED sample data for the demo. They are not real campaign results.")
    if any(s.startswith("imported_csv") for s in sources):
        out.append("Imported CSV data is only as accurate as the export it came from.")
    statuses = {r["sample_status"] for r in ranked}
    if "insufficient_data" in statuses:
        out.append("Some concepts have too little data to judge; their ranks can change a lot with more delivery.")
    if "early_signal" in statuses:
        out.append("Several results are early signals; wait for more data before cutting budget.")
    out.append("This is observational data: a higher rate is correlation, not proof that the creative caused it "
               "(audience, timing and delivery also differ).")
    out.append("Ranked by " + METRIC_NOTE[metric][0].lower() + METRIC_NOTE[metric][1:])
    return out


def learnings(ranked: list[dict], concepts: dict, metric: str, sources: list[str]) -> list[str]:
    measured = [r for r in ranked if r["primary_value"] is not None and r["concept_id"] in concepts]
    if len(measured) < 2:
        return []
    src = "simulated" if "simulated" in sources else "imported"
    lead, last = measured[0], measured[-1]
    lc, wc = concepts[lead["concept_id"]], concepts[last["concept_id"]]
    return [
        f"{lc.concept_type.capitalize()} angle led on {metric.upper()} ({pct(lead['primary_value'])}, "
        f"{STATUS_WORDS[lead['sample_status']]}, {src} data) with hook \"{lc.hook.rstrip('.')}\". Treat as a hypothesis to keep testing.",
        f"{wc.concept_type.capitalize()} angle was lowest on {metric.upper()} ({pct(last['primary_value'])}, "
        f"{STATUS_WORDS[last['sample_status']]}, {src} data). Try a new hook before dropping it.",
    ]


def next_layout(current: str) -> str:
    i = LAYOUTS.index(current) if current in LAYOUTS else 0
    return LAYOUTS[(i + 1) % len(LAYOUTS)]
