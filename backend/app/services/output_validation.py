"""Output validation: claim guard, diversity check, platform limits.

Every concept (LLM or offline) passes through here. Risk flags never silently
rewrite copy; they tell the user exactly what to check before launch.
Severity: info (FYI) · warn (check before launch) · block (do not launch as is).
"""
from __future__ import annotations

import re

from .text_utils import jaccard, short_claim, tokens, trim_words

NUMBER_RE = re.compile(r"₹\s?\d[\d,]*|\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?\s?(?:ml|g|kg|days?|hours?|mins?|minutes?|seconds?|x)\b|\b\d{2,}\b", re.I)
REGULATED_RE = re.compile(r"\b(cures?|curing|treats?|treatment|heals?|healing|clinically|clinical|dermatologist\w*|"
                          r"doctor\w*|fda|medical|medicated|prescription|anti-?acne|eliminat\w+|repairs? damage|"
                          r"reverses?|prevents? (?:ageing|aging|acne|cancer))\b", re.I)
SUPERLATIVE_RE = re.compile(r"(#\s?1\b|\bnumber one\b|\bbest\b|\bguarantee\w*|\b100\s?%|\binstant(?:ly)?\b|"
                            r"\bpermanent\w*|\bmiracle\b|\bflawless\b|\bperfect skin\b)", re.I)
SOCIAL_PROOF_RE = re.compile(r"(\b\d+[\d,.]*\s?[kKlL]?\+?\s?(?:lakh\s)?(?:customers|users|reviews|buyers|people)\b|"
                             r"\bcustomers love\b|\brated\b|\bloved by\b|\bbest-?seller\w*\b|\b\d(?:\.\d)?\s?stars?\b|"
                             r"\baward\w*\b|\bas seen on\b)", re.I)
OFFER_RE = re.compile(r"(\b\d+\s?% off\b|\bsale\b|\bdiscount\w*\b|\bfree shipping\b|\bcoupon\b|\blimited[- ]time\b|"
                      r"\boffer\b|\bbogo\b|\bbuy one get\b|\bflat ₹)", re.I)

GOOGLE_HEADLINE_MAX = 30
GOOGLE_DESCRIPTION_MAX = 90
META_HEADLINE_SOFT_MAX = 40
CTA_MAX = 20


def _flag(code: str, message: str, severity: str, field: str | None = None) -> dict:
    d = {"code": code, "message": message, "severity": severity}
    if field:
        d["field"] = field
    return d


def claim_guard(fields: dict[str, str], source_text: str, guardrails: list[str] | None = None,
                concept_type: str = "") -> list[dict]:
    """Check copy fields against the brand's sources. Returns risk flags."""
    src = (source_text or "").lower()
    src_compact = src.replace(" ", "")
    flags: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(code, msg, sev, field):
        if (code, field) not in seen:
            seen.add((code, field))
            flags.append(_flag(code, msg, sev, field))

    for field, text in fields.items():
        if not text:
            continue
        low = text.lower()
        for m in NUMBER_RE.finditer(text):
            tok = m.group(0).lower().replace(" ", "")
            if tok not in src_compact:
                add("unsupported_number", f"\"{m.group(0)}\" does not appear in your sources. Confirm it or remove it.",
                    "warn", field)
        for m in REGULATED_RE.finditer(text):
            in_src = m.group(0).lower() in src
            add("regulated_claim",
                f"\"{m.group(0)}\" is medical/clinical language. Ad platforms and ASCI rules restrict it"
                + ("; it is on your site, so keep proof ready." if in_src else "; it is not in your sources."),
                "warn" if in_src else "block", field)
        for m in SUPERLATIVE_RE.finditer(text):
            if m.group(0).lower() not in src:
                add("superlative", f"\"{m.group(0)}\" is an absolute claim you would need to prove.", "warn", field)
        for m in SOCIAL_PROOF_RE.finditer(text):
            if m.group(0).lower() not in src:
                add("fake_social_proof", f"\"{m.group(0)}\" implies reviews/customers we have no evidence for.",
                    "block", field)
        for m in OFFER_RE.finditer(text):
            if m.group(0).lower() not in src:
                add("offer_unverified", f"\"{m.group(0)}\" mentions an offer that isn't on your site. Confirm a real offer first.",
                    "block", field)
        for g in guardrails or []:
            if g and g.lower() in low:
                add("guardrail_violation", f"Uses \"{g}\", which is on your avoid list.", "block", field)

    if concept_type == "testimonial-style":
        flags.append(_flag("dramatization", "Customer-voice concept is a dramatization. Label it as such, "
                           "or swap in a real review you have permission to use.", "warn", "primary_text"))
    return flags


