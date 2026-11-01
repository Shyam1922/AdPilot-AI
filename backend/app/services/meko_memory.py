"""Meko (by Yugabyte) shared agent memory, used as AdPilot's cloud Brand Memory.

Meko exposes its memory/knowledge tools through an MCP server (https://mcp.mekodata.ai/mcp).
We speak the MCP "streamable HTTP" protocol directly with httpx (JSON-RPC 2.0 over POST,
responses as JSON or Server-Sent Events). That avoids depending on a fast-changing SDK.

AdPilot's agents and what they do in Meko (one datapack per brand):
  adpilot-brand-agent     memory_add: brand facts + approved claims after analysis
  adpilot-creative-agent  context_search before writing concepts; conversation log of each run
  adpilot-analyst-agent   memory_add + memory_promote: learnings after optimization (G3)

Every call has a short timeout. If Meko is not configured or fails, callers get None and the
app keeps working with local Brand Memory; the failure is recorded, never hidden.
"""
from __future__ import annotations

import itertools
import json
import logging
import time
from typing import Any

import httpx

from ..config import settings

log = logging.getLogger("adpilot.meko")

PROTOCOL_VERSION = "2025-06-18"
AGENTS = {"brand": "adpilot-brand-agent", "creative": "adpilot-creative-agent", "analyst": "adpilot-analyst-agent"}

_last: dict[str, Any] = {"ok": None, "error": "", "at": 0.0, "tools": 0}


class MekoError(Exception):
    pass


def configured() -> bool:
    return bool(settings.meko_api_key)


def status() -> dict:
    return {"configured": configured(), "last_ok": _last["ok"], "last_error": _last["error"],
            "last_checked": _last["at"], "tool_count": _last["tools"], "endpoint": settings.meko_url}


def _auth_headers() -> dict[str, str]:
    name = settings.meko_auth_header
    value = f"{settings.meko_auth_scheme} {settings.meko_api_key}".strip() if settings.meko_auth_scheme \
        else settings.meko_api_key
    return {name: value}


def _parse(resp: httpx.Response, want_id: int) -> dict:
    """A JSON-RPC response may arrive as plain JSON or inside an SSE stream."""
    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == want_id:
                    return msg
        raise MekoError("No matching response in event stream.")
    return resp.json()


