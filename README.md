# wati agent

AI-powered WhatsApp Business automation assistant. Manage contacts, send messages, and orchestrate workflows through natural language.

## Quick Start

### Local

```bash
# Setup
cd wati
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run (mock API - no WATI credentials needed)
WATI_USE_MOCK_API=true python -m wati_agent

# Run (real WATI API)
python -m wati_agent
```

### Docker

```bash
# Build
docker build -t wati-agent .

# Run with mock API
docker run -it -e WATI_USE_MOCK_API=true -e LLM_MODEL=openrouter/qwen/qwen3-30b-a3b -e OPENROUTER_API_KEY=sk-or-... wati-agent

# Run with real WATI API
docker run -it --env-file .env wati-agent
```

## Configuration

All settings via `.env` or environment variables:

| Variable | Description | Default |
|---|---|---|
| `LLM_MODEL` | Primary LLM model | `openrouter/qwen/qwen3-30b-a3b` |
| `LLM_FALLBACK_MODELS` | Comma-separated fallback models | `anthropic/claude-sonnet-4-20250514,openrouter/openai/gpt-4.1` |
| `OPENROUTER_API_KEY` | OpenRouter API key | - |
| `OPENAI_API_KEY` | OpenAI API key (fallback) | - |
| `ANTHROPIC_API_KEY` | Anthropic API key (fallback) | - |
| `WATI_BASE_URL` | WATI API base URL | `https://live-mt-server.wati.io` |
| `WATI_API_TOKEN` | WATI Bearer token | - |
| `WATI_USE_MOCK_API` | Use mock instead of real API | `false` |
| `WATI_DRY_RUN_DEFAULT` | Preview actions before executing | `true` |
| `WATI_LOG_LEVEL` | Log level | `INFO` |

### Multi-LLM Support

