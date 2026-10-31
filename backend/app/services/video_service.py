"""Video ad renderer v2: Pillow draws every frame, FFmpeg encodes an H.264 MP4.

Each concept type has its own look (hook tone, product scene, benefit layout), the real product is on screen from
the first seconds, and every scene keeps moving (drifting light, floating product, shine sweep, pop-ins).

No external video API is needed. The REAL product image (from the brand's site or an upload)
is composited by code, never redrawn by AI, so the ad never misrepresents the product.

Timeline comes from the concept's 4-beat video_script (default 15 s, 9:16 1080x1920 @ 30 fps):
  hook (3s)    dark brand background, hook revealed word by word
  product (4s) real product image slides in, slow zoom, name + price
  benefit (4s) approved claims pop in one by one
  cta (4s)     brand colour end card: logo, price, pulsing CTA button, website
Scenes cross-fade into each other.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import settings

FADE = 0.35  # seconds of cross-fade between scenes


class VideoError(Exception):
    pass


# --------------------------------------------------------------------------- inputs
@dataclass
class VideoInput:
    brand_name: str
    product_name: str
    hook: str
    headline: str
    cta: str
    benefits: list[str]
    price: str | None = None
    website: str = ""
    product_image: Path | None = None
    logo: Path | None = None
    colors: dict = field(default_factory=dict)
    beats: list[dict] = field(default_factory=list)   # [{beat, seconds}]
    concept_type: str = "problem"
    images: list[Path] = field(default_factory=list)  # extra real product photos
    story_lines: list[str] = field(default_factory=list)
    ai_clip: Path | None = None                        # optional AI-generated clip used for the product + benefit scenes


# --------------------------------------------------------------------------- helpers
@lru_cache(maxsize=64)
def ffmpeg_path() -> str | None:
    """System FFmpeg if installed, otherwise the copy bundled with the imageio-ffmpeg pip package."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(settings.fonts_dir / name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def rgb(hexstr: str, default=(31, 41, 55)) -> tuple[int, int, int]:
    try:
        h = hexstr.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except Exception:
        return default


def lum(c) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def mix(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 3 * t * t - 2 * t * t * t


def palette(colors: dict) -> dict:
    cs = [rgb(colors.get(k, "")) for k in ("primary", "secondary", "accent") if colors.get(k)]
    if len(cs) < 2:
        cs = [(196, 120, 42), (31, 41, 55), (248, 245, 240)]
    dark = min(cs, key=lum)
    light = max(cs, key=lum)
    pop = rgb(colors.get("primary", ""), cs[0])
    if lum(dark) > 90:
        dark = mix(dark, (0, 0, 0), 0.6)
    if lum(light) < 200:
        light = mix(light, (255, 255, 255), 0.75)
    if pop in (dark, light):
        pop = mix(dark, light, 0.5)
    return {"dark": dark, "light": light, "pop": pop, "ink": mix(dark, (0, 0, 0), 0.2)}


def vgradient(w: int, h: int, top, bottom) -> Image.Image:
    g = Image.new("RGB", (1, h))
    for y in range(h):
        g.putpixel((0, y), mix(top, bottom, y / max(1, h - 1)))
    return g.resize((w, h))


def radial_glow(size: int, color, alpha: int) -> Image.Image:
    g = Image.new("L", (size, size), 0)
    ImageDraw.Draw(g).ellipse([size * 0.3, size * 0.3, size * 0.7, size * 0.7], fill=alpha)
    g = g.filter(ImageFilter.GaussianBlur(size * 0.11))   # fades to zero well before the square's edge
    out = Image.new("RGBA", (size, size), color + (0,))
    out.putalpha(g)
    return out


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if f.getlength(test) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_font(text: str, name: str, size: int, max_w: int, max_lines: int, min_size: int = 40) -> tuple:
    while size > min_size:
        f = font(name, size)
        lines = wrap(text, f, max_w)
        if len(lines) <= max_lines and all(f.getlength(l) <= max_w for l in lines):
            return f, lines
        size -= 4
    f = font(name, min_size)
    return f, wrap(text, f, max_w)[:max_lines]


def text_img(text: str, f: ImageFont.FreeTypeFont, color) -> Image.Image:
    """Text on a fixed line box (ascent + descent) so every word shares the same baseline."""
    ascent, descent = f.getmetrics()
    w = int(f.getlength(text)) + 6
    im = Image.new("RGBA", (max(1, w), ascent + descent + 4), color + (0,))
    ImageDraw.Draw(im).text((2, 2), text, font=f, fill=color + (255,), anchor="la")
    return im


def with_alpha(im: Image.Image, a: float) -> Image.Image:
    if a >= 0.999:
        return im
    out = im.copy()
    out.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return out


def paste(base: Image.Image, im: Image.Image, x: float, y: float, a: float = 1.0) -> None:
    if a <= 0.01:
        return
    im = with_alpha(im, a)
    base.paste(im, (int(x), int(y)), im)


def pill(w: int, h: int, fill, radius: int | None = None) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius if radius is not None else h // 2,
                                         fill=tuple(fill) + (255,) if len(fill) == 3 else fill)
    return im


