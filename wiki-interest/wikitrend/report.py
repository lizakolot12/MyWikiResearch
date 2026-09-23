"""One-page A4 PDF report built from a saved run plus the agent's own conclusions.

Numbers, chart, per-series caveats and methodology are generated from the run;
the agent supplies only the title, a short summary and recommendations, so the
report cannot drift from the data. Long text is truncated to keep one page.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .charts import GRID, INK, INK2, draw, plottable  # noqa: E402
from .metrics import reason_text  # noqa: E402

T = {
    "uk": {
        "subtitle": "Wikipedia · період {window} · мови: {langs} · перегляди людей (без ботів)",
        "all": "Σ усі теми разом", "more_rows": "…і ще {n} рядів (див. JSON-вивід analyze)", "summary": "Головне", "recs": "Рекомендації", "table": "Дані по мовах",
        "cols": ["Мова", "Стаття", "Перегл./день", "На млн", "Рік до року",
                 "Тренд/рік (95% ДІ)", "Висновок", "Довіра"],
        "verdict": {"growing": "зростає", "declining": "спадає", "stable": "стабільно",
                    "slow_growth": "повільно росте", "slow_decline": "повільно спадає",
                    "unclear": "неясно", "insufficient_data": "мало даних"},
        "status": {"missing_article": "немає статті", "no_data": "немає даних"},
        "conf": {"high": "висока", "medium": "середня", "low": "низька"},
        "caveats": "Застереження щодо окремих рядів",
        "method": "Методологія та обмеження",
        "method_lines": [
            "Джерело: Wikimedia Pageviews API (agent=user, {access}); перегляди редиректів "
            "{redirects}. Дані: {window}, повні місяці.",
            "Перегляди статті — це сигнал інтересу, а не платоспроможного попиту; "
            "використовуйте їх, щоб обрати напрям для подальшої перевірки.",
            "Сплески (день ≥ 2× від 29-денної медіани) прибрано з трендів; "
            "«Рік до року» — останні 3 міс. проти тих самих місяців рік тому.",
            "Тренд — регресія на лог-шкалі з тестом Манна–Кендалла (p < 0.05); «на млн» — "
            "частка від усіх переглядів мовного розділу, тож розділи різного розміру можна порівнювати.",
            "Довіра знижується через малу аудиторію, сплески, коротку історію, суперечність "
            "між трендом і змінами рік до року та через загальне падіння трафіку розділу.",
        ],
        "yes": "враховано", "no": "не враховано",
        "demo": "ДЕМО-ДАНІ: синтетичні ряди, не реальна Вікіпедія",
    },
    "en": {
        "subtitle": "Wikipedia · period {window} · languages: {langs} · human views (bots excluded)",
        "all": "Σ all topics", "more_rows": "…and {n} more rows (see analyze JSON output)", "summary": "Key findings", "recs": "Recommendations", "table": "Data by language",
        "cols": ["Lang", "Article", "Views/day", "Per mln", "YoY",
                 "Trend/yr (95% CI)", "Verdict", "Confidence"],
        "verdict": {"growing": "growing", "declining": "declining", "stable": "stable",
                    "slow_growth": "slow growth", "slow_decline": "slow decline",
                    "unclear": "unclear", "insufficient_data": "too little data"},
        "status": {"missing_article": "no article", "no_data": "no data"},
        "conf": {"high": "high", "medium": "medium", "low": "low"},
        "caveats": "Caveats per series",
        "method": "Methodology and limitations",
        "method_lines": [
            "Source: Wikimedia Pageviews API (agent=user, {access}); redirect views {redirects}. "
            "Data: {window}, whole months.",
            "Article views signal interest, not willingness to pay; use them to pick "
            "directions for further validation.",
            "Spikes (day >= 2x its 29-day median) are removed from trends; YoY compares the "
            "last 3 months with the same months a year earlier.",
            "Trend = log-scale regression with a Mann-Kendall test (p < 0.05); 'per mln' = "
            "share of all views of that language edition, comparable across edition sizes.",
            "Confidence is lowered by small audiences, spikes, short history, disagreement "
            "between trend and YoY, and by edition-wide traffic changes.",
        ],
        "yes": "included", "no": "not included",
        "demo": "DEMO DATA: synthetic series, not real Wikipedia",
    },
}
LINE = 0.0145          # figure-fraction height of one 8.5pt text line on A4
WRAP = 110             # characters per line at 8.5pt


def _fmt_pct(v):
    return "–" if v is None else f"{v:+.0f}%"


def _short(text: str, n: int = 24) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _row(s: dict, t: dict) -> list[str]:
    if s.get("status") != "ok":
        return [s["lang"], _short(s.get("article") or "–"), "–", "–", "–", "–",
                t["status"].get(s.get("status"), s.get("status", "")), "–"]
    ci = s.get("trend_ci95")
    trend = _fmt_pct(s.get("trend_pct_yr")) + (f" ({ci[0]:+.0f}..{ci[1]:+.0f})" if ci else "")
    name = t["all"] if s.get("topic") == "ALL" else _short(s["article"])
    return [s["lang"], name, f"{s['daily_median_90d']:,}".replace(",", " "),
            f"{s['per_million']:.1f}" if s.get("per_million") is not None else "–",
            _fmt_pct(s.get("yoy_pct")), trend, t["verdict"].get(s["verdict"], s["verdict"]),
            t["conf"][s["confidence"]]]


def _wrap(text: str, width: int = WRAP, max_lines: int = 99) -> list[str]:
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1] + "…"
    return lines


def build_pdf(run: dict, out: Path, title: str, summary: str = "",
              recommendations: list[str] | None = None, assumptions: list[str] | None = None,
              ui: str = "uk") -> Path:
    t = T.get(ui, T["en"])
    fig = plt.figure(figsize=(8.27, 11.69))
    y = 0.965

    def text(s, size=8.5, weight="normal", color=INK, x=0.06):
        nonlocal y
        fig.text(x, y, s, fontsize=size, weight=weight, color=color, va="top")
        y -= LINE * size / 8.5

    def heading(s):
        nonlocal y
        y -= 0.006
        text(s, 10.5, "bold")
        y -= 0.002

    text(title[:80], 15, "bold")
    y -= 0.004
    langs = ", ".join(dict.fromkeys(s["lang"] for s in run["series"]))
    text(t["subtitle"].format(window=run["window"], langs=langs), 8.5, color=INK2)
    if run.get("demo_data"):
        text(t["demo"], 9, "bold", color="#e34948")

    if summary:
        heading(t["summary"])
        for ln in _wrap(summary, max_lines=7):
            text(ln)
    if recommendations:
        heading(t["recs"])
        for rec in recommendations[:5]:
            for i, ln in enumerate(_wrap(rec, WRAP - 3, max_lines=2)):
                text(("• " if i == 0 else "  ") + ln)

    # Table
    heading(t["table"])
    all_rows = run.get("combined", []) + run["series"]
    rows = [_row(s, t) for s in all_rows[:14]]
    h = LINE * 1.25 * (len(rows) + 1)
    ax = fig.add_axes([0.06, y - h, 0.88, h])
    ax.axis("off")
    tbl = ax.table(cellText=rows, colLabels=t["cols"], loc="upper left", cellLoc="left",
                   colWidths=[0.06, 0.19, 0.12, 0.08, 0.11, 0.17, 0.15, 0.1])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    tbl.scale(1, 1.0)
    for (r, _c), cell in tbl.get_celld().items():
        cell.set_edgecolor(GRID)
        cell.set_linewidth(0.5)
        if r == 0:
            cell.set_text_props(weight="bold", color=INK)
            cell.set_facecolor("#f3f2ef")
    bbox = tbl.get_window_extent(fig.canvas.get_renderer()).transformed(
        fig.transFigure.inverted())
    y = bbox.y0 - 0.008
    if len(all_rows) > len(rows):
        text(t["more_rows"].format(n=len(all_rows) - len(rows)), 7.5, color=INK2)
    y -= 0.022

    # Chart (legend sits below the panels: reserve one line per 4 series)
    n = len(plottable(run))
    if n:
        ch = 0.22
        a1 = fig.add_axes([0.08, y - ch, 0.39, ch - 0.02])
        a2 = fig.add_axes([0.56, y - ch, 0.36, ch - 0.02])
        draw(a1, a2, run, ui)
        y -= ch + 0.03 + (0.012 * ((n + 3) // 4) if n >= 2 else 0)

    # Caveats per series, then methodology (auto-generated)
    caveats = []
    for s in run.get("combined", []) + run["series"]:
        texts = [reason_text(c, p, ui) for c, p in s.get("_reason_codes", [])
                 if c != "no_season_check"]
        if s.get("status") == "missing_article":
            texts = [t["status"]["missing_article"]]
        if texts:
            caveats.append(f"{s['id']}: " + "; ".join(texts))
    if caveats:
        heading(t["caveats"])
        for c in caveats[:6]:
            for i, ln in enumerate(_wrap(c, WRAP - 3, max_lines=2)):
                text(("• " if i == 0 else "  ") + ln, 8)
    heading(t["method"])
    lines = [ln.format(access=run["access"], window=run["window"],
                       redirects=t["yes"] if run.get("redirects_included") else t["no"])
             for ln in t["method_lines"]] + list(assumptions or [])[:3]
    for m in lines:
        for i, ln in enumerate(_wrap(m, WRAP - 3, max_lines=2)):
            if y < 0.03:
                break
            text(("• " if i == 0 else "  ") + ln, 7.5, color=INK2)

    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)
    return out
