"""End-to-end G1 flow: demo URL -> Brand Memory -> campaign strategy -> 5 concepts -> edit/approve."""
DEMO = "https://demo.adpilot.local/"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["llm_provider"] == "offline"


def test_full_g1_flow(client):
    r = client.post("/api/brands/analyze", json={"url": DEMO})
    assert r.status_code == 200, r.text
    brand = r.json()
    assert brand["name"] == "Velvaa Skin"
    p = brand["profile"]
    assert len(p["products"]) == 3
    assert len(p["approved_claims"]) >= 4
    assert all(c["source"] for c in p["approved_claims"])
    assert any("hidden" in w for w in brand["warnings"])          # prompt-injection div stripped
    assert not any("clinically" in c["claim"].lower() for c in p["approved_claims"])
    assert brand["logo_url"] and brand["product_image_urls"]
    assert client.get(brand["logo_url"]).status_code == 200

    r = client.post("/api/campaigns", json={"brand_id": brand["id"], "objective": "sales",
                                            "channels": ["instagram", "meta_ads", "google_ads"]})
    assert r.status_code == 200, r.text
    camp = r.json()
    assert camp["status"] == "generated" and camp["strategy"]["primary_kpi"]
    assert len(camp["strategy"]["content_calendar"]) == 7

    r = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={})
    assert r.status_code == 200, r.text
    concepts = r.json()
    assert [c["concept_type"] for c in concepts] == ["problem", "demo", "storytelling", "offer", "testimonial-style"]
    assert len({c["hook"] for c in concepts}) == 5
    for c in concepts:
        assert c["platform_copy"]["google_ads"]["headlines"]
        assert all(len(h) <= 30 for h in c["platform_copy"]["google_ads"]["headlines"])
        assert len(c["video_script"]) == 4
    testimonial = concepts[-1]
    assert testimonial["primary_text"].startswith("(Dramatization)")
    assert any(f["code"] == "dramatization" for f in testimonial["risk_flags"])

    # An edit that invents a discount is flagged as blocking and cannot be approved.
    cid = concepts[0]["id"]
    r = client.patch(f"/api/concepts/{cid}", json={"headline": "50% off today only"})
    flags = {f["code"]: f["severity"] for f in r.json()["risk_flags"]}
    assert flags.get("offer_unverified") == "block"
    assert client.patch(f"/api/concepts/{cid}", json={"status": "approved"}).status_code == 409

    # Fix it, approve, and the campaign can be approved.
    r = client.patch(f"/api/concepts/{cid}", json={"headline": "Light serum for humid days"})
    assert not any(f["severity"] == "block" for f in r.json()["risk_flags"])
    assert client.patch(f"/api/concepts/{cid}", json={"status": "approved"}).json()["status"] == "approved"
    r = client.post(f"/api/concepts/{concepts[1]['id']}/regenerate", json={"field": "hook"})
    assert r.status_code == 200 and r.json()["hook"] != concepts[1]["hook"]
    r = client.patch(f"/api/campaigns/{camp['id']}", json={"status": "approved"})
    assert r.json()["status"] == "approved"

    detail = client.get(f"/api/campaigns/{camp['id']}").json()
    assert detail["campaign"]["counts"]["approved"] == 1


def test_manual_only_brand(client):
    r = client.post("/api/brands/analyze", json={"manual": {
        "brand_name": "Chai Theory", "product_name": "Masala Chai Premix",
        "product_description": "Instant masala chai premix with Assam tea and whole spices.",
        "key_features": ["Ready with hot water", "No added preservatives"], "price_range": "₹299"}})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["profile"]["product_category"] == "food & beverage"
    assert {c["source"] for c in b["profile"]["approved_claims"]} == {"user-provided"}


def test_bad_inputs(client):
    assert client.post("/api/brands/analyze", json={}).status_code == 400
    r = client.post("/api/brands/analyze", json={"url": "http://127.0.0.1/admin"})
    assert r.status_code == 400 and "private" in r.json()["detail"]
    rows = {r["provider"]: r for r in client.get("/api/integrations").json()}
    assert rows["google_ads"]["status"] == "not_connected"
    assert rows["meko"]["status"] == "not_connected"   # no key in tests
    assert client.post("/api/integrations/meko/test").json()["ok"] is False
