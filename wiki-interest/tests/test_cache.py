"""Cache: repeated and extended queries must not refetch data."""
from datetime import date

from wikitrend.cache import Cache, missing_ranges


def test_missing_ranges():
    r = (date(2024, 1, 1), date(2024, 12, 31))
    assert missing_ranges(r, None) == [r]
    assert missing_ranges(r, r) == []
    assert missing_ranges(r, (date(2024, 3, 1), date(2024, 6, 30))) == [
        (date(2024, 1, 1), date(2024, 2, 29)), (date(2024, 7, 1), date(2024, 12, 31))]
    # A request fully before the covered block also fills the gap (coverage stays contiguous).
    assert missing_ranges((date(2023, 1, 1), date(2023, 2, 1)), r) == [
        (date(2023, 1, 1), date(2023, 12, 31))]


def test_store_and_extend(tmp_path):
    c = Cache(tmp_path)
    c.store_series("k", date(2024, 1, 1), date(2024, 1, 31), {date(2024, 1, 5): 7})
    c.store_series("k", date(2024, 2, 1), date(2024, 2, 29), {date(2024, 2, 5): 9})
    assert c.coverage("k") == (date(2024, 1, 1), date(2024, 2, 29))
    assert c.load_series("k", date(2024, 1, 1), date(2024, 12, 31)) == {
        date(2024, 1, 5): 7, date(2024, 2, 5): 9}


def test_repeat_query_uses_cache(client):
    a = client.daily_views("pl", "Astronomia", date(2024, 1, 1), date(2024, 12, 31))
    n = client.requests_made
    b = client.daily_views("pl", "Astronomia", date(2024, 3, 1), date(2024, 6, 30))
    assert client.requests_made == n
    assert all(a[d] == v for d, v in b.items())
    client.daily_views("pl", "Astronomia", date(2023, 1, 1), date(2024, 12, 31))
    assert client.requests_made == n + 1
