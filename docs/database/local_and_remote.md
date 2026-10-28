# Supabase local và remote

Hai schema và cách chạy chúng: `docs/database/schema.md`.

## Local và remote

Local Supabase đã có trong repo: `supabase/config.toml`, `supabase/migrations/20261028150000_initial_customer_service_schema.sql`, và `supabase/seed.sql`. `compose.yaml` chỉ dựng backend và frontend. Postgres local do Supabase CLI chạy trong Docker.

Remote là project Supabase chung. Connection string của remote nằm trong `.env` khi cần app đang chạy, và được cất ngoài git khi máy đang trỏ local. `.env` không được commit.

| Biến                    | Dùng cho                         | Local                                                                     | Remote                                                   |
| ----------------------- | -------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------- |
| `SUPABASE_URL`          | PostgREST                        | `http://127.0.0.1:54321`                                                  | `https://<project-ref>.supabase.co`                      |
| `SUPABASE_KEY`          | Khóa PostgREST của backend       | Secret key từ `npx supabase status`, bắt đầu bằng `sb_secret_`            | Secret hoặc service_role trên dashboard                  |
| `SUPABASE_DATABASE_URL` | SQLAlchemy và `run_migration.py` | `postgresql://postgres:postgres@127.0.0.1:54322/postgres?sslmode=disable` | Connection string direct, cổng `5432`, `sslmode=require` |
| `SUPABASE_POOLER_URL`   | Checkpointer LangGraph           | Để trống                                                                  | Tùy chọn, cổng `6543`                                    |

`PostgresMemoryStore` thêm `sslmode=require` khi URL chưa có `sslmode`, nên URL local cần `?sslmode=disable`. CRM engine trong `backend/src/tools/tool_repository.py` luôn yêu cầu SSL, nên query CRM của app chưa chạy trên Postgres local.

Publishable key (`sb_publishable_...`) và Storage secret key không đi vào `SUPABASE_KEY`.

## Chạy local

Cần Docker Desktop đang chạy.

```bash
npx supabase start
npx supabase status
```

| Dịch vụ         | Cổng  |
| --------------- | ----- |
| API / PostgREST | 54321 |
| Postgres        | 54322 |
| Studio          | 54323 |
| Mailpit         | 54324 |

Studio: `http://127.0.0.1:54323`. Chọn schema `public`.

```bash
npx supabase stop
npx supabase db reset
```

`stop` giữ data. `db reset` xóa data local, chạy migration trong `supabase/migrations/`, rồi chạy `supabase/seed.sql`. Reset không chạy `backend/src/memory/migrations/`.

`npx supabase link`, `npx supabase db push --linked`, và `npx supabase db pull --linked` nói với project remote. Chuỗi migration là `20261028102131_remote_baseline.sql`, `20261028110000_align_local_design.sql`, `20261028160000_match_target_schema.sql`, rồi `20261028170000_customers_name_order.sql`. Kết quả khớp `supabase/schema-target/20261028150000_initial_customer_service_schema.sql`. File trong `schema-target/` không được đưa vào `supabase/migrations/`.

## App schema

SQL app nằm ở `backend/src/memory/migrations/`. Runner đọc `SUPABASE_DATABASE_URL`:

```bash
python scripts/database/run_migration.py
```

Dòng `Target database:` in host và cổng, không in mật khẩu. Host `127.0.0.1` là local. Host `db.<project-ref>.supabase.co` là remote. Rollback hiện chỉ gỡ sequence của file 003:

```bash
python scripts/database/run_migration.py --rollback
```

## Nạp catalog và policy vào local design

`data/` chỉ đọc. Importer ghi vào host local trong `.env`:

```bash
python scripts/database/import_reference_data.py --dry-run
python scripts/database/import_reference_data.py --write-seed
npx supabase db reset
```

`--write-seed` ghi `supabase/seed.sql`. Reset sau đó nạp file này. Sửa JSON hoặc Markdown rồi sinh lại seed. Không sửa `seed.sql` bằng tay.

| Nguồn                                  | Đích trong local design                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `data/catalog/products.json`           | `products`, `product_variants`. `size` số được lưu thành text                                                      |
| `data/catalog/products.csv`            | Không nạp. JSON là nguồn                                                                                           |
| `data/catalog/promotions.json`         | `promotions` (`start`/`end` thành `starts_on`/`ends_on`) và `promotion_products`                                   |
| `data/catalog/inventory_timeline.json` | `inventory_snapshots`. SKU biến thể vào `variant_sku`. Cột `note` không có trong bảng                              |
| `data/catalog/crm_seed.json`           | `customers`, `conversation_sessions`, `episodes`, `orders`, `order_items`. Seed không có số lượng nên quantity = 1 |
| `data/policy/*.md`                     | `policies` và `policy_versions`. Nội dung markdown vẫn dành cho RAG                                                |

## Máy mới

1. Mở Docker Desktop và đợi engine chạy.
2. `npx supabase start`, rồi `npx supabase status`.
3. Điền bốn biến local vào `.env`. Giữ connection string remote ở ngoài git.
4. `npx supabase db reset` nếu data local chưa có. Xác nhận Studio thấy `OD188213` và `S000001`.
5. `npx supabase stop` khi xong.

Remote dùng khi cần database chung của app. Secret key chỉ đặt trong `.env` của backend.
