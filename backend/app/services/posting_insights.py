"""What does this brand's audience respond to, and when? Learned from the brand's own posting history.

Pure functions over SocialPost rows. The result feeds three places: the "best time to post" chips in the UI,
the prompt for the next batch of posts, and Meko (so the learning outlives this app's database).
Always labelled with where the numbers came from (real/manual, simulated, or synthetic demo history).
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAYPARTS = [("early morning", 5, 8), ("morning", 8, 12), ("afternoon", 12, 17), ("evening", 17, 21), ("night", 21, 29)]
DEFAULT_SLOTS = {   # generic starting points, only used when a brand has no history yet
    "linkedin": (1, 10), "instagram": (3, 19), "x": (2, 9),
}
MIN_POSTS_CONFIDENT = 3


def as_ist(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def daypart(hour: int) -> str:
    h = hour if hour >= 5 else hour + 24
    for name, lo, hi in DAYPARTS:
        if lo <= h < hi:
            return name
    return "night"


def engagement(m: dict) -> int:
    return int(m.get("likes", 0)) + 2 * int(m.get("comments", 0)) + 3 * int(m.get("shares", 0)) + int(m.get("clicks", 0))


def rate(m: dict) -> float:
    imp = int(m.get("impressions", 0))
    return engagement(m) / imp if imp else 0.0


def _style(text: str) -> str:
    first = (text or "").strip().split("\n")[0]
    return "question hook" if first.endswith("?") else "statement hook"


def _length(text: str, platform: str) -> str:
    n = len(text or "")
    lo, hi = {"x": (100, 200), "instagram": (250, 450), "linkedin": (500, 900)}.get(platform, (200, 500))
    return "short" if n < lo else "long" if n > hi else "medium"


def _next_at(now: datetime, wd: int, hr: int) -> str:
    t = as_ist(now).replace(minute=0, second=0, microsecond=0, hour=hr)
    t += timedelta(days=(wd - t.weekday()) % 7)
    if t <= as_ist(now):
        t += timedelta(days=7)
    return t.astimezone(timezone.utc).isoformat()


def _conf(n: int) -> str:
    return "confident" if n >= 6 else "early signal" if n >= MIN_POSTS_CONFIDENT else "too few posts"


def analyze(posts: list[dict], now: datetime | None = None) -> dict:
    """posts: [{platform, published_at, text, concept_type, metrics, metrics_source}] (only published ones with metrics)."""
    now = now or datetime.now(timezone.utc)
    rows = [p for p in posts if p.get("published_at") and p.get("metrics") and int(p["metrics"].get("impressions", 0)) > 0]
    sources = sorted({p.get("metrics_source") or "manual" for p in rows})
    out: dict = {"posts_analyzed": len(rows), "sources": sources, "platforms": {}, "content": {}, "preferences": [],
                 "next_slots": {}, "basis": "history" if rows else "default"}

    by_plat: dict[str, list[dict]] = defaultdict(list)
    for p in rows:
        by_plat[p["platform"]].append(p)

    overall = sum(rate(p["metrics"]) for p in rows) / len(rows) if rows else 0.0
    out["avg_engagement_rate"] = round(overall, 4)

    for plat in ("linkedin", "instagram", "x"):
        ps = by_plat.get(plat, [])
        if not ps:
            wd, hr = DEFAULT_SLOTS[plat]
            out["platforms"][plat] = {"posts": 0, "avg_rate": 0.0, "best_slots": [
                {"weekday": WD[wd], "hour": hr, "daypart": daypart(hr), "rate": None, "n": 0,
                 "confidence": "general default (no history yet)"}], "heatmap": []}
            out["next_slots"][plat] = {"at": _next_at(now, wd, hr), "label": f"{WD[wd]} {hr:02d}:00 IST",
                                       "reason": "General default; post a few and AdPilot will learn your best time"}
            continue
        avg = sum(rate(p["metrics"]) for p in ps) / len(ps)
        cells: dict[tuple[int, str], list[float]] = defaultdict(list)
        hours: dict[tuple[int, str], list[int]] = defaultdict(list)
        for p in ps:
            t = as_ist(p["published_at"])
            k = (t.weekday(), daypart(t.hour))
            cells[k].append(rate(p["metrics"]))
            hours[k].append(t.hour)
        # shrink small cells toward the platform average so one lucky post doesn't win
        scored = []
        for (wd, dp), rs in cells.items():
            n = len(rs)
            shrunk = (sum(rs) + 2 * avg) / (n + 2)
            hr = sorted(hours[(wd, dp)])[len(hours[(wd, dp)]) // 2]
            scored.append({"weekday": WD[wd], "wd": wd, "hour": hr, "daypart": dp, "rate": round(shrunk, 4),
                           "raw_rate": round(sum(rs) / n, 4), "n": n, "confidence": _conf(n)})
        scored.sort(key=lambda x: (-x["rate"], -x["n"]))
        best = [s for s in scored if s["n"] >= 2][:3] or scored[:3]
        heat = [[round(sum(cells[(d, dp[0])]) / len(cells[(d, dp[0])]), 4) if cells.get((d, dp[0])) else None
                 for dp in DAYPARTS] for d in range(7)]
        out["platforms"][plat] = {"posts": len(ps), "avg_rate": round(avg, 4), "best_slots": best, "heatmap": heat,
                                  "dayparts": [d[0] for d in DAYPARTS]}
        if best and avg > 0:
            b = best[0]
            lift = b["rate"] / avg
            out["preferences"].append(
                f"{plat.capitalize()}: posts perform best {b['weekday']} {b['daypart']} (~{b['hour']}:00 IST), "
                f"{b['rate']*100:.1f}% engagement vs {avg*100:.1f}% average ({lift:.1f}x, {b['n']} posts, {b['confidence']}).")
        # next occurrence of the best slot
        slot = best[0]
        wd, hr = WD.index(slot["weekday"]), int(slot["hour"])
        out["next_slots"][plat] = {"at": _next_at(now, wd, hr), "label": f"{WD[wd]} {hr:02d}:00 IST",
                                   "reason": f"Based on {len(ps)} past {plat} posts"}

    # content patterns across all platforms
    def group(keyf) -> list[dict]:
        g: dict[str, list[float]] = defaultdict(list)
        for p in rows:
            g[keyf(p)].append(rate(p["metrics"]))
        res = [{"label": k, "rate": round(sum(v) / len(v), 4), "n": len(v)} for k, v in g.items() if v]
        return sorted(res, key=lambda x: -x["rate"])

    out["content"] = {
        "by_concept_type": group(lambda p: p.get("concept_type") or "unknown"),
        "by_hook_style": group(lambda p: _style(p.get("text", ""))),
        "by_length": group(lambda p: _length(p.get("text", ""), p["platform"])),
    }
    for key, noun in (("by_concept_type", "concept angle"), ("by_hook_style", "opening style"), ("by_length", "post length")):
        g = [x for x in out["content"][key] if x["n"] >= MIN_POSTS_CONFIDENT]
        if len(g) >= 2 and overall > 0 and g[0]["rate"] > g[-1]["rate"] * 1.15:
            out["preferences"].append(
                f"The audience responds most to the '{g[0]['label']}' {noun} ({g[0]['rate']*100:.1f}% vs "
                f"{g[-1]['rate']*100:.1f}% for '{g[-1]['label']}', {g[0]['n']} vs {g[-1]['n']} posts).")
    return out


def digest(insights: dict) -> str:
    """Stable hash of the preferences, so we only write to Meko when something actually changed."""
    return hashlib.sha1(json.dumps(insights.get("preferences", []), sort_keys=True).encode()).hexdigest()[:12]


def prompt_context(insights: dict) -> str:
    """Short text for the post-writing prompt."""
    if not insights.get("preferences"):
        return ""
    return "Posting history for this brand (from its own results; follow it where it fits):\n- " + "\n- ".join(insights["preferences"][:6])
