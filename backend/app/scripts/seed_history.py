"""Seed three different brands with ~8 weeks of SYNTHETIC activity, so the demo shows an agent that has learned.

For each brand it builds, through the real API/services:
  Brand Memory -> 4 past campaigns (one every 2 weeks) -> concepts -> ad metrics -> optimization rounds
  -> 72 published posts across LinkedIn / Instagram / X with engagement that follows a hidden, brand-specific
  audience pattern (so the best-time and best-angle insights have something real to discover)
  -> a 5th, current campaign with approved posts scheduled at the learned best times.
When Meko is configured, everything is written to it too: brand facts, optimization learnings, posting
patterns and the activity log, so a new campaign recalls them.

EVERYTHING HERE IS SYNTHETIC and labelled so (metrics source "simulated" / "synthetic_history",
brand.integrations.synthetic_history). It exists to demonstrate the loop, not to claim real results.

Run (venv active, server can be running):
    python -m app.scripts.seed_history              # offline copy + Meko if MEKO_API_KEY is set
    python -m app.scripts.seed_history --no-meko    # skip Meko (fast)
    python -m app.scripts.seed_history --gemini     # use the AI provider chain for copy (slower)
"""
from __future__ import annotations

import io
import logging
import os
import random
import sys
from datetime import datetime, timedelta, timezone

if "--no-meko" in sys.argv:
    os.environ["MEKO_API_KEY"] = ""
if "--gemini" not in sys.argv:
    os.environ["LLM_PROVIDER"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Brand, Campaign, Concept, Iteration, MetricSnapshot, SocialPost  # noqa: E402
from app.scripts.reset_demo import wipe  # noqa: E402
from app.services import meko_memory, posting_insights as pi, social_posts  # noqa: E402
from app.services.meko_sync import analyze_brand_posts, datapack_for, save_posting_insights_job  # noqa: E402
from app.api.common import brand_context, guardrail_list  # noqa: E402

IST = pi.IST
WEEKS = 8
RNG = random.Random(2026)
PLATFORMS = ("linkedin", "instagram", "x")

# Each brand has a hidden audience: when it engages, and what it likes. The insights engine must DISCOVER this.
BRANDS = [
    {
        "key": "velvaa", "url": "https://demo.adpilot.local/", "manual": None, "color": None,
        "slots": {"instagram": [(3, 20), (6, 11)], "linkedin": [(1, 10)], "x": [(0, 9), (2, 9)]},
        "concept_lift": {"offer": 1.35, "demo": 1.25, "problem": 1.0, "storytelling": 0.8, "testimonial-style": 0.9},
        "question_lift": 1.3, "base_rate": {"instagram": 0.03, "linkedin": 0.02, "x": 0.013},
        "reach": {"instagram": 4200, "linkedin": 1300, "x": 900}, "growth": 0.5,
    },
    {
        "key": "brew", "url": None, "color": (92, 58, 36), "kind": "pouch",
        "manual": {
            "brand_name": "Brew & Bloom", "product_name": "Coorg Estate Medium Roast 250g",
            "product_description": "Single-origin Arabica from a family estate in Coorg, roasted in small batches and shipped within days of roasting.",
            "target_audience": "Urban coffee drinkers aged 22-38 who brew at home",
            "price_range": "₹449", "tone": "warm, unhurried, a little nerdy",
            "key_features": ["Single-origin Arabica from Coorg", "Small-batch roasted",
                             "Roasted to order and shipped within 3 days", "Resealable pouch with one-way valve"],
        },
        "slots": {"instagram": [(5, 9), (2, 18)], "linkedin": [(2, 8)], "x": [(0, 9), (4, 8)]},
        "concept_lift": {"storytelling": 1.4, "demo": 1.25, "problem": 0.95, "offer": 0.85, "testimonial-style": 0.8},
        "question_lift": 1.1, "base_rate": {"instagram": 0.033, "linkedin": 0.015, "x": 0.017},
        "reach": {"instagram": 3600, "linkedin": 900, "x": 1100}, "growth": 0.7,
    },
    {
        "key": "threadline", "url": None, "color": (46, 70, 110), "kind": "folded",
        "manual": {
            "brand_name": "Threadline", "product_name": "Ikat Everyday Kurta",
            "product_description": "A relaxed-fit everyday kurta in handwoven cotton with naturally dyed ikat patterns.",
            "target_audience": "Working professionals aged 24-40 who want comfortable Indian wear for office and weekends",
            "price_range": "₹1,899", "tone": "easy, confident, a little playful",
            "key_features": ["Handwoven cotton", "Naturally dyed ikat patterns", "Relaxed everyday fit",
                             "Machine washable"],
        },
        "slots": {"instagram": [(4, 19), (6, 18)], "linkedin": [(3, 18)], "x": [(5, 12)]},
        "concept_lift": {"testimonial-style": 1.35, "problem": 1.25, "demo": 1.0, "storytelling": 0.95, "offer": 0.85},
        "question_lift": 1.45, "base_rate": {"instagram": 0.034, "linkedin": 0.017, "x": 0.012},
        "reach": {"instagram": 5000, "linkedin": 1100, "x": 700}, "growth": 0.6,
    },
]


# ----------------------------------------------------------------------------- small helpers
def _font(size: int):
    for name in ("DejaVuSerif-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def product_image(name: str, product: str, color: tuple, kind: str) -> bytes:
    """A simple, clearly illustrative pack shot for the manual demo brands (no real product photo exists)."""
    W = H = 900
    img = Image.new("RGB", (W, H), (244, 239, 232))
    d = ImageDraw.Draw(img)
    for y in range(H):                                            # soft vignette backdrop
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(244 - 14 * t), int(239 - 16 * t), int(232 - 20 * t)))
    d.ellipse([170, 700, 730, 790], fill=(214, 206, 196))
    if kind == "pouch":
        d.rounded_rectangle([250, 150, 650, 720], radius=34, fill=color)
        d.rectangle([250, 150, 650, 200], fill=tuple(max(0, c - 25) for c in color))
        d.rectangle([265, 120, 635, 160], fill=tuple(max(0, c - 40) for c in color))
        d.rounded_rectangle([300, 300, 600, 560], radius=18, fill=(244, 239, 232))
        d.text((450, 380), name.split("&")[0].strip(), font=_font(52), fill=color, anchor="mm")
        d.text((450, 440), "& Bloom" if "&" in name else "", font=_font(34), fill=color, anchor="mm")
        d.text((450, 510), "COORG · MEDIUM ROAST", font=_font(20), fill=color, anchor="mm")
        d.ellipse([430, 215, 470, 255], fill=(230, 224, 214))
    else:
        d.polygon([(190, 700), (260, 220), (640, 220), (710, 700)], fill=color)
        for i in range(6):
            x0 = 235 + i * 70
            d.polygon([(x0, 300 + i * 12), (x0 + 36, 270), (x0 + 72, 300 + i * 12), (x0 + 36, 330 + i * 12)],
                      fill=(244, 239, 232))
        d.rounded_rectangle([340, 560, 560, 650], radius=14, fill=(244, 239, 232))
        d.text((450, 605), name, font=_font(40), fill=color, anchor="mm")
    return _png(img)


