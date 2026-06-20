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
