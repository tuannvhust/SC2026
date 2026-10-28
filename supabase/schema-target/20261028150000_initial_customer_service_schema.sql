-- Initial schema for the AI customer-service / memory / commerce project.
-- PostgreSQL / Supabase. Review the design decisions in the accompanying instructions
-- before applying this migration to any shared or hosted project.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. Customers and conversation observability
-- ---------------------------------------------------------------------------

CREATE TABLE public.customers (
    customer_id text PRIMARY KEY,
    name text,
    honorific text,
    status text,
    phone text,
    zalo_id text UNIQUE,
    fb_id text UNIQUE,
    region text,
    address_line text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.conversation_sessions (
    -- Mã nghiệp vụ từ CRM seed, ví dụ S000001.
    session_id text PRIMARY KEY,
    customer_id text REFERENCES public.customers(customer_id) ON DELETE SET NULL,
    channel text,
    call_date date,
    status text,
    outcome text,
    call_brief_json jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    CONSTRAINT conversation_sessions_time_check
        CHECK (ended_at IS NULL OR ended_at >= started_at)
);

CREATE TABLE public.turns (
    turn_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id text NOT NULL REFERENCES public.conversation_sessions(session_id) ON DELETE CASCADE,
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

CREATE TABLE public.tool_calls (
    tool_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id uuid NOT NULL REFERENCES public.turns(turn_id) ON DELETE CASCADE,
    tool_name text NOT NULL,
    arguments_masked jsonb,
    result_masked jsonb,
    status text,
    duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 2. Profile memory, episodic memory and Mem0 outbox
-- ---------------------------------------------------------------------------

CREATE TABLE public.profile_facts (
    fact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id text NOT NULL REFERENCES public.customers(customer_id) ON DELETE CASCADE,
    profile_key text NOT NULL,
    current_value jsonb,
    status text,
    valid_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT profile_facts_customer_key_unique UNIQUE (customer_id, profile_key)
);

CREATE TABLE public.profile_fact_versions (
    version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    fact_id uuid NOT NULL REFERENCES public.profile_facts(fact_id) ON DELETE CASCADE,
    source_turn_id uuid REFERENCES public.turns(turn_id) ON DELETE SET NULL,
    value jsonb,
    source_kind text,
    accepted boolean NOT NULL DEFAULT false,
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.episodes (
    episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id text NOT NULL UNIQUE REFERENCES public.conversation_sessions(session_id) ON DELETE CASCADE,
    customer_id text REFERENCES public.customers(customer_id) ON DELETE SET NULL,
    summary_masked text,
    useful_context jsonb,
    generated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.memory_outbox (
    outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id uuid REFERENCES public.episodes(episode_id) ON DELETE CASCADE,
    fact_version_id uuid REFERENCES public.profile_fact_versions(version_id) ON DELETE CASCADE,
    operation text NOT NULL,
    mem0_memory_id text,
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    CONSTRAINT memory_outbox_has_target
        CHECK (episode_id IS NOT NULL OR fact_version_id IS NOT NULL)
);

-- ---------------------------------------------------------------------------
-- 3. Commerce: orders, products, variants and inventory
-- ---------------------------------------------------------------------------

CREATE TABLE public.orders (
    -- Mã nghiệp vụ từ CRM seed, ví dụ OD188213.
    order_id text PRIMARY KEY,
    tracking text,
    customer_id text NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    source_session_id text REFERENCES public.conversation_sessions(session_id) ON DELETE SET NULL,
    status text,
    total_vnd bigint NOT NULL DEFAULT 0 CHECK (total_vnd >= 0),
    order_date date NOT NULL DEFAULT CURRENT_DATE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX orders_tracking_unique
    ON public.orders(tracking)
    WHERE tracking IS NOT NULL;

CREATE TABLE public.order_items (
    order_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id text NOT NULL REFERENCES public.orders(order_id) ON DELETE CASCADE,
    sku text NOT NULL,
    variant_sku text,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price_vnd bigint NOT NULL CHECK (unit_price_vnd >= 0),
    line_total_vnd bigint NOT NULL CHECK (line_total_vnd >= 0),
    product_snapshot jsonb,
    CONSTRAINT order_items_line_total_check
        CHECK (line_total_vnd = quantity * unit_price_vnd)
);

CREATE TABLE public.callbacks (
    callback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id text NOT NULL REFERENCES public.customers(customer_id) ON DELETE CASCADE,
    source_session_id text REFERENCES public.conversation_sessions(session_id) ON DELETE SET NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    scheduled_at timestamptz,
    status text
);

CREATE TABLE public.products (
    sku text PRIMARY KEY,
    name text NOT NULL,
    category text,
    brand text,
    list_price_vnd bigint CHECK (list_price_vnd IS NULL OR list_price_vnd >= 0),
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    stock integer NOT NULL DEFAULT 0 CHECK (stock >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE public.product_variants (
    variant_sku text PRIMARY KEY,
    product_sku text NOT NULL REFERENCES public.products(sku) ON DELETE CASCADE,
    size text,
    color text,
    price_delta_vnd bigint NOT NULL DEFAULT 0,
    stock integer NOT NULL DEFAULT 0 CHECK (stock >= 0),
    CONSTRAINT product_variants_attributes_unique UNIQUE (product_sku, size, color)
);

CREATE TABLE public.inventory_snapshots (
    snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sku text REFERENCES public.products(sku) ON DELETE CASCADE,
    variant_sku text REFERENCES public.product_variants(variant_sku) ON DELETE CASCADE,
    observed_on date NOT NULL DEFAULT CURRENT_DATE,
    quantity integer NOT NULL CHECK (quantity >= 0),
    CONSTRAINT inventory_snapshot_has_one_target
        CHECK (num_nonnulls(sku, variant_sku) = 1)
);

-- ---------------------------------------------------------------------------
-- 4. Promotions
-- ---------------------------------------------------------------------------

CREATE TABLE public.promotions (
    promo_code text PRIMARY KEY,
    name text NOT NULL,
    type text NOT NULL,
    starts_on date,
    ends_on date,
    stackable boolean NOT NULL DEFAULT false,
    discount_vnd bigint CHECK (discount_vnd IS NULL OR discount_vnd >= 0),
    discount_percent numeric(5,2) CHECK (
        discount_percent IS NULL OR (discount_percent >= 0 AND discount_percent <= 100)
    ),
    gift_sku text REFERENCES public.products(sku) ON DELETE SET NULL,
    min_order_vnd bigint CHECK (min_order_vnd IS NULL OR min_order_vnd >= 0),
    conditions jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT promotions_date_range_check
        CHECK (starts_on IS NULL OR ends_on IS NULL OR ends_on >= starts_on)
);

CREATE TABLE public.promotion_products (
    promo_code text NOT NULL REFERENCES public.promotions(promo_code) ON DELETE CASCADE,
    target_type text NOT NULL CHECK (target_type IN ('sku', 'category', 'all')),
    target_value text NOT NULL,
    PRIMARY KEY (promo_code, target_type, target_value),
    CONSTRAINT promotion_products_all_target_check
        CHECK (target_type <> 'all' OR target_value = 'all')
);

CREATE TABLE public.order_promotions (
    order_id text NOT NULL REFERENCES public.orders(order_id) ON DELETE CASCADE,
    promo_code text NOT NULL REFERENCES public.promotions(promo_code) ON DELETE RESTRICT,
    discount_vnd bigint NOT NULL CHECK (discount_vnd >= 0),
    PRIMARY KEY (order_id, promo_code)
);

-- ---------------------------------------------------------------------------
-- 5. Policy knowledge base metadata
-- ---------------------------------------------------------------------------

CREATE TABLE public.policies (
    policy_id text PRIMARY KEY,
    title text NOT NULL,
    visibility text NOT NULL
);

CREATE TABLE public.policy_versions (
    policy_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id text NOT NULL REFERENCES public.policies(policy_id) ON DELETE CASCADE,
    effective_from date NOT NULL,
    effective_to date,
    CONSTRAINT policy_versions_date_range_check
        CHECK (effective_to IS NULL OR effective_to >= effective_from),
    CONSTRAINT policy_versions_start_unique UNIQUE (policy_id, effective_from)
);

-- POLICY_CHUNKS is intentionally omitted because it was commented out in the ERD.

-- ---------------------------------------------------------------------------
-- 6. Indexes for common joins and filters
-- ---------------------------------------------------------------------------

CREATE INDEX conversation_sessions_customer_started_idx
    ON public.conversation_sessions(customer_id, started_at DESC);
CREATE INDEX conversation_sessions_status_idx
    ON public.conversation_sessions(status);

CREATE INDEX turns_session_created_idx
    ON public.turns(session_id, created_at);
CREATE INDEX tool_calls_turn_created_idx
    ON public.tool_calls(turn_id, created_at);

CREATE INDEX profile_facts_customer_status_idx
    ON public.profile_facts(customer_id, status);
CREATE INDEX profile_fact_versions_fact_recorded_idx
    ON public.profile_fact_versions(fact_id, recorded_at DESC);
CREATE INDEX profile_fact_versions_source_turn_idx
    ON public.profile_fact_versions(source_turn_id);

CREATE INDEX episodes_customer_generated_idx
    ON public.episodes(customer_id, generated_at DESC);
CREATE INDEX memory_outbox_status_created_idx
    ON public.memory_outbox(status, created_at);

CREATE INDEX orders_customer_date_idx
    ON public.orders(customer_id, order_date DESC);
CREATE INDEX orders_source_session_idx
    ON public.orders(source_session_id);
CREATE INDEX order_items_order_idx
    ON public.order_items(order_id);
CREATE INDEX order_items_sku_idx
    ON public.order_items(sku);
CREATE INDEX callbacks_customer_scheduled_idx
    ON public.callbacks(customer_id, scheduled_at);
CREATE INDEX callbacks_status_scheduled_idx
    ON public.callbacks(status, scheduled_at);

CREATE INDEX product_variants_product_idx
    ON public.product_variants(product_sku);
CREATE INDEX inventory_snapshots_sku_observed_idx
    ON public.inventory_snapshots(sku, observed_on DESC);
CREATE INDEX inventory_snapshots_variant_observed_idx
    ON public.inventory_snapshots(variant_sku, observed_on DESC);

CREATE INDEX promotions_active_dates_idx
    ON public.promotions(starts_on, ends_on);
CREATE INDEX promotion_products_target_idx
    ON public.promotion_products(target_type, target_value);
CREATE INDEX order_promotions_promo_idx
    ON public.order_promotions(promo_code);

CREATE INDEX policy_versions_policy_effective_idx
    ON public.policy_versions(policy_id, effective_from DESC);

-- ---------------------------------------------------------------------------
-- 7. Enable RLS as a safe default
-- No anon/authenticated policies are created here. Add explicit policies before
-- allowing browser/mobile clients to access these tables directly.
-- A trusted server-side service-role client bypasses RLS; never expose its key.
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

COMMIT;
