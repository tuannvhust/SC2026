-- Rollback for 002_simplified_schema.sql (additive parts only)
-- Does NOT restore dropped legacy tables (drops stay commented in 002
-- until gated). Run only if 002 additive apply needs revert.

BEGIN;
DROP TABLE IF EXISTS public.order_items;
DROP TABLE IF EXISTS public.orders;
ALTER TABLE public.profile_facts DROP CONSTRAINT IF EXISTS chk_profile_facts_confidence;
DROP INDEX IF EXISTS public.idx_profile_facts_session;
ALTER TABLE public.profile_facts DROP COLUMN IF EXISTS confidence;
ALTER TABLE public.profile_facts DROP COLUMN IF EXISTS source_kind;
ALTER TABLE public.profile_facts DROP COLUMN IF EXISTS source_event_id;
ALTER TABLE public.profile_facts DROP COLUMN IF EXISTS source_session_id;
ALTER TABLE public.profile_facts DROP COLUMN IF EXISTS profile_value;
DROP INDEX IF EXISTS public.uq_customers_email;
DROP INDEX IF EXISTS public.uq_customers_fb;
DROP INDEX IF EXISTS public.uq_customers_zalo;
DROP INDEX IF EXISTS public.idx_customers_phone;
ALTER TABLE public.customers DROP CONSTRAINT IF EXISTS chk_customers_status;
ALTER TABLE public.customers DROP CONSTRAINT IF EXISTS chk_customers_region;
ALTER TABLE public.customers DROP COLUMN IF EXISTS source;
ALTER TABLE public.customers DROP COLUMN IF EXISTS address_verified;
ALTER TABLE public.customers DROP COLUMN IF EXISTS country_code;
ALTER TABLE public.customers DROP COLUMN IF EXISTS city;
ALTER TABLE public.customers DROP COLUMN IF EXISTS district;
ALTER TABLE public.customers DROP COLUMN IF EXISTS ward;
ALTER TABLE public.customers DROP COLUMN IF EXISTS address_line;
ALTER TABLE public.customers DROP COLUMN IF EXISTS region;
ALTER TABLE public.customers DROP COLUMN IF EXISTS email;
ALTER TABLE public.customers DROP COLUMN IF EXISTS fb_id;
ALTER TABLE public.customers DROP COLUMN IF EXISTS zalo_id;
ALTER TABLE public.customers DROP COLUMN IF EXISTS phone_verified;
ALTER TABLE public.customers DROP COLUMN IF EXISTS phone;
COMMIT;
