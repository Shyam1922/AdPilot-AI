"""Website & product extraction.

Safety:
  * Only http/https, standard ports, no credentials in URL.
  * Every hop (including redirects) is DNS-resolved and rejected if it points at a
    private / loopback / link-local / reserved address (SSRF guard).
  * Size and time limits on every request.
  * Hidden elements and scripts are stripped. Page text is treated as UNTRUSTED data:
    it is never executed and the LLM is told to ignore instructions inside it.
"""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import settings

USER_AGENT = "AdPilotBot/0.1 (+brand profile builder; respects public pages only)"
PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR|\$|USD|€|£)\s?\d[\d,]*(?:\.\d{1,2})?", re.I)
HIDDEN_STYLE_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0", re.I)


class ExtractionError(Exception):
    pass


@dataclass
class ExtractionResult:
    url: str
    final_url: str = ""
    title: str = ""
    description: str = ""
    site_name: str = ""
    og_image: str = ""
    page_images: list[str] = field(default_factory=list)   # ranked candidate photos found in the page body
    logo: str = ""
    theme_color: str = ""
    products: list[dict] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    snippets: list[dict] = field(default_factory=list)   # [{id, text}] evidence the LLM can cite
    prices: list[str] = field(default_factory=list)
    text: str = ""
    removed_hidden_elements: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


# --------------------------------------------------------------------------- URL safety
def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
                or addr.is_multicast or addr.is_unspecified)


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ExtractionError("Only http(s) URLs are supported.")
    if parsed.username or parsed.password:
        raise ExtractionError("URLs with credentials are not allowed.")
    if not parsed.hostname:
        raise ExtractionError("URL has no hostname.")
    if parsed.port not in (None, 80, 443):
        raise ExtractionError("Only standard ports (80/443) are allowed.")
    if parsed.hostname == settings.demo_store_host:
        return url
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ExtractionError(f"Could not resolve host '{parsed.hostname}'.") from exc
    for info in infos:
        if not _is_public_ip(info[4][0]):
            raise ExtractionError("URL resolves to a private or reserved address; refusing to fetch.")
    return url


def _is_demo(url: str) -> bool:
    return urlparse(url).hostname == settings.demo_store_host


def _demo_path(url: str) -> Path:
    root = (settings.sample_data_dir / "demo_store").resolve()
    rel = urlparse(url).path.lstrip("/") or "index.html"
    if rel.endswith("/"):
        rel += "index.html"
    p = (root / rel).resolve()
    if root not in p.parents and p != root:
        raise ExtractionError("Invalid demo path.")
    if not p.exists():
        raise ExtractionError("Demo page not found.")
    return p


# Pages we already read are kept for a few hours, so re-analysing a brand (or a demo rehearsal) doesn't hit the
# site again: rate limits (HTTP 429) are the most common reason a site that worked suddenly refuses.
_CACHE_DIR = settings.storage_dir.parent / ".fetch_cache"
_CACHE_TTL_S = 6 * 3600


def _cache_key(url: str, accept: str) -> Path:
    return _CACHE_DIR / (hashlib.sha256(f"{url}|{accept}".encode()).hexdigest()[:40] + ".json")


def _cache_read(url: str, accept: str):
    try:
        f = _cache_key(url, accept)
        if not f.exists() or time.time() - f.stat().st_mtime > _CACHE_TTL_S:
            return None
        d = json.loads(f.read_text())
        return base64.b64decode(d["body"]), d["ctype"], d["final"]
    except (OSError, ValueError, KeyError):
        return None


def _cache_write(url: str, accept: str, result) -> None:
    try:
        _CACHE_DIR.mkdir(exist_ok=True)
        body, ctype, final = result
        _cache_key(url, accept).write_text(json.dumps({"body": base64.b64encode(body).decode(), "ctype": ctype, "final": final}))
    except OSError:
        pass