def logo_image(name: str, color: tuple) -> bytes:
    img = Image.new("RGBA", (600, 220), (244, 239, 232, 255))
    d = ImageDraw.Draw(img)
    d.text((300, 110), name, font=_font(70), fill=color, anchor="mm")
    return _png(img)


def ist_datetime(day: datetime, hour: int, minute: int = 0) -> datetime:
    """A tz-aware UTC datetime for `hour:minute` IST on the given IST calendar day."""
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)
    return local.astimezone(timezone.utc)


def pick_time(spec: dict, platform: str, window_start: datetime, days: int = 14) -> datetime:
    """Posting time: 55% near one of the brand's true best slots, otherwise anywhere in waking hours."""
    start = pi.as_ist(window_start).replace(hour=0, minute=0, second=0, microsecond=0)
    if RNG.random() < 0.55:
        wd, hr = RNG.choice(spec["slots"][platform])
        cands = [start + timedelta(days=i) for i in range(days) if (start + timedelta(days=i)).weekday() == wd]
        day = RNG.choice(cands) if cands else start
        return ist_datetime(day, hr + RNG.choice([-1, 0, 0, 0, 1]), RNG.choice([0, 15, 30, 45]))
    day = start + timedelta(days=RNG.randrange(days))
    return ist_datetime(day, RNG.randint(7, 22), RNG.choice([0, 20, 40]))


