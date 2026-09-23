"""Self-check of the agent's draft answer before it is sent (`check-answer`).

Checks what cheap models most often get wrong in eval runs: language (see
lang_check.py) and the mandatory parts of an answer (confidence, the
interest-is-not-demand caveat, validation steps, demo-data notice, chart/PDF
path). Pattern checks only: they catch omissions, they do not grade reasoning.
"""
from __future__ import annotations

import re

from .lang_check import allowed_words, check_uk, is_ukrainian

# (key, required when, regex that satisfies it, what to add: uk, en)
REQUIRED = [
    ("confidence", lambda run: True,
     r"довір|confidence|trust",
     "довіру до висновку (висока/середня/низька) і її причини",
     "the confidence (high/medium/low) and its reasons"),
    ("caveat", lambda run: True,
     r"попит|готовн\w* платити|demand|willing|pay",
     "застереження: «Перегляди статей показують інтерес, а не готовність платити»",
     "the caveat: pageviews show interest, not demand or willingness to pay"),
    ("validation", lambda run: True,
     r"опитуван|тест|інтерв'ю|інтервʼю|перевір|survey|test|interview|validat",
     "наступний крок перевірки (опитування, тестова сторінка, рекламний тест)",
     "a validation step (survey, landing-page or ad test)"),
    ("demo", lambda run: bool(run and run.get("demo_data")),
     r"демо|синтет|demo|synthetic",
     "що це синтетичні демо-дані, а не справжня Вікіпедія",
     "that this is SYNTHETIC DEMO DATA, not real Wikipedia"),
    ("path", lambda run: bool(run and run.get("chart")),
     r"\.png|\.pdf",
     "шлях до графіка (поле chart) або PDF",
     "the chart path (field chart) or the PDF path"),
]
CAUSAL = re.compile(r"пов['ʼ]язан\w* з|спричин\w*|поясню\w*ся|через те, що|\bбо\b|"
                    r"because|due to|driven by|caused by|correlat\w*|корелю\w*", re.I)
HYPOTHESIS = re.compile(r"гіпотез|hypothes|можлив|possibl|perhaps|may be|might", re.I)


# Bare "growing/declining" words that overstate a slow or flat verdict.
UPGRADE = {
    "growing": re.compile(r"(?<!повільно )\b(зростає|зростають)\b|(?<!slow )(?<!slowly )"
                          r"\bgrowing\b", re.I),
    "declining": re.compile(r"(?<!повільно )\b(спадає|спадають)\b|(?<!slow )(?<!slowly )"
                            r"\bdeclining\b", re.I),
}


def verdict_upgrades(text: str, run: dict | None) -> list[str]:
    """Flag «зростає»/"growing" when no series in the run has that verdict."""
    if not run:
        return []
    verdicts = {s.get("verdict") for s in run.get("combined", []) + run["series"]}
    return [f"«{m.group(0)}»: no series has verdict {v}; use the verdict words from "
            f"headlines («повільно зростає», «стабільний», ...)"
            for v, rx in UPGRADE.items() if v not in verdicts
            for m in [rx.search(text)] if m]


def run_words(run: dict | None) -> set[str]:
    """Article titles, topic names and ids of a run: fine to quote in Latin script."""
    if not run:
        return set()
    return allowed_words(*(f"{s.get('article') or ''} {s.get('topic') or ''} {s.get('id')}"
                           for s in run.get("combined", []) + run["series"]),
                         *(t.get("label") or "" for t in run["topics"]))


def check_answer(text: str, run: dict | None = None) -> dict:
    uk = is_ukrainian(text)
    missing = [(m_uk if uk else m_en) for key, when, rx, m_uk, m_en in REQUIRED
               if when(run) and not re.search(rx, text, re.I)]
    hints = []
    if CAUSAL.search(text) and not HYPOTHESIS.search(text):
        hints.append("you seem to name a cause: the data shows WHEN, not WHY; label it "
                     + ("«Гіпотеза для перевірки: …»" if uk else "'Hypothesis to check: …'"))
    hints += verdict_upgrades(text, run)
    language = check_uk(text, run_words(run))
    ok = not (missing or language or hints)
    out = {"ok": ok}
    if missing:
        out["missing"] = missing
    if language:
        out["language_warnings"] = language
    if hints:
        out["hints"] = hints
    out["tell_agent"] = (
        "Send the answer as is." if ok else
        "Fix every item above in your answer, then send the corrected answer to the user. "
        "Do not run check-answer again.")
    return out
