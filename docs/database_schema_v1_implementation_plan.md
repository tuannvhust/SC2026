# Database Schema v1 — Audit and Implementation Plan

**Status:** Phase 1 audit and plan only. No migration or database change was run.  
**Project:** `D:\SC2026`  
**Design input:** [`database_schema_v1_design.md`](../database_schema_v1_design.md)

> **Phase 1.1 update (2026-10-17):** The live read-only audit has now completed. See [`database_schema_v1_live_audit.md`](database_schema_v1_live_audit.md) for the verified catalog of 9 non-system schemas and 50 tables, data aggregates, checkpoint tables, access-control finding, and updated mapping. It supersedes the initial audit limitation and prior-dump-only row counts below; the preliminary mapping later in this plan is superseded by the live audit mapping. No schema changes or migrations were run.

## Audit scope and evidence

This report separates source-code facts from database evidence. The available snapshot, [`supabase_memory_dump.md`](../supabase_memory_dump.md), was generated on 2026-10-17 at 14:05 UTC using a read-only transaction. It reports a successful connection to the application database, but deliberately inspects only `public` and four named memory tables. It contains full records and PII; this plan does not reproduce any record contents.

A fresh catalog query was attempted using the configured `.env` connection, with a read-only PostgreSQL connection option. It could not start because the current Python environment lacks a PostgreSQL driver (`ModuleNotFoundError`). No connection URL, credentials, PII, or record contents were printed. Consequently, the live database's complete schema, constraints, indexes, triggers, RLS policies, CRM tables, and current row-level integrity remain **unverified**. The four-table dump is not evidence that other tables do not exist.

No migration, DDL, DML, application DB fixture, or application test was run for this audit. This is a plan for review; schema v1 has not been implemented.

## 1. Database inventory

### 1.1 Available inventory snapshot

The dump names only these four `public` tables and reports these counts:

| Existing table | Snapshot count | Reported columns/types | Reported key / observations |
| --- | ---: | --- | --- |
| `working_events` | 67 | `event_id`, `session_id`, `turn_id`, `turn_number`, `customer_id`, `created_at`, `payload_json`; text-like columns exported as `VARCHAR`, turn as `INTEGER` | PK `event_id`; `created_at` and `payload_json` are `VARCHAR`. |
| `episodic_memory` | 6 | `session_id`, `customer_id`, `ended_at`, `payload_json`; text-like columns exported as `VARCHAR` | PK `session_id`; `ended_at` and `payload_json` are `VARCHAR`. |
| `profile_facts` | 5 | `customer_id`, `profile_key`, `profile_value_json`, `provenance_session_id`, `updated_at`; exported as `VARCHAR` | Composite PK `(customer_id, profile_key)`; values and time are strings. |
| `profile_fact_history` | 10 | `history_id`, `customer_id`, `profile_key`, `old_value_json`, `new_value_json`, `provenance_session_id`, `changed_at`; text-like columns exported as `VARCHAR` | PK `history_id`; history values and time are strings. |

The dump does **not** enumerate full schema objects, foreign keys, non-PK constraints, indexes, triggers, policies, or LangGraph checkpointer tables. It does not inspect `customers`, `customer_identities`, `customer_addresses`, order tables, or session tables. The application may therefore already have equivalent CRM/session structures outside this dump.

### 1.2 Live inventory status

The Phase 1.1 live audit is complete in [`database_schema_v1_live_audit.md`](database_schema_v1_live_audit.md). It inspected 9 non-system schemas and 50 base/partitioned tables in a read-only transaction. The connected database has no business CRM/customer/address/order/conversation-session table by catalog name; Auth tables are not treated as CRM equivalents. The exact evidence and limits are in the linked report.

### 1.3 Checkpointer inventory

