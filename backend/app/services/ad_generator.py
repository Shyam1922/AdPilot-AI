"""AI Creative Studio (copy): Brand Memory + strategy -> 5 distinct ad concepts.

One concept per type (problem, demo, storytelling, offer, testimonial-style), each with
hook, primary text, headline, CTA, visual brief and a 4-beat video script. All concepts
pass the claim guard, the diversity check and per-platform adaptation.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..schemas.brand import BrandProfile
from ..schemas.concept import CONCEPT_TYPES, AdConcept, CampaignStrategy, ConceptBatch, VideoBeat, VisualBrief
from . import llm
from .output_validation import claim_guard, hashtags, length_flags, near_duplicates, platform_copy
from .strategist import compact_profile
from .text_utils import coverage, short_claim, strip_brand, trim_words

PROMPT_VERSION = "concepts-v1"


# --------------------------------------------------------------------------- context
@dataclass
class Ctx:
    brand: str
    product: str
    product_full: str
    price: str | None
    category: str
    claims: list[str]
    value_props: list[str]
    segments: list[str]
    ctas: list[str]
    angles: list[str]
    pains: list[str]
    origin: str
    india: bool
    source_text: str
    guardrails: list[str] = field(default_factory=list)
    language: str = "en"


PAIN_MAP = [
    (("heat", "sticky", "humid", "heavy"), ["Skin feeling sticky by noon?", "Humid day, heavy products. Again?",
                                            "Why does everything feel heavy in this heat?"]),
    (("routine", "simple", "stick to"), ["Too many steps in your routine?", "Want a routine you'll actually keep?",
                                         "Ten steps every morning? No thanks."]),
    (("fragrance", "harsh", "gentle"), ["Does strong fragrance put you off?", "Looking for something gentler?"]),
    (("recognise", "ingredients", "familiar"), ["Can you recognise what's in your products?",
                                                "Miss the ingredients you grew up with?"]),
    (("white cast",), ["Tired of a white cast?", "Sunscreen that shows up grey on your skin?"]),
    (("value", "budget", "price"), ["Good products shouldn't cost a fortune.", "Paying for the label, not what's inside?"]),
]


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def build_ctx(profile: BrandProfile, strategy: CampaignStrategy, product_focus: str, guardrails: list[str],
              sources: list[dict], language: str = "en") -> Ctx:
    brand = profile.brand_name
    focus = product_focus or profile.product_name or (profile.products[0].name if profile.products else brand)
    prod = next((p for p in profile.products if p.name.lower() == focus.lower()), None) or \
        next((p for p in profile.products if focus.lower() in p.name.lower()), None)
    prod_text = " ".join([focus, prod.description if prod else "", *(prod.features if prod else [])])
    claims = [c.claim for c in profile.approved_claims]
    claims.sort(key=lambda c: -coverage(c, prod_text))  # claims about the focus product first
    needs = " ".join(h.need.lower() for h in profile.audience_hypotheses)
    pains: list[str] = []
    for cues, lines in PAIN_MAP:
        if any(c in needs for c in cues):
            pains += lines
    pains += [f"Still looking for {profile.product_category or 'products'} that actually suits you?"]
    corpus = " ".join(s["text"] for s in sources)
    m = re.search(r"([A-Z][^.]*?started in [^,.:]+)", corpus)
    origin = m.group(1).strip() if m else ""
    return Ctx(
        brand=brand, product=strip_brand(focus, brand), product_full=focus, price=prod.price if prod else None,
        category=profile.product_category or "products", claims=claims or profile.value_propositions[:3] or [brand],
        value_props=profile.value_propositions, segments=[s.name for s in strategy.segments] or ["online shoppers"],
        ctas=strategy.ctas or ["Shop now"], angles=strategy.creative_angles, pains=pains, origin=origin,
        india=bool(re.search(r"india", corpus, re.I)), source_text=corpus, guardrails=guardrails, language=language,
    )


# --------------------------------------------------------------------------- variants (offline + regenerate + iteration)
def hook_variants(t: str, x: Ctx) -> list[str]:
    p = x.product
    if t == "problem":
        return x.pains
    if t == "demo":
        return [f"{p}, up close.", "Watch the texture first.", f"How {p} fits into your morning.",
                f"This is what {p} actually feels like."]
    if t == "storytelling":
        base = [f"Why we made {p}.", f"The question behind {x.brand}."]
        if x.origin:
            short = re.sub(r"^.*?started in", "It started in", x.origin)
            base.insert(0, short.rstrip(".") + ".")
        return base
    if t == "offer":
        if x.price:
            return [f"{p}. {x.price}. That's it.", f"Everything you get for {x.price}.", f"What {x.price} gets you."]
        return [f"Everything inside {p}.", "No gimmicks. Just what's inside."]
    # testimonial-style (dramatized)
    return ["“I actually stuck with this one.”", f"“My {x.category} routine finally got shorter.”",
            "“I didn't expect to like it this much.”"]


def headline_variants(t: str, x: Ctx) -> list[str]:
    p = x.product
    c0 = x.claims[0] if x.claims else p
    return {
        "problem": [trim_words(c0, 40)[0], f"{p}, made for real days", f"Meet {p}"],
        "demo": [f"See {p} up close", f"{p}, in one look", f"Texture you can see"],
        "storytelling": [f"The story behind {x.brand}", f"Why {x.brand} exists", f"Made with familiar ingredients"],
        "offer": [f"{p} · {x.price}" if x.price else f"Inside {p}", f"Shop {p}", f"{x.brand}, simply priced"],
        "testimonial-style": [f"A day with {p}", f"Why {p} fits in", f"{p} in real life"],
    }[t]


def cta_variants(t: str, x: Ctx) -> list[str]:
    base = list(dict.fromkeys(x.ctas + ["Shop now", "Learn more"]))
    order = {"problem": 0, "demo": 1, "storytelling": 2, "offer": 0, "testimonial-style": 1}[t]
    return base[order % len(base):] + base[:order % len(base)]


def primary_variants(t: str, x: Ctx) -> list[str]:
    c = x.claims + x.value_props
    c1, c2, c3 = (c + [x.product, x.product, x.product])[:3]
    p, seg = x.product, _lc(x.segments[0]) if x.segments else "everyday use"
    if t == "problem":
        return [f"Meet {p}: {_lc(c1)}. {c2}. Made for {seg}.",
                f"{p} keeps it simple: {_lc(c1)}, {_lc(c2)}."]
    if t == "demo":
        return [f"{c1}. {c2}. {c3}. That's {p}.", f"Here's {p} in use: {_lc(c1)}, {_lc(c2)}."]
    if t == "storytelling":
        if x.origin:
            return [f"{x.origin}. {p} is what came out of it: {_lc(c1)}.",
                    f"{x.origin}. Today that idea is {p}: {_lc(c1)}, {_lc(c2)}."]
        return [f"{x.brand} set out to make {x.category} simpler. {p}: {_lc(c1)}."]
    if t == "offer":
        if x.price:
            return [f"For {x.price}: {_lc(c1)}, {_lc(c2)}. No gimmicks, just the price on our site.",
                    f"{p} is {x.price}. You get {_lc(c1)} and {_lc(c2)}."]
        return [f"What's inside: {_lc(c1)}, {_lc(c2)}. Nothing you don't need."]
    return [f"(Dramatization) A normal day with {p}: {_lc(c1)}, {_lc(c2)}. Replace with a real review before launch.",
            f"(Dramatization) Why {p} stayed in the routine: {_lc(c1)}. Swap in a real customer quote before launch."]


LAYOUT = {"problem": "bold", "demo": "hero", "storytelling": "minimal", "offer": "split", "testimonial-style": "hero"}


def visual_brief(t: str, x: Ctx) -> VisualBrief:
    scenes = {
        "problem": "Close-up of everyday frustration (a warm, humid afternoon), then the product as the calm answer",
        "demo": "Product on a clean surface; macro of texture; hand picking it up",
        "storytelling": "Warm, natural-light kitchen or workspace that hints at the brand's origin",
        "offer": "Product hero on a solid brand-colour background with price and what's included",
        "testimonial-style": "Person's everyday moment (morning routine), product in hand, caption-style text",
    }
    return VisualBrief(scene=scenes[t], composition="Vertical 9:16, product in the middle third",
                       product_placement="Real product image, centred, never redrawn or altered",
                       text_safe_area="Top 30% for hook, bottom 20% for CTA; keep clear of platform UI",
                       style=f"{', '.join(x.category.split(' & ')[:1])}; brand colours; clean, flat type",
                       layout=LAYOUT[t])


def video_script(hook: str, x: Ctx, cta: str) -> list[VideoBeat]:
    benefits = " · ".join(short_claim(c, 42) for c in x.claims[:3])
    end = f"{cta}" + (f" · {x.price}" if x.price else "")
    return [VideoBeat(beat="hook", seconds=3, on_screen_text=hook, voiceover=hook),
            VideoBeat(beat="product", seconds=4, on_screen_text=x.product_full, voiceover=f"Meet {x.product_full}."),
            VideoBeat(beat="benefit", seconds=4, on_screen_text=benefits, voiceover=". ".join(x.claims[:2]) + "."),
            VideoBeat(beat="cta", seconds=4, on_screen_text=end, voiceover=f"{cta}.")]


def offline_concept(t: str, i: int, x: Ctx) -> AdConcept:
    hook = hook_variants(t, x)[0]
    cta = cta_variants(t, x)[0]
    return AdConcept(
        concept_type=t, target_segment=x.segments[i % len(x.segments)],
        angle=x.angles[i] if i < len(x.angles) else t,
        hook=trim_words(hook, 120)[0], primary_text=primary_variants(t, x)[0],
        headline=trim_words(headline_variants(t, x)[0], 60)[0], cta=trim_words(cta, 30)[0],
        visual_brief=visual_brief(t, x), video_script=video_script(hook, x, cta),
        claim_sources=["approved_claims"], rationale=f"Offline template for the '{t}' angle using approved claims only.",
    )


def offline_batch(x: Ctx) -> ConceptBatch:
    return ConceptBatch(concepts=[offline_concept(t, i, x) for i, t in enumerate(CONCEPT_TYPES)])


# --------------------------------------------------------------------------- LLM
from pydantic import BaseModel as _BM, Field as _F  # noqa: E402


class ConceptCopy(_BM):
    """What the LLM writes. Visual brief and video script are built in code from it (faster, consistent)."""
    concept_type: str
    target_segment: str
    angle: str
    hook: str = _F(max_length=120)
    primary_text: str
    headline: str = _F(max_length=60)
    cta: str = _F(max_length=30)
    rationale: str = ""


class ConceptCopyBatch(_BM):
    concepts: list[ConceptCopy]


def build_prompt(profile: BrandProfile, strategy: CampaignStrategy, x: Ctx, memory_context: str = "") -> str:
    lang = {"en": "English", "hi": "Hindi (Devanagari)", "hinglish": "Hinglish (Hindi in Latin script mixed with English)"}
    return f"""Write 5 distinct ad concepts for this campaign.

