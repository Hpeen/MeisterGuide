# Fandom Content Fetch (parse + trafilatura) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make article-text fetching work on wikis without the TextExtracts extension (Fandom) by auto-detecting capability and falling back to `action=parse` + trafilatura, while keeping the light `prop=extracts` path for wikis that have it (minecraft.wiki).

**Architecture:** All changes live in `meister_guide/scraper/wiki_client.py`. `WikiClient` detects TextExtracts once (cached siteinfo call) and branches `iter_batches`/`fetch_by_titles` between the existing extracts path and a new parse path. Consumers (`ingest`, `on_demand`, `seed`, `worker`, `window`) are untouched.

**Tech Stack:** Python, MediaWiki action API, trafilatura (already a dependency), pytest.

**Spec:** `docs/superpowers/specs/2026-06-21-fandom-parse-fetch-design.md`

---

## File structure

- **Modify** `meister_guide/scraper/wiki_client.py` — add an injectable `extract` seam, `has_textextracts()` detection, `_parse_page(title)`, and parse branches in `iter_batches`/`fetch_by_titles`.
- **Modify** `tests/test_wiki_client.py` — new detection + parse-path tests; convert existing extracts-path tests to answer the detection call via a small helper.

No other files change.

---

## Task 1: Extraction seam + TextExtracts detection

**Files:**
- Modify: `meister_guide/scraper/wiki_client.py`
- Test: `tests/test_wiki_client.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_wiki_client.py`:

```python
def _siteinfo(extensions):
    return {"query": {"extensions": [{"name": n} for n in extensions]}}


def test_has_textextracts_true_when_extension_present():
    def get(params):
        assert params["meta"] == "siteinfo" and params["siprop"] == "extensions"
        return _siteinfo(["TextExtracts", "CirrusSearch"])
    client = WikiClient(http_get=get, delay=0, sleep=lambda s: None)
    assert client.has_textextracts() is True


def test_has_textextracts_false_when_absent():
    client = WikiClient(http_get=lambda p: _siteinfo(["CirrusSearch"]),
                        delay=0, sleep=lambda s: None)
    assert client.has_textextracts() is False


def test_has_textextracts_is_cached():
    calls = {"n": 0}
    def get(params):
        calls["n"] += 1
        return _siteinfo(["TextExtracts"])
    client = WikiClient(http_get=get, delay=0, sleep=lambda s: None)
    assert client.has_textextracts() is True
    assert client.has_textextracts() is True
    assert calls["n"] == 1                 # one siteinfo call, then cached


def test_has_textextracts_false_on_detection_failure():
    def boom(params):
        raise RuntimeError("network down")
    client = WikiClient(http_get=boom, delay=0, sleep=lambda s: None, max_retries=2)
    assert client.has_textextracts() is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -m pytest tests/test_wiki_client.py -k has_textextracts -v`
Expected: FAIL (`AttributeError: 'WikiClient' object has no attribute 'has_textextracts'`).

- [ ] **Step 3: Add the extract seam and detection (`wiki_client.py`)**

In `WikiClient.__init__`, add the `extract` param and cache field. Replace the signature and the end of `__init__`:

```python
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
```

Add these methods (place them after `_default_get`):

```python
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
                self._has_extracts = False
        return self._has_extracts
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -m pytest tests/test_wiki_client.py -k has_textextracts -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full wiki-client test file (nothing else regressed yet)**

Run: `py -m pytest tests/test_wiki_client.py -q`
Expected: PASS — detection isn't wired into `iter_batches`/`fetch_by_titles` yet, so existing tests are unaffected.

- [ ] **Step 6: Commit**

```bash
git add meister_guide/scraper/wiki_client.py tests/test_wiki_client.py
git commit -m "feat: WikiClient TextExtracts detection + injectable extract seam"
```

---

## Task 2: Parse-path fetch (action=parse + trafilatura) wired into the branches

**Files:**
- Modify: `meister_guide/scraper/wiki_client.py`
- Test: `tests/test_wiki_client.py`

- [ ] **Step 1: Add a test helper and write failing parse-path tests**

Add this helper near the top of `tests/test_wiki_client.py` (after the imports):

```python
def _extracts_client(batch_handler, **kw):
    """A WikiClient whose siteinfo reports TextExtracts present, so it takes the
    extracts path; all other requests go to batch_handler. Lets the existing
    extracts-path tests keep their request fakes unchanged."""
    def get(params):
        if params.get("meta") == "siteinfo" and params.get("siprop") == "extensions":
            return {"query": {"extensions": [{"name": "TextExtracts"}]}}
        return batch_handler(params)
    return WikiClient(http_get=get, delay=0, sleep=lambda s: None, **kw)
