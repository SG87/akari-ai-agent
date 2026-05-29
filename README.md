# ⚽ Akari Scout AI Agent

AI-powered football scouting agent that helps clubs discover hidden gems through data-driven player analysis. Built by football and AI experts in Belgium.

![Akari Scout UI](resources/akari_session_ui.png)

## What It Does

Akari Scout is a conversational AI agent that acts as your personal data scout. Ask it to find players, compare profiles, or analyze markets — it queries the AKARI database, cross-references Transfermarkt and WyScout, and delivers structured scouting reports.

**Key capabilities:**
- 🔍 **Player Discovery** — Search by position, age, nationality, league, market value, and AKARI performance scores
- 📊 **Player Analysis** — Deep dives, head-to-head comparisons, and market monitoring
- ✅ **Transfermarkt Verification** — Automatic injury, transfer, and market value checks for every recommendation
- 🧠 **Intelligent Routing** — A fast classifier selects the optimal model per request (Haiku for simple queries, Opus for complex scouting workflows)
- 💬 **Session Management** — Multi-tenant chat sessions with persistent history
- 🔀 **Multi-Provider** — Supports Anthropic Claude and OpenAI GPT via LiteLLM

---

## Architecture

```
POST /chat  →  Router (Haiku)  →  Skills Loader  →  Agent Loop  →  Session Store
                   │                     │                │
            Selects model         Assembles system    Tool-use cycle
            + skills              prompt from .md     (max 15 iterations)
                                       files               │
                                                     ┌─────┴──────┐
                                                     │  9 Tools   │
                                                     │  AKARI DB  │
                                                     │  TMarkt    │
                                                     │  WyScout   │
                                                     └────────────┘
```

### Request Flow

1. **Router** — A fast model (Haiku) classifies the user message as `SIMPLE`, `STANDARD`, or `COMPLEX` and selects the appropriate model tier and skill files
2. **Skills Loader** — Assembles a system prompt from markdown skill files (`scout-core`, `scout-search`, `scout-analysis`)
3. **Agent Loop** — Calls the LLM via LiteLLM with tool definitions. The agent can call tools and iterate up to 15 times
4. **Session Store** — Persists user and assistant messages to the session. Auto-labels sessions on first message

### Model Tiers

| Tier | Claude | GPT | When selected |
|:---|:---|:---|:---|
| SIMPLE | Haiku | GPT-5.4-mini | Greetings, simple lookups, follow-ups |
| STANDARD | Sonnet | GPT-5.5 | Player searches, profile requests |
| COMPLEX | Opus | GPT-5.5 | Multi-step workflows, strategic analysis |

---

## Tech Stack

| Component | Technology |
|:---|:---|
| Runtime | Python 3.10+ |
| API | FastAPI + Uvicorn |
| Deployment | Azure Functions (V2 ASGI) |
| LLM Gateway | LiteLLM (Anthropic Claude, OpenAI GPT) |
| Observability | Langfuse tracing |
| Data | Azure SQL (pyodbc) — AKARI Algorithm |
| External APIs | Transfermarkt (scraping), WyScout API v3 |

---

## Quick Start

### Prerequisites

- Python 3.10+
- Azure SQL database with AKARI data loaded
- Anthropic API key (required) and/or OpenAI API key

### Installation

```bash
# Clone and enter the project
git clone <repo-url>
cd akari-ai-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

At minimum, set `ANTHROPIC_API_KEY` and the database credentials (`DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`).

See the full [Configuration Reference](#configuration-reference) below.

### Running Locally

**Option 1 — Uvicorn (development)**
```bash
uvicorn app.main:app --reload --port 8000
```

**Option 2 — Azure Functions Core Tools**
```bash
func start
# App available at http://localhost:7071
```

- **Swagger docs**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/status

### Deploy to Azure

```bash
func azure functionapp publish akari-ai-agent --subscription eb471083-9c71-4d32-b8ca-b9411ae0b095
```

> See [Deployment (Azure Functions)](#deployment-azure-functions) for full setup instructions.

---

## Deployment (Azure Functions)

The app is deployed to **Azure Functions** (Linux consumption plan, Python 3.11) using the V2 ASGI integration. The FastAPI app runs unchanged inside the Azure Functions runtime via `function_app.py`.

**Production URL:** `https://akari-ai-agent.azurewebsites.net`

