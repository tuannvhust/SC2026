-- Migration: 001_schema_v1.sql
-- Description: Business and Memory Schema v1 for SC2026 Harness Agent
-- Target database: Supabase PostgreSQL (verified new project)

BEGIN;

-- 1. Bảng customers (Hồ sơ khách hàng chuẩn với customer_id ổn định)
CREATE TABLE IF NOT EXISTS public.customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT,
    preferred_name TEXT,
    honorific TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'provisional', 'merged', 'deleted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_customers_status ON public.customers (status) WHERE deleted_at IS NULL;

-- 2. Bảng customer_identities (Định danh đa kênh: Phone, Zalo, FB, Web)
CREATE TABLE IF NOT EXISTS public.customer_identities (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    identity_type TEXT NOT NULL CHECK (identity_type IN ('phone', 'zalo_id', 'fb_id', 'email', 'web_user_id', 'crm_id')),
    normalized_value TEXT NOT NULL,
    display_value TEXT,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    verified_at TIMESTAMPTZ,
    source TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disabled_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_identities_active
    ON public.customer_identities (identity_type, normalized_value)
    WHERE disabled_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_customer_identities_customer_id
    ON public.customer_identities (customer_id);

-- 3. Bảng customer_addresses (Địa chỉ khách hàng chuẩn)
CREATE TABLE IF NOT EXISTS public.customer_addresses (
    address_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    label TEXT,
    recipient_name TEXT,
    recipient_phone TEXT,
    address_line TEXT NOT NULL,
    ward TEXT,
    district TEXT,
    city TEXT NOT NULL,
    country_code CHAR(2) NOT NULL DEFAULT 'VN',
    is_default BOOLEAN NOT NULL DEFAULT false,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_customer_addresses_customer_id ON public.customer_addresses (customer_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_addresses_default
    ON public.customer_addresses (customer_id)
    WHERE is_default AND deleted_at IS NULL;

-- 4. Bảng conversation_sessions (Vòng đời phiên & Call Brief snapshot)
CREATE TABLE IF NOT EXISTS public.conversation_sessions (
    session_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    channel TEXT NOT NULL DEFAULT 'web_chat',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'ending', 'ended', 'abandoned', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    finalized_at TIMESTAMPTZ,
    outcome TEXT,
    handoff_reason TEXT,
    call_brief_json JSONB,
    call_brief_revision INTEGER NOT NULL DEFAULT 0 CHECK (call_brief_revision >= 0),
    call_brief_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversation_sessions_customer ON public.conversation_sessions (customer_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversation_sessions_status ON public.conversation_sessions (status, last_activity_at DESC);

-- 5. Bảng working_events (Working Memory theo từng lượt hội thoại)
CREATE TABLE IF NOT EXISTS public.working_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT,
    turn_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL CHECK (turn_number >= 1),
    customer_id TEXT REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL DEFAULT 'turn_saved',
    event_index INTEGER NOT NULL DEFAULT 0 CHECK (event_index >= 0),
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_working_events_turn UNIQUE (session_id, turn_id),
    CONSTRAINT uq_working_events_turn_num UNIQUE (session_id, turn_number)
);

CREATE INDEX IF NOT EXISTS idx_working_events_session_turn ON public.working_events (session_id, turn_number, created_at);
CREATE INDEX IF NOT EXISTS idx_working_events_customer ON public.working_events (customer_id, created_at);

-- 6. Bảng profile_fact_candidates (Fact chờ qua Write Gate / Durable-Fact Gate)
CREATE TABLE IF NOT EXISTS public.profile_fact_candidates (
    candidate_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT,
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    profile_key TEXT NOT NULL,
    proposed_value JSONB NOT NULL,
    is_durable_fact BOOLEAN NOT NULL DEFAULT false,
    confidence NUMERIC(4,3) CHECK (confidence >= 0 AND confidence <= 1),
    source_event_id UUID REFERENCES public.working_events(event_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'committed', 'rejected')),
    decision_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_candidates_session_status ON public.profile_fact_candidates (session_id, status);
CREATE INDEX IF NOT EXISTS idx_candidates_customer_key ON public.profile_fact_candidates (customer_id, profile_key, created_at DESC);

-- 7. Bảng profile_facts (Profile Memory hiện hành bền vững)
CREATE TABLE IF NOT EXISTS public.profile_facts (
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    profile_key TEXT NOT NULL,
    profile_value JSONB NOT NULL,
    source_session_id TEXT REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT,
    source_event_id UUID REFERENCES public.working_events(event_id) ON DELETE RESTRICT,
    source_kind TEXT NOT NULL DEFAULT 'customer_stated',
    confidence NUMERIC(4,3) CHECK (confidence >= 0 AND confidence <= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, profile_key)
);

CREATE INDEX IF NOT EXISTS idx_profile_facts_session ON public.profile_facts (source_session_id);

-- 8. Bảng profile_fact_history (Lịch sử thay đổi Profile - append-only)
CREATE TABLE IF NOT EXISTS public.profile_fact_history (
    history_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    profile_key TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    change_type TEXT NOT NULL CHECK (change_type IN ('created', 'updated', 'invalidated', 'deleted')),
    source_session_id TEXT REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT,
    source_event_id UUID REFERENCES public.working_events(event_id) ON DELETE RESTRICT,
    change_reason TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_profile_fact_history_lookup
    ON public.profile_fact_history (customer_id, profile_key, changed_at DESC, history_id DESC);

-- 9. Bảng episodic_memory (Tóm tắt phiên đã kết thúc - 1 episode / session)
CREATE TABLE IF NOT EXISTS public.episodic_memory (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL UNIQUE REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT,
    customer_id TEXT REFERENCES public.customers(customer_id) ON DELETE RESTRICT,
    summary TEXT NOT NULL,
    current_need TEXT,
    outcome TEXT,
    handoff_reason TEXT,
    products_advised JSONB NOT NULL DEFAULT '[]'::jsonb,
    orders_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    open_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_event_ids UUID[] NOT NULL DEFAULT '{}',
    turn_count INTEGER NOT NULL DEFAULT 0 CHECK (turn_count >= 0),
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ NOT NULL,
    payload_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_episodic_memory_ended_at ON public.episodic_memory (ended_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_customer ON public.episodic_memory (customer_id, ended_at DESC);

COMMIT;

