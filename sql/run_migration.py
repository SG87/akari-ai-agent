"""
Migration script for Akari Scout AI database.
Creates the agent_scout_players materialized table with indexes.

Requires CREATE TABLE and ALTER permissions on the database.
If permissions are missing, prints instructions.

Usage:
    python sql/run_migration.py
"""

import os
import sys
import time

# Add the project root to Python path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pyodbc
from dotenv import load_dotenv

# Load environment variables from the project root
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(_project_root, '.env'))


def get_connection():
    """Create a database connection using environment variables."""
    server = os.getenv('DB_SERVER')
    database = os.getenv('DB_NAME')
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASSWORD')

    connection_string = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        f"Uid={user};"
        f"Pwd={password};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
        f"Connection Timeout=30;"
    )
    return pyodbc.connect(connection_string)


# ── Descriptives CTE (reused for each season insert) ─────────────────────
DESC_CTE = """
WITH desc_dedup AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY wyId ORDER BY
            CASE WHEN TM_id IS NOT NULL THEN 0 ELSE 1 END,
            CASE WHEN [Market value] IS NOT NULL THEN 0 ELSE 1 END,
            [seasons.seasonId] DESC
    ) AS _rn FROM [dbo].[Descriptives_new]
), desc_unique AS (SELECT * FROM desc_dedup WHERE _rn = 1)
"""

# ── Column SELECT list (shared across all season inserts) ─────────────────
COLS = """
    s.[Player ID], d.shortName AS [Short name], d.firstName AS [First name], d.lastName AS [Last name],
    s.[Age], d.height AS [Height], d.weight AS [Weight],
    CAST(d.birthDate AS nvarchar(50)) AS [Birth date], d.foot AS [Foot],
    d.[birthArea.name] AS [Birth area], d.[passportArea.name] AS [Passport area],
    d.imageDataURL AS [player image], d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value] AS [Market value], d.[Contract expires] AS [Contract expires],
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
    s.[AKARI Skill], s.[AKARI Potential], s.[AKARI_Skill_rescaled], s.[AKARI_Potential_rescaled],
    s.[benchmark.successfulKeyPasses.average], s.[benchmark.successfulPassesToFinalThird.average],
    s.[benchmark.shots.average], s.[benchmark.aerialDuelsWon.average],
    s.[benchmark.gkConcededGoals.average], s.[benchmark.xgSave.average],
    s.[benchmark.interceptions.average], s.[benchmark.successfulLongPasses.average],
    s.[benchmark.dangerousOwnHalfLosses.average], s.[benchmark.successfulSlidingTackles.average],
    s.[benchmark.newSuccessfulDribbles.average], s.[benchmark.xgAssist.average],
    s.[benchmark.xgShot.average], s.[benchmark.gkSaves.average],
    s.[benchmark.chancesCreated.average], s.[benchmark.gkShotsAgainst.average],
    s.[benchmark.gkSaves.percent], s.[benchmark.AKARI.skill.average],
    s.[benchmark.gkcleansheets.percent]
"""

SEASONS = [
    ("AKARI data season 2024-2025", 0.4),
    ("AKARI data season 2025", 0.7),
    ("AKARI data season 2025-2026", 0.9),
    ("AKARI data season 2026", 1.0),
]

INDEXES = [
    ("IX_agent_playerid", "[Player ID]"),
    ("IX_agent_shortname", "[Short name]"),
    ("IX_agent_mainpos", "[Main position]"),
    ("IX_agent_competition", "[Competition]"),
    ("IX_agent_age", "[Age]"),
    ("IX_agent_area", "[Area]"),
    ("IX_agent_potential", "[AKARI Potential] DESC"),
    ("IX_agent_skill", "[AKARI Skill] DESC"),
    ("IX_agent_goals", "[Goals] DESC"),
]


def check_existing(conn) -> dict:
    """Check if agent_scout_players exists as a table or view."""
    cursor = conn.cursor()
    result = {"table": False, "view": False, "rows": 0}

    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_NAME = 'agent_scout_players' AND TABLE_TYPE = 'BASE TABLE'"
    )
    result["table"] = cursor.fetchone()[0] > 0

    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS "
        "WHERE TABLE_NAME = 'agent_scout_players'"
    )
    result["view"] = cursor.fetchone()[0] > 0

    if result["table"]:
        cursor.execute("SELECT COUNT(*) FROM [dbo].[agent_scout_players]")
        result["rows"] = cursor.fetchone()[0]

    return result


