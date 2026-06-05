"""The essay index: serialization + summarization for index-then-read retrieval.

``format_index`` / ``parse_index`` are a pure, round-trippable INDEX.md codec.
``heuristic_summary`` is the deterministic, offline fallback; ``llm_summarize``
is the one-time Haiku-tier pass used at crawl time (exercised on a real run).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .extractor import Essay

_INDEX_HEADER = (
    "# Paul Graham Essays — Index\n\n"
    "Consult this index to pick the 1-2 most relevant essays for a question, "
    "then read those files in `essays/`.\n"
)

_STOPWORDS = {
    "the", "and", "that", "this", "with", "from", "have", "they", "your", "you",
    "for", "are", "but", "not", "what", "when", "which", "their", "them", "then",
    "than", "into", "about", "would", "could", "should", "will", "more", "most",
    "some", "such", "only", "just", "like", "because", "been", "were", "being",
    "thing", "things", "people", "want", "make", "makes", "made", "very", "much",
}


@dataclass(frozen=True)
class IndexEntry:
    filename: str
    title: str
    summary: str
    keywords: list[str] = field(default_factory=list)


def format_index(entries: list[IndexEntry]) -> str:
    parts = [_INDEX_HEADER]
    for e in entries:
        parts.append(
            f"\n## {e.filename}\n"
            f"**Title:** {e.title}\n"
            f"**Summary:** {e.summary}\n"
            f"**Keywords:** {', '.join(e.keywords)}\n"
        )
    return "".join(parts)


def parse_index(markdown: str) -> list[IndexEntry]:
    entries: list[IndexEntry] = []
    filename: str | None = None
    title = summary = ""
    keywords: list[str] = []

    def flush() -> None:
        if filename is not None:
            entries.append(IndexEntry(filename, title, summary, keywords))

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            filename = line[3:].strip()
            title = summary = ""
            keywords = []
        elif line.startswith("**Title:**"):
            title = line[len("**Title:**"):].strip()
        elif line.startswith("**Summary:**"):
            summary = line[len("**Summary:**"):].strip()
        elif line.startswith("**Keywords:**"):
            raw = line[len("**Keywords:**"):].strip()
            keywords = [k.strip() for k in raw.split(",") if k.strip()]
    flush()
    return entries


def build_index(items, summarize=None) -> list[IndexEntry]:
    """Build index entries for ``(filename, essay)`` items.

    ``summarize`` is an optional ``essay -> (summary, keywords)`` callable (the
    Haiku pass). If it is absent or raises for an essay, fall back to
    ``heuristic_summary`` so one failed call never breaks the build.
    """
    entries: list[IndexEntry] = []
    for filename, essay in items:
        summary = keywords = None
        if summarize is not None:
            try:
                summary, keywords = summarize(essay)
            except Exception:  # noqa: BLE001 — fall back, never abort
                summary = None
        if summary is None:
            summary, keywords = heuristic_summary(essay)
        entries.append(IndexEntry(filename, essay.title, summary, keywords or []))
    return entries


def build_index_cached(items, cache, summarize_many=None) -> list[IndexEntry]:
    """Build index entries, reusing a ``SummaryCache`` and summarizing only the
    misses via ``summarize_many`` (filename, essay) pairs -> {filename: (summary,
    keywords)}. Anything still unsummarized falls back to the heuristic. New
    summaries are written to the cache.
    """
    cached: dict[str, tuple[str, list[str]]] = {}
    misses: list = []
    for filename, essay in items:
        hit = cache.get(essay.text)
        if hit is not None:
            cached[filename] = hit
        else:
            misses.append((filename, essay))

    fresh: dict[str, tuple[str, list[str]]] = {}
    if misses and summarize_many is not None:
        try:
            fresh = summarize_many(misses) or {}
        except Exception:  # noqa: BLE001 — fall back to heuristic, never abort
            fresh = {}

    entries: list[IndexEntry] = []
    for filename, essay in items:
        if filename in cached:
            summary, keywords = cached[filename]
        elif filename in fresh and fresh[filename][0]:
            summary, keywords = fresh[filename]
            cache.put(essay.text, summary, keywords)
        else:
            summary, keywords = heuristic_summary(essay)
            cache.put(essay.text, summary, keywords)
        entries.append(IndexEntry(filename, essay.title, summary, keywords or []))
    return entries


def heuristic_summary(essay: Essay) -> tuple[str, list[str]]:
    """Offline fallback: first sentence + frequency-ranked content keywords."""
    paragraphs = [p.strip() for p in essay.text.split("\n\n") if p.strip()]
    first = paragraphs[0] if paragraphs else essay.text.strip()
    sentence = re.split(r"(?<=[.!?])\s", first)[0] if first else ""
    summary = sentence[:160].strip()

    words = re.findall(r"[A-Za-z]{4,}", (essay.title + " " + " ".join(paragraphs[:2])).lower())
    freq: dict[str, int] = {}
    for w in words:
        if w not in _STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    keywords = sorted(freq, key=lambda w: (-freq[w], w))[:8]
    return summary, keywords


def build_summary_prompt(essay: Essay) -> str:
    """The prompt for the one-time index summary (shared by the live and batch
    paths)."""
    return (
        "Summarize this Paul Graham essay for a retrieval index. Reply EXACTLY as:\n"
        "Summary: <one sentence describing the essay's thesis>\n"
        "Keywords: <5-8 lowercase topic words, comma-separated>\n\n"
        f"Title: {essay.title}\n\n{essay.text[:6000]}"
    )


def parse_summary_response(text: str) -> tuple[str, list[str]]:
    """Parse a model summary response. Returns ('', []) if unparseable."""
    summary = ""
    keywords: list[str] = []
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("summary:"):
            summary = line.split(":", 1)[1].strip()
        elif low.startswith("keywords:"):
            keywords = [k.strip().lower() for k in line.split(":", 1)[1].split(",") if k.strip()]
    return summary, keywords


def llm_summarize(essay: Essay, client, model: str) -> tuple[str, list[str]]:
    """One-time Haiku-tier summary. Raises on any failure so the caller can fall
    back to ``heuristic_summary``."""
    resp = client.messages.create(
        model=model,
        max_tokens=200,
        messages=[{"role": "user", "content": build_summary_prompt(essay)}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    summary, keywords = parse_summary_response(text)
    if not summary:
        raise ValueError("model did not return a summary")
    return summary, keywords
