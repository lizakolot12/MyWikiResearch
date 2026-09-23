"""End-to-end CLI runs on the fake API: analyze -> follow-up -> show -> report."""
import json
import re

from wiki_interest_cli import main


def run(capsys, *args):
    code = main(list(args))
    out = capsys.readouterr().out
    return code, out


def test_full_flow(tmp_path, capsys, fake_api):
    cache = str(tmp_path / "c")
    code, out = run(capsys, "--cache-dir", cache, "analyze", "--topics",
                    "Intermittent fasting grow", "--langs", "pl,cs", "--out", str(tmp_path))
    assert code == 0
    r = json.loads(out)
    assert r["demo_data"] is True
    assert {s["lang"] for s in r["series"]} == {"pl", "cs"}
    assert all(s["verdict"] == "growing" for s in r["series"])
    assert "_monthly" not in out  # compact output for the agent
    first_requests = r["api_requests"]

    # Follow-up: add a language -> only the new language is fetched.
    code, out = run(capsys, "--cache-dir", cache, "analyze", "--topics",
                    "Intermittent fasting grow", "--langs", "pl,cs,sk", "--out", str(tmp_path))
    r2 = json.loads(out)
    assert 0 < r2["api_requests"] < first_requests

    code, out = run(capsys, "--cache-dir", cache, "show", "--series", "sk")
    assert "sk:" in out and re.search(r"20\d\d-\d\d\s+\d", out)

    pdf = tmp_path / "r.pdf"
    code, out = run(capsys, "--cache-dir", cache, "report", "--title", "Тест",
                    "--summary", "Коротко.", "--rec", "Одна.", "--out", str(pdf))
    assert code == 0 and pdf.exists()
    assert len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes())) == 1  # one page
    assert "language_warnings" not in json.loads(out)

    # Calques in the agent's own text come back as warnings (the PDF is still written).
    code, out = run(capsys, "--cache-dir", cache, "report", "--title", "Тест",
                    "--summary", "Інтерес у чеському виданні зростає рік на рік, і це "
                    "знаходиться в межах похибки.", "--out", str(pdf))
    warnings = " ".join(json.loads(out)["language_warnings"])
    assert code == 0 and "рік на рік" in warnings and "знаходиться" in warnings


def test_headlines_follow_ui_lang(tmp_path, capsys, fake_api):
    args = ["--cache-dir", str(tmp_path / "c"), "analyze", "--topics", "Astronomy",
            "--langs", "uk", "--out", str(tmp_path)]
    r = json.loads(run(capsys, *args)[1])
    assert "довіра до висновку" in r["headlines"][0]
    assert "СИНТЕТИЧНІ" in r["warning"]
    assert any("Гіпотеза для перевірки" in c for c in r["answer_checklist"])
    r = json.loads(run(capsys, *args, "--ui-lang", "en")[1])
    assert "confidence" in r["headlines"][0] and not re.search("[а-я]", r["headlines"][0])


def test_missing_article_and_bad_topic(tmp_path, capsys, fake_api):
    cache = str(tmp_path / "c")
    code, out = run(capsys, "--cache-dir", cache, "analyze", "--topics",
                    "Something missing; nothing at all", "--langs", "pl,cs", "--out",
                    str(tmp_path))
    r = json.loads(out)
    statuses = {s["id"]: s["status"] for s in r["series"]}
    assert statuses["cs:Something missing"] == "missing_article"
    assert r["topics"][1]["status"] == "not_found"


def test_invalid_input_returns_json_error(tmp_path, capsys, fake_api):
    code, out = run(capsys, "--cache-dir", str(tmp_path), "analyze", "--topics", "X",
                    "--langs", "polish!", "--out", str(tmp_path))
    assert code == 1 and "error" in json.loads(out)
