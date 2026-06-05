# Paul Graham Agent — Design

**Date:** 2026-06-05
**Status:** Approved design (grilled), pre-implementation

## Goal

A conversational agent that answers questions **as Paul Graham**, grounded in his
real essays. It must both (a) retrieve and cite his actual ideas and (b) respond
in his characteristic voice. CLI-first, with a web interface as a later phase.

## Chosen approach

A **Claude Agent SDK (Python) application that loads a custom `pg-essays` skill.**

The Agent SDK (`claude-agent-sdk`) provides the agent loop (model calls, tool use,
conversation state, skill loading) so the app stays thin. The `pg-essays` skill
bundles Paul Graham's essays as plain text files plus a `SKILL.md` defining his
persona and how to find/cite passages. Retrieval is **agentic** — the agent uses
the built-in `Read`/`Grep` tools — with **no vector database or embeddings**.

### Why this over the alternatives

- **Standalone RAG app** (embeddings + Chroma): deployable but needs a hand-built
  index/retrieve pipeline and a second API key (OpenAI). Heavier.
- **Bare Claude Code skill**: simplest, but only runs inside Claude Code — not
  deployable as a standalone app/website.
- **Agent SDK app + skill (this design)**: standalone AND uses the skill
  mechanism. Agentic grep/read over a small fixed corpus (~225 essays) removes the
  embeddings layer, leaving the project simpler than the RAG app with only one API
  key (Anthropic). Verified: `claude-agent-sdk` supports filesystem skills as a
  first-class `ClaudeAgentOptions(skills=[...])` feature.

## Architecture

Two phases. **Build phase** runs once, offline. **Runtime** runs per question.

```
BUILD (once):
  paulgraham.com ──(crawl.py)──► .claude/skills/pg-essays/essays/*.txt
                                 + .claude/skills/pg-essays/INDEX.md (Haiku-generated)

RUNTIME (per question, persistent session):
  question ──(cli.py → agent.py: ClaudeSDKClient)──►
       agent loads pg-essays skill, greps INDEX.md → picks ≤2 best essays,
       reads those files, answers as PG grounded in them, cites titles
     ──► streamed answer + sources
```

Build outputs (`essays/*.txt`, `INDEX.md`) are **gitignored** — regenerable build
artifacts, not committed (copyright; keeps repo public-safe). The repo ships
`crawl.py`; one `python tools/crawl.py` populates them locally.

## Project structure

```
paulg/
├── pyproject.toml              # deps: claude-agent-sdk, requests, beautifulsoup4, python-dotenv, anthropic
├── .env.example                # ANTHROPIC_API_KEY=
├── .gitignore                  # .env, .venv/, __pycache__/, .claude/skills/pg-essays/essays/, .../INDEX.md
├── tools/
│   └── crawl.py                # one-time: scrape essays + Haiku-generate INDEX.md
├── .claude/skills/pg-essays/
│   ├── SKILL.md                # name: pg-essays; PG persona + retrieval/citation rules (USER CONTRIBUTION)
│   ├── INDEX.md                # generated: per essay → filename, 1-line thesis, keywords (gitignored)
│   └── essays/*.txt            # one cleaned essay per file (gitignored)
├── src/paulg/
│   ├── config.py               # env, MODEL (claude-sonnet-4-6), INDEX_MODEL (claude-haiku-4-5), paths
│   ├── permissions.py          # confine_to(dir) → can_use_tool callback (Read/Grep path guard)
│   ├── agent.py                # builds ClaudeAgentOptions, persistent ClaudeSDKClient session (reusable core)
│   └── cli.py                  # interactive REPL over the agent session
└── tests/
    ├── fixtures/essay.html     # saved real PG essay page for deterministic parse tests
    ├── test_crawl.py           # unit: HTML → clean text + title
    ├── test_permissions.py     # unit: confinement callback denies outside / allows inside essays/
    └── test_agent.py           # integration (opt-in, real API): asks a question, asserts a real essay cited
```

`agent.py` is the reusable core. The future web app imports it unchanged and wraps
it in FastAPI; only the I/O layer (`cli.py`) is replaced.

## Components

### `tools/crawl.py` (build phase)
- Fetch `paulgraham.com/articles.html`; enumerate essay links; skip non-essay links
  (RSS, FAQ, external), logging what's skipped.
- For each essay: fetch, extract title + body from PG's old-style HTML (font tags,
  table layout), clean to readable plain text. Write `essays/<slug>.txt` with a
  small header (title + URL).
- **Generate `INDEX.md`**: one `claude-haiku-4-5` call per essay → a one-line thesis
  summary + 5–8 keywords. Sequential (simpler than Batches for a one-off). On a
  failed/refused call, fall back to a heuristic (title + first paragraph).
- Polite delay between fetches; skip + log failures rather than aborting the run.
- Needs `ANTHROPIC_API_KEY` (for the Haiku index pass).

