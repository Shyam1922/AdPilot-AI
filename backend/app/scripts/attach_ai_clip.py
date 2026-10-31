"""Attach an AI-generated clip to a concept and (optionally) render the video with it.

1. Get the prompt:   GET /api/concepts/<id>/ai-prompt   (or open it in http://localhost:8000/docs)
2. Make a clip in any tool (e.g. Veo in Google Flow) from the real product photo; download the .mp4
3. python -m app.scripts.attach_ai_clip --concept 1 path\to\clip.mp4 --render

Switch back any time: render again in normal mode (the default) or remove the clip:
   python -m app.scripts.attach_ai_clip --concept 1 --remove
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", nargs="?", help="path to the AI clip (.mp4, .mov, .webm)")
    ap.add_argument("--concept", type=int, required=True)
    ap.add_argument("--render", action="store_true", help="render the video using the clip")
    ap.add_argument("--remove", action="store_true", help="detach the clip(s) from this concept")
    a = ap.parse_args()
    logging.disable(logging.CRITICAL)
    with TestClient(app) as c:
        if a.remove:
            r = c.delete(f"/api/concepts/{a.concept}/ai-clip")
            print("removed" if r.status_code == 204 else r.text)
            return
        if a.clip:
            p = Path(a.clip)
            if not p.exists():
                sys.exit(f"file not found: {p}")
            r = c.post(f"/api/concepts/{a.concept}/ai-clip", files={"file": (p.name, p.read_bytes())})
            if r.status_code != 200:
                sys.exit(f"upload failed: {r.json().get('detail', r.text)}")
            print(f"attached {p.name} ({r.json()['meta']['duration_s']} s)")
        if a.render:
            r = c.post(f"/api/concepts/{a.concept}/video", json={"mode": "ai_clip"})
            if r.status_code != 202:
                sys.exit(f"render failed to start: {r.json().get('detail', r.text)}")
            aid = r.json()["id"]
            while True:
                st = c.get(f"/api/assets/{aid}").json()
                if st["status"] in ("ready", "failed"):
                    break
                time.sleep(1)
            print(f"video {st['status']}: {st.get('url') or st.get('error')}")


if __name__ == "__main__":
    main()
