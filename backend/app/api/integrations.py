"""Integrations: honest status of every publishing / ad provider. Nothing here publishes or spends money."""
from __future__ import annotations

from fastapi import APIRouter

from ..services import meko_memory, x_publisher

router = APIRouter(tags=["integrations"])

PROVIDERS = [
    {"provider": "export", "label": "Export (ZIP)", "status": "working",
     "notes": "Download approved copy (CSV), strategy and MP4s; upload them to any ad platform yourself.",
     "docs_url": ""},
    {"provider": "simulated", "label": "Simulated metrics", "status": "simulated",
     "notes": "Sample performance data for demos. Always labelled 'simulated'; never real results.", "docs_url": ""},
    {"provider": "csv", "label": "CSV import", "status": "working",
     "notes": "Upload real metrics exported from any ad platform (labelled 'imported_csv').", "docs_url": ""},
    {"provider": "google_ads", "label": "Google Ads", "status": "not_connected",
     "notes": "For advertisers (not AdSense). Needs OAuth plus an approved developer token. Designed, not connected.",
     "docs_url": "https://developers.google.com/google-ads/api/docs/start"},
    {"provider": "meta_ads", "label": "Meta Ads (Facebook + Instagram)", "status": "not_connected",
     "notes": "Needs a Meta app, a business ad account and app review for advanced access. Designed, not connected.",
     "docs_url": "https://developers.facebook.com/docs/marketing-apis"},
    {"provider": "amazon_ads", "label": "Amazon Ads", "status": "not_connected",
     "notes": "Needs registration and approval with Amazon Ads; eligibility to be verified.",
     "docs_url": "https://advertising.amazon.com/API/docs"},
    {"provider": "instagram_publishing", "label": "Instagram publishing", "status": "not_connected",
     "notes": "Needs a business/creator account linked to a Facebook Page plus app permissions.",
     "docs_url": "https://developers.facebook.com/docs/instagram-platform"},
]


def _meko_row() -> dict:
    st = meko_memory.status()
    if not st["configured"]:
        status, notes = "not_connected", "Add MEKO_API_KEY to backend/.env to enable shared agent memory."
    elif st["last_ok"] is False:
        status, notes = "error", f"Last call failed: {st['last_error']}"
    else:
        status, notes = "connected", ("Shared agent memory for Brand Memory, generation traces and learnings "
                                      "(MCP, built on YugabyteDB).")
    return {"provider": "meko", "label": "Meko agent memory (Yugabyte)", "status": status, "notes": notes,
            "docs_url": "https://mekodata.netlify.app/"}


def _x_row() -> dict:
    ok = x_publisher.configured()
    return {"provider": "x_publishing", "label": "X publishing",
            "status": "connected" if ok else "not_connected",
            "notes": ("Approved posts can be published to your X account from AdPilot, only when you press Publish."
                      if ok else "Add X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN and X_ACCESS_SECRET to backend/.env."),
            "docs_url": "https://developer.x.com/en/portal/dashboard"}


@router.get("/integrations")
def list_integrations() -> list[dict]:
    return [_meko_row(), _x_row(), *PROVIDERS]


@router.post("/integrations/meko/test")
def test_meko() -> dict:
    """Live round-trip to Meko's MCP server: lists its tools and your datapacks."""
    return meko_memory.test_connection()
