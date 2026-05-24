"""
Database access layer for the Akari Scout AI agent.

Connects to Azure SQL and queries views (agent_scout_players, etc.)
or falls back to CTE-based queries on the underlying tables directly.
No parquet files — all data comes from the database.

Ported from the akari-scout backend.
"""

import logging
from typing import Optional, List, Dict, Any

from app.config import settings

logger = logging.getLogger("akari.database")

# pyodbc is required for this module
import pyodbc


# ── SQL CTE that replicates the agent_scout_players view logic ─────────────
# Used when the view hasn't been created yet (permission issues).
# Deduplicates Descriptives_new and UNIONs 4 season tables.

_DESC_CTE = """
WITH desc_dedup AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY wyId
               ORDER BY
                   CASE WHEN TM_id IS NOT NULL THEN 0 ELSE 1 END,
                   CASE WHEN [Market value] IS NOT NULL THEN 0 ELSE 1 END,
                   [seasons.seasonId] DESC
           ) AS _rn
    FROM [dbo].[Descriptives_new]
),
desc_unique AS (
    SELECT * FROM desc_dedup WHERE _rn = 1
)
"""

# Common SELECT columns for the scout player query
_SCOUT_SELECT = """
    s.[Player ID],
    d.shortName AS [Short name],
    d.firstName AS [First name],
    d.lastName AS [Last name],
    s.[Age],
    d.height AS [Height],
    d.weight AS [Weight],
    CAST(d.birthDate AS nvarchar(50)) AS [Birth date],
    d.foot AS [Foot],
    d.[birthArea.name] AS [Birth area],
    d.[passportArea.name] AS [Passport area],
    d.imageDataURL AS [player image],
    d.TM_id AS [TM_id],
    d.TM_URL AS [TM_URL],
    s.[Team ID], s.[Team], s.[Team image],
    s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position],
    s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value] AS [Market value],
    d.[Contract expires] AS [Contract expires],
    s.[Goals], s.[Assists], s.[xG ], s.[xA ], s.[Shots ],
    s.[Successful key passes ], s.[Chances created ],
    s.[Progressive runs ], s.[Successful progressive passes ],
    s.[Touches in box ], s.[Successful dribbles ], s.[Offensive duels won ],
    s.[Successful passes to final third ], s.[Successful through passes ],
    s.[Successful long passes ], s.[Successful passes into penalty box ],
    s.[Shot assists ], s.[Third assists ], s.[Fouls suffered ], s.[Vertical passes ],
    s.[Ball recoveries ], s.[Interceptions ], s.[Successful defensive actions ],
    s.[Clearances ], s.[Duels won ], s.[Defensive duels won ], s.[Aerial duels won],
    s.[Loose ball duels won ], s.[Successful sliding tackles ],
    s.[Opponent half recoveries ], s.[Headers ],
    s.[Losses ], s.[Dangerous own half losses ], s.[Bad ball controls],
    s.[Passes ], s.[Pass length average],
    s.[Pass accuracy %], s.[Cross accuracy %], s.[Shots on target %],
    s.[Chances conversion %], s.[Duels won %], s.[Aerial duels won %],
    s.[Successful sliding tackles %], s.[xG conversion %],
    s.[xG Save ], s.[gK shots saved %], s.[Clean sheet %],
    s.[Goal kicks short ], s.[Goal kicks long ],
    s.[gk Exits ], s.[gk Successful exits ], s.[gk xG - conceded],
    s.[AKARI Skill], s.[AKARI Potential],
    s.[AKARI_Skill_rescaled], s.[AKARI_Potential_rescaled],
    s.[benchmark.successfulKeyPasses.average],
    s.[benchmark.successfulPassesToFinalThird.average],
    s.[benchmark.shots.average], s.[benchmark.aerialDuelsWon.average],
    s.[benchmark.gkConcededGoals.average], s.[benchmark.xgSave.average],
    s.[benchmark.interceptions.average], s.[benchmark.successfulLongPasses.average],
    s.[benchmark.dangerousOwnHalfLosses.average],
    s.[benchmark.successfulSlidingTackles.average],
    s.[benchmark.newSuccessfulDribbles.average], s.[benchmark.xgAssist.average],
    s.[benchmark.xgShot.average], s.[benchmark.gkSaves.average],
    s.[benchmark.chancesCreated.average], s.[benchmark.gkShotsAgainst.average],
    s.[benchmark.gkSaves.percent], s.[benchmark.AKARI.skill.average],
    s.[benchmark.gkcleansheets.percent]
"""

