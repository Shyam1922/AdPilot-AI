"""Small shared text helpers (tokenising, similarity, trimming)."""
from __future__ import annotations

import re

STOP = set("""a an the and or of for to in on with without by from at as is are be this that it its your you our we
our their they them very more most just only into over under up out not no so than then also can will made""".split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9%₹+]+", (text or "").lower()) if t not in STOP and len(t) > 1]


def jaccard(a: str, b: str) -> float:
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def coverage(claim: str, source: str) -> float:
    """Share of the claim's content words that appear in the source text."""
    tc = set(tokens(claim))
    if not tc:
        return 0.0
    ts = set(tokens(source))
    return len(tc & ts) / len(tc)


def trim_words(text: str, limit: int) -> tuple[str, bool]:
    text = (text or "").strip()
    if len(text) <= limit:
        return text, False
    cut = text[:limit + 1].rsplit(" ", 1)[0].rstrip(",.;:-–— ")
    return (cut if cut else text[:limit]), True


def sentence(text: str) -> str:
    text = (text or "").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text


def strip_brand(name: str, brand: str) -> str:
    if brand and name.lower().startswith(brand.split()[0].lower() + " "):
        return name[len(brand.split()[0]) + 1:]
    return name


def short_claim(text: str, limit: int = 42) -> str:
    """Shorten a claim without cutting mid-idea: drop a trailing clause, else trim at a word."""
    text = (text or "").strip().rstrip(".")
    if len(text) <= limit:
        return text
    head = re.split(r"\s(?:that|which|with|for|and|so)\s", text, maxsplit=1)[0].rstrip(",;: ")
    if 8 <= len(head) <= limit:
        return head
    return trim_words(text, limit)[0]
