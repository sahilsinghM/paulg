from pathlib import Path

from paulg.crawler import enumerate_essay_urls, essay_to_file_text, slug_for_url
from paulg.extractor import Essay

ARTICLES = (Path(__file__).parent / "fixtures" / "articles.html").read_text()
BASE = "http://www.paulgraham.com/"


def test_enumerate_keeps_relative_html_essays():
    urls = enumerate_essay_urls(ARTICLES, base_url=BASE)
    assert "http://www.paulgraham.com/greatwork.html" in urls
    assert "http://www.paulgraham.com/ds.html" in urls


def test_enumerate_skips_external_and_navigation_links():
    urls = enumerate_essay_urls(ARTICLES, base_url=BASE)
    assert all("ycombinator" not in u for u in urls)  # external
    assert all(not u.endswith("rss.html") for u in urls)  # feed
    assert all(not u.endswith("index.html") for u in urls)  # nav
    assert all(not u.endswith("articles.html") for u in urls)  # the index itself
    assert len(urls) == 2


def test_enumerate_deduplicates():
    doubled = ARTICLES + ARTICLES
    urls = enumerate_essay_urls(doubled, base_url=BASE)
    assert len(urls) == len(set(urls)) == 2


def test_slug_for_url():
    assert slug_for_url("http://www.paulgraham.com/greatwork.html") == "greatwork"


def test_essay_to_file_text_has_header_and_body():
    essay = Essay(title="Doing Great Work", text="Body line one.\n\nBody line two.",
                  url="http://www.paulgraham.com/greatwork.html")
    out = essay_to_file_text(essay)
    assert out.startswith("Title: Doing Great Work\n")
    assert "URL: http://www.paulgraham.com/greatwork.html" in out
    assert "Body line one." in out
    assert out.endswith("\n")  # trailing newline
