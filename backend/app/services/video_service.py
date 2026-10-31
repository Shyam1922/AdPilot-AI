"""Video ad renderer: Pillow draws every frame, FFmpeg encodes an H.264 MP4.

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


# --------------------------------------------------------------------------- helpers
@lru_cache(maxsize=64)
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


# --------------------------------------------------------------------------- renderer
class Renderer:
    def __init__(self, v: VideoInput, w: int, h: int, fps: int):
        self.v, self.W, self.H, self.fps = v, w, h, fps
        # scale factor for fonts and spacing: width-based for 9:16, height-based for shorter frames
        self.s = w / 1080 if h / w >= 1.7 else min(w / 1080, h / 1920 * 1.3)
        self.p = palette(v.colors)
        beats = {b.get("beat"): float(b.get("seconds") or 0) for b in v.beats}
        self.durs = [beats.get(k) or d for k, d in (("hook", 3.0), ("product", 4.0), ("benefit", 4.0), ("cta", 4.0))]
        self.starts = [sum(self.durs[:i]) for i in range(4)]
        self.total = sum(self.durs)
        self._prepare()

    # ---- static assets per scene (rendered once)
    def _prepare(self) -> None:
        W, H, s, p, v = self.W, self.H, self.s, self.p, self.v
        side = int(80 * s)
        self.max_text_w = W - 2 * side

        # Scene 1: hook on dark
        self.bg1 = vgradient(W, H, mix(p["dark"], p["pop"], 0.12), mix(p["dark"], (0, 0, 0), 0.35))
        self.glow1 = radial_glow(int(W * 1.1), p["pop"], 150)
        hf, lines = fit_font(v.hook, "Poppins-Bold.ttf", int(96 * s), self.max_text_w, 5, int(56 * s))
        self.hook_words: list[tuple[Image.Image, int, int]] = []
        lh = int(hf.size * 1.22)
        total_h = lh * len(lines)
        y0 = int(H * 0.44 - total_h / 2)
        space = hf.getlength(" ")
        for li, line in enumerate(lines):
            x = (W - hf.getlength(line)) / 2
            for word in line.split():
                self.hook_words.append((text_img(word, hf, p["light"]), int(x), y0 + li * lh))
                x += hf.getlength(word) + space
        ascent, descent = hf.getmetrics()
        self.hook_bottom = y0 + (len(lines) - 1) * lh + ascent + descent + int(20 * s)
        self.brand_mark_light = text_img(v.brand_name, font("Lora-Variable.ttf", int(46 * s), 600), p["light"])
        self.brand_mark_dark = text_img(v.brand_name, font("Lora-Variable.ttf", int(46 * s), 600), p["ink"])

        # Scene 2: product on light
        bg2 = vgradient(W, H, p["light"], mix(p["light"], p["pop"], 0.18))
        glow = radial_glow(int(W * 1.0), p["pop"], 110)
        bg2.paste(glow, (int((W - glow.width) / 2), int(H * 0.40 - glow.height / 2)), glow)
        self.bg2 = bg2
        self.product = load_product(v.product_image, int(W * 0.66), int(H * 0.46))
        if self.product is None:  # no image at all: a clean name card (never a fake product drawing)
            card_f = font("Lora-Variable.ttf", int(84 * s), 600)
            lines2 = wrap(v.product_name, card_f, int(W * 0.6))
            card = Image.new("RGBA", (int(W * 0.7), int(H * 0.3)), p["pop"] + (255,))
            mask = Image.new("L", card.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, card.width - 1, card.height - 1], radius=48, fill=255)
            card.putalpha(mask)
            d = ImageDraw.Draw(card)
            yy = card.height / 2 - len(lines2) * card_f.size * 0.6
            for ln in lines2:
                d.text(((card.width - card_f.getlength(ln)) / 2, yy), ln, font=card_f, fill=p["light"])
                yy += card_f.size * 1.2
            self.product = card
        self.prod_shadow = shadow(int(self.product.width * 0.8), int(60 * s))
        nf, nlines = fit_font(v.product_name, "Lora-Variable.ttf", int(70 * s), self.max_text_w, 2, int(44 * s))
        nf = font("Lora-Variable.ttf", nf.size, 600)
        self.name_imgs = [text_img(l, nf, p["ink"]) for l in nlines]
        self.name_lh = int(nf.size * 1.2)
        if v.price:
            pf = font("Poppins-Medium.ttf", int(46 * s))
            t = text_img(v.price, pf, p["light"])
            chip = pill(t.width + int(64 * s), t.height + int(36 * s), p["pop"])
            chip.paste(t, (int(32 * s), int(18 * s)), t)
            self.price_chip = chip
        else:
            self.price_chip = None

        # Scene 3: benefits
        self.bg3 = vgradient(W, H, mix(p["light"], p["pop"], 0.10), p["light"])
        small = self.product.copy()
        small.thumbnail((int(W * 0.42), int(H * 0.26)), Image.LANCZOS)
        self.small_product = small
        from .text_utils import jaccard, strip_brand
        title = v.headline
        if any(jaccard(title, b) > 0.5 for b in v.benefits):   # don't repeat a chip as the title
            title = f"Why {strip_brand(v.product_name, v.brand_name)}"
        tf, tlines = fit_font(title, "Poppins-Bold.ttf", int(68 * s), self.max_text_w, 2, int(44 * s))
        self.title_imgs = [text_img(l, tf, p["ink"]) for l in tlines]
        self.title_lh = int(tf.size * 1.2)
        bf = font("Poppins-Medium.ttf", int(44 * s))
        self.chips = []
        chip_w = self.max_text_w
        for b in v.benefits[:3]:
            bl = wrap(b, bf, chip_w - int(150 * s))[:2]
            ch = int(bf.size * 1.3 * len(bl) + 56 * s)
            c = pill(chip_w, ch, (255, 255, 255, 235), radius=int(36 * s))
            d = ImageDraw.Draw(c)
            r = int(26 * s)
            cx, cy = int(56 * s), ch // 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=p["pop"])
            d.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)],
                   fill=p["light"], width=max(3, int(6 * s)), joint="curve")
            yy = (ch - bf.size * 1.3 * len(bl)) / 2
            for ln in bl:
                d.text((int(110 * s), yy), ln, font=bf, fill=p["ink"])
                yy += bf.size * 1.3
            self.chips.append(c)

        # Scene 4: CTA end card
        self.bg4 = vgradient(W, H, p["pop"], mix(p["pop"], p["dark"], 0.45))
        self.logo_card = None
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
        end_prod = self.product.copy()
        end_prod.thumbnail((int(W * 0.46), int(H * 0.25)), Image.LANCZOS)
        self.end_product = end_prod
        cf = font("Poppins-Bold.ttf", int(62 * s))
        ct = text_img(self.v.cta, cf, p["ink"])
        self.button = pill(ct.width + int(120 * s), ct.height + int(64 * s), p["light"])
        self.button.paste(ct, (int(60 * s), int(32 * s)), ct)
        self.end_price = text_img(v.price, font("Poppins-Medium.ttf", int(54 * s)), p["light"]) if v.price else None
        domain = urlparse(v.website).hostname or v.website
        self.domain = text_img(domain.replace("www.", ""), font("Poppins-Regular.ttf", int(40 * s)), p["light"]) \
            if domain else None

    # ---- scenes: each returns an RGB frame for local time t
    def hook(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self.bg1.copy()
        g = self.glow1
        gx = W * 0.5 - g.width / 2 + math.sin(t * 1.3) * W * 0.12
        gy = H * 0.30 - g.height / 2 + math.cos(t * 0.9) * H * 0.04
        f.paste(g, (int(gx), int(gy)), g)
        paste(f, self.brand_mark_light, int(80 * s), int(120 * s), 0.85 * ease_out(t / 0.5))
        for i, (im, x, y) in enumerate(self.hook_words):
            k = ease_out((t - 0.12 - i * 0.11) / 0.28)
            paste(f, im, x, y + (1 - k) * 34 * s, k)
        done = 0.12 + len(self.hook_words) * 0.11 + 0.2
        k = ease_out((t - done) / 0.5)
        if k > 0:
            bw = int(W * 0.24 * k)
            ImageDraw.Draw(f).rounded_rectangle([(W - bw) / 2, self.hook_bottom, (W + bw) / 2,
                                                 self.hook_bottom + int(12 * s)], radius=int(6 * s), fill=self.p["pop"])
        return f

    def product_scene(self, t: float) -> Image.Image:
        W, H, s, d = self.W, self.H, self.s, self.durs[1]
        f = self.bg2.copy()
        paste(f, self.brand_mark_dark, int(80 * s), int(120 * s), 0.8)
        k = ease_out(t / 0.8)
        zoom = (0.9 + 0.1 * k) * (1 + 0.045 * ease_in_out(t / d))
        pw, ph = int(self.product.width * zoom), int(self.product.height * zoom)
        im = self.product.resize((pw, ph), Image.BILINEAR)
        cx, base_y = W / 2, H * 0.62
        sh = self.prod_shadow
        paste(f, sh, cx - sh.width / 2, base_y - sh.height / 2, k)
        paste(f, im, cx - pw / 2, base_y - ph + (1 - k) * 140 * s, k)
        y = H * 0.70
        for i, n in enumerate(self.name_imgs):
            kk = ease_out((t - 0.45) / 0.5)
            paste(f, n, (W - n.width) / 2, y + i * self.name_lh + (1 - kk) * 24 * s, kk)
        if self.price_chip is not None:
            kk = ease_out((t - 0.8) / 0.45)
            c = self.price_chip
            paste(f, c, (W - c.width) / 2, y + len(self.name_imgs) * self.name_lh + 30 * s + (1 - kk) * 24 * s, kk)
        return f

    def benefit_scene(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self.bg3.copy()
        paste(f, self.brand_mark_dark, int(80 * s), int(120 * s), 0.8)
        sp = self.small_product
        float_y = math.sin(t * 2.2) * 8 * s
        paste(f, sp, (W - sp.width) / 2, H * 0.10 + float_y, ease_out(t / 0.4))
        y = H * 0.10 + sp.height + 50 * s
        for i, ti in enumerate(self.title_imgs):
            kk = ease_out((t - 0.15) / 0.45)
            paste(f, ti, (W - ti.width) / 2, y + i * self.title_lh + (1 - kk) * 20 * s, kk)
        y += len(self.title_imgs) * self.title_lh + 50 * s
        x0 = (W - self.max_text_w) / 2
        for i, c in enumerate(self.chips):
            kk = ease_out((t - 0.45 - i * 0.45) / 0.45)
            paste(f, c, x0 - (1 - kk) * 70 * s, y, kk)
            y += c.height + 28 * s
        return f

    def cta_scene(self, t: float) -> Image.Image:
        W, H, s = self.W, self.H, self.s
        f = self.bg4.copy()
        lc = self.logo_card
        k = ease_out(t / 0.5)
        paste(f, lc, (W - lc.width) / 2, H * 0.10 + (1 - k) * 30 * s, k)
        ep = self.end_product
        k2 = ease_out((t - 0.2) / 0.6)
        paste(f, ep, (W - ep.width) / 2, H * 0.24 + (1 - k2) * 60 * s, k2)
        y = H * 0.24 + ep.height + 60 * s
        if self.end_price is not None:
            k3 = ease_out((t - 0.45) / 0.4)
            paste(f, self.end_price, (W - self.end_price.width) / 2, y, k3)
            y += self.end_price.height + 50 * s
        k4 = ease_out((t - 0.6) / 0.4)
        pulse = 1 + 0.045 * (0.5 + 0.5 * math.sin((t - 0.6) * 5.2)) * (1 if t > 1.0 else 0)
        b = self.button.resize((int(self.button.width * pulse), int(self.button.height * pulse)), Image.BILINEAR)
        paste(f, b, (W - b.width) / 2, y + (1 - k4) * 40 * s, k4)
        if self.domain is not None:
            paste(f, self.domain, (W - self.domain.width) / 2, H * 0.80, 0.9 * ease_out((t - 0.8) / 0.5))
        return f

    def frame(self, t: float) -> Image.Image:
        scenes = (self.hook, self.product_scene, self.benefit_scene, self.cta_scene)
        idx = max(i for i in range(4) if t >= self.starts[i] - 1e-9)
        local = t - self.starts[idx]
        img = scenes[idx](local)
        nxt = idx + 1
        if nxt < 4 and t > self.starts[nxt] - FADE:
            a = (t - (self.starts[nxt] - FADE)) / FADE
            img = Image.blend(img, scenes[nxt](0.0), ease_in_out(a))
        return img


def render(v: VideoInput, out_path: Path, width: int | None = None, height: int | None = None,
           fps: int | None = None, progress: Callable[[float], None] | None = None) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VideoError("FFmpeg is not installed or not on PATH.")
    W, H, FPS = width or settings.video_width, height or settings.video_height, fps or settings.video_fps
    W, H = W - W % 2, H - H % 2
    r = Renderer(v, W, H, FPS)
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
    tmp.replace(out_path)
    if progress:
        progress(1.0)
    return {"duration_s": round(r.total, 2), "width": W, "height": H, "fps": FPS, "frames": n,
            "render_ms": int((time.perf_counter() - t0) * 1000), "music": bool(music and music.exists())}
