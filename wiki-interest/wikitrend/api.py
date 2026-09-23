"""Thin clients for Wikimedia REST pageviews, MediaWiki and Wikidata APIs.

All calls go through `WikiClient`, which caches results in `Cache`:
series are fetched incrementally, metadata lookups are cached for 30 days.
"""
from __future__ import annotations

import calendar
import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from urllib.parse import quote, urlencode

from .cache import Cache, missing_ranges

USER_AGENT = (
    "wiki-interest-skill/0.1 (https://github.com/lizakolot12/MyWikiResearch; research tool)"
)
PAGEVIEWS = "https://wikimedia.org/api/rest_v1/metrics/pageviews"
WIKIDATA = "https://www.wikidata.org/w/api.php"
DATA_START = date(2015, 7, 1)  # first day of the pageviews API (agent=user)
SETTLE_DAYS = 3  # recent days may not be published yet; do not treat them as final


def _today() -> date:
    return date.today()


def settled_until(fetched_to: date, returned: list[date]) -> date:
    """Last day of a fetched range that can be cached as final.

    Days up to `today - SETTLE_DAYS` are final even without data (0 views).
    Later days count only up to the last day the API actually returned.
    """
    settled = _today() - timedelta(days=SETTLE_DAYS)
    if fetched_to <= settled:
        return fetched_to
    return min(fetched_to, max([settled, *returned]))


class ApiError(RuntimeError):
    pass


RETRY_STATUS = (429, 500, 502, 503, 504)


def _ssl_context() -> ssl.SSLContext:
    """System CA store; certifi's bundle if installed (some Python builds ship without CAs)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL = _ssl_context()


def http_get_json(url: str, params: dict | None = None):
    """GET JSON with retries (standard library only). Returns None on 404 (no data)."""
    if params:
        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    delay = 1.0
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code not in RETRY_STATUS or attempt == 4:
                body = e.read().decode("utf-8", "replace")[:200]
                raise ApiError(f"HTTP {e.code} for {url}: {body}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt == 4:
                raise ApiError(f"network error for {url}: {e}") from e
        time.sleep(delay)
        delay *= 2
    raise ApiError(f"failed: {url}")


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _parse_ts(ts: str) -> date:
    return date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))


def wiki_title(title: str) -> str:
    return title.replace(" ", "_")


class WikiClient:
    def __init__(self, cache: Cache):
        self.cache = cache
        self.requests_made = 0

    def _get(self, url, params=None):
        self.requests_made += 1
        return http_get_json(url, params)

    def _meta(self, key, fn):
        hit = self.cache.get_meta(key)
        if hit is not None:
            return hit
        value = fn()
        self.cache.put_meta(key, value)
        return value

    # ---- topic resolution ---------------------------------------------------
    def search_wikidata(self, query: str, lang: str, limit: int = 5) -> list[dict]:
        def fetch():
            data = self._get(WIKIDATA, {
                "action": "wbsearchentities", "search": query, "language": lang,
                "uselang": lang, "type": "item", "limit": limit, "format": "json",
            }) or {}
            return [
                {"qid": x["id"], "label": x.get("label", ""),
                 "description": x.get("description", "")}
                for x in data.get("search", [])
            ]
        return self._meta(f"wdsearch:{lang}:{query.lower()}", fetch)

    def entity(self, qid: str) -> dict:
        """Label, description and {lang: article title} for a Wikidata item."""
        def fetch():
            data = self._get(WIKIDATA, {
                "action": "wbgetentities", "ids": qid, "props": "sitelinks|labels|descriptions",
                "languages": "en", "format": "json",
            }) or {}
            ent = data.get("entities", {}).get(qid, {})
            links = {
                k[:-4].replace("_", "-"): v["title"]
                for k, v in ent.get("sitelinks", {}).items()
                if k.endswith("wiki") and k not in ("commonswiki", "specieswiki", "metawiki")
                and "wikiquote" not in k
            }
            return {
                "qid": qid,
                "label": ent.get("labels", {}).get("en", {}).get("value", qid),
                "description": ent.get("descriptions", {}).get("en", {}).get("value", ""),
                "sitelinks": links,
            }
        return self._meta(f"entity:{qid}", fetch)

    def qid_for_article(self, lang: str, title: str) -> str | None:
        def fetch():
            data = self._get(f"https://{lang}.wikipedia.org/w/api.php", {
                "action": "query", "titles": title, "prop": "pageprops",
                "ppprop": "wikibase_item", "redirects": 1, "format": "json", "formatversion": 2,
            }) or {}
            pages = data.get("query", {}).get("pages", [])
            if not pages or pages[0].get("missing"):
                return None
            return pages[0].get("pageprops", {}).get("wikibase_item")
        return self._meta(f"qid:{lang}:{title}", fetch)

    def redirects(self, lang: str, title: str) -> list[str]:
        """Titles that redirect to the article (includes old names after a rename)."""
        def fetch():
            data = self._get(f"https://{lang}.wikipedia.org/w/api.php", {
                "action": "query", "titles": title, "prop": "redirects", "rdnamespace": 0,
                "rdlimit": "max", "format": "json", "formatversion": 2,
            }) or {}
            pages = data.get("query", {}).get("pages", [])
            return [r["title"] for r in (pages[0].get("redirects", []) if pages else [])]
        return self._meta(f"redirects:{lang}:{title}", fetch)

    # ---- pageviews --------------------------------------------------------
    def daily_views(self, lang: str, title: str, start: date, end: date,
                    access: str = "all-access") -> dict[date, int]:
        """Daily user (non-bot) views; days without data are absent (= 0 views)."""
        start = max(start, DATA_START)
        key = f"daily:{lang}:{access}:{wiki_title(title)}"
        for a, b in missing_ranges((start, end), self.cache.coverage(key)):
            url = (f"{PAGEVIEWS}/per-article/{lang}.wikipedia/{access}/user/"
                   f"{quote(wiki_title(title), safe='')}/daily/{_ymd(a)}00/{_ymd(b)}00")
            data = self._get(url) or {}
            pts = {_parse_ts(x["timestamp"]): x["views"] for x in data.get("items", [])}
            last = settled_until(b, list(pts))
            if last >= a:
                self.cache.store_series(key, a, last, {d: v for d, v in pts.items() if d <= last})
        return self.cache.load_series(key, start, end)

    def monthly_totals(self, lang: str, start: date, end: date,
                       access: str = "all-access") -> dict[date, int]:
        """Total user views of the whole language edition per month (keyed by 1st day)."""
        start = max(start.replace(day=1), DATA_START)
        end = end.replace(day=1)
        key = f"total:{lang}:{access}"
        for a, b in missing_ranges((start, end), self.cache.coverage(key)):
            a = a if a.day == 1 else (month_end(a) + timedelta(days=1))
            if a > b:
                continue
            url = (f"{PAGEVIEWS}/aggregate/{lang}.wikipedia/{access}/user/monthly/"
                   f"{_ymd(a)}00/{_ymd(month_end(b))}00")
            data = self._get(url) or {}
            pts = {_parse_ts(x["timestamp"]).replace(day=1): x["views"]
                   for x in data.get("items", [])}
            # months are final up to the first one that is neither settled nor returned
            settled = _today() - timedelta(days=SETTLE_DAYS)
            last, m = None, a
            while m <= b and (month_end(m) <= settled or m in pts):
                last, m = m, month_end(m) + timedelta(days=1)
            if last is not None:
                self.cache.store_series(key, a, last, {m: v for m, v in pts.items() if m <= last})
        return self.cache.load_series(key, start, end)