def safe_get(url: str, max_bytes: int, accept: str = "text/html,*/*") -> tuple[bytes, str, str]:
    """GET with manual redirect handling so every hop is re-validated. Returns (body, content_type, final_url)."""
    if _is_demo(url):
        p = _demo_path(url)
        ctype = "text/html" if p.suffix == ".html" else f"image/{p.suffix.lstrip('.')}"
        return p.read_bytes()[:max_bytes], ctype, url

    cached = _cache_read(url, accept)
    if cached:
        return cached

    current = url
    with httpx.Client(timeout=settings.fetch_timeout_s, follow_redirects=False,
                      headers={"User-Agent": USER_AGENT, "Accept": accept}) as client:
        for _ in range(5):
            validate_public_url(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    current = urljoin(current, resp.headers.get("location", ""))
                    continue
                if resp.status_code in (401, 403, 406, 429, 503):
                    raise ExtractionError(
                        f"This site doesn't allow automated readers (HTTP {resp.status_code}), so AdPilot can't "
                        "read it. Enter the brand details manually instead.")
                if resp.status_code >= 400:
                    raise ExtractionError(f"Site returned HTTP {resp.status_code}.")
                declared = int(resp.headers.get("content-length") or 0)
                if declared and declared > max_bytes:
                    raise ExtractionError("Response too large.")
                chunks, size = [], 0
                for chunk in resp.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ExtractionError("Response too large.")
                    chunks.append(chunk)
                result = b"".join(chunks), resp.headers.get("content-type", ""), str(resp.url)
                _cache_write(url, accept, result)
                return result
    raise ExtractionError("Too many redirects.")


# --------------------------------------------------------------------------- parsing
def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        queue = list(data) if isinstance(data, list) else [data]
        while queue:
            item = queue.pop(0)
            if isinstance(item, dict):
                if "@graph" in item and isinstance(item["@graph"], list):
                    queue = list(item["@graph"]) + queue
                yield item


def _product_from_jsonld(item: dict, base: str) -> dict | None:
    types = item.get("@type")
    types = types if isinstance(types, list) else [types]
    if "Product" not in types:
        return None
    image = item.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    offers = item.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = None
    if isinstance(offers, dict) and offers.get("price"):
        cur = offers.get("priceCurrency", "")
        price = f"{'₹' if cur == 'INR' else cur + ' ' if cur else ''}{offers['price']}".strip()
    feats = item.get("additionalProperty") or []
    features = [_clean(f"{p.get('name', '')}: {p.get('value', '')}") for p in feats if isinstance(p, dict)]
    return {
        "name": _clean(item.get("name", "")),
        "description": _clean(item.get("description", "")),
        "price": price,
        "image_url": urljoin(base, image) if isinstance(image, str) else None,
        "features": [f for f in features if f.strip(": ")],
    }



SKIP_IMG_RE = re.compile(r"(logo|icon|sprite|avatar|badge|payment|flag|pixel|tracking|spinner|loader|placeholder|"
                         r"arrow|chevron|star|rating|social|facebook|instagram|twitter|whatsapp|banner-ad|\.svg|\.gif|data:)", re.I)
GOOD_IMG_RE = re.compile(r"(product|hero|pack|bottle|shot|collection|featured|main|gallery|item|catalog)", re.I)


def _best_from_srcset(srcset: str) -> str:
    best, best_w = "", -1
    for part in (srcset or "").split(","):
        bits = part.strip().split()
        if not bits:
            continue
        try:
            w = int(bits[1].rstrip("wx")) if len(bits) > 1 else 0
        except ValueError:
            w = 0
        if w >= best_w:
            best, best_w = bits[0], w
    return best


def collect_page_images(body, base: str, limit: int = 12) -> list[str]:
    """Candidate product/hero photos from <img>, <picture> and lazy-load attributes, best-looking first."""
    scored: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for order, img in enumerate(body.find_all("img")):
        raw = (img.get("data-src") or img.get("data-original") or img.get("data-lazy-src")
               or _best_from_srcset(img.get("srcset") or img.get("data-srcset") or "") or img.get("src") or "")
        if not raw or raw.startswith("data:"):
            continue
        url = urljoin(base, raw.split(" ")[0])
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        hint = " ".join([url, " ".join(img.get("class") or []), img.get("alt") or "", img.get("id") or ""])
        if SKIP_IMG_RE.search(hint):
            continue
        try:
            w = int(str(img.get("width", "0")).rstrip("px") or 0)
        except ValueError:
            w = 0
        if 0 < w < 120:
            continue
        seen.add(url)
        score = (3 if GOOD_IMG_RE.search(hint) else 0) + (2 if w >= 400 else 0) + (1 if img.get("alt") else 0)
        scored.append((-score, order, url))
    return [u for _, _, u in sorted(scored)][:limit]


def parse_html(html: str, url: str) -> ExtractionResult:
    res = ExtractionResult(url=url, final_url=url)
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return _clean(tag["content"])
        return ""

    res.title = _clean(soup.title.string if soup.title and soup.title.string else "") or meta("og:title")
    res.description = meta("description", "og:description", "twitter:description")
    res.site_name = meta("og:site_name", "application-name")
    og_img = meta("og:image", "twitter:image")
    res.og_image = urljoin(url, og_img) if og_img else ""
    res.theme_color = meta("theme-color")
    icon = soup.find("link", rel=lambda v: v and any("icon" in r.lower() for r in (v if isinstance(v, list) else [v])))
    logo_img = soup.find("img", attrs={"class": re.compile("logo", re.I)}) or soup.find("img", alt=re.compile("logo", re.I))
    if logo_img and logo_img.get("src"):
        res.logo = urljoin(url, logo_img["src"])
    elif icon and icon.get("href"):
        res.logo = urljoin(url, icon["href"])

    for item in _iter_jsonld(soup):
        prod = _product_from_jsonld(item, url)
        if prod and prod["name"]:
            res.products.append(prod)
        if item.get("@type") == "Organization" and not res.site_name:
            res.site_name = _clean(item.get("name", ""))

    # Strip non-content and hidden elements BEFORE reading text (prompt-injection hygiene).
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe", "form"]):
        tag.decompose()
    hidden = [t for t in soup.find_all(True)
              if t.attrs is not None and (t.has_attr("hidden") or t.get("aria-hidden") == "true"
                                          or HIDDEN_STYLE_RE.search(t.get("style", "") or ""))]
    for t in hidden:
        if not t.decomposed:
            t.decompose()
    res.removed_hidden_elements = len(hidden)

    body = soup.find("main") or soup.body or soup
    res.page_images = collect_page_images(soup.body or soup, url)
    for nav in body.find_all(["nav", "footer", "header"]):
        if nav.find("h1") is None:
            nav.decompose()

    seen: set[str] = set()

    def add(lst: list[str], text: str, lo: int = 3, hi: int = 300):
        t = _clean(text)
        if lo <= len(t) <= hi and t.lower() not in seen:
            seen.add(t.lower())
            lst.append(t)

    for h in body.find_all(["h1", "h2", "h3"]):
        add(res.headings, h.get_text(" "), 2, 140)
    for li in body.find_all("li"):
        add(res.bullets, li.get_text(" "), 6, 220)
    for p in body.find_all("p"):
        add(res.paragraphs, p.get_text(" "), 25, 600)

    full_text = _clean(body.get_text(" "))
    res.prices = list(dict.fromkeys(PRICE_RE.findall(full_text)))[:10]
    res.text = full_text[:12000]

    # Evidence snippets with stable ids so the LLM (and UI) can cite sources.
    for i, text in enumerate([res.description, *res.headings, *res.bullets, *res.paragraphs]):
        if text:
            res.snippets.append({"id": f"s{i+1}", "text": text})
    res.snippets = res.snippets[:80]

    if not res.products and (res.title or res.headings):
        res.warnings.append("No structured product data (JSON-LD) found; product details inferred from page text.")
    if len(full_text) < 200:
        res.warnings.append("Very little readable text — the site may be JavaScript-rendered. Add details manually.")
    if res.removed_hidden_elements:
        res.warnings.append(f"Ignored {res.removed_hidden_elements} hidden element(s) on the page.")
    return res


def shopify_products(url: str, limit: int = 8) -> list[dict]:
    """Most Indian D2C stores run on Shopify, which publicly exposes /products.json.
    Returns [] silently when the endpoint isn't there."""
    if _is_demo(url):
        return []
    parsed = urlparse(url)
    endpoint = f"{parsed.scheme}://{parsed.netloc}/products.json?limit={limit}"
    try:
        body, ctype, _ = safe_get(endpoint, settings.max_page_bytes, accept="application/json")
        data = json.loads(body)
    except (ExtractionError, json.JSONDecodeError, httpx.HTTPError, ValueError):
        return []
    out = []
    for p in (data.get("products") or [])[:limit]:
        desc = _clean(BeautifulSoup(p.get("body_html") or "", "html.parser").get_text(" "))
        variants = p.get("variants") or [{}]
        images = p.get("images") or [{}]
        price = variants[0].get("price")
        out.append({
            "name": _clean(p.get("title", "")),
            "description": desc[:600],
            "price": f"₹{price}" if price else None,  # Shopify omits currency; most Indian stores are INR. Verified by user later.
            "image_url": images[0].get("src"),
            "features": [t for t in (p.get("tags") or [])[:6]] if isinstance(p.get("tags"), list) else [],
        })
    return [o for o in out if o["name"]]


def extract(url: str) -> ExtractionResult:
    validate_public_url(url)
    body, ctype, final_url = safe_get(url, settings.max_page_bytes)
    if "html" not in ctype.lower() and not body.lstrip().startswith(b"<"):
        raise ExtractionError(f"Expected an HTML page, got '{ctype or 'unknown'}'.")
    res = parse_html(body.decode("utf-8", errors="replace"), final_url)
    res.url = url
    shop = shopify_products(final_url)
    if shop:
        known = {p["name"].lower() for p in res.products}
        res.products.extend(p for p in shop if p["name"].lower() not in known)
        res.warnings = [w for w in res.warnings if "JSON-LD" not in w]
        res.warnings.append("Product catalogue read from the store's public Shopify feed; confirm currency and prices.")
    return res


ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/jpg": ".jpg"}


def download_image(url: str, dest_dir: Path, stem: str) -> Path | None:
    """Download a public image safely. Returns local path or None."""
    try:
        body, ctype, _ = safe_get(url, settings.max_image_bytes, accept="image/*")
    except ExtractionError:
        return None
    ext = ALLOWED_IMAGE_TYPES.get(ctype.split(";")[0].strip().lower())
    if not ext:
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"{stem}{ext}"
    out.write_bytes(body)
    try:  # verify it is a real image
        from PIL import Image
        with Image.open(out) as im:
            im.verify()
    except Exception:
        out.unlink(missing_ok=True)
        return None
    return out
