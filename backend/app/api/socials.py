"""Connected social accounts per brand.

Honest scope: this links the brand's X / LinkedIn / Instagram accounts to AdPilot (handle + profile URL) so posts
show who they go out as and open the right profile. It is NOT an OAuth login and AdPilot cannot post on the user's
behalf: publishing stays "you press Post on the platform". Real API publishing needs each platform's developer app
and review, so those rows are reported as designed, not connected.
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..models import Brand, now
from .common import audit, get_or_404

router = APIRouter(tags=["socials"])
Platform = Literal["linkedin", "instagram", "x"]
PLATFORMS: tuple[str, ...] = ("linkedin", "instagram", "x")
LABEL = {"linkedin": "LinkedIn", "instagram": "Instagram", "x": "X"}


class SocialBody(BaseModel):
    handle_or_url: str


def normalize(platform: str, raw: str) -> tuple[str, str]:
    """Return (display handle, profile URL) or raise ValueError with a message the user can act on."""
    v = raw.strip()
    if not v:
        raise ValueError("Enter your handle or profile link.")
    if platform == "x":
        m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})(?:[/?#]|$)", v) or re.fullmatch(r"@?([A-Za-z0-9_]{1,15})", v)
        if not m:
            raise ValueError("X handles are 1-15 letters, numbers or underscores, e.g. @velvaaskin.")
        return f"@{m.group(1)}", f"https://x.com/{m.group(1)}"
    if platform == "instagram":
        m = re.search(r"instagram\.com/([A-Za-z0-9._]{1,30})(?:[/?#]|$)", v) or re.fullmatch(r"@?([A-Za-z0-9._]{1,30})", v)
        if not m:
            raise ValueError("Instagram handles use letters, numbers, dots and underscores, e.g. @velvaaskin.")
        return f"@{m.group(1)}", f"https://www.instagram.com/{m.group(1)}/"
    m = re.search(r"linkedin\.com/((?:company|in|school)/[A-Za-z0-9\-_%.]{2,100})", v)
    if not m:
        raise ValueError("Paste your LinkedIn page or profile link, e.g. linkedin.com/company/velvaa.")
    path = m.group(1)
    return path.split("/", 1)[1], f"https://www.linkedin.com/{path}/"


def _view(brand: Brand) -> list[dict]:
    saved = (brand.integrations or {}).get("socials") or {}
    out = []
    for p in PLATFORMS:
        s = saved.get(p)
        out.append({
            "platform": p, "label": LABEL[p], "connected": bool(s),
            "handle": (s or {}).get("handle", ""), "url": (s or {}).get("url", ""),
            "connected_at": (s or {}).get("connected_at"),
            "publishing": "manual_share",
            "note": "Linked for reference. You press Post on the platform; automatic posting needs the platform's "
                    "developer-app approval, so it is not connected.",
        })
    return out


@router.get("/brands/{brand_id}/socials")
def list_socials(brand_id: int, session: Session = Depends(get_session)) -> list[dict]:
    return _view(get_or_404(session, Brand, brand_id))


@router.put("/brands/{brand_id}/socials/{platform}")
def connect_social(brand_id: int, platform: Platform, body: SocialBody,
                   session: Session = Depends(get_session)) -> list[dict]:
    brand = get_or_404(session, Brand, brand_id)
    try:
        handle, url = normalize(platform, body.handle_or_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    socials = dict((brand.integrations or {}).get("socials") or {})
    socials[platform] = {"handle": handle, "url": url, "connected_at": now().isoformat()}
    brand.integrations = {**(brand.integrations or {}), "socials": socials}
    audit(session, "brand", brand.id, "social_linked", platform=platform)
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return _view(brand)


@router.delete("/brands/{brand_id}/socials/{platform}")
def disconnect_social(brand_id: int, platform: Platform, session: Session = Depends(get_session)) -> list[dict]:
    brand = get_or_404(session, Brand, brand_id)
    socials = dict((brand.integrations or {}).get("socials") or {})
    socials.pop(platform, None)
    brand.integrations = {**(brand.integrations or {}), "socials": socials}
    audit(session, "brand", brand.id, "social_unlinked", platform=platform)
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return _view(brand)
