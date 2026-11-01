"""Publish a post to X through the official API (v2 POST /2/tweets, OAuth 1.0a user context).

Optional: configured only when all four X_* keys are set in backend/.env. Nothing else in AdPilot posts
anywhere; this runs only when the user presses "Publish to X now" on an approved post.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

import httpx

from ..config import settings

API_URL = "https://api.twitter.com/2/tweets"


class XPublishError(Exception):
    pass


def configured() -> bool:
    return all([settings.x_api_key, settings.x_api_secret, settings.x_access_token, settings.x_access_secret])


def _pct(s: str) -> str:
    return quote(str(s), safe="~")


def _auth_header(method: str, url: str, *, key: str, secret: str, token: str, token_secret: str,
                 nonce: str | None = None, timestamp: str | None = None) -> str:
    """OAuth 1.0a HMAC-SHA1 header. The JSON body is not part of the signature base string."""
    p = {
        "oauth_consumer_key": key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    norm = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(p.items()))
    base = "&".join([method.upper(), _pct(url), _pct(norm)])
    signing_key = f"{_pct(secret)}&{_pct(token_secret)}"
    p["oauth_signature"] = base64.b64encode(hmac.new(signing_key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(p.items()))


def post_tweet(text: str, *, transport: httpx.BaseTransport | None = None) -> tuple[str, str]:
    """Create the tweet. Returns (tweet_id, public_url). Raises XPublishError with a readable reason."""
    if not configured():
        raise XPublishError("X keys aren't set. Add X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN and X_ACCESS_SECRET to backend/.env.")
    auth = _auth_header("POST", API_URL, key=settings.x_api_key, secret=settings.x_api_secret,
                        token=settings.x_access_token, token_secret=settings.x_access_secret)
    try:
        with httpx.Client(timeout=20, transport=transport) as c:
            r = c.post(API_URL, json={"text": text}, headers={"Authorization": auth})
    except httpx.HTTPError as exc:
        raise XPublishError(f"Couldn't reach X: {exc}") from exc
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code not in (200, 201):
        detail = body.get("detail") or body.get("title") or r.text[:200] or f"HTTP {r.status_code}"
        if r.status_code in (401, 403):
            detail += " (check the keys and that the app has Read and write permission; regenerate the access token after changing it)"
        raise XPublishError(f"X rejected the post: {detail}")
    tweet_id = (body.get("data") or {}).get("id", "")
    if not tweet_id:
        raise XPublishError("X accepted the request but returned no post id.")
    return tweet_id, f"https://x.com/i/status/{tweet_id}"
