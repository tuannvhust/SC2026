-- Align the remote baseline with the local design.
-- Additive only: app tables (working_events, episodic_memory, checkpoints,
-- profile_facts) stay. New names are filled from the old columns when both exist.

-- Customers: seed and the local design use `name`.
ALTER TABLE public.customers
  ADD COLUMN IF NOT EXISTS name text;

UPDATE public.customers
SET name = COALESCE(preferred_name, full_name)
WHERE name IS NULL
  AND COALESCE(preferred_name, full_name) IS NOT NULL;

CREATE OR REPLACE FUNCTION public.customers_sync_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.name IS NULL THEN
    NEW.name := COALESCE(NEW.preferred_name, NEW.full_name);
  END IF;
  IF NEW.preferred_name IS NULL THEN
    NEW.preferred_name := NEW.name;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_customers_sync_name ON public.customers;
CREATE TRIGGER trg_customers_sync_name
  BEFORE INSERT OR UPDATE ON public.customers
  FOR EACH ROW
  EXECUTE FUNCTION public.customers_sync_name();

-- Sessions: local design records the business call date.
ALTER TABLE public.conversation_sessions
  ADD COLUMN IF NOT EXISTS call_date date;

CREATE INDEX IF NOT EXISTS conversation_sessions_call_date_idx
  ON public.conversation_sessions (call_date);

-- Orders: keep tracking_number and total_amount_vnd, and accept the local names.
ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS tracking text,
  ADD COLUMN IF NOT EXISTS total_vnd bigint,
  ADD COLUMN IF NOT EXISTS source_session_id text;

UPDATE public.orders
SET tracking = tracking_number
WHERE tracking IS NULL AND tracking_number IS NOT NULL;

UPDATE public.orders
SET total_vnd = total_amount_vnd
WHERE total_vnd IS NULL AND total_amount_vnd IS NOT NULL;

ALTER TABLE public.orders
  DROP CONSTRAINT IF EXISTS orders_total_vnd_check;
ALTER TABLE public.orders
  ADD CONSTRAINT orders_total_vnd_check
  CHECK (total_vnd IS NULL OR total_vnd >= 0);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'orders_source_session_id_fkey'
  ) THEN
    ALTER TABLE public.orders
      ADD CONSTRAINT orders_source_session_id_fkey
      FOREIGN KEY (source_session_id)
      REFERENCES public.conversation_sessions (session_id)
      ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS orders_source_session_idx
  ON public.orders (source_session_id);

CREATE OR REPLACE FUNCTION public.orders_sync_amounts()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.tracking IS NULL THEN
    NEW.tracking := NEW.tracking_number;
  END IF;
  IF NEW.tracking_number IS NULL THEN
    NEW.tracking_number := NEW.tracking;
  END IF;
  IF NEW.total_vnd IS NULL THEN
    NEW.total_vnd := NEW.total_amount_vnd;
  END IF;
  IF NEW.total_amount_vnd IS NULL THEN
    NEW.total_amount_vnd := NEW.total_vnd;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_orders_sync_amounts ON public.orders;
CREATE TRIGGER trg_orders_sync_amounts
  BEFORE INSERT OR UPDATE ON public.orders
  FOR EACH ROW
  EXECUTE FUNCTION public.orders_sync_amounts();

-- Order lines: seed omits line_number and stores a product snapshot.
ALTER TABLE public.order_items
  ADD COLUMN IF NOT EXISTS variant_sku text,
  ADD COLUMN IF NOT EXISTS product_snapshot jsonb;

ALTER TABLE public.order_items
  ALTER COLUMN line_number SET DEFAULT 1;

CREATE INDEX IF NOT EXISTS order_items_sku_idx
  ON public.order_items (sku);

-- Products: local design stores the static stock on the product row.
ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS stock integer NOT NULL DEFAULT 0;

ALTER TABLE public.products
  DROP CONSTRAINT IF EXISTS products_stock_check;
ALTER TABLE public.products
  ADD CONSTRAINT products_stock_check CHECK (stock >= 0);

UPDATE public.products
SET stock = COALESCE(total_stock, 0)
WHERE stock = 0 AND COALESCE(total_stock, 0) > 0;

-- Promotions: accept starts_on/ends_on and keep start_date/end_date.
ALTER TABLE public.promotions
  ADD COLUMN IF NOT EXISTS starts_on date,
  ADD COLUMN IF NOT EXISTS ends_on date;

