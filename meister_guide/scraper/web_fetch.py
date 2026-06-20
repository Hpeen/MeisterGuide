"""Download a web page and extract its main article text. Pure: both the HTTP
GET and the HTML->(title, text) extractor are injectable so tests run without a
network or the trafilatura dependency. The real default extractor lazy-imports
trafilatura (mirrors the anthropic lazy-import pattern)."""
from urllib.parse import urlparse

USER_AGENT = "MeisterGuide/0.4 (game guide reader; https://github.com/meister-guide)"


def _default_get(url):
    import requests
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.text


def _default_extract(html):
    """(title, text) via trafilatura. Returns empty strings when nothing is
    extractable (e.g. a JS-only page) rather than raising."""
    import trafilatura
    text = trafilatura.extract(html) or ""
    title = ""
    meta = trafilatura.extract_metadata(html)
    if meta is not None and meta.title:
        title = meta.title
    return title, text


def fetch_main_text(url, http_get=None, extract=None):
    """Fetch `url` and return (title, text). Title falls back to the URL host
    when the extractor yields none. Only network errors propagate; empty
    extraction yields ('<host>', '') for the caller to skip."""
    get = http_get or _default_get
    extract = extract or _default_extract
    html = get(url)
    title, text = extract(html)
    if not title:
        title = urlparse(url).netloc or url
    return title, text
