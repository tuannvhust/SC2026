# Database Schema v1  -  Live Database Audit

**Audit time:** 2026-10-17 15:16 UTC  
**Mode:** live PostgreSQL catalog and aggregate SELECT; read-only transaction is on.  
**No writes:** no app store constructor, create_all, LangGraph setup, migration, DDL/DML, or fixture ran.  
**Target:** configured DB matched `SUPABASE_URL`; project and database matched the prior snapshot; database `postgres`. Project reference and connection details are omitted.  
**Server:** PostgreSQL 17.11; **schemas:** 9; **base/partitioned tables:** 50.

## Evidence labels

- **Live catalog:** read from PostgreSQL system catalogs/information schema.
- **Live aggregate:** count/validation only; no row values selected.
- **Source code:** inspected repository.
- **Prior dump:** earlier point-in-time snapshot only.
- **Not verified:** insufficient evidence.

## 1. Catalog summary

- Non-system schemas: `auth, extensions, graphql, graphql_public, pgbouncer, public, realtime, storage, vault`.
- Business customer/CRM/address/order/session name matches: **none found**.
- Three non-table relations (views/materialized/foreign relations) were present; none had customer, CRM, address, order, session, identity, profile, memory, episode, or Call Brief names.
- `auth.users`, `auth.identities`, and `auth.sessions` are Supabase Auth state, not an established CRM/customer/session model.
- `public` contains four app-memory tables, four checkpoint tables, and product catalog tables.
- Target was matched internally to configured project and prior snapshot; no host, URL, credentials, customer records, or full IDs included.
- Live memory counts are now `working_events` 75, `episodic_memory` 7, `profile_facts` 6, `profile_fact_history` 11. The prior dump reported 67, 6, 5, and 10 respectively, so the dump counts are stale.
- **Access-control finding:** all four checkpoint tables and all four app-memory tables have RLS disabled, no visible policies, and table grants to `anon` and `authenticated` that include `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and `TRUNCATE`. The `public` schema also grants `USAGE` to `anon`, `authenticated`, and `service_role` (no `CREATE`). Catalog grants alone do not prove the Supabase API exposes these tables; API schema exposure/configuration was not tested. This needs a separate access review before any migration or API exposure change.

### All discovered non-system tables

- `auth` (27): `audit_log_entries`, `custom_oauth_providers`, `flow_state`, `identities`, `instances`, `mfa_amr_claims`, `mfa_challenges`, `mfa_factors`, `mfa_recovery_code_sets`, `mfa_recovery_codes`, `oauth_authorizations`, `oauth_client_states`, `oauth_clients`, `oauth_consents`, `one_time_tokens`, `refresh_tokens`, `saml_providers`, `saml_relay_states`, `schema_migrations`, `scim_tokens`, `scim_users`, `sessions`, `sso_domains`, `sso_providers`, `users`, `webauthn_challenges`, `webauthn_credentials`
- `extensions` (0): (none)
- `graphql` (0): (none)
- `graphql_public` (0): (none)
- `pgbouncer` (0): (none)
- `public` (11): `checkpoint_blobs`, `checkpoint_migrations`, `checkpoint_writes`, `checkpoints`, `episodic_memory`, `product_variants`, `products`, `profile_fact_history`, `profile_facts`, `promotions`, `working_events`
- `realtime` (3): `messages`, `schema_migrations`, `subscription`
- `storage` (8): `buckets`, `buckets_analytics`, `buckets_vectors`, `migrations`, `objects`, `s3_multipart_uploads`, `s3_multipart_uploads_parts`, `vector_indexes`
- `vault` (1): `secrets`

### LangGraph checkpointer

- `requirements.txt` declares `langgraph-checkpoint-postgres>=2.0.0`, `langgraph>=1.0.0`, `psycopg[binary,pool]>=3.2.0`, `psycopg2-binary>=2.9.0`.
- Base Python metadata: `langgraph-checkpoint-postgres` not installed; `langgraph` 1.1.2; `SQLAlchemy` 2.0.39; `psycopg` not installed; `psycopg2-binary` not installed.
- Audit `.venv` metadata: `langgraph-checkpoint-postgres` not installed; `langgraph` not installed; `SQLAlchemy` 2.1.5; `psycopg` 3.3.6; `psycopg2-binary` 2.9.13.
- `Dockerfile.backend` builds from Python 3.11 and installs `requirements.txt`; the saver dependency is only lower-bounded (`>=2.0.0`). The deployed image’s resolved package version was not available for inspection.
- Live tables: `public.checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`; checkpoint payload was not read.
- Migration version aggregate: `{'migration_rows': 10, 'min_version': 0, 'max_version': 9}`. Deployed saver package version is not verified because absent from both local interpreters; no setup was called.

## 2. Full table inventory

All non-system table names are listed above. Detailed metadata below covers all `public` tables and all relevant customer/identity/address/order/session/memory/checkpoint matches, plus Auth users/identities/sessions. Other internal service tables are catalog-listed but not full-scanned.

### `auth.identities`

- Kind `r`; rows `exact 0`; RLS `True`; FORCE RLS `False`.
- Columns: `provider_id` `text` NOT NULL; `user_id` `uuid` NOT NULL; `identity_data` `jsonb` NOT NULL; `provider` `text` NOT NULL; `last_sign_in_at` `timestamp with time zone` NULL; `created_at` `timestamp with time zone` NULL; `updated_at` `timestamp with time zone` NULL; `email` `text` NULL DEFAULT `lower((identity_data ->> 'email'::text))`; `id` `uuid` NOT NULL DEFAULT `gen_random_uuid()`.
- Constraints: `FOREIGN KEY identities_user_id_fkey` FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE (validated); `PRIMARY KEY identities_pkey` PRIMARY KEY (id) (validated); `UNIQUE identities_provider_id_provider_unique` UNIQUE (provider_id, provider) (validated).
- Indexes: `identities_email_idx` CREATE INDEX identities_email_idx ON auth.identities USING btree (email text_pattern_ops); `identities_pkey` CREATE UNIQUE INDEX identities_pkey ON auth.identities USING btree (id); `identities_provider_id_provider_unique` CREATE UNIQUE INDEX identities_provider_id_provider_unique ON auth.identities USING btree (provider_id, provider); `identities_user_id_idx` CREATE INDEX identities_user_id_idx ON auth.identities USING btree (user_id).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `postgres`:DELETE; `postgres`:INSERT; `postgres`:REFERENCES; `postgres`:SELECT (grantable); `postgres`:TRIGGER; `postgres`:TRUNCATE; `postgres`:UPDATE.

### `auth.sessions`

- Kind `r`; rows `exact 0`; RLS `True`; FORCE RLS `False`.
- Columns: `id` `uuid` NOT NULL; `user_id` `uuid` NOT NULL; `created_at` `timestamp with time zone` NULL; `updated_at` `timestamp with time zone` NULL; `factor_id` `uuid` NULL; `aal` `auth.aal_level` NULL; `not_after` `timestamp with time zone` NULL; `refreshed_at` `timestamp without time zone` NULL; `user_agent` `text` NULL; `ip` `inet` NULL; `tag` `text` NULL; `oauth_client_id` `uuid` NULL; `refresh_token_hmac_key` `text` NULL; `refresh_token_counter` `bigint` NULL; `scopes` `text` NULL.
- Constraints: `CHECK sessions_scopes_length` CHECK (char_length(scopes) <= 4096) (validated); `FOREIGN KEY sessions_oauth_client_id_fkey` FOREIGN KEY (oauth_client_id) REFERENCES auth.oauth_clients(id) ON DELETE CASCADE (validated); `FOREIGN KEY sessions_user_id_fkey` FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE (validated); `PRIMARY KEY sessions_pkey` PRIMARY KEY (id) (validated).
- Indexes: `sessions_not_after_idx` CREATE INDEX sessions_not_after_idx ON auth.sessions USING btree (not_after DESC); `sessions_oauth_client_id_idx` CREATE INDEX sessions_oauth_client_id_idx ON auth.sessions USING btree (oauth_client_id); `sessions_pkey` CREATE UNIQUE INDEX sessions_pkey ON auth.sessions USING btree (id); `sessions_user_id_idx` CREATE INDEX sessions_user_id_idx ON auth.sessions USING btree (user_id); `user_id_created_at_idx` CREATE INDEX user_id_created_at_idx ON auth.sessions USING btree (user_id, created_at).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `postgres`:DELETE; `postgres`:INSERT; `postgres`:REFERENCES; `postgres`:SELECT (grantable); `postgres`:TRIGGER; `postgres`:TRUNCATE; `postgres`:UPDATE.

### `auth.users`

- Kind `r`; rows `exact 0`; RLS `True`; FORCE RLS `False`.
- Columns: `instance_id` `uuid` NULL; `id` `uuid` NOT NULL; `aud` `character varying(255)` NULL; `role` `character varying(255)` NULL; `email` `character varying(255)` NULL; `encrypted_password` `character varying(255)` NULL; `email_confirmed_at` `timestamp with time zone` NULL; `invited_at` `timestamp with time zone` NULL; `confirmation_token` `character varying(255)` NULL; `confirmation_sent_at` `timestamp with time zone` NULL; `recovery_token` `character varying(255)` NULL; `recovery_sent_at` `timestamp with time zone` NULL; `email_change_token_new` `character varying(255)` NULL; `email_change` `character varying(255)` NULL; `email_change_sent_at` `timestamp with time zone` NULL; `last_sign_in_at` `timestamp with time zone` NULL; `raw_app_meta_data` `jsonb` NULL; `raw_user_meta_data` `jsonb` NULL; `is_super_admin` `boolean` NULL; `created_at` `timestamp with time zone` NULL; `updated_at` `timestamp with time zone` NULL; `phone` `text` NULL DEFAULT `NULL::character varying`; `phone_confirmed_at` `timestamp with time zone` NULL; `phone_change` `text` NULL DEFAULT `''::character varying`; `phone_change_token` `character varying(255)` NULL DEFAULT `''::character varying`; `phone_change_sent_at` `timestamp with time zone` NULL; `confirmed_at` `timestamp with time zone` NULL DEFAULT `LEAST(email_confirmed_at, phone_confirmed_at)`; `email_change_token_current` `character varying(255)` NULL DEFAULT `''::character varying`; `email_change_confirm_status` `smallint` NULL DEFAULT `0`; `banned_until` `timestamp with time zone` NULL; `reauthentication_token` `character varying(255)` NULL DEFAULT `''::character varying`; `reauthentication_sent_at` `timestamp with time zone` NULL; `is_sso_user` `boolean` NOT NULL DEFAULT `false`; `deleted_at` `timestamp with time zone` NULL; `is_anonymous` `boolean` NOT NULL DEFAULT `false`.
- Constraints: `CHECK users_email_change_confirm_status_check` CHECK (email_change_confirm_status >= 0 AND email_change_confirm_status <= 2) (validated); `PRIMARY KEY users_pkey` PRIMARY KEY (id) (validated); `UNIQUE users_phone_key` UNIQUE (phone) (validated).
- Indexes: `confirmation_token_idx` CREATE UNIQUE INDEX confirmation_token_idx ON auth.users USING btree (confirmation_token) WHERE ((confirmation_token)::text !~ '^[0-9 ]*$'::text); `email_change_token_current_idx` CREATE UNIQUE INDEX email_change_token_current_idx ON auth.users USING btree (email_change_token_current) WHERE ((email_change_token_current)::text !~ '^[0-9 ]*$'::text); `email_change_token_new_idx` CREATE UNIQUE INDEX email_change_token_new_idx ON auth.users USING btree (email_change_token_new) WHERE ((email_change_token_new)::text !~ '^[0-9 ]*$'::text); `idx_users_created_at_desc` CREATE INDEX idx_users_created_at_desc ON auth.users USING btree (created_at DESC); `idx_users_email` CREATE INDEX idx_users_email ON auth.users USING btree (email); `idx_users_last_sign_in_at_desc` CREATE INDEX idx_users_last_sign_in_at_desc ON auth.users USING btree (last_sign_in_at DESC); `idx_users_name` CREATE INDEX idx_users_name ON auth.users USING btree (((raw_user_meta_data ->> 'name'::text))) WHERE ((raw_user_meta_data ->> 'name'::text) IS NOT NULL); `reauthentication_token_idx` CREATE UNIQUE INDEX reauthentication_token_idx ON auth.users USING btree (reauthentication_token) WHERE ((reauthentication_token)::text !~ '^[0-9 ]*$'::text); `recovery_token_idx` CREATE UNIQUE INDEX recovery_token_idx ON auth.users USING btree (recovery_token) WHERE ((recovery_token)::text !~ '^[0-9 ]*$'::text); `users_email_partial_key` CREATE UNIQUE INDEX users_email_partial_key ON auth.users USING btree (email) WHERE (is_sso_user = false); `users_instance_id_email_idx` CREATE INDEX users_instance_id_email_idx ON auth.users USING btree (instance_id, lower((email)::text)); `users_instance_id_idx` CREATE INDEX users_instance_id_idx ON auth.users USING btree (instance_id); `users_is_anonymous_idx` CREATE INDEX users_is_anonymous_idx ON auth.users USING btree (is_anonymous); `users_phone_key` CREATE UNIQUE INDEX users_phone_key ON auth.users USING btree (phone); `users_pkey` CREATE UNIQUE INDEX users_pkey ON auth.users USING btree (id).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `postgres`:DELETE; `postgres`:INSERT; `postgres`:REFERENCES; `postgres`:SELECT (grantable); `postgres`:TRIGGER; `postgres`:TRUNCATE; `postgres`:UPDATE.

### `public.checkpoint_blobs`

- Kind `r`; rows `exact 453`; RLS `False`; FORCE RLS `False`.
- Columns: `thread_id` `text` NOT NULL; `checkpoint_ns` `text` NOT NULL DEFAULT `''::text`; `channel` `text` NOT NULL; `version` `text` NOT NULL; `type` `text` NOT NULL; `blob` `bytea` NULL.
- Constraints: `PRIMARY KEY checkpoint_blobs_pkey` PRIMARY KEY (thread_id, checkpoint_ns, channel, version) (validated).
- Indexes: `checkpoint_blobs_pkey` CREATE UNIQUE INDEX checkpoint_blobs_pkey ON public.checkpoint_blobs USING btree (thread_id, checkpoint_ns, channel, version); `checkpoint_blobs_thread_id_idx` CREATE INDEX checkpoint_blobs_thread_id_idx ON public.checkpoint_blobs USING btree (thread_id).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.checkpoint_migrations`

