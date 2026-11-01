"""Optional AI-clip mode: attach a clip, render with it, and switch back to the normal motion render."""
import subprocess
import time

from app.services.video_service import ffmpeg_path


def _make_clip(path, seconds=3):
    subprocess.run([ffmpeg_path(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"testsrc2=size=270x480:rate=24:duration={seconds}", "-pix_fmt", "yuv420p", str(path)], check=True)


def _wait(client, aid):
    for _ in range(90):
        a = client.get(f"/api/assets/{aid}").json()
        if a["status"] in ("ready", "failed"):
            return a
        time.sleep(1)
    raise AssertionError("render timed out")


def test_ai_clip_mode_and_switch_back(client, tmp_path):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    cid = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()[0]["id"]

    # no clip yet: AI mode is refused, normal mode is the default and works
    assert client.post(f"/api/concepts/{cid}/video", json={"mode": "ai_clip"}).status_code == 409
    p = client.get(f"/api/concepts/{cid}/ai-prompt").json()
    assert "9:16" in p["prompt"] and "No on-screen text" in p["prompt"] and p["duration_s"] == 8

    # bad uploads are rejected
    assert client.post(f"/api/concepts/{cid}/ai-clip", files={"file": ("x.txt", b"hello")}).status_code == 422
    assert client.post(f"/api/concepts/{cid}/ai-clip", files={"file": ("x.mp4", b"not a video")}).status_code == 422

    clip = tmp_path / "clip.mp4"
    _make_clip(clip)
    up = client.post(f"/api/concepts/{cid}/ai-clip", files={"file": ("clip.mp4", clip.read_bytes())})
    assert up.status_code == 200 and up.json()["kind"] == "ai_clip" and 2.5 < up.json()["meta"]["duration_s"] < 3.5

    ai = _wait(client, client.post(f"/api/concepts/{cid}/video", json={"mode": "ai_clip"}).json()["id"])
    assert ai["status"] == "ready", ai["error"]
    assert ai["generation_mode"] == "template+ai_broll" and ai["meta"]["ai_clip"] is True and ai["meta"]["mode"] == "ai_clip"

    # switch back: the default render is the normal motion template again, and the AI render is kept
    plain = _wait(client, client.post(f"/api/concepts/{cid}/video", json={}).json()["id"])
    assert plain["status"] == "ready" and plain["generation_mode"] == "template" and plain["meta"]["ai_clip"] is False
    assert plain["id"] != ai["id"]

    assert client.delete(f"/api/concepts/{cid}/ai-clip").status_code == 204
    assert client.post(f"/api/concepts/{cid}/video", json={"mode": "ai_clip"}).status_code == 409


def test_video_options_pro_tier(client, tmp_path):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    cid = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()[0]["id"]
    m = {x["mode"]: x for x in client.get(f"/api/concepts/{cid}/video-options").json()["modes"]}
    assert m["motion"]["available"] and m["ai_clip"]["tier"] == "pro" and not m["ai_clip"]["available"]
    clip = tmp_path / "c.mp4"
    _make_clip(clip)
    client.post(f"/api/concepts/{cid}/ai-clip", files={"file": ("c.mp4", clip.read_bytes())})
    m = {x["mode"]: x for x in client.get(f"/api/concepts/{cid}/video-options").json()["modes"]}
    assert m["ai_clip"]["available"]
    assert client.get("/api/concepts/99999/video-options").status_code == 404


def test_ai_prompt_is_a_shot_list_without_text(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    cs = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
    prompts = {c["concept_type"]: client.get(f"/api/concepts/{c['id']}/ai-prompt").json()["prompt"] for c in cs}
    p = next(iter(prompts.values()))
    assert "Shot 1" in p and "Shot 2" in p and "Shot 3" in p
    assert "No on-screen text" in p and "attached product photo" in p
    assert len(set(prompts.values())) == len(prompts)        # each concept type gets its own prompt

    assert "first frame" in p


def test_ai_prompt_uses_the_directors_shots_when_a_model_is_available(monkeypatch):
    from app.services import ai_prompt, llm

    plan = ai_prompt._Plan(shots=[ai_prompt._Shot(action="Condensation slides down a cold steel bottle", camera="slow dolly-in", light="harsh noon sun"),
                                  ai_prompt._Shot(action="A hand lifts the bottle and tilts it", camera="macro orbit", light="rim light"),
                                  ai_prompt._Shot(action="The hand sets it down on a wet railing", camera="pull-back", light="golden hour")])
    monkeypatch.setattr(llm, "available_providers", lambda: ["gemini"])
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: llm.LLMResult(plan, "gemini", [], 1, "m"))
    out = ai_prompt.build("problem", "Brand", "Bottle", "beverage", "commuters", ["bold"], ["red"], hook="Stay cool")
    assert out["directed_by"] == "ai" and "Condensation slides" in out["prompt"]
    assert "golden hour" in out["prompt"] and "first frame" in out["prompt"]


def test_video_scripts_differ_by_concept_type(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales"}).json()
    cs = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
    sig = {}
    for c in cs:
        beats = c["video_script"]
        assert [x["beat"] for x in beats] == ["hook", "product", "benefit", "cta"]       # the renderer needs these four
        assert 13 <= sum(x["seconds"] for x in beats) <= 17
        sig[c["concept_type"]] = (tuple(x["seconds"] for x in beats), beats[2]["on_screen_text"], beats[1]["voiceover"])
    assert len(set(sig.values())) == len(sig) >= 4                                     # each type gets its own script
    assert len({v[0] for v in sig.values()}) >= 4                                      # and its own pacing
