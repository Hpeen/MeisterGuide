"""Shared display-URL helper for fetched wiki pages. The stored `url` is
display-only (the article body is what's searched), so a best-effort
reconstruction from the wiki base + title is sufficient."""
import re

# A trailing MediaWiki article path: /wiki/Title or /w/Title (needs the slash
# after "wiki"/"w", so "/wikipedia" is left alone). A leading language/site
# subpath (e.g. fandom.com/de) is preserved.
_ARTICLE_PATH_RE = re.compile(r"/(?:wiki|w)/.*$", re.IGNORECASE)


def wiki_base(url):
    """Normalize a wiki URL to its base, so a pasted page URL still yields the
    right endpoints. Strips a trailing article path (/wiki/Title or /w/Title) and
    trailing slashes; preserves a language subpath. Returns '' for falsy input."""
    if not url:
        return ""
    return _ARTICLE_PATH_RE.sub("", url.strip()).rstrip("/")


def page_url(base, title):
    """Best-effort display URL: <base>/wiki/<Title_With_Underscores>. Tolerates a
    full page URL as `base` (normalizes it first)."""
    return wiki_base(base) + "/wiki/" + title.replace(" ", "_")


def web_pageid(url):
    """Stable positive int id for a scraped web page. articles.pageid is
    UNIQUE NOT NULL INTEGER and wiki pageids are small (< 1e8), so a ~60-bit
    truncated SHA-1 of the URL never collides with a real wiki pageid and keeps
    ingestion idempotent (re-fetching the same URL is a no-op)."""
    import hashlib
    return int(hashlib.sha1(url.encode("utf-8")).hexdigest()[:15], 16)
