---
name: wiki-interest
description: Measure and compare public interest in topics across Wikipedia language editions using Wikimedia pageview statistics — growth trends, trustworthiness of the trend, audience size — and produce charts and a one-page PDF report. Use when a user asks which topics/courses to build next, which languages/markets to launch or localize in, whether interest in a topic is growing, or wants a Wikipedia-interest report ("інтерес у Вікіпедії", "перегляди Вікіпедії", "which language audiences to explore").
---

# wiki-interest

Answers "is interest in X growing, where, and can we trust it?" from Wikipedia pageviews.
All numbers come from `scripts/wiki_interest.py`. **Never compute metrics yourself and never
write your own code for the data work. Run the script and interpret its JSON.**

## Hard rules (check your answer against them before sending)
1. Use each series' `verdict` as is. `headlines` gives one ready-made line per series in the
   user's language: quote it, do not re-translate it. Do not upgrade it: `slow_growth`
   («повільно зростає») is not "growing", and `stable` («стабільний») is not "growing".
2. Give `confidence` with its main `reasons` for every series you conclude on.
3. Causes: the data shows *when* (a spike date, a peak month), never *why*. State facts
   ("spike on 2025-03-03, 37× baseline"). If you add a possible reason, label it explicitly
   as "Hypothesis to check: …". Never state a reason as fact.
4. Differences inside overlapping `trend_ci95` ranges are "about the same".
5. Pageviews show interest, not demand. Recommend next validation steps.
6. When you make a chart or PDF, give its path in the answer.
7. Answer in the user's language. In Ukrainian write literary Ukrainian: reuse the wording
   of `headlines`/`reasons`, use the terms listed in `answer_checklist` (full list:
   `references/uk_style.md`), no Russian words, no English words inside sentences
   (quote article titles: «Intermittent fasting»). This covers every message, including
   progress notes: «Вікіпедія» not "Wikipedia", «навичка» not "skill", heading «Головні
   висновки» not «Ключові знахідки».
8. **Never send an answer without `check-answer`** (workflow step 5), for every answer,
   follow-ups included. Do not write progress notes to the user ("Запускаю аналіз…"): the
   user should see only the checked answer.

## Setup (once)
```bash
python <skill_dir>/install.py --deps-only        # makes <skill_dir>/.venv with numpy, matplotlib
```
Only if a command prints `"error": "missing Python package"`. The script then uses `.venv` by itself.
`<skill_dir>` is this skill's folder. Run every command from the user's working directory
(do not `cd` into the skill), as `python <skill_dir>/scripts/wiki_interest.py ...`, so
charts and PDFs land next to the user.

## Workflow
1. **Translate the request into topics + languages.**
   - Topics: short encyclopedic names in English work best ("Intermittent fasting",
     "Astronomy", "English language"). A topic can also be a Wikidata id (`Q12345`) or an
     exact article (`uk:Астрономія`). Several topics: `--topics "A; B"`.
   - Languages: Wikipedia codes (uk, pl, cs, de, en, es, pt, ...). Map "польськомовна" → pl,
     "чеська" → cs, etc.
   - Period: "за останні 2 роки" → `--months 24` (default 24; use ≥ 24 whenever possible so
     seasonality can be handled).
2. **Run `analyze`** (it resolves topics itself):
   ```bash
   python <skill_dir>/scripts/wiki_interest.py analyze --topics "Intermittent fasting" --langs pl,cs --months 24
   ```
   `--ui-lang uk` (default) writes `headlines`, `reasons` and chart labels in Ukrainian;
   use `--ui-lang en` when the user writes in any other language.
   Check `topics[].label/description` is the thing the user meant. If it is wrong (e.g. a
   film with the same name), rerun with a better name, a `Q` id from `other_candidates`, or
   `lang:Article`.
3. **Interpret** (see the next section) and draft the answer. Include the chart path from
   `chart`.
4. **Report on request** (or when the user wants something to share):
   ```bash
   python <skill_dir>/scripts/wiki_interest.py report --title "..." --summary "..." --rec "..." --rec "..." --assumption "..." --out report.pdf
   ```
   It uses the **last analyze run**: table, chart, caveats and methodology are filled in
   automatically. You only write the title, a 2–5 sentence summary with numbers, 1–4
   recommendations and the user's own criteria/assumptions (`--assumption`). Write them in
   the user's language; `--ui-lang uk|en` sets the labels. If the output has
   `language_warnings`, fix those phrases and rerun `report` with the same `--out`.
