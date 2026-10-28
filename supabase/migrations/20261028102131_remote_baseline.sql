SET local check_function_bodies = off;

CREATE SEQUENCE "public"."customer_id_seq" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1 NO CYCLE;

CREATE SEQUENCE "public"."order_id_seq" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1 NO CYCLE;

CREATE SEQUENCE "public"."session_id_seq" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1 NO CYCLE;

CREATE TABLE "public"."checkpoint_blobs" (
  "thread_id"     text  NOT NULL,
  "checkpoint_ns" text  NOT NULL DEFAULT ''::text,
  "channel"       text  NOT NULL,
  "version"       text  NOT NULL,
  "type"          text  NOT NULL,
  "blob"          bytea,
  CONSTRAINT "checkpoint_blobs_pkey" PRIMARY KEY (thread_id, checkpoint_ns, channel, VERSION)
);

ALTER TABLE "public"."checkpoint_blobs"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."checkpoint_migrations" (
  "v" integer NOT NULL,
  CONSTRAINT "checkpoint_migrations_pkey" PRIMARY KEY (v)
);

ALTER TABLE "public"."checkpoint_migrations"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."checkpoint_writes" (
  "thread_id"     text    NOT NULL,
  "checkpoint_ns" text    NOT NULL DEFAULT ''::text,
  "checkpoint_id" text    NOT NULL,
  "task_id"       text    NOT NULL,
  "idx"           integer NOT NULL,
  "channel"       text    NOT NULL,
  "type"          text,
  "blob"          bytea   NOT NULL,
  "task_path"     text    NOT NULL DEFAULT ''::text,
  CONSTRAINT "checkpoint_writes_pkey" PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

ALTER TABLE "public"."checkpoint_writes"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."checkpoints" (
  "thread_id"            text  NOT NULL,
  "checkpoint_ns"        text  NOT NULL DEFAULT ''::text,
  "checkpoint_id"        text  NOT NULL,
  "parent_checkpoint_id" text,
  "type"                 text,
  "checkpoint"           jsonb NOT NULL,
  "metadata"             jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT "checkpoints_pkey" PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

ALTER TABLE "public"."checkpoints"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."conversation_sessions" (
  "session_id"            text                     NOT NULL,
  "customer_id"           text,
  "channel"               text                     NOT NULL DEFAULT 'web_chat'::text,
  "status"                text                     NOT NULL DEFAULT 'active'::text,
  "started_at"            timestamp with time zone NOT NULL DEFAULT now(),
  "last_activity_at"      timestamp with time zone NOT NULL DEFAULT now(),
  "ended_at"              timestamp with time zone,
  "finalized_at"          timestamp with time zone,
  "outcome"               text,
  "handoff_reason"        text,
  "call_brief_json"       jsonb,
  "call_brief_revision"   integer                  NOT NULL DEFAULT 0,
  "call_brief_updated_at" timestamp with time zone,
  "created_at"            timestamp with time zone NOT NULL DEFAULT now(),
  "updated_at"            timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "conversation_sessions_call_brief_revision_check" CHECK ((call_brief_revision >= 0)),
  CONSTRAINT "conversation_sessions_pkey" PRIMARY KEY (session_id),
  CONSTRAINT "conversation_sessions_status_check" CHECK ((status = ANY (ARRAY['active'::text, 'ending'::text, 'ended'::text, 'abandoned'::text, 'failed'::text])))
);

ALTER TABLE "public"."conversation_sessions"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."customers" (
  "customer_id"      text                     NOT NULL,
  "full_name"        text,
  "preferred_name"   text,
  "honorific"        text,
  "status"           text                     NOT NULL DEFAULT 'active'::text,
  "created_at"       timestamp with time zone NOT NULL DEFAULT now(),
  "updated_at"       timestamp with time zone NOT NULL DEFAULT now(),
  "deleted_at"       timestamp with time zone,
  "phone"            text,
  "phone_verified"   boolean                  NOT NULL DEFAULT false,
  "zalo_id"          text,
  "fb_id"            text,
  "email"            text,
  "region"           text,
  "address_line"     text,
  "ward"             text,
  "district"         text,
  "city"             text,
  "country_code"     character(2)             NOT NULL DEFAULT 'VN'::bpchar,
  "address_verified" boolean                  NOT NULL DEFAULT false,
  "source"           text,
  CONSTRAINT "chk_customers_region" CHECK (((region IS NULL) OR (region = ANY (ARRAY['bac'::text, 'trung'::text, 'nam'::text])))),
  CONSTRAINT "chk_customers_status" CHECK ((status = ANY (ARRAY['active'::text, 'provisional'::text, 'merged'::text, 'deleted'::text]))),
  CONSTRAINT "customers_pkey" PRIMARY KEY (customer_id),
  CONSTRAINT "customers_status_check" CHECK ((status = ANY (ARRAY['active'::text, 'provisional'::text, 'merged'::text, 'deleted'::text])))
);

ALTER TABLE "public"."customers"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."episodic_memory" (
  "episode_id"       uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "session_id"       text                     NOT NULL,
  "customer_id"      text,
  "summary"          text                     NOT NULL,
  "current_need"     text,
  "outcome"          text,
  "handoff_reason"   text,
  "products_advised" jsonb                    NOT NULL DEFAULT '[]'::jsonb,
  "orders_summary"   jsonb                    NOT NULL DEFAULT '[]'::jsonb,
  "open_questions"   jsonb                    NOT NULL DEFAULT '[]'::jsonb,
  "open_blockers"    jsonb                    NOT NULL DEFAULT '[]'::jsonb,
  "next_actions"     jsonb                    NOT NULL DEFAULT '[]'::jsonb,
  "source_event_ids" uuid[]                   NOT NULL DEFAULT '{}'::uuid[],
  "turn_count"       integer                  NOT NULL DEFAULT 0,
  "started_at"       timestamp with time zone,
  "ended_at"         timestamp with time zone NOT NULL,
  "payload_json"     jsonb,
  "created_at"       timestamp with time zone NOT NULL DEFAULT now(),
  "updated_at"       timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "episodic_memory_pkey" PRIMARY KEY (episode_id),
  CONSTRAINT "episodic_memory_session_id_key" UNIQUE (session_id),
  CONSTRAINT "episodic_memory_turn_count_check" CHECK ((turn_count >= 0))
);

ALTER TABLE "public"."episodic_memory"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."order_items" (
  "order_item_id"         uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "order_id"              text                     NOT NULL,
  "line_number"           integer                  NOT NULL,
  "sku"                   text                     NOT NULL,
  "product_name_snapshot" text,
  "quantity"              integer                  NOT NULL DEFAULT 1,
  "unit_price_vnd"        bigint                   NOT NULL,
  "line_total_vnd"        bigint                   NOT NULL,
  "created_at"            timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "order_items_line_number_check" CHECK ((line_number > 0)),
  CONSTRAINT "order_items_line_total_vnd_check" CHECK ((line_total_vnd >= 0)),
  CONSTRAINT "order_items_order_id_line_number_key" UNIQUE (order_id, line_number),
  CONSTRAINT "order_items_pkey" PRIMARY KEY (order_item_id),
  CONSTRAINT "order_items_quantity_check" CHECK ((quantity > 0)),
  CONSTRAINT "order_items_unit_price_vnd_check" CHECK ((unit_price_vnd >= 0))
);

ALTER TABLE "public"."order_items"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."orders" (
  "order_id"         text                     NOT NULL,
  "customer_id"      text                     NOT NULL,
  "order_date"       date                     NOT NULL,
  "status"           text                     NOT NULL,
  "tracking_number"  text,
  "total_amount_vnd" bigint,
  "currency"         character(3)             NOT NULL DEFAULT 'VND'::bpchar,
  "source_system"    text,
  "created_at"       timestamp with time zone NOT NULL DEFAULT now(),
  "updated_at"       timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "orders_pkey" PRIMARY KEY (order_id),
  CONSTRAINT "orders_total_amount_vnd_check" CHECK (((total_amount_vnd IS NULL) OR (total_amount_vnd >= 0)))
);

ALTER TABLE "public"."orders"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."product_variants" (
  "variant_sku"     character varying(100)   NOT NULL,
  "product_sku"     character varying(100)   NOT NULL,
  "size"            character varying(50),
  "color"           character varying(50),
  "price_delta_vnd" bigint                   DEFAULT 0,
  "stock"           integer                  NOT NULL DEFAULT 0,
  "created_at"      timestamp with time zone DEFAULT now(),
  "updated_at"      timestamp with time zone DEFAULT now(),
  CONSTRAINT "product_variants_pkey" PRIMARY KEY (variant_sku)
);

ALTER TABLE "public"."product_variants"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."products" (
  "sku"            character varying(100)   NOT NULL,
  "name"           character varying(255)   NOT NULL,
  "category"       character varying(100),
  "brand"          character varying(100),
  "list_price_vnd" bigint                   NOT NULL DEFAULT 0,
  "attributes"     jsonb                    DEFAULT '{}'::jsonb,
  "min_price"      bigint                   DEFAULT 0,
  "max_price"      bigint                   DEFAULT 0,
  "total_stock"    integer                  DEFAULT 0,
  "in_stock"       boolean                  DEFAULT false,
  "is_active"      boolean                  DEFAULT true,
  "created_at"     timestamp with time zone DEFAULT now(),
  "updated_at"     timestamp with time zone DEFAULT now(),
  CONSTRAINT "products_pkey" PRIMARY KEY (sku)
);

ALTER TABLE "public"."products"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."profile_facts" (
  "customer_id"       text                     NOT NULL,
  "profile_key"       text                     NOT NULL,
  "profile_value"     jsonb                    NOT NULL,
  "source_session_id" text,
  "source_event_id"   uuid,
  "source_kind"       text                     NOT NULL DEFAULT 'customer_stated'::text,
  "confidence"        numeric(4,3),
  "updated_at"        timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "chk_profile_facts_confidence" CHECK (((confidence IS NULL) OR ((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)))),
  CONSTRAINT "profile_facts_confidence_check" CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))),
  CONSTRAINT "profile_facts_pkey" PRIMARY KEY (customer_id, profile_key)
);

