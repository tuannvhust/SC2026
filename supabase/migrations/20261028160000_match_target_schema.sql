-- Đưa database (baseline + align) về đúng thiết kế trong
-- supabase/schema-target/20261028150000_initial_customer_service_schema.sql.
-- Bỏ bảng app không có trong file đó: working_events, episodic_memory,
-- checkpoint LangGraph, và các cột/trigger đồng bộ tên cũ.

-- ---------------------------------------------------------------------------
-- 1. Bỏ trigger, hàm và bảng không thuộc thiết kế
-- ---------------------------------------------------------------------------

DROP TRIGGER IF EXISTS trg_customers_sync_name ON public.customers;
DROP TRIGGER IF EXISTS trg_orders_sync_amounts ON public.orders;
DROP TRIGGER IF EXISTS trg_promotions_sync_schedule ON public.promotions;
DROP TRIGGER IF EXISTS trg_update_product_stats ON public.product_variants;

DROP EVENT TRIGGER IF EXISTS ensure_rls;

DROP FUNCTION IF EXISTS public.customers_sync_name();
DROP FUNCTION IF EXISTS public.orders_sync_amounts();
DROP FUNCTION IF EXISTS public.promotions_sync_schedule();
DROP FUNCTION IF EXISTS public.update_product_aggregated_stats();
DROP FUNCTION IF EXISTS public.rls_auto_enable();

ALTER TABLE public.profile_facts
  DROP CONSTRAINT IF EXISTS profile_facts_source_event_id_fkey;

DROP TABLE IF EXISTS public.checkpoint_blobs;
DROP TABLE IF EXISTS public.checkpoint_writes;
DROP TABLE IF EXISTS public.checkpoint_migrations;
DROP TABLE IF EXISTS public.checkpoints;
DROP TABLE IF EXISTS public.episodic_memory;
DROP TABLE IF EXISTS public.working_events;

DROP SEQUENCE IF EXISTS public.customer_id_seq;
DROP SEQUENCE IF EXISTS public.order_id_seq;
DROP SEQUENCE IF EXISTS public.session_id_seq;

-- ---------------------------------------------------------------------------
-- 2. Customers
-- ---------------------------------------------------------------------------

UPDATE public.customers
SET name = COALESCE(name, preferred_name, full_name)
WHERE name IS NULL
  AND COALESCE(preferred_name, full_name) IS NOT NULL;

UPDATE public.customers
SET zalo_id = NULL
WHERE zalo_id IS NOT NULL AND btrim(zalo_id) = '';

UPDATE public.customers
SET fb_id = NULL
WHERE fb_id IS NOT NULL AND btrim(fb_id) = '';

WITH ranked AS (
  SELECT customer_id,
         row_number() OVER (PARTITION BY zalo_id ORDER BY customer_id) AS n
  FROM public.customers
  WHERE zalo_id IS NOT NULL
)
UPDATE public.customers AS customer
SET zalo_id = NULL
FROM ranked
WHERE customer.customer_id = ranked.customer_id
  AND ranked.n > 1;

WITH ranked AS (
  SELECT customer_id,
         row_number() OVER (PARTITION BY fb_id ORDER BY customer_id) AS n
  FROM public.customers
  WHERE fb_id IS NOT NULL
)
UPDATE public.customers AS customer
SET fb_id = NULL
FROM ranked
WHERE customer.customer_id = ranked.customer_id
  AND ranked.n > 1;

DROP INDEX IF EXISTS public.idx_customers_phone;
DROP INDEX IF EXISTS public.idx_customers_status;
DROP INDEX IF EXISTS public.uq_customers_email;
DROP INDEX IF EXISTS public.uq_customers_fb;
DROP INDEX IF EXISTS public.uq_customers_zalo;

ALTER TABLE public.customers
  DROP CONSTRAINT IF EXISTS chk_customers_region,
  DROP CONSTRAINT IF EXISTS chk_customers_status,
  DROP CONSTRAINT IF EXISTS customers_status_check;

ALTER TABLE public.customers
  ALTER COLUMN status DROP NOT NULL,
  ALTER COLUMN status DROP DEFAULT;

