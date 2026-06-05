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
# is enabled — enabling writes is what lets Claude Code's native cross-session
# memory function. The corpus stays read-only regardless: the guard denies every
# direct Write/Edit tool call (native memory uses its own store, not this guard).
BASE_DISALLOWED_TOOLS = ["Bash", "WebFetch", "WebSearch"]


def build_options(config: Config, can_use_tool) -> ClaudeAgentOptions:
    """Build the SDK options for a PG chat session.

    ``can_use_tool`` is **required**: every direct tool call is gated by that
    callback (use ``confine_to(skill_dir)``), nothing is blanket-approved, and
    there is no permission-bypass path. When ``PAULG_MEMORY`` is set, Write/Edit
    are left enabled so Claude Code's native memory can persist across sessions;
    the guard still denies every direct write, so the corpus stays read-only.
    """
    if can_use_tool is None:
        raise ValueError(
            "build_options requires a can_use_tool guard — pass confine_to(skill_dir)."
        )
    disallowed = list(BASE_DISALLOWED_TOOLS)
    if not config.memory_enabled:
        disallowed += ["Write", "Edit"]
    return ClaudeAgentOptions(
        model=config.model,
        cwd=str(config.project_root),
        skills=[config.skill_name],
        system_prompt={"type": "preset", "preset": "claude_code", "append": PERSONA_SPINE},
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
        # accidentally unconfined when no guard is passed explicitly.
        if can_use_tool is None:
            can_use_tool = confine_to(config.skill_dir)
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