| Endpoint | URL |
|:---|:---|
| Health | https://akari-ai-agent.azurewebsites.net/status |
| Swagger docs | https://akari-ai-agent.azurewebsites.net/docs |
| Chat | https://akari-ai-agent.azurewebsites.net/chat |
| Sessions | https://akari-ai-agent.azurewebsites.net/sessions |

### Azure Resources

| Resource | Value |
|:---|:---|
| Subscription | `AKARI_Subscription` |
| Resource Group | `AKARI` |
| Function App | `akari-ai-agent` |
| Storage Account | `akaristorage1` |
| Region | West Europe |

### Deploy

```bash
# Ensure you're on the Akari subscription
az account set --subscription AKARI_Subscription

# Deploy (use --subscription flag if func CLI doesn't detect the app)
func azure functionapp publish akari-ai-agent

# If that gives "Can't find app", use the explicit subscription ID:
func azure functionapp publish akari-ai-agent \
  --subscription eb471083-9c71-4d32-b8ca-b9411ae0b095
```

### Update Environment Variables

```bash
az functionapp config appsettings set \
  --name akari-ai-agent \
  --resource-group AKARI \
  --settings \
    ANTHROPIC_API_KEY="..." \
    ROUTER_MODEL="anthropic/claude-haiku-4-5" \
    CLAUDE_SIMPLE_MODEL="anthropic/claude-haiku-4-5" \
    CLAUDE_STANDARD_MODEL="anthropic/claude-sonnet-4-6" \
    CLAUDE_COMPLEX_MODEL="anthropic/claude-opus-4-6" \
    DB_SERVER="..." \
    DB_NAME="..." \
    DB_USER="..." \
    DB_PASSWORD="..."
```

### Create from Scratch

If you need to recreate the Function App:

```bash
az functionapp create \
  --resource-group AKARI \
  --consumption-plan-location westeurope \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --name akari-ai-agent \
  --storage-account akaristorage1 \
  --os-type Linux

# Required for V2 Python worker model
az functionapp config appsettings set \
  --name akari-ai-agent \
  --resource-group AKARI \
  --settings AzureWebJobsFeatureFlags=EnableWorkerIndexing
```

### Known Constraints

- **pyodbc / ODBC Driver**: The Azure Functions Linux consumption plan does not include the ODBC Driver 18 for SQL Server. The `pyodbc` import is deferred (lazy) in `database.py` so the app starts regardless — it will connect if the driver is available, or log a warning and continue without database features.
- **Cold starts**: The consumption plan may take 10–30 seconds to cold-start. The first request after inactivity will be slow.
- **In-memory sessions**: The `InMemorySessionStore` does not persist across function invocations. For production, swap it with a persistent backend (Cosmos DB, Redis, Azure SQL).

---

## API Reference

All endpoints require an `X-API-Key` header (when `API_KEY` is configured). All responses use **camelCase** field names.

### Health

| Method | Endpoint | Description |
|:---|:---|:---|
| `GET` | `/status` | Health check |

**Response:**
```json
{
  "status": "healthy",
  "skillsLoaded": ["scout-analysis", "scout-core", "scout-search"],
  "toolsRegistered": 9,
  "databaseConnected": true
}
```

---

### Sessions

| Method | Endpoint | Query Params | Description |
|:---|:---|:---|:---|
| `GET` | `/sessions` | `tenantId`, `userId`, `count?`, `page?` | List sessions |
| `GET` | `/sessions/{sessionId}` | `tenantId`, `userId` | Get session with messages |
| `PUT` | `/sessions` | — | Create a new session |
| `DELETE` | `/sessions/{sessionId}` | `tenantId`, `userId` | Delete a session |
| `PATCH` | `/sessions/{sessionId}` | `tenantId`, `userId` | Update session label |

