import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fake_api as fake  # noqa: E402
from wikitrend import api  # noqa: E402
from wikitrend.api import WikiClient  # noqa: E402
from wikitrend.cache import Cache  # noqa: E402


@pytest.fixture
def fake_api(monkeypatch):
    """Route all HTTP calls to the deterministic fake Wikimedia API (tests/fake_api.py)."""
    monkeypatch.setattr(api, "http_get_json", lambda url, params=None:
                        fake.handle(url, params or {}))


@pytest.fixture
def client(tmp_path, fake_api):
    return WikiClient(Cache(tmp_path / "cache"))
