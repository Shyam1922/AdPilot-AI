"""Social posts (LinkedIn, Instagram, X) for a concept.

Same trust rules as ad copy: facts come only from approved claims / the real price, everything runs through the
claim guard, platform limits are enforced in code, and every post carries a generation_mode label. Nothing is
published anywhere: these are drafts the user copies out.
"""
from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field

from ..schemas.brand import BrandProfile
from ..schemas.concept import CampaignStrategy
from . import llm
from .ad_generator import Ctx, build_ctx
from . import tag_picker
from .output_validation import claim_guard, hashtags
from .text_utils import short_claim

PLATFORMS = ("linkedin", "instagram", "x")
LIMITS = {"linkedin": 3000, "instagram": 2200, "x": 280}
TAG_MAX = {"linkedin": 5, "instagram": 5, "x": 2}          # how many of the top 5 go inside the post text
TOP_TAGS = 5
X_URL_LEN = 23     # X counts every link as 23 characters
POST_PROMPT_VERSION = "posts-v1"


class PostCopy(BaseModel):
    platform: Literal["linkedin", "instagram", "x"]
    hook: str = Field(max_length=200)           # first line: the only line most people read
    body: str                                   # the post text WITHOUT hashtags
    hashtags: list[str] = []
    thread: list[str] = []                      # X only: follow-up posts (max 3)
    visual_idea: str = ""
    cta: str = ""


class PostBatch(BaseModel):
    posts: list[PostCopy]


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


def _neutral_hook(concept: dict, x: Ctx, variant: int) -> str:
    """A concept hook that is safe to post. Customer-voice (dramatised) hooks become a plain question."""
    if concept.get("concept_type") == "testimonial-style":
        opts = [f"What would a shorter {x.category} routine look like?", f"What do you look for in {x.category}?"]
        return opts[variant % len(opts)]
    return concept.get("hook") or f"Meet {x.product}."


# --------------------------------------------------------------------------- offline generator
def offline_post(platform: str, concept: dict, x: Ctx, website: str, variant: int = 0) -> PostCopy:
    hook = _neutral_hook(concept, x, variant)
    c = (x.claims + x.value_props + [x.product] * 3)[:3]
    price = f" ({x.price})" if x.price else ""
    link = website.rstrip("/") if website and "adpilot.local" not in website else ""
    cta = concept.get("cta") or (x.ctas[0] if x.ctas else "Shop now")
    seg = _lc(concept.get("target_segment") or (x.segments[0] if x.segments else "you"))
    ask = [f"Which of these matters most to you?", "Tell us in the comments.", f"Is this you? Say so below."][variant % 3]

    if platform == "linkedin":
        story = x.origin or f"{x.brand} set out to make {x.category} simpler."
        body = "\n\n".join([
            hook,
            story.rstrip(".") + ".",
            f"{x.product}{price} comes down to three things:\n" + "\n".join(f"→ {short_claim(t, 90)}" for t in c),
            f"Made for {seg}.",
            f"{ask}\n\n{cta}" + (f": {link}" if link else ""),
        ])
        return PostCopy(platform="linkedin", hook=hook, body=body, cta=cta,
                        visual_idea="Single product photo or a 3-slide carousel: problem, product, what's inside.")

    if platform == "instagram":
        lines = "\n".join(f"✔ {short_claim(t, 80)}" for t in c)
        body = "\n\n".join([
            f"{hook} ✨",
            f"Meet {x.product}{price}.",
            lines,
            f"{ask} 👇",
            f"{cta} → link in bio 🔗\nSave this for later 📌 and share with a friend who needs it.",
        ])
        return PostCopy(platform="instagram", hook=hook, body=body, cta=cta,
                        visual_idea="Reel (use the generated video) or carousel: 1 hook, 2 product close-up, "
                                    "3 benefits, 4 CTA. Put the hook in the first 2 seconds.")

    # X: one tight post + a short thread
    tail = f" {link}" if link else ""
    first = f"{hook}\n\n{x.product}{price}: {_lc(short_claim(c[0], 110))}.\n\n{cta}{tail}"
    thread = [f"1/ {short_claim(c[0], 200)}.", f"2/ {short_claim(c[1], 200)}.",
              f"3/ {short_claim(c[2], 200)}. {cta}{tail}".strip()]
    return PostCopy(platform="x", hook=hook, body=first, cta=cta, thread=thread,
                    visual_idea="One product image or a 6-second clip from the video.")


