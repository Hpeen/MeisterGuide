"""Shared display-URL helper for fetched wiki pages. The stored `url` is
display-only (the article body is what's searched), so a best-effort
reconstruction from the wiki base + title is sufficient."""


def page_url(base, title):
    """Best-effort display URL: <base>/wiki/<Title_With_Underscores>."""
    return (base or "").rstrip("/") + "/wiki/" + title.replace(" ", "_")
