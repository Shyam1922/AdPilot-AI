"""AI Marketing Strategist: Brand Memory + objective -> structured, editable CampaignStrategy."""
from __future__ import annotations

import json

from ..schemas.brand import BrandProfile
from ..schemas.concept import CalendarItem, CampaignStrategy, StrategySegment
from . import llm
from .text_utils import strip_brand

PROMPT_VERSION = "strategy-v1"

OBJECTIVE_KPI = {
    "awareness": "Reach and CTR (as an attention proxy)",
    "traffic": "CTR and cost per click",
    "leads": "Lead conversion rate and cost per lead",
    "sales": "Purchase conversion rate, CPA and ROAS",
    "engagement": "Engagement rate (CTR as proxy) and saves/shares",
    "launch": "Reach, CTR and first-week conversions",
}

OBJECTIVE_CTAS = {
    "awareness": ["Learn more", "Meet the range", "Watch now"],
    "traffic": ["Explore the range", "See how it works", "Learn more"],
    "leads": ["Get the guide", "Sign up", "Get notified"],
    "sales": ["Shop now", "Add to cart", "Buy now"],
    "engagement": ["Tell us yours", "Save this", "Share with a friend"],
    "launch": ["Be the first to try", "Shop the launch", "Get notified"],
}

CHANNEL_ROLES = {
    "instagram": ("Discovery and brand feel", ["Reels 9:16", "Feed 4:5", "Stories"]),
    "meta_ads": ("Paid reach and retargeting", ["Reels ads 9:16", "Feed ads 4:5"]),
    "google_ads": ("Capture people already searching", ["Responsive search ads", "Performance Max (later)"]),
    "youtube": ("Short-form reach", ["Shorts 9:16"]),
    "amazon_ads": ("Marketplace intent", ["Sponsored Products (needs Amazon Ads access)"]),
    "email": ("Repeat purchase and launches", ["Launch email", "Newsletter"]),
}


_CHANNEL_ALIASES = {
    "instagram": "instagram", "ig": "instagram", "insta": "instagram", "reels": "instagram",
    "meta": "meta_ads", "meta ads": "meta_ads", "meta_ads": "meta_ads", "facebook": "meta_ads", "facebook ads": "meta_ads",
    "google": "google_ads", "google ads": "google_ads", "google_ads": "google_ads", "search": "google_ads",
    "youtube": "youtube", "youtube shorts": "youtube", "shorts": "youtube",
    "amazon": "amazon_ads", "amazon ads": "amazon_ads", "amazon_ads": "amazon_ads",
    "email": "email", "newsletter": "email",
}


def _channel_key(raw) -> str:
    t = str(raw or "").strip().lower().replace("-", " ")
    if t in _CHANNEL_ALIASES:
        return _CHANNEL_ALIASES[t]
    for alias, key in _CHANNEL_ALIASES.items():
        if alias in t:
            return key
    return t.replace(" ", "_")


def _as_list(v) -> list[str]:
    if isinstance(v, str):
        return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def normalize_channel_plan(items, channels: list[str]) -> list[dict]:
    """Make channel_plan always [{channel, role, formats}] with known channel keys, whatever the model returned."""
    out: dict[str, dict] = {}
    for it in items or []:
        if isinstance(it, str):
            it = {"channel": it}
        if not isinstance(it, dict):
            continue
        raw = next((it[k] for k in ("channel", "platform", "name", "channel_name", "id", "title") if it.get(k)), "")
        key = _channel_key(raw)
        if not key:
            continue
        role_default, fmt_default = CHANNEL_ROLES.get(key, ("Supporting channel", ["Native formats"]))
        role = next((str(it[k]) for k in ("role", "purpose", "objective", "description", "goal") if it.get(k)), role_default)
        formats = _as_list(next((it[k] for k in ("formats", "format", "creative_formats", "ad_formats") if it.get(k)), [])) or fmt_default
        out.setdefault(key, {"channel": key, "role": role, "formats": formats})
    for ch in channels or []:   # every requested channel appears in the plan
        key = _channel_key(ch)
        if key not in out:
            role, formats = CHANNEL_ROLES.get(key, ("Supporting channel", ["Native formats"]))
            out[key] = {"channel": key, "role": role, "formats": formats}
    return list(out.values())


