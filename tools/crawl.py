#!/usr/bin/env python3
"""One-time entry point to build the Paul Graham essay corpus + index.

Usage:
    python tools/crawl.py            # uses the HTML cache (fast re-runs)
    python tools/crawl.py --refresh  # re-fetch every page from the network

Requires the project deps installed and ANTHROPIC_API_KEY set (the index pass
uses a Haiku-tier model via the Batches API). Writes into
.claude/skills/pg-essays/ and caches under data/.
"""

import argparse

from paulg.crawler import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the PG essay corpus + index.")
    parser.add_argument(
        "--refresh", action="store_true", help="re-fetch every page, ignoring the HTML cache"
    )
    args = parser.parse_args()
    main(refresh=args.refresh)
