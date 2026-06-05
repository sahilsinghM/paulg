"""One-time crawler: scrape paulgraham.com into the skill's essay corpus.

The pure pieces (URL enumeration, slug, file formatting) are testable in
isolation; ``fetch`` and ``crawl`` are the thin network/IO shell around the
Essay Extractor. Individual fetch/parse failures are skipped and logged so one
bad page never aborts the run.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .extractor import Essay, extract_essay

log = logging.getLogger("paulg.crawler")

BASE_URL = "http://www.paulgraham.com/"
ARTICLES_URL = urljoin(BASE_URL, "articles.html")

# Relative .html links on articles.html that are not essays.
_NON_ESSAY_NAMES = {"index.html", "articles.html", "rss.html"}


def enumerate_essay_urls(index_html: str, base_url: str = BASE_URL) -> list[str]:
    """Absolute essay URLs from the index page: relative .html links only,
    excluding navigation/feed links and external links, de-duplicated."""
    soup = BeautifulSoup(index_html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if "://" in href or href.startswith("//"):
            continue  # external / absolute
        if not href.lower().endswith(".html"):
            continue
        if href.split("/")[-1].lower() in _NON_ESSAY_NAMES:
            continue
        full = urljoin(base_url, href)
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def slug_for_url(url: str) -> str:
    name = urlparse(url).path.split("/")[-1]
    name = re.sub(r"\.html?$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[^A-Za-z0-9_-]", "-", name).strip("-").lower()
    return name or "essay"


def essay_to_file_text(essay: Essay) -> str:
    return f"Title: {essay.title}\nURL: {essay.url or ''}\n\n{essay.text}\n"


def fetch(url: str, timeout: int = 20) -> str:
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "paulg-crawler/0.1"})
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


def crawl(
    essays_dir: Path | str,
    *,
    base_url: str = BASE_URL,
    articles_url: str = ARTICLES_URL,
    delay: float = 1.0,
    limit: int | None = None,
    fetch_fn=fetch,
) -> list[tuple[Essay, Path]]:
    """Fetch every essay and write one cleaned text file per essay.

    Returns the (essay, path) pairs actually written. ``fetch_fn`` is injectable
    for testing without network access.
    """
    essays_dir = Path(essays_dir)
    essays_dir.mkdir(parents=True, exist_ok=True)

    urls = enumerate_essay_urls(fetch_fn(articles_url), base_url)
    if limit is not None:
        urls = urls[:limit]

    written: list[tuple[Essay, Path]] = []
    for url in urls:
        try:
            essay = extract_essay(fetch_fn(url), url=url)
            if not essay.text.strip():
                log.warning("empty body, skipping %s", url)
                continue
            path = essays_dir / f"{slug_for_url(url)}.txt"
            path.write_text(essay_to_file_text(essay), encoding="utf-8")
            written.append((essay, path))
            log.info("wrote %s (%s)", path.name, essay.title)
        except Exception as exc:  # noqa: BLE001 — skip+log, never abort the run
            log.warning("skipping %s: %s", url, exc)
        time.sleep(delay)

    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import anthropic

    from .config import load_config
    from .essay_index import build_index, format_index, llm_summarize

    cfg = load_config()
    written = crawl(cfg.essays_dir)

    # Build the rich INDEX.md: a one-time Haiku-tier summary per essay, with the
    # heuristic fallback handled inside build_index.
    client = anthropic.Anthropic(api_key=cfg.api_key)

    def summarize(essay):
        return llm_summarize(essay, client, cfg.index_model)

    items = [(path.name, essay) for essay, path in written]
    entries = build_index(items, summarize=summarize)
    cfg.index_path.write_text(format_index(entries), encoding="utf-8")

    print(
        f"Crawled {len(written)} essays into {cfg.essays_dir}; "
        f"wrote {len(entries)} index entries to {cfg.index_path}"
    )


if __name__ == "__main__":
    main()
