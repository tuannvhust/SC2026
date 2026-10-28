# Database schemas

Hai schema được giữ cùng lúc. Chúng không phải hai tên của một thiết kế.

|             | Local design                                                                                             | App schema                                                                                                    |
| ----------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Dùng để     | Xem và nạp catalog, CRM seed, policy metadata trên Supabase local                                        | Backend đang chạy: CRM, working memory, profile, episodic memory                                              |
| SQL         | `supabase/schema-target/20261028150000_initial_customer_service_schema.sql`                              | `backend/src/memory/migrations/001_schema_v1.sql`, `002_simplified_schema.sql`, `003_record_id_sequences.sql` |
| Áp dụng     | Baseline, align, `20261028160000_match_target_schema.sql`, rồi `20261028170000_customers_name_order.sql` | `python scripts/database/run_migration.py`                                                                    |
| Dữ liệu mẫu | `supabase/seed.sql`, sinh bởi `scripts/database/import_reference_data.py --write-seed`                   | Không có seed trong bộ migration này                                                                          |
| Cách dùng   | `docs/database/local_and_remote.md`                                                                      | Trỏ `SUPABASE_DATABASE_URL` rồi chạy runner ở trên                                                            |

Không áp dụng cả hai lên cùng một database. Postgres local và project đang link khớp file trong `supabase/schema-target/`. File đó không nằm trong `supabase/migrations/` và không được push. `run_migration.py` ghi vào host trong `.env`. `npx supabase db reset` chỉ đụng Postgres local.

## Local design

Các bảng trong migration local:

`customers`, `conversation_sessions`, `turns`, `tool_calls`, `profile_facts`, `profile_fact_versions`, `episodes`, `memory_outbox`, `orders`, `order_items`, `callbacks`, `products`, `product_variants`, `inventory_snapshots`, `promotions`, `promotion_products`, `order_promotions`, `policies`, `policy_versions`.

`orders.order_id` và `conversation_sessions.session_id` là text (`OD188213`, `S000001`).

## App schema

`001_schema_v1.sql` tạo CRM và memory theo bảng tách (`customer_identities`, `customer_addresses`, `working_events`, `profile_fact_candidates`, `profile_fact_history`, `episodic_memory`). `002_simplified_schema.sql` gộp một phần cột vào `customers` và thêm `orders` / `order_items`. `003_record_id_sequences.sql` thêm sequence. Checkpoint LangGraph do thư viện tạo khi app chạy.

Backend vẫn đọc `working_events`, `episodic_memory` và checkpoint LangGraph. Những bảng đó không còn trên database Supabase sau `20261028160000_match_target_schema.sql`. Đừng chạy `run_migration.py` lên database này.

## Tài liệu cũ

Các bản mô tả trước đó nằm trong `docs/database/archive/`. Script một lần và seeder CRM cũ nằm trong `scripts/database/archive/`.
