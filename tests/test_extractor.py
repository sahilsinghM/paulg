from pathlib import Path

from paulg.extractor import Essay, extract_essay

FIXTURE = (Path(__file__).parent / "fixtures" / "essay.html").read_text()


def test_extracts_title_from_html():
    essay = extract_essay(FIXTURE, url="http://www.paulgraham.com/greatwork.html")
    assert isinstance(essay, Essay)
    assert essay.title == "Doing Great Work"
    assert essay.url == "http://www.paulgraham.com/greatwork.html"


def test_extracts_clean_body_text():
    essay = extract_essay(FIXTURE)
    assert "First synthetic sentence about the work." in essay.text
    assert "second paragraph that should be preserved" in essay.text


def test_strips_markup_and_chrome():
    essay = extract_essay(FIXTURE)
    assert "<font" not in essay.text
    assert "<br" not in essay.text
    assert "Back to essays" not in essay.text  # navigation removed
    assert "var junk" not in essay.text  # script removed


def test_drops_title_repeated_at_top_of_body():
    essay = extract_essay(FIXTURE)
    assert not essay.text.startswith("Doing Great Work")


def test_preserves_paragraph_breaks():
    essay = extract_essay(FIXTURE)
    assert "\n\n" in essay.text


def test_text_has_no_surrounding_whitespace():
    essay = extract_essay(FIXTURE)
    assert essay.text == essay.text.strip()
