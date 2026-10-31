"""Gemini may return a channel plan in its own shape; the API must always honour the UI contract."""
from app.services.strategist import normalize_strategy


def test_malformed_channel_plan_is_repaired():
    bad = {"channel_plan": [{"platform": "Instagram Reels", "purpose": "Discovery", "format": "Reels, Stories"},
                            {"name": "Google Ads"}, "Meta", {"role": "no channel"}, None],
           "content_calendar": [{"day": "1", "platform": "Instagram", "idea": "Post"}],
           "segments": [{"segment": "A", "pains": "slow, sticky"}], "ctas": "Shop now"}
    out = normalize_strategy(bad, ["instagram", "meta_ads", "google_ads"])
    assert {c["channel"] for c in out["channel_plan"]} == {"instagram", "meta_ads", "google_ads"}
    assert all(isinstance(c["formats"], list) and c["role"] for c in out["channel_plan"])
    assert out["content_calendar"][0]["channel"] == "instagram" and out["content_calendar"][0]["day"] == 1
    assert out["segments"][0]["pain_points"] == ["slow", "sticky"] and out["ctas"] == ["Shop now"]


def test_stored_bad_strategy_is_fixed_on_read(client):
    from sqlmodel import Session

    from app.db import engine
    from app.models import Campaign
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    with Session(engine) as s:
        c = s.get(Campaign, camp["id"])
        c.strategy = {**c.strategy, "channel_plan": [{"platform": "Instagram"}, {"title": "Google"}]}
        s.add(c)
        s.commit()
    plan = client.get(f"/api/campaigns/{camp['id']}").json()["campaign"]["strategy"]["channel_plan"]
    assert plan and all("channel" in p and "formats" in p for p in plan)