### `.claude/skills/pg-essays/SKILL.md` (the heart — user contribution)
Frontmatter `name: pg-essays` + a description that triggers it. Body defines:
1. **Persona** — answer in first person *as* Paul Graham, in his voice.
2. **Retrieval** — consult `INDEX.md`, pick ≤2 most-relevant essays, `Read` them
   before answering (index-then-targeted-read).
3. **Grounding discipline** — only assert views the essays support; when a topic
   isn't covered, say so *in character* ("I haven't really written about that,
   but…") rather than fabricate. Cite essay titles.

### `src/paulg/permissions.py`
- `confine_to(essays_dir)` returns a `can_use_tool` callback that allows `Read`/
  `Grep` only for paths inside `essays_dir`/the skill dir and denies everything
  else (`PermissionResultDeny`). Pure, unit-tested. Necessary because the SDK
  `skills` feature is a context filter, not a sandbox — files remain reachable via
  `Read` unless a permission callback restricts them.

### `src/paulg/agent.py` (reusable core)
- Build `ClaudeAgentOptions(model=config.MODEL, skills=["pg-essays"],
  allowed_tools=["Read", "Grep"], can_use_tool=confine_to(ESSAYS_DIR),
  system_prompt=…, setting_sources=["project"])`.
- Expose a persistent **`ClaudeSDKClient`** session object: send a question, stream
  the response, retain multi-turn memory. No CLI/web concerns here.

### `src/paulg/cli.py`
- Interactive REPL over the session: read question → stream answer → print cited
  sources → loop. Clear startup error if `ANTHROPIC_API_KEY` is missing or the
  skill/essays are absent (tells the user to run the crawler).

## Key decisions (post-grill)

| Concern | Choice | Rationale |
|---|---|---|
| Framework | Claude Agent SDK (Python, `claude-agent-sdk`) | Agent loop, tool use, first-class skills |
| Retrieval | Index-then-targeted-read, ≤2 essays/turn | Best grounding per token; bounds context/cost |
| Index build | Haiku one-line summary + keywords per essay, one-time | Strong retrieval signal; heuristic fallback |
| Persona | First-person, grounding-disciplined | Immersive yet honest; clean public-deploy story |
| Essay rights | Gitignore essays + INDEX.md; ship crawler | No redistribution; repo stays public-safe/lean |
| Tools | `Read` + `Grep` only, dir-confined via `can_use_tool` | Minimal attack surface for the web phase |
| Skill location | `.claude/skills/pg-essays/`, `name: pg-essays` | Project setting source; SDK auto-discovers |
| Conversation | Persistent `ClaudeSDKClient` session | Multi-turn memory; right shape for REPL + web |
| Chat model | `claude-sonnet-4-6` (default, env-swappable to Opus) | Strong voice mimicry, cheaper/snappier for chat |
| Index model | `claude-haiku-4-5` | Cheapest for the one-time index pass |
| API keys | Anthropic only | Embeddings dropped |
| Web (later) | Reuse `agent.py`, wrap in FastAPI | Same core, different I/O |

## Error handling

- **Crawl:** skip + log failures (404, parse errors, Haiku refusals → heuristic
  fallback); polite inter-request delay; never abort the run for one bad essay.
- **Runtime:** clear, actionable message if `ANTHROPIC_API_KEY` is missing or the
  skill/essays are absent (point the user at `tools/crawl.py`); surface SDK errors.

## Testing (split: CI unit + opt-in integration)

- **Unit (deterministic, no API, run in CI):**
  - `test_crawl.py` — HTML extraction against a saved real-essay fixture → clean
    text + correct title.
  - `test_permissions.py` — the `can_use_tool` confinement callback denies a path
    outside `essays/` and allows one inside. *(Security-critical, highest value.)*
  - index format/parsing.
- **Integration (real API, opt-in via marker/env, manual/pre-release):**
  - `test_agent.py` — ask a representative question; assert the response cites a
    real essay present in `essays/`.

## Contribution points (learning mode)

1. **`SKILL.md` persona + retrieval/citation rules** — defines voice *and*
   grounding. The single most important file.
2. **Essay text extraction/cleaning in `crawl.py`** — how aggressively to strip
   PG's messy HTML and where to draw file boundaries.

## Out of scope (YAGNI)

- Vector embeddings / semantic search (addable later as an MCP tool if grep
  retrieval proves insufficient).
- The web/FastAPI app (explicit later phase). Note: serving full essay text
  publicly will need a rights review at that point.
- Multi-user accounts; persistence beyond a single session.

## Build sequence (high level)

1. Scaffold the Agent SDK app (official `new-sdk-app` setup) + project structure.
2. Write `crawl.py`; run it to populate `essays/` + Haiku `INDEX.md`.
3. Write `SKILL.md` (persona + retrieval rules — user contribution).
4. Write `permissions.py`, `agent.py`, `cli.py`.
5. Unit tests (crawl fixture, confinement, index format); opt-in integration smoke.
6. Verify with the Agent SDK verifier.
