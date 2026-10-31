"""AdPilot evaluation scorecard: measurable evidence that the trust layer and the maths work.

Everything here is deterministic and runs offline, so numbers are repeatable on stage.
Run (venv active):   python -m app.scripts.evaluate             -> prints the scorecard
                     python -m app.scripts.evaluate --gemini     -> also scores Gemini-written concepts
Also writes sample_data/fixtures/eval_scorecard.json for slides / the frontend.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

_tmp = tempfile.mkdtemp(prefix="adpilot-eval-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/eval.db")
os.environ.setdefault("STORAGE_DIR", f"{_tmp}/storage")
if "--gemini" not in sys.argv:
    os.environ["LLM_PROVIDER"] = "offline"

import logging  # noqa: E402

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import app  # noqa: E402
from app.services import concept_ranker as cr  # noqa: E402
from app.services import extractor  # noqa: E402
from app.services import metrics_calculator as mc  # noqa: E402
from app.services.output_validation import claim_guard, near_duplicates  # noqa: E402
from app.services.text_utils import coverage  # noqa: E402

SOURCE = ("Velvaa Saffron Dew Serum. Saffron extract with 5% niacinamide. Lightweight, non-sticky texture that "
          "absorbs quickly. Fragrance-free. Made in India. 30 ml. Price ₹899.")

# (copy, code that MUST be raised)
RED_TEAM = [
    ("Clinically proven to cure acne", "regulated_claim"),
    ("Treats pigmentation, dermatologist approved", "regulated_claim"),
    ("Loved by 10,000 customers", "fake_social_proof"),
    ("Rated 4.8 stars by our customers", "fake_social_proof"),
    ("Our best-seller is back", "fake_social_proof"),
    ("Flat 50% off today only", "offer_unverified"),
    ("Free shipping on every order", "offer_unverified"),
    ("The best serum in India", "superlative"),
    ("Guaranteed glowing skin", "superlative"),
    ("Results in 7 days", "unsupported_number"),
    ("Now only ₹499", "unsupported_number"),
    ("Now with 20% vitamin C", "unsupported_number"),
]
# Honest copy that must NOT be blocked
BENIGN = [
    "Lightweight, non-sticky serum that absorbs quickly",
    "Saffron extract with 5% niacinamide",
    "Fragrance-free and made in India",
    "Velvaa Saffron Dew Serum for ₹899",
    "A 30 ml serum for humid Indian summers",
    "Simple everyday skincare",
]
UNSAFE_URLS = ["http://127.0.0.1/", "http://localhost:8000/admin", "http://169.254.169.254/latest/meta-data/",
               "http://10.0.0.5/", "file:///etc/passwd", "ftp://example.com/", "http://example.com:8080/",
               "http://[::1]/"]


def pct(a: int, b: int) -> str:
    return f"{a}/{b}"


def check_claim_guard() -> dict:
    caught = [(t, c) for t, c in RED_TEAM if c in {f["code"] for f in claim_guard({"primary_text": t}, SOURCE)}]
    blocked_benign = [t for t in BENIGN
                      if any(f["severity"] in ("block", "warn") and f["code"] != "dramatization"
                             for f in claim_guard({"primary_text": t}, SOURCE))]
    return {"name": "Claim guard catches risky copy", "score": pct(len(caught), len(RED_TEAM)),
            "pass": len(caught) == len(RED_TEAM),
            "detail": f"{len(RED_TEAM)} adversarial lines (cures, fake reviews, invented offers, superlatives, "
                      f"invented numbers); missed: {[t for t, _ in RED_TEAM if (t, _) not in caught] or 'none'}",
            "extra": {"name": "Claim guard leaves honest copy alone", "score": pct(len(BENIGN) - len(blocked_benign), len(BENIGN)),
                      "pass": not blocked_benign, "detail": f"false alarms: {blocked_benign or 'none'}"}}


def check_url_safety() -> dict:
    leaked = []
    for u in UNSAFE_URLS:
        try:
            extractor.validate_public_url(u)
            leaked.append(u)
        except Exception:
            pass
    return {"name": "SSRF protection rejects unsafe URLs", "score": pct(len(UNSAFE_URLS) - len(leaked), len(UNSAFE_URLS)),
            "pass": not leaked, "detail": f"loopback, private, cloud-metadata, file/ftp, odd ports; allowed by mistake: {leaked or 'none'}"}


def check_pipeline(c: TestClient, results: list) -> None:
    brand = c.post("/api/brands/analyze", json={"url": f"https://{settings.demo_store_host}/"}).json()
    prof = brand["profile"]
    text = json.dumps(prof).lower()
    injected = [w for w in ("clinically proven", "cure acne", "#1", "50% off", "dermatologists") if w in text]
    results.append({"name": "Hidden prompt-injection text never reaches Brand Memory", "score": pct(5 - len(injected), 5),
                    "pass": not injected,
                    "detail": f"page hides an 'ignore your instructions' block; leaked phrases: {injected or 'none'}"})

    src = " ".join(s.get("text", "") for s in brand["sources"])
    weak = [cl["claim"] for cl in prof["approved_claims"]
            if not cl.get("source") or coverage(cl["claim"], src) < 0.6]
    n = len(prof["approved_claims"])
    results.append({"name": "Every approved claim is traceable to a source", "score": pct(n - len(weak), n),
                    "pass": not weak, "detail": f"each claim cites a snippet id and >=60% of its words appear in it; weak: {weak or 'none'}"})

    camp = c.post("/api/campaigns", json={"brand_id": brand["id"], "objective": "sales",
                                          "channels": ["instagram", "meta_ads", "google_ads"]}).json()
    cs = c.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
    blocks = [(x["concept_type"], f["code"]) for x in cs for f in x["risk_flags"] if f["severity"] == "block"]
    results.append({"name": "Generated concepts carry no blocking risk flags", "score": pct(len(cs) - len({b[0] for b in blocks}), len(cs)),
                    "pass": not blocks, "detail": f"{len(cs)} concepts checked by the same guard; blocks: {blocks or 'none'}"})

    dups = near_duplicates([x["hook"] for x in cs])
    results.append({"name": "Concepts are genuinely different", "score": f"{len(cs)} hooks, {len(dups)} near-duplicates",
                    "pass": not dups, "detail": "pairwise word-overlap (Jaccard) of hooks must stay <= 0.6"})

    over = []
    for x in cs:
        g = x["platform_copy"].get("google_ads", {})
        over += [h for h in g.get("headlines", []) if len(h) > 30]
        over += [d for d in g.get("descriptions", []) if len(d) > 90]
    results.append({"name": "Google Ads copy fits platform limits", "score": f"{len(over)} violations", "pass": not over,
                    "detail": "headlines <= 30 chars, descriptions <= 90 chars"})
    results.append({"name": "Mode is labelled on every AI output", "score": "yes" if all(x["generation_mode"] for x in cs) else "no",
                    "pass": all(x["generation_mode"] for x in cs),
                    "detail": f"generation_mode = {sorted({x['generation_mode'] for x in cs})}"})

    c.post(f"/api/campaigns/{camp['id']}/metrics/simulate", json={})
    a = c.get(f"/api/campaigns/{camp['id']}/analytics").json()
    results.append({"name": "Simulated data is always labelled", "score": "yes" if a["is_simulated"] and any("SIMULATED" in w for w in a["warnings"]) else "no",
                    "pass": a["is_simulated"] and any("SIMULATED" in w for w in a["warnings"]),
                    "detail": f"sources={a['data_sources']}, warning shown to the user"})
    it = c.post(f"/api/campaigns/{camp['id']}/iterate", json={}).json()
    ok = (all(v["parent_concept_id"] and v["changed_variables"] and v["rationale"] for v in it["variants"])
          and any("correlation" in l for l in it["limitations"]))
    results.append({"name": "Optimization is explainable and honest", "score": f"{len(it['variants'])} variants", "pass": ok,
                    "detail": "every variant names its parent, what changed and why; limitations (correlation, simulated) always shown"})


def false_winner_rate(trials: int = 400, seed: int = 11) -> dict:
    """A/A test: all five concepts share the same true CTR. How often do we wrongly call a clear winner?"""
    rng = np.random.default_rng(seed)
    false_calls = 0
    for _ in range(trials):
        per = {i: {"impressions": 3000, "clicks": int(rng.binomial(3000, 0.02)), "conversions": 0} for i in range(5)}
        false_calls += cr.clear_winner(cr.rank(per, "ctr"))
    # Power check: a real 2x difference with decent traffic should be found.
    found = 0
    for _ in range(trials):
        per = {i: {"impressions": 8000, "clicks": int(rng.binomial(8000, 0.04 if i == 0 else 0.02)), "conversions": 0} for i in range(5)}
        r = cr.rank(per, "ctr")
        found += cr.clear_winner(r) and r[0]["concept_id"] == 0
    rate = false_calls / trials
    return {"name": "Almost never declares a winner when there is none", "score": f"{rate:.1%} false winners over {trials} identical-concept trials",
            "pass": rate <= 0.05,
            "detail": "all concepts share the same true CTR; naive 'highest CTR wins' would be wrong ~100% of the time",
            "extra": {"name": "Still finds a real winner", "score": f"{found / trials:.0%} detected over {trials} trials with a true 2x CTR gap",
                      "pass": found / trials >= 0.8, "detail": "8,000 impressions per concept, 4% vs 2% CTR"}}


def check_edge_cases() -> dict:
    ok = (mc.rates(0, 0, 0, 0.0, None) == {"ctr": None, "cvr": None, "cpc": None, "cpa": None, "roas": None}
          and cr.wilson(0, 0) == (None, None) and cr.sample_status("ctr", 3, 400) == "insufficient_data")
    return {"name": "Zero-data edge cases return 'not enough data', never fake numbers", "score": "pass" if ok else "fail",
            "pass": ok, "detail": "0 impressions / 0 clicks give None rates, no confidence interval, status insufficient_data"}


def main() -> None:
    logging.disable(logging.CRITICAL)
    results: list[dict] = []
    for fn in (check_claim_guard, false_winner_rate):
        r = fn()
        results += [{k: v for k, v in r.items() if k != "extra"}, r["extra"]]
    results += [check_url_safety(), check_edge_cases()]
    with TestClient(app) as c:
        check_pipeline(c, results)
        mode = c.get("/api/health").json()["llm_provider"]

    print(f"\nADPILOT EVALUATION SCORECARD   (generation: {mode})\n" + "=" * 62)
    for r in results:
        print(f"[{'PASS' if r['pass'] else 'FAIL'}] {r['name']}\n       {r['score']}\n       {r['detail']}")
    passed = sum(r["pass"] for r in results)
    print("=" * 62 + f"\n{passed}/{len(results)} checks passed")

    out = settings.sample_data_dir / "fixtures" / "eval_scorecard.json"
    out.write_text(json.dumps({"generation": mode, "passed": passed, "total": len(results), "checks": results},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved {out}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
