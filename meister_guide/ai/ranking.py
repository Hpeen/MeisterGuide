"""Re-rank FTS5 candidates so the canonical topic article wins over noise
(version changelogs, disambiguation pages, history subpages, movie/event
pages). Pure functions — no DB, no I/O."""
import re

_DISAMBIG_PENALTY = 100000.0   # sink below everything real
_NOISE_PENALTY = 5000.0        # version/history/movie pages

_VERSION_PREFIX = re.compile(r"^(java|bedrock|legacy console|pocket) edition\b")
_VERSION_NUMBER = re.compile(r"\d+\.\d+")


def noise_penalty(title):
    """Non-negative penalty: higher = less useful as an answer source."""
    low = title.lower()
    if low.endswith("(disambiguation)"):
        return _DISAMBIG_PENALTY
    if _VERSION_PREFIX.match(low) and _VERSION_NUMBER.search(low):
        return _NOISE_PENALTY
    if "development versions" in low:
        return _NOISE_PENALTY
    if " history" in low:               # leading space avoids "History of …"
        return _NOISE_PENALTY
    if "a minecraft movie" in low or "live event" in low:
        return _NOISE_PENALTY
    return 0.0