ALTER TABLE "public"."profile_facts"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."promotions" (
  "promo_code"       character varying(100)   NOT NULL,
  "name"             character varying(255)   NOT NULL,
  "applies_to"       text[]                   NOT NULL,
  "type"             character varying(50)    NOT NULL,
  "gift_sku"         character varying(100),
  "discount_vnd"     bigint                   DEFAULT 0,
  "discount_percent" integer                  DEFAULT 0,
  "min_order_vnd"    bigint                   DEFAULT 0,
  "start_date"       date                     NOT NULL,
  "end_date"         date                     NOT NULL,
  "stackable"        boolean                  DEFAULT false,
  "conditions"       jsonb                    DEFAULT '{}'::jsonb,
  "created_at"       timestamp with time zone DEFAULT now(),
  "updated_at"       timestamp with time zone DEFAULT now(),
  CONSTRAINT "promotions_pkey" PRIMARY KEY (promo_code)
);

ALTER TABLE "public"."promotions"
  ENABLE ROW LEVEL SECURITY;

CREATE TABLE "public"."working_events" (
  "event_id"     uuid                     NOT NULL DEFAULT gen_random_uuid(),
  "session_id"   text                     NOT NULL,
  "turn_id"      text                     NOT NULL,
  "turn_number"  integer                  NOT NULL,
  "customer_id"  text,
  "event_type"   text                     NOT NULL DEFAULT 'turn_saved'::text,
  "event_index"  integer                  NOT NULL DEFAULT 0,
  "payload_json" jsonb                    NOT NULL DEFAULT '{}'::jsonb,
  "created_at"   timestamp with time zone NOT NULL DEFAULT now(),
  CONSTRAINT "uq_working_events_turn_num" UNIQUE (session_id, turn_number),
  CONSTRAINT "uq_working_events_turn" UNIQUE (session_id, turn_id),
  CONSTRAINT "working_events_event_index_check" CHECK ((event_index >= 0)),
  CONSTRAINT "working_events_pkey" PRIMARY KEY (event_id),
  CONSTRAINT "working_events_turn_number_check" CHECK ((turn_number >= 1))
);

