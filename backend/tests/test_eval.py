"""The evaluation scorecard doubles as a regression test: if a guard weakens, CI-style tests fail."""
from app.scripts import evaluate as ev


def test_claim_guard_red_team_and_no_false_alarms():
    r = ev.check_claim_guard()
    assert r["pass"], r["detail"]
    assert r["extra"]["pass"], r["extra"]["detail"]


def test_ssrf_blocklist():
    assert ev.check_url_safety()["pass"]


def test_false_winner_rate_is_low_and_power_is_high():
    r = ev.false_winner_rate(trials=150)
    assert r["pass"], r["score"]
    assert r["extra"]["pass"], r["extra"]["score"]


def test_full_scorecard_pipeline(client):
    results: list = []
    ev.check_pipeline(client, results)
    assert all(x["pass"] for x in results), [x["name"] for x in results if not x["pass"]]
