#!/usr/bin/env python3
"""wiki-interest CLI: Wikipedia pageview research for product decisions.

Commands (all print compact JSON unless stated otherwise):
  resolve  --topics "Astronomy" --langs uk,pl        find the article in each language
  analyze  --topics "Astronomy" --langs uk,pl,cs     fetch + metrics + chart (main command)
  show     [--series pl] [--run last]                monthly table for checking a conclusion (text)
  report   --title ... --summary ... [--rec ...]     one-page PDF from the last run
  check-answer  < draft.txt                          self-check of the answer before sending it
  cache    info|clear
  doctor                                             check setup and Wikimedia API access
Run any command with -h for options.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent


def ensure_deps() -> None:
    """Missing packages here but install.py made <skill>/.venv: rerun this command there."""
    try:
        import matplotlib  # noqa: F401
        import numpy  # noqa: F401
        return
    except ImportError as e:
        missing = e.name
    venv_dir = SKILL_DIR / ".venv"
    py = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if py.exists() and Path(sys.prefix).resolve() != venv_dir.resolve():
        os.execv(str(py), [str(py), str(Path(__file__).resolve()), *sys.argv[1:]])
    print(json.dumps({"error": f"missing Python package: {missing}",
                      "fix": f"python {SKILL_DIR / 'install.py'} --deps-only"}))
    sys.exit(2)


ensure_deps()
sys.path.insert(0, str(SKILL_DIR))

from wikitrend.analyze import (RANK_KEYS, compact, load_run, monthly_table,  # noqa: E402
                               parse_month, run_analysis, save_run)
from wikitrend.api import ApiError, WikiClient  # noqa: E402
from wikitrend.cache import DEFAULT_CACHE_DIR, Cache  # noqa: E402
from wikitrend.answer_check import check_answer, run_words  # noqa: E402
from wikitrend.lang_check import check_uk  # noqa: E402
from wikitrend.resolve import parse_langs, resolve_topic  # noqa: E402


def emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def topics_arg(values: list[str]) -> list[str]:
    """Accept both --topics A --topics B and --topics "A; B"."""
    out = []
    for v in values:
        out += [x.strip() for x in v.split(";") if x.strip()]
    return list(dict.fromkeys(out))


def doctor(cache: Cache) -> dict:
    out = {"python": sys.version.split()[0], "cache": cache.stats()["path"]}
    try:
        import matplotlib
        import numpy
        out["deps"] = f"numpy {numpy.__version__}, matplotlib {matplotlib.__version__}"
    except ImportError as e:
        out["deps"] = f"MISSING: {e}; run pip install -r requirements.txt"
    from wikitrend import api
    try:  # straight to the API: a warm cache must not hide a network problem
        views = api.http_get_json(f"{api.PAGEVIEWS}/per-article/en.wikipedia/all-access/user/"
                                  "Wikipedia/daily/2024010100/2024010700")
        found = api.http_get_json(api.WIKIDATA, {"action": "wbgetentities", "ids": "Q52",
                                                 "props": "labels", "format": "json"})
        out["pageviews_api"] = "ok" if (views or {}).get("items") else "no data returned"
        out["wikidata_api"] = "ok" if (found or {}).get("entities") else "no data returned"
    except ApiError as e:
        out["api_error"] = str(e)[:300]
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wiki_interest", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    sub = p.add_subparsers(dest="cmd", required=True)

    def topic_opts(sp):
        sp.add_argument("--topics", action="append", required=True,
                        help='topic text, Q-id or lang:Article; repeat or separate with ";"')
        sp.add_argument("--langs", required=True, help="Wikipedia language codes, e.g. uk,pl,cs")
        sp.add_argument("--search-lang", help="language of the topic text (default: auto)")

    sp = sub.add_parser("resolve", help="find articles for topics")
    topic_opts(sp)

    sp = sub.add_parser("analyze", help="fetch views and compute metrics")
    topic_opts(sp)
    sp.add_argument("--months", type=int, default=24, help="analysis window (default 24)")
    sp.add_argument("--end", help="last month YYYY-MM (default: last complete month)")
    sp.add_argument("--access", default="all-access",
                    choices=["all-access", "desktop", "mobile-web", "mobile-app"])
    sp.add_argument("--no-redirects", action="store_true", help="do not add redirect views")
    sp.add_argument("--rank-by", default="growth", choices=list(RANK_KEYS))
    sp.add_argument("--out", default="wiki-interest-output", help="folder for charts")
    sp.add_argument("--ui-lang", default="uk", choices=["uk", "en"],
                    help="language of headlines, reasons and chart labels (default uk)")

    sp = sub.add_parser("show", help="monthly numbers of a run")
    sp.add_argument("--run", default="last")
    sp.add_argument("--series", help="filter, e.g. 'pl' or 'pl:Astronomy'")

    sp = sub.add_parser("report", help="one-page PDF from a run")
    sp.add_argument("--run", default="last")
    sp.add_argument("--title", required=True)
    sp.add_argument("--summary", default="", help="2-5 sentences: the answer, with numbers")
    sp.add_argument("--rec", action="append", default=[], help="recommendation (repeatable)")
    sp.add_argument("--assumption", action="append", default=[],
                    help="user assumption/criterion to list in limitations (repeatable)")
    sp.add_argument("--out", default="wiki-interest-output/report.pdf")
    sp.add_argument("--ui-lang", default="uk", choices=["uk", "en"])

    sp = sub.add_parser("check-answer", help="check the draft answer (stdin) before sending")
    sp.add_argument("--file", help="read the draft from this file instead of stdin")
    sp.add_argument("--run", default="last", help="run the answer is about (default: last)")

    sub.add_parser("doctor", help="check dependencies, cache and API access")

    sp = sub.add_parser("cache", help="cache info or clear")
    sp.add_argument("action", choices=["info", "clear"])

    a = p.parse_args(argv)
    cache = Cache(a.cache_dir)
    client = WikiClient(cache)
    try:
        if a.cmd == "resolve":
            langs = parse_langs(a.langs)
            emit([resolve_topic(client, t, langs, a.search_lang) for t in topics_arg(a.topics)])
        elif a.cmd == "analyze":
            if not 3 <= a.months <= 120:
                raise ValueError("--months must be between 3 and 120")
            run = run_analysis(client, topics_arg(a.topics), parse_langs(a.langs), a.months,
                               parse_month(a.end) if a.end else None, a.access,
                               not a.no_redirects, a.rank_by, a.search_lang)
            from wikitrend.charts import save_chart
            chart = Path(a.out) / f"chart-{run['run_id']}.png"
            if any(s.get("_monthly") for s in run["series"]):
                run["chart"] = str(save_chart(run, chart, a.ui_lang).resolve())
            save_run(run, Path(a.cache_dir))
            emit(compact(run, a.ui_lang))
        elif a.cmd == "show":
            print(monthly_table(load_run(Path(a.cache_dir), a.run), a.series))
        elif a.cmd == "report":
            from wikitrend.report import build_pdf
            run = load_run(Path(a.cache_dir), a.run)
            out = build_pdf(run, Path(a.out), a.title, a.summary, a.rec, a.assumption,
                            a.ui_lang)
            res = {"pdf": str(out.resolve()), "run_id": run["run_id"],
                   "tell_user": "Give the user this PDF path and summarize the findings "
                                "with verdicts and confidence; run check-answer on that "
                                "answer before sending it."}
            if a.ui_lang == "uk":
                warnings = check_uk("\n".join([a.title, a.summary, *a.rec, *a.assumption]),
                                    run_words(run))
                if warnings:
                    res["language_warnings"] = warnings
                    res["tell_user"] = ("Fix these phrases in your title/summary/recs, rerun "
                                        "`report` with the same --out, then " +
                                        res["tell_user"][0].lower() + res["tell_user"][1:])
            emit(res)
        elif a.cmd == "check-answer":
            text = Path(a.file).read_text() if a.file else sys.stdin.read()
            if not text.strip():
                raise ValueError("empty answer: pass the full draft on stdin (heredoc)")
            try:
                run = load_run(Path(a.cache_dir), a.run)
            except FileNotFoundError:
                run = None
            emit(check_answer(text, run))
        elif a.cmd == "doctor":
            emit(doctor(cache))
        elif a.cmd == "cache":
            if a.action == "clear":
                cache.clear()
            emit(cache.stats())
    except (ApiError, ValueError, FileNotFoundError) as e:
        emit({"error": str(e)})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
