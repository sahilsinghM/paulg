"""The reusable agent core: build options and drive a persistent PG chat session.

This module has no CLI or web concerns. A terminal REPL (``cli.py``) or a future
web layer both drive ``PGSession`` the same way: ``ask(question)`` streams the
answer text chunk by chunk, and the session keeps multi-turn memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from .config import Config
from .permissions import confine_to

# Short persona spine appended to the Claude Code preset so tool-use behavior is
# preserved. The authoritative persona + grounding rules live in the skill's
# SKILL.md; this guarantees the persona applies on every turn.
PERSONA_SPINE = (
    "You are Paul Graham — the essayist, programmer, and startup investor. "
    "For every question, use the pg-essays skill: find the most relevant essays, "
    "read the one or two that matter, and answer in the first person as Paul Graham, "
    "grounded in what those essays actually say. End your answer with a 'Sources:' "
    "line naming the essay titles you drew on. If your essays do not address the "
    "topic, say so plainly in character rather than inventing a view."
)

# Always hard-disabled: shell + network. Write/Edit are added too unless memory
# is enabled (then the path guard confines writes to the memory directory).
BASE_DISALLOWED_TOOLS = ["Bash", "WebFetch", "WebSearch"]

# Appended to the system prompt only when cross-session memory is enabled.
MEMORY_SPINE = (
    "\n\nYou have a persistent memory file at memory/about_user.md. At the start "
    "of a conversation, read it to recall what you already know about this person. "
    "When you learn a durable fact about them — their projects, role, situation, or "
    "preferences — append a concise line to that file so you remember next time."
)


def build_options(config: Config, can_use_tool) -> ClaudeAgentOptions:
    """Build the SDK options for a PG chat session.

    ``can_use_tool`` is **required**: every tool call is gated by that callback
    (use ``confine_to(...)``), nothing is blanket-approved. There is intentionally
    no permission-bypass path — a session is always confined. When memory is
    enabled, Write/Edit stay enabled (the guard confines them to the memory dir);
    otherwise they're hard-disabled too.
    """
    if can_use_tool is None:
        raise ValueError(
            "build_options requires a can_use_tool guard — pass confine_to(skill_dir)."
        )
    disallowed = list(BASE_DISALLOWED_TOOLS)
    append = PERSONA_SPINE
    if config.memory_enabled:
        append += MEMORY_SPINE
    else:
        disallowed += ["Write", "Edit"]
    return ClaudeAgentOptions(
        model=config.model,
        cwd=str(config.project_root),
        skills=[config.skill_name],
        system_prompt={"type": "preset", "preset": "claude_code", "append": append},
        # Empty list: the can_use_tool callback decides every tool call. The SDK
        # still auto-injects Skill(<skill>) into allowedTools because skills=[...]
        # is set, so the Skill tool works despite the empty list (the callback
        # also explicitly allows Skill).
        allowed_tools=[],
        disallowed_tools=disallowed,
        can_use_tool=can_use_tool,
    )


class PGSession:
    """A persistent, multi-turn Paul Graham chat session."""

    def __init__(self, config: Config, can_use_tool=None) -> None:
        # Default to confining to the skill directory so a session is never
        # accidentally unconfined when no guard is passed explicitly. When memory
        # is enabled, also permit writes inside the (created) memory directory.
        if can_use_tool is None:
            write_root = None
            if config.memory_enabled:
                config.memory_dir.mkdir(parents=True, exist_ok=True)
                starter = config.memory_dir / "about_user.md"
                if not starter.exists():
                    starter.write_text("# What I know about this person\n\n", encoding="utf-8")
                write_root = config.memory_dir
            can_use_tool = confine_to(config.skill_dir, write_root=write_root)
        self._client = ClaudeSDKClient(build_options(config, can_use_tool))

    async def __aenter__(self) -> "PGSession":
        await self._client.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.disconnect()

    async def ask(self, question: str) -> AsyncIterator[str]:
        """Send a question; yield answer text chunks as they stream in."""
        await self._client.query(question)
        async for message in self._client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        yield block.text
            elif isinstance(message, ResultMessage):
                return
