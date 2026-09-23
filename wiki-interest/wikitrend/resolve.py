"""Turn a user topic into one Wikidata item and its article title in each language."""
from __future__ import annotations

import re

from .api import WikiClient

LANG_RE = re.compile(r"^[a-z]{2,3}(-[a-z]+)*$")
QID_RE = re.compile(r"^Q\d+$")
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
SKIP_DESCRIPTIONS = ("disambiguation page", "wikimedia list", "wikimedia category",
                     "wikimedia template", "сторінка значень", "wikimedia-begriffsklärungsseite")


def parse_langs(s: str) -> list[str]:
    langs = [x.strip().lower() for x in s.replace(";", ",").split(",") if x.strip()]
    bad = [x for x in langs if not LANG_RE.match(x)]
    if bad:
        raise ValueError(f"invalid language code(s): {bad}; use Wikipedia codes like uk,pl,cs,en")
    return list(dict.fromkeys(langs))


def _search_order(topic: str, langs: list[str], search_lang: str | None) -> list[str]:
    if search_lang:
        order = [search_lang]
    elif CYRILLIC.search(topic):
        order = ["uk", "ru"]
    else:
        order = ["en"]
    return list(dict.fromkeys(order + ["en"] + langs))


def resolve_topic(client: WikiClient, topic: str, langs: list[str],
                  search_lang: str | None = None) -> dict:
    """Resolve `topic` given as free text, a QID (Q123) or an article (uk:Астрономія)."""
    topic = topic.strip()
    qid, candidates, how = None, [], None
    m = re.match(r"^([a-z-]{2,12}):(.+)$", topic)
    if QID_RE.match(topic):
        qid, how = topic, "qid"
    elif m and LANG_RE.match(m.group(1)):
        how = "article"
        qid = client.qid_for_article(m.group(1), m.group(2))
        if qid is None:
            return {"input": topic, "status": "not_found",
                    "error": f"article {m.group(2)!r} not found in {m.group(1)}.wikipedia"}
    else:
        how = "search"
        for lang in _search_order(topic, langs, search_lang):
            found = [c for c in client.search_wikidata(topic, lang)
                     if not any(s in c["description"].lower() for s in SKIP_DESCRIPTIONS)]
            if found:
                candidates, qid = found, found[0]["qid"]
                break
        if qid is None:
            return {"input": topic, "status": "not_found",
                    "error": "no Wikidata item found; try an English name or lang:Article"}

    ent = client.entity(qid)
    titles = {lang: ent["sitelinks"].get(lang) for lang in langs}
    out = {
        "input": topic, "status": "ok", "resolved_by": how, "qid": qid,
        "label": ent["label"], "description": ent["description"], "titles": titles,
        "available_in": len(ent["sitelinks"]),
    }
    if len(candidates) > 1:
        out["other_candidates"] = [
            f'{c["qid"]}: {c["label"]} ({c["description"]})' for c in candidates[1:3]]
    missing = [lang for lang, t in titles.items() if not t]
    if missing:
        out["missing_in"] = missing
    return out
