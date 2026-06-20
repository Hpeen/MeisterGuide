"""Shared display-URL helper for fetched wiki pages. The stored `url` is
display-only (the article body is what's searched), so a best-effort
reconstruction from the wiki base + title is sufficient."""


def page_url(base, title):
    """Best-effort display URL: <base>/wiki/<Title_With_Underscores>."""
    return (base or "").rstrip("/") + "/wiki/" + title.replace(" ", "_")


def web_pageid(url):
    """Stable positive int id for a scraped web page. articles.pageid is
    UNIQUE NOT NULL INTEGER and wiki pageids are small (< 1e8), so a ~60-bit
    truncated SHA-1 of the URL never collides with a real wiki pageid and keeps
    ingestion idempotent (re-fetching the same URL is a no-op)."""
    import hashlib
    return int(hashlib.sha1(url.encode("utf-8")).hexdigest()[:15], 16)
