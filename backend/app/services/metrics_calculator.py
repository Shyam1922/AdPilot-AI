"""Deterministic campaign metrics. All arithmetic lives here; the LLM never computes numbers.

Undefined rates (zero denominator) are None, never 0, so the UI shows "—".
Every row keeps its source_type: simulated | imported_csv | api:<provider>.
"""
from __future__ import annotations

import csv
import io
import random
import re
from collections import defaultdict
from datetime import date, timedelta


def safe_div(a: float, b: float) -> float | None:
    return a / b if b else None


def rates(impressions: int, clicks: int, conversions: int, spend: float, revenue: float | None) -> dict:
    return {
        "ctr": safe_div(clicks, impressions),
        "cvr": safe_div(conversions, clicks),
        "cpc": safe_div(spend, clicks),
        "cpa": safe_div(spend, conversions),
        "roas": safe_div(revenue, spend) if revenue is not None else None,
    }


def aggregate(rows: list) -> dict[int, dict]:
    """rows: MetricSnapshot-like objects. Returns {concept_id: totals + rates}."""
    acc: dict[int, dict] = defaultdict(lambda: {"impressions": 0, "clicks": 0, "conversions": 0, "spend": 0.0,
                                                "revenue": None, "sources": set()})
    for r in rows:
        a = acc[r.concept_id]
        a["impressions"] += r.impressions
        a["clicks"] += r.clicks
        a["conversions"] += r.conversions
        a["spend"] += r.spend
        if r.revenue is not None:
            a["revenue"] = (a["revenue"] or 0.0) + r.revenue
        a["sources"].add(r.source_type)
    out = {}
    for cid, a in acc.items():
        out[cid] = {**{k: v for k, v in a.items() if k != "sources"}, "spend": round(a["spend"], 2),
                    "revenue": round(a["revenue"], 2) if a["revenue"] is not None else None,
                    "sources": sorted(a["sources"]),
                    **rates(a["impressions"], a["clicks"], a["conversions"], a["spend"], a["revenue"])}
    return out


def totals(per_concept: dict[int, dict]) -> dict:
    t = {"impressions": 0, "clicks": 0, "conversions": 0, "spend": 0.0, "revenue": None}
    for a in per_concept.values():
        for k in ("impressions", "clicks", "conversions", "spend"):
            t[k] += a[k]
        if a["revenue"] is not None:
            t["revenue"] = (t["revenue"] or 0.0) + a["revenue"]
    t["spend"] = round(t["spend"], 2)
    if t["revenue"] is not None:
        t["revenue"] = round(t["revenue"], 2)
    return {**t, **rates(t["impressions"], t["clicks"], t["conversions"], t["spend"], t["revenue"])}


def daily(rows: list) -> list[dict]:
    acc: dict[str, dict] = defaultdict(lambda: {"impressions": 0, "clicks": 0, "conversions": 0, "spend": 0.0})
    for r in rows:
        d = acc[r.day]
        d["impressions"] += r.impressions
        d["clicks"] += r.clicks
        d["conversions"] += r.conversions
        d["spend"] += r.spend
    return [{"day": k, **{**v, "spend": round(v["spend"], 2)}} for k, v in sorted(acc.items())]


# --------------------------------------------------------------------------- simulated data
# Plausible, clearly fake baselines by concept type. They exist so the demo has numbers to
# analyse; they are NOT benchmarks and are always labelled source_type="simulated".
SIM_BASE = {
    "problem": (0.016, 0.034), "demo": (0.012, 0.040), "storytelling": (0.009, 0.026),
    "offer": (0.014, 0.044), "testimonial-style": (0.011, 0.030),
}


def parse_price(price: str | None) -> float | None:
    if not price:
        return None
    m = re.search(r"\d[\d,]*(?:\.\d+)?", price)
    return float(m.group(0).replace(",", "")) if m else None


def simulate(concepts: list, days: int = 7, seed: int = 42, aov: float | None = None,
             start: date | None = None) -> list[dict]:
    """Deterministic sample performance per concept/day. Variants get less delivery (they're newer)."""
    start = start or (date.today() - timedelta(days=days))
    aov = aov or 799.0
    rows = []
    for c in concepts:
        rng = random.Random(f"{seed}-{c.id}")
        ctr0, cvr0 = SIM_BASE.get(c.concept_type, (0.011, 0.03))
        lift = 1 + rng.uniform(-0.18, 0.18)
        daily_imps = rng.randint(1800, 4200) if c.parent_concept_id is None else rng.randint(500, 1400)
        if c.is_exploration:
            daily_imps = rng.randint(250, 700)
        for d in range(days):
            imps = max(0, int(daily_imps * (1 + rng.gauss(0, 0.12))))
            clicks = max(0, int(round(imps * ctr0 * lift * (1 + rng.gauss(0, 0.15)))))
            conv = max(0, int(round(clicks * cvr0 * lift * (1 + rng.gauss(0, 0.35)))))
            spend = round(imps / 1000 * rng.uniform(140, 210), 2)   # ₹ CPM
            rows.append({"concept_id": c.id, "platform": "meta", "day": (start + timedelta(days=d)).isoformat(),
                         "impressions": imps, "clicks": clicks, "conversions": conv, "spend": spend,
                         "revenue": round(conv * aov, 2), "source_type": "simulated"})
    return rows


# --------------------------------------------------------------------------- CSV import
CSV_COLUMNS = ["concept_id", "day", "platform", "impressions", "clicks", "conversions", "spend", "revenue"]


def parse_csv(text: str, valid_concept_ids: set[int]) -> tuple[list[dict], list[str]]:
    rows, errors = [], []
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    missing = [c for c in CSV_COLUMNS[:7] if c not in (reader.fieldnames or [])]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Expected: {', '.join(CSV_COLUMNS)}"]
    for i, r in enumerate(reader, start=2):
        try:
            cid = int(r["concept_id"])
            if cid not in valid_concept_ids:
                raise ValueError(f"concept_id {cid} is not in this campaign")
            date.fromisoformat(r["day"].strip())
            imps, clicks, conv = int(r["impressions"]), int(r["clicks"]), int(r["conversions"])
            spend = float(r["spend"])
            rev = float(r["revenue"]) if (r.get("revenue") or "").strip() else None
            if min(imps, clicks, conv) < 0 or spend < 0 or clicks > imps or conv > clicks:
                raise ValueError("counts must be non-negative, clicks ≤ impressions, conversions ≤ clicks")
            rows.append({"concept_id": cid, "day": r["day"].strip(), "platform": (r["platform"] or "unknown").strip(),
                         "impressions": imps, "clicks": clicks, "conversions": conv, "spend": spend,
                         "revenue": rev, "source_type": "imported_csv"})
        except (ValueError, KeyError, TypeError) as exc:
            errors.append(f"Row {i}: {exc}")
    return rows, errors
