"""MediaWiki API client for minecraft.wiki — streams batched plain-text article
extracts. Pure: HTTP and sleep are injectable so tests run without a network."""
import json
import time
from dataclasses import dataclass
from typing import Optional

DEFAULT_API = "https://minecraft.wiki/api.php"
USER_AGENT = (
    "MeisterGuide/0.3 (offline Minecraft guide reader; "
    "https://github.com/meister-guide)"
)


@dataclass
class WikiArticle:
    pageid: int
    title: str
    text: str
    revid: Optional[int]


class WikiClient:
    def __init__(self, api_url=DEFAULT_API, http_get=None, delay=1.0,
                 sleep=time.sleep):
        self._api = api_url
        self._http_get = http_get or self._default_get
        self._delay = delay
        self._sleep = sleep

    def _default_get(self, params):
        import requests
        resp = requests.get(self._api, params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _params(self, continue_token):
        params = {
            "action": "query", "format": "json",
            "generator": "allpages", "gapnamespace": 0, "gaplimit": "max",
            "prop": "extracts", "explaintext": 1, "exlimit": "max",
            "maxlag": 5,
        }
        if continue_token:
            params.update(json.loads(continue_token))
        return params

    @staticmethod
    def _articles_from(data):
        pages = data.get("query", {}).get("pages", {})
        out = []
        for page in pages.values():
            if "extract" not in page:
                continue
            out.append(WikiArticle(page["pageid"], page["title"],
                                   page["extract"], page.get("lastrevid")))
        return out

    def iter_batches(self, start_token=None):
        """Yield (list[WikiArticle], next_token|None) per API batch."""
        token = start_token
        while True:
            data = self._http_get(self._params(token))
            articles = self._articles_from(data)
            cont = data.get("continue")
            next_token = json.dumps(cont) if cont else None
            yield articles, next_token
            if next_token is None:
                return
            token = next_token
            self._sleep(self._delay)
