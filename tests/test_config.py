import pytest

from paulg.config import Config, ConfigError, ensure_corpus, load_config


def test_missing_api_key_raises_actionable_error(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Avoid picking up a real .env on disk.
    with pytest.raises(ConfigError) as exc:
        load_config(base_dir=tmp_path, use_dotenv=False)
    message = str(exc.value)
    assert "ANTHROPIC_API_KEY" in message
    assert ".env" in message  # tells the user how to fix it


def test_load_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("PAULG_MODEL", raising=False)
    monkeypatch.delenv("PAULG_INDEX_MODEL", raising=False)
    cfg = load_config(base_dir=tmp_path, use_dotenv=False)
    assert isinstance(cfg, Config)
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.index_model == "claude-haiku-4-5"
    assert cfg.skill_name == "pg-essays"
    assert cfg.essays_dir == cfg.skill_dir / "essays"


def test_model_override_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PAULG_MODEL", "claude-opus-4-8")
    cfg = load_config(base_dir=tmp_path, use_dotenv=False)
    assert cfg.model == "claude-opus-4-8"


def test_memory_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("PAULG_MEMORY", raising=False)
    cfg = load_config(base_dir=tmp_path, use_dotenv=False)
    assert cfg.memory_enabled is False


def test_memory_enabled_via_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("PAULG_MEMORY", "1")
    cfg = load_config(base_dir=tmp_path, use_dotenv=False)
    assert cfg.memory_enabled is True


def test_ensure_corpus_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    cfg = load_config(base_dir=tmp_path, use_dotenv=False)
    with pytest.raises(ConfigError) as exc:
        ensure_corpus(cfg)
    assert "crawl" in str(exc.value)


def test_ensure_corpus_passes_when_essays_present(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    cfg = load_config(base_dir=tmp_path, use_dotenv=False)
    cfg.essays_dir.mkdir(parents=True)
    (cfg.essays_dir / "a.txt").write_text("Title: A\nURL: x\n\nbody")
    ensure_corpus(cfg)  # must not raise