def load_product(path: Path | None, max_w: int, max_h: int) -> Image.Image | None:
    if not path or not Path(path).exists():
        return None
    im = Image.open(path).convert("RGBA")
    alpha = im.getchannel("A")
    has_alpha = alpha.getextrema()[0] < 250
    if has_alpha:
        box = alpha.getbbox()
        if box:
            im = im.crop(box)
    im.thumbnail((max_w, max_h), Image.LANCZOS)
    if not has_alpha:  # photo without transparency: put it on a rounded card
        pad = 24
        card = Image.new("RGBA", (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
        mask = Image.new("L", card.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=36, fill=255)
        card.paste(Image.new("RGBA", card.size, (255, 255, 255, 255)), (0, 0), mask)
        card.paste(im, (pad, pad), im)
        im = card
    return im


def shadow(w: int, h: int, alpha: int = 90) -> Image.Image:
    s = Image.new("RGBA", (w * 2, h * 4), (0, 0, 0, 0))
    ImageDraw.Draw(s).ellipse([w * 0.5, h * 1.5, w * 1.5, h * 2.5], fill=(30, 15, 5, alpha))
    return s.filter(ImageFilter.GaussianBlur(h * 0.5))



# --------------------------------------------------------------------------- optional AI clip
def probe_clip(path: Path) -> float | None:
    """Duration in seconds if FFmpeg can read the file, else None (not a video)."""
    import re
    ff = ffmpeg_path()
    if not ff:
        return None
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m or "Video:" not in r.stderr:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def extract_clip_frames(clip: Path, w: int, h: int, fps: int, seconds: float, dest: Path) -> list[Path]:
    """Decode the clip into W x H JPEG frames (cover-cropped to the video frame, audio dropped)."""
    ff = ffmpeg_path()
    if not ff:
        raise VideoError("FFmpeg is not installed or not on PATH.")
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-loglevel", "error", "-i", str(clip), "-t", f"{seconds:.2f}", "-an", "-vf",
           f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}", "-q:v", "3",
           str(dest / "%04d.jpg")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    frames = sorted(dest.glob("*.jpg"))
    if r.returncode != 0 or not frames:
        raise VideoError(f"Could not read the AI clip: {r.stderr[-300:]}")
    return frames

# --------------------------------------------------------------------------- renderer
# One visual style per concept type, so five concepts never look like the same template.
STYLES = {
    "problem":           {"tone": "dark", "serif": False, "layout": "callouts", "num": False},
    "demo":              {"tone": "pop",  "serif": False, "layout": "callouts", "num": True},
    "storytelling":      {"tone": "warm", "serif": True,  "layout": "story",    "num": False},
    "offer":             {"tone": "dark", "serif": False, "layout": "chips",    "num": False},
    "testimonial-style": {"tone": "warm", "serif": False, "layout": "quote",    "num": False},
}


def overshoot(t: float) -> float:
    """0 -> 1 with a small bounce, for pop-in elements."""
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


@lru_cache(maxsize=8)
def _grid(w: int, h: int):
    import numpy as np
    return np.mgrid[0:h, 0:w]


def shine(im: Image.Image, prog: float, strength: float = 0.5) -> Image.Image:
    """A light band sweeping across an RGBA image, only where the image is opaque."""
    import numpy as np
    if prog <= 0 or prog >= 1:
        return im
    a = np.asarray(im.convert("RGBA"), dtype=np.uint8)
    h, w = a.shape[:2]
    yy, xx = _grid(w, h)
    pos = (prog * 1.5 - 0.25) * (w + h * 0.4)
    band = np.clip(1 - np.abs((xx + yy * 0.4) - pos) / (w * 0.16), 0, 1) * strength
    rgb = a[..., :3].astype(np.float32)
    rgb = rgb + (255 - rgb) * band[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a[..., 3]]).astype(np.uint8), "RGBA")


def split_sentences(text: str, limit: int = 3, max_len: int = 90) -> list[str]:
    import re
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text or "") if p.strip()]
    out = []
    for p in parts:
        if len(p) > max_len:
            p = p[:max_len].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        out.append(p)
    return out[:limit]