Uses [litellm](https://docs.litellm.ai/) with automatic fallback routing:

```
Qwen3-30B-A3B → Claude Sonnet 4 → GPT-4.1
```

The primary model is [Qwen3-30B-A3B](https://qwenlm.github.io/blog/qwen3/) — a Mixture-of-Experts model with strong function calling support, multilingual capabilities, and excellent cost-effectiveness (only 3B active parameters per inference). Fallbacks to Anthropic Claude Sonnet and OpenAI GPT-4.1 ensure maximum resilience. Any model supported by litellm can be swapped via `.env` without code changes.

If the primary model fails (rate limit, timeout, error), the agent automatically tries the next provider. Zero downtime for the user.

---

## Problem Framing

The assignment asks for an AI agent that translates natural language into WATI API calls. I approached this as two distinct problems: first, understanding what the user actually wants from a free-form instruction, and second, orchestrating the right API calls in the right order to make it happen safely.

### MVP Scope

I scoped the MVP around three principles:

1. **Agent logic over UI polish**: CLI REPL instead of web UI. The intelligence is in the agent loop, not the interface.
2. **Real API compatibility**: Built against the WATI API V1 endpoints from the assignment. The architecture supports adding V3 or future API versions without changing the agent layer.
3. **Safety by default**: Dry-run mode with natural language confirmation, preview before execution. The agent explains what it will do before doing it.

### What I intentionally left out

- Web UI / frontend (CLI demonstrates the same agent logic)
- Persistent database (in-memory + JSON file sessions are sufficient for the demo)
- Webhook handling (would require a running server, out of scope for CLI demo)

---

## Architecture

### System Overview

```
User (CLI)
    → wati agent (REPL)
        → WatiAgent.handle_message()
            → ConversationMemory (session context)
            → litellm Router (LLM with fallbacks)
                → LLM decides which tools to call
                → Agent executes tools against WATI API
                → Results feed back to LLM
                → LLM decides next step or responds
            → AuditLogger (every API call recorded)
        → Response displayed to user
```

### Agentic Tool-Use Loop

The core design decision: **the LLM controls the execution flow** via native tool_use (function calling). There is no separate "planner" that generates a static plan — the LLM sees real API results and adapts.

Example flow for "Send welcome template to all VIP contacts":

1. LLM calls `get_contacts(page_size=100)` → gets 10 contacts
2. LLM filters VIP contacts from results (5 found)
3. LLM calls `get_templates()` → finds welcome_message template ID
4. LLM explains plan to user, asks confirmation
5. LLM calls `send_template_message()` × 5
6. LLM summarizes results

This is superior to a "plan then execute" approach because:
- Intermediate results inform later steps (the contact list determines who gets messages)
- The LLM handles branching naturally (0 results? tell the user instead of failing)
- Confirmation/preview is part of the conversation flow

### Project Structure

```
src/wati_agent/
├── config.py              # Pydantic Settings with env var loading
├── api/
│   ├── base.py            # WatiClient Protocol (interface)
│   ├── http.py            # BaseHttpClient (shared connection + request instrumentation)
│   ├── client.py          # V3 HTTP client (ready for production accounts)
│   ├── client_v1.py       # V1 HTTP client (primary, assignment endpoints)
│   ├── mock.py            # Mock client with seed data (10 contacts, 6 templates)
│   └── models.py          # Pydantic V2 models for all API payloads
├── agent/
│   ├── agent.py           # Agentic loop: LLM ↔ tool execution ↔ LLM
│   ├── tools.py           # 13 tool definitions (function calling format)
│   ├── prompts.py         # System prompt with behavioral rules
│   └── memory.py          # Session memory + JSON persistence
├── executor/
│   ├── __init__.py        # PlanExecutor: build, validate, execute steps with audit
│   ├── plan.py            # ActionPlan/ActionStep models with status tracking
│   ├── validator.py       # Pre-execution parameter validation
│   └── rollback.py        # Rollback manager (reverse completed steps on failure)
├── cli/
│   └── chat.py            # Rich REPL with /audit (unified timeline), /help, /dry-run
└── observability/
    ├── logging.py         # structlog (JSON in prod, console in debug)
    └── audit.py           # JSONL audit trail (per API mode) with cross-session queries
```

### Key Design Patterns

- **Protocol-based API client**: `WatiClient` is a Python Protocol (structural subtyping). `V1WatiClient` (primary), `RealWatiClient` (V3 for production), and `MockWatiClient` all implement it without inheritance. Swapping is transparent.
- **BaseHttpClient**: Shared base class for V3 and V1 clients — connection setup, teardown, and request instrumentation in one place. Zero duplication.
- **Factory with cascading health check**: On startup, tries V1 → Mock (5s timeout). V3 client code is ready for production accounts. User sees the mode in the CLI header.
- **litellm Router for LLM fallbacks**: Primary model → configurable fallbacks. Automatic retry on failure, transparent to the agent logic.

---

## AI/LLM Usage

### Why Qwen 3 + litellm + tool_use

- **Qwen3-30B-A3B** as the primary model — a MoE architecture (30B total, 3B active) with strong function calling, excellent multilingual support, and very low inference cost via OpenRouter.
- **litellm** provides a unified interface to 100+ LLM providers. The agent code doesn't know or care which provider is active — it calls `router.acompletion()` and gets tool calls back. This means anyone can run the demo with any provider.
- **Native tool_use** (function calling) instead of text parsing. The LLM returns structured JSON with tool names and parameters. No regex, no prompt-based output parsing, no fragile extraction.

### Prompt Design

The system prompt (`agent/prompts.py`) encodes 11 behavioral rules including:
- **Look up before acting** — always fetch data before operating on it
- **Duplicate send detection** — warn before re-sending the same template to the same contacts
- **Template parameter filling** — auto-fill `{{1}}`, `{{2}}` from contact data
- **Match user's language** — respond in whatever language the user writes in
- **Explain errors clearly** — don't fail silently

### Tool Design

13 tools covering the V1 API endpoints from the assignment. Each tool has:
- A clear description (the LLM reads these to decide what to call)
- Typed parameters with descriptions
- Required vs optional parameter distinction

---

## Build Notes

### Time Allocation (~5 hours total)

| Phase | Focus | Time | % |
|---|---|---|---|
| Foundation | Project structure, config, Pydantic models, Protocol, observability, architecture decisions | 70min | 23% |
| API Layer | V1 httpx client, mock client with seed data, factory cascade, Pydantic response models | 55min | 18% |
| Agent Core | 13 tool definitions, system prompt, agentic loop, conversation memory | 50min | 17% |
| Executor | PlanExecutor, validator, rollback manager, dry-run two-phase flow | 35min | 12% |
| CLI | Rich REPL, /audit (unified timeline), /dry-run toggle, commands | 25min | 8% |
| Tests | 87 tests covering all layers below the LLM | 30min | 10% |
| Polish | LLM fallback routing, session persistence, docs, code review | 35min | 12% |

### V2 Roadmap

- Full WATI API V3 integration
- Web interface with FastAPI backend and WebSocket streaming
- PostgreSQL for audit trail and session persistence
- Webhook integration for real-time conversation events

---

## Trade-offs

| Decision | Alternative | Why This Choice |
|---|---|---|
| **CLI REPL** | Web UI | I wanted to focus my time on the agent logic, not on frontend. A CLI lets me demonstrate the full loop without any UI dependencies. |
| **Qwen3 MoE via litellm** | GPT-4 / Claude direct | I chose a MoE model (30B total, 3B active) for cost-efficiency while keeping strong function calling. litellm lets me swap providers without touching agent code, so I added Claude Sonnet and GPT-4.1 as automatic fallbacks. |
| **V1 API + Mock** | V3 + V1 + Mock | I focused on V1 since those are the sandbox endpoints provided. The mock is swappable via Protocol for testing without credentials. V3 client code is ready for production but not in the startup cascade — keeping it simple for the demo. |
| **Native tool_use** | Text parsing / ReAct | Function calling gives me structured JSON with tool names and parameters. No regex parsing, no prompt fragility. litellm translates the format across providers automatically. |
| **Protocol (structural typing)** | ABC inheritance | I defined `WatiClient` as a Protocol so the V1 and Mock clients don't need to inherit anything — they just implement the same methods. Adding a V3 client later requires zero changes to the agent layer. |
| **In-memory + JSON** | SQLite / Redis | For a CLI demo, file-based persistence is sufficient. The interfaces are clean enough that swapping to a database in V2 would be straightforward. |
| **Health check on startup** | Per-request fallback | I check API availability once at startup (5s timeout) instead of risking a 30s timeout on every user request. The user sees which mode is active in the CLI header. |

---

## CLI Commands

| Command | Description |
|---|---|
| `/audit` | Unified timeline: messages + API calls for current session |
| `/audit --all` | Full audit log across all sessions (most recent first) |
| `/audit --session <id>` | Audit for a specific session |
| `/dry-run on\|off` | Toggle dry-run mode (preview before executing) |
| `/clear` | Clear conversation history |
| `/help` | Show available commands |
| `/quit` | Save session context and exit |

## API Coverage

13 tools across 7 domains, all using WATI API V1 endpoints from the assignment.

| Domain | Tool | V1 Endpoint |
|---|---|---|
| **Contacts** | `get_contacts` | `GET /api/v1/getContacts` |
| | `get_contact` | `GET /api/v1/getContactInfo/{number}` |
| | `add_contact` | `POST /api/v1/addContact/{number}` |
| | `update_contacts` | `POST /api/v1/updateContactAttributes/{number}` |
| **Tags** | `add_tag` | `POST /api/v1/addTag/{number}` |
| | `remove_tag` | `DELETE /api/v1/removeTag/{number}/{tag}` |
| **Messages** | `send_text_message` | `POST /api/v1/sendSessionMessage/{number}` |
| **Templates** | `get_templates` | `GET /api/v1/getMessageTemplates` |
| | `send_template_message` | `POST /api/v1/sendTemplateMessage/{number}` |
| **Operators** | `assign_operator` | `POST /api/v1/assignOperator/{number}` |
| | `get_operators` | `GET /api/v1/getOperators` |
| **Tickets** | `assign_ticket` | `POST /api/v1/tickets/assign` |
| **Broadcasts** | `send_broadcast_to_segment` | `POST /api/v1/sendBroadcastToSegment` |

The Protocol-based architecture supports adding V3 or future API versions without changing the agent layer. The mock client implements all 13 tools with stateful in-memory data.

## Development

```bash
make dev       # Install with dev dependencies
make run       # Run with real WATI API
make run-mock  # Run with mock API (no credentials needed)
make test      # Run tests (87 tests)
make test-cov  # Run tests with coverage report
make lint      # Ruff + mypy
make fmt       # Auto-format
make clean     # Remove caches and build artifacts
```

## Testing

```bash
pytest tests/ -v          # All tests
pytest tests/ -v --cov    # With coverage
```

Test coverage (87 tests):
- Mock API client (contacts, templates, messages, tags, tickets, operators, broadcasts)
- Mock data correctness (VIP/non-VIP segments, 5+5 split, Premium≠VIP)
- Action step validator (required params, unknown tools)
- Rollback manager (irreversible actions, status toggle)
- Tool definitions (schema validation, completeness)
- PlanExecutor (build, execute, skip, validate, endpoint resolution)
- TOOL_HTTP_MAP completeness and validity
- Audit JSONL persistence + cross-session loading
- Session memory (CRUD, trimming, save/load, accumulated context preload)
- CLI helpers (natural language intent detection)
