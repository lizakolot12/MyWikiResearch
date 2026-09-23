"""Unit tests for the statistics: each rule is checked on a series with a known answer."""
from datetime import date, timedelta

import numpy as np

from wikitrend.metrics import (analyze_series, detect_spikes, log_trend, mann_kendall,
                               seasonal_trend)


def make_daily(start, end, level=1000, growth=0.0, season=0.0, noise=0.05, seed=1,
               spikes=()):
    rnd = np.random.default_rng(seed)
    out, d = {}, start
    while d <= end:
        yrs = (d - start).days / 365.25
        mu = level * (1 + growth) ** yrs
        mu *= 1 + season * np.cos(2 * np.pi * (d.timetuple().tm_yday - 15) / 365)
        out[d] = max(0, int(mu * (1 + rnd.normal(0, noise))))
        d += timedelta(days=1)
    for day, mult in spikes:
        out[day] = int(out[day] * mult)
    return out


def totals_for(start, end, per_month=3e8):
    m, out = start.replace(day=1), {}
    while m <= end:
        out[m] = int(per_month)
        m = (m + timedelta(days=32)).replace(day=1)
    return out


START, W0, W1 = date(2023, 6, 1), date(2024, 9, 1), date(2026, 8, 31)


def test_log_trend_recovers_known_growth():
    y = 100 * 1.3 ** (np.arange(24) / 12)
    g, lo, hi = log_trend(y)
    assert abs(g - 30) < 0.5 and lo <= g <= hi


def test_mann_kendall_detects_monotonic_and_ignores_noise():
    assert mann_kendall(np.arange(20.0))[1] < 0.001
    rnd = np.random.default_rng(0)
    assert mann_kendall(rnd.normal(size=24))[1] > 0.05


def test_spikes_detected_and_removed():
    vals = np.full(200, 1000.0)
    vals[100] = 20000
    vals[101] = 8000
    mask, clean, _ = detect_spikes(vals)
    assert mask[100] and mask[101] and mask.sum() == 2
    assert abs(clean[100] - 1000) < 1e-6


def test_small_daily_noise_is_not_a_spike():
    rnd = np.random.default_rng(3)
    vals = rnd.poisson(50, 400).astype(float)
    assert detect_spikes(vals)[0].sum() == 0


def test_growing_series_verdict_high_confidence():
    r = analyze_series(make_daily(START, W1, growth=0.4), totals_for(START, W1), W0, W1)
    assert r["verdict"] == "growing" and r["confidence"] == "high"
    assert 30 < r["trend_pct_yr"] < 50 and r["yoy_months_up"] == "24/24"


def test_flat_series_is_stable():
    r = analyze_series(make_daily(START, W1, growth=0.0), totals_for(START, W1), W0, W1)
    assert r["verdict"] == "stable"


def test_viral_spike_does_not_create_growth():
    spikes = [(date(2026, 6, 1) + timedelta(days=i), 30) for i in range(5)]
    r = analyze_series(make_daily(START, W1, spikes=spikes), totals_for(START, W1), W0, W1)
    assert r["verdict"] == "stable"
    assert r["top_spikes"][0]["date"] == "2026-06-01"
    assert r["spike_share"] > 0.1


def test_tiny_audience_gets_low_confidence():
    r = analyze_series(make_daily(START, W1, level=12, noise=0.3), totals_for(START, W1), W0, W1)
    assert r["confidence"] == "low"
    assert any(c == "tiny_base" for c, _ in r["_reason_codes"])


def test_seasonal_series_trend_is_seasonally_adjusted():
    # Strong January peak, no real growth; 24-month window starting in a low season.
    d = make_daily(START, W1, growth=0.0, season=0.7)
    r = analyze_series(d, totals_for(START, W1), W0, W1)
    assert r.get("trend_method") == "seasonally_adjusted"
    assert r["verdict"] == "stable"


def test_seasonal_trend_with_real_growth():
    months = [date(2024 + (8 + i) // 12, (8 + i) % 12 + 1, 1) for i in range(24)]
    y = np.array([100 * 1.25 ** (i / 12) * (2.0 if m.month == 1 else 1.0)
                  for i, m in enumerate(months)])
    g, lo, hi, p = seasonal_trend(months, y)
    assert abs(g - 25) < 1 and p < 0.01


def test_platform_decline_flagged_by_relative_trend():
    # Article views fall 20%/yr but the whole edition falls 35%/yr -> share grows.
    d = make_daily(START, W1, growth=-0.2)
    tot, m = {}, START
    while m <= W1:
        tot[m] = int(3e8 * 0.65 ** ((m - START).days / 365.25))
        m = (m + timedelta(days=32)).replace(day=1)
    r = analyze_series(d, tot, W0, W1)
    assert r["verdict"] == "declining" and r["trend_rel_pct_yr"] > 0
    assert any(c == "rel_contradicts" for c, _ in r["_reason_codes"])
    assert r["confidence"] != "high"


def test_new_article_uses_only_full_months():
    d = {k: v for k, v in make_daily(START, W1).items() if k >= date(2026, 2, 15)}
    r = analyze_series(d, totals_for(START, W1), W0, W1)
    assert r["months_analyzed"] == 6  # Mar..Aug 2026
    assert r["article_first_views"] == "2026-02-15"
    assert r["confidence"] == "low"


def test_no_data():
    assert analyze_series({}, {}, W0, W1)["status"] == "no_data"


def test_modest_consistent_growth_is_slow_growth():
    r = analyze_series(make_daily(START, W1, growth=0.06, noise=0.02), totals_for(START, W1),
                       W0, W1)
    assert r["verdict"] == "slow_growth"
