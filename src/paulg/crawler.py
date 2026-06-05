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

from .cache import cached_fetch, is_cached
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
    html_cache_dir: Path | str | None = None,
    refresh: bool = False,
) -> list[tuple[Essay, Path]]:
    """Fetch every essay and write one cleaned text file per essay.

    Returns the (essay, path) pairs actually written. ``fetch_fn`` is injectable
    for testing. When ``html_cache_dir`` is set, pages are fetched once and
    re-served from disk (``refresh`` forces a re-fetch); the polite delay is
    skipped for cache hits so re-crawls after an extractor change are near-instant.
    """
    essays_dir = Path(essays_dir)
    essays_dir.mkdir(parents=True, exist_ok=True)

    def get(url: str) -> str:
        if html_cache_dir is not None:
            return cached_fetch(url, html_cache_dir, fetch_fn, refresh=refresh)
        return fetch_fn(url)

    def was_network_fetch(url: str) -> bool:
        return html_cache_dir is None or refresh or not is_cached(url, html_cache_dir)

    urls = enumerate_essay_urls(get(articles_url), base_url)
    if limit is not None:
        urls = urls[:limit]

    written: list[tuple[Essay, Path]] = []
    for url in urls:
        hit_network = was_network_fetch(url)
        try:
            essay = extract_essay(get(url), url=url)
            if not essay.text.strip():
                log.warning("empty body, skipping %s", url)
                continue
            path = essays_dir / f"{slug_for_url(url)}.txt"
            path.write_text(essay_to_file_text(essay), encoding="utf-8")
            written.append((essay, path))
            log.info("wrote %s (%s)", path.name, essay.title)
        except Exception as exc:  # noqa: BLE001 — skip+log, never abort the run
            log.warning("skipping %s: %s", url, exc)
        if hit_network:
            time.sleep(delay)  # only rate-limit real network fetches

    return written


def summarize_via_batch(missing, client, model: str) -> dict:
    """Summarize the missing (filename, essay) pairs with one Message Batches
    job. Returns {filename: (summary, keywords)}. Bypasses the per-minute rate
    limit and costs 50% less than live calls. Returns {} on any failure so the
    caller falls back to the heuristic.
    """
    if not missing:
        return {}
    import time as _time

    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    from .essay_index import build_summary_prompt, parse_summary_response

    id_to_name = {}
    requests_ = []
    for i, (filename, essay) in enumerate(missing):
        cid = f"e{i}"  # custom_id charset-safe; map back to filename
        id_to_name[cid] = filename
        requests_.append(
            Request(
                custom_id=cid,
                params=MessageCreateParamsNonStreaming(
                    model=model,
                    max_tokens=200,
                    messages=[{"role": "user", "content": build_summary_prompt(essay)}],
                ),
            )
        )

    batch = client.messages.batches.create(requests=requests_)
    log.info("submitted batch %s with %d summaries", batch.id, len(requests_))
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        _time.sleep(20)

    out: dict = {}
    for result in client.messages.batches.results(batch.id):
        if result.result.type != "succeeded":
            continue
        text = "".join(
            b.text for b in result.result.message.content if getattr(b, "type", None) == "text"
        )
        summary, keywords = parse_summary_response(text)
        if summary:
            out[id_to_name[result.custom_id]] = (summary, keywords)
    return out


def main(refresh: bool = False) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import anthropic

    from .cache import SummaryCache
    from .config import load_config
    from .essay_index import build_index_cached, format_index

    cfg = load_config()
    data_dir = cfg.project_root / "data"

    # Fetch-once HTML cache: a re-crawl after an extractor change re-extracts
    # offline. `refresh=True` re-fetches from the network.
    written = crawl(
        cfg.essays_dir,
        delay=0.5,
        html_cache_dir=data_dir / "html_cache",
        refresh=refresh,
    )

    # Index pass: only summarize cache-miss essays, and do it via the Batches API
    # (50% cheaper, bypasses the per-minute rate limit). Heuristic fallback inside
    # build_index_cached.
    client = anthropic.Anthropic(api_key=cfg.api_key)
    cache = SummaryCache(data_dir / "summary_cache.json")
    items = [(path.name, essay) for essay, path in written]
    entries = build_index_cached(
        items,
        cache,
        summarize_many=lambda missing: summarize_via_batch(missing, client, cfg.index_model),
    )
    cfg.index_path.write_text(format_index(entries), encoding="utf-8")

    print(
        f"Crawled {len(written)} essays into {cfg.essays_dir}; "
        f"wrote {len(entries)} index entries to {cfg.index_path}"
    )


if __name__ == "__main__":
    main()
