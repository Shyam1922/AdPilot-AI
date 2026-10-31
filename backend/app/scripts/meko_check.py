"""Live Meko check: prints the real parameters of the tools AdPilot uses, then runs each once.

Run (venv active, MEKO_API_KEY in backend/.env):   python -m app.scripts.meko_check
Creates one datapack named "AdPilot · connection test". Prints no secrets.
"""
from __future__ import annotations

import json

from app.services import meko_memory as m

USED = ["datapack_create", "datapack_list", "memory_add", "memory_promote", "context_search",
        "conversation_create", "conversation_add_message"]


def short(x, n=300) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s[:n] + ("…" if len(s) > n else "")


def main() -> None:
    if not m.configured():
        print("MEKO_API_KEY is not set in backend/.env")
        return
    s = m._Session(20)
    try:
        info = s.initialize()
        print("server:", short(info.get("serverInfo"), 120), "| protocol:", info.get("protocolVersion"))
        tools = {t["name"]: t for t in s.list_tools()}
        print(f"{len(tools)} tools\n")
        for name in USED:
            t = tools.get(name)
            if not t:
                print(f"!! {name}: NOT on this server")
                continue
            sch = t.get("inputSchema", {})
            print(f"{name}: params={sorted(sch.get('properties', {}))} required={sch.get('required', [])}")
        print("\n--- live calls (the same sequence the app uses) ---")
        cid0 = s.conversation(m.AGENTS["brand"], None, "AdPilot connection test · setup")
        print("conversation_create ->", cid0)
        dp_res = s.call("datapack_create", {"name": "AdPilot · connection test", "conversation_id": cid0})
        print("datapack_create ->", short(dp_res))
        dp = m._find_id(dp_res, "datapack_id", "id")
        print("datapack id found:", dp)
        cid = s.conversation(m.AGENTS["brand"], dp, "AdPilot connection test")
        r = s.call("memory_add", {"text": "AdPilot connection test: Velvaa Skin is a fictional demo brand.",
                                  "agent_id": m.AGENTS["brand"], "datapack_id": dp, "conversation_id": cid})
        print("memory_add ->", short(r))
        mid = m._find_id(r, "memory_id", "id")
        print("context_search ->", short(s.call("context_search", {"query": "Velvaa Skin", "agent_id": m.AGENTS["brand"],
                                                                     "datapack_id": dp, "conversation_id": cid, "limit": 3})))
        print("conversation_add_message ->", short(s.call("conversation_add_message", {
            "conversation_id": cid, "agent_id": m.AGENTS["brand"], "datapack_id": dp,
            "input": "test input", "output": "test output", "plan": ["step 1", "step 2"]})))
        if mid:
            try:
                print("memory_promote ->", short(s.call("memory_promote", {"memory_ids": [mid], "agent_id": m.AGENTS["brand"],
                                                                          "conversation_id": cid, "datapack_id": dp})))
            except Exception as exc:
                print("memory_promote (optional) failed:", exc)
        print("\nALL CALLS OK")
    except Exception as exc:  # show the exact failure so we can fix parameter names
        print("\nFAILED:", type(exc).__name__, exc)
    finally:
        s.close()


if __name__ == "__main__":
    main()
