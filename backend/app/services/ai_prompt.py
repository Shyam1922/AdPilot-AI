"""A ready-to-paste prompt for an AI video tool (Veo, Runway, Higgsfield, ...).

Written as three short shots so the AI clip looks different from our own template video (which is a layout with
text). It describes pictures and motion only: the app puts the verified copy, price and call to action on top, so
the tool is told to render no text. The real product photo is the reference image supplied by the user, and the
tool is told never to redraw the product. Shots depend on the concept type and on the product family."""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from . import llm

log = logging.getLogger(__name__)

# family -> concept type -> (shot 1, shot 2, shot 3). {p} is the product.
_SHOTS: dict[str, dict[str, tuple[str, str, str]]] = {
    "skin": {
        "problem": ("a hand wipes a shiny forehead in hazy afternoon heat, city blur behind",
                    "the hand reaches into frame and picks up {p} from a cool stone ledge, a drop of serum on a fingertip",
                    "fresh, matte-dewy skin in soft window light, a relieved exhale, {p} standing beside the mirror"),
        "demo": ("extreme macro of a serum drop swelling at a dropper tip, light refracting through it",
                 "a fingertip spreads the serum across the back of a hand, the texture absorbing in real time",
                 "{p} on a glass tray, a slow light sweep across the bottle"),
        "storytelling": ("saffron threads and rice water in small bowls on a sunlit kitchen counter, steam drifting",
                         "hands pour and stir, the mixture becomes a clear golden serum, cut to {p} being filled",
                         "{p} on a window sill at sunrise, the room waking up around it"),
        "offer": ("{p} spins slowly on a pedestal against a warm colour backdrop, quick light flashes",
                  "fast cuts: the cap turns, a drop falls, the box opens with a soft pop",
                  "{p} centred and still, a confident final hold"),
        "testimonial-style": ("a morning bathroom routine, a person seen only from the shoulders down, towel and mirror steam",
                              "hands apply {p}, a small satisfied smile reflected in the mirror",
                              "the person leaves frame into daylight, {p} left on the shelf"),
    },
    "food": {
        "problem": ("a tired hand reaches for a bland, cold cup on a grey morning desk",
                    "{p} is opened, steam and aroma rolling out in slow motion",
                    "a fresh cup, warm light, a first sip and a visible sigh of relief"),
        "demo": ("extreme macro of {p} being scooped or ground, grains falling in slow motion",
                 "a slow pour with steam and swirling texture",
                 "the finished cup beside {p}, light sweeping over it"),
        "storytelling": ("a sunlit farm or roastery at dawn, hands sorting the raw ingredient",
                         "the ingredient is processed and packed, golden dust in the light",
                         "{p} on a wooden counter in morning light, steam rising"),
        "offer": ("{p} drops into frame onto a bold colour backdrop with a small burst of ingredients",
                  "quick cuts: open, pour, steam, stir",
                  "{p} centred with a finished serving beside it, a confident hold"),
        "testimonial-style": ("a kitchen counter in the morning, a person seen only from the hands",
                              "they make a cup with {p}, smile at the first smell",
                              "a relaxed sip by the window, {p} in the background"),
    },
    "fashion": {
        "problem": ("a hand pushes through a crowded wardrobe of stiff, uncomfortable clothes",
                    "{p} is lifted off its hanger, the fabric falling soft and light",
                    "{p} worn, an easy walk through bright daylight, framed from the shoulders down"),
        "demo": ("extreme macro of the weave and stitching of {p}",
                 "fabric stretching and swinging, a hand smoothing it flat",
                 "{p} hanging in warm window light, a slow pan down its length"),
        "storytelling": ("a loom or hand-stitching close-up, threads in motion, warm workshop light",
                         "hands finish and fold {p}",
                         "{p} laid out on a clean surface, soft daylight"),
        "offer": ("{p} swings into frame on a hanger against a bold colour backdrop",
                  "quick cuts of the fabric, collar, stitching and fit",
                  "{p} centred and still, a confident hold"),
        "testimonial-style": ("a person getting ready in daylight, seen from the shoulders down",
                              "they put on {p} and check themselves in the mirror, relaxed",
                              "they walk out the door, light catching the fabric"),
    },
    "generic": {
        "problem": ("a hand struggles with a clumsy everyday routine, cluttered desk, flat light",
                    "{p} enters the frame and the scene calms",
                    "everything tidy and bright, {p} clearly in frame"),
        "demo": ("extreme macro of the details of {p} under soft side light",
                 "hands pick it up and use it, a clear close view of how it works",
                 "{p} set down, a slow light sweep across it"),
        "storytelling": ("the raw materials and tools of a small workshop, warm light",
                         "hands make and finish {p}",
                         "{p} on a clean surface in morning light"),
        "offer": ("{p} spins on a pedestal against a bold colour backdrop",
                  "fast cuts of its details and a box opening",
                  "{p} centred and still, a confident hold"),
        "testimonial-style": ("an everyday scene, a person seen only from the hands",
                              "they use {p} naturally, a small smile",
                              "they move on with their day, {p} left in frame"),
    },
}
_FAMILY = {"skin": "skin", "beauty": "skin", "cosmetic": "skin", "personal care": "skin", "food": "food",
           "beverage": "food", "coffee": "food", "tea": "food", "snack": "food", "fashion": "fashion",
           "apparel": "fashion", "cloth": "fashion", "wear": "fashion"}


