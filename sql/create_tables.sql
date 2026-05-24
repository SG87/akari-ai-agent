-- ============================================================================
-- Akari Scout AI – Create materialized table
-- Creates agent_scout_players as a TABLE (not a view) for fast queries.
-- Populates from 4 season tables + Descriptives_new.
-- Run after grant_permissions.sql has been executed by an admin.
-- ============================================================================

-- Drop existing table/view if exists
IF OBJECT_ID('dbo.agent_scout_players', 'V') IS NOT NULL
    DROP VIEW dbo.agent_scout_players;
GO

IF OBJECT_ID('dbo.agent_scout_players', 'U') IS NOT NULL
    DROP TABLE dbo.agent_scout_players;
GO

-- Create table from season 2024-2025
WITH desc_dedup AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY wyId ORDER BY
            CASE WHEN TM_id IS NOT NULL THEN 0 ELSE 1 END,
            CASE WHEN [Market value] IS NOT NULL THEN 0 ELSE 1 END,
            [seasons.seasonId] DESC
    ) AS _rn FROM [dbo].[Descriptives_new]
), desc_unique AS (SELECT * FROM desc_dedup WHERE _rn = 1)
SELECT
    CAST(0.4 AS float) AS season_weight,
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
INTO [dbo].[agent_scout_players]
FROM [dbo].[AKARI data season 2024-2025] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID];
GO

-- Insert season 2025
WITH desc_dedup AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY wyId ORDER BY
            CASE WHEN TM_id IS NOT NULL THEN 0 ELSE 1 END,
            CASE WHEN [Market value] IS NOT NULL THEN 0 ELSE 1 END,
            [seasons.seasonId] DESC
    ) AS _rn FROM [dbo].[Descriptives_new]
), desc_unique AS (SELECT * FROM desc_dedup WHERE _rn = 1)
INSERT INTO [dbo].[agent_scout_players]
SELECT CAST(0.7 AS float), s.[Player ID],
    d.shortName, d.firstName, d.lastName, s.[Age],
    d.height, d.weight, CAST(d.birthDate AS nvarchar(50)), d.foot,
    d.[birthArea.name], d.[passportArea.name], d.imageDataURL, d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value], d.[Contract expires],
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
FROM [dbo].[AKARI data season 2025] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID];
GO

-- Insert season 2025-2026
WITH desc_dedup AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY wyId ORDER BY
            CASE WHEN TM_id IS NOT NULL THEN 0 ELSE 1 END,
            CASE WHEN [Market value] IS NOT NULL THEN 0 ELSE 1 END,
            [seasons.seasonId] DESC
    ) AS _rn FROM [dbo].[Descriptives_new]
), desc_unique AS (SELECT * FROM desc_dedup WHERE _rn = 1)
INSERT INTO [dbo].[agent_scout_players]
SELECT CAST(0.9 AS float), s.[Player ID],
    d.shortName, d.firstName, d.lastName, s.[Age],
    d.height, d.weight, CAST(d.birthDate AS nvarchar(50)), d.foot,
    d.[birthArea.name], d.[passportArea.name], d.imageDataURL, d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value], d.[Contract expires],
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
FROM [dbo].[AKARI data season 2025-2026] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID];
GO

-- Insert season 2026
WITH desc_dedup AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY wyId ORDER BY
            CASE WHEN TM_id IS NOT NULL THEN 0 ELSE 1 END,
            CASE WHEN [Market value] IS NOT NULL THEN 0 ELSE 1 END,
            [seasons.seasonId] DESC
    ) AS _rn FROM [dbo].[Descriptives_new]
), desc_unique AS (SELECT * FROM desc_dedup WHERE _rn = 1)
INSERT INTO [dbo].[agent_scout_players]
SELECT CAST(1.0 AS float), s.[Player ID],
    d.shortName, d.firstName, d.lastName, s.[Age],
    d.height, d.weight, CAST(d.birthDate AS nvarchar(50)), d.foot,
    d.[birthArea.name], d.[passportArea.name], d.imageDataURL, d.TM_id, d.TM_URL,
    s.[Team ID], s.[Team], s.[Team image], s.[Competition ID], s.[Competition], s.[Competition format],
    s.[Division level], s.[Area], s.[Season], s.[Season ID],
    s.[Role], s.[Position], s.[Main position], s.[Second position], s.[Third position],
    s.[Main position %], s.[Second position %], s.[Third position %],
    s.[Games played], s.[Starting 11 %], s.[Minutes played %], s.[Substituted in %],
    d.[Market value], d.[Contract expires],
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
FROM [dbo].[AKARI data season 2026] s
LEFT JOIN desc_unique d ON d.wyId = s.[Player ID];
GO

-- ============================================================================
-- Indexes for fast lookups
-- ============================================================================
CREATE NONCLUSTERED INDEX [IX_agent_playerid] ON [dbo].[agent_scout_players] ([Player ID]);
CREATE NONCLUSTERED INDEX [IX_agent_shortname] ON [dbo].[agent_scout_players] ([Short name]);
CREATE NONCLUSTERED INDEX [IX_agent_mainpos] ON [dbo].[agent_scout_players] ([Main position]);
CREATE NONCLUSTERED INDEX [IX_agent_competition] ON [dbo].[agent_scout_players] ([Competition]);
CREATE NONCLUSTERED INDEX [IX_agent_age] ON [dbo].[agent_scout_players] ([Age]);
CREATE NONCLUSTERED INDEX [IX_agent_area] ON [dbo].[agent_scout_players] ([Area]);
CREATE NONCLUSTERED INDEX [IX_agent_potential] ON [dbo].[agent_scout_players] ([AKARI Potential] DESC);
CREATE NONCLUSTERED INDEX [IX_agent_skill] ON [dbo].[agent_scout_players] ([AKARI Skill] DESC);
CREATE NONCLUSTERED INDEX [IX_agent_goals] ON [dbo].[agent_scout_players] ([Goals] DESC);
GO

-- Verify
SELECT COUNT(*) AS total_rows FROM [dbo].[agent_scout_players];
SELECT season_weight, COUNT(*) AS rows_per_season FROM [dbo].[agent_scout_players] GROUP BY season_weight ORDER BY season_weight;
GO