- Kind `r`; rows `exact 10`; RLS `False`; FORCE RLS `False`.
- Columns: `v` `integer` NOT NULL.
- Constraints: `PRIMARY KEY checkpoint_migrations_pkey` PRIMARY KEY (v) (validated).
- Indexes: `checkpoint_migrations_pkey` CREATE UNIQUE INDEX checkpoint_migrations_pkey ON public.checkpoint_migrations USING btree (v).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.checkpoint_writes`

- Kind `r`; rows `exact 1677`; RLS `False`; FORCE RLS `False`.
- Columns: `thread_id` `text` NOT NULL; `checkpoint_ns` `text` NOT NULL DEFAULT `''::text`; `checkpoint_id` `text` NOT NULL; `task_id` `text` NOT NULL; `idx` `integer` NOT NULL; `channel` `text` NOT NULL; `type` `text` NULL; `blob` `bytea` NOT NULL; `task_path` `text` NOT NULL DEFAULT `''::text`.
- Constraints: `PRIMARY KEY checkpoint_writes_pkey` PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) (validated).
- Indexes: `checkpoint_writes_pkey` CREATE UNIQUE INDEX checkpoint_writes_pkey ON public.checkpoint_writes USING btree (thread_id, checkpoint_ns, checkpoint_id, task_id, idx); `checkpoint_writes_thread_id_idx` CREATE INDEX checkpoint_writes_thread_id_idx ON public.checkpoint_writes USING btree (thread_id).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.checkpoints`