5. **Self-check (mandatory, last step).** Put your full draft answer into `check-answer`:
   ```bash
   python <skill_dir>/scripts/wiki_interest.py check-answer <<'EOF'
   <the full answer exactly as you will send it>
   EOF
   ```
   It checks the answer against the last run: language, confidence, the
   interest-is-not-demand caveat, a validation step, chart/PDF path,
   causes stated as facts. `"ok": true` → send the answer. Otherwise fix every item in
   `missing`, `language_warnings` and `hints`, then send the corrected answer (do not run
   the check a second time).

Example of the answer style in Ukrainian (numbers come from `headlines`):
> У польськомовній Вікіпедії інтерес до теми «Intermittent fasting» спадає: тренд −18% на
> рік (95% ДІ: від −20 до −17), вище, ніж рік тому, 0 з 12 місяців. Довіра до висновку
> висока. У чеськомовній спад такий самий (−19%): різниця перебуває в межах довірчих
> інтервалів. Перегляди статей показують інтерес, а не готовність платити, тому наступний
> крок — опитування або рекламний тест.

## Reading the JSON
Start from `headlines` (one line per series). With several topics, `combined` has one series per
language, summing all topic articles: `xx:ALL(n topics)`. Base the per-language conclusion on
it, and mention `topics_agreement` when the topics disagree. `ranking` ranks these combined series.

Fields of each series (one topic in one language, or combined):
| field | meaning |
|---|---|
| `daily_median_90d` | typical human views per day now = audience size |
| `per_million` | views per million views of that language edition (compare across languages) |
| `yoy_pct` | last 3 months vs same 3 months a year ago (spikes removed) |
| `yoy_months_up` | "11/12" = 11 of 12 months higher than a year earlier (consistency) |
| `trend_pct_yr`, `trend_ci95` | growth per year over the window and its 95% range |
| `trend_rel_pct_yr` | same, relative to all traffic of that edition |
| `mk_p` | p-value of the trend test; < 0.05 means the trend is not noise |
| `spike_share`, `top_spikes` | share of views from one-off spikes (news, virality), removed from trends |
| `seasonality` | strong yearly pattern; trend is then seasonally adjusted |
| `verdict` | growing / slow_growth / stable / slow_decline / declining / unclear / insufficient_data |
| `confidence` + `reasons` | high / medium / low and **why** |
| `status: missing_article` | no article in that language: a signal in itself (content gap) |
| `ranking.order` | series sorted by `--rank-by` (growth, growth_rel, yoy, size, share) |

## More guidance for conclusions
- For `unclear`, say the data does not show a reliable trend.
- Compare languages by `per_million` and growth, not by raw views (editions differ ×100 in size).
- Growth and size are different criteria. If the user did not say which matters, show both: `--rank-by growth` is the default, `--rank-by size` for audience size.
- A high `spike_share` or a big item in `top_spikes` means news-driven attention. Mention the date.
- Example for rule 4: −19.2% vs −19.3% is the same trend, not "faster".
- Several articles for one idea (e.g. "English language; English as a second or foreign
  language") make the answer more robust. Say whether they agree.
- If you are unsure about a number, check the monthly data with `show --series pl`.

## Follow-ups (cheap: data is cached)
- "add Slovak": rerun `analyze` with the extra language. Cached series are not re-downloaded.
- "3 years instead": `--months 36`. Only the missing months are fetched.
- "only mobile": `--access mobile-web` (or `mobile-app`, `desktop`).
- "what about a year ago": `--end 2025-08` (backtest: would we have trusted this then?).
- "rank by audience size": `--rank-by size`.
- Monthly numbers of the last run: `show [--series pl]`. Older runs: `--run <run_id>`.

## Errors
`{"error": ...}` on stdout, exit code 1. A network/HTTP error means the Wikimedia API is
unreachable: tell the user, don't invent numbers. "no Wikidata item": try the English name
or `lang:Article`.

More detail: `references/methodology.md` (how each metric works) and
`references/pitfalls.md` (traps when interpreting). Read them only if the user asks how
conclusions were reached or a result looks odd.