```

Append the new parse-path tests:

```python
def _no_textextracts_get(handler):
    """Wrap a request handler so siteinfo reports NO TextExtracts (parse path)."""
    def get(params):
        if params.get("meta") == "siteinfo" and params.get("siprop") == "extensions":
            return {"query": {"extensions": []}}
        return handler(params)
    return get


def test_parse_page_builds_article_via_extract():
    def get(params):
        assert params["action"] == "parse" and params["page"] == "Seamoth"
        assert params["prop"] == "text"
        return {"parse": {"pageid": 7, "title": "Seamoth", "revid": 42,
                          "text": "<p>raw html</p>"}}
    client = WikiClient(http_get=get, delay=0, sleep=lambda s: None,
                        extract=lambda html: "clean text for " + html)
    art = client._parse_page("Seamoth")
    assert isinstance(art, WikiArticle)
    assert (art.pageid, art.title, art.revid) == (7, "Seamoth", 42)
    assert art.text == "clean text for <p>raw html</p>"


def test_parse_page_none_when_text_empty():
    client = WikiClient(
        http_get=lambda p: {"parse": {"pageid": 1, "title": "X", "revid": 1,
                                      "text": "<p></p>"}},
        delay=0, sleep=lambda s: None, extract=lambda html: "   ")
    assert client._parse_page("X") is None


def test_parse_page_none_when_no_parse_key():
    client = WikiClient(http_get=lambda p: {"error": {"code": "missingtitle"}},
                        delay=0, sleep=lambda s: None, extract=lambda h: "t")
    assert client._parse_page("Ghost") is None       # error/no parse -> skipped


def test_fetch_by_titles_uses_parse_when_no_textextracts():
    def handler(params):
        assert params["action"] == "parse"            # not prop=extracts
        title = params["page"]
        return {"parse": {"pageid": hash(title) & 0xffff, "title": title,
                          "revid": 1, "text": f"<p>{title}</p>"}}
    client = WikiClient(http_get=_no_textextracts_get(handler), delay=0,
                        sleep=lambda s: None, extract=lambda h: h)  # html passthrough
    arts = client.fetch_by_titles(["Reaper Leviathan", "Seamoth"])
    assert sorted(a.title for a in arts) == ["Reaper Leviathan", "Seamoth"]
    assert all(isinstance(a, WikiArticle) for a in arts)


def test_iter_batches_uses_parse_when_no_textextracts():
    page1 = {"query": {"allpages": [{"title": "A"}, {"title": "B"}]},
             "continue": {"apcontinue": "C", "continue": "-||"}}
    page2 = {"query": {"allpages": [{"title": "C"}]}}
    allpages = [page1, page2]
    def handler(params):
        if params.get("list") == "allpages":
            assert params["apnamespace"] == 0
            return allpages.pop(0)
        if params.get("action") == "parse":
            t = params["page"]
            return {"parse": {"pageid": ord(t), "title": t, "revid": 1,
                              "text": f"<p>{t}</p>"}}
        raise AssertionError(params)
    client = WikiClient(http_get=_no_textextracts_get(handler), delay=0,
                        sleep=lambda s: None, extract=lambda h: h)
    batches = list(client.iter_batches())
    titles = [a.title for batch, _ in batches for a in batch]
    assert titles == ["A", "B", "C"]
    assert batches[0][1] == '{"apcontinue": "C", "continue": "-||"}'
    assert batches[-1][1] is None
