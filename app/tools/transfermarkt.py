"""
Transfermarkt scraper — web scraping client for transfermarkt.com.

Scrapes player pages directly using httpx + BeautifulSoup.
No API key required. Uses browser-like headers to avoid blocks.

Ported from the akari-scout codebase.
"""

import json
import re
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup


# ── Configuration ──────────────────────────────────────────────────────────

_BASE = "https://www.transfermarkt.com"

_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_TIMEOUT = 30.0


def _serialize(data: Any) -> str:
    """Serialize data to JSON string."""
    def default_handler(obj: Any) -> Any:
        """Handle non-serialisable types (datetime, etc.) for JSON output."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)
    return json.dumps(data, indent=2, default=default_handler, ensure_ascii=False)


# ── Low-level helpers ──────────────────────────────────────────────────────

async def _fetch(path: str, params: Optional[dict] = None) -> BeautifulSoup:
    """GET a page and return a BeautifulSoup tree."""
    url = f"{_BASE}{path}" if path.startswith("/") else path
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
    ) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")


def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _parse_value(text: str) -> str:
    """Normalise a Transfermarkt market-value string."""
    return _clean(text).replace("\xa0", " ")


# ── Search ─────────────────────────────────────────────────────────────────

async def _search_player(query: str) -> list[dict]:
    """Search Transfermarkt for a player by name."""
    soup = await _fetch("/schnellsuche/ergebnis/schnellsuche", {"query": query})
    results: list[dict] = []

    for table in soup.select("table.items"):
        for row in table.select("tbody tr"):
            try:
                link_el = row.select_one("td.hauptlink a")
                if not link_el:
                    continue
                name = _clean(link_el.get_text())
                href = link_el.get("href", "")
                id_match = re.search(r"/spieler/(\d+)", href)
                if not id_match:
                    continue
                player_id = int(id_match.group(1))

                club, age, position, market_value, nationality = "", "", "", "", ""
                for cell in row.select("td"):
                    text = _clean(cell.get_text())
                    club_link = cell.select_one("a[href*='/verein/']")
                    if club_link and not club:
                        club = _clean(club_link.get_text()) or club_link.get("title", "")
                    if "€" in text and not market_value:
                        market_value = text
                    if text.isdigit() and len(text) <= 2 and not age:
                        age = text

                pos_el = row.select_one("td.zentriert")
                if pos_el:
                    pos_text = _clean(pos_el.get_text())
                    if pos_text and not pos_text.isdigit():
                        position = pos_text

                flag_el = row.select_one("img.flaggenrahmen")
                if flag_el:
                    nationality = flag_el.get("alt", "") or flag_el.get("title", "")

                results.append({
                    "name": name, "id": player_id, "club": club, "age": age,
                    "position": position, "nationality": nationality,
                    "market_value": market_value, "url": f"{_BASE}{href}",
                })
            except Exception:
                continue
    return results


# ── Profile ────────────────────────────────────────────────────────────────

async def _get_player_profile(player_id: int) -> dict:
    """Get a player's profile: basic info + current market value."""
    soup = await _fetch(f"/x/profil/spieler/{player_id}")
    profile: dict = {"player_id": player_id}

    name_el = soup.select_one("h1.data-header__headline-wrapper")
    if name_el:
        raw = _clean(name_el.get_text())
        profile["name"] = re.sub(r"^#\d+\s+", "", raw)

    mv_el = soup.select_one(".data-header__market-value-wrapper")
    if mv_el:
        mv_text = _parse_value(mv_el.get_text())
        mv_match = re.search(r"[\d.,]+\s*(?:mln\.|k)?\s*€", mv_text)
        profile["market_value"] = mv_match.group(0).strip() if mv_match else mv_text

    club_el = soup.select_one(".data-header__club a")
    if club_el:
        profile["current_club"] = _clean(club_el.get_text())

    info_spans = soup.select(
        "span.info-table__content--regular, span.info-table__content--bold"
    )
    i = 0
    while i < len(info_spans) - 1:
        label = _clean(info_spans[i].get_text()).lower()
        value = _clean(info_spans[i + 1].get_text())
        if any(k in label for k in ["date of birth", "geb", "born"]):
            profile["birth_age"] = value
            age_match = re.search(r"\((\d+)\)", value)
            if age_match:
                profile["age"] = int(age_match.group(1))
        elif any(k in label for k in ["position", "positie"]):
            profile["position"] = value
        elif any(k in label for k in ["citizenship", "nationality"]):
            profile["nationality"] = value
        elif "contract" in label:
            profile["contract_until"] = value
        elif any(k in label for k in ["foot", "voet"]):
            profile["foot"] = value
        i += 2

    return profile