def _family(category: str) -> str:
    c = (category or "").lower()
    return next((v for k, v in _FAMILY.items() if k in c), "generic")


class _Shot(BaseModel):
    action: str = Field(description="What physically moves in the frame, one clear action, concrete verbs")
    camera: str = Field(description="One camera move only, e.g. slow dolly-in, macro orbit, locked-off")
    light: str = Field(description="Light and atmosphere for this shot")


class _Plan(BaseModel):
    shots: list[_Shot] = Field(min_length=3, max_length=3)


_DIRECTOR = (
    "You are a commercial cinematographer writing shot descriptions for an image-to-video model (Seedance, Veo, Kling). "
    "The brand's real product photo is the first frame, so NEVER describe the product's looks (shape, colour, label): "
    "describe only what moves, what the camera does and how the light behaves. Rules: exactly 3 shots (3 s, 3 s, 2 s); "
    "one clear action and one camera move per shot; concrete physical verbs and sensory detail (condensation sliding, "
    "steam curling, fabric swaying, a drop swelling and falling, dust in a light beam); realistic physics; the product "
    "stays still and rigid unless a hand lifts or turns it; hands and shoulders only, never a face talking to camera; "
    "no text, logos, captions or screens anywhere; 20 to 40 words per field; no marketing adjectives like 'stunning'. "
    "Make the three shots tell the story of THIS concept (its hook and angle) for THIS audience, set in an Indian context "
    "that fits them. Do not reuse generic stock scenes."
)


def _director(concept_type: str, brand: str, product: str, category: str, segment: str, tone: list[str],
              first_feature: str, hook: str, angle: str, scene: str) -> list[tuple[str, str, str]] | None:
    """Ask the LLM for concept-specific shots. Returns None when no model is available (the caller then uses the
    built-in shot lists), so credits spent on a video model are never wasted on an empty or generic prompt."""
    if not llm.available_providers():
        return None
    user = (f"Brand: {brand}\nProduct: {product} ({category})\nConcept type: {concept_type}\nAngle: {angle}\n"
            f"Hook line: {hook}\nAudience: {segment}\nTone: {', '.join(tone)[:100]}\n"
            f"Key feature (do not depict as text): {first_feature}\nScene idea from the brief: {scene}\n"
            "Write the 3 shots.")
    try:
        res = llm.generate_json("ai_video_shots", user, _Plan, lambda: None, temperature=0.9, system=_DIRECTOR, timeout=40)
    except Exception as exc:                                                    # never break the endpoint
        log.warning("ai_prompt director failed: %s", exc)
        return None
    if res.mode == "offline" or res.data is None:
        return None
    return [(x.action.strip().rstrip("."), x.camera.strip().rstrip("."), x.light.strip().rstrip(".")) for x in res.data.shots]


def build(concept_type: str, brand: str, product: str, category: str, segment: str, tone: list[str],
          colours: list[str], first_feature: str = "", hook: str = "", angle: str = "", scene: str = "") -> dict:
    directed = _director(concept_type, brand, product, category, segment, tone, first_feature, hook, angle, scene)
    tone_txt = ", ".join(t for t in tone if t)[:80] or "clean, modern"
    default_light = "soft natural light with warm highlights"
    if directed:
        (s1, c1, l1), (s2, c2, l2), (s3, c3, l3) = directed
    else:
        shots = _SHOTS[_family(category)].get(concept_type) or _SHOTS[_family(category)]["demo"]
        s1, s2, s3 = (x.format(p=product) for x in shots)
        c1, c2, c3 = "slow dolly-in with gentle parallax", "slow macro orbit, shallow depth of field", "slow pull-back to a steady hold"
        l1 = l2 = l3 = default_light
    col = " and ".join(c for c in colours if c)[:60]
    prompt = (
        f"Animate the attached product photo as the first frame. Vertical 9:16, 8 seconds, three shots with smooth cuts, "
        f"for {brand}'s {product}. "
        f"Shot 1 (0-3 s): {s1}. Camera: {c1}. Light: {l1}. "
        f"Shot 2 (3-6 s): {s2}. Camera: {c2}. Light: {l2}. "
        f"Shot 3 (6-8 s): {s3}. Camera: {c3}. Light: {l3}. "
        f"Mood: {tone_txt}" + (f"; colours {col}" if col else "") + ". "
        f"Keep the product identical in every frame (same shape, colour, label and logo), with no morphing or warping. "
        f"Realistic physics and smooth natural motion. Keep the top 25% and bottom 30% of the frame calm. "
        f"No on-screen text, captions, extra logos, speech or lyrics."
    )
    return {"prompt": " ".join(prompt.split()), "duration_s": 8, "aspect_ratio": "9:16",
            "directed_by": "ai" if directed else "template"}