class _Session:
    """One short-lived MCP session: initialize, call tools, done."""

    def __init__(self, timeout: float):
        self.client = httpx.Client(timeout=httpx.Timeout(timeout, connect=max(timeout, 30.0)))
        self.session_id: str | None = None
        self.ids = itertools.count(1)

    def _post(self, payload: dict, expect_reply: bool = True) -> dict | None:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL_VERSION, **_auth_headers()}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        r = self.client.post(settings.meko_url, json=payload, headers=headers)
        if r.status_code in (401, 403):
            raise MekoError(f"Meko rejected the API key (HTTP {r.status_code}). Check MEKO_API_KEY / MEKO_AUTH_* settings.")
        if r.status_code >= 400:
            raise MekoError(f"Meko HTTP {r.status_code}: {r.text[:200]}")
        self.session_id = r.headers.get("mcp-session-id", self.session_id)
        if not expect_reply:
            return None
        msg = _parse(r, payload["id"])
        if "error" in msg:
            raise MekoError(f"Meko error: {msg['error'].get('message', msg['error'])}")
        return msg.get("result", {})

    def initialize(self) -> dict:
        res = self._post({"jsonrpc": "2.0", "id": next(self.ids), "method": "initialize",
                          "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                     "clientInfo": {"name": "adpilot-ai", "version": "0.1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)
        return res or {}

    def list_tools(self) -> list[dict]:
        return (self._post({"jsonrpc": "2.0", "id": next(self.ids), "method": "tools/list", "params": {}}) or {}).get("tools", [])

    def call(self, tool: str, args: dict) -> Any:
        args = {k: v for k, v in args.items() if v is not None}
        if isinstance(args.get("metadata"), (dict, list)):  # Meko's live server expects metadata as a JSON string
            args["metadata"] = json.dumps(args["metadata"])
        res = self._post({"jsonrpc": "2.0", "id": next(self.ids), "method": "tools/call",
                          "params": {"name": tool, "arguments": args}}) or {}
        if res.get("isError"):
            text = " ".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
            raise MekoError(f"{tool} failed: {text[:300]}")
        if res.get("structuredContent") is not None:
            out = res["structuredContent"]
        else:
            texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
            out = "\n".join(texts)
        out = _unwrap(out)
        if isinstance(out, dict) and out.get("error"):
            raise MekoError(f"{tool} failed: {out.get('error')} {out.get('detail', '')}".strip())
        return out

    def conversation(self, agent: str, datapack_id: str | None, title: str) -> str:
        """Most Meko tools require a conversation_id: open one for this agent action."""
        res = self.call("conversation_create", {"agent_id": agent, "datapack_id": datapack_id, "title": title,
                                                "metadata": {"source": "adpilot"}})
        cid = _find_id(res, "conversation_id", "id")
        if not cid:
            raise MekoError(f"conversation_create returned no id: {str(res)[:200]}")
        return cid

    def close(self) -> None:
        self.client.close()


def _unwrap(obj: Any) -> Any:
    """Meko sometimes wraps payloads as {"result": "<json text>"}; decode until we reach data."""
    for _ in range(4):
        if isinstance(obj, str):
            try:
                obj = json.loads(obj)
                continue
            except (json.JSONDecodeError, TypeError):
                return obj
        if isinstance(obj, dict) and set(obj) == {"result"} and isinstance(obj["result"], (str, dict, list)):
            obj = obj["result"]
            continue
        return obj
    return obj


def _run(fn, timeout: float | None = None, attempts: int = 2):
    """Open a session, run fn(session), record health. Returns None on any failure.
    A timed-out call is retried once on a fresh session (Meko's TLS handshake is sometimes slow)."""
    if not configured():
        return None
    for attempt in range(attempts):
        s = _Session(max(timeout or 0, settings.meko_timeout_s))
        try:
            s.initialize()
            out = fn(s)
            _last.update(ok=True, error="", at=time.time())
            return out
        except httpx.TimeoutException as exc:
            _last.update(ok=False, error=f"Meko timed out ({type(exc).__name__}). Check your connection or raise MEKO_TIMEOUT_S.",
                         at=time.time())
            log.warning("meko call timed out (attempt %d/%d): %s", attempt + 1, attempts, exc)
        except (MekoError, httpx.HTTPError, ValueError, OSError) as exc:
            _last.update(ok=False, error=str(exc)[:300], at=time.time())
            log.warning("meko call failed: %s", exc)
            return None
        finally:
            s.close()
    return None


def _find_id(obj: Any, *keys: str) -> str | None:
    """Pull an id out of a tool result whose exact shape we don't control."""
    if isinstance(obj, dict):
        for k in keys:
            if obj.get(k):
                return str(obj[k])
        for v in obj.values():
            found = _find_id(v, *keys)
            if found:
                return found
    if isinstance(obj, list):
        for v in obj:
            found = _find_id(v, *keys)
            if found:
                return found
    return None


# --------------------------------------------------------------------------- public API
def test_connection() -> dict:
    """Live check for the Integrations page and for judges."""
    if not configured():
        return {"ok": False, "configured": False, "message": "Set MEKO_API_KEY in backend/.env to connect Meko."}

    def go(s: _Session):
        tools = s.list_tools()
        names = sorted(t.get("name", "") for t in tools)
        _last["tools"] = len(names)
        packs = None
        if "datapack_list" in names:
            cid = s.conversation(AGENTS["brand"], None, "Connection test")
            packs = s.call("datapack_list", {"limit": 5, "conversation_id": cid})
        return {"ok": True, "configured": True, "tool_count": len(names), "tools": names, "datapacks": packs}

    res = _run(go, timeout=15)
    return res or {"ok": False, "configured": True, "message": _last["error"] or "Could not reach Meko."}


def _find_named(obj, name: str):
    """Walk a datapack_list result and return the id of the datapack called `name`."""
    if isinstance(obj, dict):
        if obj.get("name") == name:
            return obj.get("datapack_id") or obj.get("id")
        for v in obj.values():
            r = _find_named(v, name)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_named(v, name)
            if r:
                return r
    return None


def _list_packs(obj, out=None):
    """Collect (name, id) pairs from a datapack_list result of unknown shape."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        i = obj.get("datapack_id") or obj.get("id") or obj.get("uuid")
        n = obj.get("name") or obj.get("datapack_name") or obj.get("title")
        if i and n:
            out.append((str(n), str(i)))
        for v in obj.values():
            _list_packs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _list_packs(v, out)
    return out


_CACHE = settings.storage_dir.parent / ".meko_datapacks.json"   # survives reset_demo (which wipes storage/)


def _cache_get(name: str) -> str | None:
    try:
        return json.loads(_CACHE.read_text()).get(name)
    except (OSError, ValueError):
        return None


def _cache_put(name: str, dp: str | None) -> None:
    if not dp:
        return
    try:
        data = json.loads(_CACHE.read_text()) if _CACHE.exists() else {}
    except (OSError, ValueError):
        data = {}
    data[name] = dp
    try:
        _CACHE.write_text(json.dumps(data, indent=2))
    except OSError:
        pass


def tag(brand: str, text: str) -> str:
    """All brands share one datapack (free plans cap how many datapacks you can create), so every
    memory and every search is tagged with the brand name to keep brands apart."""
    return f"[Brand: {brand}] {text}" if brand else text


def ensure_datapack(brand_name: str, brand_id: int, existing: str | None) -> str | None:
    """One datapack per brand (clean isolation). Order: MEKO_DATAPACK_ID override, the saved id, an
    existing AdPilot datapack for this brand (matched by brand name, so datapacks from earlier test
    runs are reused instead of using up the plan's limit), then a new one."""
    if settings.meko_datapack_id:
        return settings.meko_datapack_id
    if existing:
        return existing

    def go(s: _Session):
        name = f"AdPilot · {brand_name}"
        cached = _cache_get(name)
        if cached:
            return cached
        cid = s.conversation(AGENTS["brand"], None, f"Set up datapack · {brand_name}")
        packs = _list_packs(s.call("datapack_list", {"limit": 100, "conversation_id": cid}))
        for n, i in packs:
            if n == name or (n.lower().startswith("adpilot") and brand_name.lower() in n.lower()):
                return i
        last = None
        for attempt in range(3):   # a name can exist without being listed (other account view): use a new one
            try_name = name if attempt == 0 else f"{name} {attempt + 1}"
            try:
                res = s.call("datapack_create", {"name": try_name, "conversation_id": cid})
                return _find_id(res, "datapack_id", "id")
            except MekoError as exc:
                last = exc
                if "FREE_TIER" in str(exc) or "already exists" not in str(exc).lower():
                    break
        raise MekoError(f"{last} (datapacks seen in list: {len(packs)}). If this is a limit error, delete unused "
                        f"datapacks in Meko or set MEKO_DATAPACK_ID.")

    dp = _run(go, timeout=45)
    _cache_put(f"AdPilot · {brand_name}", dp)
    return dp


def sync_brand(datapack_id: str, profile: dict) -> dict | None:
    """Save the brand's verified facts as Meko memories (brand agent), inside one traced conversation."""
    claims = [f"- {c['claim']} (source {c['source']})" for c in profile.get("approved_claims", [])]
    facts = [
        f"Brand {profile.get('brand_name')} sells {profile.get('product_category')}. "
        f"Products: {', '.join(p['name'] + (' at ' + p['price'] if p.get('price') else '') for p in profile.get('products', []))}.",
        "Approved claims (verified against the brand's website):\n" + "\n".join(claims[:12]),
        f"Brand tone: {', '.join(profile.get('brand_tone', []))}. "
        f"Differentiators: {'; '.join(profile.get('differentiators', []))}.",
        "Unconfirmed, do not claim: " + "; ".join(profile.get("unknowns_to_confirm", [])),
    ]

    bn = profile.get("brand_name") or ""

    def go(s: _Session):
        agent = AGENTS["brand"]
        cid = s.conversation(agent, datapack_id, f"Brand Memory sync · {profile.get('brand_name')}")
        s.call("conversation_add_message", {"conversation_id": cid, "agent_id": agent, "datapack_id": datapack_id,
                                            "input": "Sync verified Brand Memory from AdPilot analysis",
                                            "output": "\n\n".join(facts),
                                            "plan": ["extract site", "ground claims", "store facts as memories"]})
        ids = []
        for text in facts:
            r = s.call("memory_add", {"text": tag(bn, text), "agent_id": agent, "datapack_id": datapack_id,
                                      "conversation_id": cid,
                                      "metadata": {"source": "adpilot", "kind": "brand_fact", "brand": bn}})
            ids.append(_find_id(r, "memory_id", "id"))
        return {"memories_added": len(facts), "memory_ids": [i for i in ids if i], "conversation_id": cid}

    return _run(go, timeout=60)


def context_for_generation(datapack_id: str, query: str, title: str = "Concept generation", brand: str = "") -> tuple[str, str | None]:
    """Creative agent opens a conversation and pulls relevant memories / learnings.
    Returns (context_text, conversation_id); ("", None) if Meko is unavailable."""
    def go(s: _Session):
        agent = AGENTS["creative"]
        cid = s.conversation(agent, datapack_id, title)
        res = s.call("context_search", {"query": tag(brand, query), "agent_id": agent, "datapack_id": datapack_id,
                                         "conversation_id": cid, "limit": 8})
        return res, cid

    out = _run(go, timeout=10)
    if not out:
        return "", None
    res, cid = out
    text = res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)
    return text[:4000], cid


def log_generation(datapack_id: str, conversation_id: str | None, campaign_name: str, request: str,
                   output_summary: str, plan: list[str]) -> dict | None:
    """Record the generation run (decision trace) in the creative agent's conversation."""
    def go(s: _Session):
        agent = AGENTS["creative"]
        cid = conversation_id or s.conversation(agent, datapack_id, f"Concepts · {campaign_name}")
        s.call("conversation_add_message", {"conversation_id": cid, "agent_id": agent, "datapack_id": datapack_id,
                                            "input": request, "output": output_summary, "plan": plan})
        return {"conversation_id": cid}

    return _run(go, timeout=45)


def promotion_policy(text: str) -> tuple[bool, str]:
    """Code decides what becomes shared knowledge, not the model. A learning is held back (kept private to the
    analyst agent) when it rests on too little data, so a weak guess can't steer every other agent."""
    t = (text or "").lower()
    if "insufficient data" in t:
        return False, "held: too little data to rely on"
    if len(t.strip()) < 25:
        return False, "held: too short to be a usable learning"
    return True, "promoted: states its data source and a usable sample"


def save_learnings(datapack_id: str, learnings: list[str], kind: str = "learning",
                   title: str = "Optimization learnings", brand: str = "") -> dict | None:
    """Analyst agent stores every learning (private), promotes only those the policy approves, and writes the
    decision (what was promoted, what was held and why) into the conversation trace."""
    def go(s: _Session):
        agent = AGENTS["analyst"]
        cid = s.conversation(agent, datapack_id, title)
        ids, approved, held = [], [], []
        for text in learnings:
            ok, why = promotion_policy(text)
            r = s.call("memory_add", {"text": tag(brand, text), "agent_id": agent, "datapack_id": datapack_id,
                                      "conversation_id": cid,
                                      "metadata": {"source": "adpilot", "kind": kind, "brand": brand,
                                                   "promotion": "promoted" if ok else "held"}})
            mid = _find_id(r, "memory_id", "id")
            if mid:
                ids.append(mid)
                (approved if ok else held).append((mid, why, text))
        promoted = None
        if approved:
            try:
                promoted = s.call("memory_promote", {"memory_ids": [m for m, _, _ in approved], "agent_id": agent,
                                                     "conversation_id": cid, "datapack_id": datapack_id})
            except MekoError as exc:  # promotion needs owner/maintainer rights; keep the memories anyway
                promoted = {"error": str(exc)}
        try:                                          # the decision itself is part of the trace
            lines = [f"- {why}: {text[:140]}" for _, why, text in [*approved, *held]]
            s.call("conversation_add_message", {"conversation_id": cid, "agent_id": agent, "datapack_id": datapack_id,
                                                "input": f"Promotion policy for {len(learnings)} learning(s)",
                                                "output": "\n".join(lines) or "nothing to promote",
                                                "plan": ["store privately", "apply promotion policy", "promote approved"]})
        except MekoError:
            pass
        return {"memories_added": len(learnings), "memory_ids": ids, "promoted": promoted,
                "promoted_count": len(approved), "held_count": len(held), "conversation_id": cid}

    return _run(go, timeout=60)


def read_memory(datapack_id: str, queries: list[str], title: str = "Memory view", brand: str = "") -> dict[str, str]:
    """What Meko remembers, for display: one context search per question. {} if Meko is unavailable."""
    def go(s: _Session):
        agent = AGENTS["creative"]
        cid = s.conversation(agent, datapack_id, title)
        out = {}
        for q in queries:
            res = s.call("context_search", {"query": tag(brand, q), "agent_id": agent, "datapack_id": datapack_id,
                                             "conversation_id": cid, "limit": 6})
            out[q] = (res if isinstance(res, str) else json.dumps(res, ensure_ascii=False))[:2500]
        return out

    return _run(go, timeout=20) or {}
