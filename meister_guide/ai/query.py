"""Turn a free-text chat question into the content terms worth searching for,
so the FTS index isn't polluted by question/stop words ('how do I make a …')."""
import re

# Curated question + stop words. Small on purpose: only words that never help
# locate a Minecraft topic. Real nouns/verbs of interest are kept.
_STOP = {
    "how", "do", "does", "did", "done", "doing", "i", "you", "we", "they",
    "to", "a", "an", "the", "make", "makes", "made", "making", "work", "works",
    "working", "get", "gets", "getting", "is", "are", "was", "were", "be",
    "of", "in", "on", "for", "with", "and", "or", "what", "whats", "why",
    "when", "where", "who", "which", "can", "could", "should", "would", "will",
    "my", "me", "it", "this", "that", "best", "way", "ways", "use", "using",
    "need", "want", "about", "as", "at", "by", "from", "into",
}


def clean_query(text):
    """Return content terms: lowercased, no punctuation, no stop/short words,
    de-duplicated in order. Never returns empty — if cleaning removes
    everything, falls back to the de-duplicated raw tokens."""
    tokens = re.findall(r"\w+", (text or "").lower())

    def dedupe(words):
        seen, out = set(), []
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append(w)
        return out

    terms = dedupe(t for t in tokens if len(t) >= 2 and t not in _STOP)
    return terms or dedupe(tokens)
