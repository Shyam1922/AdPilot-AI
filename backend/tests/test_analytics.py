"""G3: metrics maths, ranking honesty, CSV validation and the optimization loop."""
from types import SimpleNamespace as NS

from app.services import concept_ranker as cr
from app.services import metrics_calculator as mc


def test_rates_zero_denominators_are_none():
    r = mc.rates(0, 0, 0, 0.0, None)
    assert r == {"ctr": None, "cvr": None, "cpc": None, "cpa": None, "roas": None}
    r = mc.rates(1000, 20, 2, 300.0, 1600.0)
    assert r["ctr"] == 0.02 and r["cvr"] == 0.1 and r["cpc"] == 15.0 and r["cpa"] == 150.0
    assert abs(r["roas"] - 5.333) < 0.01


def test_wilson_and_gates():
    lo, hi = cr.wilson(20, 1000)
    assert 0.012 < lo < 0.02 < hi < 0.031
    assert cr.wilson(0, 0) == (None, None)
    assert cr.sample_status("ctr", 3, 400) == "insufficient_data"
    assert cr.sample_status("ctr", 12, 1500) == "early_signal"
    assert cr.sample_status("ctr", 60, 5000) == "directional"


def test_ranking_needs_separated_intervals_to_call_a_winner():
    close = {1: {"clicks": 22, "impressions": 1000, "conversions": 0}, 2: {"clicks": 20, "impressions": 1000, "conversions": 0}}
    assert not cr.clear_winner(cr.rank(close, "ctr"))
    far = {1: {"clicks": 400, "impressions": 10000, "conversions": 0}, 2: {"clicks": 100, "impressions": 10000, "conversions": 0}}
    ranked = cr.rank(far, "ctr")
    assert ranked[0]["concept_id"] == 1 and cr.clear_winner(ranked) and ranked[0]["p_best"] > 0.99


def test_csv_validation():
    text = ("concept_id,day,platform,impressions,clicks,conversions,spend,revenue\n"
            "1,2026-10-25,meta,1000,20,2,300,1600\n"
            "9,2026-10-25,meta,1000,20,2,300,\n"          # unknown concept
            "1,2026-10-26,meta,10,20,2,300,\n")           # clicks > impressions
    rows, errors = mc.parse_csv(text, {1})
    assert len(rows) == 1 and rows[0]["source_type"] == "imported_csv" and len(errors) == 2
    assert mc.parse_csv("a,b\n1,2\n", {1})[1][0].startswith("Missing column")


def test_simulation_is_deterministic_and_labelled():
    cs = [NS(id=i, concept_type=t, parent_concept_id=None, is_exploration=False)
          for i, t in enumerate(["problem", "demo"], 1)]
    a, b = mc.simulate(cs, 3, 42), mc.simulate(cs, 3, 42)
    assert a == b and all(r["source_type"] == "simulated" for r in a) and len(a) == 6


def test_optimization_loop(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={})
    assert client.post(f"/api/campaigns/{camp['id']}/iterate", json={}).status_code == 409   # no data yet

    r = client.post(f"/api/campaigns/{camp['id']}/metrics/simulate", json={})
    assert r.json() == {"rows_saved": 35, "source_type": "simulated"}
    a = client.get(f"/api/campaigns/{camp['id']}/analytics").json()
    assert a["is_simulated"] and a["objective_metric"] == "cvr" and any("SIMULATED" in w for w in a["warnings"])
    assert len(a["by_concept"]) == 5 and a["totals"]["impressions"] > 0
    assert all(x["ci_low"] <= x["primary_value"] <= x["ci_high"] for x in a["by_concept"])

    it = client.post(f"/api/campaigns/{camp['id']}/iterate", json={"batch_size": 4}).json()
    assert len(it["variants"]) == 4
    assert sum(v["is_exploration"] for v in it["variants"]) == 1
    assert all(v["parent_concept_id"] and v["changed_variables"] and v["rationale"] for v in it["variants"])
    assert any("SIMULATED" in l for l in it["limitations"]) and any("correlation" in l for l in it["limitations"])
    brand = client.get(f"/api/brands/{b['id']}").json()
    assert len(brand["learnings"]) >= 2 and "simulated" in brand["learnings"][0]["text"]


def test_trend_model_learns_traits_and_trends():
    from types import SimpleNamespace as NS

    from app.services import trend_model

    def ad(t, seg, layout, hook):
        return NS(concept_type=t, target_segment=seg, visual_brief={"layout": layout}, hook=hook, cta="Shop now")

    concepts = {1: ad("offer", "A", "split", "Get 20% off"), 2: ad("demo", "B", "hero", "See it work"),
                3: ad("story", "A", "split", "Why we started"), 4: ad("demo", "B", "hero", "Skin that lasts")}
    per = {1: {"impressions": 20000, "clicks": 600, "conversions": 30}, 2: {"impressions": 20000, "clicks": 200, "conversions": 10},
           3: {"impressions": 20000, "clicks": 560, "conversions": 28}, 4: {"impressions": 20000, "clicks": 220, "conversions": 11}}
    rows = [NS(concept_id=1, day=f"2026-10-{d:02d}", impressions=1000, clicks=10 + 4 * d, conversions=1) for d in range(1, 8)]
    out = trend_model.analyse(per, rows, concepts, "ctr")
    top = out["effects"][0]
    assert top["p_better"] > 0.8 and top["trait"] in ("layout", "audience", "angle", "hook style")
    assert trend_model.best_value(out["effects"], "layout", exclude="hero") == "split"
    assert out["trends"][0]["verdict"] == "rising"
    assert trend_model.analyse({}, [], {}, "ctr")["effects"] == []
