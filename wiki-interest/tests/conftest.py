import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wikitrend import api  # noqa: E402
from wikitrend.api import WikiClient  # noqa: E402
from wikitrend.cache import Cache  # noqa: E402


@pytest.fixture
def fake_api(monkeypatch):
    """Route all HTTP calls to the deterministic fake Wikimedia API."""
    monkeypatch.setattr(api, "FAKE", True)


@pytest.fixture
def client(tmp_path, fake_api):
    return WikiClient(Cache(tmp_path / "cache"))
