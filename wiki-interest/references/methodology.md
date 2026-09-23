# Methodology

Read this when the user asks how a number was produced, or a result looks odd.
Implementation: `wikitrend/metrics.py` (all thresholds are constants at the top of the file).

## Data
- **Source:** Wikimedia REST Pageviews API, `agent=user`. Traffic that Wikimedia classifies as
  bots or spiders is excluded. Data starts in July 2015.
- **Article views:** daily views of the article **plus its redirects**. Redirects include old
  titles after a rename, so a rename does not show up as a crash. At most 20 redirects are
  counted; if the cap is hit, a reason says so.
- **Edition totals:** monthly user views of the whole language edition (e.g. all of pl.wikipedia).
- **Topic ↔ article:** a Wikidata item links the same concept across languages. The titles
  differ ("Astronomy", "Астрономія", "Astronomia"), but the concept is the same.
- **Window:** whole calendar months ending with the last complete month (`--end` to move it).
  At least 15 months are always fetched so that year-over-year is available.

## Spikes
Everything is computed on the log1p scale. A day is a spike if its views are ≥ 2× the 29-day
rolling median **and** more than 5 robust SDs (MAD × 1.4826) above it. Spike days are replaced
by the rolling median in the "clean" series. All trends use the clean series.
- `spike_share`: the share of views in the window that were spike excess.
- `top_spikes`: up to 3 largest events (start date, length, peak, multiple of baseline).

## Levels
- `daily_median_90d`: median daily views over the last 90 days (raw). This is audience size.
- `per_million`: clean article views ÷ edition views × 10⁶, last 3 months. It makes editions
  of different size comparable.
- `wiki_daily_total`: views per day of the whole edition, for context.

## Growth
- `yoy_pct`: mean clean daily views in the last 3 months vs the same 3 months a year earlier.
  Comparing the same months is immune to seasonality.
- `yoy_months_up`: for every month in the window with data a year earlier, is it higher?
  "12/12" is a consistent rise; "6/12" is noise.
- `trend_pct_yr`: OLS slope of log(monthly clean average), converted to %/year, with a 95%
  interval (`trend_ci95`). Significance comes from the Mann–Kendall test (`mk_p`), which is
  non-parametric and robust to outliers.
- **Seasonality:** with ≥ 24 months, month-of-year effects are fitted on detrended values.
  If they explain ≥ 30% of the variance and peak/low ≥ 1.25×, the series is seasonal. Then
  the trend comes from a regression with month dummies (`trend_method: seasonally_adjusted`),
  and significance comes from the **Seasonal** Mann–Kendall test, which compares January only
  with January, and so on.
- `trend_rel_pct_yr`: the same trend on `per_million`. If it disagrees with `trend_pct_yr`, the
  change comes from the edition's overall traffic (e.g. Wikipedia-wide decline), not from the topic.

## Verdict
| verdict | rule |
|---|---|
| growing | trend ≥ +10%/yr and p < 0.05 |
| declining | trend ≤ −10%/yr and p < 0.05 |
| slow_growth / slow_decline | abs(trend) is 3–10%/yr and p < 0.05 (consistent but modest) |
| stable | abs(trend) < 10%/yr, not significant (or < 3%/yr) |
| unclear | abs(trend) ≥ 10%/yr but p ≥ 0.05 |
| insufficient_data | < 6 months |

## Confidence (start at 3 points; high = 3, medium = 2, low ≤ 1)
| condition | points |
|---|---|
| verdict unclear | −1 |
| median views < 30/day | −2 |
| median views < 150/day | −1 |
| spike share ≥ 30% | −1 |
| < 12 months analysed | −2 |
| < 18 months analysed | −1 |
| relative trend has the opposite sign (growing/declining only) | −1 |
| YoY has the opposite sign (growing/declining only) | −1 |
| stable, but 95% interval goes beyond ±25%/yr | −1 |

Every deduction adds a human-readable entry to `reasons`.

## Known limitations
- Views measure attention, not purchase intent. Students, journalists and bots that were not
  classified as bots all count.
- Mobile apps and search-engine answer boxes (and AI summaries) move traffic away from
  Wikipedia over time. This is why the relative trend is reported.
- One article is a narrow proxy for a topic. Pass several related articles as separate topics
  (e.g. "Intermittent fasting; Fasting; Ketogenic diet") and check that they agree.
- Speakers of a language may read another edition (many Czech readers use en.wikipedia).
  Per-language views are a lower bound of the interest of that audience.
