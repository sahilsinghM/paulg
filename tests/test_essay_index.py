from paulg.cache import SummaryCache
from paulg.essay_index import (
    IndexEntry,
    build_index,
    build_index_cached,
    build_summary_prompt,
    format_index,
    heuristic_summary,
    parse_index,
    parse_summary_response,
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


def test_build_summary_prompt_includes_title_and_body():
    essay = Essay(title="How to Do Great Work", text="Some essay body about ambition.")
    prompt = build_summary_prompt(essay)
    assert "How to Do Great Work" in prompt
    assert "ambition" in prompt
    assert "Summary:" in prompt and "Keywords:" in prompt  # the response format


def test_parse_summary_response_well_formed():
    text = "Summary: Great work needs curiosity.\nKeywords: work, curiosity, ambition"
    summary, keywords = parse_summary_response(text)
    assert summary == "Great work needs curiosity."
    assert keywords == ["work", "curiosity", "ambition"]


def test_parse_summary_response_is_label_case_insensitive_and_tolerates_missing_keywords():
    summary, keywords = parse_summary_response("SUMMARY: A thesis.")
    assert summary == "A thesis."
    assert keywords == []


def test_parse_summary_response_garbage_returns_empty():
    summary, keywords = parse_summary_response("no labels here at all")
    assert summary == ""
    assert keywords == []


def test_build_index_cached_uses_cache_hits_without_summarizing(tmp_path):
    cache = SummaryCache(tmp_path / "c.json")
    essay = Essay(title="A", text="body text")
    cache.put(essay.text, "cached summary", ["k"])
    calls = []

    def summarize_many(missing):
        calls.append(missing)
        return {}

    entries = build_index_cached([("a.txt", essay)], cache, summarize_many=summarize_many)
    assert entries[0].summary == "cached summary"
    assert calls == []  # cache hit -> no summarization


def test_build_index_cached_summarizes_misses_and_caches(tmp_path):
    cache = SummaryCache(tmp_path / "c.json")
    essay = Essay(title="A", text="fresh body")

    def summarize_many(missing):
        return {fn: ("batch summary", ["b"]) for fn, _ in missing}

    entries = build_index_cached([("a.txt", essay)], cache, summarize_many=summarize_many)
    assert entries[0].summary == "batch summary"
    assert cache.get(essay.text) == ("batch summary", ["b"])  # now persisted


def test_build_index_cached_heuristic_when_summarizer_omits(tmp_path):
    cache = SummaryCache(tmp_path / "c.json")
    essay = Essay(title="A", text="The first sentence here. And a second.")
    entries = build_index_cached([("a.txt", essay)], cache, summarize_many=lambda m: {})
    assert entries[0].summary  # heuristic fallback, non-empty
    assert "first sentence here" in entries[0].summary.lower()