def engagement(spec: dict, platform: str, when: datetime, concept_type: str, text: str, progress: float) -> dict:
    t = pi.as_ist(when)
    near = any(t.weekday() == wd and abs(t.hour - hr) <= 1 for wd, hr in spec["slots"][platform])
    slot = 1.75 if near else (0.85 if t.hour < 7 or t.hour >= 23 else 1.0)
    first = text.strip().split("\n")[0]
    style = spec["question_lift"] if first.endswith("?") else 1.0
    lift = spec["concept_lift"].get(concept_type, 1.0)
    imp = int(spec["reach"][platform] * RNG.uniform(0.7, 1.3) * (1 + spec["growth"] * progress))
    rate = spec["base_rate"][platform] * slot * lift * style * RNG.uniform(0.8, 1.2)
    eng = imp * rate
    return {"impressions": imp, "likes": int(eng * 0.68), "comments": int(eng * 0.06), "shares": int(eng * 0.03),
            "clicks": int(eng * 0.15)}


# ----------------------------------------------------------------------------- main build
def seed_brand(c: TestClient, spec: dict, now: datetime) -> dict:
    body = {"url": spec["url"]} if spec["url"] else {"manual": spec["manual"]}
    brand = c.post("/api/brands/analyze", json=body).json()
    bid = brand["id"]
    name = brand["name"]
    if spec["manual"]:
        c.post(f"/api/brands/{bid}/uploads", data={"role": "logo"}, files={"file": ("logo.png", logo_image(name, spec["color"]), "image/png")})
        c.post(f"/api/brands/{bid}/uploads", data={"role": "product"},
               files={"file": ("product.png", product_image(name, spec["manual"]["product_name"], spec["color"], spec["kind"]), "image/png")})
    print(f"\n=== {name} (brand #{bid}) ===")

    objectives = ["awareness", "sales", "launch", "sales"]
    created = []
    for i in range(4):
        start = now - timedelta(days=WEEKS * 7 - i * 14)
        camp = c.post("/api/campaigns", json={"brand_id": bid, "objective": objectives[i],
                                               "channels": ["instagram", "meta_ads", "google_ads"]}).json()
        cid = camp["id"]
        concepts = c.post(f"/api/campaigns/{cid}/concepts/generate", json={}).json()
        by_type = {x["concept_type"]: x for x in concepts}
        # approve the three strongest-looking concepts (strongest for THIS audience: the ones it will favour)
        ranked = sorted(concepts, key=lambda x: -spec["concept_lift"].get(x["concept_type"], 1))
        for x in ranked[:3]:
            c.patch(f"/api/concepts/{x['id']}", json={"status": "approved"})
        # ad metrics: 7 days, driven by the same hidden audience taste
        with Session(engine) as s:
            camp_row = s.get(Campaign, cid)
            camp_row.created_at = camp_row.updated_at = start
            camp_row.status = "approved" if i < 3 else "scheduled"
            s.add(camp_row)
            for x in concepts:
                row = s.get(Concept, x["id"])
                row.created_at = row.updated_at = start
                s.add(row)
                lift = spec["concept_lift"].get(x["concept_type"], 1.0)
                for d in range(7):
                    day = (start + timedelta(days=1 + d)).date().isoformat()
                    imp = int(RNG.uniform(2500, 4200) * (1 + 0.04 * i))
                    clicks = int(imp * 0.012 * lift * RNG.uniform(0.85, 1.15))
                    conv = int(clicks * 0.032 * lift * RNG.uniform(0.7, 1.3))
                    s.add(MetricSnapshot(campaign_id=cid, concept_id=x["id"], platform="meta", day=day, impressions=imp,
                                         clicks=clicks, conversions=conv, spend=round(imp / 1000 * RNG.uniform(60, 90), 2),
                                         revenue=round(conv * RNG.uniform(900, 1500), 2) if spec["key"] != "brew" else round(conv * RNG.uniform(380, 520), 2),
                                         source_type="simulated", captured_at=start + timedelta(days=8)))
            s.commit()
        it = c.post(f"/api/campaigns/{cid}/iterate", json={}).json()           # learns -> Brand Memory (+ Meko)
        with Session(engine) as s:
            row = s.get(Iteration, it["id"])
            row.created_at = start + timedelta(days=9)
            s.add(row)
            for v in s.exec(select(Concept).where(Concept.iteration_id == it["id"])).all():
                v.created_at = v.updated_at = start + timedelta(days=9)
                s.add(v)
            s.commit()
        created.append((cid, start, [x["id"] for x in ranked[:3]]))
        print(f"  campaign #{cid} {objectives[i]:9s} started {start.date()}  concepts+metrics+optimization round")

    # posts: 2 variants x 3 platforms x 3 approved concepts per campaign, published in the 14 days after its start
    n_posts = 0
    for i, (cid, start, approved_ids) in enumerate(created):
        with Session(engine) as s:
            camp = s.get(Campaign, cid)
            brand_row, profile, strategy = brand_context(s, camp)
            for cx in approved_ids:
                concept = s.get(Concept, cx)
                cd = {k: getattr(concept, k) for k in ("concept_type", "target_segment", "angle", "hook",
                                                         "primary_text", "headline", "cta")}
                for variant in (0, 1):
                    posts, mode, _ = social_posts.generate(cd, profile, strategy, camp.product_focus,
                                                           guardrail_list(brand_row), brand_row.sources,
                                                           brand_row.website, list(PLATFORMS), "en", variant=variant)
                    for d in posts:
                        when = pick_time(spec, d["platform"], start)
                        progress = ((when - (now - timedelta(days=WEEKS * 7))).days) / (WEEKS * 7)
                        m = engagement(spec, d["platform"], when, concept.concept_type, d["text"], max(0, min(1, progress)))
                        s.add(SocialPost(campaign_id=cid, concept_id=cx, platform=d["platform"], hook=d["hook"],
                                         text=d["text"], hashtags=d["hashtags"], thread=d["thread"],
                                         visual_idea=d["visual_idea"], cta=d["cta"], risk_flags=d["risk_flags"],
                                         status="published", generation_mode=mode, prompt_version="synthetic-history",
                                         published_at=when, publish_mode="synthetic_history", metrics=m,
                                         metrics_source="synthetic_history", created_at=when - timedelta(days=1),
                                         updated_at=when))
                        n_posts += 1
            s.commit()
    print(f"  {n_posts} published posts with engagement history")

    # current campaign: Meko-informed concepts + posts scheduled at the learned best times
    camp = c.post("/api/campaigns", json={"brand_id": bid, "objective": "sales",
                                           "channels": ["instagram", "meta_ads", "google_ads"]}).json()
    cid = camp["id"]
    concepts = c.post(f"/api/campaigns/{cid}/concepts/generate", json={}).json()
    with Session(engine) as s:
        insights = analyze_brand_posts(s, bid)
    top = sorted(concepts, key=lambda x: -spec["concept_lift"].get(x["concept_type"], 1))[:2]
    for x in top:
        c.patch(f"/api/concepts/{x['id']}", json={"status": "approved"})
        for p in c.post(f"/api/concepts/{x['id']}/posts/generate", json={}).json():
            c.patch(f"/api/posts/{p['id']}", json={"status": "approved"})
            slot = (insights["next_slots"].get(p["platform"]) or {}).get("at")
            if slot:
                c.post(f"/api/posts/{p['id']}/schedule", json={"scheduled_at": slot})
    ins_text = insights["preferences"][:3]
    print(f"  current campaign #{cid}: 2 concepts approved, 6 posts scheduled at learned best times")
    for line in ins_text:
        print(f"    learned: {line}")

    with Session(engine) as s:
        b = s.get(Brand, bid)
        b.integrations = {**(b.integrations or {}), "synthetic_history": {
            "weeks": WEEKS, "campaigns": 4, "posts": n_posts, "note": "Synthetic demo history, not real results.",
            "generated_at": now.isoformat()}}
        s.add(b)
        s.commit()
    save_posting_insights_job(bid)       # posting patterns -> Meko
    return {"brand_id": bid, "name": name, "current_campaign": cid, "posts": n_posts}


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger().setLevel(logging.WARNING)
    now = datetime.now(timezone.utc)
    wipe()
    print("cleared database and storage; Meko configured:", meko_memory.configured())
    out = []
    with TestClient(app) as c:
        for spec in BRANDS:
            out.append(seed_brand(c, spec, now))
        print("\n--- Meko status per brand ---")
        for r in out:
            b = c.get(f"/api/brands/{r['brand_id']}").json()
            m = (b.get("integrations") or {}).get("meko", {})
            print(f"  {r['name']:14s} status={m.get('status', 'not_configured'):14s} "
                  f"brand facts={m.get('memories_added', 0)} learnings={m.get('learnings_saved', 0)} "
                  f"posting patterns={m.get('posting_patterns_saved', 0)}")
    print("\nDONE. Open the app: pick a brand in the top-right switcher, then Campaigns -> the newest campaign.")
    print("Everything here is SYNTHETIC demo history and is labelled that way in the UI and in Meko.")


if __name__ == "__main__":
    main()