- Kind `r`; rows `exact 469`; RLS `False`; FORCE RLS `False`.
- Columns: `thread_id` `text` NOT NULL; `checkpoint_ns` `text` NOT NULL DEFAULT `''::text`; `checkpoint_id` `text` NOT NULL; `parent_checkpoint_id` `text` NULL; `type` `text` NULL; `checkpoint` `jsonb` NOT NULL; `metadata` `jsonb` NOT NULL DEFAULT `'{}'::jsonb`.
- Constraints: `PRIMARY KEY checkpoints_pkey` PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id) (validated).
- Indexes: `checkpoints_pkey` CREATE UNIQUE INDEX checkpoints_pkey ON public.checkpoints USING btree (thread_id, checkpoint_ns, checkpoint_id); `checkpoints_thread_id_idx` CREATE INDEX checkpoints_thread_id_idx ON public.checkpoints USING btree (thread_id).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.episodic_memory`

- Kind `r`; rows `exact 7`; RLS `False`; FORCE RLS `False`.
- Columns: `session_id` `character varying` NOT NULL; `customer_id` `character varying` NULL; `ended_at` `character varying` NOT NULL; `payload_json` `character varying` NOT NULL.
- Constraints: `PRIMARY KEY episodic_memory_pkey` PRIMARY KEY (session_id) (validated).
- Indexes: `episodic_memory_pkey` CREATE UNIQUE INDEX episodic_memory_pkey ON public.episodic_memory USING btree (session_id); `idx_episodic_memory_customer` CREATE INDEX idx_episodic_memory_customer ON public.episodic_memory USING btree (customer_id, ended_at).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.product_variants`

