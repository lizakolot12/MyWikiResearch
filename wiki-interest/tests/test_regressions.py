"""Regression tests for bugs fixed in stage 2 (one test per bug)."""
import importlib.util
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from wiki_interest_cli import main
from wikitrend import api
from wikitrend.analyze import rank_pool
from wikitrend.answer_check import check_answer, unhedged_causes, verdict_upgrades
from wikitrend.api import WikiClient
from wikitrend.cache import Cache

SKILL = Path(__file__).resolve().parent.parent


def load_installer():
    spec = importlib.util.spec_from_file_location("installer", SKILL / "install.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- install.py -----------------------------------------------------------------
def test_zip_builds_archive_and_installs_nothing(tmp_path, monkeypatch):
    inst = load_installer()
    monkeypatch.setattr(inst, "place", lambda *a, **k: pytest.fail("--zip must not install"))
    monkeypatch.setattr(inst, "install_deps",
                        lambda *a, **k: pytest.fail("--zip must not install deps"))
    out = tmp_path / "skill.zip"
    assert inst.main(["--zip", str(out)]) == 0
    names = zipfile.ZipFile(out).namelist()
    assert "wiki-interest/SKILL.md" in names
    assert not any("/.cache/" in n or "/.venv/" in n for n in names)


def test_copy_to_link_keeps_data_cache(tmp_path, monkeypatch):
    inst = load_installer()
    src = tmp_path / "repo" / "wiki-interest"
    (src / "scripts").mkdir(parents=True)
    monkeypatch.setattr(inst, "SRC", src)
    dest = tmp_path / "skills" / "wiki-interest"
    (dest / ".cache").mkdir(parents=True)
    (dest / ".cache" / "cache.sqlite").write_text("data")

    inst.place(dest, link=True)
    assert dest.is_symlink()
    assert (src / ".cache" / "cache.sqlite").read_text() == "data"


def test_copy_to_link_does_not_overwrite_source_cache(tmp_path, monkeypatch):
    inst = load_installer()
    src = tmp_path / "repo" / "wiki-interest"
    (src / ".cache").mkdir(parents=True)
    (src / ".cache" / "cache.sqlite").write_text("source")
    monkeypatch.setattr(inst, "SRC", src)
    dest = tmp_path / "skills" / "wiki-interest"
    (dest / ".cache").mkdir(parents=True)
    (dest / ".cache" / "cache.sqlite").write_text("copy")

    inst.place(dest, link=True)
    assert (src / ".cache" / "cache.sqlite").read_text() == "source"
    backup = tmp_path / "skills" / "wiki-interest-cache-backup" / "cache.sqlite"
    assert backup.read_text() == "copy"


# ---- analyze.py -----------------------------------------------------------------
def test_language_without_combined_series_is_ranked():
    series = [{"lang": "pl", "id": "pl:A"}, {"lang": "pl", "id": "pl:B"},
              {"lang": "cs", "id": "cs:A"}]
    combined = [{"lang": "pl", "id": "pl:ALL(2 topics)"}]
    assert [s["id"] for s in rank_pool(series, combined)] == ["pl:ALL(2 topics)", "cs:A"]
    assert rank_pool(series[2:], []) == series[2:]


def test_ranking_keeps_language_with_one_article(tmp_path, capsys, fake_api):
    # "Something missing" has no cs article, so cs has one series and no combined one.
    code = main(["--cache-dir", str(tmp_path / "c"), "analyze", "--topics",
                 "Something missing; Astronomy", "--langs", "pl,cs", "--out", str(tmp_path)])
    order = json.loads(capsys.readouterr().out)["ranking"]["order"]
    assert code == 0
    assert any(x.startswith("pl:ALL") for x in order)
    assert any(x.startswith("cs:Astronomy") for x in order)


# ---- doctor ---------------------------------------------------------------------
def test_doctor_bypasses_cache(tmp_path, capsys, fake_api, monkeypatch):
    calls = []
    real = api.http_get_json
    monkeypatch.setattr(api, "http_get_json",
                        lambda url, params=None: calls.append(url) or real(url, params))
    for _ in range(2):
        main(["--cache-dir", str(tmp_path / "c"), "doctor"])
        out = json.loads(capsys.readouterr().out)
        assert out["pageviews_api"] == "ok" and out["wikidata_api"] == "ok"
    assert len(calls) == 4  # two API calls per run, none answered from the cache


def test_doctor_reports_network_error(tmp_path, capsys, monkeypatch):
    def down(url, params=None):
        raise api.ApiError("network error: unreachable")
    monkeypatch.setattr(api, "http_get_json", down)
    main(["--cache-dir", str(tmp_path / "c"), "doctor"])
    assert "unreachable" in json.loads(capsys.readouterr().out)["api_error"]


# ---- api.py: unpublished days are not cached as covered ---------------------------
def stub_daily(published_until: date, calls: list):
    def get(url, params=None):
        calls.append(url)
        start, end = url.split("/")[-2:]
        d = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
        e = min(date(int(end[:4]), int(end[4:6]), int(end[6:8])), published_until)
        items = []
        while d <= e:
            items.append({"timestamp": d.strftime("%Y%m%d00"), "views": 100})
            d += timedelta(days=1)
        return {"items": items}
    return get


def test_unpublished_days_are_fetched_again(tmp_path, monkeypatch):
    today = date(2026, 9, 2)
    monkeypatch.setattr(api, "_today", lambda: today)
    calls = []
    monkeypatch.setattr(api, "http_get_json", stub_daily(date(2026, 8, 30), calls))
    client = WikiClient(Cache(tmp_path))
    views = client.daily_views("pl", "X", date(2026, 8, 1), date(2026, 8, 31))
    assert date(2026, 8, 31) not in views
    assert client.cache.coverage("daily:pl:all-access:X")[1] == date(2026, 8, 30)

    # The API publishes Aug 31 later: a repeat query fetches only the missing day.
    monkeypatch.setattr(api, "http_get_json", stub_daily(date(2026, 8, 31), calls))
    views = client.daily_views("pl", "X", date(2026, 8, 1), date(2026, 8, 31))
    assert views[date(2026, 8, 31)] == 100
    assert calls[-1].endswith("/2026083100/2026083100")


def test_settled_days_without_views_are_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_today", lambda: date(2026, 9, 20))
    calls = []
    monkeypatch.setattr(api, "http_get_json", stub_daily(date(2026, 8, 20), calls))
    client = WikiClient(Cache(tmp_path))
    client.daily_views("pl", "X", date(2026, 8, 1), date(2026, 8, 31))
    client.daily_views("pl", "X", date(2026, 8, 1), date(2026, 8, 31))
    assert len(calls) == 1  # Aug 21-31 are settled: 0 views, not "unpublished"


def test_unpublished_month_total_is_fetched_again(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_today", lambda: date(2026, 9, 1))
    calls = []

    def totals(url, params=None):
        calls.append(url)
        return {"items": [{"timestamp": "2026070100", "views": 5}]}  # August not published
    monkeypatch.setattr(api, "http_get_json", totals)
    client = WikiClient(Cache(tmp_path))
    client.monthly_totals("pl", date(2026, 7, 1), date(2026, 8, 31))
    assert client.cache.coverage("total:pl:all-access")[1] == date(2026, 7, 1)
    client.monthly_totals("pl", date(2026, 7, 1), date(2026, 8, 31))
    assert len(calls) == 2 and "/2026080100/" in calls[-1]


# ---- answer_check.py --------------------------------------------------------------
def test_negated_growth_is_not_an_upgrade():
    run = {"series": [{"verdict": "stable"}], "combined": []}
    assert not verdict_upgrades("Інтерес не зростає і не спадає: він стабільний.", run)
    assert not verdict_upgrades("Interest is not growing; it isn't declining either.", run)
    assert verdict_upgrades("Інтерес зростає.", run)


def test_hedge_only_counts_in_its_own_sentence():
    text = "Можливо, це сезонність. Інтерес упав, бо школярі втратили інтерес до науки."
    assert unhedged_causes(text) == ["Інтерес упав, бо школярі втратили інтерес до науки."]
    assert not unhedged_causes("Гіпотеза для перевірки: інтерес упав, бо змінилася програма.")
    hints = check_answer(text).get("hints", [])
    assert any("cause" in h for h in hints)
