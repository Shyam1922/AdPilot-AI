"""G2: render a real MP4 through the API, then export the approved campaign as a ZIP."""
import io
import shutil
import subprocess
import zipfile

import pytest

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg not installed")


def _setup(client):
    b = client.post("/api/brands/analyze", json={"url": "https://demo.adpilot.local/"}).json()
    camp = client.post("/api/campaigns", json={"brand_id": b["id"], "objective": "sales",
                                               "channels": ["instagram"]}).json()
    concepts = client.post(f"/api/campaigns/{camp['id']}/concepts/generate", json={}).json()
    return b, camp, concepts


def test_video_render_and_export(client):
    b, camp, concepts = _setup(client)
    cid = concepts[0]["id"]

    assert client.get(f"/api/campaigns/{camp['id']}/export").status_code == 409   # nothing approved yet

    r = client.post(f"/api/concepts/{cid}/video", json={"format": "1:1"})
    assert r.status_code == 202 and r.json()["status"] == "queued"
    asset = client.get(f"/api/assets/{r.json()['id']}").json()        # TestClient runs background tasks first
    assert asset["status"] == "ready", asset["error"]
    assert asset["url"].endswith(".mp4") and asset["meta"]["duration_s"] == 15.0
    video = client.get(asset["url"])
    assert video.status_code == 200 and video.content[4:8] == b"ftyp"   # a real MP4 container

    detail = client.get(f"/api/campaigns/{camp['id']}").json()
    assert detail["concepts"][0]["latest_video"]["status"] == "ready"
    assert detail["campaign"]["counts"]["videos_ready"] == 1

    client.patch(f"/api/concepts/{cid}", json={"status": "approved"})
    z = client.get(f"/api/campaigns/{camp['id']}/export")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert {"campaign.json", "strategy.json", "concepts.json", "ad_copy.csv", "README.txt",
            f"videos/concept_{cid}.mp4"} <= set(names)
