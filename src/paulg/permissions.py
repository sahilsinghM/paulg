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
# Mutating tools, permitted only inside the memory directory when one is set.
_WRITE_TOOLS = {"Write": "file_path", "Edit": "file_path"}


def _within(root: Path, target: str) -> bool:
    """True iff ``target`` resolves to ``root`` or somewhere beneath it."""
    try:
        resolved = Path(target).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    return resolved == root or resolved.is_relative_to(root)


def confine_to(
    root: Path | str,
    write_root: Path | str | None = None,
    read_tools: dict[str, str] = _READ_TOOLS,
):
    """Return an async ``can_use_tool`` callback confined to ``root``.

    Reads are allowed inside ``root`` (and inside ``write_root`` if set). Writes
    (``Write``/``Edit``) are allowed **only** inside ``write_root`` — the memory
    directory — and denied everywhere else, so the essay corpus stays read-only.
    When ``write_root`` is ``None`` the agent is fully read-only.
    """
    root_resolved = Path(root).resolve()
    write_resolved = Path(write_root).resolve() if write_root is not None else None

    async def can_use_tool(tool_name: str, tool_input: dict, context):
        if tool_name == "Skill":
            return PermissionResultAllow()

        if tool_name in read_tools:
            target = tool_input.get(read_tools[tool_name])
            if target and (
                _within(root_resolved, str(target))
                or (write_resolved and _within(write_resolved, str(target)))
            ):
                return PermissionResultAllow()
            return PermissionResultDeny(
                message=(
                    f"{tool_name} is restricted to the essay corpus at "
                    f"{root_resolved}. Provide a path inside it."
                )
            )

        if write_resolved is not None and tool_name in _WRITE_TOOLS:
            target = tool_input.get(_WRITE_TOOLS[tool_name])
            if target and _within(write_resolved, str(target)):
                return PermissionResultAllow()
            return PermissionResultDeny(
                message=(
                    f"{tool_name} is restricted to the memory directory at "
                    f"{write_resolved}. The essay corpus is read-only."
                )
            )

        return PermissionResultDeny(message=f"Tool '{tool_name}' is not permitted.")

    return can_use_tool
