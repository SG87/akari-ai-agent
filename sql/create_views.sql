-- ============================================================================
-- Akari Scout AI – Database Views
-- Creates views for recent season data to serve the AI scouting agent
-- Seasons: 2024-2025 (lower weight), 2025, 2025-2026, 2026
--
-- Player identity data (name, birth date, height, market value, etc.)
-- comes EXCLUSIVELY from Descriptives_new, joined by wyId = Player ID.
-- Statistics, competition context, and AKARI scores come from season tables.
-- Season tables are NOT used for any descriptive fields.
-- ============================================================================

-- Drop existing views if they exist
IF OBJECT_ID('dbo.agent_scout_players', 'V') IS NOT NULL
    DROP VIEW dbo.agent_scout_players;
GO

IF OBJECT_ID('dbo.agent_scout_detailed_stats', 'V') IS NOT NULL
    DROP VIEW dbo.agent_scout_detailed_stats;
GO

-- ============================================================================
-- VIEW 1: agent_scout_players
-- Unified player profiles with key stats from recent AKARI season tables.
-- Player identity sourced EXCLUSIVELY from Descriptives_new (joined on wyId).
-- Includes season_weight: 0.4 → 0.7 → 0.9 → 1.0 for recency ranking.
-- ============================================================================
CREATE VIEW dbo.agent_scout_players AS

-- Helper CTE: deduplicate Descriptives_new to one row per player
-- (picks the row with the most recent TM_id / Market value data)
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

SELECT
    -- Season weight
    0.4 AS season_weight,

    -- Identity (ONLY from Descriptives_new)
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

    -- Transfermarkt ID (from Descriptives_new)
    d.TM_id AS [TM_id],
    d.TM_URL AS [TM_URL],

    -- Team & Competition (from season table — season-specific)
    s.[Team ID],
    s.[Team],
    s.[Team image],
    s.[Competition ID],
    s.[Competition],
    s.[Competition format],
    s.[Division level],
    s.[Area],
    s.[Season],
    s.[Season ID],

    -- Position (from season table)
    s.[Role],
    s.[Position],
    s.[Main position],
    s.[Second position],
    s.[Third position],
    s.[Main position %],
    s.[Second position %],
    s.[Third position %],

    -- Playing time
    s.[Games played],
    s.[Starting 11 %],
    s.[Minutes played %],
    s.[Substituted in %],

    -- Contract & Market (ONLY from Descriptives_new)
    d.[Market value] AS [Market value],
    d.[Contract expires] AS [Contract expires],

    -- Attacking stats (per 90)
    s.[Goals],
    s.[Assists],
    s.[xG ],
    s.[xA ],
    s.[Shots ],
    s.[Successful key passes ],
    s.[Chances created ],
    s.[Progressive runs ],
    s.[Successful progressive passes ],
    s.[Touches in box ],
    s.[Successful dribbles ],
    s.[Offensive duels won ],
    s.[Successful passes to final third ],
    s.[Successful through passes ],
    s.[Successful long passes ],
    s.[Successful passes into penalty box ],
    s.[Shot assists ],
    s.[Third assists ],
    s.[Fouls suffered ],
    s.[Vertical passes ],

    -- Defensive stats (per 90)
    s.[Ball recoveries ],
    s.[Interceptions ],
    s.[Successful defensive actions ],
    s.[Clearances ],
    s.[Duels won ],
    s.[Defensive duels won ],
    s.[Aerial duels won],
    s.[Loose ball duels won ],
    s.[Successful sliding tackles ],
    s.[Opponent half recoveries ],
    s.[Headers ],

    -- Negative stats
    s.[Losses ],
    s.[Dangerous own half losses ],
    s.[Bad ball controls],

    -- Passing
    s.[Passes ],
    s.[Pass length average],

    -- Percentages
    s.[Pass accuracy %],
    s.[Cross accuracy %],
    s.[Shots on target %],
    s.[Chances conversion %],
    s.[Duels won %],
    s.[Aerial duels won %],
    s.[Successful sliding tackles %],
    s.[xG conversion %],

    -- GK stats
    s.[xG Save ],
    s.[gK shots saved %],
    s.[Clean sheet %],
    s.[Goal kicks short ],
    s.[Goal kicks long ],
    s.[gk Exits ],
    s.[gk Successful exits ],
    s.[gk xG - conceded],

    -- AKARI KPIs
    s.[AKARI Skill],
    s.[AKARI Potential],
    s.[AKARI_Skill_rescaled],
    s.[AKARI_Potential_rescaled],

    -- Benchmarks
    s.[benchmark.successfulKeyPasses.average],
    s.[benchmark.successfulPassesToFinalThird.average],
    s.[benchmark.shots.average],
    s.[benchmark.aerialDuelsWon.average],
    s.[benchmark.gkConcededGoals.average],
    s.[benchmark.xgSave.average],
    s.[benchmark.interceptions.average],
    s.[benchmark.successfulLongPasses.average],
    s.[benchmark.dangerousOwnHalfLosses.average],
    s.[benchmark.successfulSlidingTackles.average],
    s.[benchmark.newSuccessfulDribbles.average],
    s.[benchmark.xgAssist.average],
    s.[benchmark.xgShot.average],
    s.[benchmark.gkSaves.average],
    s.[benchmark.chancesCreated.average],
    s.[benchmark.gkShotsAgainst.average],
    s.[benchmark.gkSaves.percent],
    s.[benchmark.AKARI.skill.average],
    s.[benchmark.gkcleansheets.percent]

