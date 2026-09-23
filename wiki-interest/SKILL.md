---
name: wiki-interest
description: Measure and compare public interest in topics across Wikipedia language editions using Wikimedia pageview statistics — growth trends, trustworthiness of the trend, audience size — and produce charts and a one-page PDF report. Use when a user asks which topics/courses to build next, which languages/markets to launch or localize in, whether interest in a topic is growing, or wants a Wikipedia-interest report ("інтерес у Вікіпедії", "перегляди Вікіпедії", "which language audiences to explore").
---

# wiki-interest

Answers "is interest in X growing, where, and can we trust it?" from Wikipedia pageviews.
**All numbers come from `scripts/wiki_interest.py`: never compute metrics or write your own
code for the data.** Run commands from the user's folder (do not `cd` into the skill):
`python <skill_dir>/scripts/wiki_interest.py ...`. If a command prints `missing Python
package`, run `python <skill_dir>/install.py --deps-only` once.

## Workflow
1. **Topics and languages.** Topics: short English encyclopedic names ("Intermittent
   fasting", "English language"), a Wikidata id (`Q12345`) or an article (`uk:Астрономія`);
   several: `--topics "A; B"`. Languages: Wikipedia codes (uk, pl, cs, de...). Period:
   `--months 24` by default; keep ≥ 24 so seasonality is handled.
2. **Analyze:** `analyze --topics "Intermittent fasting" --langs pl,cs --months 24`
   (add `--ui-lang en` if the user does not write in Ukrainian). Check that
   `topics[].label/description` is what the user meant; if not, rerun with a better name, a
   `Q` id from `other_candidates` or `lang:Article`.
3. **Draft the answer** from `headlines` (see Rules). Include the `chart` path.
4. **PDF on request:** `report --title "..." --summary "..." --rec "..." --assumption "..."
   --out report.pdf`. It uses the last `analyze`; you write only the title, a 2–5 sentence
   summary with numbers, 1–4 recommendations and the user's criteria. If it returns
   `language_warnings`, fix those phrases and rerun with the same `--out`.
5. **Self-check, always last, for every answer:**
   ```bash
   python <skill_dir>/scripts/wiki_interest.py check-answer <<'EOF'
   <the full answer exactly as you will send it>
   EOF
   ```
   `"ok": true` → send. Otherwise fix everything in `missing`, `language_warnings` and
   `hints`, then send without checking again. Do not send progress notes before this.

## Rules
1. Quote `headlines` (one line per series, already in the user's language) and keep each
   `verdict`: `slow_growth` and `stable` are not "growing"; for `unclear` say there is no
   reliable trend. Differences inside overlapping `trend_ci95` ranges are "the same".
2. Give `confidence` and its `reasons` for every conclusion.
3. Data shows *when* (spike dates, peak months), never *why*. Label any cause
   "Hypothesis to check: …" («Гіпотеза для перевірки: …»).
4. Say that pageviews show interest, not demand, and suggest a validation step (survey,
   landing-page or ad test).
5. Compare languages by `per_million` and growth, not raw views. Size
   (`daily_median_90d`, `--rank-by size`) and growth (default ranking) are different
   criteria: show both unless the user chose one.
6. With several topics, conclude per language from `combined` (`xx:ALL(n topics)`) and
   mention `topics_agreement` when the topics disagree.
7. In Ukrainian: literary language with the terms from `answer_checklist`
   (`references/uk_style.md`), no Russian or English words inside sentences, article titles
   in «quotes», «Вікіпедія» in the text. Style:

> У польськомовній Вікіпедії інтерес до теми «Intermittent fasting» спадає: тренд −18% на рік, довіра до висновку висока.

## Fields you may cite
| field | meaning |
|---|---|
| `verdict`, `confidence`, `reasons` | growing / slow_growth / stable / slow_decline / declining / unclear; high / medium / low and why |
| `trend_pct_yr`, `trend_ci95` | % per year over the window and its 95% range |
| `yoy_pct`, `yoy_months_up` | last 3 months vs a year earlier; "11/12" months above last year |
| `daily_median_90d`, `per_million` | views per day now; share of the whole language edition |
| `top_spikes`, `seasonality` | one-off spikes (date, ×baseline); yearly peak month |
| `status: missing_article` | no article in that language (possibly a content gap) |
| `ranking.order` | languages sorted by `--rank-by` (growth, growth_rel, yoy, size, share) |

## Follow-ups (data is cached; only missing days are fetched)
Add a language: rerun `analyze` with it. Longer period: `--months 36`. Mobile only:
`--access mobile-web`. A year earlier: `--end 2025-08`. Monthly numbers to check a claim:
`show --series pl`.

## Errors
`{"error": ...}` with exit code 1. A network or HTTP error means the Wikimedia API is
unreachable: tell the user and do not invent numbers. How the metrics work and common traps:
`references/methodology.md` (read only if asked, or if a result looks odd).