- Kind `r`; rows `exact 96`; RLS `True`; FORCE RLS `False`.
- Columns: `variant_sku` `character varying(100)` NOT NULL; `product_sku` `character varying(100)` NOT NULL; `size` `character varying(50)` NULL; `color` `character varying(50)` NULL; `price_delta_vnd` `bigint` NULL DEFAULT `0`; `stock` `integer` NOT NULL DEFAULT `0`; `created_at` `timestamp with time zone` NULL DEFAULT `now()`; `updated_at` `timestamp with time zone` NULL DEFAULT `now()`.
- Constraints: `FOREIGN KEY product_variants_product_sku_fkey` FOREIGN KEY (product_sku) REFERENCES products(sku) ON DELETE CASCADE (validated); `PRIMARY KEY product_variants_pkey` PRIMARY KEY (variant_sku) (validated).
- Indexes: `idx_variants_product_sku` CREATE INDEX idx_variants_product_sku ON public.product_variants USING btree (product_sku); `product_variants_pkey` CREATE UNIQUE INDEX product_variants_pkey ON public.product_variants USING btree (variant_sku).
- Non-internal triggers: `trg_update_product_stats` CREATE TRIGGER trg_update_product_stats AFTER INSERT OR DELETE OR UPDATE ON product_variants FOR EACH ROW EXECUTE FUNCTION update_product_aggregated_stats().
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.products`

- Kind `r`; rows `exact 40`; RLS `True`; FORCE RLS `False`.
- Columns: `sku` `character varying(100)` NOT NULL; `name` `character varying(255)` NOT NULL; `category` `character varying(100)` NULL; `brand` `character varying(100)` NULL; `list_price_vnd` `bigint` NOT NULL DEFAULT `0`; `attributes` `jsonb` NULL DEFAULT `'{}'::jsonb`; `min_price` `bigint` NULL DEFAULT `0`; `max_price` `bigint` NULL DEFAULT `0`; `total_stock` `integer` NULL DEFAULT `0`; `in_stock` `boolean` NULL DEFAULT `false`; `is_active` `boolean` NULL DEFAULT `true`; `created_at` `timestamp with time zone` NULL DEFAULT `now()`; `updated_at` `timestamp with time zone` NULL DEFAULT `now()`.
- Constraints: `PRIMARY KEY products_pkey` PRIMARY KEY (sku) (validated).
- Indexes: `idx_products_in_stock` CREATE INDEX idx_products_in_stock ON public.products USING btree (in_stock) WHERE (in_stock = true); `idx_products_price` CREATE INDEX idx_products_price ON public.products USING btree (min_price, max_price); `products_pkey` CREATE UNIQUE INDEX products_pkey ON public.products USING btree (sku).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.profile_fact_history`