def near_duplicates(hooks: list[str], threshold: float = 0.6) -> list[tuple[int, int, float]]:
    out = []
    for i in range(len(hooks)):
        for j in range(i + 1, len(hooks)):
            s = jaccard(hooks[i], hooks[j])
            if s > threshold:
                out.append((i, j, round(s, 2)))
    return out


def hashtags(brand: str, category: str, claims: list[str], india: bool) -> list[str]:
    tags = ["#" + re.sub(r"[^A-Za-z0-9]", "", brand)]
    cat = re.sub(r"[^A-Za-z0-9]", "", category.split("&")[0].strip().title())
    if cat:
        tags.append("#" + cat)
        if india:
            tags.append("#Indian" + cat)
    text = " ".join(claims).lower()
    for word, tag in [("fragrance-free", "#FragranceFree"), ("spf", "#SunscreenDaily"), ("niacinamide", "#Niacinamide"),
                      ("rice water", "#RiceWater"), ("saffron", "#Kesar"), ("made in india", "#MadeInIndia"),
                      ("vegan", "#Vegan"), ("cotton", "#Cotton"), ("handmade", "#Handmade"), ("coffee", "#CoffeeLovers")]:
        if word in text and tag not in tags:
            tags.append(tag)
    if india and "#MadeInIndia" not in tags:
        tags.append("#MadeInIndia")
    tags.append("#D2CIndia" if india else "#ShopSmall")
    return list(dict.fromkeys(tags))[:8]


def platform_copy(hook: str, primary_text: str, headline: str, cta: str, product: str, brand: str,
                  claims: list[str], value_prop: str, tags: list[str]) -> tuple[dict, list[dict]]:
    """Adapt one concept to each platform's format and limits."""
    flags: list[dict] = []
    caption = f"{hook}\n\n{primary_text}\n\n{cta} → link in bio\n\n{' '.join(tags)}"

    meta_headline, cut = trim_words(headline, META_HEADLINE_SOFT_MAX)
    meta_desc = next((short_claim(c, 30) for c in claims if len(short_claim(c, 30)) <= 30), brand)

    # Google RSA headlines: only lines that fit 30 chars whole (or shorten cleanly by clause).
    candidates = [headline, product, f"{brand} {product}" if brand not in product else product,
                  *[short_claim(c, GOOGLE_HEADLINE_MAX) for c in claims], f"{cta} at {brand}", brand]
    g_heads: list[str] = []
    trimmed = False
    for c in candidates:
        if c and 8 <= len(c) <= GOOGLE_HEADLINE_MAX and c.lower() not in {h.lower() for h in g_heads}:
            g_heads.append(c)
        if len(g_heads) == 5:
            break
    descs = []
    for c in [primary_text, " · ".join(short_claim(x, 40) for x in claims[:2]) + f". {cta}.",
              f"{value_prop} {cta}." if value_prop else ""]:
        t, cut = trim_words(c, GOOGLE_DESCRIPTION_MAX)
        trimmed |= cut
        if t and t not in descs:
            descs.append(t)
    if trimmed:
        flags.append(_flag("trimmed_for_platform",
                           "Some Google Ads lines were shortened at a word boundary to fit 30/90 characters. Review them.",
                           "info", "platform_copy"))
    return ({
        "instagram": {"caption": caption, "hashtags": tags},
        "meta_ads": {"primary_text": f"{hook} {primary_text}", "headline": meta_headline, "description": meta_desc,
                     "cta": cta},
        "google_ads": {"headlines": g_heads[:5], "descriptions": descs[:2]},
    }, flags)


def length_flags(headline: str, cta: str) -> list[dict]:
    out = []
    if len(headline) > META_HEADLINE_SOFT_MAX:
        out.append(_flag("long_headline", f"Headline is {len(headline)} characters; aim for ≤{META_HEADLINE_SOFT_MAX}.",
                         "info", "headline"))
    if len(cta) > CTA_MAX:
        out.append(_flag("long_cta", f"CTA is {len(cta)} characters; aim for ≤{CTA_MAX}.", "info", "cta"))
    return out


def content_tokens(text: str) -> set[str]:
    return set(tokens(text))
