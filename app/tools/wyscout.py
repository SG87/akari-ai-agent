"""
WyScout API v3 client — fetches player data from the WyScout platform.

Requires WYSCOUT_USERNAME and WYSCOUT_PASSWORD in environment.
Gracefully degrades when credentials are not configured.

Ported from the akari-scout codebase.
"""

import json
from typing import Any

import httpx

from app.config import settings


_BASE_URL = "https://apirest.wyscout.com/v3"


def _serialize(data: Any) -> str:
    """Serialize data to JSON string."""
    def default_handler(obj: Any) -> Any:
        """Handle non-serialisable types (datetime, etc.) for JSON output."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)
    return json.dumps(data, indent=2, default=default_handler, ensure_ascii=False)


async def check_wyscout(player_name: str) -> str:
    """Cross-reference a player on WyScout for additional scouting data.

    Fetches player details, transfer history, career stats, and contract info
    from the WyScout API v3.

    Args:
        player_name: The full name of the player to look up.

    Note: Requires WYSCOUT_USERNAME and WYSCOUT_PASSWORD in environment.
    """
    username = settings.WYSCOUT_USERNAME
    password = settings.WYSCOUT_PASSWORD

    if not username or not password:
        return _serialize({
            "status": "not_configured",
            "message": (
                "WyScout API credentials not configured. "
                "Set WYSCOUT_USERNAME and WYSCOUT_PASSWORD to enable this check."
            ),
            "player_name": player_name,
        })

    auth = (username, password)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Search for the player
            resp = await client.get(
                f"{_BASE_URL}/search",
                params={"query": player_name, "objectType": "player"},
                auth=auth,
            )
            resp.raise_for_status()
            search_data = resp.json()

            players = search_data.get("players", [])
            if not players:
                return _serialize({
                    "status": "not_found",
                    "message": f"No WyScout results for '{player_name}'.",
                    "player_name": player_name,
                })

            wy_player = players[0]
            wy_id = wy_player.get("wyId")

            report: dict[str, Any] = {
                "player_name": player_name,
                "wyscout_id": wy_id,
                "player_details": wy_player,
            }

            # Transfers
            try:
                tresp = await client.get(
                    f"{_BASE_URL}/players/{wy_id}/transfers", auth=auth
                )
                tresp.raise_for_status()
                report["transfers"] = tresp.json()
            except Exception as e:
                report["transfers_error"] = str(e)

            # Career stats
            try:
                sresp = await client.get(
                    f"{_BASE_URL}/players/{wy_id}/career", auth=auth
                )
                sresp.raise_for_status()
                report["career"] = sresp.json()
            except Exception as e:
                report["career_error"] = str(e)

            # Contract info
            try:
                cresp = await client.get(
                    f"{_BASE_URL}/players/{wy_id}/contractinfo", auth=auth
                )
                cresp.raise_for_status()
                report["contract"] = cresp.json()
            except Exception as e:
                report["contract_error"] = str(e)

            return _serialize(report)

    except Exception as e:
        return _serialize({
            "status": "error",
            "message": f"WyScout API error: {str(e)}",
            "player_name": player_name,
        })