UPDATE public.promotions
SET starts_on = start_date
WHERE starts_on IS NULL AND start_date IS NOT NULL;

UPDATE public.promotions
SET ends_on = end_date
WHERE ends_on IS NULL AND end_date IS NOT NULL;

ALTER TABLE public.promotions
  ALTER COLUMN applies_to SET DEFAULT '{}'::text[];

ALTER TABLE public.promotions
  ALTER COLUMN discount_percent TYPE numeric(5,2)
  USING discount_percent::numeric(5,2);

ALTER TABLE public.promotions
  DROP CONSTRAINT IF EXISTS promotions_date_range_check;
ALTER TABLE public.promotions
  ADD CONSTRAINT promotions_date_range_check
  CHECK (starts_on IS NULL OR ends_on IS NULL OR ends_on >= starts_on);

CREATE OR REPLACE FUNCTION public.promotions_sync_schedule()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.starts_on IS NULL THEN
    NEW.starts_on := NEW.start_date;
  END IF;
  IF NEW.start_date IS NULL THEN
    NEW.start_date := NEW.starts_on;
  END IF;
  IF NEW.ends_on IS NULL THEN
    NEW.ends_on := NEW.end_date;
  END IF;
  IF NEW.end_date IS NULL THEN
    NEW.end_date := NEW.ends_on;
  END IF;
  IF NEW.applies_to IS NULL THEN
    NEW.applies_to := '{}'::text[];
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_promotions_sync_schedule ON public.promotions;
CREATE TRIGGER trg_promotions_sync_schedule
  BEFORE INSERT OR UPDATE ON public.promotions
  FOR EACH ROW
  EXECUTE FUNCTION public.promotions_sync_schedule();

CREATE INDEX IF NOT EXISTS promotions_active_dates_idx
  ON public.promotions (starts_on, ends_on);

CREATE TABLE IF NOT EXISTS public.promotion_products (
  promo_code text NOT NULL REFERENCES public.promotions (promo_code) ON DELETE CASCADE,
  target_type text NOT NULL CHECK (target_type IN ('sku', 'category', 'all')),
  target_value text NOT NULL,
  PRIMARY KEY (promo_code, target_type, target_value),
  CONSTRAINT promotion_products_all_target_check
    CHECK (target_type <> 'all' OR target_value = 'all')
);

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

CREATE INDEX IF NOT EXISTS promotion_products_target_idx
  ON public.promotion_products (target_type, target_value);

-- Tables that exist only in the local design.
CREATE TABLE IF NOT EXISTS public.inventory_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sku text REFERENCES public.products (sku) ON DELETE CASCADE,
  variant_sku text REFERENCES public.product_variants (variant_sku) ON DELETE CASCADE,
  observed_on date NOT NULL DEFAULT CURRENT_DATE,
  quantity integer NOT NULL CHECK (quantity >= 0),
  CONSTRAINT inventory_snapshot_has_one_target
    CHECK (num_nonnulls(sku, variant_sku) = 1)
);

CREATE INDEX IF NOT EXISTS inventory_snapshots_sku_observed_idx
  ON public.inventory_snapshots (sku, observed_on DESC);
CREATE INDEX IF NOT EXISTS inventory_snapshots_variant_observed_idx
  ON public.inventory_snapshots (variant_sku, observed_on DESC);

