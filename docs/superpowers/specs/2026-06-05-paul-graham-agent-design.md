# Paul Graham Agent — Design

**Date:** 2026-06-05
**Status:** Approved design, pre-implementation

## Goal

A conversational agent that answers questions **as Paul Graham**, grounded in his
real essays. It must both (a) retrieve and cite his actual ideas and (b) respond
in his characteristic voice. CLI-first, with a web interface as a later phase.

## Chosen approach

A **Claude Agent SDK (Python) application that loads a custom `pg-essays` skill.**

The Agent SDK provides the agent loop (model calls, tool use, conversation state,
skill loading) so the app stays thin. The `pg-essays` skill bundles Paul Graham's
essays as plain text files plus a `SKILL.md` that defines his persona and tells the
agent how to find and cite passages. Retrieval is **agentic**: the agent uses the
built-in `read`/`grep` tools to locate relevant essays, rather than a vector
database.

### Why this over the alternatives

- **Standalone RAG app** (embeddings + Chroma) was the first design. It is
  deployable but requires a hand-built crawl→index→retrieve→generate pipeline and
  a second API key (OpenAI embeddings).
- **A bare Claude Code skill** is simpler but only runs inside Claude Code — it
  cannot be deployed as a standalone app/website.
- **Agent SDK app + skill (this design)** is the "both worlds" option: it is a
  standalone, web-deployable program AND it uses the skill mechanism. Critically,
  agentic grep/read retrieval over a small fixed corpus (~225 essays, a few MB)
  removes the entire embeddings/vector-DB layer, leaving the project *simpler*
  than the standalone RAG app and needing only one API key (Anthropic).

## Architecture

Two phases. **Build phase** runs once, offline. **Runtime** runs per question.

```
BUILD (once):
  paulgraham.com ──(crawl.py)──► skills/pg-essays/essays/*.txt + INDEX.md

RUNTIME (per question):
  question ──(cli.py → agent.py)──► Claude Agent SDK
       agent loads pg-essays skill, greps INDEX.md / essays/,
       reads matching files, answers as PG grounded in them, cites titles
     ──► streamed answer + sources
```

The build phase output (`essays/*.txt`, `INDEX.md`) is **committed** to the repo so
the app is self-contained — no crawl needed to run it.

## Project structure

```
paulg/
├── pyproject.toml              # deps: claude-agent-sdk, requests, beautifulsoup4, python-dotenv
├── .env.example                # ANTHROPIC_API_KEY=
├── .gitignore                  # .env, .venv/, __pycache__/
├── tools/
│   └── crawl.py                # one-time scraper → skill essays/ + INDEX.md
├── skills/
│   └── pg-essays/
│       ├── SKILL.md            # PG persona + retrieval/citation instructions
│       ├── INDEX.md            # generated: essay title → filename map
│       └── essays/*.txt        # one cleaned essay per file (committed)
├── src/paulg/
│   ├── config.py               # env loading, model name, paths, constants
│   ├── agent.py                # builds ClaudeAgentOptions, loads pg-essays skill (reusable core)
│   └── cli.py                  # interactive REPL over the agent
└── tests/
    └── test_agent.py           # smoke test: ask a question, assert a real essay is cited
```

`agent.py` is the reusable core. The future web app imports it unchanged and wraps
it in FastAPI; only the I/O layer (`cli.py`) is replaced.

## Components

### `tools/crawl.py` (build phase)
- Fetch the essay index (`paulgraham.com/articles.html`), enumerate essay links.
- For each essay: fetch the page, extract the title and body text from PG's
  old-style HTML (font tags, table layout), clean to readable plain text.
- Write one `essays/<slug>.txt` per essay (with a small header: title + URL).
- Write `INDEX.md` mapping essay titles → filenames for cheap lookup.
- Polite delay between requests; skip + log essays that 404 or fail to parse
  rather than aborting the whole run.

### `skills/pg-essays/SKILL.md` (the heart of the project)
Defines:
1. **Persona** — answer *as* Paul Graham, in his voice.
2. **Retrieval instructions** — consult `INDEX.md`, grep/read `essays/` for relevant
   passages before answering.
3. **Grounding/citation rules** — ground answers in retrieved passages; cite essay
   titles; say so plainly when the essays do not cover a topic (no fabrication).

### `src/paulg/agent.py` (reusable core)
- Build `ClaudeAgentOptions`: model = `claude-opus-4-8` (configurable via env),
  load the `pg-essays` skill, enable `read`/`grep` (and minimal `bash`) tools
  scoped to the skill directory, set the system prompt / persona wiring.
- Expose a function/class that takes a question (and conversation history) and
  streams the agent's response. No CLI or web concerns here.

### `src/paulg/cli.py`
- Interactive REPL: read a question, stream the agent's answer, print cited
  sources, loop. Clear startup error if `ANTHROPIC_API_KEY` is missing.

## Key decisions

| Concern | Choice | Rationale |
|---|---|---|
| Framework | Claude Agent SDK (Python, `claude-agent-sdk`) | Provides the agent loop, tool use, skill loading |
| Retrieval | Agentic `grep`/`read` over bundled essays | No embeddings/vector DB needed for a small fixed corpus; one API key |
| Skill packaging | `pg-essays/` with `SKILL.md` + `essays/*.txt` + generated `INDEX.md` | Self-contained, committed, idiomatic skill layout |
| Crawler | `requests` + `BeautifulSoup`, one-time | PG's site is static HTML; crawling is a one-off |
| Chat model | `claude-opus-4-8` (default, env-configurable) | Best stylistic mimicry; swappable to Sonnet/Haiku for cost |
| Output | Streamed to terminal + printed source list | Responsive CLI; transparent grounding |
| API keys | Anthropic only | Embeddings dropped |
| Web (later) | Reuse `agent.py`, wrap in FastAPI | Same core, different I/O |

## Error handling

- **Crawl:** skip + log failures (404, parse errors); polite inter-request delay;
  never abort the whole run for one bad essay.
- **Runtime:** clear, actionable message if `ANTHROPIC_API_KEY` is missing or the
  essays/skill are absent; surface SDK errors rather than swallowing them.

## Testing

- `tests/test_agent.py`: a smoke test that asks a representative question (e.g.
  "What does Paul Graham think about startup ideas?") and asserts the response
  references a real essay present in `essays/`. Keeps the retrieval+grounding path
  honest without over-mocking the model.

## Contribution points (learning mode)

Two decisions with real design judgment will be handed to the user to implement:

1. **`SKILL.md` persona + retrieval/citation instructions** — defines both the
   voice and how the agent grounds itself. The single most important file.
2. **Essay text extraction/cleaning in `crawl.py`** — how aggressively to strip
   PG's messy HTML and where to draw chunk/file boundaries.

## Out of scope (YAGNI)

- Vector embeddings / semantic search (can be added later as an MCP tool if grep
  retrieval proves insufficient).
- The web/FastAPI app (explicitly a later phase).
- Multi-user accounts, persistence beyond a single CLI session.

## Build sequence (high level)

1. Scaffold the Agent SDK app (official `new-sdk-app` setup) + project structure.
2. Write `crawl.py`; run it to populate `essays/` + `INDEX.md`.
3. Write `SKILL.md` (persona + retrieval rules).
4. Write `agent.py` (load skill, configure options) + `cli.py`.
5. Smoke test; verify with the Agent SDK verifier.