```

- [ ] **Step 2: Convert the existing extracts-path tests to answer detection**

In `tests/test_wiki_client.py`, change the client construction in these tests from
`WikiClient(http_get=<fake>, delay=0, sleep=lambda s: None[, max_retries=N])` to
`_extracts_client(<fake>[, max_retries=N])` (keep each `<fake>` body unchanged):

- `test_iter_batches_parses_articles_and_stops` → `client = _extracts_client(fake_get)`
- `test_iter_batches_follows_continue_token` → `client = _extracts_client(fake_get)`
- `test_retries_transient_error_then_succeeds` → `client = _extracts_client(flaky_get)`
- `test_maxlag_error_is_retried` → `client = _extracts_client(lagging_get)`
- `test_gives_up_after_max_retries` → `client = _extracts_client(always_fail, max_retries=3)`
- `test_non_maxlag_api_error_raises` → `client = _extracts_client(erroring_get, max_retries=3)`
- `test_request_gaplimit_is_aligned_to_extract_limit` → `client = _extracts_client(fake_get)`
- `test_badcontinue_raises_invalid_continue_error` → `client = _extracts_client(fake_get)`
- `test_fetch_by_titles_builds_titles_param_and_parses` → `client = _extracts_client(fake_get)`

Leave unchanged (no detection call happens): `test_article_count_reads_statistics`,
`test_default_delay_is_zero`, `test_fetch_by_titles_empty_input_makes_no_request`
(empty list returns before detection), all `iter_redirect_mappings`/`search_titles`
tests.

- [ ] **Step 3: Run the new + converted tests to verify the new ones fail**

Run: `py -m pytest tests/test_wiki_client.py -q`
Expected: FAIL — the new parse-path tests fail (`_parse_page` missing; parse branch not implemented). The converted extracts tests should still pass (helper answers siteinfo, extracts path unchanged). If a converted test fails, the helper conversion is wrong — fix before continuing.

- [ ] **Step 4: Implement `_parse_page` and the parse branches (`wiki_client.py`)**

Add `_parse_page` (after `fetch_by_titles`, or near `_articles_from`):

```python
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
```

Rename the current `iter_batches` body to `_iter_batches_extracts` and add a
dispatcher plus the parse walker. Replace the existing `iter_batches` method:

```python
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
```

(The body of `_iter_batches_extracts` is exactly the previous `iter_batches`
body — move it verbatim.)

Add the parse branch to `fetch_by_titles`. Replace its body:

```python
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
```

- [ ] **Step 5: Run the full wiki-client tests**

Run: `py -m pytest tests/test_wiki_client.py -q`
Expected: PASS (new parse tests + detection tests + converted extracts tests).

- [ ] **Step 6: Run the full suite**

Run: `py -m pytest -q`
Expected: PASS (full suite green; consumers untouched).

- [ ] **Step 7: Commit**

```bash
git add meister_guide/scraper/wiki_client.py tests/test_wiki_client.py
git commit -m "feat: action=parse + trafilatura fetch for wikis without TextExtracts"
```

---

## Task 3: Real-wiki verification (manual, no code)

**Files:** none (verification only).

- [ ] **Step 1: Bounded live check against Subnautica**

With the merged code, run a throwaway bounded ingest against the real Subnautica
wiki and confirm articles now store with real text. From the repo root:

```
PYTHONPATH=. py -c "import tempfile,os,zlib; from meister_guide.db.database import connect,init_db; from meister_guide.db.games import GamesRepo,api_url_for; from meister_guide.db.articles import ArticlesRepo,ScrapeStateRepo; from meister_guide.scraper.wiki_client import WikiClient; from meister_guide.scraper.ingest import run_ingest; d=tempfile.mkdtemp(); c=connect(os.path.join(d,'t.db')); init_db(c); g=GamesRepo(c); sub=g.add('Subnautica',[],'https://subnautica.fandom.com'); cl=WikiClient(api_url=api_url_for(sub.wiki_url)); a=ArticlesRepo(c); s=ScrapeStateRepo(c); run_ingest(cl,a,s,c,game_id=sub.id,base='https://subnautica.fandom.com',should_cancel=lambda: a.count(game_id=sub.id)>=3); print('stored:', a.count(game_id=sub.id)); print('uses_extracts:', cl.has_textextracts())"
```
Expected: `stored: 3` (or more) and `uses_extracts: False` — i.e. the parse path
ran and real articles were stored. (This hits the live network; if offline, skip
and note it.)

- [ ] **Step 2: Confirm Minecraft path unaffected (optional, live)**

`WikiClient(api_url="https://minecraft.wiki/api.php").has_textextracts()` should be
`True` (so Minecraft keeps the light extracts path). Skip if offline.

---

## Self-review notes

- **Spec coverage:** extract seam (T1 step 3) ✓; `has_textextracts` cached + fail→False (T1) ✓; `_parse_page` via action=parse + extract, None on empty/missing (T2) ✓; `iter_batches` parse branch via list=allpages + per-title parse, same `(articles, token)` contract (T2) ✓; `fetch_by_titles` parse branch (T2) ✓; consumers untouched (only wiki_client.py + its test change) ✓; existing extracts tests answer detection via helper (T2 step 2) ✓; real-wiki validation (T3) ✓.
- **Type/name consistency:** `has_textextracts()`, `_parse_page(title)`, `_iter_batches_extracts`/`_iter_batches_parse`, `extract` seam, and `_has_extracts` cache used consistently across tasks and tests.
- **Resilience choice (documented in `_parse_page`):** per-page errors → None (skip) so a single bad page can't abort a multi-hour walk; the enumeration request is unwrapped so network-down surfaces.
- **No placeholders:** every code/test/command step is concrete.