ALTER TABLE "public"."working_events"
  ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.rls_auto_enable()
  RETURNS event_trigger
  LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path TO 'pg_catalog'
  AS $function$
DECLARE
  cmd record;
  tbl name;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        SELECT c.relname INTO tbl FROM pg_catalog.pg_class c WHERE c.oid = cmd.objid;
        EXECUTE format('alter table if exists %I.%I enable row level security', cmd.schema_name, tbl);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$function$;

CREATE OR REPLACE FUNCTION public.update_product_aggregated_stats()
  RETURNS TRIGGER
  LANGUAGE plpgsql
  AS $function$
DECLARE
    target_sku VARCHAR(100);
    base_price BIGINT;
BEGIN
    IF (TG_OP = 'DELETE') THEN
        target_sku := OLD.product_sku;
    ELSE
        target_sku := NEW.product_sku;
    END IF;

    SELECT list_price_vnd INTO base_price FROM products WHERE sku = target_sku;

    IF base_price IS NOT NULL THEN
        UPDATE products
        SET 
            min_price = COALESCE((SELECT MIN(base_price + price_delta_vnd) FROM product_variants WHERE product_sku = target_sku), base_price),
            max_price = COALESCE((SELECT MAX(base_price + price_delta_vnd) FROM product_variants WHERE product_sku = target_sku), base_price),
            total_stock = COALESCE((SELECT SUM(stock) FROM product_variants WHERE product_sku = target_sku), 0),
            in_stock = (COALESCE((SELECT SUM(stock) FROM product_variants WHERE product_sku = target_sku), 0) > 0),
            updated_at = NOW()
        WHERE sku = target_sku;
    END IF;

    RETURN NULL;
