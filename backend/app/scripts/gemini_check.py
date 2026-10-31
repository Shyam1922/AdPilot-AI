"""Live Gemini check: runs brand analysis -> strategy -> 5 concepts on the demo store and reports
which steps used Gemini, how long each took, and what the trust layer caught. Prints no secrets.

Run (venv active, GEMINI_API_KEY in backend/.env):   python -m app.scripts.gemini_check
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from app.config import settings
from app.schemas.brand import ManualBrandInput
from app.services import ad_generator, brand_analyzer, llm, strategist
from app.services.extractor import extract


def main() -> None:
    print("model:", llm.current_model(), "| provider now:", llm.active_provider(), "|", llm.gemini_status())
    if llm.active_provider() != "gemini":
        print("Gemini is not active (no key, LLM_PROVIDER=offline, or paused after an error).")
        return

    t = time.perf_counter()
    a = brand_analyzer.analyze(extract("https://demo.adpilot.local/"), ManualBrandInput(),
                               Path(tempfile.mkdtemp(prefix="gemini-check-")))
    p = a.profile
    print(f"\n1) brand_profile: mode={a.mode}  {time.perf_counter() - t:.1f}s")
    print(f"   products={len(p.products)} approved_claims={len(p.approved_claims)} unknowns={len(p.unknowns_to_confirm)}")
    moved = [u for u in p.unknowns_to_confirm if u.startswith("Confirm before using")]
    print(f"   claims rejected by grounding check: {len(moved)}")
    for u in moved[:3]:
        print("     -", u[:120])
    print("   tone:", p.brand_tone, "| warnings:", a.warnings)

    t = time.perf_counter()
    s = strategist.generate(p, "sales", ["instagram", "meta_ads", "google_ads"], p.product_name)
    print(f"\n2) campaign_strategy: mode={s.mode}  {time.perf_counter() - t:.1f}s")
    print("   positioning:", s.data.positioning_statement[:160])

    t = time.perf_counter()
    concepts, mode, warns = ad_generator.generate(p, s.data, p.product_name, [], a.sources)
    print(f"\n3) ad_concepts: mode={mode}  {time.perf_counter() - t:.1f}s  warnings={warns}")
    for c in concepts:
        flags = [f"{f['code']}:{f['severity']}" for f in c["risk_flags"] if f["code"] != "trimmed_for_platform"]
        print(f"   [{c['concept_type']}] {c['hook']}  |  {c['headline']}  |  {c['cta']}")
        if flags:
            print("      flags:", flags)

    ok = a.mode == s.mode == mode == "gemini"
    print("\nGEMINI OK" if ok else "\nSome steps fell back to offline: see the modes above.")


if __name__ == "__main__":
    main()
