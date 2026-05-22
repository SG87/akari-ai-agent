"""
AKARI player database tools — parquet-based search and discovery.

Ported from the akari-scout codebase. Uses pandas to query local parquet
files for player search, profile retrieval, similarity lookups, and
statistical leaders.
"""

import json
import os
from typing import Any, Optional

import pandas as pd

from app.config import settings


# ── Helpers ────────────────────────────────────────────────────────────────

def _parquet_path(name: str) -> str:
    """Resolve path to a parquet file in DATA_DIR."""
    return os.path.join(os.path.abspath(settings.DATA_DIR), f"{name}.parquet")


def _has_parquet(name: str) -> bool:
    """Check if a parquet file exists."""
    return os.path.exists(_parquet_path(name))


def _serialize(data: Any) -> str:
    """Serialize data to JSON, handling datetime and other types."""
    def default_handler(obj: Any) -> Any:
        """Handle non-serialisable types (datetime, etc.) for JSON output."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)
    return json.dumps(data, indent=2, default=default_handler, ensure_ascii=False)


# Competition alias mapping (common names → Wyscout DB names)
_COMPETITION_ALIASES: dict[str, str] = {
    "1.hnl": "Superleague", "1. hnl": "Superleague",
    "croatian first league": "Superleague", "croatian league": "Superleague",
    "jupiler pro league": "Pro League", "belgian first division": "Pro League",
    "belgian pro league": "Pro League", "eerste klasse": "Pro League",
    "1a pro league": "Pro League",
    "eredivisie": "Eredivisie",
    "epl": "Premier League", "english premier league": "Premier League",
    "bundesliga": "Bundesliga",
    "ligue 1": "Ligue 1", "ligue 2": "Ligue 2",
    "serie a": "Serie A", "serie b": "Serie B", "calcio": "Serie A",
    "la liga": "LaLiga", "laliga": "LaLiga",
    "liga portugal": "Liga Portugal", "primeira liga": "Liga Portugal",
    "super lig": "Super Lig", "turkish super league": "Super Lig",
    "mls": "MLS", "major league soccer": "MLS",
    "j1 league": "J1 League", "j-league": "J1 League",
    "k league 1": "K League 1",
    "allsvenskan": "Allsvenskan",
    "eliteserien": "Eliteserien",
    "ekstraklasa": "Ekstraklasa",
    "superligaen": "Superligaen",
}

# Columns safe for sorting
_SORTABLE_COLUMNS = [
    "AKARI Potential", "AKARI Skill",
    "AKARI_Potential_rescaled", "AKARI_Skill_rescaled",
    "Goals", "Assists", "xG ", "xA ",
    "Shots ", "Successful key passes ", "Chances created ",
    "Progressive runs ", "Ball recoveries ", "Interceptions ",
    "Duels won ", "Defensive duels won ", "Aerial duels won",
    "Pass accuracy %", "Age", "Market value", "Games played",
]

# Known area names (lazy-loaded cache)
_known_areas: set[str] | None = None


def _load_known_areas() -> set[str]:
    """Load distinct area names from parquet (cached)."""
    global _known_areas
    if _known_areas is not None:
        return _known_areas
    areas: set[str] = set()
    if _has_parquet("vw_scout_players"):
        try:
            df = pd.read_parquet(_parquet_path("vw_scout_players"), columns=["Area"])
            areas = {a.lower() for a in df["Area"].dropna().unique()}
        except Exception:
            pass
    _known_areas = areas
    return areas


def _resolve_competition(name: str) -> str:
    """Resolve a common competition name to its DB name."""
    return _COMPETITION_ALIASES.get(name.lower().strip(), name)


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
    if not _has_parquet("vw_scout_players"):
        return _serialize({"error": "Player data not available. Place vw_scout_players.parquet in DATA_DIR."})

    try:
        df = pd.read_parquet(_parquet_path("vw_scout_players"))
    except Exception as e:
        return _serialize({"error": f"Failed to read player data: {e}"})

    # Resolve competition alias — smart area detection
    if competition:
        if competition.lower().strip() in _load_known_areas() and not area:
            area = competition
            competition = None
        else:
            competition = _resolve_competition(competition)

    # Apply filters
    if name:
        nl = name.lower()
        mask = (
            df["Short name"].str.lower().str.contains(nl, na=False)
            | df["First name"].str.lower().str.contains(nl, na=False)
            | df["Last name"].str.lower().str.contains(nl, na=False)
        )
        df = df[mask]

    if position:
        positions = [p.strip().lower() for p in position.split(",")]
        mask = pd.Series(False, index=df.index)
        for p in positions:
            mask = mask | (
                df["Main position"].str.lower().str.contains(p, na=False)
                | df.get("Second position", pd.Series(dtype=str)).str.lower().str.contains(p, na=False)
                | df.get("Third position", pd.Series(dtype=str)).str.lower().str.contains(p, na=False)
                | df.get("Position", pd.Series(dtype=str)).str.lower().str.contains(p, na=False)
            )
        df = df[mask]

    if max_age is not None:
        df = df[df["Age"] <= max_age]
    if min_age is not None:
        df = df[df["Age"] >= min_age]

    if nationality:
        nats = [n.strip().lower() for n in nationality.split(",")]
        mask = pd.Series(False, index=df.index)
        for n in nats:
            mask = mask | (
                df["Birth area"].str.lower().str.contains(n, na=False)
                | df.get("Passport area", pd.Series(dtype=str)).str.lower().str.contains(n, na=False)
            )
        df = df[mask]

    if competition:
        df = df[df["Competition"].str.lower().str.contains(competition.lower(), na=False)]
    if area:
        df = df[df["Area"].str.lower().str.contains(area.lower(), na=False)]
    if team:
        df = df[df["Team"].str.lower().str.contains(team.lower(), na=False)]
    if foot:
        df = df[df["Foot"] == foot]
    if season:
        df = df[df["Season"] == season]
    if min_akari_skill_rescaled is not None:
        df = df[df["AKARI_Skill_rescaled"] >= min_akari_skill_rescaled]
    if min_akari_potential_rescaled is not None:
        df = df[df["AKARI_Potential_rescaled"] >= min_akari_potential_rescaled]
    if max_market_value is not None:
        df = df[df["Market value"] <= max_market_value]
    if min_games_played is not None:
        df = df[df["Games played"] >= min_games_played]

    # Sort
    sort_col = sort_by if sort_by in _SORTABLE_COLUMNS else "AKARI Potential"
    if "season_weight" in df.columns:
        df["_sort_key"] = df["season_weight"] * df[sort_col].fillna(0)
    else:
        df["_sort_key"] = df[sort_col].fillna(0)
    df = df.sort_values("_sort_key", ascending=False).drop(columns=["_sort_key"])
    df = df.head(limit)
    df = df.where(pd.notnull(df), None)

    return _serialize({"count": len(df), "players": df.to_dict(orient="records")})


def get_player_profile(player_id: float) -> str:
    """Get the full profile of a specific player by their Player ID."""
    if not _has_parquet("vw_scout_players"):
        return _serialize({"error": "Player data not available."})
    try:
        df = pd.read_parquet(_parquet_path("vw_scout_players"))
        df = df[df["Player ID"] == player_id]
        df = df.where(pd.notnull(df), None)
        records = df.to_dict(orient="records")
        if not records:
            return _serialize({"error": f"Player {player_id} not found"})
        return _serialize({"player_id": player_id, "seasons": records, "count": len(records)})
    except Exception as e:
        return _serialize({"error": f"Profile lookup failed: {e}"})


def get_similar_players(player_id: float, limit: int = 10) -> str:
    """Find players similar to a given player using the AKARI Similarity algorithm."""
    if not _has_parquet("similarity"):
        return _serialize({"error": "Similarity data not available."})
    try:
        df = pd.read_parquet(_parquet_path("similarity"))
        df = df[df["baseplayer"] == player_id]
        df = df.sort_values("Similarity (the lower the better)", ascending=True)
        df = df.head(limit)
        df = df.where(pd.notnull(df), None)
        return _serialize({
            "player_id": player_id,
            "similar_players": df.to_dict(orient="records"),
            "count": len(df),
        })
    except Exception as e:
        return _serialize({"error": f"Similarity lookup failed: {e}"})


def get_competitions() -> str:
    """Get a list of all available competitions in the AKARI database."""
    if not _has_parquet("competitions"):
        return _serialize({"error": "Competition data not available."})
    try:
        df = pd.read_parquet(_parquet_path("competitions"))
        df = df.where(pd.notnull(df), None)
        return _serialize({"competitions": df.to_dict(orient="records"), "count": len(df)})
    except Exception as e:
        return _serialize({"error": f"Competition lookup failed: {e}"})


def get_stat_leaders(
    metric: str,
    position: Optional[str] = None,
    competition: Optional[str] = None,
    limit: int = 20,
) -> str:
    """Get the top players ranked by a specific statistical metric."""
    if not _has_parquet("vw_scout_players"):
        return _serialize({"error": "Player data not available."})

    if competition:
        competition = _resolve_competition(competition)

    try:
        df = pd.read_parquet(_parquet_path("vw_scout_players"))
        df = df.dropna(subset=[metric])

        if position:
            pl = position.lower()
            mask = (
                df["Main position"].str.lower().str.contains(pl, na=False)
                | df.get("Position", pd.Series(dtype=str)).str.lower().str.contains(pl, na=False)
            )
            df = df[mask]

        if competition:
            df = df[df["Competition"].str.lower().str.contains(competition.lower(), na=False)]

        if "season_weight" in df.columns:
            df["_sort"] = df["season_weight"] * df[metric].fillna(0)
        else:
            df["_sort"] = df[metric].fillna(0)
        df = df.sort_values("_sort", ascending=False).head(limit)
        df = df.drop(columns=["_sort"])
        df = df.where(pd.notnull(df), None)
        return _serialize({"metric": metric, "leaders": df.to_dict(orient="records"), "count": len(df)})
    except Exception as e:
        return _serialize({"error": f"Stat leaders lookup failed: {e}"})


def list_discoverable_fields() -> str:
    """List all filter parameters whose valid values can be discovered."""
    fields = ["position", "competition", "area", "nationality", "season", "foot", "metric", "role"]
    return _serialize({
        "fields": fields,
        "count": len(fields),
        "hint": "Call discover_values(field=<name>) for any of these to get valid values.",
    })


def discover_values(field: str) -> str:
    """Get all valid values for a specific filter parameter."""
    # Static fields
    static: dict[str, list[str]] = {
        "foot": ["left", "right", "both"],
        "metric": [
            "AKARI Skill", "AKARI Potential",
            "AKARI_Skill_rescaled", "AKARI_Potential_rescaled",
            "Goals", "Assists", "xG ", "xA ",
            "Shots ", "Successful key passes ", "Chances created ",
            "Progressive runs ", "Ball recoveries ", "Interceptions ",
            "Duels won ", "Defensive duels won ", "Aerial duels won",
            "Pass accuracy %", "Duels won %", "Successful dribbles ",
            "Successful passes to final third ",
        ],
    }
    if field in static:
        return _serialize({"field": field, "values": static[field]})

    # Dynamic fields from parquet
    column_map: dict[str, str] = {
        "position": "Main position",
        "competition": "Competition",
        "area": "Area",
        "nationality": "Birth area",
        "season": "Season",
        "role": "Role",
    }
    col = column_map.get(field)
    if not col:
        return _serialize({"error": f"Unknown field: {field}"})

    if not _has_parquet("vw_scout_players"):
        return _serialize({"error": "Player data not available."})

    try:
        df = pd.read_parquet(_parquet_path("vw_scout_players"), columns=[col])
        values = sorted(df[col].dropna().unique().tolist())
        return _serialize({"field": field, "values": values, "count": len(values)})
    except Exception as e:
        return _serialize({"error": f"Discovery failed: {e}"})