- Kind `r`; rows `exact 11`; RLS `False`; FORCE RLS `False`.
- Columns: `history_id` `integer` NOT NULL DEFAULT `nextval('profile_fact_history_history_id_seq'::regclass)`; `customer_id` `character varying` NOT NULL; `profile_key` `character varying` NOT NULL; `old_value_json` `character varying` NULL; `new_value_json` `character varying` NOT NULL; `provenance_session_id` `character varying` NOT NULL; `changed_at` `character varying` NOT NULL.
- Constraints: `PRIMARY KEY profile_fact_history_pkey` PRIMARY KEY (history_id) (validated).
- Indexes: `idx_profile_fact_history_customer` CREATE INDEX idx_profile_fact_history_customer ON public.profile_fact_history USING btree (customer_id, profile_key, changed_at); `profile_fact_history_pkey` CREATE UNIQUE INDEX profile_fact_history_pkey ON public.profile_fact_history USING btree (history_id).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.profile_facts`

- Kind `r`; rows `exact 6`; RLS `False`; FORCE RLS `False`.
- Columns: `customer_id` `character varying` NOT NULL; `profile_key` `character varying` NOT NULL; `profile_value_json` `character varying` NOT NULL; `provenance_session_id` `character varying` NOT NULL; `updated_at` `character varying` NOT NULL.
- Constraints: `PRIMARY KEY profile_facts_pkey` PRIMARY KEY (customer_id, profile_key) (validated).
- Indexes: `profile_facts_pkey` CREATE UNIQUE INDEX profile_facts_pkey ON public.profile_facts USING btree (customer_id, profile_key).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.promotions`

