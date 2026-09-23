# Pitfalls when interpreting Wikipedia interest

1. **Wrong article.** A search can land on a film, a band or a disambiguation page. Always check
   `topics[].label/description`. Fix it with a `Q` id from `other_candidates` or `lang:Article`.
2. **News spike taken as a trend.** A celebrity diet, an eclipse or a death can multiply views
   for days. Trends ignore spikes. If `top_spikes` is large, say that attention was event-driven.
3. **Comparing raw views across languages.** en.wikipedia is ~100× cs.wikipedia. Use
   `per_million` for "where is the topic relatively more popular", and `daily_median_90d` for
   "where is the audience bigger".
4. **Seasonality.** Diets peak in January and astronomy around events. Short windows starting
   in a low season look like growth. Use ≥ 24 months; trust `yoy_pct` and `yoy_months_up`.
5. **Platform-wide decline.** Many editions are losing traffic. If `trend_pct_yr` < 0 but
   `trend_rel_pct_yr` ≥ 0, the topic holds its share and only the platform shrinks.
6. **Small numbers.** At 20 views/day, ±30% is noise. `confidence` will be low; say so.
7. **Missing article.** `missing_article` means no audience can be measured in that language.
   It may be a content gap (an opportunity) or low interest. You cannot tell which from pageviews.
8. **Renames and merges.** Redirects are counted. If an article was merged into another, the
   history may still jump. Check with `show` if a series looks broken.
9. **Wrong conclusion strength.** "Interest grows 30%/yr with high confidence" is a reason to
   investigate a market, not proof of demand. Recommend validation: surveys, ads tests,
   search volume.
