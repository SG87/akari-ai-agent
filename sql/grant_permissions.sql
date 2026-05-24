-- ============================================================================
-- Run this with an Azure SQL admin account (e.g. server admin login).
-- Grants Stijn_reader the ability to create tables, views, and indexes.
-- ============================================================================

-- Grant DDL permissions
GRANT CREATE TABLE TO [Stijn_reader];
GRANT CREATE VIEW TO [Stijn_reader];
GRANT ALTER ON SCHEMA::dbo TO [Stijn_reader];

-- Verify
SELECT 
    dp.permission_name, 
    dp.state_desc,
    dp.class_desc
FROM sys.database_permissions dp
WHERE dp.grantee_principal_id = DATABASE_PRINCIPAL_ID('Stijn_reader')
  AND dp.class_desc = 'DATABASE';
