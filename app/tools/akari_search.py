"""
AKARI player database tools — SQL-first with parquet fallback.

Uses the Database abstraction layer to query Azure SQL views first,
falling back to local parquet files when the database is unavailable.
Ported from the akari-scout codebase.
"""

import json
from typing import Any, Optional

from app.database import db


# ── Helpers ────────────────────────────────────────────────────────────────

def _serialize(data: Any) -> str:
    """Serialize data to JSON, handling datetime and other types."""
    def default_handler(obj: Any) -> Any:
        """Handle non-serialisable types (datetime, etc.) for JSON output."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)
    return json.dumps(data, indent=2, default=default_handler, ensure_ascii=False)


# ── Tool handlers ──────────────────────────────────────────────────────────

def search_players(
    name: Optional[str] = None,
    position: Optional[str] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    nationality: Optional[str] = None,
    competition: Optional[str] = None,
    area: Optional[str] = None,
    team: Optional[str] = None,
    foot: Optional[str] = None,
    season: Optional[str] = None,
    min_akari_skill_rescaled: Optional[float] = None,
    min_akari_potential_rescaled: Optional[float] = None,
    max_market_value: Optional[float] = None,
    min_games_played: Optional[int] = None,
    sort_by: str = "AKARI Potential",
    limit: int = 20,
) -> str:
    """Search the AKARI database for players matching specific criteria."""
    # Build filters dict for the Database layer
    filters: dict[str, Any] = {}
    if name:
        filters["name"] = name
    if position:
        filters["position"] = position
    if min_age is not None:
        filters["min_age"] = min_age
    if max_age is not None:
        filters["max_age"] = max_age
    if nationality:
        filters["nationality"] = nationality
    if competition:
        filters["competition"] = competition
    if area:
        filters["area"] = area
    if team:
        filters["team"] = team
    if foot:
        filters["foot"] = foot
    if season:
        filters["season"] = season
    if min_akari_skill_rescaled is not None:
        filters["min_akari_skill_rescaled"] = min_akari_skill_rescaled
    if min_akari_potential_rescaled is not None:
        filters["min_akari_potential_rescaled"] = min_akari_potential_rescaled
    if max_market_value is not None:
        filters["max_market_value"] = max_market_value
    if min_games_played is not None:
        filters["min_games_played"] = min_games_played
    filters["sort_by"] = sort_by
    filters["limit"] = limit

    results = db.search_players(filters)
    if not results and not db.is_connected:
        return _serialize({"error": "Database not connected. Check DB_SERVER, DB_USER, DB_PASSWORD in .env."})

    return _serialize({"count": len(results), "players": results})


def get_player_profile(player_id: float) -> str:
    """Get the full profile of a specific player by their Player ID."""
    results = db.get_player_profile(player_id)
    if not results:
        return _serialize({"error": f"Player {player_id} not found"})
    return _serialize({"player_id": player_id, "seasons": results, "count": len(results)})


def get_similar_players(player_id: float, limit: int = 10) -> str:
    """Find players similar to a given player using the AKARI Similarity algorithm."""
    results = db.get_similar_players(player_id, limit)
    if not results:
        return _serialize({"error": "Similarity data not available."})
    return _serialize({
        "player_id": player_id,
        "similar_players": results,
        "count": len(results),
    })


def get_competitions() -> str:
    """Get a list of all available competitions in the AKARI database."""
    results = db.get_competitions()
    if not results:
        return _serialize({"error": "Competition data not available."})
    return _serialize({"competitions": results, "count": len(results)})


def get_stat_leaders(
    metric: str,
    position: Optional[str] = None,
    competition: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Get the top players ranked by a specific statistical metric."""
    results = db.get_stat_leaders(metric, position, competition, limit)
    if not results:
        return _serialize({"error": f"No results for metric '{metric}'."})
    return _serialize({"metric": metric, "leaders": results, "count": len(results)})


def list_discoverable_fields() -> str:
    """List all filter parameters whose valid values can be discovered."""
    fields = db.get_discoverable_fields()
    return _serialize({
        "fields": fields,
        "count": len(fields),
        "hint": "Call discover_values(field=<name>) for any of these to get valid values.",
    })


def discover_values(field: str) -> str:
    """Get all valid values for a specific filter parameter."""
    result = db.get_distinct_values(field)
    return _serialize(result)
