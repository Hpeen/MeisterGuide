"""MediaWiki API client (per-wiki via injected api_url): bulk batched extract streaming for ingest, plus search + fetch-by-title for on-demand fetch. Pure: HTTP and sleep are injectable so tests run without a network."""
import json
import time
from dataclasses import dataclass
from typing import Optional

DEFAULT_API = "https://minecraft.wiki/api.php"
USER_AGENT = (
    "MeisterGuide/0.3 (offline Minecraft guide reader; "
    "https://github.com/meister-guide)"
)


class InvalidContinueError(RuntimeError):
    """The MediaWiki API rejected a resume (continue) token as invalid/stale.

    Distinct from a generic API error so the ingest orchestrator can recover by
    restarting enumeration from the beginning rather than failing."""


@dataclass
class WikiArticle:
    pageid: int
    title: str
    text: str
    revid: Optional[int]


def _normalize_category(name):
    """Turn 'Mobs' or 'Category:Mobs' into a 'Category:'-prefixed title.
    Returns '' for blank input so the caller can short-circuit."""
    name = (name or "").strip()
    if not name:
        return ""
    if name.lower().startswith("category:"):
        return name
    return "Category:" + name


class WikiClient:
    def __init__(self, api_url=DEFAULT_API, http_get=None, delay=0.0,
                 sleep=time.sleep, max_retries=5, backoff=1.0):
        self._api = api_url
        self._http_get = http_get or self._default_get
        self._delay = delay
        self._sleep = sleep
        self._max_retries = max_retries
        self._backoff = backoff

    def _default_get(self, params):
        import requests
        resp = requests.get(self._api, params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _params(self, continue_token):
        # gaplimit is aligned to the realistic extract yield: full-text extracts
        # return only 1 per request (TextExtracts caps exlimit=1 without
        # exintro), so a large gaplimit (e.g. "max"=500) just ships hundreds of
        # unused page-metadata entries per request. Politeness is via maxlag.
        params = {
            "action": "query", "format": "json",
            "generator": "allpages", "gapnamespace": 0, "gaplimit": 20,
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

    def _fetch(self, params):
        """One API call with bounded exponential backoff on transient failures
        and MediaWiki maxlag responses."""
        wait = self._backoff
        last_err = None
        for attempt in range(self._max_retries):
            try:
                data = self._http_get(params)
            except Exception as err:          # transient HTTP/network error
                last_err = err
                self._sleep(wait)
                wait *= 2
                continue
            if isinstance(data, dict) and "error" in data:
                code = data["error"].get("code")
                if code == "maxlag":
                    self._sleep(wait)
                    wait *= 2
                    continue
                if code == "badcontinue":
                    raise InvalidContinueError(str(data["error"]))
                raise RuntimeError(f"MediaWiki API error: {data['error']}")
            return data
        raise RuntimeError(f"MediaWiki API failed after {self._max_retries} "
                           f"attempts: {last_err}")

    def article_count(self):
        """Total article-namespace count, for the ingest progress total."""
        data = self._fetch({
            "action": "query", "format": "json",
            "meta": "siteinfo", "siprop": "statistics", "maxlag": 5,
        })
        return data.get("query", {}).get("statistics", {}).get("articles")

    def search_titles(self, query, limit=5):
        """MediaWiki full-text search (list=search) in the article namespace.
        Returns a list of page titles for the on-demand fetcher to pull."""
        data = self._fetch({
            "action": "query", "format": "json",
            "list": "search", "srsearch": query,
            "srnamespace": 0, "srlimit": limit, "maxlag": 5,
        })
        results = data.get("query", {}).get("search", [])
        return [r["title"] for r in results if "title" in r]

    def fetch_by_titles(self, titles):
        """Fetch plain-text extracts for specific titles (prop=extracts) in one request. Reuses _articles_from to build WikiArticles."""
        if not titles:
            return []
        data = self._fetch({
            "action": "query", "format": "json",
            "titles": "|".join(titles),
            "prop": "extracts", "explaintext": 1, "exlimit": "max",
            "maxlag": 5,
        })
        return self._articles_from(data)

    def _redirect_params(self, continue_token):
        # Enumerate redirect pages in the article namespace. aplimit is held at
        # 50 to match the per-request title cap of the redirect resolver below,
        # so one enumeration batch maps to exactly one resolve request.
        params = {
            "action": "query", "format": "json",
            "list": "allpages", "apnamespace": 0,
            "apfilterredir": "redirects", "aplimit": 50,
            "maxlag": 5,
        }
        if continue_token:
            params.update(json.loads(continue_token))
        return params

    @staticmethod
    def _titles_from_allpages(data):
        pages = data.get("query", {}).get("allpages", [])
        return [p["title"] for p in pages if "title" in p]

    def _resolve_redirects(self, titles):
        """Resolve redirect titles to their target titles in one request via the
        API's redirect resolver. Returns list of (from_title, to_title)."""
        if not titles:
            return []
        data = self._fetch({
            "action": "query", "format": "json",
            "titles": "|".join(titles), "redirects": 1, "maxlag": 5,
        })
        out = []
        for entry in data.get("query", {}).get("redirects", []):
            frm, to = entry.get("from"), entry.get("to")
            if frm and to:
                out.append((frm, to))
        return out

    def iter_redirect_mappings(self, start_token=None):
        """Yield (list[(from_title, to_title)], next_token|None) per allpages
        batch — each batch's redirect titles resolved to their targets in a
        single follow-up request. Mirrors iter_batches for the orchestrator."""
        token = start_token
        while True:
            data = self._fetch(self._redirect_params(token))
            mappings = self._resolve_redirects(self._titles_from_allpages(data))
            cont = data.get("continue")
            next_token = json.dumps(cont) if cont else None
            yield mappings, next_token
            if next_token is None:
                return
            token = next_token
            self._sleep(self._delay)

    def _category_members(self, category, namespaces):
        """Yield member dicts ({'pageid','ns','title'}) for one category,
        following cmcontinue. `namespaces` is a cmnamespace value, e.g. '0|14'
        (articles + subcategories) or '0' (articles only)."""
        token = None
        while True:
            params = {
                "action": "query", "format": "json",
                "list": "categorymembers", "cmtitle": category,
                "cmnamespace": namespaces, "cmlimit": 500, "maxlag": 5,
            }
            if token:
                params.update(token)
            data = self._fetch(params)
            for member in data.get("query", {}).get("categorymembers", []):
                yield member
            cont = data.get("continue")
            if not cont:
                return
            token = cont
            self._sleep(self._delay)

    def iter_category_members(self, category):
        """Article titles in `category`, walked one level deep: the category's
        direct article members (ns 0) plus the article members of each immediate
        subcategory (ns 14). Deduped, order-preserving. Returns [] for a blank
        category name without making a request."""
        cat = _normalize_category(category)
        if not cat:
            return []
        titles, subcats, seen = [], [], set()
        for member in self._category_members(cat, "0|14"):
            if member.get("ns") == 14:
                subcats.append(member["title"])
            else:
                title = member.get("title")
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
        for sub in subcats:
            for member in self._category_members(sub, "0"):
                if member.get("ns") != 0:
                    continue
                title = member.get("title")
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
        return titles

    def iter_batches(self, start_token=None):
        """Yield (list[WikiArticle], next_token|None) per API batch."""
        token = start_token
        while True:
            data = self._fetch(self._params(token))
            articles = self._articles_from(data)
            cont = data.get("continue")
            next_token = json.dumps(cont) if cont else None
            yield articles, next_token
            if next_token is None:
                return
            token = next_token
            self._sleep(self._delay)