#### `PUT /sessions` — Create session

**Request body:**
```json
{
  "tenantId": "club-123",
  "userId": "user-456",
  "label": "Scouting U21 wingers"
}
```

**Response:**
```json
{
  "sessionId": "7f72252b-acad-4893-906d-077759c336d3"
}
```

#### `GET /sessions` — List sessions

**Response:**
```json
[
  {
    "sessionId": "7f72252b-...",
    "tenantId": "club-123",
    "userId": "user-456",
    "label": "Scouting U21 wingers",
    "messageCount": 4,
    "createdAt": "2026-05-29T10:00:00Z",
    "updatedAt": "2026-05-29T10:15:00Z"
  }
]
```

#### `GET /sessions/{sessionId}` — Get session with messages

**Response:**
```json
{
  "sessionId": "7f72252b-...",
  "tenantId": "club-123",
  "userId": "user-456",
  "label": "Scouting U21 wingers",
  "messages": [
    {
      "persona": "user",
      "message": "Find me young wingers in Eredivisie",
      "timestamp": "2026-05-29T10:00:00Z",
      "metadata": null
    },
    {
      "persona": "assistant",
      "message": "Here are the top U21 wingers...",
      "timestamp": "2026-05-29T10:00:12Z",
      "metadata": {
        "model": "anthropic/claude-sonnet-4-6",
        "provider": "claude",
        "tier": "STANDARD",
        "toolsCalled": ["search_players"],
        "iterations": 2,
        "usage": {
          "inputTokens": 4200,
          "outputTokens": 850
        }
      }
    }
  ]
}
```

---

### Chat

| Method | Endpoint | Query Params | Description |
|:---|:---|:---|:---|
| `POST` | `/chat` | `tenantId`, `userId`, `sessionId?`, `provider?` | Send a message |

- **`sessionId`** is optional — if omitted, a new session is created automatically
- **`provider`** is optional — defaults to `claude`. Accepts `claude` or `gpt`

**Request body:**
```json
{
  "message": "Find me centre backs aged 20-23 in the Bundesliga with high AKARI Potential"
}
```

**Response:**
```json
{
  "sessionId": "7f72252b-...",
  "persona": "assistant",
  "message": "Here are the top centre backs...",
  "timestamp": "2026-05-29T10:00:12Z",
  "metadata": {
    "model": "anthropic/claude-sonnet-4-6",
    "provider": "claude",
    "tier": "STANDARD",
    "toolsCalled": ["search_players", "check_transfermarkt"],
    "iterations": 3,
    "usage": {
      "inputTokens": 5100,
      "outputTokens": 1200,
      "cacheReadInputTokens": 3800,
      "cacheCreationInputTokens": 0
    }
  }
}
```

---

## Tools (9 registered)

| Tool | Source | Description |
|:---|:---|:---|
| `search_players` | AKARI DB | Multi-filter player search (position, age, nationality, league, AKARI scores) |
| `get_player_profile` | AKARI DB | Full player profile by Player ID across all seasons |
| `get_similar_players` | AKARI DB | Find similar players using the AKARI Similarity Algorithm |
| `get_competitions` | AKARI DB | List all available competitions |
| `get_stat_leaders` | AKARI DB | Top players by any statistical metric |
| `list_discoverable_fields` | AKARI DB | List filter parameters that support value discovery |
| `discover_values` | AKARI DB | Get valid values for a specific filter (positions, leagues, etc.) |
| `check_transfermarkt` | Transfermarkt | Player injuries, transfers, market value, and contract info |
| `check_wyscout` | WyScout | Career stats and contract information from WyScout API |

---

## Project Structure

