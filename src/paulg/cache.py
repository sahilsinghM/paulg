"""Caching for fast, cheap re-crawls.

- ``cached_fetch`` is a fetch-once HTML cache: pages are saved to disk so a
  re-crawl (e.g. after an extractor fix) re-extracts offline with no re-fetch.
- ``SummaryCache`` keys Haiku summaries by a hash of the essay text, so only
  changed/new essays are re-summarized.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse


def _cache_path(url: str, cache_dir: Path) -> Path:
    name = urlparse(url).path.split("/")[-1] or "index.html"
    return cache_dir / name


def is_cached(url: str, cache_dir: Path | str) -> bool:
    """True if ``url`` already has a cached page under ``cache_dir``."""
    return _cache_path(url, Path(cache_dir)).exists()


def cached_fetch(url: str, cache_dir: Path | str, fetch_fn, refresh: bool = False) -> str:
    """Return the page for ``url``, fetching via ``fetch_fn`` only on a cache miss
    (or when ``refresh`` is set). Caches the result under ``cache_dir``."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(url, cache_dir)
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8")
    content = fetch_fn(url)
    path.write_text(content, encoding="utf-8")
    return content


class SummaryCache:
    """Content-addressed cache of (summary, keywords) keyed by a hash of the
    essay text. Persists to a JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._data: dict[str, dict] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    @staticmethod
    def _key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, text: str) -> tuple[str, list[str]] | None:
        entry = self._data.get(self._key(text))
        if entry is None:
            return None
        return entry["summary"], entry["keywords"]

    def put(self, text: str, summary: str, keywords: list[str]) -> None:
        self._data[self._key(text)] = {"summary": summary, "keywords": list(keywords)}
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data), encoding="utf-8")
