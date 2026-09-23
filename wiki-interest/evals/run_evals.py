#!/usr/bin/env python3
"""Run evals/cases.yaml against a real agent (Claude Code CLI) and score the transcripts.

Each case runs in a fresh temp workspace with the skill installed at
.claude/skills/wiki-interest, so the agent discovers it as a project skill.

  python evals/run_evals.py --model claude-haiku-4-5-20251001            # real Wikimedia API
  python evals/run_evals.py --model claude-haiku-4-5-20251001 --fake     # offline synthetic API
  python evals/run_evals.py --only fasting_pl_cs --keep                  # keep workspace
  python evals/run_evals.py --fake --judge claude-sonnet-5               # + LLM rubric grading

Writes evals/results/<timestamp>.json with per-check results, turns, cost and the answer.
Requires: `claude` CLI logged in, pyyaml.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
TOOLS = "Bash,Read,Write,Edit,Glob,Grep,Skill"
JUDGE_PROMPT = """You grade an AI agent's answer about Wikipedia interest trends.
FACTS = the tool output (JSON) the agent received. ANSWER = what the user saw.
Grade each criterion 1 (met) or 0 (violated):
- verdict_fidelity: every trend claim matches the series' verdict in FACTS (e.g. "stable" or
  "slow_growth" must not be presented as strong growth; "unclear" not as a trend).
- numbers_correct: numbers quoted in ANSWER match FACTS (rounding is fine).
- confidence_stated: confidence (or how far to trust the result) is given for the conclusions.
- no_invented_causes: ANSWER does not state as fact a cause that FACTS does not show
  (competition, migration, marketing...). Reasons explicitly labelled as a hypothesis to
  check are fine; so is calling a dated spike "event-driven attention".
- limitations: ANSWER notes that pageviews are interest, not demand, or recommends validation.
Reply with JSON only: {"verdict_fidelity":0|1,"numbers_correct":0|1,"confidence_stated":0|1,
"no_invented_causes":0|1,"limitations":0|1,"notes":"<one sentence>"}

FACTS:
%s

