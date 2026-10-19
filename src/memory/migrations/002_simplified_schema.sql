-- Migration: 002_simplified_schema.sql
-- Target: 14 tables per docs/SC2026_database_schema_simplified.md
-- Gate: drops stay commented until preflight COUNT(*)=0 + backup +
-- code refactor all pass. No CASCADE. Live REST preflight 2026-10-19:
-- customer_identities=0, customer_addresses=0, candidates=0, history=0;
-- sessions=5, events=20, episodes=4 kept; orders/order_items missing.

BEGIN;

-- 0. Preflight read-only (run separately, abort if any count > 0):
-- SELECT COUNT(*) FROM public.customer_identities;
-- SELECT COUNT(*) FROM public.customer_addresses;
-- SELECT COUNT(*) FROM public.profile_fact_candidates;
-- SELECT COUNT(*) FROM public.profile_fact_history;

-- 1. customers: flatten identity + default address columns
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS zalo_id TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS fb_id TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS region TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS address_line TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS ward TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS district TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS city TEXT;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS country_code CHAR(2) NOT NULL DEFAULT 'VN';
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS address_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE public.customers ADD COLUMN IF NOT EXISTS source TEXT;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_customers_region') THEN
    ALTER TABLE public.customers ADD CONSTRAINT chk_customers_region
      CHECK (region IS NULL OR region IN ('bac','trung','nam'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_customers_status') THEN
    ALTER TABLE public.customers ADD CONSTRAINT chk_customers_status
      CHECK (status IN ('active','provisional','merged','deleted'));
  END IF;
END $$;

-- Phone NOT unique (seed C034/C035 share one phone).
CREATE INDEX IF NOT EXISTS idx_customers_phone ON public.customers (phone) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_zalo
  ON public.customers (zalo_id) WHERE deleted_at IS NULL AND zalo_id IS NOT NULL AND zalo_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_fb
  ON public.customers (fb_id) WHERE deleted_at IS NULL AND fb_id IS NOT NULL AND fb_id <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_email
  ON public.customers (lower(email)) WHERE deleted_at IS NULL AND email IS NOT NULL AND email <> '';

-- 2. Backup legacy tables before any destructive step (run once):
-- CREATE TABLE IF NOT EXISTS public._backup_customer_identities AS TABLE public.customer_identities;
-- CREATE TABLE IF NOT EXISTS public._backup_customer_addresses AS TABLE public.customer_addresses;
-- CREATE TABLE IF NOT EXISTS public._backup_profile_fact_candidates AS TABLE public.profile_fact_candidates;
-- CREATE TABLE IF NOT EXISTS public._backup_profile_fact_history AS TABLE public.profile_fact_history;

-- 3. orders + order_items (new business tables)
CREATE TABLE IF NOT EXISTS public.orders (
  order_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
  order_date DATE NOT NULL,
  status TEXT NOT NULL,
  tracking_number TEXT,
  total_amount_vnd BIGINT CHECK (total_amount_vnd IS NULL OR total_amount_vnd >= 0),
  currency CHAR(3) NOT NULL DEFAULT 'VND',
  source_system TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_customer_date ON public.orders (customer_id, order_date DESC);
CREATE INDEX IF NOT EXISTS idx_orders_tracking ON public.orders (tracking_number) WHERE tracking_number IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.order_items (
  order_item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id TEXT NOT NULL REFERENCES public.orders(order_id) ON DELETE RESTRICT,
  line_number INTEGER NOT NULL CHECK (line_number > 0),
  sku TEXT NOT NULL,
  product_name_snapshot TEXT,
  quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
  unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),
  line_total_vnd BIGINT NOT NULL CHECK (line_total_vnd >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, line_number)
);
-- No FK sku->catalog: snapshots must survive catalog removal.

-- 4. profile_facts: align names to simplified target
ALTER TABLE public.profile_facts ADD COLUMN IF NOT EXISTS profile_value JSONB;
ALTER TABLE public.profile_facts ADD COLUMN IF NOT EXISTS source_session_id TEXT REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT;
ALTER TABLE public.profile_facts ADD COLUMN IF NOT EXISTS source_event_id UUID REFERENCES public.working_events(event_id) ON DELETE RESTRICT;
ALTER TABLE public.profile_facts ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'customer_stated';
ALTER TABLE public.profile_facts ADD COLUMN IF NOT EXISTS confidence NUMERIC(4,3);

DO $migration$
BEGIN
  -- Chuyển dữ liệu từ tên cột cũ nếu cột cũ còn tồn tại.
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'profile_facts'
      AND column_name = 'profile_value_json'
  ) THEN
    EXECUTE $sql$
      UPDATE public.profile_facts
      SET profile_value = profile_value_json::jsonb
      WHERE profile_value IS NULL
        AND profile_value_json IS NOT NULL
    $sql$;
  END IF;

  -- Chuyển provenance từ tên cột cũ nếu còn tồn tại.
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'profile_facts'
      AND column_name = 'provenance_session_id'
  ) THEN
    EXECUTE $sql$
      UPDATE public.profile_facts
      SET source_session_id = provenance_session_id
      WHERE source_session_id IS NULL
        AND provenance_session_id IS NOT NULL
    $sql$;
  END IF;

  -- Thêm CHECK constraint nếu bảng chưa có constraint này.
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_profile_facts_confidence'
      AND conrelid = 'public.profile_facts'::regclass
  ) THEN
    ALTER TABLE public.profile_facts
      ADD CONSTRAINT chk_profile_facts_confidence
      CHECK (
        confidence IS NULL
        OR (confidence >= 0 AND confidence <= 1)
      );
  END IF;
END
$migration$;

CREATE INDEX IF NOT EXISTS idx_profile_facts_session ON public.profile_facts (source_session_id);

-- 5. Drops ONLY after preflight + backup + refactor. No CASCADE.
-- DROP TABLE IF EXISTS public.customer_identities;
-- DROP TABLE IF EXISTS public.customer_addresses;
-- DROP TABLE IF EXISTS public.profile_fact_candidates;
-- DROP TABLE IF EXISTS public.profile_fact_history;

COMMIT;
