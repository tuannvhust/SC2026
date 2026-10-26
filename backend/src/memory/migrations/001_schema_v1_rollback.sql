-- Migration: 001_schema_v1_rollback.sql
-- Rollback script for Business and Memory Schema v1

BEGIN;

-- Drop tables in reverse order respecting foreign key dependencies
DROP TABLE IF EXISTS public.episodic_memory CASCADE;
DROP TABLE IF EXISTS public.profile_fact_history CASCADE;
DROP TABLE IF EXISTS public.profile_facts CASCADE;
DROP TABLE IF EXISTS public.profile_fact_candidates CASCADE;
DROP TABLE IF EXISTS public.working_events CASCADE;
DROP TABLE IF EXISTS public.conversation_sessions CASCADE;
DROP TABLE IF EXISTS public.customer_addresses CASCADE;
DROP TABLE IF EXISTS public.customer_identities CASCADE;
DROP TABLE IF EXISTS public.customers CASCADE;

COMMIT;