END;
$function$;

ALTER TABLE "public"."conversation_sessions"
  ADD CONSTRAINT "conversation_sessions_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id) ON DELETE RESTRICT;

ALTER TABLE "public"."episodic_memory"
  ADD CONSTRAINT "episodic_memory_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id) ON DELETE RESTRICT;

ALTER TABLE "public"."episodic_memory"
  ADD CONSTRAINT "episodic_memory_session_id_fkey" FOREIGN KEY (session_id) REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT;

ALTER TABLE "public"."orders"
  ADD CONSTRAINT "orders_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id) ON DELETE RESTRICT;

ALTER TABLE "public"."order_items"
  ADD CONSTRAINT "order_items_order_id_fkey" FOREIGN KEY (order_id) REFERENCES public.orders(order_id) ON DELETE RESTRICT;

ALTER TABLE "public"."product_variants"
  ADD CONSTRAINT "product_variants_product_sku_fkey" FOREIGN KEY (product_sku) REFERENCES public.products(sku) ON DELETE CASCADE;

ALTER TABLE "public"."profile_facts"
  ADD CONSTRAINT "profile_facts_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id) ON DELETE RESTRICT;

ALTER TABLE "public"."profile_facts"
  ADD CONSTRAINT "profile_facts_source_session_id_fkey" FOREIGN KEY (source_session_id) REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT;

ALTER TABLE "public"."promotions"
  ADD CONSTRAINT "promotions_gift_sku_fkey" FOREIGN KEY (gift_sku) REFERENCES public.products(sku) ON DELETE SET NULL;

ALTER TABLE "public"."working_events"
  ADD CONSTRAINT "working_events_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES public.customers(customer_id) ON DELETE RESTRICT;

ALTER TABLE "public"."profile_facts"
  ADD CONSTRAINT "profile_facts_source_event_id_fkey" FOREIGN KEY (source_event_id) REFERENCES public.working_events(event_id) ON DELETE RESTRICT;

ALTER TABLE "public"."working_events"
  ADD CONSTRAINT "working_events_session_id_fkey" FOREIGN KEY (session_id) REFERENCES public.conversation_sessions(session_id) ON DELETE RESTRICT;

CREATE INDEX checkpoint_blobs_thread_id_idx ON public.checkpoint_blobs USING btree (thread_id);

CREATE INDEX checkpoint_writes_thread_id_idx ON public.checkpoint_writes USING btree (thread_id);

CREATE INDEX checkpoints_thread_id_idx ON public.checkpoints USING btree (thread_id);

CREATE INDEX idx_conversation_sessions_customer ON public.conversation_sessions USING btree (customer_id, started_at DESC);

CREATE INDEX idx_conversation_sessions_status ON public.conversation_sessions USING btree (status, last_activity_at DESC);

CREATE INDEX idx_customers_phone ON public.customers USING btree (phone)
  WHERE (deleted_at IS NULL);

CREATE INDEX idx_customers_status ON public.customers USING btree (status)
  WHERE (deleted_at IS NULL);

CREATE INDEX idx_episodic_memory_customer ON public.episodic_memory USING btree (customer_id, ended_at DESC);

CREATE INDEX idx_episodic_memory_ended_at ON public.episodic_memory USING btree (ended_at DESC);

CREATE INDEX idx_orders_customer_date ON public.orders USING btree (customer_id, order_date DESC);

CREATE INDEX idx_orders_tracking ON public.orders USING btree (tracking_number)
  WHERE (tracking_number IS NOT NULL);

CREATE INDEX idx_products_in_stock ON public.products USING btree (in_stock)
  WHERE (in_stock = true);

