"""
Tool registry — central registration and dispatch for all agent tools.

Provides Anthropic-format tool schemas and executes tool calls by name.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.tools import akari_search, transfermarkt, wyscout

logger = logging.getLogger("akari.tools")


@dataclass
class ToolDefinition:
    """A registered tool with its Anthropic schema and handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable
    is_async: bool = False


# ── Global registry ────────────────────────────────────────────────────────

_TOOLS: dict[str, ToolDefinition] = {}


def _register(tool: ToolDefinition) -> None:
    """Register a tool definition."""
    _TOOLS[tool.name] = tool


def get_all_tools() -> list[dict[str, Any]]:
    """Return all tool schemas in Anthropic format."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in _TOOLS.values()
    ]


async def execute_tool(name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool by name with the given input. Returns JSON string."""
    tool = _TOOLS.get(name)
    if not tool:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        logger.info("TOOL_CALL | name=%s | input_keys=%s", name, list(tool_input.keys()))
        if tool.is_async:
            result = await tool.handler(**tool_input)
        else:
            result = tool.handler(**tool_input)
        return result
    except Exception as e:
        logger.error("TOOL_ERROR | name=%s | error=%s", name, str(e))
        return json.dumps({"error": f"Tool '{name}' failed: {str(e)}"})


# ── Register all tools ─────────────────────────────────────────────────────

def _init_tools() -> None:
    """Register all available tools."""

    # ── AKARI Search Tools ──────────────────────────────────────────────

    _register(ToolDefinition(
        name="search_players",
        description=(
            "Search the AKARI database for players matching specific criteria. "
            "Supports filtering by name, position, age range, nationality, competition, "
            "area (country/market), team, foot, season, AKARI scores, market value, "
            "and minimum games played. Use discover_values() first to look up valid "
            "parameter values. Multi-value support: position and nationality accept "
            "comma-separated values."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Player name (partial match)"},
                "position": {"type": "string", "description": "Position(s), comma-separated"},
                "min_age": {"type": "integer", "description": "Minimum age"},
                "max_age": {"type": "integer", "description": "Maximum age"},
                "nationality": {"type": "string", "description": "Nationality(s), comma-separated"},
                "competition": {"type": "string", "description": "Specific league name"},
                "area": {"type": "string", "description": "Country/market (e.g. 'Croatia', 'Belgium')"},
                "team": {"type": "string", "description": "Team name"},
                "foot": {"type": "string", "enum": ["left", "right", "both"]},
                "season": {"type": "string", "description": "Season (e.g. '2025-2026')"},
                "min_akari_skill_rescaled": {"type": "number", "description": "Minimum AKARI Skill (rescaled)"},
                "min_akari_potential_rescaled": {"type": "number", "description": "Minimum AKARI Potential (rescaled)"},
                "max_market_value": {"type": "number", "description": "Maximum market value in EUR"},
                "min_games_played": {"type": "integer", "description": "Minimum games played"},
                "sort_by": {"type": "string", "description": "Column to sort by (default: 'AKARI Potential')"},
                "limit": {"type": "integer", "description": "Max results (default: 20)"},
            },
            "required": [],
        },
        handler=akari_search.search_players,
    ))

    _register(ToolDefinition(
        name="get_player_profile",
        description="Get the full profile of a specific player by their Player ID.",
        input_schema={
            "type": "object",
            "properties": {
                "player_id": {"type": "number", "description": "The Player ID from search results"},
            },
            "required": ["player_id"],
        },
        handler=akari_search.get_player_profile,
    ))

    _register(ToolDefinition(
        name="get_similar_players",
        description=(
            "Find players similar to a given player using the AKARI Similarity algorithm. "
            "Returns players ordered by similarity score (lower = more similar)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "player_id": {"type": "number", "description": "The Player ID to find similar players for"},
                "limit": {"type": "integer", "description": "Max results (default: 10)"},
            },
            "required": ["player_id"],
        },
        handler=akari_search.get_similar_players,
    ))

    _register(ToolDefinition(
        name="get_competitions",
        description="Get a list of all available competitions in the AKARI database.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=akari_search.get_competitions,
    ))

    _register(ToolDefinition(
        name="get_stat_leaders",
        description=(
            "Get the top players ranked by a specific statistical metric. "
            "Use discover_values(field='metric') to see available metrics."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "metric": {"type": "string", "description": "The metric to rank by"},
                "position": {"type": "string", "description": "Filter by position"},
                "competition": {"type": "string", "description": "Filter by competition"},
                "limit": {"type": "integer", "description": "Max results (default: 20)"},
            },
            "required": ["metric"],
        },
        handler=akari_search.get_stat_leaders,
    ))

    _register(ToolDefinition(
        name="list_discoverable_fields",
        description="List all filter parameters whose valid values can be discovered via discover_values().",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=akari_search.list_discoverable_fields,
    ))

    _register(ToolDefinition(
        name="discover_values",
        description=(
            "Get all valid values for a specific filter parameter. "
            "Call this before searching to find exact valid values for position, "
            "competition, area, nationality, season, foot, metric, or role."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "field": {"type": "string", "description": "The parameter name to discover values for"},
            },
            "required": ["field"],
        },
        handler=akari_search.discover_values,
    ))

    # ── Transfermarkt ──────────────────────────────────────────────────

    _register(ToolDefinition(
        name="check_transfermarkt",
        description=(
            "Cross-reference a player on Transfermarkt to verify real-world status. "
            "MANDATORY: Call this for every player before presenting results. "
            "Returns profile, injuries, transfer history, and market value. "
            "If TM_id is available from search results, pass it as transfermarkt_id."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "player_name": {"type": "string", "description": "Full name of the player"},
                "transfermarkt_id": {
                    "type": "integer",
                    "description": "Optional Transfermarkt player ID (faster than name search)",
                },
            },
            "required": ["player_name"],
        },
        handler=transfermarkt.check_transfermarkt,
        is_async=True,
    ))

    # ── WyScout ────────────────────────────────────────────────────────

    _register(ToolDefinition(
        name="check_wyscout",
        description=(
            "Cross-reference a player on WyScout for additional scouting data. "
            "Fetches player details, transfer history, career stats, and contract info. "
            "Requires WyScout API credentials to be configured."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "player_name": {"type": "string", "description": "Full name of the player"},
            },
            "required": ["player_name"],
        },
        handler=wyscout.check_wyscout,
        is_async=True,
    ))


# Initialize on import
_init_tools()
