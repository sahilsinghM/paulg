# paulg — chat with Paul Graham

A conversational agent that answers **as Paul Graham**, grounded in his essays.
Built on the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python):
a thin app that loads a `pg-essays` skill and retrieves essays agentically
(`Read`/`Grep` — no vector database, no embeddings).

## How it works

```
BUILD (once):   paulgraham.com ──(tools/crawl.py)──► .claude/skills/pg-essays/essays/*.txt + INDEX.md
RUNTIME (chat): question ──► agent reads INDEX.md → reads the 1-2 best essays → answers as PG, cited
```

- **Index-then-read retrieval.** A generated `INDEX.md` (one-line thesis + keywords
  per essay) lets the agent pick the right essay(s) before reading them.
- **Confined.** The agent's file tools are restricted to the skill directory by a
  permission guard — no shell, no writes, no filesystem escape.
- **Grounded persona.** `SKILL.md` defines Paul Graham's voice and the rule to only
  assert essay-supported views.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then add your ANTHROPIC_API_KEY
```

## Build the corpus (one-time)

```bash
python tools/crawl.py       # crawls the essays + builds INDEX.md (needs the key + network)
```

The essay corpus and `INDEX.md` are **gitignored** (regenerable build artifacts —
Paul Graham's essays are copyrighted and not redistributed here). The repo ships
two clearly-synthetic *sample* essays so the app runs before you crawl.

## Chat

```bash
paulg          # or: python -m paulg.cli
```

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | required |
| `PAULG_MODEL` | `claude-sonnet-4-6` | chat model (set `claude-opus-4-8` for harder questions) |
| `PAULG_INDEX_MODEL` | `claude-haiku-4-5` | one-time essay-summary model used by the crawler |
| `PAULG_SKILL_DIR` | `.claude/skills/pg-essays` | skill location — **also the agent's confinement boundary**; point it only at the skill dir |
| `PAULG_MEMORY` | _(off)_ | set to `1` to enable cross-session memory via Claude Code's native store (see below) |

### Memory (opt-in)

By default the agent is **fully read-only** — the permission guard denies every
direct write, so the agent cannot modify the corpus or your filesystem.

`PAULG_MEMORY=1` enables the `Write`/`Edit` tools, which lets **Claude Code's
native cross-session memory** persist what it learns about you. That memory is
managed by Claude Code and stored under `~/.claude/projects/<project>/memory/` —
it is **not** governed by this app's permission guard (the guard still denies
every *direct* write the agent attempts, and the essay corpus stays read-only).
If you want memory under your app's own control instead, that's a future
enhancement; the platform owns the native-memory boundary today.

### Faster re-crawls

`tools/crawl.py` caches raw HTML under `data/html_cache/` (re-runs re-extract
offline — no re-fetch) and summaries under `data/summary_cache.json` (only
new/changed essays are re-summarized). The index pass runs through the **Message
Batches API** (50% cheaper, no per-minute rate-limit throttling). Use
`python tools/crawl.py --refresh` to force a full network re-fetch.

## Tests

```bash
pytest                 # fast deterministic unit tests
pytest -m integration  # opt-in: real-API end-to-end (needs the key + a built corpus)
```

## Layout

| Path | What |
|---|---|
| `src/paulg/extractor.py` | Essay Extractor — HTML → cleaned `{title, text}` |
| `src/paulg/essay_index.py` | INDEX.md serialization + summaries |
| `src/paulg/permissions.py` | filesystem confinement guard |
| `src/paulg/crawler.py` | one-time corpus crawler |
| `src/paulg/agent.py` | reusable `PGSession` core |
| `src/paulg/cli.py` | interactive REPL |
| `.claude/skills/pg-essays/SKILL.md` | the persona + retrieval rules |
| `docs/superpowers/specs/` | design spec |
