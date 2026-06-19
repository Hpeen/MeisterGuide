"""Pure helper: turn corpus counts + ingest completion flags into the Guides-tab
status line. Kept Qt-free and dependency-free so it is trivially unit-testable —
the overshoot bug hid that the download was unfinished, so completeness must be
stated honestly from the resume-token state, not implied by a full progress bar."""


def guides_status_text(article_count: int, articles_done: bool,
                       redirects_done: bool) -> str:
    if article_count <= 0:
        return "No guides yet — click Update guides"
    if not articles_done:
        return f"Incomplete — {article_count:,} downloaded · click Update to resume"
    if not redirects_done:
        return "Almost done — click Update to link related topics"
    return f"Complete · {article_count:,} articles"
