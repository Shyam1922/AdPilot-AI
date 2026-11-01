"""Social posts: platform limits, claim guard, edit/approve rules, no fake proof."""
from app.services.ad_generator import CLICHE_RE


def _concept(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    cs = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
    return camp["id"], cs


def test_generate_three_platforms_within_limits(client):
    camp_id, cs = _concept(client)
    r = client.post(f"/api/concepts/{cs[0]['id']}/posts/generate", json={})
    assert r.status_code == 200
    posts = {p["platform"]: p for p in r.json()}
    assert set(posts) == {"linkedin", "instagram", "x"}
    assert posts["x"]["char_count"] <= 280 and len(posts["x"]["thread"]) == 3
    assert posts["instagram"]["text"].count("#") >= 3 and "link in bio" in posts["instagram"]["text"]
    assert all(p["generation_mode"] for p in posts.values())
    assert all(not [f for f in p["risk_flags"] if f["severity"] == "block"] for p in posts.values())
    assert len(client.get(f"/api/campaigns/{camp_id}/posts").json()) == 3


def test_testimonial_concept_never_posts_a_fake_quote(client):
    _, cs = _concept(client)
    t = next(c for c in cs if c["concept_type"] == "testimonial-style")
    for p in client.post(f"/api/concepts/{t['id']}/posts/generate", json={"platforms": ["x", "linkedin"]}).json():
        assert "“" not in p["text"] and "I actually" not in p["text"]


def test_edit_reruns_guard_and_blocks_approval(client):
    _, cs = _concept(client)
    post = client.post(f"/api/concepts/{cs[0]['id']}/posts/generate", json={"platforms": ["linkedin"]}).json()[0]
    bad = client.patch(f"/api/posts/{post['id']}", json={"text": "Loved by 10,000+ customers. Flat 50% off today!"}).json()
    assert any(f["severity"] == "block" for f in bad["risk_flags"]) and bad["edited"]
    assert client.patch(f"/api/posts/{post['id']}", json={"status": "approved"}).status_code == 409
    ok = client.post(f"/api/posts/{post['id']}/regenerate").json()
    assert ok["status"] == "generated" and not ok["edited"]
    assert client.patch(f"/api/posts/{post['id']}", json={"status": "approved"}).json()["status"] == "approved"


def test_x_over_limit_cannot_be_approved(client):
    _, cs = _concept(client)
    post = client.post(f"/api/concepts/{cs[0]['id']}/posts/generate", json={"platforms": ["x"]}).json()[0]
    r = client.patch(f"/api/posts/{post['id']}", json={"text": "word " * 80})
    assert r.json()["char_count"] > 280
    assert client.patch(f"/api/posts/{post['id']}", json={"status": "approved"}).status_code == 409


def test_cliche_filter_pattern():
    assert CLICHE_RE.search("Unlock glowing skin") and CLICHE_RE.search("A game-changer for you")
    assert not CLICHE_RE.search("Skin feeling sticky by noon?")


def test_concepts_have_no_cliches(client):
    _, cs = _concept(client)
    assert not [c for c in cs if CLICHE_RE.search(c["hook"])]


def test_export_includes_approved_posts(client):
    import io
    import zipfile
    camp_id, cs = _concept(client)
    client.patch(f"/api/concepts/{cs[0]['id']}", json={"status": "approved"})
    ps = client.post(f"/api/concepts/{cs[0]['id']}/posts/generate", json={"platforms": ["instagram"]}).json()
    client.patch(f"/api/posts/{ps[0]['id']}", json={"status": "approved"})
    r = client.get(f"/api/campaigns/{camp_id}/export")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "social_posts.json" in names and any(n.startswith("social_posts/instagram_") for n in names)


def test_delete_brand_removes_everything_under_it(client):
    from sqlmodel import Session, select

    from app.db import engine
    from app.models import Campaign, Concept, SocialPost

    brand_id = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()["id"]
    camp_id = client.post("/api/campaigns", json={"brand_id": brand_id, "objective": "sales"}).json()["id"]
    cs = client.post(f"/api/campaigns/{camp_id}/concepts/generate", json={}).json()
    client.post(f"/api/concepts/{cs[0]['id']}/posts/generate", json={})
    keep = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()["id"]

    assert client.delete(f"/api/brands/{brand_id}").status_code == 204
    assert client.get(f"/api/brands/{brand_id}").status_code == 404
    assert client.get(f"/api/campaigns/{camp_id}").status_code == 404
    assert client.delete(f"/api/brands/{brand_id}").status_code == 404
    assert client.get(f"/api/brands/{keep}").status_code == 200          # other brands untouched
    with Session(engine) as s:
        assert not s.exec(select(Campaign).where(Campaign.brand_id == brand_id)).all()
        assert not s.exec(select(Concept).where(Concept.campaign_id == camp_id)).all()
        assert not s.exec(select(SocialPost).where(SocialPost.campaign_id == camp_id)).all()
