import json

from paulg.cache import SummaryCache, cached_fetch, is_cached


def test_cached_fetch_writes_on_miss_and_returns_content(tmp_path):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return "<html>essay</html>"

    out = cached_fetch("http://x/greatwork.html", tmp_path, fetch_fn=fake_fetch)
    assert out == "<html>essay</html>"
    assert calls == ["http://x/greatwork.html"]
    assert (tmp_path / "greatwork.html").exists()


def test_cached_fetch_serves_from_cache_without_refetch(tmp_path):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return "<html>essay</html>"

    cached_fetch("http://x/greatwork.html", tmp_path, fetch_fn=fake_fetch)
    out = cached_fetch("http://x/greatwork.html", tmp_path, fetch_fn=fake_fetch)
    assert out == "<html>essay</html>"
    assert calls == ["http://x/greatwork.html"]  # fetched once, second served from disk


def test_cached_fetch_refresh_bypasses_cache(tmp_path):
    calls = []

    def fake_fetch(url):
        calls.append(url)
        return f"v{len(calls)}"

    cached_fetch("http://x/a.html", tmp_path, fetch_fn=fake_fetch)
    out = cached_fetch("http://x/a.html", tmp_path, fetch_fn=fake_fetch, refresh=True)
    assert out == "v2"
    assert len(calls) == 2


def test_is_cached_reflects_disk_state(tmp_path):
    url = "http://x/greatwork.html"
    assert is_cached(url, tmp_path) is False
    cached_fetch(url, tmp_path, fetch_fn=lambda u: "<html/>")
    assert is_cached(url, tmp_path) is True


def test_summary_cache_put_get_round_trip(tmp_path):
    cache = SummaryCache(tmp_path / "summaries.json")
    assert cache.get("essay body text") is None  # miss
    cache.put("essay body text", "a summary", ["k1", "k2"])
    assert cache.get("essay body text") == ("a summary", ["k1", "k2"])


def test_summary_cache_keys_on_content(tmp_path):
    cache = SummaryCache(tmp_path / "s.json")
    cache.put("text A", "summary A", ["a"])
    assert cache.get("text B") is None  # different content -> miss
    assert cache.get("text A") == ("summary A", ["a"])


def test_summary_cache_persists_across_instances(tmp_path):
    path = tmp_path / "s.json"
    SummaryCache(path).put("body", "sum", ["k"])  # writes to disk
    reloaded = SummaryCache(path)
    assert reloaded.get("body") == ("sum", ["k"])
    # stored as JSON on disk
    assert json.loads(path.read_text())