# --------------------------------------------------------------------------- LLM
def build_post_prompt(concept: dict, x: Ctx, platforms: list[str], website: str, memory_context: str = "") -> str:
    lang = {"en": "English", "hi": "Hindi (Devanagari)", "hinglish": "Hinglish (Hindi in Latin script mixed with English)"}
    return f"""Write one social post per platform for this ad concept: {', '.join(platforms)}.

Brand: {x.brand}. Product: {x.product_full} (price on site: {x.price or "unknown"}). Website: {website or "n/a"}
Concept: type={concept.get('concept_type')}, angle={concept.get('angle')}, hook={concept.get('hook')},
headline={concept.get('headline')}, cta={concept.get('cta')}, audience={concept.get('target_segment')}
Approved claims you may use: {json.dumps(x.claims, ensure_ascii=False)}
Avoid: {json.dumps(x.guardrails, ensure_ascii=False)}
Language: {lang.get(x.language, "English")}
Internal learnings (direction only, not product facts): {memory_context or "none yet"}

Craft rules (these decide whether people stop scrolling):
- The first line is everything. Open with a specific tension, a surprising detail from the claims, or a sharp question. No "Introducing", "Discover", "Unlock", "Elevate", "game-changer".
- One idea per post. Concrete beats generic: name the moment (a humid 3pm, a 10-step routine), not "great results".
- Write like a person: short sentences, line breaks, no corporate filler, no stacked exclamation marks.
- End by inviting a reply (a real question) and one clear CTA.
- linkedin: 700-1200 characters, founder/brand voice, a small insight or story, 3-4 short paragraphs or → bullets, no hashtags (the app adds them), at most 1-2 emoji.
- instagram: first 125 characters carry the hook, friendly and visual, line breaks, 3-6 emoji, a save/share prompt, no hashtags (the app adds them), CTA "link in bio". Add visual_idea (reel or carousel plan).
- x: body at most 240 characters incl. the CTA, punchy, no hashtags (the app adds them), plus a thread of exactly 3 follow-up posts (each at most 260 characters) that expand the claims.
- Facts only from the approved claims and the real price. NEVER invent numbers, discounts, reviews, ratings, customer counts, awards or medical outcomes. Do not write fake customer quotes.
- Do not write hashtags anywhere; leave the hashtags array empty. The app adds the 5 best tags itself."""


def _compose(p: PostCopy, x: Ctx, tags: list[str]) -> tuple[str, list[str], list[str]]:
    """Final text, hashtags used, thread, with the platform's limits applied."""
    tl = list(dict.fromkeys(tags))[:TAG_MAX[p.platform]]        # the system's top tags, in order; model-written tags are ignored
    body = p.body.strip()
    for t in tl:                                   # don't repeat tags that the model already wrote inline
        body = re.sub(rf"\s*{re.escape(t)}\b", "", body, flags=re.I) if body.count(t) > 1 else body
    text = body + ("\n\n" + " ".join(tl) if tl else "")
    thread = [t.strip() for t in p.thread][:3] if p.platform == "x" else []
    return text, tl, thread


def _x_len(text: str) -> int:
    return len(re.sub(r"https?://\S+", "x" * X_URL_LEN, text))


def finalize(p: PostCopy, concept: dict, x: Ctx, tags: list[str]) -> dict:
    text, tl, thread = _compose(p, x, tags)
    top = list(tags[:TOP_TAGS])
    flags = claim_guard({"post": text, **{f"thread_{i+1}": t for i, t in enumerate(thread)}},
                        x.source_text + " " + (x.price or ""), x.guardrails, "")
    if p.platform == "x":
        if _x_len(text) > LIMITS["x"]:              # cut tags first, then body at a word boundary
            text = p.body.strip()
            if _x_len(text) > LIMITS["x"]:
                cut = text[: LIMITS["x"] - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
                text = cut
            tl = []
            flags.append({"code": "trimmed", "severity": "info", "field": "post",
                          "message": "Trimmed to fit X's 280-character limit."})
        thread = [t if len(t) <= LIMITS["x"] else t[: LIMITS["x"] - 1].rsplit(" ", 1)[0] + "…" for t in thread]
    elif len(text) > LIMITS[p.platform]:
        text = text[: LIMITS[p.platform] - 1].rsplit(" ", 1)[0] + "…"
        flags.append({"code": "trimmed", "severity": "info", "field": "post",
                      "message": f"Trimmed to fit {p.platform}'s {LIMITS[p.platform]}-character limit."})
    chars = _x_len(text) if p.platform == "x" else len(text)
    return {"platform": p.platform, "hook": p.hook, "text": text, "hashtags": top, "thread": thread,
            "visual_idea": p.visual_idea, "cta": p.cta, "risk_flags": flags, "char_count": chars,
            "char_limit": LIMITS[p.platform]}


def generate(concept: dict, profile: BrandProfile, strategy: CampaignStrategy, product_focus: str,
             guardrails: list[str], sources: list[dict], website: str, platforms: list[str],
             language: str = "en", memory_context: str = "", variant: int = 0) -> tuple[list[dict], str, list[str]]:
    x = build_ctx(profile, strategy, product_focus, guardrails, sources, language)
    platforms = [p for p in PLATFORMS if p in platforms] or list(PLATFORMS)
    derived = hashtags(x.brand, x.category, [x.product_full, *x.claims[:3]], x.india)
    tags_by = {pl: tag_picker.pick(pl, x.brand, x.category, derived, x.india) for pl in platforms}

    def offline() -> PostBatch:
        return PostBatch(posts=[offline_post(p, concept, x, website, variant) for p in platforms])

    res = llm.generate_json("social_posts", build_post_prompt(concept, x, platforms, website, memory_context),
                            PostBatch, offline, temperature=0.9 if not variant else 1.0, timeout=45)
    by_platform: dict[str, PostCopy] = {}
    for p in res.data.posts:
        by_platform.setdefault(p.platform, p)
    posts = []
    for plat in platforms:
        p = by_platform.get(plat) or offline_post(plat, concept, x, website, variant)
        posts.append(finalize(p, concept, x, tags_by[plat]))
    return posts, res.mode, list(res.warnings)
