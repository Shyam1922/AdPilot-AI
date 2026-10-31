"""Campaign export: one ZIP with everything needed to launch manually on any ad platform."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..models import Asset, Brand, Campaign, Concept


def _slug(s: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in s.lower()).strip("-")[:40] or "campaign"


def build_zip(brand: Brand, camp: Campaign, concepts: list[Concept], videos: dict[int, Asset],
              posts: list | None = None) -> tuple[bytes, str]:
    buf = io.BytesIO()
    approved = [c for c in concepts if c.status == "approved"]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("campaign.json", json.dumps({
            "brand": brand.name, "website": brand.website, "campaign": camp.name, "objective": camp.objective,
            "channels": camp.channels, "product_focus": camp.product_focus, "status": camp.status,
            "exported_at": datetime.now(timezone.utc).isoformat()}, indent=2, ensure_ascii=False))
        z.writestr("strategy.json", json.dumps(camp.strategy, indent=2, ensure_ascii=False))
        z.writestr("concepts.json", json.dumps([{
            "id": c.id, "type": c.concept_type, "segment": c.target_segment, "hook": c.hook,
            "primary_text": c.primary_text, "headline": c.headline, "cta": c.cta,
            "platform_copy": c.platform_copy, "visual_brief": c.visual_brief, "video_script": c.video_script,
            "risk_flags": c.risk_flags, "generation_mode": c.generation_mode} for c in approved],
            indent=2, ensure_ascii=False))

        rows = io.StringIO()
        w = csv.writer(rows)
        w.writerow(["concept_id", "concept_type", "platform", "field", "text", "video_file"])
        for c in approved:
            vid = videos.get(c.id)
            vname = f"videos/concept_{c.id}.mp4" if vid and vid.status == "ready" else ""
            pc = c.platform_copy or {}
            ig = pc.get("instagram", {})
            w.writerow([c.id, c.concept_type, "instagram", "caption", ig.get("caption", ""), vname])
            meta = pc.get("meta_ads", {})
            for f in ("primary_text", "headline", "description", "cta"):
                w.writerow([c.id, c.concept_type, "meta_ads", f, meta.get(f, ""), vname])
            g = pc.get("google_ads", {})
            for i, hdl in enumerate(g.get("headlines", []), 1):
                w.writerow([c.id, c.concept_type, "google_ads", f"headline_{i}", hdl, ""])
            for i, d in enumerate(g.get("descriptions", []), 1):
                w.writerow([c.id, c.concept_type, "google_ads", f"description_{i}", d, ""])
        z.writestr("ad_copy.csv", "﻿" + rows.getvalue())   # BOM so Excel shows ₹ correctly

        for c in approved:
            vid = videos.get(c.id)
            if vid and vid.status == "ready" and vid.path and Path(vid.path).exists():
                z.write(vid.path, f"videos/concept_{c.id}.mp4")

        approved_posts = [p for p in (posts or []) if p.status == "approved"]
        if approved_posts:
            z.writestr("social_posts.json", json.dumps([{
                "id": p.id, "concept_id": p.concept_id, "platform": p.platform, "text": p.text,
                "thread": p.thread, "visual_idea": p.visual_idea, "risk_flags": p.risk_flags,
                "generation_mode": p.generation_mode} for p in approved_posts], indent=2, ensure_ascii=False))
            for p in approved_posts:
                body = p.text + ("\n\n--- thread ---\n" + "\n\n".join(p.thread) if p.thread else "")
                z.writestr(f"social_posts/{p.platform}_concept_{p.concept_id}_post_{p.id}.txt", body)

        modes = sorted({c.generation_mode for c in approved})
        z.writestr("README.txt", "\n".join([
            f"AdPilot AI export · {camp.name} · {brand.name}",
            "",
            f"{len(approved)} approved concept(s). Copy written by: {', '.join(modes) or 'n/a'} (a provider name such as gemini or groq = an AI model,",
            "offline = AdPilot's rule-based templates). Every product claim was checked against the brand's sources;",
            "see risk_flags in concepts.json for anything to review before launch.",
            "",
            "Videos were rendered by AdPilot's template pipeline (Pillow + FFmpeg) using the brand's real product image.",
            "Concepts marked '(Dramatization)' are not real customer reviews.",
            "",
            f"{len(approved_posts)} approved social post(s) are in social_posts/ (copy-paste drafts for LinkedIn, Instagram and X).",
            "Nothing in this export has been published or spent. Upload to your ad platform after review.",
        ]))
    return buf.getvalue(), f"adpilot-{_slug(brand.name)}-{_slug(camp.name)}.zip"