FROM [dbo].[AKARI data season 2024-2025] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]

UNION ALL

SELECT
    0.7 AS season_weight,
    s.[Player ID],
    d.shortName, d.firstName, d.lastName,
    s.[Age],
    d.height, d.weight, CAST(d.birthDate AS nvarchar(50)), d.foot,
    d.[birthArea.name], d.[passportArea.name], d.imageDataURL,
    d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value], d.[Contract expires],
    s.[Goals], s.[Assists], s.[xG ], s.[xA ], s.[Shots ], s.[Successful key passes ],
    s.[Chances created ], s.[Progressive runs ], s.[Successful progressive passes ],
    s.[Touches in box ], s.[Successful dribbles ], s.[Offensive duels won ],
    s.[Successful passes to final third ], s.[Successful through passes ],
    s.[Successful long passes ], s.[Successful passes into penalty box ],
    s.[Shot assists ], s.[Third assists ], s.[Fouls suffered ], s.[Vertical passes ],
    s.[Ball recoveries ], s.[Interceptions ], s.[Successful defensive actions ],
    s.[Clearances ], s.[Duels won ], s.[Defensive duels won ], s.[Aerial duels won],
    s.[Loose ball duels won ], s.[Successful sliding tackles ], s.[Opponent half recoveries ],
    s.[Headers ],
    s.[Losses ], s.[Dangerous own half losses ], s.[Bad ball controls],
    s.[Passes ], s.[Pass length average],
    s.[Pass accuracy %], s.[Cross accuracy %], s.[Shots on target %], s.[Chances conversion %],
    s.[Duels won %], s.[Aerial duels won %], s.[Successful sliding tackles %], s.[xG conversion %],
    s.[xG Save ], s.[gK shots saved %], s.[Clean sheet %], s.[Goal kicks short ],
    s.[Goal kicks long ], s.[gk Exits ], s.[gk Successful exits ], s.[gk xG - conceded],
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
FROM [dbo].[AKARI data season 2025] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]

UNION ALL

SELECT
    0.9 AS season_weight,
    s.[Player ID],
    d.shortName, d.firstName, d.lastName,
    s.[Age],
    d.height, d.weight, CAST(d.birthDate AS nvarchar(50)), d.foot,
    d.[birthArea.name], d.[passportArea.name], d.imageDataURL,
    d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value], d.[Contract expires],
    s.[Goals], s.[Assists], s.[xG ], s.[xA ], s.[Shots ], s.[Successful key passes ],
    s.[Chances created ], s.[Progressive runs ], s.[Successful progressive passes ],
    s.[Touches in box ], s.[Successful dribbles ], s.[Offensive duels won ],
    s.[Successful passes to final third ], s.[Successful through passes ],
    s.[Successful long passes ], s.[Successful passes into penalty box ],
    s.[Shot assists ], s.[Third assists ], s.[Fouls suffered ], s.[Vertical passes ],
    s.[Ball recoveries ], s.[Interceptions ], s.[Successful defensive actions ],
    s.[Clearances ], s.[Duels won ], s.[Defensive duels won ], s.[Aerial duels won],
    s.[Loose ball duels won ], s.[Successful sliding tackles ], s.[Opponent half recoveries ],
    s.[Headers ],
    s.[Losses ], s.[Dangerous own half losses ], s.[Bad ball controls],
    s.[Passes ], s.[Pass length average],
    s.[Pass accuracy %], s.[Cross accuracy %], s.[Shots on target %], s.[Chances conversion %],
    s.[Duels won %], s.[Aerial duels won %], s.[Successful sliding tackles %], s.[xG conversion %],
    s.[xG Save ], s.[gK shots saved %], s.[Clean sheet %], s.[Goal kicks short ],
    s.[Goal kicks long ], s.[gk Exits ], s.[gk Successful exits ], s.[gk xG - conceded],
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
FROM [dbo].[AKARI data season 2025-2026] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID]