ALTER TABLE public.customers
  DROP COLUMN IF EXISTS full_name,
  DROP COLUMN IF EXISTS preferred_name,
  DROP COLUMN IF EXISTS deleted_at,
  DROP COLUMN IF EXISTS phone_verified,
  DROP COLUMN IF EXISTS email,
  DROP COLUMN IF EXISTS ward,
  DROP COLUMN IF EXISTS district,
  DROP COLUMN IF EXISTS city,
  DROP COLUMN IF EXISTS country_code,
  DROP COLUMN IF EXISTS address_verified,
  DROP COLUMN IF EXISTS source;

ALTER TABLE public.customers
  DROP CONSTRAINT IF EXISTS customers_zalo_id_key,
  DROP CONSTRAINT IF EXISTS customers_fb_id_key;

ALTER TABLE public.customers
  ADD CONSTRAINT customers_zalo_id_key UNIQUE (zalo_id),
  ADD CONSTRAINT customers_fb_id_key UNIQUE (fb_id);

-- ---------------------------------------------------------------------------
-- 3. Conversation sessions
-- ---------------------------------------------------------------------------

UPDATE public.conversation_sessions
SET ended_at = started_at
WHERE ended_at IS NOT NULL AND ended_at < started_at;

DROP INDEX IF EXISTS public.idx_conversation_sessions_customer;
DROP INDEX IF EXISTS public.idx_conversation_sessions_status;
DROP INDEX IF EXISTS public.conversation_sessions_call_date_idx;

ALTER TABLE public.conversation_sessions
  DROP CONSTRAINT IF EXISTS conversation_sessions_status_check,
  DROP CONSTRAINT IF EXISTS conversation_sessions_call_brief_revision_check,
  DROP CONSTRAINT IF EXISTS conversation_sessions_customer_id_fkey;

ALTER TABLE public.conversation_sessions
  ALTER COLUMN channel DROP NOT NULL,
  ALTER COLUMN channel DROP DEFAULT,
  ALTER COLUMN status DROP NOT NULL,
  ALTER COLUMN status DROP DEFAULT;

ALTER TABLE public.conversation_sessions
  DROP COLUMN IF EXISTS last_activity_at,
  DROP COLUMN IF EXISTS finalized_at,
  DROP COLUMN IF EXISTS handoff_reason,
  DROP COLUMN IF EXISTS call_brief_revision,
  DROP COLUMN IF EXISTS call_brief_updated_at,
  DROP COLUMN IF EXISTS created_at,
  DROP COLUMN IF EXISTS updated_at;

ALTER TABLE public.conversation_sessions
  ADD CONSTRAINT conversation_sessions_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE SET NULL;

ALTER TABLE public.conversation_sessions
  DROP CONSTRAINT IF EXISTS conversation_sessions_time_check;

ALTER TABLE public.conversation_sessions
  ADD CONSTRAINT conversation_sessions_time_check
  CHECK (ended_at IS NULL OR ended_at >= started_at);

-- ---------------------------------------------------------------------------
-- 4. Orders and order items
-- ---------------------------------------------------------------------------

UPDATE public.orders
SET tracking = COALESCE(tracking, tracking_number)
WHERE tracking IS NULL AND tracking_number IS NOT NULL;

UPDATE public.orders
SET total_vnd = COALESCE(total_vnd, total_amount_vnd, 0);

WITH ranked AS (
  SELECT order_id,
         row_number() OVER (PARTITION BY tracking ORDER BY order_id) AS n
  FROM public.orders
  WHERE tracking IS NOT NULL
)
UPDATE public.orders AS ord
SET tracking = NULL
FROM ranked
WHERE ord.order_id = ranked.order_id
  AND ranked.n > 1;

DROP INDEX IF EXISTS public.idx_orders_customer_date;
DROP INDEX IF EXISTS public.idx_orders_tracking;

ALTER TABLE public.orders
  DROP CONSTRAINT IF EXISTS orders_total_amount_vnd_check,
  DROP CONSTRAINT IF EXISTS orders_total_vnd_check;

ALTER TABLE public.orders
  ALTER COLUMN total_vnd SET DEFAULT 0,
  ALTER COLUMN total_vnd SET NOT NULL,
  ALTER COLUMN status DROP NOT NULL,
  ALTER COLUMN order_date SET DEFAULT CURRENT_DATE;

ALTER TABLE public.orders
  ADD CONSTRAINT orders_total_vnd_check CHECK (total_vnd >= 0);