# The full CTE-based query that mimics the view (UNION ALL of 4 seasons)
_SCOUT_PLAYERS_CTE_QUERY = f"""
{_DESC_CTE},
scout_all AS (
    SELECT 0.4 AS season_weight, {_SCOUT_SELECT}
    FROM [dbo].[AKARI data season 2024-2025] s
    LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]

    UNION ALL

    SELECT 0.7 AS season_weight, {_SCOUT_SELECT}
    FROM [dbo].[AKARI data season 2025] s
    LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]

    UNION ALL

    SELECT 0.9 AS season_weight, {_SCOUT_SELECT}
    FROM [dbo].[AKARI data season 2025-2026] s
    LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]

    UNION ALL

    SELECT 1.0 AS season_weight, {_SCOUT_SELECT}
    FROM [dbo].[AKARI data season 2026] s
    LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]
)
"""


class Database:
    """Database abstraction — queries Azure SQL views or underlying tables."""

    # Maps common / colloquial league names to their Wyscout DB names.
    _COMPETITION_ALIASES: Dict[str, str] = {
        # Croatia
        "1.hnl": "Superleague", "1. hnl": "Superleague",
        "hrvatska nogometna liga": "Superleague", "supersport hnl": "Superleague",
        "croatian first league": "Superleague", "croatian league": "Superleague",
        "croatia 1.hnl": "Superleague", "croatia superleague": "Superleague",
        "2.hnl": "First NL", "2. hnl": "First NL", "croatia second league": "First NL",
        "3.hnl": "Second NL",
        # Slovenia
        "slovenian league": "1. SNL", "slovenian first league": "1. SNL",
        "prva liga slovenia": "1. SNL", "1. snl": "1. SNL", "prvaliga": "1. SNL",
        # Austria
        "austrian league": "Bundesliga", "austrian first league": "Bundesliga",
        "tipico bundesliga": "Bundesliga", "austrian bundesliga": "Bundesliga",
        # Serbia
        "serbian league": "Super Liga", "serbian super liga": "Super Liga",
        "serbian superliga": "Super Liga", "serbian first league": "Super Liga",
        # Belgium
        "jupiler pro league": "Pro League", "belgian first division": "Pro League",
        "eerste klasse": "Pro League", "belgian pro league": "Pro League",
        "1a pro league": "Pro League",
        "1b pro league": "Challenger Pro League", "proximus league": "Challenger Pro League",
        # Netherlands
        "eredivisie": "Eredivisie",
        "eerste divisie": "Eerste Divisie", "keuken kampioen divisie": "Eerste Divisie",
        # England
        "epl": "Premier League", "english premier league": "Premier League",
        # Germany
        "bundesliga": "Bundesliga", "2. bundesliga": "2. Bundesliga",
        # France
        "ligue 1": "Ligue 1", "ligue 2": "Ligue 2",
        # Italy
        "serie a": "Serie A", "serie b": "Serie B", "calcio": "Serie A",
        # Spain
        "la liga": "LaLiga", "laliga": "LaLiga", "liga": "LaLiga",
        "la liga 2": "LaLiga 2", "segunda division": "Segunda División",
        # Portugal
        "primeira liga": "Liga Portugal", "liga portugal": "Liga Portugal",
        "liga nos": "Liga Portugal",
        # Turkey
        "süper lig": "Super Lig", "super lig": "Super Lig",
        "turkish super league": "Super Lig",
        # Greece
        "greek super league": "Super League 1",
        # Scotland
        "scottish premiership": "Premiership", "spfl premiership": "Premiership",
        # Switzerland
        "swiss super league": "Super League",
        # Denmark
        "danish superliga": "Superligaen", "superligaen": "Superligaen",
        # Sweden
        "allsvenskan": "Allsvenskan",
        # Norway
        "eliteserien": "Eliteserien",
        # Finland
        "veikkausliiga": "Veikkausliiga",
        # Poland
        "ekstraklasa": "Ekstraklasa",
        # Czech Republic
        "czech first league": "First League", "fortuna liga": "First League",
        # Romania
        "liga 1": "SuperLiga", "romanian first league": "SuperLiga",
        # Bulgaria
        "bulgarian first league": "First League", "parva liga": "First League",
        # Hungary
        "nb i": "NB I", "hungarian first division": "NB I",
        # Slovakia
        "slovak super liga": "Nike Liga",
        # Ukraine
        "ukrainian premier league": "Premier League",
        # Russia
        "russian premier league": "Premier League",
        # Japan
        "j-league": "J1 League", "j1 league": "J1 League", "j league": "J1 League",
        # South Korea
        "k league 1": "K League 1", "k league": "K League 1",
        # USA
        "mls": "MLS", "major league soccer": "MLS",
        # Argentina
        "liga profesional": "Liga Profesional", "superliga argentina": "Liga Profesional",
        # Brazil
        "brasileirao": "Serie A", "brasileirão": "Serie A",
        # Mexico
        "liga mx": "Liga MX",
        # Colombia
        "liga betplay": "Liga BetPlay", "colombian first division": "Liga BetPlay",
        # Chile
        "primera division chile": "Primera División",
        # Egypt
        "egyptian premier league": "Premier League",
        # Saudi Arabia
        "saudi pro league": "Pro League", "roshn saudi league": "Pro League",
        # Australia
        "a-league": "A-League",
        # China
        "chinese super league": "Super League", "csl": "Super League",
    }

    # Columns that are safe to use in ORDER BY (whitelist for sort_by)
    _SORTABLE_COLUMNS = [
        'AKARI Potential', 'AKARI Skill',
        'AKARI_Potential_rescaled', 'AKARI_Skill_rescaled',
        'Goals', 'Assists', 'xG ', 'xA ',
        'Shots ', 'Successful key passes ', 'Chances created ',
        'Progressive runs ', 'Ball recoveries ', 'Interceptions ',
        'Duels won ', 'Defensive duels won ', 'Aerial duels won',
        'Pass accuracy %', 'Age', 'Market value', 'Games played',
    ]

    # Valid metric names for stat leaders
    _VALID_METRICS = [
        "AKARI Skill", "AKARI Potential",
        "AKARI_Skill_rescaled", "AKARI_Potential_rescaled",
        "Goals", "Assists",
        "xG ", "xA ",
        "Shots ", "Successful key passes ", "Chances created ",
        "Progressive runs ", "Successful progressive passes ",
        "Touches in box ", "Successful dribbles ",
        "Offensive duels won ", "Successful passes to final third ",
        "Successful through passes ", "Successful long passes ",
        "Successful passes into penalty box ",
        "Ball recoveries ", "Interceptions ",
        "Successful defensive actions ", "Clearances ",
        "Duels won ", "Defensive duels won ", "Aerial duels won",
        "Loose ball duels won ", "Successful sliding tackles ",
        "Losses ", "Dangerous own half losses ", "Bad ball controls",
        "Pass accuracy %", "Cross accuracy %", "Shots on target %",
        "Chances conversion %", "Duels won %", "Aerial duels won %",
        "Successful sliding tackles %",
        "xG conversion %",
        "xG Save ", "gK shots saved %", "Clean sheet %",
    ]

    # Static fields with fixed or pre-known values
    _STATIC_VALUES: Dict[str, Dict[str, Any]] = {
        "foot": {
            "description": "Preferred foot of the player",
            "values": ["left", "right", "both"],
        },
        "metric": {
            "description": (
                "Statistical metric name for use with get_stat_leaders. "
                "Note: some metric names have trailing spaces — use them exactly as shown."
            ),
            "values": [],  # populated from _VALID_METRICS at init
        },
    }

    # Dynamic fields: column names for SQL
    _DYNAMIC_FIELDS: Dict[str, Dict[str, str]] = {
        "position": {
            "description": "Player position (Main position, Second position, Third position, Position)",
            "sql_column": "Main position",
        },
        "role": {
            "description": "Broad player role category",
            "sql_column": "Role",
        },
        "competition": {
            "description": "Competition name — use exact value or partial match",
            "sql_column": "Competition",
        },
        "area": {
            "description": "Geographic area of the competition",
            "sql_column": "Area",
        },
        "nationality": {
            "description": "Player birth area / nationality (Birth area and Passport area)",
            "sql_column": "Birth area",
        },
        "season": {
            "description": "Season identifier",
            "sql_column": "Season",
        },
    }

    # View name (checked first) and table-based fallback
    _VIEW_NAME = "agent_scout_players"
    _DETAILED_VIEW_NAME = "agent_scout_detailed_stats"

    def __init__(self):
        self._conn = None
        self._use_table: Optional[bool] = None  # True = table exists, fastest
        self._use_views: Optional[bool] = None   # True = view exists, fast
        self._known_areas: Optional[set] = None
        # Populate metric values
        self._STATIC_VALUES["metric"]["values"] = self._VALID_METRICS.copy()

    def connect(self):
        """Establish database connection."""
        if not settings.DB_SERVER or not settings.DB_PASSWORD:
            logger.warning("Database credentials not configured — cannot connect")
            return

        try:
            self._conn = pyodbc.connect(settings.connection_string)
            logger.info("✅ Database connected to %s/%s as %s",
                        settings.DB_SERVER, settings.DB_NAME, settings.DB_USER)

            # Check for materialized table first (fastest), then view, then CTE fallback
            self._use_table = self._check_table_exists(self._VIEW_NAME)
            if self._use_table:
                logger.info("   Using TABLE: %s (indexed, fastest)", self._VIEW_NAME)
                self._use_views = True  # same query path — SELECT FROM table
            else:
                self._use_views = self._check_view_exists(self._VIEW_NAME)
                if self._use_views:
                    logger.info("   Using VIEW: %s", self._VIEW_NAME)
                else:
                    logger.info("   No table/view found — using CTE queries (slow)")

        except Exception as e:
            logger.error("❌ Database connection failed: %s", e)
            self._conn = None

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Database connection closed")

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def _check_view_exists(self, view_name: str) -> bool:
        """Check if a SQL view exists in the database."""
        if not self.is_connected:
            return False
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_NAME = ?",
                view_name
            )
            return cursor.fetchone()[0] > 0
        except Exception:
            return False

    def _check_table_exists(self, table_name: str) -> bool:
        """Check if a SQL table (not view) exists in the database."""
        if not self.is_connected:
            return False
        try:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_NAME = ? AND TABLE_TYPE = 'BASE TABLE'",
                table_name
            )
            return cursor.fetchone()[0] > 0
        except Exception:
            return False

    def _execute_query(self, query: str, params: list = None) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as list of dicts."""
        if not self.is_connected:
            return []

        try:
            cursor = self._conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error("Query error: %s", e)
            return []

    def _scout_source(self) -> str:
        """Return the FROM clause — either the view or the CTE-based query."""
        if self._use_views:
            return f"[dbo].[{self._VIEW_NAME}]"
        # Use CTE — caller must prepend the CTE definitions
        return "scout_all"

    def _build_scout_query(self, select: str, where: str = "",
                           params: list = None, order_by: str = "",
                           limit: int = 50) -> tuple:
        """Build a complete scout player query, using views or CTE fallback.

        Returns (query_string, params_list).
        """
        if self._use_views:
            query = f"SELECT TOP {limit} {select} FROM [dbo].[{self._VIEW_NAME}]"
        else:
            query = f"{_SCOUT_PLAYERS_CTE_QUERY} SELECT TOP {limit} {select} FROM scout_all"

        if where:
            query += f" WHERE {where}"
        if order_by:
            query += f" ORDER BY {order_by}"

        return query, params or []

    # ── Area / competition helpers ─────────────────────────────────────

    def _load_known_areas(self) -> set:
        """Load known area names (cached)."""
        if self._known_areas is not None:
            return self._known_areas

        if self._use_views:
            query = (
                f"SELECT DISTINCT [Area] FROM [dbo].[{self._VIEW_NAME}] "
                "WHERE [Area] IS NOT NULL"
            )
        else:
            query = (
                f"{_SCOUT_PLAYERS_CTE_QUERY} "
                "SELECT DISTINCT [Area] FROM scout_all "
                "WHERE [Area] IS NOT NULL"
            )
        rows = self._execute_query(query)
        self._known_areas = {r['Area'].lower() for r in rows if r.get('Area')}
        return self._known_areas

    def _resolve_competition(self, name: str) -> str:
        """Resolve a common competition name to its Wyscout DB name."""
        return self._COMPETITION_ALIASES.get(name.lower().strip(), name)

    def _is_area_name(self, value: str) -> bool:
        """Check if a value is a country/area name rather than a competition."""
        known = self._load_known_areas()
        return value.lower().strip() in known

    # ── Search players ─────────────────────────────────────────────────

    def search_players(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Search players with full filter support."""
        if not self.is_connected:
            return []

        # Resolve competition aliases
        if filters.get('competition'):
            comp = filters['competition']
            if self._is_area_name(comp) and not filters.get('area'):
                filters['area'] = comp
                del filters['competition']
            else:
                filters['competition'] = self._resolve_competition(comp)

        conditions = []
        params = []

        if filters.get('name'):
            conditions.append(
                "([Short name] LIKE ? OR [First name] LIKE ? OR [Last name] LIKE ?)"
            )
            name_val = f"%{filters['name']}%"
            params.extend([name_val, name_val, name_val])

        if filters.get('position'):
            positions = [p.strip() for p in filters['position'].split(',')]
            pos_conds = []
            for p in positions:
                pos_conds.append(
                    "([Main position] LIKE ? OR [Second position] LIKE ? "
                    "OR [Third position] LIKE ? OR [Position] LIKE ?)"
                )
                val = f"%{p}%"
                params.extend([val, val, val, val])
            conditions.append(f"({' OR '.join(pos_conds)})")

        if filters.get('max_age'):
            conditions.append("[Age] <= ?")
            params.append(filters['max_age'])

        if filters.get('min_age'):
            conditions.append("[Age] >= ?")
            params.append(filters['min_age'])

        if filters.get('nationality'):
            nats = [n.strip() for n in filters['nationality'].split(',')]
            nat_conds = []
            for n in nats:
                nat_conds.append("([Birth area] LIKE ? OR [Passport area] LIKE ?)")
                val = f"%{n}%"
                params.extend([val, val])
            conditions.append(f"({' OR '.join(nat_conds)})")

        if filters.get('competition'):
            conditions.append("[Competition] LIKE ?")
            params.append(f"%{filters['competition']}%")

        if filters.get('season'):
            conditions.append("[Season] = ?")
            params.append(filters['season'])

        if filters.get('min_akari_skill'):
            conditions.append("[AKARI Skill] >= ?")
            params.append(filters['min_akari_skill'])

        if filters.get('min_akari_potential'):
            conditions.append("[AKARI Potential] >= ?")
            params.append(filters['min_akari_potential'])

        if filters.get('min_akari_skill_rescaled'):
            conditions.append("[AKARI_Skill_rescaled] >= ?")
            params.append(filters['min_akari_skill_rescaled'])

        if filters.get('min_akari_potential_rescaled'):
            conditions.append("[AKARI_Potential_rescaled] >= ?")
            params.append(filters['min_akari_potential_rescaled'])

        if filters.get('max_market_value'):
            conditions.append("[Market value] <= ?")
            params.append(filters['max_market_value'])

        if filters.get('min_games_played'):
            conditions.append("[Games played] >= ?")
            params.append(filters['min_games_played'])

        if filters.get('team'):
            conditions.append("[Team] LIKE ?")
            params.append(f"%{filters['team']}%")

        if filters.get('area'):
            conditions.append("[Area] LIKE ?")
            params.append(f"%{filters['area']}%")

        if filters.get('foot'):
            conditions.append("[Foot] = ?")
            params.append(filters['foot'])

        where = " AND ".join(conditions) if conditions else ""
        limit = filters.get('limit', 50)

        sort_col = filters.get('sort_by', 'AKARI Potential')
        if sort_col not in self._SORTABLE_COLUMNS:
            sort_col = 'AKARI Potential'

        order_by = f"season_weight * ISNULL([{sort_col}], 0) DESC"

        query, _ = self._build_scout_query("*", where, params, order_by, limit)
        return self._execute_query(query, params)

    # ── Player profile ─────────────────────────────────────────────────

    def get_player_profile(self, player_id: float) -> Optional[List[Dict[str, Any]]]:
        """Get full player profile by Player ID (across all seasons)."""
        if not self.is_connected:
            return None

        query, _ = self._build_scout_query(
            "*", "[Player ID] = ?", [player_id], limit=10
        )
        results = self._execute_query(query, [player_id])
        return results if results else None

    # ── Similar players ────────────────────────────────────────────────

    def get_similar_players(self, player_id: float, limit: int = 10) -> List[Dict[str, Any]]:
        """Get similar players from the Similarity table."""
        if not self.is_connected:
            return []

        query = f"""
            SELECT TOP {limit}
                s.[Player ID],
                s.[Similar player name],
                s.[Similarity (the lower the better)] AS similarity_score,
                s.[Base player name]
            FROM [dbo].[Similarity] s
            WHERE s.baseplayer = ?
            ORDER BY s.[Similarity (the lower the better)] ASC
        """
        return self._execute_query(query, [player_id])

    # ── Competitions ───────────────────────────────────────────────────

    def get_competitions(self) -> List[Dict[str, Any]]:
        """Get list of competitions."""
        if not self.is_connected:
            return []
        return self._execute_query(
            "SELECT * FROM [dbo].[Wyscout_Competition_IDs] ORDER BY [competitions.name]"
        )

    # ── Stat leaders ───────────────────────────────────────────────────

    def get_stat_leaders(self, metric: str, position: str = None,
                         competition: str = None, limit: int = 20) -> List[Dict[str, Any]]:
        """Get top players by a given metric."""
        if not self.is_connected:
            return []

        if competition:
            competition = self._resolve_competition(competition)

        # Validate metric name to prevent SQL injection
        if metric not in self._VALID_METRICS:
            return []

        conditions = [f"[{metric}] IS NOT NULL"]
        params = []

        if position:
            conditions.append(
                "([Main position] LIKE ? OR [Position] LIKE ?)"
            )
            params.extend([f"%{position}%", f"%{position}%"])

        if competition:
            conditions.append("[Competition] LIKE ?")
            params.append(f"%{competition}%")

        where = " AND ".join(conditions)
        order_by = f"season_weight * [{metric}] DESC"

        select = (
            f"[Player ID], [Short name], [First name], [Last name], "
            f"[Age], [Team], [Competition], [Main position], "
            f"[{metric}], [AKARI Skill], [AKARI Potential], "
            f"[Season], season_weight"
        )

        query, _ = self._build_scout_query(select, where, params, order_by, limit)
        return self._execute_query(query, params)

    # ── Discovery ──────────────────────────────────────────────────────

    def get_discoverable_fields(self) -> List[str]:
        """Return the list of all fields that support value discovery."""
        return sorted(list(self._STATIC_VALUES.keys()) + list(self._DYNAMIC_FIELDS.keys()))

    def get_distinct_values(self, field: str) -> Dict[str, Any]:
        """Return distinct valid values for a given filter parameter."""
        # Static fields
        if field in self._STATIC_VALUES:
            entry = self._STATIC_VALUES[field]
            return {
                "field": field,
                "description": entry["description"],
                "values": entry["values"],
                "count": len(entry["values"]),
            }

        if field not in self._DYNAMIC_FIELDS:
            return {"field": field, "description": "Unknown field", "values": [], "count": 0}

        if not self.is_connected:
            return {"field": field, "description": "Database not connected", "values": [], "count": 0}

        meta = self._DYNAMIC_FIELDS[field]
        col = meta["sql_column"]
        description = meta["description"]

        # For competition field, enrich with area info
        if field == "competition":
            return self._discover_competitions(description)

        # Build a distinct query that works with both views and CTE
        if self._use_views:
            query = (
                f"SELECT DISTINCT [{col}] FROM [dbo].[{self._VIEW_NAME}] "
                f"WHERE [{col}] IS NOT NULL ORDER BY [{col}]"
            )
        else:
            query = (
                f"{_SCOUT_PLAYERS_CTE_QUERY} "
                f"SELECT DISTINCT [{col}] FROM scout_all "
                f"WHERE [{col}] IS NOT NULL ORDER BY [{col}]"
            )
        rows = self._execute_query(query)
        values = sorted({r[col] for r in rows if r.get(col)})
        return {"field": field, "description": description, "values": values, "count": len(values)}

    def _discover_competitions(self, description: str) -> Dict[str, Any]:
        """Return distinct competitions enriched with area for disambiguation."""
        field = "competition"

        if self._use_views:
            query = (
                "SELECT DISTINCT [Competition], [Area] "
                f"FROM [dbo].[{self._VIEW_NAME}] "
                "WHERE [Competition] IS NOT NULL "
                "ORDER BY [Area], [Competition]"
            )
        else:
            query = (
                f"{_SCOUT_PLAYERS_CTE_QUERY} "
                "SELECT DISTINCT [Competition], [Area] FROM scout_all "
                "WHERE [Competition] IS NOT NULL "
                "ORDER BY [Area], [Competition]"
            )
        rows = self._execute_query(query)
        values = sorted(
            {f"{r['Competition']} ({r['Area']})" for r in rows
             if r.get('Competition') and r.get('Area')}
        )
        return {"field": field, "description": description,
                "values": values, "count": len(values)}


# Global database instance
db = Database()