UNION ALL

SELECT
    1.0 AS season_weight,
    s.[Player ID],
    d.shortName, d.firstName, d.lastName,
    s.[Age],
    d.height, d.weight, CAST(d.birthDate AS nvarchar(50)), d.foot,
    d.[birthArea.name], d.[passportArea.name], d.imageDataURL,
    d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value], d.[Contract expires],
    s.[Goals], s.[Assists], s.[xG ], s.[xA ], s.[Shots ], s.[Successful key passes ],
    s.[Chances created ], s.[Progressive runs ], s.[Successful progressive passes ],
    s.[Touches in box ], s.[Successful dribbles ], s.[Offensive duels won ],
    s.[Successful passes to final third ], s.[Successful through passes ],
    s.[Successful long passes ], s.[Successful passes into penalty box ],
    s.[Shot assists ], s.[Third assists ], s.[Fouls suffered ], s.[Vertical passes ],
    s.[Ball recoveries ], s.[Interceptions ], s.[Successful defensive actions ],
    s.[Clearances ], s.[Duels won ], s.[Defensive duels won ], s.[Aerial duels won],
    s.[Loose ball duels won ], s.[Successful sliding tackles ], s.[Opponent half recoveries ],
    s.[Headers ],
    s.[Losses ], s.[Dangerous own half losses ], s.[Bad ball controls],
    s.[Passes ], s.[Pass length average],
    s.[Pass accuracy %], s.[Cross accuracy %], s.[Shots on target %], s.[Chances conversion %],
    s.[Duels won %], s.[Aerial duels won %], s.[Successful sliding tackles %], s.[xG conversion %],
    s.[xG Save ], s.[gK shots saved %], s.[Clean sheet %], s.[Goal kicks short ],
    s.[Goal kicks long ], s.[gk Exits ], s.[gk Successful exits ], s.[gk xG - conceded],
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
FROM [dbo].[AKARI data season 2026] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID];

GO

-- ============================================================================
-- VIEW 2: agent_scout_detailed_stats
-- Detailed per-90 stats from All_statistics_current joined with Descriptives_new
-- ============================================================================
CREATE VIEW dbo.agent_scout_detailed_stats AS

