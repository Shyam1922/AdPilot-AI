"""A small, transparent model that learns which creative traits and trends actually move the metric.

Two parts, both explainable on one slide:

1. Trait effects (empirical-Bayes beta-binomial). Every ad is described by traits: angle (concept type), audience
   segment, layout, hook style, CTA. For each trait value we pool clicks / impressions over every ad that has it and
   compute a posterior rate. The prior is centred on the campaign's overall rate with a fixed strength, so small
   samples are pulled toward the average instead of producing wild lifts. We report the lift against the overall rate
   and P(better than overall) from posterior draws. The next batch uses these to choose a layout and an audience.
2. Daily trend (weighted least squares). For each ad we fit rate ~ day, weighted by impressions, and report whether it
   is rising, flat or fading (creative fatigue) only when the slope is clearly away from zero.

It is observational data: effects are associations, not proof of cause. Nothing here needs a GPU or a download.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

PRIOR_STRENGTH = 60          # pseudo-impressions that pull small samples toward the overall rate
DRAWS = 2000
OVERDISPERSION = 8          # ads of the same trait differ for other reasons, so count each impression as 1/8 of evidence
MIN_DAYS = 5
_URGENT = ("now", "today", "last", "only", "limited", "hurry", "sale", "off", "free", "ends")


def hook_style(hook: str) -> str:
    h = (hook or "").lower()
    if "?" in h:
        return "question"
    if any(ch.isdigit() for ch in h):
        return "number"
    if any(f" {w} " in f" {h} " or h.startswith(w + " ") for w in _URGENT):
        return "urgency"
    return "statement"


def traits(c) -> dict[str, str]:
    vb = c.visual_brief or {}
    return {"angle": c.concept_type, "audience": c.target_segment or "all", "layout": str(vb.get("layout") or "hero"),
            "hook style": hook_style(c.hook), "CTA": (c.cta or "").strip().lower()[:24] or "none"}


def _counts(metric: str, a: dict) -> tuple[int, int, str]:
    """(successes, trials, label) for the metric the campaign optimises. Cost metrics fall back to CTR."""
    if metric == "cvr" and a.get("clicks"):
        return int(a["conversions"]), int(a["clicks"]), "CVR"
    return int(a["clicks"]), int(a["impressions"]), "CTR"


def _quantile(xs: list[float], q: float) -> float:
    return xs[min(len(xs) - 1, max(0, int(q * len(xs))))]


def trait_effects(per: dict, concepts: dict, metric: str) -> tuple[list[dict], str]:
    rows = [(cid, *_counts(metric, a)) for cid, a in per.items() if cid in concepts]
    label = _counts(metric, next(iter(per.values())))[2] if per else "CTR"
    total_s = sum(r[1] for r in rows)
    total_n = sum(r[2] for r in rows)
    if total_n <= 0:
        return [], label
    overall = total_s / total_n
    a0, b0 = overall * PRIOR_STRENGTH, (1 - overall) * PRIOR_STRENGTH
    groups: dict[tuple[str, str], list[tuple[int, int, int]]] = defaultdict(list)
    for cid, s, n, _lab in rows:
        for k, v in traits(concepts[cid]).items():
            groups[(k, v)].append((cid, s, n))
    rng = random.Random(7)
    out = []
    for (k, v), items in groups.items():
        s, n = sum(i[1] for i in items), sum(i[2] for i in items)
        a, b = a0 + s / OVERDISPERSION, b0 + (n - s) / OVERDISPERSION
        draws = sorted(rng.betavariate(a, b) for _ in range(DRAWS))
        mean = a / (a + b)
        out.append({"trait": k, "value": v, "ads": len(items), "trials": n, "rate": mean,
                    "ci_low": _quantile(draws, 0.05), "ci_high": _quantile(draws, 0.95),
                    "lift": mean / overall - 1 if overall else 0.0,
                    "p_better": sum(1 for d in draws if d > overall) / DRAWS})
    out.sort(key=lambda r: -r["p_better"])
    return out, label


def trends(rows: list, concepts: dict, metric: str) -> list[dict]:
    by: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    for r in rows:
        if r.concept_id in concepts and r.day:
            d = by[r.concept_id][r.day]
            d[0] += r.clicks if metric != "cvr" else r.conversions
            d[1] += r.impressions if metric != "cvr" else r.clicks
    out = []
    for cid, days in by.items():
        pts = sorted((day, s, n) for day, (s, n, _) in days.items() if n > 0)
        if len(pts) < MIN_DAYS:
            continue
        xs = list(range(len(pts)))
        ys = [s / n for _, s, n in pts]
        ws = [n for _, _, n in pts]
        wm = sum(ws) / len(ws)
        w = [x / wm for x in ws]                                   # weights with mean 1
        sw = sum(w)
        xb = sum(wi * x for wi, x in zip(w, xs)) / sw
        yb = sum(wi * y for wi, y in zip(w, ys)) / sw
        sxx = sum(wi * (x - xb) ** 2 for wi, x in zip(w, xs))
        if sxx <= 0:
            continue
        slope = sum(wi * (x - xb) * (y - yb) for wi, x, y in zip(w, xs, ys)) / sxx
        resid = sum(wi * (y - (yb + slope * (x - xb))) ** 2 for wi, x, y in zip(w, xs, ys))
        se = math.sqrt(resid / max(1, len(pts) - 2) / sxx)
        z = slope / se if se > 0 else 0.0
        verdict = "rising" if z > 2 else "fading" if z < -2 else "flat"
        c = concepts[cid]
        out.append({"concept_id": cid, "label": f"#{cid} {c.concept_type}", "days": len(pts),
                    "slope_per_day": slope, "z": z, "verdict": verdict,
                    "first": ys[0], "last": ys[-1]})
    out.sort(key=lambda r: r["z"])
    return out


def best_value(effects: list[dict], trait: str, exclude: str = "", min_p: float = 0.6) -> str | None:
    """The trait value with the highest posterior rate, if the model is reasonably sure it beats the average."""
    cands = [e for e in effects if e["trait"] == trait and e["value"] != exclude and e["p_better"] >= min_p]
    return max(cands, key=lambda e: e["rate"])["value"] if cands else None


def pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def analyse(per: dict, rows: list, concepts: dict, metric: str) -> dict:
    effects, label = trait_effects(per, concepts, metric)
    tr = trends(rows, concepts, metric)
    notes: list[str] = []
    if effects:
        strong = [e for e in effects if e["ads"] >= 2 and e["trials"] >= 500]
        up = [e for e in strong if e["p_better"] >= 0.8][:2]
        down = [e for e in sorted(strong, key=lambda r: r["p_better"]) if e["p_better"] <= 0.2][:1]
        for e in up:
            notes.append(f"{e['trait'].capitalize()} \"{e['value']}\" is {e['lift'] * 100:+.0f}% vs the campaign average "
                         f"on {label} ({pct(e['rate'])}, P(better) {e['p_better'] * 100:.0f}%, {e['ads']} ads).")
        for e in down:
            notes.append(f"{e['trait'].capitalize()} \"{e['value']}\" trails the average ({e['lift'] * 100:+.0f}% on {label}, "
                         f"P(better) {e['p_better'] * 100:.0f}%).")
    for t in tr:
        if t["verdict"] != "flat":
            notes.append(f"{t['label']} is {t['verdict']}: {label} moved from {pct(t['first'])} to {pct(t['last'])} "
                         f"over {t['days']} days.")
    if not notes:
        notes.append("No trait or trend is clearly separated from the average yet; more delivery is needed.")
    return {"metric_label": label, "effects": effects[:14], "trends": tr[:8], "notes": notes[:5],
            "method": (f"Empirical-Bayes beta-binomial over ad traits (prior strength {PRIOR_STRENGTH}, evidence discounted "
                       f"{OVERDISPERSION}x for ad-to-ad noise) plus a "
                       "weighted linear trend per ad. Association in observed data, not proof of cause.")}
