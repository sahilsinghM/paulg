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


def test_extracts_body_from_unclosed_font_tag():
    # Regression: Paul Graham's essays use UNCLOSED <font> tags, so the body
    # lives in an implicitly-open font. Mutating <br> nodes in the parsed tree
    # used to collapse that font and drop the whole essay (startupideas.txt
    # extracted 69 chars instead of ~41k). The body must survive.
    html = (
        "<html><head><title>Tricky Essay</title></head><body>"
        "<font size=2 face=verdana>Want to start a startup? Get funded.</font>"
        "<font size=2 face=verdana>\nNovember 2012<br><br>"
        "This is the real essay body that must survive extraction, with enough "
        "text to be the largest font block on the page.<br><br>"
        "A second real paragraph that also must be present in the output."
        "</body></html>"  # the second <font> is intentionally never closed
    )
    essay = extract_essay(html)
    assert "real essay body that must survive" in essay.text
    assert "second real paragraph" in essay.text
    assert "\n\n" in essay.text
