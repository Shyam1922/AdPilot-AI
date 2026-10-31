"""Gemini diagnostic: which Flash models can this key use, and how fast does a tiny JSON request come back?

Run (venv active):   python -m app.scripts.gemini_ping
Prints no secrets.
"""
from __future__ import annotations

import time

import httpx

from app.config import settings

BASE = "https://generativelanguage.googleapis.com/v1beta"
H = {"x-goog-api-key": settings.gemini_api_key}


def ping(model: str, thinking: dict | None, timeout: float = 60) -> str:
    gen = {"responseMimeType": "application/json", "temperature": 0.2}
    if thinking:
        gen["thinkingConfig"] = thinking
    body = {"contents": [{"role": "user", "parts": [{"text": 'Return {"ok": true} as JSON.'}]}], "generationConfig": gen}
    t = time.perf_counter()
    try:
        r = httpx.post(f"{BASE}/models/{model}:generateContent", json=body, headers=H, timeout=timeout)
    except httpx.HTTPError as exc:
        return f"{exc.__class__.__name__} after {time.perf_counter() - t:.1f}s"
    took = time.perf_counter() - t
    if r.status_code != 200:
        return f"HTTP {r.status_code} in {took:.1f}s: {r.text[:160]}"
    usage = r.json().get("usageMetadata", {})
    return f"OK in {took:.1f}s (thinking tokens: {usage.get('thoughtsTokenCount', 0)})"


def main() -> None:
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set in backend/.env")
        return
    try:
        r = httpx.get(f"{BASE}/models", params={"pageSize": 200}, headers=H, timeout=20)
        names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        flash = [n for n in names if "flash" in n]
        print(f"{len(names)} models available to this key. Flash models:")
        for n in flash:
            print("  -", n)
    except Exception as exc:
        print("Could not list models:", exc)
        flash = []
    model = settings.gemini_model
    print(f"\nTiny request on {model}:")
    level = {"thinkingBudget": 0} if model.startswith("gemini-2") else {"thinkingLevel": "low"}
    print("  with low thinking :", ping(model, level))
    print("  default thinking  :", ping(model, None))
    lite = [n for n in flash if "lite" in n and n != model]
    if lite:
        print(f"\nTiny request on {lite[0]} (lighter model):")
        print("  default thinking  :", ping(lite[0], None))


if __name__ == "__main__":
    main()
