"""All user-facing wording in one place: reasons, verdicts, headlines, answer checklist.

The agent quotes these strings instead of translating them itself: a cheap model
translating on the fly is the main source of calques and Russianisms in Ukrainian
answers. Ukrainian terms here must match references/uk_style.md and the banned
forms in lang_check.py.
"""
from __future__ import annotations

import re

REASONS = {
    "en": {
        "no_trend": "fewer than 6 months of data",
        "not_significant": "trend {g:+.0f}%/yr is not statistically significant (p={p:.2f})",
        "tiny_base": "very small audience ({base} views/day): noise dominates",
        "small_base": "small audience ({base} views/day)",
        "spiky": "{share:.0%} of views came from one-off spikes (news/virality)",
        "short": "only {months} months analysed",
        "new_article": "article has views only since {since}",
        "rel_contradicts": "relative to the whole edition's traffic the trend is {rel:+.0f}%/yr: "
                           "the change mostly reflects overall traffic of this Wikipedia",
        "yoy_contradicts": "latest year-over-year change ({yoy:+.0f}%) contradicts the trend",
        "no_season_check": "< 24 months: seasonality not checked",
        "seasonal": "strong seasonality (peak in {peak}, x{amp} vs low month); "
                    "trend is seasonally adjusted",
        "wide_ci": "wide uncertainty ({lo:+.0f}%..{hi:+.0f}%/yr)",
        "redirects_capped": "only {used} of {total} redirects counted",
        "topics_disagree": "topics move in different directions ({up} up, {down} down, "
                           "{flat} flat/unclear of {n})",
    },
    "uk": {
        "no_trend": "даних менше ніж за 6 місяців",
        "not_significant": "тренд {g:+.0f}%/рік статистично не значущий (p = {p:.2f})",
        "tiny_base": "дуже мала аудиторія (переглядів за день: {base}): випадкові коливання "
                     "переважають",
        "small_base": "мала аудиторія (переглядів за день: {base})",
        "spiky": "{share:.0%} переглядів припадає на разові сплески (новини, віральність)",
        "short": "проаналізовано лише {months} міс.",
        "new_article": "стаття має перегляди лише від {since}",
        "rel_contradicts": "відносно всього трафіку мовного розділу тренд становить "
                           "{rel:+.0f}%/рік: зміна здебільшого повторює динаміку всієї "
                           "цієї Вікіпедії",
        "yoy_contradicts": "остання зміна рік до року ({yoy:+.0f}%) суперечить тренду",
        "no_season_check": "даних менше ніж за 24 міс.: сезонність не перевірено",
        "seasonal": "виразна сезонність (пік — {peak}, у {amp} раза більше, ніж у "
                    "найслабший місяць); тренд скориговано з урахуванням сезонності",
        "wide_ci": "широкий інтервал невизначеності: від {lo:+.0f} до {hi:+.0f}%/рік",
        "redirects_capped": "враховано лише {used} з {total} перенаправлень",
        "topics_disagree": "теми змінюються в різних напрямках (зростання: {up}, спад: {down}, "
                           "без чіткого тренду: {flat}; усього тем: {n})",
    },
}

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "uk": ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень", "серпень",
           "вересень", "жовтень", "листопад", "грудень"],
}

# Short labels (PDF table) and full predicates for headlines ("interest IS GROWING").
VERDICT = {
    "en": {"growing": "growing", "declining": "declining", "stable": "stable",
           "slow_growth": "slow growth", "slow_decline": "slow decline",
           "unclear": "unclear", "insufficient_data": "too little data"},
    "uk": {"growing": "зростає", "declining": "спадає", "stable": "стабільний",
           "slow_growth": "повільно зростає", "slow_decline": "повільно спадає",
           "unclear": "тренд неясний", "insufficient_data": "замало даних"},
}
HEADLINE_VERDICT = {
    "uk": {"growing": "інтерес ЗРОСТАЄ", "declining": "інтерес СПАДАЄ",
           "stable": "інтерес СТАБІЛЬНИЙ", "slow_growth": "інтерес ПОВІЛЬНО ЗРОСТАЄ",
           "slow_decline": "інтерес ПОВІЛЬНО СПАДАЄ",
           "unclear": "надійного тренду НЕМАЄ", "insufficient_data": "ЗАМАЛО ДАНИХ"},
}
CONF = {
    "en": {"high": "high", "medium": "medium", "low": "low"},
    "uk": {"high": "висока", "medium": "середня", "low": "низька"},
}

# Ukrainian terms the agent must use: (use this, instead of). Mirrors references/uk_style.md.
GLOSSARY_UK = [
    ("мовний розділ Вікіпедії", "видання, редакція"),
    ("рік до року", "року на року, рік на рік"),
    ("довіра до висновку", "впевненість"),
    ("сплеск", "спайк, викид"),
    ("сезонність", "сезонна модель"),
    ("у межах", "знаходиться в межах"),
    ("за мовами, щодо теми", "по мовах, по темі"),
    ("у 2,1 раза / у 2 рази / у 5 разів", "в 2,1 рази"),
    ("протягом", "на протязі"),
    ("становить", "складає (про числа)"),
    ("головні висновки", "ключові знахідки"),
    ("з тих самих причин, такий самий", "за тих же причин, такий же"),
    ("Вікіпедія (у тексті)", "Wikipedia посеред речення"),
]