SELECT
    -- Player identity (from Descriptives_new)
    d.wyId AS player_id,
    d.shortName AS short_name,
    d.firstName AS first_name,
    d.lastName AS last_name,
    d.birthDate AS birth_date,
    d.height,
    d.weight,
    d.foot,
    d.imageDataURL AS player_image,
    d.[birthArea.name] AS birth_area,
    d.[passportArea.name] AS passport_area,
    d.[role.name] AS role,
    d.[Market value] AS market_value,
    d.[Contract expires] AS contract_expires,
    d.[Birth country] AS birth_country,

    -- Transfermarkt ID (from Descriptives_new)
    d.TM_id AS tm_id,
    d.TM_URL AS tm_url,

    -- Season & Competition context
    s.[seasons.seasonId] AS season_id,
    s.competitionId AS competition_id,

    -- Position
    s.position1_name,
    s.position1_percent,
    s.position2_name,
    s.position2_percent,
    s.position3_name,
    s.position3_percent,
    s.[Simplified.Position] AS simplified_position,
    s.PositionsShortCode AS position_short_code,

    -- Playing time
    s.[matches.total] AS matches_total,
    s.[matchesInStart.total] AS matches_in_start,
    s.[minutesOnField.total] AS minutes_on_field,
    s.[percentage.starting11] AS pct_starting11,
    s.[percentage.substitutedin] AS pct_substituted_in,
    s.[percentage.minutesplayed] AS pct_minutes_played,

    -- Goals & Scoring
    s.[goals.total] AS goals_total,
    s.[goals.average] AS goals_avg,
    s.[assists.total] AS assists_total,
    s.[assists.average] AS assists_avg,
    s.[shots.total] AS shots_total,
    s.[shots.average] AS shots_avg,
    s.[headShots.average] AS head_shots_avg,
    s.[xgShot.total] AS xg_total,
    s.[xgShot.average] AS xg_avg,
    s.[xgAssist.total] AS xa_total,
    s.[xgAssist.average] AS xa_avg,
    s.[shotsOnTarget.percent] AS shots_on_target_pct,
    s.[goalConversion.percent] AS goal_conversion_pct,

    -- Passing
    s.[passes.average] AS passes_avg,
    s.[successfulPasses.percent] AS pass_accuracy_pct,
    s.[passLength.average] AS pass_length_avg,
    s.[successfulKeyPasses.average] AS key_passes_avg,
    s.[successfulSmartPasses.average] AS smart_passes_avg,
    s.[successfulPassesToFinalThird.average] AS passes_final_third_avg,
    s.[successfulThroughPasses.average] AS through_passes_avg,
    s.[successfulLongPasses.average] AS long_passes_avg,
    s.[successfulProgressivePasses.average] AS progressive_passes_avg,
    s.[successfulCrosses.percent] AS cross_accuracy_pct,
    s.[verticalPasses.average] AS vertical_passes_avg,
    s.[shotAssists.average] AS shot_assists_avg,

    -- Dribbling & Creativity
    s.[successfulDribbles.average] AS dribbles_avg,
    s.[newSuccessfulDribbles.average] AS new_dribbles_avg,
    s.[touchInBox.average] AS touch_in_box_avg,
    s.[progressiveRun.average] AS progressive_runs_avg,
    s.[successfulAttackingActions.average] AS attacking_actions_avg,

    -- Duels
    s.[duelsWon.average] AS duels_won_avg,
    s.[duelsWon.percent] AS duels_won_pct,
    s.[defensiveDuelsWon.average] AS def_duels_won_avg,
    s.[defensiveDuelsWon.percent] AS def_duels_won_pct,
    s.[offensiveDuelsWon.average] AS off_duels_won_avg,
    s.[aerialDuelsWon.percent] AS aerial_duels_won_pct,
    s.[looseBallDuelsWon.average] AS loose_ball_duels_avg,
    s.[newDuelsWon.percent] AS new_duels_won_pct,

    -- Defensive
    s.[interceptions.average] AS interceptions_avg,
    s.[successfulDefensiveAction.average] AS def_actions_avg,
    s.[clearances.average] AS clearances_avg,
    s.[successfulSlidingTackles.average] AS sliding_tackles_avg,
    s.[successfulSlidingTackles.percent] AS sliding_tackles_pct,
    s.[ballRecoveries.average] AS ball_recoveries_avg,
    s.[opponentHalfRecoveries.average] AS opp_half_recoveries_avg,

    -- Losses
    s.[losses.average] AS losses_avg,
    s.[dangerousOwnHalfLosses.average] AS dangerous_losses_avg,
    s.[missedBalls.average] AS missed_balls_avg,

    -- GK stats
    s.[gkSaves.percent] AS gk_saves_pct,
    s.[gkConcededGoals.total] AS gk_conceded_total,
    s.[gkConcededGoals.average] AS gk_conceded_avg,
    s.[gkExits.average] AS gk_exits_avg,
    s.[gkSuccessfulExits.average] AS gk_successful_exits_avg,
    s.[xgSave.total] AS xg_save_total,
    s.[xgSave.average] AS xg_save_avg,
    s.[gkCleanSheets.total] AS gk_clean_sheets,

    -- Discipline
    s.[foulsSuffered.average] AS fouls_suffered_avg,

    -- AKARI & League
    s.mean_AKARI AS akari_score,
    s.[League.Strength.Coefficient] AS league_strength_coefficient,

    -- Team
    s.[team.id] AS team_id

FROM [dbo].[All_statistics_current] s
INNER JOIN [dbo].[Descriptives_new] d
    ON s.wyId = CAST(d.wyId AS varchar(255));

GO
