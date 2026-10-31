"""Render stylised product images + logo for the FICTIONAL demo brand "Velvaa Skin".

Run: python -m app.scripts.make_demo_images
Outputs transparent PNGs into sample_data/demo_store/images/.
"""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import settings

OUT = settings.sample_data_dir / "demo_store" / "images"
FONTS = settings.fonts_dir
S = 1000  # canvas


def font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def vgrad(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    g = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(4)))
    return g


def hgrad_mask_highlight(w: int, h: int) -> Image.Image:
    """Vertical glossy highlight strip for glass/plastic."""
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    for x in range(w):
        t = x / w
        a = 0
        if 0.12 < t < 0.22:
            a = int(110 * (1 - abs(t - 0.17) / 0.05))
        elif 0.78 < t < 0.86:
            a = int(45 * (1 - abs(t - 0.82) / 0.04))
        d.line([(x, 0), (x, h)], fill=max(0, a))
    return m


def body(w: int, h: int, top: tuple, bottom: tuple, radius: int) -> Image.Image:
    shape = Image.new("L", (w, h), 0)
    ImageDraw.Draw(shape).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
    fill = vgrad(w, h, top, bottom)
    hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    hl.putalpha(hgrad_mask_highlight(w, h))
    fill = Image.alpha_composite(fill, hl)
    fill.putalpha(shape)
    return fill


def shadow(canvas: Image.Image, cx: int, y: int, w: int) -> None:
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - w // 2, y - 22, cx + w // 2, y + 22], fill=(60, 30, 10, 110))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))


def label(canvas: Image.Image, box: tuple, name_lines: list[str], sub: str, accent: tuple) -> None:
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle(box, radius=14, fill=(250, 244, 234, 255))
    cx = (x0 + x1) // 2
    d.text((cx, y0 + 52), "velvaa", font=font("Lora-Variable.ttf", 54, 600), fill=(60, 34, 20), anchor="mm")
    d.line([(cx - 40, y0 + 92), (cx + 40, y0 + 92)], fill=accent, width=3)
    y = y0 + 132
    for line in name_lines:
        d.text((cx, y), line, font=font("Poppins-Medium.ttf", 30), fill=(60, 34, 20), anchor="mm")
        y += 40
    d.text((cx, y1 - 36), sub, font=font("Poppins-Regular.ttf", 22), fill=(120, 90, 70), anchor="mm")


def serum() -> Image.Image:
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx = S // 2
    shadow(c, cx, 905, 360)
    b = body(300, 430, (214, 120, 40, 255), (140, 62, 18, 255), 48)
    c.alpha_composite(b, (cx - 150, 470))
    neck = body(120, 50, (40, 30, 26, 255), (20, 16, 14, 255), 10)
    c.alpha_composite(neck, (cx - 60, 425))
    bulb = body(96, 190, (52, 40, 34, 255), (24, 18, 16, 255), 46)
    c.alpha_composite(bulb, (cx - 48, 245))
    label(c, (cx - 120, 560, cx + 120, 830), ["Saffron Dew", "Serum"], "30 ml", (214, 140, 40))
    return c


def cleanser() -> Image.Image:
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx = S // 2
    shadow(c, cx, 905, 300)
    cap = body(200, 120, (236, 236, 232, 255), (200, 200, 194, 255), 22)
    c.alpha_composite(cap, (cx - 100, 778))
    # tapered tube: draw as polygon mask
    w, h = 300, 560
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (w, 0), (w - 50, h), (50, h)], fill=255)
    tube = vgrad(w, h, (226, 236, 228, 255), (190, 214, 200, 255))
    hl = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    hl.putalpha(hgrad_mask_highlight(w, h))
    tube = Image.alpha_composite(tube, hl)
    tube.putalpha(mask)
    c.alpha_composite(tube, (cx - 150, 225))
    ImageDraw.Draw(c).rectangle([cx - 150, 225, cx + 150, 250], fill=(176, 200, 186, 255))
    label(c, (cx - 115, 330, cx + 115, 600), ["Rice Water", "Gel Cleanser"], "100 ml", (120, 170, 140))
    return c


def spf() -> Image.Image:
    c = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    cx = S // 2
    shadow(c, cx, 905, 320)
    b = body(270, 520, (255, 214, 140, 255), (238, 170, 80, 255), 70)
    c.alpha_composite(b, (cx - 135, 385))
    cap = body(170, 140, (250, 248, 242, 255), (214, 210, 200, 255), 30)
    c.alpha_composite(cap, (cx - 85, 260))
    label(c, (cx - 110, 500, cx + 110, 770), ["Sun-Kissed", "SPF 50 Fluid"], "50 ml", (230, 150, 60))
    return c


def logo() -> Image.Image:
    img = Image.new("RGBA", (600, 180), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.text((300, 82), "velvaa", font=font("Lora-Variable.ttf", 120, 600), fill=(74, 40, 22), anchor="mm")
    d.text((300, 158), "S K I N", font=font("Poppins-Medium.ttf", 26), fill=(196, 120, 40), anchor="mm")
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [("serum", serum), ("cleanser", cleanser), ("spf", spf), ("logo", logo)]:
        fn().save(OUT / f"{name}.png", optimize=True)
        print("wrote", OUT / f"{name}.png")


if __name__ == "__main__":
    main()