- Kind `r`; rows `exact 13`; RLS `True`; FORCE RLS `False`.
- Columns: `promo_code` `character varying(100)` NOT NULL; `name` `character varying(255)` NOT NULL; `applies_to` `text[]` NOT NULL; `type` `character varying(50)` NOT NULL; `gift_sku` `character varying(100)` NULL; `discount_vnd` `bigint` NULL DEFAULT `0`; `discount_percent` `integer` NULL DEFAULT `0`; `min_order_vnd` `bigint` NULL DEFAULT `0`; `start_date` `date` NOT NULL; `end_date` `date` NOT NULL; `stackable` `boolean` NULL DEFAULT `false`; `conditions` `jsonb` NULL DEFAULT `'{}'::jsonb`; `created_at` `timestamp with time zone` NULL DEFAULT `now()`; `updated_at` `timestamp with time zone` NULL DEFAULT `now()`.
- Constraints: `FOREIGN KEY promotions_gift_sku_fkey` FOREIGN KEY (gift_sku) REFERENCES products(sku) ON DELETE SET NULL (validated); `PRIMARY KEY promotions_pkey` PRIMARY KEY (promo_code) (validated).
- Indexes: `idx_promotions_dates` CREATE INDEX idx_promotions_dates ON public.promotions USING btree (start_date, end_date); `idx_promotions_gift_sku` CREATE INDEX idx_promotions_gift_sku ON public.promotions USING btree (gift_sku); `promotions_pkey` CREATE UNIQUE INDEX promotions_pkey ON public.promotions USING btree (promo_code).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

### `public.working_events`

