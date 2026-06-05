import asyncio

import pytest

from paulg.permissions import confine_to


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def root(tmp_path):
    skill = tmp_path / "pg-essays"
    (skill / "essays").mkdir(parents=True)
    (skill / "essays" / "a.txt").write_text("startup ideas")
    return skill


def test_allows_read_inside_corpus(root):
    cb = confine_to(root)
    res = run(cb("Read", {"file_path": str(root / "essays" / "a.txt")}, None))
    assert res.behavior == "allow"


def test_denies_read_outside_corpus(root):
    cb = confine_to(root)
    res = run(cb("Read", {"file_path": "/etc/passwd"}, None))
    assert res.behavior == "deny"


def test_denies_traversal_escape(root):
    cb = confine_to(root)
    sneaky = str(root / "essays" / ".." / ".." / ".." / "etc" / "passwd")
    res = run(cb("Read", {"file_path": sneaky}, None))
    assert res.behavior == "deny"


def test_allows_grep_inside_corpus(root):
    cb = confine_to(root)
    res = run(cb("Grep", {"pattern": "startup", "path": str(root / "essays")}, None))
    assert res.behavior == "allow"


def test_denies_grep_without_explicit_path(root):
    # No path -> Grep would default to cwd (outside the corpus). Deny.
    cb = confine_to(root)
    res = run(cb("Grep", {"pattern": "startup"}, None))
    assert res.behavior == "deny"


def test_allows_skill_tool(root):
    cb = confine_to(root)
    res = run(cb("Skill", {"name": "pg-essays"}, None))
    assert res.behavior == "allow"


def test_denies_bash(root):
    cb = confine_to(root)
    res = run(cb("Bash", {"command": "cat /etc/passwd"}, None))
    assert res.behavior == "deny"


def test_denies_all_direct_writes(root):
    # The guard denies every direct write; the corpus is read-only. (Claude Code's
    # native memory writes via its own store, not through this callback.)
    cb = confine_to(root)
    assert run(cb("Write", {"file_path": str(root / "x.md")}, None)).behavior == "deny"
    assert run(cb("Write", {"file_path": str(root / "essays" / "a.txt")}, None)).behavior == "deny"
    assert run(cb("Edit", {"file_path": "/tmp/evil.sh"}, None)).behavior == "deny"
