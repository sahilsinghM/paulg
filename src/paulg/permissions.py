"""Path Confinement: a permission guard that keeps the agent inside the corpus.

The SDK's skills feature is a context filter, not a sandbox — skill files stay
reachable via Read unless a permission callback restricts them. ``confine_to``
returns the ``can_use_tool`` callback that enforces real confinement: read tools
are allowed only for paths resolved inside the skill directory; the Skill tool is
allowed; everything else is denied.
"""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

# Read-only tools that take a path we must confine. Read uses `file_path`;
# Grep/Glob use `path`.
_READ_TOOLS = {"Read": "file_path", "Grep": "path", "Glob": "path"}


def _within(root: Path, target: str) -> bool:
    """True iff ``target`` resolves to ``root`` or somewhere beneath it."""
    try:
        resolved = Path(target).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved == root or resolved.is_relative_to(root)


def confine_to(root: Path | str, read_tools: dict[str, str] = _READ_TOOLS):
    """Return an async ``can_use_tool`` callback confined to ``root``."""
    root_resolved = Path(root).resolve()

    async def can_use_tool(tool_name: str, tool_input: dict, context):
        if tool_name == "Skill":
            return PermissionResultAllow()

        if tool_name in read_tools:
            target = tool_input.get(read_tools[tool_name])
            if target and _within(root_resolved, str(target)):
                return PermissionResultAllow()
            return PermissionResultDeny(
                message=(
                    f"{tool_name} is restricted to the essay corpus at "
                    f"{root_resolved}. Provide a path inside it."
                )
            )

        return PermissionResultDeny(message=f"Tool '{tool_name}' is not permitted.")

    return can_use_tool