ALTER TABLE public.orders
  DROP COLUMN IF EXISTS tracking_number,
  DROP COLUMN IF EXISTS total_amount_vnd,
  DROP COLUMN IF EXISTS currency,
  DROP COLUMN IF EXISTS source_system,
  DROP COLUMN IF EXISTS updated_at;

DROP INDEX IF EXISTS public.orders_tracking_unique;
CREATE UNIQUE INDEX orders_tracking_unique
  ON public.orders (tracking)
  WHERE tracking IS NOT NULL;

UPDATE public.order_items
SET line_total_vnd = quantity * unit_price_vnd
WHERE line_total_vnd IS DISTINCT FROM quantity * unit_price_vnd;

ALTER TABLE public.order_items
  DROP CONSTRAINT IF EXISTS order_items_line_number_check,
  DROP CONSTRAINT IF EXISTS order_items_order_id_line_number_key,
  DROP CONSTRAINT IF EXISTS order_items_order_id_fkey,
  DROP CONSTRAINT IF EXISTS order_items_line_total_check;

ALTER TABLE public.order_items
  ALTER COLUMN quantity DROP DEFAULT;

ALTER TABLE public.order_items
  DROP COLUMN IF EXISTS line_number,
  DROP COLUMN IF EXISTS product_name_snapshot,
  DROP COLUMN IF EXISTS created_at;

ALTER TABLE public.order_items
  ADD CONSTRAINT order_items_order_id_fkey
  FOREIGN KEY (order_id) REFERENCES public.orders (order_id) ON DELETE CASCADE;

ALTER TABLE public.order_items
  ADD CONSTRAINT order_items_line_total_check
  CHECK (line_total_vnd = quantity * unit_price_vnd);

-- ---------------------------------------------------------------------------
-- 5. Products and variants
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS public.idx_products_in_stock;
DROP INDEX IF EXISTS public.idx_products_price;
DROP INDEX IF EXISTS public.idx_variants_product_sku;

ALTER TABLE public.products
  DROP COLUMN IF EXISTS min_price,
  DROP COLUMN IF EXISTS max_price,
  DROP COLUMN IF EXISTS total_stock,
  DROP COLUMN IF EXISTS in_stock,
  DROP COLUMN IF EXISTS is_active;

ALTER TABLE public.products
  ALTER COLUMN sku TYPE text,
  ALTER COLUMN name TYPE text,
  ALTER COLUMN category TYPE text,
  ALTER COLUMN brand TYPE text;

UPDATE public.products
SET attributes = '{}'::jsonb
WHERE attributes IS NULL;

UPDATE public.products
SET created_at = now()
WHERE created_at IS NULL;

UPDATE public.products
SET updated_at = now()
WHERE updated_at IS NULL;

ALTER TABLE public.products
  ALTER COLUMN list_price_vnd DROP NOT NULL,
  ALTER COLUMN list_price_vnd DROP DEFAULT,
  ALTER COLUMN attributes SET DEFAULT '{}'::jsonb,
  ALTER COLUMN attributes SET NOT NULL,
  ALTER COLUMN created_at SET DEFAULT now(),
  ALTER COLUMN created_at SET NOT NULL,
  ALTER COLUMN updated_at SET DEFAULT now(),
  ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE public.products
  DROP CONSTRAINT IF EXISTS products_list_price_vnd_check;

ALTER TABLE public.products
  ADD CONSTRAINT products_list_price_vnd_check
  CHECK (list_price_vnd IS NULL OR list_price_vnd >= 0);

ALTER TABLE public.product_variants
  DROP COLUMN IF EXISTS created_at,
  DROP COLUMN IF EXISTS updated_at;

ALTER TABLE public.product_variants
  ALTER COLUMN variant_sku TYPE text,
  ALTER COLUMN product_sku TYPE text,
  ALTER COLUMN size TYPE text,
  ALTER COLUMN color TYPE text;

UPDATE public.product_variants
SET price_delta_vnd = 0
WHERE price_delta_vnd IS NULL;

ALTER TABLE public.product_variants
  ALTER COLUMN price_delta_vnd SET DEFAULT 0,
  ALTER COLUMN price_delta_vnd SET NOT NULL;

ALTER TABLE public.product_variants
  DROP CONSTRAINT IF EXISTS product_variants_stock_check,
  DROP CONSTRAINT IF EXISTS product_variants_attributes_unique;

