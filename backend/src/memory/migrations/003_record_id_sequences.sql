-- Atomic allocators for new customer, order, and conversation-session IDs.
-- Legacy IDs remain untouched; only matching normalized IDs seed these counters.
BEGIN;

CREATE SEQUENCE IF NOT EXISTS public.customer_id_seq START WITH 1;
CREATE SEQUENCE IF NOT EXISTS public.order_id_seq START WITH 1;
CREATE SEQUENCE IF NOT EXISTS public.session_id_seq START WITH 1;

SELECT setval('public.customer_id_seq',
  GREATEST(COALESCE((SELECT MAX(substring(customer_id FROM '^C([0-9]+)$')::bigint)
    FROM public.customers WHERE customer_id ~ '^C[0-9]+$'), 1), 1),
  COALESCE((SELECT MAX(substring(customer_id FROM '^C([0-9]+)$')::bigint)
    FROM public.customers WHERE customer_id ~ '^C[0-9]+$'), 0) > 0);

SELECT setval('public.order_id_seq',
  GREATEST(COALESCE((SELECT MAX(substring(order_id FROM '^OD([0-9]+)$')::bigint)
    FROM public.orders WHERE order_id ~ '^OD[0-9]+$'), 1), 1),
  COALESCE((SELECT MAX(substring(order_id FROM '^OD([0-9]+)$')::bigint)
    FROM public.orders WHERE order_id ~ '^OD[0-9]+$'), 0) > 0);

SELECT setval('public.session_id_seq',
  GREATEST(COALESCE((SELECT MAX(substring(session_id FROM '^S([0-9]+)$')::bigint)
    FROM public.conversation_sessions WHERE session_id ~ '^S[0-9]+$'), 1), 1),
  COALESCE((SELECT MAX(substring(session_id FROM '^S([0-9]+)$')::bigint)
    FROM public.conversation_sessions WHERE session_id ~ '^S[0-9]+$'), 0) > 0);

COMMIT;
