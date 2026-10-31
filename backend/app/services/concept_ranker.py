"""Ranking with honest uncertainty: Wilson intervals, sample-size gates, Beta-Binomial P(best).

A "winner" is declared only when the leader's lower bound clears the runner-up's upper bound.
"""
from __future__ import annotations

import math

import numpy as np

OBJECTIVE_METRIC = {"sales": "cvr", "leads": "cvr", "traffic": "ctr", "engagement": "ctr", "launch": "ctr",
                    "awareness": "ctr"}
METRIC_NOTE = {
    "ctr": "Click-through rate (clicks ÷ impressions).",
    "cvr": "Conversion rate (conversions ÷ clicks), the metric that matches a sales/leads objective.",
}
AWARENESS_NOTE = "For awareness, CTR is used as an attention proxy; reach data would be better."

# Minimum evidence before we say anything (successes = clicks for CTR, conversions for CVR).
GATES = {"ctr": {"early": (500, 5), "directional": (3000, 20)},
         "cvr": {"early": (50, 5), "directional": (200, 20)}}


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def counts(perf: dict, metric: str) -> tuple[int, int]:
    """(successes, trials) for the metric."""
    if metric == "cvr":
        return perf["conversions"], perf["clicks"]
    return perf["clicks"], perf["impressions"]


def sample_status(metric: str, successes: int, n: int) -> str:
    g = GATES[metric]
    if n < g["early"][0] or successes < g["early"][1]:
        return "insufficient_data"
    if n < g["directional"][0] or successes < g["directional"][1]:
        return "early_signal"
    return "directional"


def p_best(items: list[tuple[int, int]], draws: int = 4000, seed: int = 7) -> list[float]:
    """Share of Beta(1+s, 1+n-s) posterior draws in which each item has the highest rate."""
    if not items:
        return []
    rng = np.random.default_rng(seed)
    samples = np.stack([rng.beta(1 + s, 1 + max(0, n - s), draws) for s, n in items])
    wins = np.bincount(samples.argmax(axis=0), minlength=len(items))
    return [round(float(w) / draws, 3) for w in wins]


def rank(per_concept: dict[int, dict], metric: str) -> list[dict]:
    ids = list(per_concept)
    cs = [counts(per_concept[i], metric) for i in ids]
    pb = p_best(cs)
    out = []
    for i, cid in enumerate(ids):
        s, n = cs[i]
        lo, hi = wilson(s, n)
        out.append({"concept_id": cid, "primary_value": (s / n) if n else None, "ci_low": lo, "ci_high": hi,
                    "successes": s, "trials": n, "sample_status": sample_status(metric, s, n), "p_best": pb[i]})
    out.sort(key=lambda r: (r["primary_value"] is not None, r["primary_value"] or 0), reverse=True)
    for k, r in enumerate(out, 1):
        r["rank"] = k
    return out


def clear_winner(ranked: list[dict]) -> bool:
    if len(ranked) < 2 or ranked[0]["ci_low"] is None or ranked[1]["ci_high"] is None:
        return False
    return ranked[0]["ci_low"] > ranked[1]["ci_high"] and ranked[0]["sample_status"] != "insufficient_data"