ALTER TABLE public.product_variants
  ADD CONSTRAINT product_variants_stock_check CHECK (stock >= 0),
  ADD CONSTRAINT product_variants_attributes_unique UNIQUE (product_sku, size, color);

-- ---------------------------------------------------------------------------
-- 6. Promotions
-- ---------------------------------------------------------------------------

UPDATE public.promotions
SET starts_on = start_date
WHERE starts_on IS NULL AND start_date IS NOT NULL;

UPDATE public.promotions
SET ends_on = end_date
WHERE ends_on IS NULL AND end_date IS NOT NULL;

INSERT INTO public.promotion_products (promo_code, target_type, target_value)
SELECT
  promo.promo_code,
  CASE
    WHEN item = '*' THEN 'all'
    WHEN item LIKE 'category:%' THEN 'category'
    ELSE 'sku'
  END,
  CASE
    WHEN item = '*' THEN 'all'
    WHEN item LIKE 'category:%' THEN substr(item, 10)
    ELSE item
  END
FROM public.promotions AS promo
CROSS JOIN LATERAL unnest(promo.applies_to) AS item
WHERE item IS NOT NULL AND btrim(item) <> ''
ON CONFLICT DO NOTHING;

DROP INDEX IF EXISTS public.idx_promotions_dates;
DROP INDEX IF EXISTS public.idx_promotions_gift_sku;

ALTER TABLE public.promotions
  DROP COLUMN IF EXISTS applies_to,
  DROP COLUMN IF EXISTS start_date,
  DROP COLUMN IF EXISTS end_date,
  DROP COLUMN IF EXISTS created_at,
  DROP COLUMN IF EXISTS updated_at;

ALTER TABLE public.promotions
  ALTER COLUMN promo_code TYPE text,
  ALTER COLUMN name TYPE text,
  ALTER COLUMN type TYPE text,
  ALTER COLUMN gift_sku TYPE text;

UPDATE public.promotions
SET stackable = false
WHERE stackable IS NULL;

UPDATE public.promotions
SET conditions = '{}'::jsonb
WHERE conditions IS NULL;

ALTER TABLE public.promotions
  ALTER COLUMN stackable SET DEFAULT false,
  ALTER COLUMN stackable SET NOT NULL,
  ALTER COLUMN conditions SET DEFAULT '{}'::jsonb,
  ALTER COLUMN conditions SET NOT NULL,
  ALTER COLUMN discount_vnd DROP DEFAULT,
  ALTER COLUMN discount_percent DROP DEFAULT,
  ALTER COLUMN min_order_vnd DROP DEFAULT;

ALTER TABLE public.promotions
  DROP CONSTRAINT IF EXISTS promotions_discount_vnd_check,
  DROP CONSTRAINT IF EXISTS promotions_discount_percent_check,
  DROP CONSTRAINT IF EXISTS promotions_min_order_vnd_check;

ALTER TABLE public.promotions
  ADD CONSTRAINT promotions_discount_vnd_check
    CHECK (discount_vnd IS NULL OR discount_vnd >= 0),
  ADD CONSTRAINT promotions_discount_percent_check
    CHECK (discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)),
  ADD CONSTRAINT promotions_min_order_vnd_check
    CHECK (min_order_vnd IS NULL OR min_order_vnd >= 0);

-- ---------------------------------------------------------------------------
-- 7. Profile facts: fact_id là khóa chính, current_value thay profile_value
-- ---------------------------------------------------------------------------

ALTER TABLE public.profile_fact_versions
  DROP CONSTRAINT IF EXISTS profile_fact_versions_fact_id_fkey;

ALTER TABLE public.profile_facts
  DROP CONSTRAINT IF EXISTS profile_facts_source_session_id_fkey,
  DROP CONSTRAINT IF EXISTS profile_facts_customer_id_fkey,
  DROP CONSTRAINT IF EXISTS chk_profile_facts_confidence,
  DROP CONSTRAINT IF EXISTS profile_facts_confidence_check,
  DROP CONSTRAINT IF EXISTS profile_facts_pkey;

DROP INDEX IF EXISTS public.idx_profile_facts_session;
DROP INDEX IF EXISTS public.profile_facts_fact_id_key;

