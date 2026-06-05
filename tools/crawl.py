#!/usr/bin/env python3
"""One-time entry point to build the Paul Graham essay corpus + index.

Usage:
    python tools/crawl.py

Requires the project deps installed and ANTHROPIC_API_KEY set (the index pass
uses a Haiku-tier model). Writes into .claude/skills/pg-essays/.
"""

from paulg.crawler import main

if __name__ == "__main__":
    main()
