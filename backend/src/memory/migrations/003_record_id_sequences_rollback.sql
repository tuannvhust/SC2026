-- Remove only the newly introduced allocators; preserve all CRM records.
BEGIN;
DROP SEQUENCE IF EXISTS public.session_id_seq;
DROP SEQUENCE IF EXISTS public.order_id_seq;
DROP SEQUENCE IF EXISTS public.customer_id_seq;
COMMIT;
