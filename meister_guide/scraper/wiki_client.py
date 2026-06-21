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
    """Ensure a category name carries a 'Category:' prefix (e.g. 'Mobs' or 'Category:Mobs').
    Returns '' for blank input so the caller can short-circuit."""
    name = (name or "").strip()
    if not name:
        return ""
    if name.lower().startswith("category:"):
        return name
    return "Category:" + name


class WikiClient:
    def __init__(self, api_url=DEFAULT_API, http_get=None, delay=0.0,
                 sleep=time.sleep, max_retries=5, backoff=1.0, extract=None):
        self._api = api_url
        self._http_get = http_get or self._default_get
        self._delay = delay
        self._sleep = sleep
        self._max_retries = max_retries
        self._backoff = backoff
        self._extract = extract or self._default_extract
        self._has_extracts = None      # cached TextExtracts capability

    def _default_get(self, params):
        import requests
        resp = requests.get(self._api, params=params,
                            headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _default_extract(html):
        """Plain text from rendered wiki HTML. Lazy-imports trafilatura (already a
        dependency) so importing this module never requires it."""
        import trafilatura
        return trafilatura.extract(html, include_comments=False,
                                   include_tables=True) or ""

    def has_textextracts(self):
        """True if the wiki has the TextExtracts extension (cached, one siteinfo
        call). On a detection failure, returns False so we use the parse path."""
        if self._has_extracts is None:
            try:
                data = self._fetch({
                    "action": "query", "format": "json",
                    "meta": "siteinfo", "siprop": "extensions", "maxlag": 5,
                })
                exts = data.get("query", {}).get("extensions", [])
                self._has_extracts = any(e.get("name") == "TextExtracts"
                                         for e in exts)
            except Exception:
                # Treat as absent (use the parse path); cached for this client's
                # lifetime — a fresh WikiClient is built per download, so the next
                # run re-detects.
                self._has_extracts = False
        return self._has_extracts

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
        """Fetch plain-text articles for specific titles. Uses prop=extracts when
        available, else action=parse + trafilatura per title."""
        if not titles:
            return []
        if not self.has_textextracts():
            return [a for a in (self._parse_page(t) for t in titles)
                    if a is not None]
        data = self._fetch({
            "action": "query", "format": "json",
            "titles": "|".join(titles),
            "prop": "extracts", "explaintext": 1, "exlimit": "max",
            "maxlag": 5,
        })
        return self._articles_from(data)

    def _parse_page(self, title):
        """Fetch one page via action=parse, extract plain text with self._extract,
        return a WikiArticle (or None if missing/empty). Per-page failures return
        None so one bad page never aborts a bulk walk; systemic failures still
        surface from the enumeration request in _iter_batches_parse."""
        try:
            data = self._fetch({
                "action": "parse", "format": "json", "page": title,
                "prop": "text", "formatversion": 2, "redirects": 1, "maxlag": 5,
            })
        except Exception:
            return None
        parse = data.get("parse")
        if not parse:
            return None
        text = (self._extract(parse.get("text") or "") or "").strip()
        if not text:
            return None
        return WikiArticle(parse.get("pageid"), parse.get("title", title),
                           text, parse.get("revid"))

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
                sub = member.get("title")
                if sub:
                    subcats.append(sub)
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
        """Yield (list[WikiArticle], next_token|None) per batch. Uses the light
        extracts path when the wiki has TextExtracts, else action=parse +
        trafilatura."""
        if self.has_textextracts():
            yield from self._iter_batches_extracts(start_token)
        else:
            yield from self._iter_batches_parse(start_token)

    def _iter_batches_extracts(self, start_token=None):
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

    def _iter_batches_parse(self, start_token=None):
        token = start_token
        while True:
            params = {
                "action": "query", "format": "json", "list": "allpages",
                # aplimit kept at 50: each title is a separate action=parse fetch,
                # so a small enumeration page keeps per-batch commits frequent
                # (mirrors the redirect walker).
                "apnamespace": 0, "aplimit": 50, "maxlag": 5,
            }
            if token:
                params.update(json.loads(token))
            data = self._fetch(params)
            titles = [p["title"] for p in data.get("query", {}).get("allpages", [])
                      if "title" in p]
            articles = [a for a in (self._parse_page(t) for t in titles)
                        if a is not None]
            cont = data.get("continue")
            next_token = json.dumps(cont) if cont else None
            yield articles, next_token
            if next_token is None:
                return
            token = next_token
            self._sleep(self._delay)
