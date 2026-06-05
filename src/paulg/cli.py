"""Interactive terminal REPL over a PGSession."""

from __future__ import annotations

import asyncio
import sys

from .agent import PGSession
from .config import Config, ConfigError, load_config

BANNER = "Paul Graham — ask me anything about startups, ideas, and writing.\n(Ctrl-D or 'exit' to quit.)\n"


async def _chat(config: Config) -> None:
    async with PGSession(config) as session:
        while True:
            try:
                question = input("you> ").strip()
            except EOFError:
                print()
                break
            if question.lower() in {"exit", "quit"}:
                break
            if not question:
                continue
            print("pg>  ", end="", flush=True)
            async for chunk in session.ask(question):
                print(chunk, end="", flush=True)
            print("\n")


def main() -> int:
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    print(BANNER)
    try:
        asyncio.run(_chat(config))
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
