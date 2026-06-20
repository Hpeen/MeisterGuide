"""Brave Search API client. Pure: the HTTP call is injectable so tests run
without a network or a real key. Returns (title, url) pairs for the web-fetch
orchestrator to scrape."""

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "MeisterGuide/0.4 (game guide reader; https://github.com/meister-guide)"


class BraveSearchClient:
    def __init__(self, api_key, http_get=None):
        self._api_key = api_key
        self._http_get = http_get or self._default_get

    def _default_get(self, url, headers, params):
        import requests
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def search(self, query, count=3):
        """Return up to `count` (title, url) pairs for `query`. Raises on a
        network/API error (the worker catches it)."""
        data = self._http_get(
            ENDPOINT,
            {"X-Subscription-Token": self._api_key,
             "Accept": "application/json",
             "User-Agent": USER_AGENT},
            {"q": query, "count": count},
        )
        results = data.get("web", {}).get("results", [])
        out = []
        for r in results[:count]:
            url = r.get("url")
            if url:
                out.append((r.get("title") or url, url))
        return out


class DuckDuckGoSearchClient:
    """Keyless web search via the `ddgs` library (DuckDuckGo). Pure: the search
    call is injectable so tests run without ddgs or a network. Same (title, url)
    interface as BraveSearchClient, so it's a drop-in for run_web_fetch.

    Caveat: ddgs scrapes an unofficial endpoint and can rate-limit or break;
    Brave (keyed) is the reliable upgrade."""
    def __init__(self, search_fn=None):
        self._search_fn = search_fn or self._default_search

    def _default_search(self, query, count):
        from ddgs import DDGS
        return DDGS().text(query, max_results=count)

    def search(self, query, count=3):
        """Return up to `count` (title, url) pairs for `query`. Raises on a
        library/network error (the worker catches it)."""
        results = self._search_fn(query, count) or []
        out = []
        for r in results[:count]:
            url = r.get("href")
            if url:
                out.append((r.get("title") or url, url))
        return out


def make_search_client(brave_api_key):
    """Pick the web-search provider: Brave when a key is set (more reliable),
    else the free keyless DuckDuckGo client."""
    if brave_api_key:
        return BraveSearchClient(brave_api_key)
    return DuckDuckGoSearchClient()