- Kind `r`; rows `exact 75`; RLS `False`; FORCE RLS `False`.
- Columns: `event_id` `character varying` NOT NULL; `session_id` `character varying` NOT NULL; `turn_id` `character varying` NOT NULL; `turn_number` `integer` NOT NULL; `customer_id` `character varying` NULL; `created_at` `character varying` NOT NULL; `payload_json` `character varying` NOT NULL.
- Constraints: `PRIMARY KEY working_events_pkey` PRIMARY KEY (event_id) (validated); `UNIQUE working_events_session_id_turn_id_key` UNIQUE (session_id, turn_id) (validated); `UNIQUE working_events_session_id_turn_number_key` UNIQUE (session_id, turn_number) (validated).
- Indexes: `idx_working_events_customer` CREATE INDEX idx_working_events_customer ON public.working_events USING btree (customer_id, created_at); `working_events_pkey` CREATE UNIQUE INDEX working_events_pkey ON public.working_events USING btree (event_id); `working_events_session_id_turn_id_key` CREATE UNIQUE INDEX working_events_session_id_turn_id_key ON public.working_events USING btree (session_id, turn_id); `working_events_session_id_turn_number_key` CREATE UNIQUE INDEX working_events_session_id_turn_number_key ON public.working_events USING btree (session_id, turn_number).
- Non-internal triggers: (none).
- Policies: (none visible).
- Visible grants: `anon`:DELETE; `anon`:INSERT; `anon`:REFERENCES; `anon`:SELECT; `anon`:TRIGGER; `anon`:TRUNCATE; `anon`:UPDATE; `authenticated`:DELETE; `authenticated`:INSERT; `authenticated`:REFERENCES; `authenticated`:SELECT; `authenticated`:TRIGGER; `authenticated`:TRUNCATE; `authenticated`:UPDATE; `postgres`:DELETE (grantable); `postgres`:INSERT (grantable); `postgres`:REFERENCES (grantable); `postgres`:SELECT (grantable); `postgres`:TRIGGER (grantable); `postgres`:TRUNCATE (grantable); `postgres`:UPDATE (grantable); `service_role`:DELETE; `service_role`:INSERT; `service_role`:REFERENCES; `service_role`:SELECT; `service_role`:TRIGGER; `service_role`:TRUNCATE; `service_role`:UPDATE.

## 3. Data-integrity aggregates

Counts only; no customer values, payload contents, addresses, tokens, or full IDs selected. JSON/time checks use `pg_input_is_valid`.

- **working_events  -  customer id counts:** `total=75`, `null_customer=7`, `anonymous_customer=20`
- **working_events  -  created_at invalid timestamptz count:** `count=0`
- **working_events  -  payload_json invalid JSONB count:** `count=0`
- **working_events  -  possible test-like pattern rows; unverified:** `count=55`
- **profile_facts  -  customer id counts:** `total=6`, `null_customer=0`, `anonymous_customer=1`
- **profile_facts  -  profile_value_json invalid JSONB count:** `count=0`
- **profile_facts  -  updated_at invalid timestamptz count:** `count=0`
- **profile_facts  -  possible test-like pattern rows; unverified:** `count=5`
- **profile_fact_history  -  customer id counts:** `total=11`, `null_customer=0`, `anonymous_customer=1`
- **profile_fact_history  -  old_value_json invalid JSONB count:** `count=0`
- **profile_fact_history  -  new_value_json invalid JSONB count:** `count=0`
- **profile_fact_history  -  changed_at invalid timestamptz count:** `count=0`
- **profile_fact_history  -  possible test-like pattern rows; unverified:** `count=10`
- **episodic_memory  -  customer id counts:** `total=7`, `null_customer=0`, `anonymous_customer=1`
- **episodic_memory  -  ended_at invalid timestamptz count:** `count=0`
- **episodic_memory  -  payload_json invalid JSONB count:** `count=0`
- **episodic_memory  -  possible test-like pattern rows; unverified:** `count=6`
- **episodic_memory  -  rows without working-event session:** `count=0`
- **working_events  -  sessions without episode; may be unfinalized:** `count=32`
- **profile_facts  -  provenance sessions absent from working_events:** `count=0`
- **profile_fact_history  -  provenance sessions absent from working_events:** `count=0`
- **auth.identities  -  normalized duplicates; Supabase Auth, not CRM:** `duplicate_groups=0`, `excess_rows=0`
- **Event to normalized session check:** no business session table found; FK orphan check is not applicable.
- **Customer resolution:** no canonical business customer table; CRM resolution cannot be evaluated. Null/anonymous counts were measured.

### Interpretation limits

- Test-like ID patterns are review signals only, not proof of fixtures; no rows were classified, moved, or deleted.
- A customer ID absent from event history is not proof it is invalid.
- Episode/event comparison is relative only to available memory events.
- Parseability does not prove timezone/business semantics.

## 4. Code and environment

