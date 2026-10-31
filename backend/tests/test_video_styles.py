"""Video v2: each concept type looks different, text/motion is not limited to the first frame, copy is cleaned."""
from PIL import ImageChops, ImageStat

from app.services.video_jobs import _clean_benefits, _story_text
from app.services.video_service import STYLES, Renderer, VideoInput


def _input(ctype: str, **kw) -> VideoInput:
    return VideoInput(brand_name="Comet", product_name="Comet Everyday Tee", hook="Finding quality shouldn't be hard.",
                      headline="Simplify your search", cta="Shop now", benefits=["Soft 100% cotton feel", "Made for daily wear"],
                      price="₹799", website="https://wearcomet.com", colors={"primary": "#1f2937"},
                      concept_type=ctype, story_lines=["It started with one tee.", "Now it is a wardrobe."], **kw)


def _diff(a, b) -> float:
    """Mean absolute pixel difference (0-255)."""
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def test_every_concept_type_has_its_own_look():
    frames = {t: Renderer(_input(t), 270, 480, 30).frame(7.5) for t in STYLES}
    types = list(frames)
    for i in range(len(types)):
        for j in range(i + 1, len(types)):
            assert _diff(frames[types[i]], frames[types[j]]) > 5, (types[i], types[j])


def test_motion_continues_after_the_first_second():
    r = Renderer(_input("demo"), 270, 480, 30)
    for t in (4.5, 8.0, 12.5, 14.0):   # product, benefits and CTA scenes keep moving
        assert _diff(r.frame(t), r.frame(t + 0.4)) > 0.3, t


def test_missing_photo_uses_labelled_placeholder_not_fake_product():
    r = Renderer(_input("problem"), 270, 480, 30)
    assert r.placeholder is True


def test_testimonial_is_disclosed_and_internal_notes_removed():
    r = Renderer(_input("testimonial-style"), 270, 480, 30)
    assert r.disclosure is not None and r.dis_pill is not None
    cleaned = _story_text("(Dramatization) A normal day with it. Replace with a real review before launch.")
    assert "Dramatization" not in cleaned and "Replace" not in cleaned


def test_benefits_never_just_the_brand_name():
    out = _clean_benefits(["Comet", "Comet Everyday Tee"], "Comet", "Comet Everyday Tee",
                          {"approved_claims": [{"claim": "Soft cotton that stays soft after washes"}],
                           "value_propositions": ["Made for daily wear in warm weather"]}, "")
    assert out and all(b not in ("Comet", "Comet Everyday Tee") for b in out) and len(out) == 2
