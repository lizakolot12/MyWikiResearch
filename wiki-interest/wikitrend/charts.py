"""Charts: absolute monthly views (log scale) and growth index, as two panels.

Two panels instead of a dual axis: absolute size and relative growth are
different measures, and languages differ in size by orders of magnitude.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

# Validated categorical palette (fixed order, never cycled); text in neutral inks.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
MAX_SERIES = len(PALETTE)

LABELS = {
    "uk": {"abs": "Переглядів/день (без сплесків, лог. шкала)",
           "idx": "Індекс зростання (перші 3 міс. = 100)"},
    "en": {"abs": "Views/day (spikes removed, log scale)",
           "idx": "Growth index (first 3 months = 100)"},
}


def _series_label(s: dict, multi_topic: bool) -> str:
    if s.get("topic") == "ALL":
        return f"{s['lang']} · Σ"
    return f"{s['lang']} · {s['topic']}" if multi_topic else s["lang"]


def plottable(run: dict) -> list[dict]:
    """Series to draw: per-language combined lines when several topics were analysed."""
    ok = [s for s in (run.get("combined") or run["series"]) if s.get("_monthly")]
    ok.sort(key=lambda s: -s.get("daily_median_90d", 0))
    return ok[:MAX_SERIES]


def draw(ax_abs, ax_idx, run: dict, ui: str = "uk") -> None:
    L = LABELS.get(ui, LABELS["en"])
    series = plottable(run)
    multi = len({s["qid"] for s in series}) > 1
    n_months = max((len(s["_monthly"]) for s in series), default=12)
    for i, s in enumerate(series):
        color = PALETTE[i]
        months = [date.fromisoformat(m + "-01") for m in s["_monthly"]]
        clean = [v[1] for v in s["_monthly"].values()]
        label = _series_label(s, multi)
        ax_abs.plot(months, clean, color=color, lw=2, label=label)
        if len(series) <= 3:  # raw series (with spikes) as a faint line
            ax_abs.plot(months, [v[0] for v in s["_monthly"].values()], color=color, lw=1,
                        alpha=0.35)
        base = sum(clean[:3]) / max(len(clean[:3]), 1)
        if base > 0:
            idx = [v / base * 100 for v in clean]
            ax_idx.plot(months, idx, color=color, lw=2, label=label)
    ax_abs.set_yscale("log")
    fmt = FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", " "))
    ax_abs.yaxis.set_major_formatter(fmt)
    ax_abs.yaxis.set_minor_formatter(fmt)
    ax_abs.tick_params(axis="y", which="minor", labelsize=6)
    ax_idx.axhline(100, color=INK2, lw=0.8, ls="--")
    for ax, title in ((ax_abs, L["abs"]), (ax_idx, L["idx"])):
        ax.set_title(title, fontsize=9, color=INK, loc="left")
        ax.grid(True, color=GRID, lw=0.6)
        ax.tick_params(labelsize=7, colors=INK2)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(GRID)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=max(1, n_months // 5)))
    if len(series) >= 2:  # one shared legend under both panels
        ax_abs.legend(fontsize=7, frameon=False, ncol=4, loc="upper left",
                      bbox_to_anchor=(0, -0.13), borderaxespad=0)


def save_chart(run: dict, path: Path, ui: str = "uk") -> Path:
    n = len(plottable(run))
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.4 + 0.2 * ((n + 3) // 4)))
    draw(a, b, run, ui)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
