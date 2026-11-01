"""Scheduling / publishing posts, posting insights, and the SQLite auto-migration."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, text

from app.services import posting_insights as pi


def _setup(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    cs = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
    posts = client.post(f"/api/concepts/{cs[0]['id']}/posts/generate", json={}).json()
    return b["id"], camp["id"], posts


def test_cannot_publish_unapproved(client):
    _, _, posts = _setup(client)
    p = posts[0]
    assert client.post(f"/api/posts/{p['id']}/publish", json={}).status_code == 409
    assert client.post(f"/api/posts/{p['id']}/schedule",
                       json={"scheduled_at": datetime.now(timezone.utc).isoformat()}).status_code == 409


def test_schedule_publish_metrics_flow(client):
    brand_id, camp_id, posts = _setup(client)
    p = posts[1]
    client.patch(f"/api/posts/{p['id']}", json={"status": "approved"})
    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    s = client.post(f"/api/posts/{p['id']}/schedule", json={"scheduled_at": when}).json()
    assert s["status"] == "scheduled" and s["scheduled_at"]
    assert client.delete(f"/api/posts/{p['id']}/schedule").json()["status"] == "approved"
    pub = client.post(f"/api/posts/{p['id']}/publish", json={"mode": "simulated"}).json()
    assert pub["status"] == "published" and pub["publish_mode"] == "simulated" and pub["published_at"]
    # a published post can't be edited or deleted-by-edit
    assert client.patch(f"/api/posts/{p['id']}", json={"text": "changed"}).status_code == 409
    # real numbers are labelled manual; simulate fills the rest as simulated
    m = client.post(f"/api/posts/{p['id']}/metrics",
                    json={"impressions": 1000, "likes": 40, "comments": 3, "shares": 2, "clicks": 12}).json()
    assert m["metrics_source"] == "manual" and m["engagement_rate"] == round((40 + 6 + 6 + 12) / 1000, 4)
    ins = client.get(f"/api/brands/{brand_id}/posting-insights").json()
    assert ins["posts_analyzed"] == 1 and "manual" in ins["sources"]
    assert set(ins["next_slots"]) == {"linkedin", "instagram", "x"}
    listed = client.get(f"/api/campaigns/{camp_id}/posts").json()
    assert all(x["suggested"] and x["suggested"]["label"] for x in listed)
    assert client.get(f"/api/brands/{brand_id}/memory").json()["configured"] is False


def test_simulate_engagement_is_labelled(client):
    _, camp_id, posts = _setup(client)
    for p in posts:
        client.patch(f"/api/posts/{p['id']}", json={"status": "approved"})
        client.post(f"/api/posts/{p['id']}/publish", json={"mode": "simulated"})
    r = client.post(f"/api/campaigns/{camp_id}/posts/simulate-engagement").json()
    assert r["source"] == "simulated" and r["posts_updated"] == 3
    assert {x["metrics_source"] for x in client.get(f"/api/campaigns/{camp_id}/posts").json()} == {"simulated"}


def test_insights_pick_the_winning_slot():
    posts = []
    base = datetime(2026, 9, 7, tzinfo=timezone.utc)      # a Monday
    for week in range(8):
        # Thursday 20:00 IST = 14:30 UTC: strong. Tuesday 09:00 IST: weak.
        posts.append(dict(platform="instagram", published_at=base + timedelta(days=week * 7 + 3, hours=14, minutes=30),
                          text="Sticky skin by noon?", concept_type="offer", metrics_source="synthetic_history",
                          metrics=dict(impressions=3000, likes=210, comments=12, shares=6, clicks=40)))
        posts.append(dict(platform="instagram", published_at=base + timedelta(days=week * 7 + 1, hours=3, minutes=30),
                          text="Meet the serum", concept_type="demo", metrics_source="synthetic_history",
                          metrics=dict(impressions=3000, likes=70, comments=3, shares=1, clicks=15)))
    r = pi.analyze(posts, now=datetime(2026, 11, 1, tzinfo=timezone.utc))
    best = r["platforms"]["instagram"]["best_slots"][0]
    assert best["weekday"] == "Thu" and best["daypart"] == "evening"
    assert r["content"]["by_hook_style"][0]["label"] == "question hook"
    assert any("Thursday" in x or "Thu" in x for x in r["preferences"])
    assert r["next_slots"]["instagram"]["label"].startswith("Thu")


def test_auto_migration_adds_missing_columns(tmp_path, monkeypatch):
    from app import db
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE socialpost (id INTEGER PRIMARY KEY, campaign_id INTEGER, concept_id INTEGER, "
                       "platform VARCHAR, hook VARCHAR, text VARCHAR)"))
    monkeypatch.setattr(db, "engine", eng)
    added = db.ensure_columns()
    assert "socialpost.published_at" in added and "socialpost.metrics" in added
    assert db.ensure_columns() == []          # idempotent


def test_connect_socials(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    base = f"/api/brands/{b['id']}/socials"
    assert [s["connected"] for s in client.get(base).json()] == [False, False, False]
    r = client.put(f"{base}/x", json={"handle_or_url": "https://twitter.com/velvaaskin?lang=en"}).json()
    x = next(s for s in r if s["platform"] == "x")
    assert x["connected"] and x["handle"] == "@velvaaskin" and x["url"] == "https://x.com/velvaaskin"
    ig = next(s for s in client.put(f"{base}/instagram", json={"handle_or_url": "velvaa.skin"}).json() if s["platform"] == "instagram")
    assert ig["handle"] == "@velvaa.skin"
    li = next(s for s in client.put(f"{base}/linkedin", json={"handle_or_url": "https://www.linkedin.com/company/velvaa/"}).json()
              if s["platform"] == "linkedin")
    assert li["handle"] == "velvaa" and li["publishing"] == "manual_share"
    assert client.put(f"{base}/linkedin", json={"handle_or_url": "velvaa"}).status_code == 422
    assert client.put(f"{base}/x", json={"handle_or_url": "bad handle!!"}).status_code == 422
    left = client.delete(f"{base}/x").json()
    assert [s["connected"] for s in left] == [True, True, False] or sum(s["connected"] for s in left) == 2



def test_top_five_tags_are_unique_ordered_and_platform_specific():
    from app.services import tag_picker

    d = ["#VelvaaSkin", "#Skincare", "#IndianSkincare", "#FragranceFree", "#Niacinamide", "#MadeInIndia", "#D2CIndia"]
    ig = tag_picker.pick("instagram", "Velvaa Skin", "skincare", d, True)
    li = tag_picker.pick("linkedin", "Velvaa Skin", "skincare", d, True)
    assert len(ig) == 5 and len(li) == 5 and len({t.lower() for t in ig}) == 5
    assert ig[0] == "#VelvaaSkin" and ig[1] in ("#FragranceFree", "#Niacinamide")      # brand first, then a product tag
    assert "#BeautyIndustry" in li and ig != li                                         # LinkedIn leans professional
    assert len(tag_picker.pick("x", "Odd Co", "gadgets", [], False)) == 5               # unknown category still gets 5


def test_promotion_policy_holds_weak_learnings_and_traces_the_decision(monkeypatch):
    from app.services import meko_memory as mm

    assert mm.promotion_policy("Offer angle led on CTR (1.65%, directional, simulated data) with hook X.")[0]
    assert not mm.promotion_policy("Demo angle was lowest on CTR (0.9%, insufficient data, imported data).")[0]

    calls = []

    class Fake:
        def conversation(self, agent, dp, title):
            return "c1"

        def call(self, tool, args):
            calls.append((tool, args))
            return {"id": f"m{len(calls)}"}

    monkeypatch.setattr(mm, "_run", lambda fn, timeout=None, attempts=2: fn(Fake()))
    out = mm.save_learnings("dp1", ["Offer angle led on CTR (1.65%, directional, imported data) with a clear hook.",
                                    "Demo angle was lowest on CTR (0.9%, insufficient data, imported data) so far."], brand="B")
    assert out["promoted_count"] == 1 and out["held_count"] == 1
    promote = next(a for t, a in calls if t == "memory_promote")
    assert len(promote["memory_ids"]) == 1                                   # only the approved one
    assert any(t == "conversation_add_message" and "held" in a["output"] for t, a in calls)