class Renderer:
    def __init__(self, v: VideoInput, w: int, h: int, fps: int, clip_frames: list[Path] | None = None):
        self.v, self.W, self.H, self.fps = v, w, h, fps
        self.clip_frames = clip_frames or []
        self.s = w / 1080 if h / w >= 1.7 else min(w / 1080, h / 1920 * 1.3)
        self.p = palette(v.colors)
        self.style = STYLES.get(v.concept_type, STYLES["problem"])
        beats = {b.get("beat"): float(b.get("seconds") or 0) for b in v.beats}
        self.durs = [beats.get(k) or d for k, d in (("hook", 3.0), ("product", 4.0), ("benefit", 4.0), ("cta", 4.0))]
        self.starts = [sum(self.durs[:i]) for i in range(4)]
        self.total = sum(self.durs)
        self.placeholder = False
        self._prepare()
        if self.clip_frames:
            self._prepare_ai()

    # ---- shared pieces
    def _blob(self, color, alpha):
        return radial_glow(int(self.W * 0.95), color, alpha)

    def _anim_bg(self, base: Image.Image, t: float, blob: Image.Image, blob2: Image.Image | None = None) -> Image.Image:
        W, H = self.W, self.H
        f = base.copy()
        f.paste(blob, (int(W * 0.5 - blob.width / 2 + math.sin(t * 0.9) * W * 0.22),
                       int(H * 0.28 - blob.height / 2 + math.cos(t * 0.7) * H * 0.05)), blob)
        b2 = blob2 or blob
        f.paste(b2, (int(W * 0.5 - b2.width / 2 + math.cos(t * 0.6 + 1) * W * 0.25),
                     int(H * 0.78 - b2.height / 2 + math.sin(t * 0.8) * H * 0.05)), b2)
        return f

    def _placeholder_tile(self) -> Image.Image:
        """No real photo available: a clean brand packshot tile (never a fake product drawing)."""
        W, H, s, p, v = self.W, self.H, self.s, self.p, self.v
        w, h = int(W * 0.56), int(H * 0.32)
        tile = Image.fromarray(__import__("numpy").asarray(vgradient(w, h, p["pop"], mix(p["pop"], p["dark"], 0.55))))
        tile = tile.convert("RGBA")
        d = ImageDraw.Draw(tile)
        r = int(h * 0.17)
        cx, cy = w // 2, int(h * 0.36)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=p["light"] + (255,))
        mf = font("Lora-Variable.ttf", int(r * 1.25), 600)
        ini = (v.brand_name.strip()[:1] or "A").upper()
        d.text((cx, cy), ini, font=mf, fill=p["ink"] + (255,), anchor="mm")
        nf, lines = fit_font(v.product_name, "Poppins-Bold.ttf", int(46 * s), int(w * 0.84), 2, int(28 * s))
        yy = int(h * 0.66)
        for ln in lines:
            d.text((w // 2, yy), ln, font=nf, fill=p["light"] + (255,), anchor="mm")
            yy += int(nf.size * 1.25)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(44 * s), fill=255)
        tile.putalpha(mask)
        self.placeholder = True
        return tile

    # ---- static assets per scene (rendered once)
    def _prepare(self) -> None:
        W, H, s, p, v = self.W, self.H, self.s, self.p, self.v
        st = self.style
        side = int(80 * s)
        self.max_text_w = W - 2 * side
        tone = st["tone"]
        self.on_dark = tone in ("dark", "pop")
        self.txt = p["light"] if self.on_dark else p["ink"]

        imgs = [load_product(pth, int(W * 0.66), int(H * 0.44)) for pth in ([v.product_image] if v.product_image else []) + list(v.images)]
        imgs = [i for i in imgs if i is not None]
        self.main = imgs[0] if imgs else self._placeholder_tile()
        self.second = None
        if len(imgs) > 1 and v.concept_type != "offer":
            sec = imgs[1].copy()
            sec.thumbnail((int(W * 0.30), int(H * 0.19)), Image.LANCZOS)
            self.second = sec.rotate(-6, expand=True, resample=Image.BICUBIC)
        # blurred full-bleed backdrop from the real photo (storytelling)
        self.cover = None
        for pth in ([v.product_image] if v.product_image else []) + list(v.images):
            if pth and Path(pth).exists():
                try:
                    raw = Image.open(pth).convert("RGB")
                    small = raw.copy(); small.thumbnail((200, 360))
                    small = small.filter(ImageFilter.GaussianBlur(8)).resize((W, H), Image.BILINEAR)
                    self.cover = Image.blend(small, Image.new("RGB", (W, H), p["dark"]), 0.45)
                    break
                except Exception:  # noqa: BLE001
                    pass

        self.glow_pop = self._blob(p["pop"], 120)
        self.glow_light = self._blob(p["light"], 90)
        self.prod_shadow = shadow(int(self.main.width * 0.8), int(60 * s))
        mfont = font("Lora-Variable.ttf", int(46 * s), 600)
        self.brand_light = text_img(v.brand_name, mfont, p["light"])
        self.brand_ink = text_img(v.brand_name, mfont, p["ink"])
        self.brand_txt = self.brand_light if self.on_dark else self.brand_ink

        # ---- hook
        if tone == "dark":
            self.bg1 = vgradient(W, H, mix(p["dark"], p["pop"], 0.12), mix(p["dark"], (0, 0, 0), 0.35))
        elif tone == "pop":
            self.bg1 = vgradient(W, H, p["pop"], mix(p["pop"], p["dark"], 0.55))
        else:
            self.bg1 = vgradient(W, H, p["light"], mix(p["light"], p["pop"], 0.25))
        fam = "Lora-Variable.ttf" if st["serif"] else "Poppins-Bold.ttf"
        hf, lines = fit_font(v.hook, fam, int(100 * s), self.max_text_w, 5, int(56 * s))
        if st["serif"]:
            hf = font(fam, hf.size, 600)
        self.hook_words: list[tuple[Image.Image, int, int]] = []
        lh = int(hf.size * 1.22)
        y0 = int(H * 0.36 - lh * len(lines) / 2)
        space = hf.getlength(" ")
        for li, line in enumerate(lines):
            x = (W - hf.getlength(line)) / 2
            for word in line.split():
                self.hook_words.append((text_img(word, hf, self.txt), int(x), y0 + li * lh))
                x += hf.getlength(word) + space
        a_, d_ = hf.getmetrics()
        self.hook_bottom = y0 + (len(lines) - 1) * lh + a_ + d_ + int(20 * s)
        self.quote_mark = text_img("“", font("Poppins-Bold.ttf", int(280 * s)), p["pop"]) \
            if v.concept_type == "testimonial-style" else None
        peek = self.main.copy()
        peek.thumbnail((int(W * 0.62), int(H * 0.34)), Image.LANCZOS)
        self.peek = peek

        # ---- product scene
        self.bg2 = vgradient(W, H, p["light"], mix(p["light"], p["pop"], 0.18))
        nf, nlines = fit_font(v.product_name, "Lora-Variable.ttf", int(70 * s), self.max_text_w, 2, int(44 * s))
        nf = font("Lora-Variable.ttf", nf.size, 600)
        self.name_imgs = [text_img(l, nf, p["light"] if st["layout"] == "story" and self.cover is not None else p["ink"]) for l in nlines]
        self.name_lh = int(nf.size * 1.2)
        self.price_chip = None
        if v.price:
            t = text_img(v.price, font("Poppins-Medium.ttf", int(46 * s)), p["light"])
            chip = pill(t.width + int(64 * s), t.height + int(36 * s), p["pop"])
            chip.paste(t, (int(32 * s), int(18 * s)), t)
            self.price_chip = chip
        self.tag_img = None
        if v.concept_type == "offer" and v.price:
            self.tag_img = text_img(v.price, font("Poppins-Bold.ttf", int(54 * s)), p["light"])

        # ---- benefits
        from .text_utils import jaccard, strip_brand
        self.bg3 = vgradient(W, H, mix(p["light"], p["pop"], 0.10), p["light"])
        self.bg3_dark = vgradient(W, H, mix(p["dark"], p["pop"], 0.25), mix(p["dark"], (0, 0, 0), 0.3))
        title = v.headline
        if any(jaccard(title, b) > 0.5 for b in v.benefits):
            title = f"Why {strip_brand(v.product_name, v.brand_name)}"
        self.dark3 = st["layout"] == "story" or v.concept_type == "demo"
        self.title_text = title
        tcol = p["light"] if self.dark3 else p["ink"]
        tf, tlines = fit_font(title, "Poppins-Bold.ttf", int(64 * s), self.max_text_w, 2, int(42 * s))
        self.title_imgs = [text_img(l, tf, tcol) for l in tlines]
        self.title_lh = int(tf.size * 1.2)
        bf = font("Poppins-Medium.ttf", int(42 * s))
        self.chips = []
        chip_w = self.max_text_w if st["layout"] == "chips" else int(self.max_text_w * 0.9)
        for i, b in enumerate(v.benefits[:3]):
            bl = wrap(b, bf, chip_w - int(150 * s))[:2]
            ch = int(bf.size * 1.3 * len(bl) + 56 * s)
            c = pill(chip_w, ch, (255, 255, 255, 240), radius=int(36 * s))
            d = ImageDraw.Draw(c)
            r = int(26 * s)
            cx, cy = int(56 * s), ch // 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=p["pop"])
            if st["num"]:
                d.text((cx, cy), str(i + 1), font=font("Poppins-Bold.ttf", int(34 * s)), fill=p["light"], anchor="mm")
            else:
                d.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)],
                       fill=p["light"], width=max(3, int(6 * s)), joint="curve")
            yy = (ch - bf.size * 1.3 * len(bl)) / 2
            for ln in bl:
                d.text((int(110 * s), yy), ln, font=bf, fill=p["ink"])
                yy += bf.size * 1.3
            self.chips.append(c)
        mid = self.main.copy()
        mid.thumbnail((int(W * 0.50), int(H * 0.27)), Image.LANCZOS)
        self.mid = mid
        # story lines (storytelling) / quote (testimonial-style)
        sf = font("Lora-Variable.ttf", int(62 * s), 600)
        self.story = []
        for ln in v.story_lines[:3]:
            for part in wrap(ln, sf, self.max_text_w)[:3]:
                self.story.append(text_img(part, sf, p["light"]))
            self.story.append(None)  # paragraph gap
        self.story_lh = int(sf.size * 1.3)
        qf = font("Poppins-Medium.ttf", int(50 * s))
        qlines = wrap(" ".join(v.story_lines[:2]) or v.hook, qf, int(self.max_text_w - 120 * s))[:6]
        self.quote_lines = [text_img(l, qf, p["ink"]) for l in qlines]
        self.quote_lh = int(qf.size * 1.4)
        dis = text_img("DRAMATIZED · NOT A REAL CUSTOMER REVIEW", font("Poppins-Medium.ttf", int(30 * s)), p["light"])
        self.dis_pill = pill(dis.width + int(56 * s), dis.height + int(26 * s), p["ink"])
        self.dis_pill.paste(dis, (int(28 * s), int(13 * s)), dis)

        # ---- CTA end card
        self.bg4 = vgradient(W, H, p["pop"], mix(p["pop"], p["dark"], 0.45))
        if v.logo and Path(v.logo).exists():
            logo = Image.open(v.logo).convert("RGBA")
            box = logo.getchannel("A").getbbox()
            if box:
                logo = logo.crop(box)
            logo.thumbnail((int(W * 0.5), int(H * 0.09)), Image.LANCZOS)
            card = pill(logo.width + int(96 * s), logo.height + int(72 * s), p["light"], radius=int(40 * s))
            card.paste(logo, (int(48 * s), int(36 * s)), logo)
            self.logo_card = card
        else:
            self.logo_card = text_img(v.brand_name, font("Lora-Variable.ttf", int(84 * s), 600), p["light"])
        endp = self.main.copy()
        endp.thumbnail((int(W * 0.44), int(H * 0.24)), Image.LANCZOS)
        self.end_product = endp
        tg = fit_font(v.headline, "Poppins-Bold.ttf", int(56 * s), self.max_text_w, 2, int(38 * s))
        self.tagline = [text_img(l, tg[0], p["light"]) for l in tg[1]]
        self.tag_lh = int(tg[0].size * 1.2)
        ct = text_img(v.cta, font("Poppins-Bold.ttf", int(62 * s)), p["ink"])
        self.button = pill(ct.width + int(120 * s), ct.height + int(64 * s), p["light"])
        self.button.paste(ct, (int(60 * s), int(32 * s)), ct)
        self.end_price = text_img(v.price, font("Poppins-Medium.ttf", int(54 * s)), p["light"]) if v.price else None
        domain = urlparse(v.website).hostname or v.website
        self.domain = text_img(domain.replace("www.", ""), font("Poppins-Regular.ttf", int(40 * s)), p["light"]) if domain else None
        aw = int(70 * s)
        self.arrow = Image.new("RGBA", (aw, int(aw * 0.7)), (0, 0, 0, 0))
        ImageDraw.Draw(self.arrow).line([(aw * 0.12, aw * 0.12), (aw * 0.5, aw * 0.52), (aw * 0.88, aw * 0.12)],
                                        fill=p["light"] + (255,), width=max(4, int(9 * s)), joint="curve")
        self.disclosure = None
        if v.concept_type == "testimonial-style":
            self.disclosure = text_img("Dramatization, not a real customer review",
                                       font("Poppins-Regular.ttf", int(30 * s)), p["light"])

    # ---- scenes: each returns an RGB frame for local time t
    def hook(self, t: float) -> Image.Image:
        W, H, s, p = self.W, self.H, self.s, self.p
        f = self._anim_bg(self.bg1, t, self.glow_light if self.style["tone"] == "pop" else self.glow_pop)
        paste(f, self.brand_txt, int(80 * s), int(120 * s), 0.85 * ease_out(t / 0.5))
        if self.quote_mark is not None:
            paste(f, self.quote_mark, int(70 * s), int(H * 0.18) + (1 - ease_out(t / 0.5)) * 30 * s, 0.9 * ease_out(t / 0.5))
        for i, (im, x, y) in enumerate(self.hook_words):
            k = ease_out((t - 0.12 - i * 0.10) / 0.28)
            paste(f, im, x, y + (1 - k) * 34 * s, k)
        done = 0.12 + len(self.hook_words) * 0.10 + 0.2
        k = ease_out((t - done) / 0.5)
        if k > 0:
            bw = int(W * 0.24 * k)
            ImageDraw.Draw(f).rounded_rectangle([(W - bw) / 2, self.hook_bottom, (W + bw) / 2,
                                                 self.hook_bottom + int(12 * s)], radius=int(6 * s), fill=p["pop"] if self.style["tone"] != "pop" else p["light"])
        # the real product is on screen from the first seconds
        kp = ease_out((t - 0.9) / 0.8)
        pk = self.peek
        y = H - pk.height * 0.78 + (1 - kp) * pk.height * 0.9 + math.sin(t * 2.2) * 6 * s
        paste(f, shine(pk, (t - 1.6) / 1.2, 0.45), (W - pk.width) / 2, y, kp)
        return f

    def product_scene(self, t: float) -> Image.Image:
        W, H, s, p, d = self.W, self.H, self.s, self.p, self.durs[1]
        if self.cover is not None and self.style["layout"] == "story":
            f = self.cover.copy()
        else:
            f = self._anim_bg(self.bg2, t, self.glow_pop, self.glow_light)
        paste(f, self.brand_light if self.cover is not None and self.style["layout"] == "story" else self.brand_ink,
              int(80 * s), int(120 * s), 0.8)
        k = ease_out(t / 0.8)
        zoom = (0.88 + 0.12 * k) * (1 + 0.06 * ease_in_out(t / d))
        pw, ph = int(self.main.width * zoom), int(self.main.height * zoom)
        im = shine(self.main.resize((pw, ph), Image.BILINEAR), (t - 1.0) / 1.4, 0.5)
        cx, base_y = W / 2, H * 0.60
        bob = math.sin(t * 2.0) * 7 * s
        if self.tag_img is not None:   # offer: spinning price burst behind the product
            self._burst(f, t)
        sh = self.prod_shadow
        paste(f, sh, cx - sh.width / 2, base_y - sh.height / 2, k)
        paste(f, im, cx - pw / 2, base_y - ph + (1 - k) * 140 * s + bob, k)
        if self.second is not None:
            k2 = ease_out((t - 1.0) / 0.6)
            paste(f, self.second, W * 0.66 + (1 - k2) * 300 * s, H * 0.17 + math.sin(t * 1.7) * 6 * s, k2)
        y = H * 0.69
        for i, n in enumerate(self.name_imgs):
            kk = ease_out((t - 0.45) / 0.5)
            paste(f, n, (W - n.width) / 2, y + i * self.name_lh + (1 - kk) * 24 * s, kk)
        if self.price_chip is not None:
            kk = overshoot((t - 0.8) / 0.55)
            c = self.price_chip
            sc = max(0.01, kk)
            c2 = c.resize((max(1, int(c.width * sc)), max(1, int(c.height * sc))), Image.BILINEAR)
            paste(f, c2, (W - c2.width) / 2, y + len(self.name_imgs) * self.name_lh + 30 * s, min(1, kk))
        return f

    def _burst(self, f: Image.Image, t: float) -> None:
        W, H, s, p = self.W, self.H, self.s, self.p
        k = overshoot((t - 0.7) / 0.6)
        if k <= 0.02:
            return
        R = int(190 * s * k)
        size = R * 2 + 4
        layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pts = []
        n = 18
        ang0 = t * 0.6
        for i in range(n * 2):
            r = R if i % 2 == 0 else R * 0.82
            a = ang0 + i * math.pi / n
            pts.append((size / 2 + r * math.cos(a), size / 2 + r * math.sin(a)))
        ImageDraw.Draw(layer).polygon(pts, fill=p["pop"] + (255,))
        paste(f, layer, W * 0.80 - size / 2, H * 0.22 - size / 2, 1)
        tg = self.tag_img
        paste(f, tg, W * 0.80 - tg.width / 2, H * 0.22 - tg.height / 2, min(1, k))

    def benefit_scene(self, t: float) -> Image.Image:
        lay = self.style["layout"]
        return {"callouts": self._b_callouts, "story": self._b_story, "quote": self._b_quote,
                "chips": self._b_chips}[lay](t)

    def _titles(self, f, t, y):
        W, s = self.W, self.s
        for i, ti in enumerate(self.title_imgs):
            kk = ease_out((t - 0.15) / 0.45)
            paste(f, ti, (W - ti.width) / 2, y + i * self.title_lh + (1 - kk) * 20 * s, kk)
        return y + len(self.title_imgs) * self.title_lh

    def _b_callouts(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        dark = self.v.concept_type == "demo"
        f = self._anim_bg(self.bg3_dark if dark else self.bg3, t, self.glow_pop, self.glow_light if not dark else self.glow_pop)
        paste(f, self.brand_light if dark else self.brand_ink, int(80 * s), int(120 * s), 0.8)
        y = self._titles(f, t, H * 0.15)
        m = self.mid
        k = ease_out(t / 0.5)
        paste(f, shine(m, (t - 0.6) / 1.4, 0.45), (W - m.width) / 2, y + 30 * s + math.sin(t * 2.2) * 9 * s, k)
        y = y + 30 * s + m.height + 50 * s
        for i, c in enumerate(self.chips):
            kk = overshoot((t - 0.5 - i * 0.5) / 0.5)
            side = (W - self.max_text_w) / 2
            tx = side if i % 2 == 0 else W - side - c.width
            start = -c.width if i % 2 == 0 else W
            paste(f, c, start + (tx - start) * min(1.15, max(0, kk)), y, min(1, kk * 1.5))
            y += c.height + 26 * s
        return f

    def _b_chips(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self._anim_bg(self.bg3, t, self.glow_pop, self.glow_light)
        paste(f, self.brand_ink, int(80 * s), int(120 * s), 0.8)
        sp = self.mid
        paste(f, shine(sp, (t - 0.5) / 1.4, 0.45), (W - sp.width) / 2, H * 0.10 + math.sin(t * 2.2) * 8 * s, ease_out(t / 0.4))
        y = self._titles(f, t, H * 0.10 + sp.height + 50 * s) + 50 * s
        x0 = (W - self.max_text_w) / 2
        for i, c in enumerate(self.chips):
            kk = ease_out((t - 0.45 - i * 0.45) / 0.45)
            paste(f, c, x0 - (1 - kk) * 70 * s, y, kk)
            y += c.height + 28 * s
        return f

    def _b_story(self, t: float) -> Image.Image:
        W, H, s, p = self.W, self.H, self.s, self.p
        base = self.cover.copy() if self.cover is not None else vgradient(W, H, mix(p["dark"], p["pop"], 0.25), p["dark"])
        f = self._anim_bg(base, t, self.glow_pop, self.glow_pop)
        paste(f, self.brand_light, int(80 * s), int(120 * s), 0.8)
        y = H * 0.20
        idx = 0
        for im in self.story:
            if im is None:
                y += self.story_lh * 0.45
                continue
            k = ease_out((t - 0.2 - idx * 0.42) / 0.5)
            paste(f, im, (W - im.width) / 2, y + (1 - k) * 26 * s, k)
            y += self.story_lh
            idx += 1
        m = self.mid
        paste(f, shine(m, (t - 1.0) / 1.4, 0.45), (W - m.width) / 2, H * 0.80 - m.height / 2 + math.sin(t * 2.0) * 8 * s,
              ease_out((t - 1.0) / 0.6))
        return f

    def _b_quote(self, t: float) -> Image.Image:
        W, H, s, p = self.W, self.H, self.s, self.p
        f = self._anim_bg(self.bg3, t, self.glow_pop, self.glow_light)
        paste(f, self.brand_ink, int(80 * s), int(120 * s), 0.8)
        kk = ease_out(t / 0.5)
        paste(f, self.dis_pill, (W - self.dis_pill.width) / 2, H * 0.17 + (1 - kk) * 20 * s, kk)
        ch = int(self.quote_lh * len(self.quote_lines) + 150 * s)
        card = pill(self.max_text_w, ch, (255, 255, 255, 245), radius=int(48 * s))
        d = ImageDraw.Draw(card)
        d.text((int(44 * s), int(-30 * s)), "“", font=font("Poppins-Bold.ttf", int(220 * s)), fill=p["pop"] + (255,))
        yy = int(110 * s)
        for i, l in enumerate(self.quote_lines):
            prog = max(0.0, min(1.0, (t - 0.4 - i * 0.35) / 0.4))
            if prog > 0:
                card.paste(l.crop((0, 0, max(1, int(l.width * prog)), l.height)), (int(60 * s), yy),
                           l.crop((0, 0, max(1, int(l.width * prog)), l.height)))
            yy += self.quote_lh
        paste(f, card, (W - card.width) / 2, H * 0.24 + (1 - kk) * 40 * s, kk)
        m = self.mid
        paste(f, shine(m, (t - 1.2) / 1.4, 0.45), (W - m.width) / 2, H * 0.24 + ch + 60 * s + math.sin(t * 2) * 8 * s,
              ease_out((t - 0.9) / 0.5))
        return f

    def cta_scene(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self._anim_bg(self.bg4, t, self.glow_light, self.glow_light)
        lc = self.logo_card
        k = ease_out(t / 0.5)
        paste(f, lc, (W - lc.width) / 2, H * 0.09 + (1 - k) * 30 * s, k)
        ep = self.end_product
        k2 = ease_out((t - 0.2) / 0.6)
        scale = 1 + 0.03 * math.sin(t * 1.6)
        e2 = ep.resize((int(ep.width * scale), int(ep.height * scale)), Image.BILINEAR)
        paste(f, shine(e2, (t % 2.0) / 2.0, 0.4), (W - e2.width) / 2, H * 0.21 + (1 - k2) * 60 * s, k2)
        y = H * 0.21 + ep.height + 40 * s
        for i, tl in enumerate(self.tagline):
            kk = ease_out((t - 0.4 - i * 0.12) / 0.4)
            paste(f, tl, (W - tl.width) / 2, y + i * self.tag_lh + (1 - kk) * 20 * s, kk)
        y += len(self.tagline) * self.tag_lh + 20 * s
        if self.end_price is not None:
            k3 = ease_out((t - 0.6) / 0.4)
            paste(f, self.end_price, (W - self.end_price.width) / 2, y, k3)
            y += self.end_price.height + 36 * s
        k4 = overshoot((t - 0.8) / 0.5)
        pulse = 1 + 0.04 * (0.5 + 0.5 * math.sin((t - 0.8) * 5.2)) * (1 if t > 1.2 else 0)
        sc = max(0.01, k4) * pulse
        b = shine(self.button, ((t - 1.2) % 1.6) / 1.6 if t > 1.2 else 0, 0.55)
        b = b.resize((max(1, int(b.width * sc)), max(1, int(b.height * sc))), Image.BILINEAR)
        paste(f, b, (W - b.width) / 2, y, min(1, k4))
        paste(f, self.arrow, (W - self.arrow.width) / 2, y + b.height + 14 * s + abs(math.sin(t * 3.2)) * 18 * s,
              ease_out((t - 1.4) / 0.4))
        if self.domain is not None:
            paste(f, self.domain, (W - self.domain.width) / 2, H * 0.86, 0.9 * ease_out((t - 0.8) / 0.5))
        if self.disclosure is not None:
            paste(f, self.disclosure, (W - self.disclosure.width) / 2, H * 0.92, 0.85)
        return f

    # ---- optional AI-clip mode (product + benefit scenes play the AI clip; our text sits on top)
    def _prepare_ai(self) -> None:
        W, H, s, p, v = self.W, self.H, self.s, self.p, self.v
        import numpy as np
        h2 = int(H * 0.55)
        a = (np.linspace(0, 1, h2) ** 1.6 * 200).astype("uint8")
        bottom = Image.new("RGBA", (W, h2), (0, 0, 0, 0))
        bottom.putalpha(Image.fromarray(np.repeat(a[:, None], W, axis=1), "L"))
        self.scrim_bottom = bottom
        h3 = int(H * 0.16)
        a2 = (np.linspace(1, 0, h3) ** 1.5 * 140).astype("uint8")
        top = Image.new("RGBA", (W, h3), (0, 0, 0, 0))
        top.putalpha(Image.fromarray(np.repeat(a2[:, None], W, axis=1), "L"))
        self.scrim_top = top
        nf, nl = fit_font(v.product_name, "Lora-Variable.ttf", int(70 * s), self.max_text_w, 2, int(44 * s))
        nf = font("Lora-Variable.ttf", nf.size, 600)
        self.ai_names = [text_img(l, nf, (255, 255, 255)) for l in nl]
        tf, tl = fit_font(self.title_text, "Poppins-Bold.ttf", int(64 * s), self.max_text_w, 2, int(42 * s))
        self.ai_titles = [text_img(l, tf, (255, 255, 255)) for l in tl]
        lab = text_img("AI-generated video", font("Poppins-Medium.ttf", int(28 * s)), (255, 255, 255))
        self.ai_badge = pill(lab.width + int(44 * s), lab.height + int(20 * s), (0, 0, 0, 150))
        self.ai_badge.paste(lab, (int(22 * s), int(10 * s)), lab)

    def _clip_frame(self, i: int) -> Image.Image:
        cache = self.__dict__.setdefault("_fc", {})
        if i not in cache:
            if len(cache) >= 12:
                cache.pop(next(iter(cache)))
            cache[i] = Image.open(self.clip_frames[i]).convert("RGB")
        return cache[i]

    def _clip_at(self, clip_t: float) -> Image.Image:
        n = len(self.clip_frames)
        i = int(max(0.0, clip_t) * self.fps)
        if n > 1 and i >= n:               # clip shorter than the scene: ping-pong instead of freezing
            period = 2 * (n - 1)
            i = i % period
            i = period - i if i >= n else i
        return self._clip_frame(min(i, n - 1)).copy()

    def _ai_base(self, clip_t: float, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self._clip_at(clip_t)
        f.paste(self.scrim_top, (0, 0), self.scrim_top)
        f.paste(self.scrim_bottom, (0, H - self.scrim_bottom.height), self.scrim_bottom)
        paste(f, self.brand_light, int(80 * s), int(120 * s), 0.9)
        paste(f, self.ai_badge, int(80 * s), H - int(110 * s), 0.9)
        return f

    def ai_product(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self._ai_base(t, t)
        y = H * 0.70
        for i, n in enumerate(self.ai_names):
            kk = ease_out((t - 0.4) / 0.5)
            paste(f, n, (W - n.width) / 2, y + i * self.name_lh + (1 - kk) * 24 * s, kk)
        if self.price_chip is not None:
            kk = overshoot((t - 0.8) / 0.55)
            c = self.price_chip
            sc = max(0.01, kk)
            c2 = c.resize((max(1, int(c.width * sc)), max(1, int(c.height * sc))), Image.BILINEAR)
            paste(f, c2, (W - c2.width) / 2, y + len(self.ai_names) * self.name_lh + 30 * s, min(1, kk))
        return f

    def ai_benefit(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self._ai_base(self.durs[1] + t, t)
        y = H * 0.30
        for i, ti in enumerate(self.ai_titles):
            kk = ease_out((t - 0.15) / 0.45)
            paste(f, ti, (W - ti.width) / 2, y + i * self.title_lh + (1 - kk) * 20 * s, kk)
        y += len(self.ai_titles) * self.title_lh + 36 * s
        for i, c in enumerate(self.chips):
            kk = overshoot((t - 0.5 - i * 0.5) / 0.5)
            side = (W - self.max_text_w) / 2
            tx = side if i % 2 == 0 else W - side - c.width
            start = -c.width if i % 2 == 0 else W
            paste(f, c, start + (tx - start) * min(1.15, max(0, kk)), y, min(1, kk * 1.5))
            y += c.height + 22 * s
        return f

    def _progress(self, f: Image.Image, t: float) -> Image.Image:
        W, s = self.W, self.s
        n, gap = 4, int(10 * s)
        bw = (W - 2 * int(60 * s) - gap * (n - 1)) // n
        d = ImageDraw.Draw(f, "RGBA")
        y = int(52 * s)
        for i in range(n):
            x = int(60 * s) + i * (bw + gap)
            frac = max(0.0, min(1.0, (t - self.starts[i]) / self.durs[i]))
            d.rounded_rectangle([x, y, x + bw, y + int(7 * s)], radius=int(4 * s), fill=(255, 255, 255, 70))
            if frac > 0:
                d.rounded_rectangle([x, y, x + max(int(8 * s), int(bw * frac)), y + int(7 * s)], radius=int(4 * s),
                                    fill=(255, 255, 255, 225))
        return f

    def frame(self, t: float) -> Image.Image:
        if self.clip_frames:
            scenes = (self.hook, self.ai_product, self.ai_benefit, self.cta_scene)
        else:
            scenes = (self.hook, self.product_scene, self.benefit_scene, self.cta_scene)
        idx = max(i for i in range(4) if t >= self.starts[i] - 1e-9)
        local = t - self.starts[idx]
        img = scenes[idx](local)
        nxt = idx + 1
        if nxt < 4 and t > self.starts[nxt] - FADE:
            a = (t - (self.starts[nxt] - FADE)) / FADE
            img = Image.blend(img, scenes[nxt](0.0), ease_in_out(a))
        return self._progress(img, t)


def render(v: VideoInput, out_path: Path, width: int | None = None, height: int | None = None,
           fps: int | None = None, progress: Callable[[float], None] | None = None) -> dict:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise VideoError("FFmpeg is not installed or not on PATH.")
    W, H, FPS = width or settings.video_width, height or settings.video_height, fps or settings.video_fps
    W, H = W - W % 2, H - H % 2
    frames_dir = None
    clip_frames = None
    if v.ai_clip:
        import tempfile
        frames_dir = Path(tempfile.mkdtemp(prefix="adpilot-clip-"))
        beats = {b.get("beat"): float(b.get("seconds") or 0) for b in v.beats}
        need = (beats.get("product") or 4.0) + (beats.get("benefit") or 4.0)
        clip_frames = extract_clip_frames(Path(v.ai_clip), W, H, FPS, need, frames_dir)
    r = Renderer(v, W, H, FPS, clip_frames)
    n = int(round(r.total * FPS))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".part.mp4")
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-"]
    music = Path(settings.music_path) if settings.music_path else None
    if music and music.exists():
        cmd += ["-i", str(music), "-af", f"afade=t=out:st={max(0, r.total - 1.2):.2f}:d=1.2", "-c:a", "aac",
                "-b:a", "128k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(tmp)]
    t0 = time.perf_counter()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(n):
            proc.stdin.write(r.frame(i / FPS).tobytes())  # type: ignore[union-attr]
            if progress and i % 15 == 0:
                progress(i / n)
        proc.stdin.close()  # type: ignore[union-attr]
        err = proc.stderr.read().decode(errors="replace")  # type: ignore[union-attr]
        if proc.wait(timeout=120) != 0:
            raise VideoError(f"FFmpeg failed: {err[-400:]}")
    except BrokenPipeError as exc:
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise VideoError(f"FFmpeg stopped early: {err[-400:]}") from exc
    finally:
        if proc.poll() is None:
            proc.kill()
        if frames_dir:
            shutil.rmtree(frames_dir, ignore_errors=True)
    tmp.replace(out_path)
    if progress:
        progress(1.0)
    return {"duration_s": round(r.total, 2), "width": W, "height": H, "fps": FPS, "frames": n,
            "render_ms": int((time.perf_counter() - t0) * 1000), "music": bool(music and music.exists()),
            "ai_clip": bool(v.ai_clip)}