CREATE INDEX idx_products_price ON public.products USING btree (min_price, max_price);

CREATE INDEX idx_profile_facts_session ON public.profile_facts USING btree (source_session_id);

CREATE INDEX idx_promotions_dates ON public.promotions USING btree (start_date, end_date);

CREATE INDEX idx_promotions_gift_sku ON public.promotions USING btree (gift_sku);

CREATE INDEX idx_variants_product_sku ON public.product_variants USING btree (product_sku);

CREATE INDEX idx_working_events_customer ON public.working_events USING btree (customer_id, created_at);

CREATE INDEX idx_working_events_session_turn ON public.working_events USING btree (session_id, turn_number, created_at);

CREATE UNIQUE INDEX uq_customers_email ON public.customers USING btree (lower(email))
  WHERE ((deleted_at IS NULL) AND (email IS NOT NULL) AND (email <> ''::text));

CREATE UNIQUE INDEX uq_customers_fb ON public.customers USING btree (fb_id)
  WHERE ((deleted_at IS NULL) AND (fb_id IS NOT NULL) AND (fb_id <> ''::text));

CREATE UNIQUE INDEX uq_customers_zalo ON public.customers USING btree (zalo_id)
  WHERE ((deleted_at IS NULL) AND (zalo_id IS NOT NULL) AND (zalo_id <> ''::text));

CREATE TRIGGER trg_update_product_stats
  AFTER INSERT OR DELETE OR UPDATE ON public.product_variants
  FOR EACH ROW
  EXECUTE FUNCTION public.update_product_aggregated_stats();

CREATE EVENT TRIGGER "ensure_rls"
  ON ddl_command_end
  WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
  EXECUTE FUNCTION "public"."rls_auto_enable"();

GRANT EXECUTE ON FUNCTION "public"."rls_auto_enable"() TO PUBLIC, "anon", "authenticated";

REVOKE ALL ON FUNCTION "public"."rls_auto_enable"() FROM "postgres";

GRANT EXECUTE ON FUNCTION "public"."rls_auto_enable"() TO "postgres";

GRANT EXECUTE ON FUNCTION "public"."rls_auto_enable"() TO "service_role";

GRANT EXECUTE ON FUNCTION "public"."update_product_aggregated_stats"() TO PUBLIC, "anon", "authenticated";

REVOKE ALL ON FUNCTION "public"."update_product_aggregated_stats"() FROM "postgres";

GRANT EXECUTE ON FUNCTION "public"."update_product_aggregated_stats"() TO "postgres";

GRANT EXECUTE ON FUNCTION "public"."update_product_aggregated_stats"() TO "service_role";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."customer_id_seq" TO "anon", "authenticated";

REVOKE ALL ON SEQUENCE "public"."customer_id_seq" FROM "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."customer_id_seq" TO "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."customer_id_seq" TO "service_role";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."order_id_seq" TO "anon", "authenticated";

REVOKE ALL ON SEQUENCE "public"."order_id_seq" FROM "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."order_id_seq" TO "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."order_id_seq" TO "service_role";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."session_id_seq" TO "anon", "authenticated";

REVOKE ALL ON SEQUENCE "public"."session_id_seq" FROM "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."session_id_seq" TO "postgres";

GRANT SELECT, UPDATE, USAGE ON SEQUENCE "public"."session_id_seq" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_blobs" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."checkpoint_blobs" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_blobs" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_blobs" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_migrations" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."checkpoint_migrations" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_migrations" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_migrations" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_writes" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."checkpoint_writes" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_writes" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoint_writes" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoints" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."checkpoints" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoints" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."checkpoints" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."conversation_sessions" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."conversation_sessions" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."conversation_sessions" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."conversation_sessions" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."customers" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."customers" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."customers" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."customers" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."episodic_memory" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."episodic_memory" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."episodic_memory" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."episodic_memory" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."order_items" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."order_items" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."order_items" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."order_items" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."orders" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."orders" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."orders" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."orders" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."product_variants" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."product_variants" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."product_variants" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."product_variants" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."products" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."products" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."products" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."products" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."profile_facts" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."profile_facts" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."profile_facts" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."profile_facts" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."promotions" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."promotions" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."promotions" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."promotions" TO "service_role";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."working_events" TO "anon", "authenticated";

REVOKE ALL ON TABLE "public"."working_events" FROM "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."working_events" TO "postgres";

GRANT DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE ON TABLE "public"."working_events" TO "service_role";

