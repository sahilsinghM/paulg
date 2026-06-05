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

# Read-only tools the agent may use to retrieve essays. Excludes shell/edit/network.
READ_TOOLS = ["Read", "Grep", "Glob"]


def build_options(config: Config, can_use_tool=None) -> ClaudeAgentOptions:
    """Build the SDK options for a PG chat session.

    When ``can_use_tool`` is provided (slice #4 confinement), tool calls are
    gated by that callback rather than blanket-approved, and shell/edit/network
    tools are hard-disabled. Without it (walking skeleton), the read-only tools
    are pre-approved and permissions are bypassed for a headless run.
    """
    common = dict(
        model=config.model,
        cwd=str(config.project_root),
        skills=[config.skill_name],
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": PERSONA_SPINE,
        },
    )
    if can_use_tool is not None:
        return ClaudeAgentOptions(
            **common,
            allowed_tools=[],  # let the callback decide every tool call
            disallowed_tools=["Bash", "Write", "Edit", "WebFetch", "WebSearch"],
            can_use_tool=can_use_tool,
        )
    return ClaudeAgentOptions(
        **common,
        allowed_tools=READ_TOOLS,
        permission_mode="bypassPermissions",
    )


class PGSession:
    """A persistent, multi-turn Paul Graham chat session."""

    def __init__(self, config: Config, can_use_tool=None) -> None:
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