- [`postgres_store.py`](../src/memory/working/postgres_store.py#L24): selects `SUPABASE_DATABASE_URL` then `DATABASE_URL`; no `TEST_DATABASE_URL` or `APP_ENV` guard. Constructor calls `metadata.create_all()` at line 149; not invoked.
- [`builder.py`](../src/graph/builder.py#L176): saver selects `SUPABASE_POOLER_URL` or memory DB fallback and calls `setup()` at startup; not invoked. `session_id` is `thread_id`.
- [`tool_repository.py`](../src/tools/tool_repository.py#L422): CRM lookup is a fixed stub; [`memory_write`](../src/tools/tool_repository.py#L1231) queues rather than writing a candidate row.
- [`persistence_nodes.py`](../src/graph/nodes/persistence_nodes.py#L129): per-turn event append; finalize at line 287 writes episode and explicit profile facts/history.
- [`input_nodes.py`](../src/graph/nodes/input_nodes.py#L617): Call Brief reads events/profile/episodes and supplied sessions/orders; ordinary API response in [`graph_runner.py`](../src/api/routers/graph_runner.py#L232) omits it; no snapshot table exists.
- [`test_memory_lifecycle.py`](../scripts/test_memory_lifecycle.py#L38): can select `DATABASE_URL` or `SUPABASE_DATABASE_URL`; may hit application DB. Frontend sends `anonymous` in [`use-chat-stream.ts`](../frontend/hooks/use-chat-stream.ts#L99).

## 5. Test isolation and migration safety

- `.env` has `SUPABASE_DATABASE_URL`; `TEST_DATABASE_URL` and `SUPABASE_POOLER_URL` were absent.
- README recommends `.venv` and Python 3.11 compatible. No `.venv` existed; an ignored audit `.venv` was created with already-declared DB drivers, SQLAlchemy, and dotenv. No tracked dependency/application code changed.
- Recommend separate test/application Supabase projects; test requires `APP_ENV=test` + `TEST_DATABASE_URL`, fail-fast/no fallback, project guard without URL logging, synthetic fixtures only.
- Future migration requires native backup and verified restore to separate project, schema/count snapshots, versioned migration and approval. None run here.

## 6. Updated v1 mapping

| Existing live evidence | Target | Status | Handling / reason |
| --- | --- | --- | --- |
| No business customer/CRM table; Auth users are auth state | `customers` | `CREATE` | Create after confirming external CRM and stable customer key. |
| Auth identities exist but are not CRM mapping | `customer_identities` | `CREATE` | Do not reuse without approved customer mapping. |
| No address table | `customer_addresses` | `CREATE` | Check external commerce source before creating. |
| No business conversation table; auth.sessions is Auth state | `conversation_sessions + Call Brief snapshot` | `CREATE` | Create after mapping event session IDs/status. |
| public.working_events | `working_events` | `MIGRATE` | Retain; validate/convert JSON/time; add FK only after mapping. |
| No candidate table; queue is in event payload | `profile_fact_candidates` | `CREATE` | Backfill only with provenance and durable-fact decision. |
| public.profile_facts, string JSON/time | `profile_facts` | `MIGRATE` | Preserve key; validate conversion; customer FK awaits CRM. |
| public.profile_fact_history, string JSON/time | `profile_fact_history` | `MIGRATE` | Preserve order; reconcile values/provenance/change types. |
| public.episodic_memory, string JSON/time | `episodic_memory` | `MIGRATE` | Preserve episodes; validate payload/session mapping. |
| Four live public checkpoint tables | `LangGraph saver infrastructure` | `REUSE` | Leave saver-owned schema/data unchanged. |
| No order table; CRM tool stub | `Authoritative order source` | `INVESTIGATE` | Locate external source; avoid parallel ledger. |
| Public product catalog tables | `Outside v1` | `REUSE` | Leave product catalog unchanged. |

## 7. Approval gate

Live catalog and aggregate audit completed in read-only mode; this does not authorize schema changes. Confirm external CRM/order source, canonical customer ID, address/session ownership, mapping for anonymous/orphan/pattern counts, Call Brief contract, durable-fact gate, finalize idempotency, test-project fail-closed behavior, and deployed saver version before preparing migration.

**No migration was run. No application/frontend code changed. Schema v1 is not implemented.**
