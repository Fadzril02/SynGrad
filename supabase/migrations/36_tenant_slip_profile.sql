-- =============================================================================
-- Migration 36: Tenant slip parsing profile (Universal Slip Reader Foundation)
--
-- Adds slip_profile to tenants table to support university-specific rule parsers
-- ('utm') vs the universal AI slip reader (NULL).
-- =============================================================================
BEGIN;

-- 1. tenants: Add slip_profile (TEXT NULL)
ALTER TABLE public.tenants
    ADD COLUMN IF NOT EXISTS slip_profile TEXT NULL;

-- 2. Configure 'utm' profile for UTM tenant
UPDATE public.tenants
SET slip_profile = 'utm'
WHERE id = 'UTM';

COMMIT;

-- =============================================================================
-- VERIFY QUERIES
-- =============================================================================
-- 1. Verify slip_profile column on tenants:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'slip_profile';
--
-- 2. Verify UTM tenant has slip_profile = 'utm':
-- SELECT id, name, slip_profile FROM public.tenants WHERE id = 'UTM';

/*
-- =============================================================================
-- ROLLBACK
-- =============================================================================
BEGIN;
ALTER TABLE public.tenants DROP COLUMN IF EXISTS slip_profile;
COMMIT;
*/
