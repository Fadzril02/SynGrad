-- =============================================================================
-- Migration 38: no DB default for credits (DECISIONS.md #9)
-- A row inserted without credits must fail loud, not silently become 3.
-- NOT NULL stays, so a missing value is rejected by the DB.
-- =============================================================================
BEGIN;

ALTER TABLE IF EXISTS academic_records ALTER COLUMN credits DROP DEFAULT;
ALTER TABLE IF EXISTS courses ALTER COLUMN credits DROP DEFAULT;
ALTER TABLE IF EXISTS template_courses ALTER COLUMN credit_hour DROP DEFAULT;

COMMIT;

-- Verify (expect 0 rows):
-- SELECT table_name, column_name, column_default FROM information_schema.columns
-- WHERE table_schema = 'public'
--   AND (table_name, column_name) IN (('academic_records','credits'),('courses','credits'),('template_courses','credit_hour'))
--   AND column_default IS NOT NULL;

-- Rollback:
-- BEGIN;
-- ALTER TABLE IF EXISTS academic_records ALTER COLUMN credits SET DEFAULT 3;
-- ALTER TABLE IF EXISTS courses ALTER COLUMN credits SET DEFAULT 3;
-- ALTER TABLE IF EXISTS template_courses ALTER COLUMN credit_hour SET DEFAULT 3;
-- COMMIT;
