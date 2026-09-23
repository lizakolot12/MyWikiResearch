"""Orchestrates one analysis run: resolve topics, fetch views, compute metrics, save."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from .api import WikiClient, month_end
from .i18n import CHECKLIST, TEXT, headline, lang_or_en, reason_text
from .metrics import add_months, analyze_series
from .resolve import resolve_topic

MAX_REDIRECTS = 20
RANK_KEYS = {
    "growth": "trend_pct_yr", "growth_rel": "trend_rel_pct_yr", "yoy": "yoy_pct",
    "size": "daily_median_90d", "share": "per_million",
}


def last_complete_month(today: date | None = None) -> date:
    today = today or date.today()
    return add_months(today.replace(day=1), -1)


def parse_month(s: str) -> date:
    return datetime.strptime(s, "%Y-%m").date()


def _fetch_article(client: WikiClient, lang, title, start, end, access, with_redirects):
    daily = client.daily_views(lang, title, start, end, access)
    info = {"redirects_total": 0, "redirects_used": 0}
    if with_redirects:
        reds = client.redirects(lang, title)
        info["redirects_total"] = len(reds)
        for r in reds[:MAX_REDIRECTS]:
            for d, v in client.daily_views(lang, r, start, end, access).items():
                daily[d] = daily.get(d, 0) + v
        info["redirects_used"] = min(len(reds), MAX_REDIRECTS)
    return daily, info


def run_analysis(client: WikiClient, topics: list[str], langs: list[str], months: int = 24,
                 end_month: date | None = None, access: str = "all-access",
                 with_redirects: bool = True, rank_by: str = "growth",
                 search_lang: str | None = None) -> dict:
    end_m = end_month or last_complete_month()
    window_start = add_months(end_m, -(months - 1))
    window_end = month_end(end_m)
    fetch_start = min(window_start, add_months(end_m, -14))  # YoY needs 15 months

    resolved = [resolve_topic(client, t, langs, search_lang) for t in topics]
    jobs = [(r, lang, r["titles"][lang]) for r in resolved if r["status"] == "ok"
            for lang in langs]

    def work(job):
        r, lang, title = job
        base = {"topic": r["label"], "qid": r["qid"], "lang": lang, "article": title,
                "id": f"{lang}:{r['label']}"}
        if not title:
            return {**base, "status": "missing_article",
                    "note": f"no {lang}.wikipedia article linked to {r['qid']}"}
        daily, info = _fetch_article(client, lang, title, fetch_start, window_end, access,
                                     with_redirects)
        totals = client.monthly_totals(lang, fetch_start, window_end, access)
        res = analyze_series(daily, totals, window_start, window_end)
        res["_daily"] = daily
        res["_totals"] = totals
        if info["redirects_total"] > info["redirects_used"]:
            res.setdefault("_reason_codes", []).append(
                ["redirects_capped", {"used": info["redirects_used"],
                                      "total": info["redirects_total"]}])
        res["reasons"] = [reason_text(c, p) for c, p in res.get("_reason_codes", [])]
        return {**base, **res, "redirects_counted": info["redirects_used"]}

    with ThreadPoolExecutor(max_workers=6) as pool:
        series = list(pool.map(work, jobs))
    combined = combine_by_lang(series, langs, window_start, window_end)
    for s in series:
        s.pop("_daily", None)
        s.pop("_totals", None)

    key = RANK_KEYS.get(rank_by, "trend_pct_yr")
    ranked = sorted([s for s in rank_pool(series, combined) if s.get(key) is not None],
                    key=lambda s: -s[key])
    run = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "window": f"{window_start:%Y-%m}..{end_m:%Y-%m}",
        "months": months, "access": access, "agent": "user (bots excluded)",
        "redirects_included": with_redirects,
        "topics": resolved,
        "series": series,
        "combined": combined,
        "ranking": {"by": rank_by, "metric": key,
                    "order": [f"{s['id']} ({s[key]})" for s in ranked]},
        "api_requests": client.requests_made,
    }
    return run


def rank_pool(series: list[dict], combined: list[dict]) -> list[dict]:
    """One entry per language: its combined series, or its only series if there is one."""
    langs = {c["lang"] for c in combined}
    return combined + [s for s in series if s["lang"] not in langs]


UP = ("growing", "slow_growth")
DOWN = ("declining", "slow_decline")


def combine_by_lang(series: list[dict], langs: list[str], window_start, window_end) -> list[dict]:
    """With several topics: one series per language = sum of all topic articles.

    Also reports whether the individual topics agree, so a conclusion per
    language does not hide topics that move in opposite directions.
    """
    out = []
    for lang in langs:
        ok = [s for s in series if s["lang"] == lang and s.get("status") == "ok"]
        if len(ok) < 2:
            continue
        daily: dict = {}
        for s in ok:
            for d, v in s["_daily"].items():
                daily[d] = daily.get(d, 0) + v
        res = analyze_series(daily, ok[0]["_totals"], window_start, window_end)
        res["reasons"] = [reason_text(c, p) for c, p in res.get("_reason_codes", [])]
        up = sum(s["verdict"] in UP for s in ok)
        down = sum(s["verdict"] in DOWN for s in ok)
        counts = {"up": up, "down": down, "flat": len(ok) - up - down, "n": len(ok)}
        agree = TEXT["en"]["agreement"].format(**counts)
        if up and down:
            res["_reason_codes"].append(["topics_disagree", counts])
            res["reasons"].append(reason_text("topics_disagree", counts))
            if res["confidence"] == "high":
                res["confidence"] = "medium"
        out.append({"id": f"{lang}:ALL({len(ok)} topics)", "lang": lang, "topic": "ALL",
                    "qid": "ALL", "article": " + ".join(s["article"] for s in ok),
                    "topics_agreement": agree, "_agreement": counts, **res})
    return out


# ---- persistence --------------------------------------------------------------
def runs_dir(cache_dir: Path) -> Path:
    d = Path(cache_dir) / "runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(run: dict, cache_dir: Path) -> Path:
    path = runs_dir(cache_dir) / f"{run['run_id']}.json"
    path.write_text(json.dumps(run, ensure_ascii=False, indent=1))
    (runs_dir(cache_dir) / "last.txt").write_text(run["run_id"])
    return path


def load_run(cache_dir: Path, run_id: str = "last") -> dict:
    d = runs_dir(cache_dir)
    if run_id == "last":
        if not (d / "last.txt").exists():
            raise FileNotFoundError("no previous run; call `analyze` first")
        run_id = (d / "last.txt").read_text().strip()
    return json.loads((d / f"{run_id}.json").read_text())


def compact(run: dict, lang: str = "en") -> dict:
    """What the agent sees: all conclusions, no per-month data (use `show` for that).

    Headlines, reasons and the checklist are in `lang`, so the agent quotes them
    instead of translating (translation by a small model is where calques come from).
    """
    lang = lang_or_en(lang)
    out = {"headlines": [headline(s, lang) for s in run.get("combined", []) + run["series"]],
           "answer_checklist": CHECKLIST[lang]}
    out.update({k: v for k, v in run.items() if k not in ("series", "topics", "combined")})
    out["topics"] = [{k: v for k, v in t.items() if k != "titles"} for t in run["topics"]]

    def strip(s: dict) -> dict:
        s = {**s, "reasons": [reason_text(c, p, lang) for c, p in s.get("_reason_codes", [])]}
        if s.get("_agreement"):
            s["topics_agreement"] = TEXT[lang]["agreement"].format(**s["_agreement"])
        return {k: v for k, v in s.items()
                if not k.startswith("_") and v is not None and v != []}
    if run.get("combined"):
        out["combined"] = [strip(s) for s in run["combined"]]
    out["series"] = [strip(s) for s in run["series"]]
    return out


def monthly_table(run: dict, series_id: str | None = None) -> str:
    lines = []
    for s in run.get("combined", []) + run["series"]:
        if series_id and series_id.lower() not in s["id"].lower():
            continue
        if "_monthly" not in s:
            lines.append(f"# {s['id']}: {s.get('status')}")
            continue
        lines.append(f"# {s['id']} — {s['article']}")
        lines.append("month    avg/day  avg/day(no spikes)  per_million")
        for m, (raw, clean, tot) in s["_monthly"].items():
            days = (month_end(parse_month(m)) - parse_month(m)).days + 1
            pm = f"{clean * days / tot * 1e6:.2f}" if tot else "-"
            lines.append(f"{m}  {raw:>8.1f}  {clean:>18.1f}  {pm:>11}")
    return "\n".join(lines) or "no matching series"

