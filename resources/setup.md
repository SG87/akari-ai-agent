# Akari Scout — API Specification

Detailed endpoint documentation for the Akari Scout AI agent backend.  
For project overview, setup, and architecture see the main [README.md](../README.md).

---

## Endpoints

### Health

#### GET /status
Checks the status of the API, loaded skills, and registered tools.

**Response:**
```json
{
    "status": "healthy",
    "skills_loaded": ["scout-analysis", "scout-core", "scout-search"],
    "tools_registered": 9,
    "data_dir_exists": true
}
```

---

### Session Management

![Akari Scout UI Mockup](akari_session_ui.png)

#### GET /sessions
Returns a paginated list of sessions for a tenant.

| Parameter | Type | Required | Default | Description |
|:---|:---|:---|:---|:---|
| `tenantId` | string | ✅ | — | Tenant identifier |
| `count` | number | — | 10 | Number of sessions per page |
| `page` | number | — | 1 | Page number |

**Response:**
```json
[
    {
        "id": "uuid",
        "label": "Session 1"
    }
]
```

#### GET /sessions/{sessionId}
Returns a session with its full message history.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `tenantId` | query string | ✅ | Tenant identifier |

**Response:**
```json
{
    "id": "uuid",
    "label": "Session 1",
    "messages": [
        {
            "persona": "user",
            "message": "Find U21 left wingers in Belgium",
            "timestamp": "2026-05-22T20:00:00Z"
        },
        {
            "persona": "assistant",
            "message": "Here are the top matches...",
            "timestamp": "2026-05-22T20:00:03Z"
        }
    ]
}
```

#### PUT /sessions
Creates a new session for a tenant.

**Request body:**
```json
{
    "tenantId": "string",
    "label": "string (optional — defaults to datetime)"
}
```

**Response:**
```json
{
    "id": "uuid"
}
```

#### DELETE /sessions/{sessionId}
Deletes a session.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `tenantId` | query string | ✅ | Tenant identifier |

**Response:**
```json
{
    "success": true
}
```

#### PATCH /sessions/{sessionId}
Updates a session's label.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `tenantId` | query string | ✅ | Tenant identifier |

**Request body:**
```json
{
    "label": "Updated Session Title"
}
```

**Response:**
```json
{
    "success": true
}
```

---

### Chat

#### POST /chat
Send a message to the Akari Scout AI agent.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `tenantId` | query string | ✅ | Tenant identifier |
| `sessionId` | query string | ✅ | Session identifier |

**Request body:**
```json
{
    "message": "Find U21 left wingers in the Belgian league under €2M",
    "timestamp": "2026-05-22T20:00:00Z"
}
```

**Response:**
```json
{
    "persona": "assistant",
    "message": "Here are the top matches from the AKARI database...",
    "timestamp": "2026-05-22T20:00:03Z",
    "metadata": {
        "model": "claude-sonnet-4-20250514",
        "tier": "STANDARD",
        "tools_called": ["search_players", "check_transfermarkt"],
        "iterations": 3,
        "usage": {
            "input_tokens": 1234,
            "output_tokens": 567
        }
    }
}
```

**Chat flow:**
1. Load session history from store
2. Classify request via router → select model + skills
3. Auto-label session on first message (if using default label)
4. Build system prompt from selected skill files
5. Run Anthropic agent loop with registered tools
6. Persist both user message and assistant response to session
7. Return response with metadata

---

## Tool Schemas

### search_players
Multi-filter player search against the AKARI database.

| Parameter | Type | Description |
|:---|:---|:---|
| `name` | string | Player name (partial match) |
| `position` | string | Position(s), comma-separated |
| `min_age` / `max_age` | integer | Age range |
| `nationality` | string | Nationality(s), comma-separated |
| `competition` | string | League name (aliases resolved automatically) |
| `area` | string | Country/market (e.g. "Croatia", "Belgium") |
| `team` | string | Team name |
| `foot` | string | `left`, `right`, or `both` |
| `season` | string | Season (e.g. "2025-2026") |
| `min_akari_skill_rescaled` | number | Minimum AKARI Skill score |
| `min_akari_potential_rescaled` | number | Minimum AKARI Potential score |
| `max_market_value` | number | Maximum market value in EUR |
| `min_games_played` | integer | Minimum games played |
| `sort_by` | string | Column to sort by (default: "AKARI Potential") |
| `limit` | integer | Max results (default: 20) |

### get_player_profile
| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `player_id` | number | ✅ | Player ID from search results |

### get_similar_players
| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `player_id` | number | ✅ | Player ID to find similar players for |
| `limit` | integer | — | Max results (default: 10) |

### get_competitions
No parameters. Returns all available competitions.

### get_stat_leaders
| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `metric` | string | ✅ | Metric to rank by |
| `position` | string | — | Filter by position |
| `competition` | string | — | Filter by competition |
| `limit` | integer | — | Max results (default: 20) |

### list_discoverable_fields / discover_values
Discovery tools for finding valid parameter values before searching.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `field` | string | ✅ | One of: `position`, `competition`, `area`, `nationality`, `season`, `foot`, `metric`, `role` |

### check_transfermarkt
**Mandatory** for every player output. Cross-references Transfermarkt for injuries, transfers, and market value.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `player_name` | string | ✅ | Full player name |
| `transfermarkt_id` | integer | — | TM player ID (faster than name search) |

### check_wyscout
Cross-references WyScout for career stats, transfer history, and contract info.

| Parameter | Type | Required | Description |
|:---|:---|:---|:---|
| `player_name` | string | ✅ | Full player name |

> Requires `WYSCOUT_USERNAME` and `WYSCOUT_PASSWORD` in environment. Returns graceful "not_configured" message when credentials are missing.