def create_table(conn):
    """Create the materialized agent_scout_players table."""
    cursor = conn.cursor()

    # Drop existing view if present (table takes priority)
    cursor.execute(
        "IF OBJECT_ID('dbo.agent_scout_players', 'V') IS NOT NULL "
        "DROP VIEW dbo.agent_scout_players"
    )
    conn.commit()

    # Drop existing table if present
    cursor.execute(
        "IF OBJECT_ID('dbo.agent_scout_players', 'U') IS NOT NULL "
        "DROP TABLE dbo.agent_scout_players"
    )
    conn.commit()

    # Create table from first season using SELECT INTO
    first_table, first_weight = SEASONS[0]
    print(f"  Creating from {first_table} (weight={first_weight})...")
    t0 = time.time()

    create_sql = f"""
    {DESC_CTE}
    SELECT CAST({first_weight} AS float) AS season_weight, {COLS}
    INTO [dbo].[agent_scout_players]
    FROM [dbo].[{first_table}] s
    LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]
    """
    cursor.execute(create_sql)
    conn.commit()
    cursor.execute("SELECT COUNT(*) FROM [dbo].[agent_scout_players]")
    count = cursor.fetchone()[0]
    print(f"    ✓ {count:,} rows ({time.time()-t0:.1f}s)")

    # Insert remaining seasons
    for table_name, weight in SEASONS[1:]:
        print(f"  Inserting {table_name} (weight={weight})...")
        t0 = time.time()

        insert_sql = f"""
        {DESC_CTE}
        INSERT INTO [dbo].[agent_scout_players]
        SELECT CAST({weight} AS float), {COLS}
        FROM [dbo].[{table_name}] s
        LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]
        """
        cursor.execute(insert_sql)
        conn.commit()
        print(f"    ✓ done ({time.time()-t0:.1f}s)")

    cursor.execute("SELECT COUNT(*) FROM [dbo].[agent_scout_players]")
    total = cursor.fetchone()[0]
    return total


def create_indexes(conn):
    """Add indexes for fast lookups."""
    cursor = conn.cursor()
    for idx_name, col in INDEXES:
        t0 = time.time()
        try:
            cursor.execute(
                f"CREATE NONCLUSTERED INDEX [{idx_name}] "
                f"ON [dbo].[agent_scout_players] ({col})"
            )
            conn.commit()
            print(f"  ✅ {idx_name} ({time.time()-t0:.1f}s)")
        except Exception as e:
            if "already exists" in str(e):
                print(f"  ⏭️  {idx_name} (already exists)")
            else:
                print(f"  ⚠️  {idx_name}: {e}")


def verify_data(conn):
    """Verify the table has correct data."""
    cursor = conn.cursor()

    cursor.execute(
        "SELECT season_weight, COUNT(*) AS cnt "
        "FROM [dbo].[agent_scout_players] "
        "GROUP BY season_weight ORDER BY season_weight"
    )
    print("  Season breakdown:")
    for row in cursor.fetchall():
        print(f"    weight={row[0]}: {row[1]:,} rows")

    cursor.execute(
        "SELECT COUNT(DISTINCT [Player ID]) FROM [dbo].[agent_scout_players]"
    )
    print(f"  Unique players: {cursor.fetchone()[0]:,}")

    cursor.execute(
        "SELECT COUNT(*) FROM [dbo].[agent_scout_players] WHERE TM_id IS NOT NULL"
    )
    print(f"  With Transfermarkt ID: {cursor.fetchone()[0]:,}")


def main():
    print("🔌 Connecting to database...")
    conn = get_connection()
    print(f"✅ Connected as {os.getenv('DB_USER')}\n")

    # Step 1: Check what exists
    print("📋 Step 1: Checking existing objects...")
    existing = check_existing(conn)
    if existing["table"]:
        print(f"  ✅ agent_scout_players TABLE exists ({existing['rows']:,} rows)")
        print("  ℹ️  Re-creating to refresh data...\n")
    elif existing["view"]:
        print("  ⚠️  agent_scout_players exists as VIEW — will replace with TABLE\n")
    else:
        print("  ❌ agent_scout_players not found — will create\n")

    # Step 2: Create table
    print("📋 Step 2: Creating agent_scout_players table...")
    t0 = time.time()
    try:
        total = create_table(conn)
        elapsed = time.time() - t0
        print(f"  ✅ Table created: {total:,} total rows in {elapsed:.1f}s\n")
    except pyodbc.ProgrammingError as e:
        if 'permission' in str(e).lower() or 'CREATE TABLE' in str(e):
            print(f"\n  ❌ CREATE TABLE permission denied.")
            print(f"  Run sql/grant_permissions.sql with an admin account first.")
            print(f"  Error: {e}")
            conn.close()
            return
        raise

    # Step 3: Create indexes
    print("📋 Step 3: Creating indexes...")
    create_indexes(conn)

    # Step 4: Verify
    print("\n📋 Step 4: Verifying data...")
    verify_data(conn)

    conn.close()
    print("\n🎉 Done! The agent will now use the indexed table for fast queries.")


if __name__ == '__main__':
    main()