CREATE TABLE IF NOT EXISTS public.turns (
  turn_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id text NOT NULL REFERENCES public.conversation_sessions (session_id) ON DELETE CASCADE,
  turn_number integer NOT NULL CHECK (turn_number > 0),
  input_masked text,
  normalized_input_masked text,
  assistant_output_masked text,
  trace_json jsonb,
  ttft_ms integer CHECK (ttft_ms IS NULL OR ttft_ms >= 0),
  total_latency_ms integer CHECK (total_latency_ms IS NULL OR total_latency_ms >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT turns_session_turn_number_unique UNIQUE (session_id, turn_number)
);

CREATE INDEX IF NOT EXISTS turns_session_created_idx
  ON public.turns (session_id, created_at);

CREATE TABLE IF NOT EXISTS public.tool_calls (
  tool_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  turn_id uuid NOT NULL REFERENCES public.turns (turn_id) ON DELETE CASCADE,
  tool_name text NOT NULL,
  arguments_masked jsonb,
  result_masked jsonb,
  status text,
  duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS tool_calls_turn_created_idx
  ON public.tool_calls (turn_id, created_at);

ALTER TABLE public.profile_facts
  ADD COLUMN IF NOT EXISTS fact_id uuid NOT NULL DEFAULT gen_random_uuid();

CREATE UNIQUE INDEX IF NOT EXISTS profile_facts_fact_id_key
  ON public.profile_facts (fact_id);

CREATE TABLE IF NOT EXISTS public.profile_fact_versions (
  version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fact_id uuid NOT NULL REFERENCES public.profile_facts (fact_id) ON DELETE CASCADE,
  source_turn_id uuid REFERENCES public.turns (turn_id) ON DELETE SET NULL,
  value jsonb,
  source_kind text,
  accepted boolean NOT NULL DEFAULT false,
  recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS profile_fact_versions_fact_recorded_idx
  ON public.profile_fact_versions (fact_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS profile_fact_versions_source_turn_idx
  ON public.profile_fact_versions (source_turn_id);

CREATE TABLE IF NOT EXISTS public.episodes (
  episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id text NOT NULL UNIQUE REFERENCES public.conversation_sessions (session_id) ON DELETE CASCADE,
  customer_id text REFERENCES public.customers (customer_id) ON DELETE SET NULL,
  summary_masked text,
  useful_context jsonb,
  generated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS episodes_customer_generated_idx
  ON public.episodes (customer_id, generated_at DESC);

CREATE TABLE IF NOT EXISTS public.memory_outbox (
  outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  episode_id uuid REFERENCES public.episodes (episode_id) ON DELETE CASCADE,
  fact_version_id uuid REFERENCES public.profile_fact_versions (version_id) ON DELETE CASCADE,
  operation text NOT NULL,
  mem0_memory_id text,
  status text NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  CONSTRAINT memory_outbox_has_target
    CHECK (episode_id IS NOT NULL OR fact_version_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS memory_outbox_status_created_idx
  ON public.memory_outbox (status, created_at);

CREATE TABLE IF NOT EXISTS public.callbacks (
  callback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id text NOT NULL REFERENCES public.customers (customer_id) ON DELETE CASCADE,
  source_session_id text REFERENCES public.conversation_sessions (session_id) ON DELETE SET NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  scheduled_at timestamptz,
  status text
);

CREATE INDEX IF NOT EXISTS callbacks_customer_scheduled_idx
  ON public.callbacks (customer_id, scheduled_at);
CREATE INDEX IF NOT EXISTS callbacks_status_scheduled_idx
  ON public.callbacks (status, scheduled_at);

CREATE TABLE IF NOT EXISTS public.order_promotions (
  order_id text NOT NULL REFERENCES public.orders (order_id) ON DELETE CASCADE,
  promo_code text NOT NULL REFERENCES public.promotions (promo_code) ON DELETE RESTRICT,
  discount_vnd bigint NOT NULL CHECK (discount_vnd >= 0),
  PRIMARY KEY (order_id, promo_code)
);

CREATE INDEX IF NOT EXISTS order_promotions_promo_idx
  ON public.order_promotions (promo_code);

CREATE TABLE IF NOT EXISTS public.policies (
  policy_id text PRIMARY KEY,
  title text NOT NULL,
  visibility text NOT NULL
);

CREATE TABLE IF NOT EXISTS public.policy_versions (
  policy_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_id text NOT NULL REFERENCES public.policies (policy_id) ON DELETE CASCADE,
  effective_from date NOT NULL,
  effective_to date,
  CONSTRAINT policy_versions_date_range_check
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
  CONSTRAINT policy_versions_start_unique UNIQUE (policy_id, effective_from)
);

CREATE INDEX IF NOT EXISTS policy_versions_policy_effective_idx
  ON public.policy_versions (policy_id, effective_from DESC);

ALTER TABLE public.turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tool_calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_fact_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.callbacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_promotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.policy_versions ENABLE ROW LEVEL SECURITY;

GRANT ALL ON TABLE
  public.turns,
  public.tool_calls,
  public.profile_fact_versions,
  public.episodes,
  public.memory_outbox,
  public.callbacks,
  public.inventory_snapshots,
  public.promotion_products,
  public.order_promotions,
  public.policies,
  public.policy_versions
TO anon, authenticated, service_role;
