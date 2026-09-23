"""Deterministic fake Wikimedia API, used by tests and offline demos.

Enabled only with WIKITREND_FAKE_API=1. Every result produced in this mode is
marked "demo_data": true — never present it as real Wikipedia data.

Responses mimic the real endpoints' JSON shape. Series properties come from a
hash of (lang, title), except for a few special words in the topic:
  "grow" -> +40%/yr, "decline" -> -30%/yr, "viral"/"eclipse" -> one huge spike,
  "tiny"/"quipu" -> ~10 views/day, "seasonal"/"fasting"/"diet" -> January peak,
  "missing" -> no cs/sk article.
"""
from __future__ import annotations

import hashlib
import math
import random
from datetime import date, timedelta
from urllib.parse import unquote

LANG_SIZE = {"en": 20000, "de": 4000, "fr": 3500, "es": 3500, "ru": 3000, "ja": 3000,
             "pl": 1500, "it": 2000, "uk": 900, "cs": 600, "sk": 200, "nl": 900, "pt": 1500}
LANG_TOTAL = {"en": 250e6, "de": 30e6, "fr": 25e6, "es": 30e6, "ru": 30e6, "ja": 35e6,
              "pl": 9e6, "it": 12e6, "uk": 4e6, "cs": 3e6, "sk": 0.8e6, "nl": 5e6, "pt": 8e6}
_TOPICS: dict[str, str] = {}   # qid -> topic text


def _h(*parts) -> int:
    return int(hashlib.md5("|".join(parts).encode()).hexdigest()[:8], 16)


def _qid(q: str) -> str:
    qid = f"Q{900000 + _h(q.lower()) % 99999}"
    _TOPICS[qid] = q
    return qid


def _day(ts: str) -> date:
    return date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))


def _series_params(lang: str, title: str):
    t = title.lower()
    h = _h(lang, title)
    growth = (h % 70 - 30) / 100            # -30%..+40% per year
    if "grow" in t:
        growth = 0.40
    if "decline" in t:
        growth = -0.30
    level = LANG_SIZE.get(lang, 300) * (0.5 + (h % 100) / 100)
    if "tiny" in t or "quipu" in t:
        level = 10
    viral = "viral" in t or "eclipse" in t
    seasonal = any(w in t for w in ("seasonal", "fasting", "diet"))
    return growth, level, viral, seasonal, h


def _daily(lang: str, title: str, start: date, end: date):
    growth, level, viral, seasonal, h = _series_params(lang, unquote(title).replace("_", " "))
    rnd = random.Random(h)
    items, d = [], date(2015, 7, 1)
    ref = date(2026, 8, 31)
    while d <= end:
        years = (d - ref).days / 365.25
        mu = level * (1 + growth) ** years * (1 + 0.1 * math.sin(d.weekday()))
        if seasonal:
            mu *= 1 + 0.4 * math.cos(2 * math.pi * (d.timetuple().tm_yday - 10) / 365)
        v = max(0, int(rnd.gauss(mu, math.sqrt(mu) + 0.08 * mu)))
        if (viral and d == date(2025, 3, 3)) or (h % 5 == 0 and d == date(2025, 11, 20)):
            v = int(mu * (40 if viral else 6))
        if viral and date(2025, 3, 3) < d < date(2025, 3, 10):
            v = int(mu * 8)
        if d >= start and v > 0:
            items.append({"project": f"{lang}.wikipedia", "article": title, "granularity": "daily",
                          "timestamp": d.strftime("%Y%m%d00"), "access": "all-access",
                          "agent": "user", "views": v})
        d += timedelta(days=1)
    return {"items": items} if items else None


def _monthly_total(lang: str, start: date, end: date):
    base = LANG_TOTAL.get(lang, 2e6) * 30
    items, d = [], start.replace(day=1)
    while d <= end:
        years = (d - date(2026, 8, 1)).days / 365.25
        items.append({"project": f"{lang}.wikipedia", "access": "all-access", "agent": "user",
                      "granularity": "monthly", "timestamp": d.strftime("%Y%m%d00"),
                      "views": int(base * 0.97 ** years)})
        d = (d + timedelta(days=32)).replace(day=1)
    return {"items": items}


def _sitelinks(topic: str) -> dict:
    missing = "missing" in topic.lower()
    return {f"{lang}wiki": {"title": f"{topic} ({lang})"}
            for lang in LANG_SIZE if not (missing and lang in ("cs", "sk"))}


def handle(url: str, params: dict):
    if "/per-article/" in url:
        parts = url.split("/per-article/")[1].split("/")
        lang, title, start, end = parts[0].split(".")[0], parts[3], parts[5], parts[6]
        if title.endswith("_redirect"):
            return None
        return _daily(lang, title, _day(start), _day(end))
    if "/aggregate/" in url:
        parts = url.split("/aggregate/")[1].split("/")
        return _monthly_total(parts[0].split(".")[0], _day(parts[4]), _day(parts[5]))
    action = params.get("action")
    if action == "wbsearchentities":
        q = params["search"]
        if "nothing" in q.lower():
            return {"search": []}
        qid = _qid(q)
        return {"search": [
            {"id": qid, "label": q, "description": f"demo topic '{q}'"},
            {"id": _qid(q + " (film)"), "label": q + " (film)", "description": "demo film"},
        ]}
    if action == "wbgetentities":
        qid = params["ids"]
        topic = _TOPICS.get(qid, qid)
        return {"entities": {qid: {
            "labels": {"en": {"value": topic}},
            "descriptions": {"en": {"value": f"demo topic '{topic}'"}},
            "sitelinks": _sitelinks(topic)}}}
    if action == "query" and params.get("prop") == "pageprops":
        title = params["titles"]
        return {"query": {"pages": [{"title": title,
                                     "pageprops": {"wikibase_item": _qid(title)}}]}}
    if action == "query" and params.get("prop") == "redirects":
        return {"query": {"pages": [{"title": params["titles"], "redirects": [
            {"title": params["titles"] + " redirect"}]}]}}
    raise ValueError(f"fake API: unsupported request {url} {params}")
