"""Brand Intelligence Engine: extraction result + manual facts -> BrandProfile (Brand Memory).

Two paths share the same deterministic grounding pass:
  * Gemini: structured JSON from the page snippets (untrusted) + manual input
  * Offline: heuristics over the same snippets (always available)

Grounding rule: an approved claim must cite a real source id (page snippet `s*`,
product `p*`, manual input `m*`) and its content words must actually appear in that
source. Anything else is moved to `unknowns_to_confirm`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings
from ..schemas.brand import (ApprovedClaim, AudienceHypothesis, BrandProfile, ManualBrandInput,
                             ProductInfo)
from . import llm
from .extractor import ExtractionResult, download_image
from .text_utils import coverage, sentence

PROMPT_VERSION = "brand-v1"

CATEGORY_LEXICON = {
    "skincare": ["serum", "cleanser", "moisturi", "spf", "sunscreen", "skin", "face wash", "toner", "niacinamide"],
    "haircare": ["shampoo", "conditioner", "hair oil", "scalp", "hair"],
    "fashion & apparel": ["t-shirt", "kurta", "dress", "jeans", "apparel", "saree", "sneaker", "fashion"],
    "food & beverage": ["coffee", "tea", "snack", "chocolate", "granola", "masala", "beverage", "protein bar"],
    "electronics": ["earbuds", "charger", "speaker", "smartwatch", "headphone", "cable"],
    "home & living": ["candle", "bedsheet", "cookware", "decor", "furniture", "planter"],
    "fitness & wellness": ["yoga", "supplement", "whey", "fitness", "gym", "wellness"],
    "jewellery & accessories": ["necklace", "earring", "ring", "bracelet", "jewel", "watch strap"],
}

TONE_LEXICON = {
    "honest": ["exactly what", "transparent", "no promises", "honest", "what's in", "we'd rather"],
    "warm": ["grandmother", "kitchen", "family", "home", "love", "trusted"],
    "gentle": ["gentle", "fragrance-free", "soothing", "calm", "soft", "mild"],
    "modern": ["modern", "routine", "everyday", "daily", "simple"],
    "premium": ["luxury", "premium", "crafted", "artisanal", "finest"],
    "playful": ["fun", "!", "yay", "oops", "vibe"],
    "bold": ["bold", "fearless", "unapologetic", "power"],
    "rooted in India": ["india", "indian", "desi", "ayurved", "jaipur", "kerala", "made in india"],
}

AUDIENCE_RULES = [
    # (cue words, segment, need)
    (["humid", "summer", "hot"], "People in hot, humid Indian cities", "Products that don't feel heavy or sticky in the heat"),
    (["short routine", "three-step", "simple", "routine you'll actually keep", "gentle routine"],
     "Skincare beginners who want a short routine", "A simple routine that is easy to stick to"),
    (["fragrance-free", "sensitive", "gentle"], "People who prefer fragrance-free, gentle products", "Avoiding added fragrance and harsh feel"),
    (["kitchen", "grandmother", "saffron", "rice water", "ayurved", "traditional"],
     "Shoppers who trust familiar Indian ingredients", "Ingredients they recognise from home"),
    (["no white cast", "indian skin"], "People with medium to deep Indian skin tones", "Sun protection without a white cast"),
    (["student", "college", "budget", "affordable"], "Students and young professionals on a budget", "Good value for money"),
    (["gift", "gifting", "festive"], "Gift shoppers", "An easy, giftable pick"),
]

OFFER_WORDS = re.compile(r"\b(\d+\s?% off|sale|discount|coupon|buy one|bogo|free shipping|flat ₹)", re.I)
REVIEW_WORDS = re.compile(r"\b(reviews?|rated|ratings?|stars?|customers love|happy customers)\b", re.I)


@dataclass
class BrandAnalysis:
    profile: BrandProfile
    mode: str
    warnings: list[str] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)   # [{id, text, url}]
    logo_path: str = ""
    product_image_paths: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- sources
def build_sources(ext: ExtractionResult | None, manual: ManualBrandInput) -> list[dict]:
    """Every fact the brand profile may rest on, each with a citable id."""
    out: list[dict] = []
    if ext:
        url = ext.final_url or ext.url
        out += [{"id": s["id"], "text": s["text"], "url": url} for s in ext.snippets]
        for i, p in enumerate(ext.products, 1):
            text = " ".join(x for x in [p["name"], p.get("description") or "", *p.get("features", []),
                                        f"Price {p['price']}" if p.get("price") else ""] if x)
            out.append({"id": f"p{i}", "text": text, "url": url})
    m = manual
    manual_bits = [m.brand_name, m.product_name, m.product_description, m.target_audience,
                   f"Price range {m.price_range}" if m.price_range else None, m.tone, *m.key_features]
    for i, text in enumerate([b for b in manual_bits if b], 1):
        out.append({"id": f"m{i}", "text": text, "url": "user-provided"})
    return out


# --------------------------------------------------------------------------- grounding
def ground_claims(profile: BrandProfile, sources: list[dict], guardrails: list[str]) -> BrandProfile:
    by_id = {s["id"]: s for s in sources}
    kept: list[ApprovedClaim] = []
    unknowns = list(profile.unknowns_to_confirm)
    blocked = [g.lower() for g in guardrails if g.strip()]
    for c in profile.approved_claims:
        src_ids = re.findall(r"\b[spm]\d+\b", c.source)
        src_text = " ".join(by_id[s]["text"] for s in src_ids if s in by_id)
        if c.source.strip().lower() in {"user-provided", "user provided"}:
            src_text = " ".join(s["text"] for s in sources if s["url"] == "user-provided")
        ok = bool(src_text) and coverage(c.claim, src_text) >= 0.6
        if ok and any(b in c.claim.lower() for b in blocked):
            ok = False
        if ok:
            kept.append(c)
        else:
            unknowns.append(f"Confirm before using: \"{c.claim}\" (not found in the sources)")
    profile.approved_claims = kept
    profile.unknowns_to_confirm = list(dict.fromkeys(unknowns))
    return profile


# --------------------------------------------------------------------------- visual identity
def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb[:3])


def dominant_colors(path: Path, n: int = 3) -> list[str]:
    from PIL import Image

    with Image.open(path) as im:
        im = im.convert("RGBA").resize((96, 96))
        data = im.get_flattened_data() if hasattr(im, "get_flattened_data") else im.getdata()
        px = [p[:3] for p in data if p[3] > 200 and not (min(p[:3]) > 235) and not (max(p[:3]) < 20)]
    if not px:
        return []
    small = Image.new("RGB", (len(px), 1))
    small.putdata(px)
    pal = small.quantize(colors=n + 2).getpalette()[: (n + 2) * 3]
    counts = sorted(small.quantize(colors=n + 2).getcolors(), reverse=True)
    out = []
    for _, idx in counts:
        rgb = pal[idx * 3: idx * 3 + 3]
        if len(rgb) == 3:
            out.append(_hex(rgb))
    return out[:n]


def visual_identity(ext: ExtractionResult | None, images: list[Path], tone: list[str]) -> dict:
    colors: list[str] = []
    if ext and re.fullmatch(r"#[0-9a-fA-F]{6}", ext.theme_color or ""):
        colors.append(ext.theme_color.upper())
    for p in images[:2]:
        try:
            colors += dominant_colors(p)
        except Exception:
            pass
    def rgb(h: str) -> tuple[int, int, int]:
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]

    distinct: list[str] = []
    for c in colors:  # drop near-duplicates so primary/secondary/accent actually differ
        if all(sum((a - b) ** 2 for a, b in zip(rgb(c), rgb(d))) ** 0.5 > 60 for d in distinct):
            distinct.append(c)
    colors = distinct or ["#1F2937"]
    while len(colors) < 3:
        colors.append({1: "#F5EFE6", 2: "#111827"}[len(colors)])
    return {"primary": colors[0], "secondary": colors[1], "accent": colors[2],
            "style": tone[:3] or ["clean"], "source": "theme-color + image colours" if ext else "default"}


# --------------------------------------------------------------------------- offline heuristics
def _category(text: str) -> str:
    t = text.lower()
    scores = {cat: sum(t.count(w) for w in words) for cat, words in CATEGORY_LEXICON.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "consumer products"


def _tone(text: str, manual_tone: str | None) -> list[str]:
    if manual_tone:
        return [t.strip() for t in re.split(r"[,/]", manual_tone) if t.strip()][:4]
    t = text.lower()
    scores = {tone: sum(t.count(w) for w in words) for tone, words in TONE_LEXICON.items()}
    ranked = [k for k, v in sorted(scores.items(), key=lambda kv: -kv[1]) if v > 0]
    return ranked[:4] or ["clear", "friendly", "confident"]


def _brand_name(ext: ExtractionResult | None, manual: ManualBrandInput) -> str:
    if manual.brand_name:
        return manual.brand_name.strip()
    if ext:
        if ext.site_name:
            return ext.site_name
        if ext.title:
            return re.split(r"\s[|\-–—:]\s", ext.title)[0].strip()
        host = urlparse(ext.url).hostname or ""
        return host.replace("www.", "").split(".")[0].title()
    return "Untitled brand"


def offline_profile(ext: ExtractionResult | None, manual: ManualBrandInput, sources: list[dict]) -> BrandProfile:
    corpus = " ".join(s["text"] for s in sources)
    name = _brand_name(ext, manual)

    products: list[ProductInfo] = []
    for p in (ext.products if ext else []):
        products.append(ProductInfo(name=p["name"], description=p.get("description", ""), price=p.get("price"),
                                    image_url=p.get("image_url"), features=p.get("features", [])))
    if manual.product_name and not any(manual.product_name.lower() in p.name.lower() for p in products):
        products.insert(0, ProductInfo(name=manual.product_name, description=manual.product_description or "",
                                       price=manual.price_range, features=manual.key_features))

    bullets = ext.bullets if ext else []
    snippet_id = {s["text"]: s["id"] for s in sources}
    claims = [ApprovedClaim(claim=b, source=snippet_id.get(b, "")) for b in bullets
              if not OFFER_WORDS.search(b) and not REVIEW_WORDS.search(b)]
    for f in manual.key_features:
        claims.append(ApprovedClaim(claim=f, source="user-provided"))

    description = (manual.product_description or (ext.description if ext else "")
                   or (ext.paragraphs[0] if ext and ext.paragraphs else ""))
    benefit_cues = ("free", "without", "no ", "lightweight", "gentle", "made for", "suitable", "quick", "easy", "made in")
    value_props = [sentence(description)] if description else []
    value_props += [b for b in bullets if any(c in b.lower() for c in benefit_cues)]
    value_props = list(dict.fromkeys(v for v in value_props if v))[:5]

    hyps: list[AudienceHypothesis] = []
    if manual.target_audience:
        hyps.append(AudienceHypothesis(segment=manual.target_audience, need="As described by the brand",
                                       evidence="user-provided", confidence="high"))
    low = corpus.lower()
    for cues, seg, need in AUDIENCE_RULES:
        hit = next((c for c in cues if c in low), None)
        if hit:
            src = next((s for s in sources if hit in s["text"].lower()), None)
            hyps.append(AudienceHypothesis(segment=seg, need=need,
                                           evidence=f"{src['id']}: \"{src['text'][:90]}\"" if src else "assumption",
                                           confidence="medium" if src else "low"))
    if len(hyps) < 2:
        hyps.append(AudienceHypothesis(segment="Online shoppers aged 22-35 in Indian metros",
                                       need="Trustworthy products they can buy quickly online",
                                       evidence="assumption", confidence="low"))
    hyps = hyps[:4]

    diffs = []
    if re.search(r"kitchen|grandmother|ayurved|traditional|heritage", low):
        diffs.append("Rooted in familiar Indian ingredients")
    if "made in india" in low:
        diffs.append("Made in India")
    if "fragrance-free" in low or "free from added fragrance" in low:
        diffs.append("Fragrance-free formulas")
    prices = [float(re.sub(r"[^\d.]", "", p.price)) for p in products if p.price and re.search(r"\d", p.price)]
    if prices and max(prices) < 1500:
        diffs.append(f"Accessible pricing (₹{min(prices):.0f}–₹{max(prices):.0f} on the site)")
    if re.search(r"exactly what|transparent|honest", low):
        diffs.append("Openly says what is in each product")

    unknowns = []
    if not OFFER_WORDS.search(corpus):
        unknowns.append("Any current offer or discount (none found on the site)")
    if not REVIEW_WORDS.search(corpus):
        unknowns.append("Customer reviews or ratings you are allowed to quote (none found)")
    if re.search(r"working on|in progress|pending", low) and "certif" in low:
        unknowns.append("Certification status: the site says it is still in progress")
    if not prices:
        unknowns.append("Product prices")
    if not manual.target_audience:
        unknowns.append("Confirm the target audience (current segments are hypotheses)")

    return BrandProfile(
        brand_name=name,
        product_name=products[0].name if products else (manual.product_name or ""),
        product_category=_category(corpus),
        description=description,
        products=products,
        value_propositions=value_props,
        features=list(dict.fromkeys([*bullets, *manual.key_features]))[:10],
        audience_hypotheses=hyps,
        brand_tone=_tone(corpus, manual.tone),
        differentiators=diffs[:5],
        approved_claims=claims[:12],
        unknowns_to_confirm=unknowns,
        source_urls=[ext.final_url or ext.url] if ext else [],
    )


# --------------------------------------------------------------------------- LLM prompt
def build_prompt(ext: ExtractionResult | None, manual: ManualBrandInput, sources: list[dict]) -> str:
    page = {
        "title": ext.title if ext else "", "meta_description": ext.description if ext else "",
        "products": ext.products if ext else [],
        "snippets": [{"id": s["id"], "text": s["text"]} for s in sources if s["url"] != "user-provided"],
    }
    manual_src = [{"id": s["id"], "text": s["text"]} for s in sources if s["url"] == "user-provided"]
    return f"""Build a brand profile for a marketing team.