TEXT = {
    "en": {
        "no_article": "{id}: NO ARTICLE in this language (nothing to measure)",
        "no_data": "{id}: no data",
        "trend": "trend {g:+.0f}%/yr (95% {lo:+.0f}..{hi:+.0f})",
        "yoy_up": "{m} months above last year",
        "views": "{v} views/day",
        "per_million": "{pm:.0f} per million",
        "confidence": "confidence {c}",
        "agreement": "{up} up, {down} down, {flat} flat/unclear of {n} topics",
        "demo": "SYNTHETIC DEMO DATA (not real Wikipedia): tell the user.",
    },
    "uk": {
        "no_article": "{id}: СТАТТІ НЕМАЄ в цьому мовному розділі (виміряти інтерес "
                      "неможливо; це може бути прогалина в контенті)",
        "no_data": "{id}: даних немає",
        "trend": "тренд {g:+.0f}%/рік (95% ДІ: від {lo:+.0f} до {hi:+.0f})",
        "yoy_up": "місяців вище, ніж рік тому: {m}",
        "views": "переглядів за день: {v}",
        "per_million": "{pm:.0f} на мільйон переглядів розділу",
        "confidence": "довіра до висновку {c}",
        "agreement": "зростання: {up}, спад: {down}, без чіткого тренду: {flat}; "
                     "усього тем: {n}",
        "demo": "СИНТЕТИЧНІ ДЕМО-ДАНІ (не справжня Вікіпедія): обов'язково скажи про це "
                "користувачеві.",
    },
}

CHECKLIST = {
    "en": [
        "use the verdict words from headlines; never upgrade slow_growth/stable to 'growing'",
        "give confidence and its reasons",
        "the data shows WHEN (spike dates, peak months), not WHY: any reason must be labelled "
        "'Hypothesis to check: ...'",
        "say that pageviews measure interest, not demand, and suggest how to validate "
        "(survey, landing-page or ad test)",
    ],
    "uk": [
        "quote the verdict words from headlines as is; «повільно зростає» and «стабільний» "
        "are NOT «зростає»",
        "give «довіра до висновку» (висока/середня/низька) and its reasons",
        "the data shows WHEN (spike dates, peak months), not WHY: label any reason "
        "«Гіпотеза для перевірки: …»",
        "say «Перегляди статей показують інтерес, а не готовність платити» and suggest "
        "validation (опитування, тестова сторінка, рекламний тест)",
        "write literary Ukrainian, no Russian words, no English words inside sentences. "
        "Terms: " + "; ".join(f"{a} (не «{b}»)" for a, b in GLOSSARY_UK),
    ],
}
SELF_CHECK = ("LAST STEP, mandatory: pass your full draft answer to `check-answer` "
              "(heredoc, see SKILL.md), fix what it reports, then send")
for _items in CHECKLIST.values():
    _items.append(SELF_CHECK)
DEMO_CHECK = {"en": "say the data is SYNTHETIC DEMO DATA",
              "uk": "say the data is synthetic: «це синтетичні демо-дані»"}


def lang_or_en(lang: str) -> str:
    return lang if lang in REASONS else "en"


def uk_numbers(text: str) -> str:
    """Ukrainian number style: decimal comma (0,05), space as thousands separator."""
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", " ", text)
    return re.sub(r"(?<=\d)\.(?=\d)", ",", text)


def reason_text(code: str, params: dict, lang: str = "en") -> str:
    lang = lang_or_en(lang)
    if code == "seasonal":
        params = {**params, "peak": MONTHS[lang][params["peak"] - 1]}
    text = REASONS[lang][code].format(**params)
    return uk_numbers(text) if lang == "uk" else text


def headline(s: dict, lang: str = "en") -> str:
    """One-line conclusion per series, phrased so it can be quoted as is."""
    lang = lang_or_en(lang)
    t = TEXT[lang]
    if s.get("status") == "missing_article":
        return t["no_article"].format(id=s["id"])
    if s.get("status") != "ok":
        return t["no_data"].format(id=s["id"])
    verdict = (HEADLINE_VERDICT[lang][s["verdict"]] if lang in HEADLINE_VERDICT
               else s["verdict"].upper())
    parts = [verdict]
    if s.get("trend_pct_yr") is not None:
        lo, hi = s["trend_ci95"]
        parts.append(t["trend"].format(g=s["trend_pct_yr"], lo=lo, hi=hi))
    if s.get("yoy_months_up"):
        parts.append(t["yoy_up"].format(m=s["yoy_months_up"].replace("/", " з ")
                                        if lang == "uk" else s["yoy_months_up"]))
    parts.append(t["views"].format(v=f"{s['daily_median_90d']:,}"))
    if s.get("per_million") is not None:
        parts.append(t["per_million"].format(pm=s["per_million"]))
    conf = CONF[lang][s["confidence"]].upper()
    body = ", ".join(parts) + "; " + t["confidence"].format(c=conf)
    if lang == "uk":  # numbers only: the id may contain an article title like "Web 2.0"
        body = uk_numbers(body)
    reasons = [reason_text(c, p, lang) for c, p in s.get("_reason_codes", [])]
    if reasons:
        body += " (" + "; ".join(reasons) + ")"
    return f"{s['id']}: {body}"
