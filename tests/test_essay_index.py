from paulg.essay_index import (
    IndexEntry,
    build_index,
    format_index,
    heuristic_summary,
    parse_index,
)
from paulg.extractor import Essay

ENTRIES = [
    IndexEntry(
        filename="greatwork.txt",
        title="How to Do Great Work",
        summary="How to choose and do work that matters.",
        keywords=["ambition", "curiosity", "work"],
    ),
    IndexEntry(
        filename="ds.txt",
        title="Do Things that Don't Scale",
        summary="Why founders should do unscalable things early on.",
        keywords=["startups", "growth"],
    ),
]


def test_format_then_parse_round_trips():
    assert parse_index(format_index(ENTRIES)) == ENTRIES


def test_parse_ignores_preamble_and_blank_lines():
    md = "# Header\n\nsome preamble text\n\n" + format_index(ENTRIES).split("\n", 1)[1]
    parsed = parse_index(md)
    assert [e.filename for e in parsed] == ["greatwork.txt", "ds.txt"]


def test_parse_handles_empty_keywords():
    md = "## x.txt\n**Title:** X\n**Summary:** A thing.\n**Keywords:** \n"
    [entry] = parse_index(md)
    assert entry.keywords == []


def test_heuristic_summary_uses_first_paragraph():
    essay = Essay(
        title="On Ideas",
        text="The best ideas feel like problems. They nag you for years.\n\nSecond paragraph.",
    )
    summary, keywords = heuristic_summary(essay)
    assert "best ideas feel like problems" in summary.lower()
    assert isinstance(keywords, list) and keywords


def test_build_index_uses_summarize_when_available():
    items = [("a.txt", Essay(title="A", text="Body about startups."))]
    entries = build_index(items, summarize=lambda e: ("LLM summary", ["x", "y"]))
    assert entries[0].summary == "LLM summary"
    assert entries[0].keywords == ["x", "y"]


def test_build_index_falls_back_to_heuristic_on_error():
    items = [("a.txt", Essay(title="A", text="The body sentence here. More text."))]

    def boom(_essay):
        raise RuntimeError("api down")

    entries = build_index(items, summarize=boom)
    assert entries[0].summary  # non-empty heuristic summary
    assert "LLM" not in entries[0].summary
