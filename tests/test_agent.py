"""Opt-in integration test: exercises the full grounding path against the real API.

Excluded from the default run (marker ``integration`` + addopts ``-m 'not
integration'``) and additionally skipped when no API key is present. Run with:

    pytest -m integration
"""

import asyncio
import os

import pytest

from paulg.agent import PGSession
from paulg.config import ensure_corpus, load_config
from paulg.essay_index import parse_index
from paulg.permissions import confine_to

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="integration test needs ANTHROPIC_API_KEY",
)
def test_answers_and_cites_a_real_essay():
    config = load_config()
    ensure_corpus(config)

    async def run() -> str:
        guard = confine_to(config.skill_dir)
        async with PGSession(config, can_use_tool=guard) as session:
            chunks = []
            async for chunk in session.ask("Where do good startup ideas come from?"):
                chunks.append(chunk)
            return "".join(chunks)

    answer = asyncio.run(run())

    assert len(answer) > 50, "expected a substantive answer"

    # The answer should be grounded: it cites a real essay from the corpus.
    real_titles = [e.title for e in parse_index(config.index_path.read_text())]
    base_titles = [t.split(" (")[0] for t in real_titles]  # drop "(sample)" suffix
    cited = any(t and t in answer for t in base_titles) or "Sources" in answer
    assert cited, "expected the answer to cite a real essay (Sources line / title)"