Brand Memory (verified): {compact_profile(profile)}
Strategy: {json.dumps({"positioning": strategy.positioning_statement, "kpi": strategy.primary_kpi,
                       "segments": [s.name for s in strategy.segments], "angles": strategy.creative_angles,
                       "ctas": strategy.ctas}, ensure_ascii=False)}
Focus product: {x.product_full} (price on site: {x.price or "unknown"})
Approved claims you may use (verbatim meaning only): {json.dumps(x.claims, ensure_ascii=False)}
Avoid: {json.dumps(x.guardrails, ensure_ascii=False)}
Language: {lang.get(x.language, "English")}
Shared agent memory from Meko (internal learnings; use for direction, not as new product facts):
{memory_context or "none yet"}

Rules:
- Exactly one concept per concept_type, in this order: {", ".join(CONCEPT_TYPES)}.
- Each concept a clearly different angle and hook (no two hooks sharing most words).
- hook ≤ 90 chars, headline ≤ 40 chars, cta ≤ 20 chars.
- Use ONLY approved claims for product facts. No numbers, prices, discounts, reviews, ratings, customer counts,
  certifications or medical words unless they appear in the approved claims or price.
- testimonial-style must start primary_text with "(Dramatization)" and must not pretend to be a real review.
- offer: if no real offer exists, frame value (what you get for the real price), never invent a discount.
- target_segment: one of the strategy segments. rationale: one short sentence."""


def _finalize(c: AdConcept, x: Ctx, tags: list[str]) -> dict:
    if len(c.video_script) != 4:
        c.video_script = video_script(c.hook, x, c.cta)
    fields = {"hook": c.hook, "primary_text": c.primary_text, "headline": c.headline, "cta": c.cta,
              "video_script": " ".join(b.on_screen_text for b in c.video_script)}
    flags = claim_guard(fields, x.source_text + " " + (x.price or ""), x.guardrails, c.concept_type)
    flags += length_flags(c.headline, c.cta)
    pc, pflags = platform_copy(c.hook, c.primary_text, c.headline, c.cta, x.product, x.brand, x.claims,
                               x.value_props[0] if x.value_props else "", tags)
    d = c.model_dump()
    d["platform_copy"] = pc
    d["risk_flags"] = flags + pflags
    return d


def generate(profile: BrandProfile, strategy: CampaignStrategy, product_focus: str, guardrails: list[str],
             sources: list[dict], language: str = "en", memory_context: str = "") -> tuple[list[dict], str, list[str]]:
    """Returns (concept dicts ready to save, generation_mode, warnings)."""
    x = build_ctx(profile, strategy, product_focus, guardrails, sources, language)

    def repair(batch: ConceptBatch) -> ConceptBatch:
        by_type = {}
        for c in batch.concepts:
            by_type.setdefault(c.concept_type, c)
        fixed = [by_type.get(t) or offline_concept(t, i, x) for i, t in enumerate(CONCEPT_TYPES)]
        for c in fixed:
            if c.concept_type == "testimonial-style" and not c.primary_text.startswith("(Dramatization)"):
                c.primary_text = "(Dramatization) " + c.primary_text
        return ConceptBatch(concepts=fixed)

    def to_batch(copy: ConceptCopyBatch) -> ConceptBatch:
        out = []
        for i, c in enumerate(copy.concepts):
            t = c.concept_type if c.concept_type in CONCEPT_TYPES else CONCEPT_TYPES[min(i, 4)]
            out.append(AdConcept(concept_type=t, target_segment=c.target_segment, angle=c.angle, hook=c.hook,
                                 primary_text=c.primary_text, headline=c.headline, cta=c.cta,
                                 visual_brief=visual_brief(t, x), video_script=video_script(c.hook, x, c.cta),
                                 claim_sources=["approved_claims"], rationale=c.rationale))
        return repair(ConceptBatch(concepts=out))

    offline = offline_batch(x)
    res = llm.generate_json("ad_concepts", build_prompt(profile, strategy, x, memory_context), ConceptCopyBatch,
                            lambda: ConceptCopyBatch(concepts=[ConceptCopy(**c.model_dump(include=set(ConceptCopy.model_fields)))
                                                               for c in offline.concepts]),
                            temperature=0.9, timeout=45)
    concepts = to_batch(res.data).concepts if res.mode == "gemini" else offline.concepts
    warnings = list(res.warnings)

    # Diversity: replace the later of any near-duplicate pair with an alternative hook.
    for i, j, s in near_duplicates([c.hook for c in concepts]):
        alts = [h for h in hook_variants(concepts[j].concept_type, x) if h != concepts[j].hook]
        if alts:
            concepts[j].hook = alts[0]
            warnings.append(f"Hooks {i+1} and {j+1} were too similar ({s}); rewrote hook {j+1}.")

    tags = hashtags(x.brand, x.category, [x.product_full, *x.claims[:3]], x.india)
    out = [_finalize(c, x, tags) for c in concepts]
    for d in out:
        d["generation_mode"] = res.mode
        d["prompt_version"] = PROMPT_VERSION
    return out, res.mode, warnings


# --------------------------------------------------------------------------- single-field regenerate
def regenerate_field(concept: dict, field_name: str, profile: BrandProfile, strategy: CampaignStrategy,
                     product_focus: str, guardrails: list[str], sources: list[dict]) -> tuple[dict, str]:
    x = build_ctx(profile, strategy, product_focus, guardrails, sources)
    t = concept["concept_type"]
    current = concept.get(field_name, "")
    pools = {"hook": hook_variants, "headline": headline_variants, "cta": cta_variants, "primary_text": primary_variants}
    alts = [v for v in pools[field_name](t, x) if v != current] or [current]
    limits = {"hook": 120, "headline": 60, "cta": 30, "primary_text": 600}

    from pydantic import BaseModel

    class FieldOut(BaseModel):
        value: str

    prompt = (f"Rewrite the {field_name} of this {t} ad concept so it is clearly different from the current one.\n"
              f"Concept: {json.dumps(concept, ensure_ascii=False, default=str)[:3000]}\n"
              f"Current {field_name} (do NOT repeat): {current}\n"
              f"Approved claims only: {json.dumps(x.claims, ensure_ascii=False)}\n"
              f"Max {limits[field_name]} characters. No invented numbers, offers, reviews or medical words.")
    res = llm.generate_json(f"regenerate_{field_name}", prompt, FieldOut, lambda: FieldOut(value=alts[0]), temperature=1.0)
    new = trim_words(res.data.value, limits[field_name])[0]
    updated = dict(concept)
    updated[field_name] = new
    if field_name == "hook":
        updated["video_script"] = [b.model_dump() for b in video_script(new, x, updated["cta"])]
    tags = hashtags(x.brand, x.category, [x.product_full, *x.claims[:3]], x.india)
    ac = AdConcept.model_validate({k: updated[k] for k in AdConcept.model_fields if k in updated})
    final = _finalize(ac, x, tags)
    final["generation_mode"] = res.mode
    return final, res.mode


def refresh_derived(concept: dict, profile: BrandProfile, strategy: CampaignStrategy, product_focus: str,
                    guardrails: list[str], sources: list[dict]) -> dict:
    """After a user edit: recompute risk flags + platform copy (copy itself is kept as written)."""
    x = build_ctx(profile, strategy, product_focus, guardrails, sources)
    tags = hashtags(x.brand, x.category, [x.product_full, *x.claims[:3]], x.india)
    limits = {"hook": 120, "headline": 60, "cta": 30}
    data = {k: concept[k] for k in AdConcept.model_fields if k in concept}
    for k, n in limits.items():
        data[k] = (data.get(k) or "")[:n]
    final = _finalize(AdConcept.model_validate(data), x, tags)
    for k in ("hook", "primary_text", "headline", "cta"):  # keep the user's words exactly as typed
        final[k] = concept[k]
    final["platform_copy"], _ = platform_copy(concept["hook"], concept["primary_text"], concept["headline"],
                                              concept["cta"], x.product, x.brand, x.claims,
                                              x.value_props[0] if x.value_props else "", tags)
    fields = {k: concept[k] for k in ("hook", "primary_text", "headline", "cta")}
    final["risk_flags"] = (claim_guard(fields, x.source_text + " " + (x.price or ""), x.guardrails,
                                       concept["concept_type"]) + length_flags(concept["headline"], concept["cta"]))
    return final