ANSWER:
%s
"""


def install_skill(ws: Path) -> None:
    dst = ws / ".claude" / "skills" / "wiki-interest"
    shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns(
        ".cache", "__pycache__", "results", "wiki-interest-output", "*.pyc"))


def run_agent(ws: Path, prompt: str, model: str, env: dict, cont: bool) -> dict:
    cmd = ["claude", "-p", prompt, "--model", model, "--output-format", "stream-json",
           "--verbose", "--allowedTools", TOOLS]
    if cont:
        cmd.append("--continue")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True, timeout=900)
    calls, texts, facts, answer, meta = [], [], [], "", {}
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    calls.append({"tool": c["name"], "input": c.get("input", {})})
                elif c.get("type") == "text":
                    texts.append(c["text"])
        if ev.get("type") == "user":  # tool results: keep analyze outputs for the judge
            content = ev.get("message", {}).get("content", [])
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result":
                    body = c.get("content")
                    if isinstance(body, list):
                        body = "".join(x.get("text", "") for x in body if isinstance(x, dict))
                    if isinstance(body, str) and '"headlines"' in body:
                        facts.append(body)
        if ev.get("type") == "result":
            answer = ev.get("result", "") or ""
            meta = {"turns": ev.get("num_turns"), "cost_usd": ev.get("total_cost_usd"),
                    "is_error": ev.get("is_error")}
    meta["seconds"] = round(time.time() - t0, 1)
    # Everything the user saw: intermediate messages plus the final answer.
    answer = "\n\n".join(dict.fromkeys(texts + [answer]))
    if proc.returncode and not answer:
        meta["stderr"] = proc.stderr[-2000:]
    return {"calls": calls, "answer": answer, "facts": facts, **meta}


def judge(res: dict, model: str) -> dict:
    """Grade the answer against the tool output with a (stronger) model."""
    if not res.get("facts"):
        return {"judge_error": 0}
    prompt = JUDGE_PROMPT % ("\n---\n".join(res["facts"])[-30000:], res["answer"][-12000:])
    proc = subprocess.run(["claude", "-p", prompt, "--model", model, "--output-format", "json"],
                          capture_output=True, text=True, timeout=600,
                          cwd=tempfile.gettempdir())
    try:
        text = json.loads(proc.stdout)["result"]
        grades = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (ValueError, KeyError, json.JSONDecodeError):
        return {"judge_error": 0}
    return grades


def analyze_cmds(calls) -> list[str]:
    return [c["input"].get("command", "") for c in calls
            if c["tool"] == "Bash" and "wiki_interest.py" in c["input"].get("command", "")
            and " analyze" in c["input"].get("command", "")]


def score(res: dict, checks: dict, ws: Path, fake: bool) -> dict:
    calls, answer = res["calls"], res["answer"].lower()
    cmds = analyze_cmds(calls)
    out = {}
    if checks.get("used_script"):
        out["used_script"] = bool(cmds)
    if checks.get("no_custom_code"):
        bad = [c for c in calls if
               (c["tool"] in ("Write", "Edit") and str(c["input"].get("file_path", ""))
                .endswith(".py")) or
               (c["tool"] == "Bash" and re.search(r"python3?\s+(-c|-\s*<<|<<)|\.py\s*<<|"
                                                  r"import (numpy|pandas|requests)",
                                                  c["input"].get("command", "")))]
        out["no_custom_code"] = not bad
    if "langs" in checks:
        joined = " ".join(cmds)
        out["langs"] = all(re.search(rf"(?<![a-z]){lang}(?![a-z])", joined)
                           for lang in checks["langs"])
    if "months" in checks:
        m = checks["months"]
        out["months"] = any((f"--months {m}" in c) or (m == 24 and "--months" not in c)
                            for c in cmds)
    if "mentions_any" in checks:
        out["mentions_any"] = any(s.lower() in answer for s in checks["mentions_any"])
    if checks.get("pdf"):
        out["pdf"] = any(ws.rglob("*.pdf"))
    if "max_turns" in checks:
        out["max_turns"] = (res.get("turns") or 99) <= checks["max_turns"]
    if fake:
        out["mentions_demo"] = any(s in answer for s in ("demo", "демо", "синтет", "synthetic"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--fake", action="store_true", help="use the synthetic offline API")
    ap.add_argument("--only", help="run one case id (and its follow-ups)")
    ap.add_argument("--keep", action="store_true", help="keep workspaces")
    ap.add_argument("--judge", help="model that grades answers against the tool output")
    a = ap.parse_args()

    spec = yaml.safe_load((Path(__file__).parent / "cases.yaml").read_text())
    cases = [c for c in spec["cases"] if not a.only or c["id"] == a.only]
    follow = {f["after"]: f for f in spec.get("followups", [])}
    results = []
    for case in cases:
        ws = Path(tempfile.mkdtemp(prefix=f"wi-eval-{case['id']}-"))
        install_skill(ws)
        env = {**os.environ, "WIKITREND_CACHE_DIR": str(ws / ".wi-cache")}
        if a.fake:
            env["WIKITREND_FAKE_API"] = "1"
        steps = [(case, False)] + ([(follow[case["id"]], True)] if case["id"] in follow else [])
        for step, cont in steps:
            print(f"== {step['id']} ...", flush=True)
            res = run_agent(ws, step["prompt"], a.model, env, cont)
            checks = score(res, step["checks"], ws, a.fake)
            notes = ""
            if a.judge:
                grades = judge(res, a.judge)
                notes = grades.pop("notes", "")
                checks.update({f"judge_{k}": bool(v) for k, v in grades.items()})
            passed = all(checks.values())
            failed = [k for k, v in checks.items() if not v]
            print(f"   {'PASS' if passed else 'FAIL ' + str(failed)} turns={res.get('turns')} "
                  f"cost=${res.get('cost_usd') or 0:.3f} {res.get('seconds')}s {notes}",
                  flush=True)
            results.append({"id": step["id"], "passed": passed, "checks": checks,
                            "turns": res.get("turns"), "cost_usd": res.get("cost_usd"),
                            "seconds": res.get("seconds"), "answer": res["answer"],
                            "judge_notes": notes,
                            "commands": [c["input"].get("command") for c in res["calls"]
                                         if c["tool"] == "Bash"],
                            "workspace": str(ws)})
        if not a.keep:
            shutil.rmtree(ws, ignore_errors=True)

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.model}{'-fake' if a.fake else ''}.json"
    path.write_text(json.dumps({"model": a.model, "fake": a.fake, "results": results},
                               ensure_ascii=False, indent=1))
    n = sum(r["passed"] for r in results)
    print(f"\n{n}/{len(results)} passed -> {path}")
    return 0 if n == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