ALTER TABLE public.profile_facts
  ADD COLUMN IF NOT EXISTS current_value jsonb,
  ADD COLUMN IF NOT EXISTS status text,
  ADD COLUMN IF NOT EXISTS valid_until timestamptz,
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

UPDATE public.profile_facts
SET current_value = profile_value
WHERE current_value IS NULL;

ALTER TABLE public.profile_facts
  DROP COLUMN IF EXISTS profile_value,
  DROP COLUMN IF EXISTS source_session_id,
  DROP COLUMN IF EXISTS source_event_id,
  DROP COLUMN IF EXISTS source_kind,
  DROP COLUMN IF EXISTS confidence;

ALTER TABLE public.profile_facts
  ADD CONSTRAINT profile_facts_pkey PRIMARY KEY (fact_id),
  ADD CONSTRAINT profile_facts_customer_key_unique UNIQUE (customer_id, profile_key),
  ADD CONSTRAINT profile_facts_customer_id_fkey
    FOREIGN KEY (customer_id) REFERENCES public.customers (customer_id) ON DELETE CASCADE;

ALTER TABLE public.profile_fact_versions
  ADD CONSTRAINT profile_fact_versions_fact_id_fkey
  FOREIGN KEY (fact_id) REFERENCES public.profile_facts (fact_id) ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- 8. Index đúng tên trong file thiết kế
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS conversation_sessions_customer_started_idx
  ON public.conversation_sessions (customer_id, started_at DESC);
CREATE INDEX IF NOT EXISTS conversation_sessions_status_idx
  ON public.conversation_sessions (status);

CREATE INDEX IF NOT EXISTS turns_session_created_idx
  ON public.turns (session_id, created_at);
CREATE INDEX IF NOT EXISTS tool_calls_turn_created_idx
  ON public.tool_calls (turn_id, created_at);

CREATE INDEX IF NOT EXISTS profile_facts_customer_status_idx
  ON public.profile_facts (customer_id, status);
CREATE INDEX IF NOT EXISTS profile_fact_versions_fact_recorded_idx
  ON public.profile_fact_versions (fact_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS profile_fact_versions_source_turn_idx
  ON public.profile_fact_versions (source_turn_id);

CREATE INDEX IF NOT EXISTS episodes_customer_generated_idx
  ON public.episodes (customer_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS memory_outbox_status_created_idx
  ON public.memory_outbox (status, created_at);

CREATE INDEX IF NOT EXISTS orders_customer_date_idx
  ON public.orders (customer_id, order_date DESC);
CREATE INDEX IF NOT EXISTS orders_source_session_idx
  ON public.orders (source_session_id);
CREATE INDEX IF NOT EXISTS order_items_order_idx
  ON public.order_items (order_id);
CREATE INDEX IF NOT EXISTS order_items_sku_idx
  ON public.order_items (sku);
CREATE INDEX IF NOT EXISTS callbacks_customer_scheduled_idx
  ON public.callbacks (customer_id, scheduled_at);
CREATE INDEX IF NOT EXISTS callbacks_status_scheduled_idx
  ON public.callbacks (status, scheduled_at);

CREATE INDEX IF NOT EXISTS product_variants_product_idx
  ON public.product_variants (product_sku);
CREATE INDEX IF NOT EXISTS inventory_snapshots_sku_observed_idx
  ON public.inventory_snapshots (sku, observed_on DESC);
CREATE INDEX IF NOT EXISTS inventory_snapshots_variant_observed_idx
  ON public.inventory_snapshots (variant_sku, observed_on DESC);

CREATE INDEX IF NOT EXISTS promotions_active_dates_idx
  ON public.promotions (starts_on, ends_on);
CREATE INDEX IF NOT EXISTS promotion_products_target_idx
  ON public.promotion_products (target_type, target_value);
CREATE INDEX IF NOT EXISTS order_promotions_promo_idx
  ON public.order_promotions (promo_code);

CREATE INDEX IF NOT EXISTS policy_versions_policy_effective_idx
  ON public.policy_versions (policy_id, effective_from DESC);

-- ---------------------------------------------------------------------------
-- 9. RLS trên mọi bảng của thiết kế
-- ---------------------------------------------------------------------------

ALTER TABLE public.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tool_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_fact_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.callbacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_variants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_promotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_versions ENABLE ROW LEVEL SECURITY;