<untrusted_page>
{json.dumps(page, ensure_ascii=False)[:14000]}
</untrusted_page>

Facts typed by the brand owner (trusted):
{json.dumps(manual_src, ensure_ascii=False)}
Claims the brand owner said to avoid: {json.dumps(manual.claims_to_avoid, ensure_ascii=False)}

Rules:
- approved_claims: only statements directly supported by a snippet/product/manual fact. Set "source" to its id
  (e.g. "s7", "p2", "m1"). Keep wording close to the source. No medical, cure or performance claims.
- audience_hypotheses: likely customer segments. "evidence" quotes the supporting snippet id, or "assumption".
  Use "low" confidence for assumptions.
- unknowns_to_confirm: facts a marketer would need that the sources don't give (offers, reviews, certifications,
  audience confirmation, prices...).
- products: copy name/price/image_url/features from the page data; never invent prices.
- brand_tone: 3-4 adjectives describing how the brand speaks.
- visual_identity: leave empty {{}} (computed separately)."""


# --------------------------------------------------------------------------- main entry
def _big_enough(path: Path, strict: bool) -> bool:
    """Skip thumbnails and banners. Photos tied to a product are kept even when small; page photos must be >= 300px."""
    try:
        from PIL import Image
        w, h = Image.open(path).size
    except Exception:  # noqa: BLE001
        return False
    if strict:
        return min(w, h) >= 300 and max(w, h) / max(1, min(w, h)) <= 3.5
    return min(w, h) >= 120


def analyze(ext: ExtractionResult | None, manual: ManualBrandInput, brand_dir: Path) -> BrandAnalysis:
    sources = build_sources(ext, manual)
    warnings = list(ext.warnings) if ext else []
    fallback = lambda: offline_profile(ext, manual, sources)  # noqa: E731
    result = llm.generate_json("brand_profile", build_prompt(ext, manual, sources), BrandProfile, fallback,
                               temperature=0.3)
    profile = result.data
    warnings += result.warnings

    # Keep page facts authoritative even if the LLM dropped or altered them.
    if ext and ext.products:
        llm_by_name = {p.name.lower(): p for p in profile.products}
        merged = []
        for p in ext.products:
            lp = llm_by_name.get(p["name"].lower())
            merged.append(ProductInfo(name=p["name"], description=p.get("description") or (lp.description if lp else ""),
                                      price=p.get("price"), image_url=p.get("image_url"),
                                      features=p.get("features") or (lp.features if lp else [])))
        profile.products = merged
    if manual.brand_name:
        profile.brand_name = manual.brand_name
    profile.source_urls = [ext.final_url or ext.url] if ext else []
    profile = ground_claims(profile, sources, manual.claims_to_avoid)

    if result.mode != "offline":
        # The product name must be a product we actually found (or the one the user typed).
        names = [p.name for p in profile.products]
        if manual.product_name:
            profile.product_name = manual.product_name
        elif names and profile.product_name not in names:
            match = next((n for n in names if profile.product_name and profile.product_name.lower() in n.lower()), None)
            profile.product_name = match or names[0]
        # Never end up with fewer claims than the deterministic path: add verbatim, sourced bullets Gemini skipped.
        base = offline_profile(ext, manual, sources)
        have = " ".join(c.claim.lower() for c in profile.approved_claims)
        for c in base.approved_claims:
            if c.claim.lower() not in have and coverage(c.claim, have) < 0.8:
                profile.approved_claims.append(c)

    # Assets: logo + product images (safe download).
    brand_dir.mkdir(parents=True, exist_ok=True)
    logo_path = ""
    if ext and ext.logo:
        p = download_image(ext.logo, brand_dir, "logo")
        logo_path = str(p) if p else ""
    image_paths: list[Path] = []
    urls = [p.image_url for p in profile.products if p.image_url]
    if ext and ext.og_image and ext.og_image not in urls:
        urls.append(ext.og_image)
    for u in (ext.page_images if ext else []):   # photos found in the page body (hero, gallery, lazy-loaded)
        if u not in urls:
            urls.append(u)
    n_products = len([p for p in profile.products if p.image_url])
    for i, u in enumerate(urls[:10]):
        p = download_image(u, brand_dir, f"product_{i+1}")
        if p and _big_enough(p, strict=i >= n_products):
            image_paths.append(p)
        elif p:
            p.unlink(missing_ok=True)
        if len(image_paths) >= 6:
            break
    if urls and not image_paths:
        warnings.append("Could not find usable product photos on the site. Upload a product photo for better videos.")
    elif not urls:
        warnings.append("No product photos found on the site. Upload a product photo for better videos.")

    color_imgs = ([Path(logo_path)] if logo_path else []) + image_paths
    profile.visual_identity = visual_identity(ext, color_imgs, profile.brand_tone)
    return BrandAnalysis(profile=profile, mode=result.mode, warnings=list(dict.fromkeys(warnings)), sources=sources,
                         logo_path=logo_path, product_image_paths=[str(p) for p in image_paths])
