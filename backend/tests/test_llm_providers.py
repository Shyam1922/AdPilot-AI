"""Provider fallback: Gemini down -> next configured provider answers; all down -> offline generator."""
import json

import httpx
from pydantic import BaseModel

from app.config import settings
from app.services import llm


class Out(BaseModel):
    answer: str


class _Resp:
    def __init__(self, code, payload):
        self.status_code, self._p, self.text = code, payload, json.dumps(payload)

    def json(self):
        return self._p


def _set(monkeypatch, **kw):
    for k, v in kw.items():
        object.__setattr__(settings, k, v)


def _reset_breakers():
    llm._breaker.update(until=0.0, reason="")
    llm._oai_breaker.clear()


def _fake(gemini_code, groq_code):
    calls = []

    def post(url, **kw):
        calls.append(url)
        if "generativelanguage" in url:
            return _Resp(gemini_code, {"error": {"message": "busy"}} if gemini_code != 200 else
                         {"candidates": [{"content": {"parts": [{"text": '{"answer":"from gemini"}'}]}}]})
        if "groq" in url:
            return _Resp(groq_code, {"choices": [{"message": {"content": '{"answer":"from groq"}'}}]}
                         if groq_code == 200 else {"error": "x"})
        raise httpx.ConnectError("no")
    return post, calls


def _run():
    return llm.generate_json("t", "say hi", Out, lambda: Out(answer="offline"))


def test_gemini_down_groq_answers(monkeypatch):
    old = {k: getattr(settings, k) for k in ("llm_provider", "gemini_api_key", "groq_api_key")}
    try:
        _set(monkeypatch, llm_provider="auto", gemini_api_key="g", groq_api_key="k")
        _reset_breakers()
        post, calls = _fake(503, 200)
        monkeypatch.setattr(llm.httpx, "post", post)
        r = _run()
        assert r.mode == "groq" and r.data.answer == "from groq" and any("unavailable" in w for w in r.warnings)
        assert llm.providers_status()[1]["name"] == "groq"
    finally:
        for k, v in old.items():
            _set(monkeypatch, **{k: v})
        _reset_breakers()


def test_all_down_uses_offline(monkeypatch):
    old = {k: getattr(settings, k) for k in ("llm_provider", "gemini_api_key", "groq_api_key")}
    try:
        _set(monkeypatch, llm_provider="auto", gemini_api_key="g", groq_api_key="k")
        _reset_breakers()
        post, _ = _fake(503, 500)
        monkeypatch.setattr(llm.httpx, "post", post)
        r = _run()
        assert r.mode == "offline" and r.data.answer == "offline"
    finally:
        for k, v in old.items():
            _set(monkeypatch, **{k: v})
        _reset_breakers()


def test_no_keys_is_offline():
    assert llm.active_provider() == "offline"