The runtime constructs LangGraph `PostgresSaver` with a connection pool and invokes `setup()` in [`src/graph/builder.py`](../src/graph/builder.py#L176). Live catalog confirms `public.checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and `checkpoint_migrations` (10 migration rows, versions 0–9). The deployed `langgraph-checkpoint-postgres` package version is still unverified because it is absent from the inspected local interpreters. Preserve the four saver tables as separate LangGraph infrastructure; do not reshape them as business memory.

### 1.4 Existing migration assets and automatic schema creation

No Alembic or versioned SQL migration files were found in the repository inventory. `PostgresMemoryStore.__init__` declares the four memory tables and invokes `metadata.create_all(engine)` in [`src/memory/working/postgres_store.py`](../src/memory/working/postgres_store.py#L74). This can create missing tables during store initialization; it does not provide an explicit, versioned schema migration path. The constructor also includes a history table definition. The dump's four-table coverage does not establish whether LangGraph or unrelated application tables exist.

## 2. Code read/write map

| Flow | Current behavior and evidence | Schema v1 implication |
| --- | --- | --- |
| Customer identity lookup | `resolve_identity_node` parses contact data and calls `crm_get_customer` in [`input_nodes.py`](../src/graph/nodes/input_nodes.py#L282). The current `crm_get_customer` implementation in [`tool_repository.py`](../src/tools/tool_repository.py#L422) is a stub returning a fixed sample customer for phone lookup; it does not query `customers` or `customer_identities`. | No live identity repository is currently evidenced. Before schema design is mapped, identify the actual CRM source and its canonical customer key. Do not infer a real table from this stub. |
| Customer/session linking | When an ID is resolved, `resolve_identity_node` calls `update_session_customer_id`; that updates the `customer_id` snapshot and identity inside matching `working_events` rows ([`input_nodes.py`](../src/graph/nodes/input_nodes.py#L334), [`postgres_store.py`](../src/memory/working/postgres_store.py#L279)). | `working_events.customer_id` is currently denormalized. v1 should source session ownership from the canonical session/customer relation and decide whether to retain a synchronized snapshot. |
| Call Brief inputs | `build_call_brief_node` reads current session events, profile facts, and recent episodes; CRM-provided `customer_info.sessions` and `orders` are also used ([`input_nodes.py`](../src/graph/nodes/input_nodes.py#L617)). Current `sessions` and `orders` therefore depend on caller/CRM data, while profile and episodes use PostgreSQL memory tables. | Current code does not read normalized CRM tables or persist a session snapshot column. |
| Call Brief persistence | `persist_turn_node` serializes the current brief inside each `working_events.payload_json` ([`persistence_nodes.py`](../src/graph/nodes/persistence_nodes.py#L129)). It is not a dedicated session record/snapshot. | v1 design's `conversation_sessions.call_brief_json` and revision/timestamp need a repository and update contract. |
| Working event write | `persist_turn_node` builds transcript/tool/identity/status payload and calls `append_turn` after graph execution ([`persistence_nodes.py`](../src/graph/nodes/persistence_nodes.py#L129)); `append_turn` inserts/updates `working_events` ([`postgres_store.py`](../src/memory/working/postgres_store.py#L149)). `get_session_events` reads them by session and turn order ([`postgres_store.py`](../src/memory/working/postgres_store.py#L249)). | Existing table is actively used; treat all conversions and new keys as a data migration with idempotency and compatibility planning. |
| `memory.write` | [`tool_repository.py`](../src/tools/tool_repository.py#L1231) returns `queued_for_session_commit`; it does not write directly to profile storage or create a separate candidate row. Tool calls/results are captured in the current turn's event payload. | `profile_fact_candidates` is a new durable staging workflow in v1, not a reuse of an existing table. Current queue exists only as event content until finalize. |
| Profile and history writes | On finalize, `_successful_profile_updates` extracts successful `memory.write` tool calls from events ([`persistence_nodes.py`](../src/graph/nodes/persistence_nodes.py#L171)). `persist_call_node` writes the episode, then calls `ProfileStore.add_profile_facts` ([`persistence_nodes.py`](../src/graph/nodes/persistence_nodes.py#L287)). That upserts current facts and appends history when the value differs ([`profile_store.py`](../src/memory/profile/profile_store.py#L48), [`postgres_store.py`](../src/memory/working/postgres_store.py#L365)). | Fact history is tied to finalize and does not currently have v1 event provenance, JSONB values, or a transactional write-gate candidate workflow. Note profile vectors are also upserted in Qdrant; PostgreSQL is the structured source. |
| Episode finalize | `/api/chat/end-session` calls `finalize_session`; it reads events, restores a customer ID, calls `persist_call_node`, and returns the stored episode/profile result ([`chat.py`](../src/api/routers/chat.py#L32), [`graph_runner.py`](../src/api/routers/graph_runner.py#L136)). The graph persists an episode only when `session_ended` is true and events exist ([`persistence_nodes.py`](../src/graph/nodes/persistence_nodes.py#L287)). | Current lifecycle has no durable `conversation_sessions` status/finalized timestamp; episode and session lifecycle can disagree. |
| API / frontend Call Brief | `/api/chat` calls `response_from_graph`; the ordinary response includes reply, session/turn IDs, and handoff fields, not `call_brief` ([`chat.py`](../src/api/routers/chat.py#L57), [`graph_runner.py`](../src/api/routers/graph_runner.py#L232)). Stream mode emits that same response as one SSE data event. Frontend consumes text/products and separately posts end-session ([`use-chat-stream.ts`](../frontend/hooks/use-chat-stream.ts#L94), [`use-chat-stream.ts`](../frontend/hooks/use-chat-stream.ts#L220)). No Call Brief UI/API contract was found in `frontend`. Finalize response contains episode/profile facts, but frontend does not currently render a Call Brief snapshot. | Decide whether brief is returned in chat response, a dedicated endpoint, or a typed stream event, and build an explicit frontend contract. |
| LangGraph checkpoint | `initialize_graph_checkpointer` uses `SUPABASE_POOLER_URL` if set, otherwise `SUPABASE_DATABASE_URL`/`DATABASE_URL`, calls saver `setup()`, and installs it ([`builder.py`](../src/graph/builder.py#L176), [`postgres_store.py`](../src/memory/working/postgres_store.py#L36)). `invoke_customer_turn` supplies `thread_id=active_session_id` ([`graph_runner.py`](../src/api/routers/graph_runner.py#L50)). | Checkpointer shares the selected PostgreSQL database but is logically separate. Inspect deployed tables and keep the session ID convention stable. |

## 3. Current schema to v1 mapping

Status definitions: `REUSE` means compatible and retained; `ALTER` means compatible object needs additive/change migration; `CREATE` means a new table is needed after checking equivalents; `MIGRATE` means existing data/shape needs an explicit transformation; `INVESTIGATE` means evidence is incomplete. The preliminary table below is superseded by the completed live mapping in [`database_schema_v1_live_audit.md`](database_schema_v1_live_audit.md#6-updated-v1-mapping).

| Current table/object | v1 target | Action | Handling existing data | Risk |
| --- | --- | --- | --- | --- |
| CRM customer object(s), not covered by dump | `customers` | `INVESTIGATE` (then `REUSE`, `ALTER`, or `CREATE`) | Map canonical ID/name/status; retain source IDs and reconcile duplicates before adding constraints. | Duplicate or incompatible customer IDs could mislink all memory. |
| CRM identity object(s), not covered by dump | `customer_identities` | `INVESTIGATE` (then `REUSE`, `ALTER`, or `CREATE`) | Normalize identity type/value and verification; detect active duplicates before unique partial index. | Wrong normalization can merge distinct people or fail uniqueness. |
| Address tables, not covered by dump | `customer_addresses` | `INVESTIGATE` (then `REUSE`, `ALTER`, or `CREATE`) | Reuse CRM address source; migrate only with provenance and verified ownership. | Address PII and default-address uniqueness; avoid copying order snapshots as current addresses. |
| Order table(s), not covered by dump | No new v1 orders table; reference existing orders in brief/episode summary | `INVESTIGATE` | Identify authoritative order source and stable order keys; v1 episode may retain a snapshot/reference only. | Creating a parallel order ledger would diverge from CRM/commerce. |
| Session table(s), not covered by dump | `conversation_sessions` (including Call Brief snapshot) | `INVESTIGATE` (then `REUSE`/`ALTER`/`CREATE`) | Map session IDs, channel, customer, timestamps/status; derive only fields supported by events. | Existing API assumes a session ID, but no session table is proven by the dump. |
| `working_events` | `working_events` | `MIGRATE` | Preserve event IDs/payloads; parse `created_at` to `TIMESTAMPTZ`, validate `payload_json` to `JSONB`; add event type/index and uniqueness only after defining deterministic mappings and duplicate checks. Resolve `anonymous` and customer ownership only from verified sources. | Malformed JSON/timestamps, event duplication, orphan sessions, and new uniqueness collisions. |
| Current in-event queued `memory.write` calls/results | `profile_fact_candidates` | `CREATE` after checking equivalents | Backfill candidates only where successful tool call/result, key/value, provenance, and durable-fact decision can be established. Otherwise preserve event history and do not invent acceptance status. | The current queue has no durable `is_durable_fact` or review decision. |
| `profile_facts` | `profile_facts` | `MIGRATE` | Preserve `(customer_id, profile_key)`; parse `profile_value_json` into JSONB; map provenance to session/event only when resolvable; convert timestamp. | Existing values may not meet new FK/JSON/provenance constraints. |
| `profile_fact_history` | `profile_fact_history` | `MIGRATE` | Preserve order/IDs; parse old/new value strings, allowing SQL NULL for old value; convert time and provenance; reconcile new history semantics before adding FK. | Current dump history lacks `source_event_id`, has mandatory new value and string timestamp; old history may not fit new change types. |
| `episodic_memory` | `episodic_memory` | `MIGRATE` | Preserve one row per session; parse `payload_json`, extract v1 fields only when their types/shapes validate; convert `ended_at`; map customer through session/canonical customer relation rather than trusting denormalized value. | Session or customer orphans, vague summaries, and payload keys/types differ from normalized v1 columns. |
| LangGraph saver tables | LangGraph checkpointer infrastructure | `INVESTIGATE`, then `REUSE` | Preserve saver-owned data and version metadata; do not reshape as business tables. Back up with PostgreSQL-native backup. | Exact saver package/schema version and existing checkpoint history are unknown from the dump. |
| Call Brief currently inside event payload | `conversation_sessions.call_brief_json` | `ALTER` session table if found, otherwise included in `CREATE` | Consider latest valid brief per session as an initial snapshot only after validating that it is complete and belongs to that session. Keep old event payloads immutable. | Event brief may be stale, incomplete, or include transient current-turn values. |

**Current-data concerns evidenced by the snapshot/design:** timestamps and JSON are stored as `VARCHAR`; the design's reviewed snapshot reports 67 working events, 6 episodes, 5 current profile facts, and 10 history rows. The design flags test-like IDs and a session with working events but no episode. Treat those as candidates for manual provenance review, not as proof that records are test-only or safe to delete. The dump includes no complete orphan report, no exhaustive JSON/timestamp validation, and no CRM/customer table counts. No production row was classified or reclassified during this audit.

## 4. Decisions to confirm before implementation

1. Which CRM/customer and order system is authoritative, and what is the canonical stable `customer_id`? The current `crm.get_customer` tool is a stub.
2. Are there existing customer, identity, address, order, or session tables to reuse? Resolve this only from the complete live catalog plus owner confirmation.
3. Should unresolved customers store SQL `NULL` in event/session ownership? The v1 design says yes; the frontend currently sends the literal `anonymous` for chat and end-session.
4. What constitutes an approved durable fact? `memory.write` currently carries only key/value/provenance and queues it until finalize; the proposed `is_durable_fact` gate needs an explicit source and decision rule.
5. What is the v1 session finalization invariant and retry contract across session status, episode, profile history/current fact, and checkpointer? Define transaction boundaries and partial-failure recovery.
6. What is the Call Brief API and UI contract (response field, dedicated endpoint, or versioned event), and which brief fields may be persisted/returned?
7. Which database role performs migrations versus runtime reads/writes? Confirm RLS/policies and service-role handling after inspecting the live catalog. Keep credentials out of logs and reports.
8. Which existing rows are verified application, synthetic test, or unknown? Classify by provenance/evidence, not ID prefixes alone.

## 5. Test environment isolation

### Current code assessment

There is no `TEST_DATABASE_URL` reference in application code or tests. `default_database_url()` in [`postgres_store.py`](../src/memory/working/postgres_store.py#L24) selects `SUPABASE_DATABASE_URL` and falls back to `DATABASE_URL`; it cannot select a test URL explicitly. `checkpointer_database_url()` selects `SUPABASE_POOLER_URL` or the same application fallback. This is unsafe as a test-target selector.

Unit tests generally inject temporary SQLite stores. However, [`scripts/test_memory_lifecycle.py`](../scripts/test_memory_lifecycle.py#L38) selects `DATABASE_URL` or `SUPABASE_DATABASE_URL` and can therefore target the application database. The dump script is read-only but exports full records and must not be treated as a general-purpose test fixture. No live test script was run in this audit.

### Recommended isolation

- Use two distinct Supabase projects: one dedicated to development/test and one for application/production. Use separate credentials/roles and CI secrets; do not clone production PII into test.
- Require an explicit `APP_ENV=test` plus `TEST_DATABASE_URL` for every DB integration test or lifecycle script. Fail fast if missing; never fall back to `SUPABASE_DATABASE_URL`, `DATABASE_URL`, or the application pooler.
- Add a target guard that rejects a production project/ref for test mode without printing the URL. Keep the guard metadata-only and test it with fake URLs.
- Give the test project synthetic data and a disposable reset/seed mechanism isolated from application credentials. Keep ordinary unit tests on temporary SQLite or mocks.
- Apply schema migrations first to the test project, validate, then use a separately reviewed migration invocation against the application project.

## 6. Migration plan and order

All steps below are future work and require approval after this audit. They must use versioned migration files and an explicit target database. No DDL/DML is authorized by this report.

### Phase 0 — Evidence and preflight

1. Restore PostgreSQL driver availability in a controlled development environment; run catalog-only audit using a read-only DB role/transaction. Capture exact schema inventory and non-sensitive aggregate data diagnostics.
2. Confirm target project identity out-of-band without logging connection strings. Confirm backup access, role grants, RLS, maintenance window, and target-specific migration guard.
3. Generate a PostgreSQL-native consistent backup and verify that it can be restored to a separate scratch/test project. Record backup ID/time, version, owner, and restore-check result; do not store secrets in the plan/logs.
4. Take before-migration row counts and keyed counts for every in-scope table. Save schema-only DDL and constraint/index/policy manifests securely.

### Phase 1 — Test project and additive structure

5. Provision/use the dedicated test Supabase project and configure `TEST_DATABASE_URL`; prove tests fail closed when it is missing and prove its project target differs from application. Keep app and test credentials separate.
6. Decide reuse/alter/create for CRM and session objects from live inventory. Create only truly absent v1 tables (`customers`, identities, addresses, sessions, candidates, etc.) and add compatible nullable columns/indexes first. Preserve LangGraph saver schema.
7. Add new v1 structures in a versioned migration; do not drop or rename old columns/tables in the expansion stage. Use concurrent index creation where appropriate and supported by the migration runner.

### Phase 2 — Data profiling and backfill

8. Compute counts of null/`anonymous`/unmatched customer IDs, missing sessions, orphan event/session/customer references, duplicate identity keys, duplicate active default addresses, duplicate event idempotency keys, and episodes whose source session is missing. Report counts only and require owner decisions for ambiguous rows.
9. Validate all candidate timestamps with a non-throwing parser before conversion. Report invalid counts and representative values only in restricted local review if needed; never put PII in the plan. Convert to `TIMESTAMPTZ` only after format/time-zone semantics are approved.
10. Validate JSON strings with PostgreSQL `jsonb` casts in a read-only preflight or a test copy. Report invalid counts and shape/type distributions; do not silently replace bad values with `{}`. Preserve an immutable copy of source values until reconciliation passes.
11. Backfill/reconcile customer/session relationships using verified CRM keys. Convert unresolved `anonymous` ownership to `NULL` only where semantics are confirmed. Do not create placeholder customers to satisfy FKs.
12. Backfill normalized session lifecycle and Call Brief snapshots only from validated records; mark unknown historical state explicitly rather than fabricating ended/finalized status. Backfill candidates only if an explicit durable-fact decision can be supported.

### Phase 3 — Constraints and application cutover

13. Compare source/target row counts and stable key sets. Verify JSON round-trip, timestamps, identity matching, and all FK orphan counts are zero or have an approved documented exception.
14. Add/validate FKs and checks after cleanup decisions; add unique constraints/indexes only after duplicate reports pass. Keep default deletes restrictive as designed. Confirm RLS policies and application grants with read/write role tests in the test project.
15. Update repositories/API/frontend only in a later implementation phase, after migration contract approval. Use dual-read or compatibility adapters during cutover if needed; do not dual-write without reconciliation/idempotency semantics.
16. Run acceptance tests and end-to-end data reconciliation in the test project. Obtain explicit approval before applying the reviewed migration to the application project.

## 7. Rollback plan

- Before any production DDL, verify a restorable point-in-time/native backup and have a tested restore runbook. A backup is not sufficient until restore is proven.
- Use expand-contract migrations: additive objects first, backfill in resumable batches, then switch reads/writes. Keep old columns/representations until post-cutover validation and a retention window have passed.
- Record migration version and each batch's checkpoint/count. Make backfills idempotent and preserve source IDs/values so they can be replayed or reconciled.
- On application failure before contract: disable v1 reads/writes via feature/config switch, revert application code to old repositories, and leave additive schema/data untouched. Do not automatically delete new rows.
- If converted data is wrong, stop writes, restore the pre-migration backup to a separate project for diagnosis, and prefer a corrective forward migration. Restore production only under the separately approved disaster recovery procedure because restore may discard writes made after backup.
- Never drop old columns/tables as part of the initial cutover. Schedule destructive cleanup only in a later approved migration after validated backup, stable operation, and explicit review.

## 8. Acceptance test plan

These are proposed tests for the implementation phase; none were run in this audit.

1. **Environment guard:** missing `TEST_DATABASE_URL`, an application URL in test mode, or missing `APP_ENV=test` fails before connecting; no fallback to application URL. Test with fake URLs and ensure diagnostics redact credentials.
2. **Schema inventory:** all v1 tables/columns/types/PK/FK/unique/check/index definitions match approved migration; RLS and privileges match the chosen runtime/migration roles; LangGraph saver still initializes on the expected database and session `thread_id`.
3. **Identity:** verified phone/channel identity maps to one stable customer; ambiguous or unresolved identity does not leak another customer's records and stores no fake `anonymous` customer row.
4. **Call Brief:** returning customer brief loads only that customer's CRM/profile/episodes and active session events; snapshot persists with monotonic revision and is returned through the approved API/SSE contract for frontend rendering.
5. **Working events:** appends are ordered, idempotent for retries, have valid JSON/timestamps, and enforce approved session/customer references; historical events remain readable.
6. **Profile write gate:** `memory.write` creates a provenance-bearing candidate; non-durable, rejected, or unverified candidates do not update current profile; approved commit atomically appends history and upserts current fact.
7. **Profile history:** create/update/invalidate behavior preserves old/new values, source session/event, change type, order, and JSON types; repeated finalize does not duplicate history.
8. **Finalize:** active/ending/ended transitions are correct; episode creation is idempotent; empty or failed finalize is not reported as successful ended; events without episodes remain recoverable.
9. **Migration reconciliation:** pre/post counts and stable keys match; all approved JSON/timestamp conversions round-trip; orphan and uniqueness reports are zero or match signed-off exceptions; no test fixtures are silently dropped.
10. **Rollback rehearsal:** test project can switch back to old read path before contract, preserve additive data, and restore from verified backup without relying on unreviewed destructive SQL.

## Phase 1 exit criteria

Phase 1 and Phase 1.1 read-only audits are complete. The live catalog and aggregate integrity checks are documented in [`database_schema_v1_live_audit.md`](database_schema_v1_live_audit.md). Migration is still **not authorized or implemented**: resolve the remaining external CRM/order, identity mapping, session lifecycle, access-control, and test-isolation decisions, then obtain approval before preparing a versioned migration.