def normalize_strategy(d: dict, channels: list[str]) -> dict:
    """Repair a stored/generated strategy so the UI contract always holds (no missing keys, right types)."""
    d = dict(d or {})
    d["channel_plan"] = normalize_channel_plan(d.get("channel_plan"), channels)
    fallback_ch = d["channel_plan"][0]["channel"] if d["channel_plan"] else "instagram"
    cal = []
    for i, it in enumerate(d.get("content_calendar") or []):
        if not isinstance(it, dict):
            continue
        try:
            day = int(it.get("day") or i + 1)
        except (TypeError, ValueError):
            day = i + 1
        cal.append({"day": day, "channel": _channel_key(it.get("channel") or it.get("platform")) or fallback_ch,
                    "content": str(it.get("content") or it.get("idea") or it.get("title") or ""),
                    "concept_type": str(it.get("concept_type") or it.get("type") or "")})
    d["content_calendar"] = cal
    segs = []
    for sg in d.get("segments") or []:
        if isinstance(sg, dict):
            segs.append({"name": str(sg.get("name") or sg.get("segment") or "Audience"),
                         "pain_points": _as_list(sg.get("pain_points") or sg.get("pains") or []),
                         "message": str(sg.get("message") or sg.get("key_message") or "")})
    d["segments"] = segs
    for k in ("campaign_themes", "creative_angles", "ctas", "assumptions", "not_claimed"):
        d[k] = _as_list(d.get(k))
    return d


def offline_strategy(profile: BrandProfile, objective: str, channels: list[str], product_focus: str,
                     audience_note: str) -> CampaignStrategy:
    brand = profile.brand_name
    product = strip_brand(product_focus or profile.product_name or "the range", brand)
    hyps = profile.audience_hypotheses[:3]
    claims = [c.claim for c in profile.approved_claims]
    diff = profile.differentiators[0] if profile.differentiators else (claims[0] if claims else "")
    audience = audience_note or (hyps[0].segment if hyps else "online shoppers in India")

    segments = []
    for h in hyps or []:
        pains = [h.need]
        related = [c for c in claims if any(w in c.lower() for w in h.need.lower().split()[:4])][:1]
        segments.append(StrategySegment(
            name=h.segment, pain_points=pains,
            message=f"{product}: {related[0] if related else (profile.value_propositions[0] if profile.value_propositions else diff)}"))
    if not segments:
        segments.append(StrategySegment(name=audience, pain_points=["Not sure which product to trust"],
                                        message=f"{product} from {brand}: {diff or 'made simple'}"))

    themes = []
    if any("india" in d.lower() or "ingredient" in d.lower() for d in profile.differentiators):
        themes.append("Familiar Indian ingredients, modern routine")
    if any(w in " ".join(claims).lower() for w in ("humid", "summer", "lightweight", "non-sticky")):
        themes.append("Made for Indian weather")
    if any("fragrance-free" in c.lower() for c in claims):
        themes.append("Gentle by default")
    themes.append({"sales": "Your next favourite, for everyday", "launch": "Something new on the shelf",
                   "awareness": f"Meet {brand}", "traffic": "See what's inside",
                   "leads": "Get the routine that fits you", "engagement": "Show us your routine"}.get(objective, f"Meet {brand}"))

    angles = [
        "Problem → solution: name the everyday frustration, show the product fixing it",
        "Product demo: texture, size and how to use it in under 10 seconds",
        "Origin story: why the brand started and what it refuses to do",
        "Value framing: what you get at this price (only real prices, no invented discounts)",
        "Customer voice: dramatized everyday moment, clearly labelled until real reviews exist",
    ]

    channel_plan = []
    for ch in channels or ["instagram", "meta_ads"]:
        role, formats = CHANNEL_ROLES.get(ch, ("Supporting channel", ["Native formats"]))
        channel_plan.append({"channel": ch, "role": role, "formats": formats})

    cal_channels = [c["channel"] for c in channel_plan] or ["instagram"]
    types = ["problem", "demo", "storytelling", "offer", "testimonial-style", "demo", "problem"]
    calendar = [CalendarItem(day=i + 1, channel=cal_channels[i % len(cal_channels)],
                             content=f"{t.replace('-', ' ').capitalize()} creative for {product}", concept_type=t)
                for i, t in enumerate(types)]

    lead_claim = next((c for c in claims if any(w in c.lower() for w in ("light", "gentle", "free", "easy", "quick"))),
                      claims[0] if claims else "")
    aud = audience[:1].lower() + audience[1:]
    positioning = (f"For {aud}, {brand}'s {product} offers {lead_claim[:1].lower() + lead_claim[1:] if lead_claim else 'a simple everyday pick'}"
                   f"{'. What sets it apart: ' + diff[:1].lower() + diff[1:] if diff else ''}.")

    return CampaignStrategy(
        objective=objective, positioning_statement=positioning, primary_kpi=OBJECTIVE_KPI.get(objective, "CTR"),
        segments=segments, campaign_themes=themes[:4], creative_angles=angles, channel_plan=channel_plan,
        ctas=OBJECTIVE_CTAS.get(objective, ["Learn more"]), content_calendar=calendar,
        assumptions=[f"Audience segments are hypotheses ({', '.join(h.confidence for h in hyps) or 'low'} confidence) until tested",
                     "No budget or past performance data yet; channel mix is a starting point, not a forecast"],
        not_claimed=["No performance predictions (reach, sales or ROAS)", "No discounts or offers unless you confirm one",
                     "No reviews, ratings or certifications that are not on your site",
                     *[f"Not confirmed: {u}" for u in profile.unknowns_to_confirm[:2]]],
    )