# ── Injuries ───────────────────────────────────────────────────────────────

async def _get_player_injuries(player_id: int) -> list[dict]:
    """Get a player's injury history."""
    soup = await _fetch(f"/x/verletzungen/spieler/{player_id}")
    injuries: list[dict] = []
    table = soup.select_one("table.items")
    if not table:
        return injuries

    for row in table.select("tbody tr"):
        try:
            cells = row.select("td")
            if len(cells) < 3:
                continue
            injury: dict = {}
            if cells:
                injury["season"] = _clean(cells[0].get_text())
            injury_el = row.select_one("td.hauptlink")
            if injury_el:
                injury["injury"] = _clean(injury_el.get_text())

            for cell in cells:
                text = _clean(cell.get_text())
                if re.match(r"\d{1,2}\s+\w+\.?\s+\d{4}", text):
                    if "from" not in injury:
                        injury["from"] = text
                    else:
                        injury["to"] = text
                if "dag" in text.lower():
                    injury["days_out"] = text
                if text.isdigit() and "games_missed" not in injury:
                    injury["games_missed"] = int(text)

            if injury.get("injury"):
                injuries.append(injury)
        except Exception:
            continue
    return injuries


# ── Transfers ──────────────────────────────────────────────────────────────

async def _get_player_transfers(player_id: int) -> list[dict]:
    """Get a player's transfer history via Transfermarkt's ceAPI."""
    url = f"{_BASE}/ceapi/transferHistory/list/{player_id}"
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    transfers: list[dict] = []
    for t in data.get("transfers", []):
        transfer: dict = {}
        if "season" in t:
            transfer["season"] = t["season"]
        if "date" in t:
            transfer["date"] = t["date"]
        from_data = t.get("from", {})
        if isinstance(from_data, dict):
            transfer["from_club"] = from_data.get("clubName", "")
        to_data = t.get("to", {})
        if isinstance(to_data, dict):
            transfer["to_club"] = to_data.get("clubName", "")
        if "fee" in t:
            transfer["fee"] = t["fee"]
        if "marketValue" in t:
            transfer["market_value"] = t["marketValue"]
        if t.get("loan"):
            transfer["is_loan"] = True
        transfers.append(transfer)
    return transfers


# ── Consolidated report (the tool handler) ─────────────────────────────────

async def check_transfermarkt(
    player_name: str,
    transfermarkt_id: Optional[int] = None,
) -> str:
    """Cross-reference a player on Transfermarkt to verify real-world status.

    MANDATORY: Call this for every player before presenting results.

    Returns a consolidated report with:
    - Player profile (age, club, position, current market value)
    - Recent injuries (type, duration, games missed)
    - Transfer history (recent moves, fees, loan/permanent)
    - Market value trend

    Args:
        player_name: The full name of the player.
        transfermarkt_id: Optional Transfermarkt player ID (from TM_id in search results).
    """
    player_id = transfermarkt_id

    # If no ID, search by name
    if not player_id:
        try:
            search_results = await _search_player(player_name)
        except Exception as e:
            return _serialize({
                "status": "error",
                "message": f"Transfermarkt search failed: {e}",
                "player_name": player_name,
            })

        if not search_results:
            return _serialize({
                "status": "not_found",
                "message": f"No results found on Transfermarkt for '{player_name}'.",
                "player_name": player_name,
            })

        match = search_results[0]
        player_id = match.get("id")
        if not player_id:
            return _serialize({
                "status": "error",
                "message": "Could not extract player ID from search results.",
                "search_results": search_results[:3],
            })

    # Fetch profile, injuries, and transfers in parallel
    report: dict[str, Any] = {"player_name": player_name, "transfermarkt_id": player_id}

    try:
        profile = await _get_player_profile(player_id)
        report["profile"] = profile
    except Exception as e:
        report["profile_error"] = str(e)

    try:
        injuries = await _get_player_injuries(player_id)
        report["injuries"] = injuries
    except Exception as e:
        report["injuries_error"] = str(e)

    try:
        transfers = await _get_player_transfers(player_id)
        report["transfers"] = transfers
    except Exception as e:
        report["transfers_error"] = str(e)

    return _serialize(report)