```
akari-ai-agent/
├── function_app.py           Azure Functions entry point (ASGI wrapper)
├── host.json                 Azure Functions host config
├── local.settings.json       Local dev settings for func start
├── .funcignore               Deployment exclusion list
├── requirements.txt          Python dependencies
├── .env                      Environment variables (local only)
│
├── skills/
│   ├── scout-core.md         Base persona & guardrails (always loaded)
│   ├── scout-search.md       Player search workflow
│   └── scout-analysis.md     Player analysis & market intelligence
│
├── sql/
│   ├── create_tables.sql     SQL table/view definitions
│   └── ...
│
├── resources/
│   ├── setup.md              Detailed API specification
│   └── akari_session_ui.png  UI screenshot
│
└── app/
    ├── main.py               FastAPI app & routes
    ├── config.py             Settings (pydantic-settings, .env)
    ├── models.py             Pydantic models (camelCase serialization)
    ├── router.py             Haiku-based request classifier
    ├── agent.py              Tool-use agent loop dispatcher
    ├── skills.py             Skill file loader
    ├── session_store.py      In-memory session store (swappable)
    ├── database.py           Azure SQL connection & queries
    │
    ├── providers/
    │   ├── base.py           AgentResponse dataclass
    │   └── litellm_provider.py  LiteLLM agent loop (with Anthropic caching)
    │
    └── tools/
        ├── registry.py       Tool registry & dispatch
        ├── akari_search.py   AKARI DB tools (7 tools)
        ├── transfermarkt.py  Transfermarkt scraper
        └── wyscout.py        WyScout API client
```

---

## Configuration Reference

| Variable | Required | Description |
|:---|:---|:---|
| **Auth** | | |
| `API_KEY` | — | API key for `X-API-Key` header authentication. If unset, all requests are allowed |
| **LLM Keys** | | |
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API key |
| `OPENAI_API_KEY` | — | OpenAI API key (required for GPT provider) |
| **Router** | | |
| `ROUTER_MODEL` | ✅ | LiteLLM model string for request classification (e.g. `anthropic/claude-haiku-4-5`) |
| **Claude Models** | | |
| `CLAUDE_SIMPLE_MODEL` | ✅ | Claude model for SIMPLE tier (e.g. `anthropic/claude-haiku-4-5`) |
| `CLAUDE_STANDARD_MODEL` | ✅ | Claude model for STANDARD tier (e.g. `anthropic/claude-sonnet-4-6`) |
| `CLAUDE_COMPLEX_MODEL` | ✅ | Claude model for COMPLEX tier (e.g. `anthropic/claude-opus-4-6`) |
| **GPT Models** | | |
| `GPT_SIMPLE_MODEL` | ✅ | GPT model for SIMPLE tier |
| `GPT_STANDARD_MODEL` | ✅ | GPT model for STANDARD tier |
| `GPT_COMPLEX_MODEL` | ✅ | GPT model for COMPLEX tier |
| **Database** | | |
| `DB_SERVER` | ✅ | Azure SQL server hostname |
| `DB_NAME` | ✅ | Database name |
| `DB_USER` | ✅ | Database user |
| `DB_PASSWORD` | ✅ | Database password |
| **Langfuse** | | |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse public key (enables tracing) |
| `LANGFUSE_SECRET_KEY` | — | Langfuse secret key |
| `LANGFUSE_HOST` | — | Langfuse host (e.g. `https://cloud.langfuse.com`) |
| **WyScout** | | |
| `WYSCOUT_USERNAME` | — | WyScout API username |
| `WYSCOUT_PASSWORD` | — | WyScout API password |

---

## Prompt Caching

For Anthropic models, the agent loop places cache-control breakpoints on:
1. **System prompt** — large, identical for the same skill set
2. **Last tool definition** — stable across all requests

Cached input tokens are billed at ~10% of normal cost. On multi-turn agent loops this typically saves **50–90%** of input costs because the system prompt + tools prefix is resent verbatim every iteration. Cache stats (`cacheReadInputTokens`, `cacheCreationInputTokens`) are included in the response metadata.

---

## License

Proprietary — Akari Analytics © 2026
