"""Trend, spike, seasonality and confidence metrics for one pageview series.

Every number the agent reports should come from here, so that conclusions are
reproducible. See references/methodology.md for the reasoning behind each rule.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

# Thresholds (kept in one place so they can be tuned and documented).
SPIKE_MIN_RATIO = 2.0         # a spike day is at least 2x its local baseline...
SPIKE_MAD_K = 5.0             # ...and 5 robust SDs above it (log scale)
GROWTH_MIN_PCT = 10.0         # |trend| >= this per year (and significant): growing/declining
SLOW_MIN_PCT = 3.0            # significant but 3..10%/yr: slow_growth/slow_decline
P_SIGNIFICANT = 0.05
LOW_BASE = 30                 # median daily views below this: very small audience
SMALL_BASE = 150
SPIKE_SHARE_HIGH = 0.30
SEASON_STRENGTH = 0.3         # month-of-year explains >= 30% of detrended variance...
SEASON_AMPLITUDE = 1.25       # ...and peak month is >= 25% above the low month


def month_key(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def rolling_median(x: np.ndarray, w: int = 29) -> np.ndarray:
    h = w // 2
    if len(x) == 0:
        return x
    padded = np.pad(x, h, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, w)
    return np.median(windows, axis=1)


def detect_spikes(values: np.ndarray):
    """Return (spike_mask, cleaned_values, baseline) for daily views.

    Works on log1p scale so the rule is the same for 50 and 50 000 views/day.
    Spike days are replaced by their local 29-day median in the cleaned series.
    """
    lv = np.log1p(values.astype(float))
    base = rolling_median(lv)
    resid = lv - base
    mad = 1.4826 * np.median(np.abs(resid - np.median(resid))) if len(resid) else 0.0
    thresh = max(SPIKE_MAD_K * mad, math.log(SPIKE_MIN_RATIO))
    mask = (resid > thresh) & (values >= 10)
    baseline = np.expm1(base)
    cleaned = np.where(mask, baseline, values.astype(float))
    return mask, cleaned, baseline


def spike_events(days: list[date], values, mask, baseline, top: int = 3) -> list[dict]:
    events, i = [], 0
    while i < len(days):
        if not mask[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(days) and mask[j + 1]:
            j += 1
        seg = slice(i, j + 1)
        peak = int(np.argmax(values[seg])) + i
        events.append({
            "date": days[i].isoformat(), "days": j - i + 1, "peak_views": int(values[peak]),
            "x_baseline": round(float(values[peak] / max(baseline[peak], 1.0)), 1),
            "_excess": float(np.sum(values[seg] - baseline[seg])),
        })
        i = j + 1
    events.sort(key=lambda e: -e["_excess"])
    for e in events:
        del e["_excess"]
    return events[:top]


def mann_kendall(y: np.ndarray) -> tuple[float, float]:
    """Mann-Kendall trend test. Returns (tau, two-sided p-value)."""
    n = len(y)
    if n < 4:
        return 0.0, 1.0
    s = 0.0
    for i in range(n - 1):
        s += np.sum(np.sign(y[i + 1:] - y[i]))
    var = n * (n - 1) * (2 * n + 5) / 18.0
    z = 0.0 if s == 0 else (s - np.sign(s)) / math.sqrt(var)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    tau = s / (n * (n - 1) / 2)
    return float(tau), float(p)


def log_trend(y: np.ndarray) -> tuple[float, float, float]:
    """OLS on log(y). Returns (% change per year, CI95 low, CI95 high)."""
    n = len(y)
    x = np.arange(n, dtype=float)
    ly = np.log(np.maximum(y, max(float(np.median(y)) * 0.01, 1e-12)))
    xm = x - x.mean()
    slope = float(np.sum(xm * (ly - ly.mean())) / np.sum(xm ** 2))
    resid = ly - (ly.mean() + slope * xm)
    se = math.sqrt(float(np.sum(resid ** 2)) / max(n - 2, 1) / float(np.sum(xm ** 2)))
    pct = lambda s: (math.exp(12 * s) - 1) * 100  # noqa: E731
    return pct(slope), pct(slope - 1.96 * se), pct(slope + 1.96 * se)


def seasonal_trend(months: list[date], y: np.ndarray) -> tuple[float, float, float, float]:
    """Trend with month-of-year effects removed + Seasonal Mann-Kendall p-value.

    Returns (% per year, CI95 low, CI95 high, p). Used when seasonality is strong,
    where a plain trend test would confuse the seasonal swing with growth.
    """
    ly = np.log(np.maximum(y, max(float(np.median(y)) * 0.01, 1e-12)))
    t = np.arange(len(y), dtype=float)
    mons = sorted({m.month for m in months})
    X = np.column_stack([t] + [[1.0 if m.month == k else 0.0 for m in months] for k in mons])
    coef, *_ = np.linalg.lstsq(X, ly, rcond=None)
    resid = ly - X @ coef
    dof = max(len(y) - X.shape[1], 1)
    cov = np.linalg.pinv(X.T @ X) * float(np.sum(resid ** 2)) / dof
    slope, se = float(coef[0]), math.sqrt(max(float(cov[0, 0]), 0.0))
    s_tot, var_tot = 0.0, 0.0
    for k in mons:
        yk = np.array([v for m, v in zip(months, y) if m.month == k])
        n = len(yk)
        for i in range(n - 1):
            s_tot += float(np.sum(np.sign(yk[i + 1:] - yk[i])))
        var_tot += n * (n - 1) * (2 * n + 5) / 18.0
    z = 0.0 if s_tot == 0 or var_tot == 0 else (s_tot - np.sign(s_tot)) / math.sqrt(var_tot)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    pct = lambda b: (math.exp(12 * b) - 1) * 100  # noqa: E731
    return pct(slope), pct(slope - 1.96 * se), pct(slope + 1.96 * se), float(p)


def seasonality(months: list[date], y: np.ndarray) -> dict | None:
    """Month-of-year pattern on detrended log values; needs >= 24 months."""
    if len(y) < 24:
        return None
    ly = np.log(np.maximum(y, 1e-9))
    x = np.arange(len(y), dtype=float)
    coef = np.polyfit(x, ly, 1)
    resid = ly - np.polyval(coef, x)
    by_month = {}
    for m, r in zip(months, resid):
        by_month.setdefault(m.month, []).append(r)
    means = {k: float(np.mean(v)) for k, v in by_month.items()}
    fitted = np.array([means[m.month] for m in months])
    total = float(np.var(resid))
    strength = float(np.var(fitted) / total) if total > 0 else 0.0
    return {
        "strength": round(strength, 2),
        "peak_month": max(means, key=means.get),
        "low_month": min(means, key=means.get),
        "amplitude_x": round(math.exp(max(means.values()) - min(means.values())), 2),
    }


def _pct(a: float, b: float) -> float | None:
    return None if b <= 0 else (a / b - 1) * 100


def analyze_series(daily: dict[date, int], totals: dict[date, int],
                   window_start: date, window_end: date) -> dict:
    """Compute all metrics for one article.

    daily: views per day (may start before window_start to allow YoY).
    totals: total views of the language edition per month.
    window_*: analysis period; must be whole months.
    """
    if not daily or sum(daily.values()) == 0:
        return {"status": "no_data"}
    first_fetch = min(min(daily), window_start)
    days = [first_fetch + timedelta(days=i)
            for i in range((window_end - first_fetch).days + 1)]
    values = np.array([daily.get(d, 0) for d in days], dtype=float)
    first_seen = next(d for d, v in zip(days, values) if v > 0)

    mask, cleaned, baseline = detect_spikes(values)

    # Monthly aggregates (average views per day; clean = spikes removed).
    agg: dict[date, list] = {}
    for d, v, c in zip(days, values, cleaned):
        a = agg.setdefault(month_key(d), [0.0, 0.0, 0])
        a[0] += v
        a[1] += c
        a[2] += 1
    # Only whole months with the article in existence (skips the partial first month).
    usable = [m for m in sorted(agg) if m >= first_seen]
    raw_m = {m: agg[m][0] / agg[m][2] for m in usable}
    clean_m = {m: agg[m][1] / agg[m][2] for m in usable}

    win_months = [m for m in usable if window_start <= m <= window_end]
    out: dict = {"status": "ok", "months_analyzed": len(win_months)}
    if first_seen > window_start + timedelta(days=31):
        out["article_first_views"] = first_seen.isoformat()

    in_win = np.array([window_start <= d <= window_end for d in days])
    last90 = values[-90:]
    out["daily_median_90d"] = int(np.median(last90))
    win_total = float(values[in_win].sum())
    out["spike_share"] = round(float(np.sum((values - cleaned)[in_win & mask])) / win_total, 2) \
        if win_total > 0 else 0.0
    out["top_spikes"] = spike_events(
        [d for d, w in zip(days, in_win) if w], values[in_win], mask[in_win], baseline[in_win])

    # Share of the whole language edition (views per million), last 3 months.
    last3 = win_months[-3:]
    tot3 = sum(totals.get(m, 0) for m in last3)
    views3 = sum(clean_m[m] * agg[m][2] for m in last3)
    if tot3 > 0:
        out["per_million"] = round(views3 / tot3 * 1e6, 2)
        out["wiki_daily_total"] = int(tot3 / sum(agg[m][2] for m in last3))

    # Year over year: last 3 months vs the same months a year earlier.
    prev3 = [add_months(m, -12) for m in last3]
    if last3 and all(m in clean_m for m in prev3):
        out["yoy_pct"] = round(_pct(np.mean([clean_m[m] for m in last3]),
                                    np.mean([clean_m[m] for m in prev3])) or 0, 1)
    pairs = [(clean_m[m], clean_m[add_months(m, -12)]) for m in win_months
             if add_months(m, -12) in clean_m]
    if pairs:
        out["yoy_months_up"] = f"{sum(a > b for a, b in pairs)}/{len(pairs)}"

    # Trend over the analysis window (seasonally adjusted when seasonality is strong).
    y = np.array([clean_m[m] for m in win_months])
    if len(y) >= 6:
        s = seasonality(win_months, y)
        seasonal = bool(s and s["strength"] >= SEASON_STRENGTH
                        and s["amplitude_x"] >= SEASON_AMPLITUDE)
        if seasonal:
            out["seasonality"] = {k: s[k] for k in ("peak_month", "low_month", "amplitude_x",
                                                    "strength")}
            g, lo, hi, p = seasonal_trend(win_months, y)
            out["trend_method"] = "seasonally_adjusted"
        else:
            g, lo, hi = log_trend(y)
            p = mann_kendall(y)[1]
        out.update(trend_pct_yr=round(g, 1), trend_ci95=[round(lo, 1), round(hi, 1)],
                   mk_p=round(p, 3))
        share = np.array([clean_m[m] * agg[m][2] / totals[m] for m in win_months
                          if totals.get(m)])
        if len(share) == len(y):
            rel = seasonal_trend(win_months, share)[0] if seasonal else log_trend(share)[0]
            out["trend_rel_pct_yr"] = round(rel, 1)

    out = _plain(out)
    out["verdict"], out["confidence"], out["_reason_codes"] = judge(out)
    out["_monthly"] = {m.isoformat()[:7]: [round(raw_m[m], 1), round(clean_m[m], 1),
                                           totals.get(m, 0)] for m in win_months}
    return out


def _plain(o):
    """Convert numpy scalars to Python types so results serialize to JSON."""
    if isinstance(o, dict):
        return {k: _plain(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    return o


def judge(r: dict) -> tuple[str, str, list[list]]:
    """Turn metrics into a direction verdict, a high/medium/low confidence and reasons.

    Reasons are [code, params] pairs; see i18n.REASONS for their text.
    """
    reasons: list[list] = []
    score = 3
    g, p = r.get("trend_pct_yr"), r.get("mk_p", 1.0)
    if g is None:
        return "insufficient_data", "low", [["no_trend", {}]]

    if p < P_SIGNIFICANT and g >= GROWTH_MIN_PCT:
        verdict = "growing"
    elif p < P_SIGNIFICANT and g <= -GROWTH_MIN_PCT:
        verdict = "declining"
    elif p < P_SIGNIFICANT and g >= SLOW_MIN_PCT:
        verdict = "slow_growth"
    elif p < P_SIGNIFICANT and g <= -SLOW_MIN_PCT:
        verdict = "slow_decline"
    elif abs(g) < GROWTH_MIN_PCT:
        verdict = "stable"
    else:
        verdict = "unclear"
        reasons.append(["not_significant", {"g": g, "p": p}])
        score -= 1

    base = r.get("daily_median_90d", 0)
    if base < LOW_BASE:
        score -= 2
        reasons.append(["tiny_base", {"base": base}])
    elif base < SMALL_BASE:
        score -= 1
        reasons.append(["small_base", {"base": base}])

    if r.get("spike_share", 0) >= SPIKE_SHARE_HIGH:
        score -= 1
        reasons.append(["spiky", {"share": r["spike_share"]}])

    months = r.get("months_analyzed", 0)
    if months < 12:
        score -= 2
        reasons.append(["short", {"months": months}])
    elif months < 18:
        score -= 1
        reasons.append(["short", {"months": months}])
    if r.get("article_first_views"):
        reasons.append(["new_article", {"since": r["article_first_views"]}])

    rel = r.get("trend_rel_pct_yr")
    directional = ("growing", "declining", "slow_growth", "slow_decline")
    if rel is not None and verdict in directional and (rel > 0) != (g > 0) \
            and abs(rel) >= 5:
        score -= 1
        reasons.append(["rel_contradicts", {"rel": rel}])

    yoy = r.get("yoy_pct")
    if yoy is not None and verdict in directional and (yoy > 0) != (g > 0) \
            and abs(yoy) >= 5:
        score -= 1
        reasons.append(["yoy_contradicts", {"yoy": yoy}])

    if months < 24:
        reasons.append(["no_season_check", {}])
    elif r.get("seasonality"):
        reasons.append(["seasonal", {"peak": r["seasonality"]["peak_month"],
                                     "amp": r["seasonality"]["amplitude_x"]}])

    lo, hi = r.get("trend_ci95", [None, None])
    if verdict == "stable" and lo is not None and (lo < -25 or hi > 25):
        score -= 1
        reasons.append(["wide_ci", {"lo": lo, "hi": hi}])

    conf = "high" if score >= 3 else "medium" if score == 2 else "low"
    return verdict, conf, reasons