def compact_profile(profile: BrandProfile) -> str:
    """Only what the strategist/copywriter needs. Smaller prompts = faster, cheaper, more focused answers."""
    return json.dumps({
        "brand": profile.brand_name, "category": profile.product_category, "description": profile.description,
        "products": [{"name": p.name, "price": p.price} for p in profile.products],
        "value_propositions": profile.value_propositions[:5],
        "approved_claims": [c.claim for c in profile.approved_claims],
        "audience_hypotheses": [{"segment": h.segment, "need": h.need, "confidence": h.confidence}
                                for h in profile.audience_hypotheses],
        "tone": profile.brand_tone, "differentiators": profile.differentiators,
        "do_not_claim_unconfirmed": profile.unknowns_to_confirm,
    }, ensure_ascii=False)


def build_prompt(profile: BrandProfile, objective: str, channels: list[str], product_focus: str,
                 audience_note: str, budget_note: str) -> str:
    return f"""Create a campaign strategy for this brand.

Brand Memory (trusted, already verified):
{compact_profile(profile)}

Campaign objective: {objective}
Channels: {json.dumps(channels)}
Product focus: {product_focus or profile.product_name}
Audience note from user: {audience_note or "none"}
Budget note from user: {budget_note or "none"}

Rules:
- Base every message on approved_claims, value_propositions and differentiators only.
- primary_kpi must match the objective ({OBJECTIVE_KPI.get(objective)}).
- creative_angles: 5 distinct angles matching concept types problem, demo, storytelling, offer, testimonial-style.
- content_calendar: 7 items (day 1-7), each on one of the given channels.
- assumptions: what you assumed. not_claimed: things we deliberately do not claim (no performance predictions).
- No predicted numbers of any kind."""


def generate(profile: BrandProfile, objective: str, channels: list[str], product_focus: str = "",
             audience_note: str = "", budget_note: str = "") -> llm.LLMResult[CampaignStrategy]:
    fb = lambda: offline_strategy(profile, objective, channels, product_focus, audience_note)  # noqa: E731

    def fix(s: CampaignStrategy) -> CampaignStrategy:
        s.objective = objective
        s.channel_plan = normalize_channel_plan(s.channel_plan, channels)
        return s

    return llm.generate_json("campaign_strategy",
                             build_prompt(profile, objective, channels, product_focus, audience_note, budget_note),
                             CampaignStrategy, fb, temperature=0.6, postprocess=fix)
