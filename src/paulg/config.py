"""Configuration: environment loading, model defaults, and corpus paths.

A single ``load_config`` is the entry point. It fails fast with an actionable
``ConfigError`` when the Anthropic API key is missing, so both the chat runtime
and the one-time crawler give the user the same clear message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_INDEX_MODEL = "claude-haiku-4-5"
SKILL_NAME = "pg-essays"


class ConfigError(Exception):
    """Raised when configuration is missing or invalid (e.g. no API key)."""


@dataclass(frozen=True)
class Config:
    api_key: str
    model: str
    index_model: str
    skill_name: str
    project_root: Path
    skill_dir: Path
    essays_dir: Path
    index_path: Path


def load_config(base_dir: Path | None = None, use_dotenv: bool = True) -> Config:
    """Load configuration from the environment.

    ``base_dir`` is the project root containing ``.claude/skills`` (defaults to
    the current working directory). ``use_dotenv`` loads a local ``.env`` first.
    Raises ``ConfigError`` with a fix-it message if ``ANTHROPIC_API_KEY`` is unset.
    """
    if use_dotenv:
        from dotenv import load_dotenv

        load_dotenv()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to a .env file in the project "
            "root (see .env.example) or export it in your shell."
        )

    base = Path(base_dir) if base_dir is not None else Path.cwd()
    skill_dir = Path(
        os.environ.get("PAULG_SKILL_DIR", base / ".claude" / "skills" / SKILL_NAME)
    )
    essays_dir = skill_dir / "essays"

    return Config(
        api_key=api_key,
        model=os.environ.get("PAULG_MODEL", DEFAULT_MODEL),
        index_model=os.environ.get("PAULG_INDEX_MODEL", DEFAULT_INDEX_MODEL),
        skill_name=SKILL_NAME,
        project_root=base,
        skill_dir=skill_dir,
        essays_dir=essays_dir,
        index_path=skill_dir / "INDEX.md",
    )


def ensure_corpus(config: Config) -> None:
    """Raise ``ConfigError`` with a fix-it message if the essay corpus is absent."""
    if not config.essays_dir.exists() or not any(config.essays_dir.glob("*.txt")):
        raise ConfigError(
            f"No essays found at {config.essays_dir}. Build the corpus first by "
            f"running `python tools/crawl.py` (needs ANTHROPIC_API_KEY and network)."
        )
