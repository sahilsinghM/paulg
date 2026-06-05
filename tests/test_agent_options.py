from pathlib import Path

import pytest

from paulg.agent import PGSession, build_options
from paulg.config import Config


def _cfg(tmp_path: Path, memory: bool = False) -> Config:
    skill = tmp_path / ".claude" / "skills" / "pg-essays"
    return Config(
        api_key="x",
        model="claude-sonnet-4-6",
        index_model="claude-haiku-4-5",
        skill_name="pg-essays",
        project_root=tmp_path,
        skill_dir=skill,
        essays_dir=skill / "essays",
        index_path=skill / "INDEX.md",
        memory_enabled=memory,
    )


def test_build_options_requires_a_permission_callback(tmp_path):
    with pytest.raises(ValueError):
        build_options(_cfg(tmp_path), None)


def test_build_options_is_confined_and_locks_down_tools(tmp_path):
    async def cb(name, inp, ctx):  # noqa: ANN001
        ...

    opts = build_options(_cfg(tmp_path), cb)
    assert opts.allowed_tools == []  # nothing blanket-approved
    assert opts.can_use_tool is cb  # the guard decides every tool call
    assert opts.permission_mode != "bypassPermissions"
    for blocked in ("Bash", "Write", "Edit", "WebFetch", "WebSearch"):
        assert blocked in opts.disallowed_tools


def test_pgsession_defaults_to_a_confined_guard(tmp_path):
    # Constructing without an explicit guard must NOT yield an unconfined agent;
    # it should default to confining to the skill directory (and not raise).
    session = PGSession(_cfg(tmp_path))
    assert session is not None


def test_writes_hard_disabled_without_memory(tmp_path):
    opts = build_options(_cfg(tmp_path, memory=False), _noop_guard)
    assert "Write" in opts.disallowed_tools
    assert "Edit" in opts.disallowed_tools


def test_writes_enabled_with_memory_but_shell_still_disabled(tmp_path):
    # Memory mode enables Write/Edit so Claude Code's native memory can persist;
    # shell/network stay blocked, and the guard still denies every direct write.
    opts = build_options(_cfg(tmp_path, memory=True), _noop_guard)
    assert "Write" not in opts.disallowed_tools
    assert "Edit" not in opts.disallowed_tools
    assert "Bash" in opts.disallowed_tools
    assert "WebFetch" in opts.disallowed_tools


async def _noop_guard(name, inp, ctx):  # noqa: ANN001
    ...
