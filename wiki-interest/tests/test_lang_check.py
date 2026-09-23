"""Ukrainian language check: catches the calques seen in real Haiku answers."""
from pathlib import Path

from wikitrend.i18n import CHECKLIST, REASONS, TEXT, headline, reason_text
from wikitrend.lang_check import check_uk

ROOT = Path(__file__).resolve().parent.parent

# Sentences from an eval answer of Claude Haiku 4.5 (before the language fixes).
BAD = ("| Року на року (останні 3 місяці) | -18,2% | -19,2% |\n"
       "Різниця між -18,3% та -19,2% знаходиться в межах перекриття довірчих інтервалів. "
       "Обидва видання мають пік у січні (в 2,1 рази вищий за липень), просто stediy спад. "
       "Впевненість висока завдяки сильній сезонній моделі.")


def test_catches_known_calques():
    text = " ".join(check_uk(BAD))
    for word in ("Року на року", "знаходиться", "видання", "2,1 рази", "stediy",
                 "Впевненість", "сезонній моделі"):
        assert word in text, word


def test_second_round_calques():
    """Found in the first Haiku run after the fix: keep them from coming back."""
    text = ("Довіра до висновку теж висока за тих же причин. Переглядачі показують інтерес. "
            "Відносно до загального трафіку розділу інтерес вищий у польській Wikipedia.")
    found = " ".join(check_uk(text))
    for word in ("тих же", "Переглядачі", "Відносно до", "Wikipedia"):
        assert word in found, word


def test_russian_words_and_letters():
    assert check_uk("Інтерес зростає, что видно з даних за останні два роки у Вікіпедії.")
    assert check_uk("Інтерес зростає и це видно з даних за останні два роки у Вікіпедії.")
    assert check_uk("Інтерес зростає, ёлка це видно з даних за останні два роки у Вікіпедії.")


def test_clean_text_passes():
    good = ("У польськомовній Вікіпедії інтерес до теми «Intermittent fasting» спадає: тренд "
            "−18% на рік, рік до року −18,2%. Довіра до висновку висока. Різниця між "
            "розділами перебуває в межах довірчих інтервалів; пік у 2,1 раза вищий. "
            "Файл: /tmp/x/chart-1.png, команда `analyze --langs pl`.")
    assert check_uk(good) == []


def test_article_titles_allowed_when_listed():
    text = "Інтерес до статті Astronomy у чеськомовній Вікіпедії зростає вже другий рік."
    assert check_uk(text)
    assert check_uk(text, {"astronomy"}) == []


def test_english_text_is_not_checked():
    assert check_uk("Interest is growing in the Czech edition, year over year.") == []


def test_generated_ukrainian_is_clean():
    """Everything the code itself writes in Ukrainian must pass its own check."""
    s = {"id": "pl:Intermittent fasting", "status": "ok", "verdict": "slow_growth",
         "trend_pct_yr": 4.2, "trend_ci95": [1.5, 6.9], "yoy_months_up": "10/12",
         "daily_median_90d": 1389, "per_million": 159.3, "confidence": "medium",
         "_reason_codes": [["seasonal", {"peak": 1, "amp": 2.1}],
                           ["not_significant", {"g": 4, "p": 0.12}],
                           ["small_base", {"base": 40}], ["spiky", {"share": 0.4}]]}
    line = headline(s, "uk")
    assert "0,12" in line and "2,1 раза" in line and "1 389" in line
    assert check_uk(line, {"intermittent", "fasting"}) == []
    params = {"g": 4, "p": 0.2, "base": 9, "share": 0.4, "months": 9, "since": "2025-03",
              "rel": -3, "yoy": -8, "peak": 2, "amp": 1.4, "lo": -30, "hi": 20, "used": 20,
              "total": 31, "up": 1, "down": 1, "flat": 0, "n": 2, "id": "pl:X", "v": "10",
              "c": "НИЗЬКА", "m": "3 з 12", "pm": 3.0}
    texts = [reason_text(code, params, "uk") for code in REASONS["uk"]]
    texts += [t.format(**params) for t in TEXT["uk"].values()]
    assert check_uk(". ".join(texts)) == []
    assert "Гіпотеза для перевірки" in " ".join(CHECKLIST["uk"])


def test_skill_example_is_clean():
    skill = (ROOT / "SKILL.md").read_text()
    example = "\n".join(ln[2:] for ln in skill.splitlines() if ln.startswith("> "))
    assert example and check_uk(example) == []


def test_old_eval_answers_are_flagged():
    """Calques from real Haiku answers before the language fixes must be flagged."""
    answers = [
        "Року на року інтерес у чеському виданні знаходиться в межах похибки.",
        "Інтерес зріс в 2,1 рази, а впевненість висока.",
        "На протязі двох років переглядів сторінок показують stediy спад.",
    ]
    for a in answers:
        assert check_uk(a), a


def test_participles_and_numeral_agreement():
    text = ("Спадаючий тренд обумовлений сезонністю; аудиторія становить 131 переглядів на "
            "день, а в чеськомовній Вікіпедії 1 552 переглядів і розділ має 3 растучих ринки. "
            "Теми растуть, проверю в чеськомовній розділі.")
    found = " ".join(check_uk(text))
    for word in ("Спадаючий", "обумовлений", "131 переглядів", "1 552 переглядів",
                 "растучих", "растуть", "проверю", "чеськомовній розділі"):
        assert word in found, word
    ok = ("Аудиторія становить 1 389 переглядів на день, 111 переглядів і 236 переглядів; "
          "інтерес, що зростає, у польськомовній Вікіпедії. Ключі та гарячі теми.")
    assert check_uk(ok) == []
