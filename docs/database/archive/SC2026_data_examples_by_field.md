> Archived on 2026-10-28. This file is not a current schema. See `docs/database/schema.md`.

# SC2026 — Data mẫu cho từng trường trong schema

> **Mục đích:** tài liệu tham khảo để developer đối chiếu kiểu dữ liệu và giá trị mẫu khi sửa code lưu CRM, conversation session, memory, order và catalog.
>
> **Nguồn chính:** `docs/database/archive/SC2026_database_schema_simplified.md`, các migration trong `backend/src/memory/migrations/`, seed/catalog tại `data/catalog/` và JSON Schema trong `data/schemas/` trên branch `develop`.
>
> **Lưu ý:** schema simplified trong tài liệu là **schema mục tiêu**, không phải xác nhận rằng Supabase live đã áp dụng đầy đủ. Các timestamp ngoài dữ liệu seed, UUID, session mới và nội dung hội thoại mới dưới đây là **giá trị minh họa**. Không insert thủ công các dòng checkpoint LangGraph.

## 1. Quy ước đọc tài liệu

- `C031`, `OD188213`, `SKU-AP-X-2024`, `SKU-AP-X`, `SKU-SN-RUN1-38-DEN`, `AIR-OCT` là các giá trị có cơ sở từ seed/catalog hiện tại.
- Seed hiện có session `S-OLD-1`, `S-OLD-2`, `S-OLD-3`. Trong ví dụ mục tiêu, `S000001` là **ID đề xuất sau khi chuẩn hóa** `S-OLD-1`, không phải ID gốc hiện tại trong file seed. Chỉ đổi ID trong dữ liệu thật khi đã có mapping và cập nhật đầy đủ các khóa tham chiếu.
- Quy ước ID đề xuất cho bản ghi mới: customer `C051`, `C052`, …; order `OD` + ít nhất 6 chữ số; session `S000004`, `S000005`, … sau khi đồng bộ sequence và chuẩn hóa seed. Đây là quy ước mục tiêu, không có nghĩa runtime hiện tại đã sinh ID theo quy ước này.
- `null` có nghĩa là nguồn dữ liệu chưa cung cấp hoặc giá trị chưa được xác minh. Không điền dữ liệu suy đoán vào hồ sơ thật chỉ để tránh `null`.
- Tiền lưu bằng số nguyên VND, ví dụ `4290000`; số điện thoại phải là chuỗi để giữ số `0` ở đầu.

## 2. `public.customers` — hồ sơ khách hàng

Nguồn mẫu định danh: khách `C031` trong `data/catalog/crm_seed.json`. Seed chỉ có `name`, không có tên đầy đủ hay địa chỉ đã xác minh, nên ví dụ map `name` sang cả `full_name` và `preferred_name` theo importer mục tiêu; địa chỉ để `null`.

```json
{
	"customer_id": "C031",
	"full_name": "Oanh",
	"preferred_name": "Oanh",
	"honorific": "chị",
	"phone": "0985003703",
	"phone_verified": false,
	"zalo_id": "zalo_oanh96",
	"fb_id": "fb.oanh.620",
	"email": null,
	"region": "bac",
	"address_line": null,
	"ward": null,
	"district": null,
	"city": null,
	"country_code": "VN",
	"address_verified": false,
	"status": "provisional",
	"source": "crm_seed",
	"created_at": "2026-10-26T08:00:00+07:00",
	"updated_at": "2026-10-26T08:00:00+07:00",
	"deleted_at": null
}
```

| Trường             | Ví dụ                       | Ghi chú                                                                                                  |
| ------------------ | --------------------------- | -------------------------------------------------------------------------------------------------------- |
| `customer_id`      | `C031`                      | PK, giữ nguyên ID seed. ID mới theo đề xuất `C051` trở đi.                                               |
| `full_name`        | `Oanh`                      | Tên hiện có trong seed; không tự suy ra họ tên dài hơn.                                                  |
| `preferred_name`   | `Oanh`                      | Tên gọi hiển thị; ví dụ này dùng cùng giá trị seed `name`.                                               |
| `honorific`        | `chị`                       | Giữ cách xưng hô từ seed.                                                                                |
| `phone`            | `0985003703`                | TEXT, giữ số `0` đầu; không đặt UNIQUE vì seed có hai khách dùng chung phone.                            |
| `phone_verified`   | `false`                     | Chỉ đặt `true` khi có quy trình xác minh rõ ràng.                                                        |
| `zalo_id`          | `zalo_oanh96`               | Định danh kênh, nullable; kiểm tra trùng trước khi lưu.                                                  |
| `fb_id`            | `fb.oanh.620`               | Định danh Facebook, nullable.                                                                            |
| `email`            | `null`                      | Seed không cung cấp email cho dòng mẫu này.                                                              |
| `region`           | `bac`                       | Các giá trị mục tiêu: `bac`, `trung`, `nam`, hoặc `null`.                                                |
| `address_line`     | `null`                      | Không tự coi địa chỉ trong tóm tắt hội thoại là địa chỉ mặc định đã xác minh.                            |
| `ward`             | `null`                      | Chưa có dữ liệu cấu trúc.                                                                                |
| `district`         | `null`                      | Chưa có dữ liệu cấu trúc.                                                                                |
| `city`             | `null`                      | Chưa có dữ liệu cấu trúc.                                                                                |
| `country_code`     | `VN`                        | Mặc định theo schema mục tiêu.                                                                           |
| `address_verified` | `false`                     | Chưa xác minh địa chỉ.                                                                                   |
| `status`           | `provisional`               | Ví dụ theo seed importer mục tiêu; trạng thái cho phép gồm `active`, `provisional`, `merged`, `deleted`. |
| `source`           | `crm_seed`                  | Nguồn tạo/import bản ghi.                                                                                |
| `created_at`       | `2026-10-26T08:00:00+07:00` | Ví dụ timestamp ISO 8601; DB có thể tự sinh `now()`.                                                     |
| `updated_at`       | `2026-10-26T08:00:00+07:00` | Cập nhật khi bản ghi thay đổi.                                                                           |
| `deleted_at`       | `null`                      | Dùng soft delete; bản ghi đang hoạt động để `null`.                                                      |

## 3. `public.orders` — đơn hàng

Nguồn mẫu: đơn `OD188213` của `C031` trong seed.

```json
{
	"order_id": "OD188213",
	"customer_id": "C031",
	"order_date": "2026-02-17",
	"status": "delivered",
	"tracking_number": null,
	"total_amount_vnd": 4290000,
	"currency": "VND",
	"source_system": "crm_seed",
	"created_at": "2026-02-17T09:00:00+07:00",
	"updated_at": "2026-02-17T09:00:00+07:00"
}
```

| Trường             | Ví dụ                       | Ghi chú                                                                              |
| ------------------ | --------------------------- | ------------------------------------------------------------------------------------ |
| `order_id`         | `OD188213`                  | ID có trong seed; format đề xuất cho đơn mới là `OD` + ít nhất 6 chữ số.             |
| `customer_id`      | `C031`                      | FK đến `customers.customer_id`.                                                      |
| `order_date`       | `2026-02-17`                | DATE theo `YYYY-MM-DD`; lấy từ trường `date` của seed.                               |
| `status`           | `delivered`                 | Giữ trạng thái từ nguồn; kiểm soát tập trạng thái ở application/schema.              |
| `tracking_number`  | `null`                      | Đơn `OD188213` không có `tracking` trong seed. Ví dụ đơn `OD301177` có `GHN7781234`. |
| `total_amount_vnd` | `4290000`                   | Lấy từ `price_vnd` trong seed; không tính lại từ memory.                             |
| `currency`         | `VND`                       | Giá trị mặc định theo schema mục tiêu.                                               |
| `source_system`    | `crm_seed`                  | Nguồn import; đơn tạo bởi tool có thể dùng nhãn hệ thống tương ứng.                  |
| `created_at`       | `2026-02-17T09:00:00+07:00` | Timestamp minh họa; seed chỉ có ngày, không có giờ tạo thật.                         |
| `updated_at`       | `2026-02-17T09:00:00+07:00` | Timestamp minh họa, không phải dữ liệu giờ có sẵn trong seed.                        |

## 4. `public.order_items` — chi tiết đơn hàng

Seed hiện có một SKU mỗi đơn và không cung cấp số lượng; importer mục tiêu dùng `quantity = 1`. Seed cũng không cung cấp tên snapshot riêng, nên `product_name_snapshot` có thể là `null` thay vì tự bịa tên lịch sử.

```json
{
	"order_item_id": "b7e17c5c-5ad2-41c5-8a40-e37a6e0c5b21",
	"order_id": "OD188213",
	"line_number": 1,
	"sku": "SKU-AP-X-2024",
	"product_name_snapshot": null,
	"quantity": 1,
	"unit_price_vnd": 4290000,
	"line_total_vnd": 4290000,
	"created_at": "2026-02-17T09:00:00+07:00"
}
```

| Trường                  | Ví dụ                                  | Ghi chú                                                                                 |
| ----------------------- | -------------------------------------- | --------------------------------------------------------------------------------------- |
| `order_item_id`         | `b7e17c5c-5ad2-41c5-8a40-e37a6e0c5b21` | UUID minh họa; nên để DB tự sinh `gen_random_uuid()`.                                   |
| `order_id`              | `OD188213`                             | FK đến `orders.order_id`.                                                               |
| `line_number`           | `1`                                    | Dòng đầu trong đơn; kết hợp với `order_id` phải unique.                                 |
| `sku`                   | `SKU-AP-X-2024`                        | SKU tại thời điểm mua; giữ snapshot lịch sử ngay cả khi SKU không còn trong catalog.    |
| `product_name_snapshot` | `null`                                 | Seed không có cột tên sản phẩm ở cấp dòng đơn. Chỉ ghi tên nếu nguồn lịch sử có căn cứ. |
| `quantity`              | `1`                                    | Giả định theo importer hiện tại vì seed không cung cấp quantity.                        |
| `unit_price_vnd`        | `4290000`                              | Với giả định quantity = 1, dùng giá đơn hàng trong seed.                                |
| `line_total_vnd`        | `4290000`                              | `quantity × unit_price_vnd`; trong ví dụ này bằng giá đơn.                              |
| `created_at`            | `2026-02-17T09:00:00+07:00`            | Timestamp minh họa.                                                                     |

## 5. `public.conversation_sessions` — vòng đời session

Dòng minh họa dùng session mới `S000004` của khách `C031`. `S000001` trong `call_brief_json` đại diện cho session lịch sử `S-OLD-1` **sau khi được chuẩn hóa theo quy ước mục tiêu**. Call Brief JSON bên dưới tuân theo các trường được định nghĩa trong `data/schemas/call_brief.schema.json`.

```json
{
	"session_id": "S000004",
	"customer_id": "C031",
	"channel": "hotline",
	"status": "active",
	"started_at": "2026-10-26T08:00:00+07:00",
	"last_activity_at": "2026-10-26T08:05:00+07:00",
	"ended_at": null,
	"finalized_at": null,
	"outcome": null,
	"handoff_reason": null,
	"call_brief_json": {
		"customer_phone": "0985003703",
		"customer_name": "Oanh",
		"honorific": "chị",
		"is_returning": true,
		"n_previous_sessions": 1,
		"last_session": {
			"session_id": "S000001",
			"date": "2026-02-17",
			"channel": "hotline",
			"summary": "Mua AirPure X bản 2024 giá 4.290.000đ, phòng 20m².",
			"outcome": "chot_don"
		},
		"profile_facts": {
			"room_area_m2": 20
		},
		"products_advised": [
			{
				"sku": "SKU-AP-X-2024",
				"price_quoted_vnd": 4290000,
				"promo_code": null,
				"promo_still_active": null,
				"quoted_on": "2026-02-17"
			}
		],
		"orders": [
			{
				"order_id": "OD188213",
				"status": "delivered"
			}
		],
		"open_blockers": [],
		"open_questions": ["Chị muốn kiểm tra giá hiện tại hay sản phẩm thay thế?"],
		"must_not_ask": ["room_area_m2"],
		"stale_warnings": [
			"SKU lịch sử SKU-AP-X-2024 cần được xác minh trong catalog trước khi báo giá lại."
		],
		"suggested_opening": "Dạ chào chị Oanh ạ. Lần trước chị đã tìm hiểu AirPure X, em tiếp tục hỗ trợ chị nhé ạ.",
		"suggested_next_action": "Xác nhận nhu cầu hiện tại và kiểm tra SKU, giá, tồn kho đang có hiệu lực.",
		"generated_at": "2026-10-26T08:00:00+07:00",
		"latency_ms": 140,
		"precomputed_parts": ["customer_profile", "last_session", "orders"]
	},
	"call_brief_revision": 1,
	"call_brief_updated_at": "2026-10-26T08:00:00+07:00",
	"created_at": "2026-10-26T08:00:00+07:00",
	"updated_at": "2026-10-26T08:05:00+07:00"
}
```

| Trường                  | Ví dụ                       | Ghi chú                                                                                                                       |
| ----------------------- | --------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `session_id`            | `S000004`                   | ID session mới theo quy ước mục tiêu.                                                                                         |
| `customer_id`           | `C031`                      | Nullable nếu chưa xác định được khách.                                                                                        |
| `channel`               | `hotline`                   | Ví dụ khác trong schema hợp đồng: `chat_fanpage`, `zalo_oa`, `web_chat`, `other`.                                             |
| `status`                | `active`                    | Các trạng thái mục tiêu: `active`, `ending`, `ended`, `abandoned`, `failed`.                                                  |
| `started_at`            | `2026-10-26T08:00:00+07:00` | Thời điểm bắt đầu.                                                                                                            |
| `last_activity_at`      | `2026-10-26T08:05:00+07:00` | Cập nhật mỗi lần có hoạt động.                                                                                                |
| `ended_at`              | `null`                      | Chỉ ghi thời điểm kết thúc khi session thật sự kết thúc.                                                                      |
| `finalized_at`          | `null`                      | Chỉ ghi sau khi bước persist/finalize hoàn thành.                                                                             |
| `outcome`               | `null`                      | Chưa có kết quả khi session đang active. Enum Call Brief lịch sử: `hen_goi_lai`, `chot_don`, `tu_choi`, `chuyen_may`, `khac`. |
| `handoff_reason`        | `null`                      | Chỉ lưu lý do chuyển người thật khi có handoff.                                                                               |
| `call_brief_json`       | object JSON ở trên          | Snapshot JSONB theo schema CallBrief; không thêm `customer_id` vào object nếu bám đúng schema hiện tại.                       |
| `call_brief_revision`   | `1`                         | Revision snapshot; tăng khi cập nhật.                                                                                         |
| `call_brief_updated_at` | `2026-10-26T08:00:00+07:00` | Thời điểm snapshot được lưu.                                                                                                  |
| `created_at`            | `2026-10-26T08:00:00+07:00` | DB có thể tự sinh `now()`.                                                                                                    |
| `updated_at`            | `2026-10-26T08:05:00+07:00` | Thời điểm cập nhật session gần nhất.                                                                                          |

## 6. `public.working_events` — dữ liệu theo turn

`payload_json` là JSONB dùng chứa transcript của turn, identity snapshot, tool calls/results và trạng thái. Ví dụ event ID được dùng lại trong phần profile provenance bên dưới.

```json
{
	"event_id": "b2d5d3ef-0c3d-4c29-8f0e-68fb2c630b2d",
	"session_id": "S000004",
	"turn_id": "9fa19642-35c8-4cd3-9b6b-3c2906e0c12b",
	"turn_number": 1,
	"customer_id": "C031",
	"event_type": "turn_saved",
	"event_index": 0,
	"payload_json": {
		"messages": [
			{
				"type": "human",
				"content": "Phòng khách nhà em khoảng 20m², em muốn hỏi giá máy lọc không khí."
			},
			{
				"type": "ai",
				"content": "Dạ, em sẽ kiểm tra sản phẩm và giá hiện tại cho mình ạ."
			}
		],
		"identity": {
			"customer_id": "C031",
			"phone": "0985003703",
			"name": "Oanh",
			"honorific": "chị"
		},
		"tool_calls": [],
		"tool_results": [],
		"call_brief": {},
		"status": {
			"input_valid": true,
			"output_valid": true,
			"is_handoff": false,
			"session_ended": false,
			"session_outcome": null
		}
	},
	"created_at": "2026-10-26T08:05:00+07:00"
}
```

| Trường         | Ví dụ                                  | Ghi chú                                                                          |
| -------------- | -------------------------------------- | -------------------------------------------------------------------------------- |
| `event_id`     | `b2d5d3ef-0c3d-4c29-8f0e-68fb2c630b2d` | UUID; có thể để DB tự sinh nếu cơ chế insert hỗ trợ.                             |
| `session_id`   | `S000004`                              | FK đến session chứa turn.                                                        |
| `turn_id`      | `9fa19642-35c8-4cd3-9b6b-3c2906e0c12b` | TEXT dùng định danh/idempotency cho turn; không nhất thiết cùng format session.  |
| `turn_number`  | `1`                                    | Số thứ tự turn trong session, bắt đầu từ 1.                                      |
| `customer_id`  | `C031`                                 | Có thể `null` trước khi nhận diện.                                               |
| `event_type`   | `turn_saved`                           | Giá trị mặc định theo schema mục tiêu.                                           |
| `event_index`  | `0`                                    | Chỉ số event trong turn; ví dụ event đầu tiên.                                   |
| `payload_json` | object JSON ở trên                     | JSONB; bảo đảm serializable và không lưu dữ liệu thừa/sensitive không cần thiết. |
| `created_at`   | `2026-10-26T08:05:00+07:00`            | Thời điểm ghi event.                                                             |

## 7. `public.profile_facts` — fact bền vững hiện hành

Mỗi cặp `(customer_id, profile_key)` chỉ giữ một giá trị hiện hành. Ví dụ minh họa fact diện tích phòng được xác nhận ở session mới.

```json
{
	"customer_id": "C031",
	"profile_key": "room_area_m2",
	"profile_value": 20,
	"source_session_id": "S000004",
	"source_event_id": "b2d5d3ef-0c3d-4c29-8f0e-68fb2c630b2d",
	"source_kind": "customer_stated",
	"confidence": 0.99,
	"updated_at": "2026-10-26T08:05:00+07:00"
}
```

| Trường              | Ví dụ                                  | Ghi chú                                                                            |
| ------------------- | -------------------------------------- | ---------------------------------------------------------------------------------- |
| `customer_id`       | `C031`                                 | FK đến customer sở hữu fact.                                                       |
| `profile_key`       | `room_area_m2`                         | Tên slot ổn định; ví dụ khác `budget_vnd`, `has_young_children`, `preferred_size`. |
| `profile_value`     | `20`                                   | JSONB; có thể là number, string, boolean, array hoặc object tùy loại fact.         |
| `source_session_id` | `S000004`                              | Session nguồn gần nhất.                                                            |
| `source_event_id`   | `b2d5d3ef-0c3d-4c29-8f0e-68fb2c630b2d` | UUID event nguồn; có thể null nếu chưa có event phù hợp.                           |
| `source_kind`       | `customer_stated`                      | Loại nguồn; ví dụ giá trị này minh họa fact do khách trực tiếp nói.                |
| `confidence`        | `0.99`                                 | NUMERIC từ 0 đến 1; chỉ đặt khi hệ thống có căn cứ đánh giá độ tin cậy.            |
| `updated_at`        | `2026-10-26T08:05:00+07:00`            | Lần cập nhật gần nhất.                                                             |

## 8. `public.episodic_memory` — tóm tắt session đã kết thúc

Ví dụ dùng session lịch sử `S000001`, đại diện cho seed ID `S-OLD-1` sau khi đã được chuẩn hóa. Thời gian chính xác dưới đây chỉ minh họa vì seed lịch sử cung cấp ngày nhưng không cung cấp giờ bắt đầu/kết thúc.

```json
{
	"episode_id": "76db6358-b8d6-4f8c-9911-a7ae5aafe0c0",
	"session_id": "S000001",
	"customer_id": "C031",
	"summary": "Mua AirPure X bản 2024 giá 4.290.000đ, phòng 20m², địa chỉ giao: 12 ngõ 38 Hoàng Cầu, Đống Đa, Hà Nội",
	"current_need": "Mua máy lọc không khí cho phòng 20m²",
	"outcome": "chot_don",
	"handoff_reason": null,
	"products_advised": [
		{
			"sku": "SKU-AP-X-2024",
			"price_quoted_vnd": 4290000,
			"promo_code": null,
			"quoted_on": "2026-02-17"
		}
	],
	"orders_summary": [
		{ "order_id": "OD188213", "sku": "SKU-AP-X-2024", "status": "delivered" }
	],
	"open_questions": [],
	"open_blockers": [],
	"next_actions": ["Xác minh nhu cầu và giá hiện hành nếu khách quay lại"],
	"source_event_ids": [],
	"turn_count": 4,
	"started_at": "2026-02-17T09:00:00+07:00",
	"ended_at": "2026-02-17T09:10:00+07:00",
	"payload_json": { "source": "crm_seed", "time_precision": "illustrative" },
	"created_at": "2026-10-26T08:00:00+07:00",
	"updated_at": "2026-10-26T08:00:00+07:00"
}
```

| Trường             | Ví dụ                                                  | Ghi chú                                                                                                        |
| ------------------ | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `episode_id`       | `76db6358-b8d6-4f8c-9911-a7ae5aafe0c0`                 | UUID minh họa; DB tự sinh.                                                                                     |
| `session_id`       | `S000001`                                              | Một episode cho một session.                                                                                   |
| `customer_id`      | `C031`                                                 | Nullable với session guest chưa được nhận diện.                                                                |
| `summary`          | `Mua AirPure X bản 2024 giá 4.290.000đ, phòng 20m²...` | Tóm tắt nguồn seed; tránh coi summary là nguồn dữ liệu order chính thức.                                       |
| `current_need`     | `Mua máy lọc không khí cho phòng 20m²`                 | Tóm tắt nhu cầu chính; ví dụ diễn giải từ summary.                                                             |
| `outcome`          | `chot_don`                                             | Giá trị có trong seed; CallBrief enum hiện tại gồm `hen_goi_lai`, `chot_don`, `tu_choi`, `chuyen_may`, `khac`. |
| `handoff_reason`   | `null`                                                 | Không có handoff trong ví dụ này.                                                                              |
| `products_advised` | array chứa `SKU-AP-X-2024`                             | JSONB; lưu sản phẩm đã tư vấn và giá lịch sử khi có nguồn.                                                     |
| `orders_summary`   | array chứa `OD188213`                                  | Chỉ là tóm tắt episode; bảng `orders` mới là nguồn dữ liệu đơn hàng nghiệp vụ.                                 |
| `open_questions`   | `[]`                                                   | Câu hỏi chưa xử lý khi session kết thúc.                                                                       |
| `open_blockers`    | `[]`                                                   | Trở ngại còn tồn đọng.                                                                                         |
| `next_actions`     | `["Xác minh nhu cầu..."]`                              | Hành động dự kiến sau phiên.                                                                                   |
| `source_event_ids` | `[]`                                                   | Mảng UUID; seed lịch sử không cung cấp working event IDs.                                                      |
| `turn_count`       | `4`                                                    | Số lượt minh họa, không phải con số có sẵn trong seed.                                                         |
| `started_at`       | `2026-02-17T09:00:00+07:00`                            | Timestamp minh họa vì seed chỉ lưu ngày.                                                                       |
| `ended_at`         | `2026-02-17T09:10:00+07:00`                            | Timestamp minh họa; bắt buộc theo schema mục tiêu.                                                             |
| `payload_json`     | `{"source":"crm_seed",...}`                            | JSONB bổ sung, không thay thế các cột có cấu trúc.                                                             |
| `created_at`       | `2026-10-26T08:00:00+07:00`                            | Thời điểm import episode minh họa.                                                                             |
| `updated_at`       | `2026-10-26T08:00:00+07:00`                            | Thời điểm cập nhật episode gần nhất.                                                                           |

## 9. `public.products` — catalog sản phẩm

Nguồn: `data/catalog/products.json`; ví dụ `SKU-AP-X` là sản phẩm hiện hành trong catalog. `min_price`, `max_price`, `total_stock`, `in_stock`, `is_active` là các trường của schema DB mục tiêu; cách tính/đồng bộ các trường này phải nhất quán với importer hiện hành.

```json
{
	"sku": "SKU-AP-X",
	"name": "Máy lọc không khí AirPure X",
	"category": "gia-dung/may-loc-khong-khi",
	"brand": "AirPure",
	"list_price_vnd": 4890000,
	"attributes": {
		"room_area_m2": 25,
		"features": "HEPA H13, cảm biến PM2.5, chế độ ngủ",
		"warranty_months": 24,
		"child_safe_lock": false
	},
	"min_price": 4890000,
	"max_price": 4890000,
	"total_stock": 40,
	"in_stock": true,
	"is_active": true,
	"created_at": "2026-10-15T00:00:00+07:00",
	"updated_at": "2026-10-15T00:00:00+07:00"
}
```

| Trường           | Ví dụ                         | Ghi chú                                                                                           |
| ---------------- | ----------------------------- | ------------------------------------------------------------------------------------------------- |
| `sku`            | `SKU-AP-X`                    | PK và mã sản phẩm trong catalog.                                                                  |
| `name`           | `Máy lọc không khí AirPure X` | Tên sản phẩm từ catalog.                                                                          |
| `category`       | `gia-dung/may-loc-khong-khi`  | Category slug từ catalog.                                                                         |
| `brand`          | `AirPure`                     | Nhãn hiệu.                                                                                        |
| `list_price_vnd` | `4890000`                     | Giá niêm yết; số nguyên VND.                                                                      |
| `attributes`     | object JSON trong ví dụ       | JSONB; chứa diện tích phòng, tính năng, bảo hành, khóa trẻ em.                                    |
| `min_price`      | `4890000`                     | Ví dụ tính bằng list price vì SKU mẫu không có variants; xác nhận công thức tại importer/runtime. |
| `max_price`      | `4890000`                     | Cùng lưu ý với `min_price`.                                                                       |
| `total_stock`    | `40`                          | Stock tĩnh trong file catalog. Không cộng thêm inventory timeline vào giá trị này.                |
| `in_stock`       | `true`                        | Ví dụ trạng thái từ stock tĩnh; tồn kho theo ngày có thể khác.                                    |
| `is_active`      | `true`                        | Trạng thái bán trong catalog DB.                                                                  |
| `created_at`     | `2026-10-15T00:00:00+07:00`   | Timestamp minh họa; catalog JSON chỉ có `reference_date`.                                         |
| `updated_at`     | `2026-10-15T00:00:00+07:00`   | Timestamp minh họa.                                                                               |

## 10. `public.product_variants` — biến thể

Nguồn: `data/catalog/products.json`, variant đầu của `SKU-SN-RUN1`.

```json
{
	"variant_sku": "SKU-SN-RUN1-38-DEN",
	"product_sku": "SKU-SN-RUN1",
	"size": "38",
	"color": "den",
	"price_delta_vnd": 0,
	"stock": 9,
	"created_at": "2026-10-15T00:00:00+07:00",
	"updated_at": "2026-10-15T00:00:00+07:00"
}
```

| Trường            | Ví dụ                       | Ghi chú                                                                         |
| ----------------- | --------------------------- | ------------------------------------------------------------------------------- |
| `variant_sku`     | `SKU-SN-RUN1-38-DEN`        | PK của biến thể.                                                                |
| `product_sku`     | `SKU-SN-RUN1`               | FK đến `products.sku`.                                                          |
| `size`            | `38`                        | Lưu TEXT theo schema DB mục tiêu; chuyển từ số `38` trong JSON.                 |
| `color`           | `den`                       | Giá trị chuẩn hóa trong catalog.                                                |
| `price_delta_vnd` | `0`                         | Chênh lệch giá so với sản phẩm cha.                                             |
| `stock`           | `9`                         | Stock tĩnh trong variants JSON; inventory timeline có thể điều chỉnh theo ngày. |
| `created_at`      | `2026-10-15T00:00:00+07:00` | Timestamp minh họa.                                                             |
| `updated_at`      | `2026-10-15T00:00:00+07:00` | Timestamp minh họa.                                                             |

## 11. `public.promotions` — khuyến mãi

Nguồn: `data/catalog/promotions.json`, chương trình `AIR-OCT`. `applies_to` được lưu thành PostgreSQL `TEXT[]` theo schema mục tiêu.

```json
{
	"promo_code": "AIR-OCT",
	"name": "Giảm 300.000đ máy lọc không khí AirPure Pro",
	"applies_to": ["SKU-AP-PRO"],
	"type": "fixed",
	"gift_sku": null,
	"discount_vnd": 300000,
	"discount_percent": 0,
	"min_order_vnd": 0,
	"start_date": "2026-10-05",
	"end_date": "2026-10-30",
	"stackable": false,
	"conditions": null,
	"created_at": "2026-10-15T00:00:00+07:00",
	"updated_at": "2026-10-15T00:00:00+07:00"
}
```

| Trường             | Ví dụ                                         | Ghi chú                                                                                                                                 |
| ------------------ | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `promo_code`       | `AIR-OCT`                                     | PK/mã chương trình từ promotions JSON.                                                                                                  |
| `name`             | `Giảm 300.000đ máy lọc không khí AirPure Pro` | Tên chương trình.                                                                                                                       |
| `applies_to`       | `["SKU-AP-PRO"]`                              | Danh sách SKU/category targets. Ví dụ khác có `category:...`.                                                                           |
| `type`             | `fixed`                                       | Loại từ nguồn; các promotion khác có thể là `gift`, `percent`, `percent_second_item`. Không tự đổi enum khi chưa cập nhật logic/schema. |
| `gift_sku`         | `null`                                        | AIR-OCT không tặng SKU; ví dụ `GIFT-FILTER` có `SKU-AP-FLT-X`.                                                                          |
| `discount_vnd`     | `300000`                                      | Mức giảm cố định bằng VND.                                                                                                              |
| `discount_percent` | `0`                                           | Nguồn AIR-OCT không cung cấp phần trăm; ví dụ dùng `0` theo default DB.                                                                 |
| `min_order_vnd`    | `0`                                           | Không có giá trị min order trong record AIR-OCT; ví dụ dùng default DB.                                                                 |
| `start_date`       | `2026-10-05`                                  | Map từ `start` trong catalog JSON.                                                                                                      |
| `end_date`         | `2026-10-30`                                  | Map từ `end` trong catalog JSON; cần thống nhất ngày kết thúc có tính inclusive.                                                        |
| `stackable`        | `false`                                       | Giá trị từ nguồn.                                                                                                                       |
| `conditions`       | `null`                                        | AIR-OCT không có conditions; với RUN-10 có object điều kiện.                                                                            |
| `created_at`       | `2026-10-15T00:00:00+07:00`                   | Timestamp minh họa.                                                                                                                     |
| `updated_at`       | `2026-10-15T00:00:00+07:00`                   | Timestamp minh họa.                                                                                                                     |

## 12. `public.checkpoints` — LangGraph checkpoint

> **Không tạo/ghi dòng checkpoint bằng seed thủ công.** Đây chỉ là hình dạng minh họa dựa trên schema mục tiêu; nội dung thật do LangGraph checkpointer serialize và quản lý.

```json
{
	"thread_id": "S000004",
	"checkpoint_ns": "",
	"checkpoint_id": "1f9d0e45-0e8f-4cbd-a30c-dfe3b0fe5301",
	"parent_checkpoint_id": null,
	"type": "json",
	"checkpoint": {
		"v": 1,
		"id": "1f9d0e45-0e8f-4cbd-a30c-dfe3b0fe5301",
		"ts": "2026-10-26T01:00:00+00:00",
		"channel_values": { "messages": [] },
		"channel_versions": {},
		"versions_seen": {}
	},
	"metadata": { "source": "input", "step": 1, "writes": {} }
}
```

| Trường                 | Ví dụ                                     | Ghi chú                                                                          |
| ---------------------- | ----------------------------------------- | -------------------------------------------------------------------------------- |
| `thread_id`            | `S000004`                                 | Trong cấu hình ứng dụng, thường dùng session ID làm LangGraph thread ID.         |
| `checkpoint_ns`        | `""`                                      | Namespace rỗng là ví dụ phổ biến; không tự sửa namespace của checkpoint hiện có. |
| `checkpoint_id`        | `1f9d0e45-0e8f-4cbd-a30c-dfe3b0fe5301`    | ID checkpoint theo checkpointer.                                                 |
| `parent_checkpoint_id` | `null`                                    | Không có checkpoint cha nếu là checkpoint đầu.                                   |
| `type`                 | `json`                                    | Ví dụ minh họa; type thực tế phụ thuộc serializer.                               |
| `checkpoint`           | object JSON                               | Payload state do checkpointer quản lý; không tự dựng để thay checkpoint thật.    |
| `metadata`             | `{"source":"input","step":1,"writes":{}}` | Metadata do runtime/checkpointer ghi.                                            |

## 13. `public.checkpoint_writes` — write của checkpoint

```json
{
	"thread_id": "S000004",
	"checkpoint_ns": "",
	"checkpoint_id": "1f9d0e45-0e8f-4cbd-a30c-dfe3b0fe5301",
	"task_id": "9d9c5fc3-82bb-4c64-a57e-bbbcd244e310",
	"idx": 0,
	"channel": "messages",
	"type": "msgpack",
	"blob": "<bytea do LangGraph serializer tạo>",
	"task_path": ""
}
```

| Trường          | Ví dụ                                  | Ghi chú                                                                      |
| --------------- | -------------------------------------- | ---------------------------------------------------------------------------- |
| `thread_id`     | `S000004`                              | Thread đang được lưu.                                                        |
| `checkpoint_ns` | `""`                                   | Namespace.                                                                   |
| `checkpoint_id` | `1f9d0e45-0e8f-4cbd-a30c-dfe3b0fe5301` | Checkpoint chứa write.                                                       |
| `task_id`       | `9d9c5fc3-82bb-4c64-a57e-bbbcd244e310` | Task ID do runtime sinh.                                                     |
| `idx`           | `0`                                    | Thứ tự write trong task.                                                     |
| `channel`       | `messages`                             | Channel được ghi.                                                            |
| `type`          | `msgpack`                              | Giá trị minh họa; phụ thuộc serializer được dùng.                            |
| `blob`          | `<bytea do LangGraph serializer tạo>`  | Placeholder mô tả, **không phải literal để insert**; dữ liệu phải là binary. |
| `task_path`     | `""`                                   | Task path; ví dụ namespace/path rỗng.                                        |

## 14. `public.checkpoint_blobs` — blob theo channel/version

```json
{
	"thread_id": "S000004",
	"checkpoint_ns": "",
	"channel": "messages",
	"version": "1",
	"type": "msgpack",
	"blob": "<bytea do LangGraph serializer tạo>"
}
```

| Trường          | Ví dụ                                 | Ghi chú                                                      |
| --------------- | ------------------------------------- | ------------------------------------------------------------ |
| `thread_id`     | `S000004`                             | Thread ID.                                                   |
| `checkpoint_ns` | `""`                                  | Namespace.                                                   |
| `channel`       | `messages`                            | Channel name.                                                |
| `version`       | `1`                                   | TEXT theo schema; ví dụ chuỗi `"1"`, không phải integer.     |
| `type`          | `msgpack`                             | Kiểu serializer minh họa.                                    |
| `blob`          | `<bytea do LangGraph serializer tạo>` | Placeholder; giá trị thật là binary do checkpointer quản lý. |

## 15. `public.checkpoint_migrations` — version migration của checkpointer

```json
{
	"v": 1
}
```

| Trường | Ví dụ | Ghi chú                                                                                                                                                      |
| ------ | ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `v`    | `1`   | Chỉ là giá trị minh họa. Phiên bản thật phải do migration/version của checkpointer cài đặt; không seed thủ công và không ép về `1` nếu DB đã ở version khác. |

## 16. JSON mẫu theo `data/schemas/call_brief.schema.json`

Đây là object JSON mẫu theo các trường trong **schema CallBrief hiện tại**. Không thêm `customer_id` hoặc `session_id` vào object này chỉ vì các giá trị đó có trong graph state/database.

```json
{
	"customer_phone": "0985003703",
	"customer_name": "Oanh",
	"honorific": "chị",
	"is_returning": true,
	"n_previous_sessions": 1,
	"last_session": {
		"session_id": "S000001",
		"date": "2026-02-17",
		"channel": "hotline",
		"summary": "Mua AirPure X bản 2024 giá 4.290.000đ, phòng 20m².",
		"outcome": "chot_don"
	},
	"profile_facts": { "room_area_m2": 20 },
	"products_advised": [
		{
			"sku": "SKU-AP-X-2024",
			"price_quoted_vnd": 4290000,
			"promo_code": null,
			"promo_still_active": null,
			"quoted_on": "2026-02-17"
		}
	],
	"orders": [{ "order_id": "OD188213", "status": "delivered" }],
	"open_blockers": [],
	"open_questions": ["Chị muốn kiểm tra giá hiện tại hay sản phẩm thay thế?"],
	"must_not_ask": ["room_area_m2"],
	"stale_warnings": [
		"SKU lịch sử SKU-AP-X-2024 cần được xác minh trước khi báo giá lại."
	],
	"suggested_opening": "Dạ chào chị Oanh ạ. Lần trước chị đã tìm hiểu AirPure X, em tiếp tục hỗ trợ chị nhé ạ.",
	"suggested_next_action": "Xác nhận nhu cầu hiện tại và kiểm tra giá, tồn kho hiện hành.",
	"generated_at": "2026-10-26T08:00:00+07:00",
	"latency_ms": 140,
	"precomputed_parts": ["customer_profile", "last_session", "orders"]
}
```

| Trường                    | Giá trị mẫu / kiểu                                                                                                         |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `customer_phone`          | `"0985003703"` — string                                                                                                    |
| `customer_name`           | `"Oanh"` hoặc `null`                                                                                                       |
| `honorific`               | `"chị"` hoặc `null`                                                                                                        |
| `is_returning`            | `true` — boolean                                                                                                           |
| `n_previous_sessions`     | `1` — integer                                                                                                              |
| `last_session`            | object như ví dụ, hoặc `null` nếu chưa có phiên trước                                                                      |
| `last_session.session_id` | `"S000001"`                                                                                                                |
| `last_session.date`       | `"2026-02-17"`                                                                                                             |
| `last_session.channel`    | `"hotline"`                                                                                                                |
| `last_session.summary`    | string tóm tắt                                                                                                             |
| `last_session.outcome`    | `"chot_don"` — một trong `hen_goi_lai`, `chot_don`, `tu_choi`, `chuyen_may`, `khac`                                        |
| `profile_facts`           | object; ví dụ `{"room_area_m2": 20}`                                                                                       |
| `products_advised`        | array sản phẩm đã tư vấn; giá quote integer, mã KM string/null, `promo_still_active` boolean/null, `quoted_on` date string |
| `orders`                  | array order; `order_id` string, `status` string; chỉ thêm `variant_sku` khi có variant SKU thực                            |
| `open_blockers`           | array string, ví dụ `[]`                                                                                                   |
| `open_questions`          | array string                                                                                                               |
| `must_not_ask`            | array slot names, ví dụ `["room_area_m2"]`                                                                                 |
| `stale_warnings`          | array string                                                                                                               |
| `suggested_opening`       | string                                                                                                                     |
| `suggested_next_action`   | string                                                                                                                     |
| `generated_at`            | timestamp ISO 8601 có timezone                                                                                             |
| `latency_ms`              | `140` — integer milliseconds, giá trị minh họa                                                                             |
| `precomputed_parts`       | array string                                                                                                               |

## 17. JSON mẫu theo `data/schemas/handoff_brief.schema.json`

```json
{
	"customer_phone": "0985003703",
	"customer_name": "Oanh",
	"customer_id": "C031",
	"channel": "hotline",
	"escalation_reason": "khach_yeu_cau_gap_nguoi",
	"escalation_reason_detail": "Khách muốn trao đổi trực tiếp với nhân viên tư vấn.",
	"conversation_summary": "Khách Oanh đã tìm hiểu máy lọc không khí AirPure X cho phòng khoảng 20m². Hệ thống cần xác minh SKU và giá hiện tại trước khi tiếp tục tư vấn.",
	"product_advised": "SKU-AP-X",
	"price_quoted_vnd": 4890000,
	"promo_code": null,
	"facts_confirmed": { "room_area_m2": 20 },
	"open_questions": [],
	"sentiment": "binh_thuong",
	"next_action": "Nhân viên xác minh giá và SKU hiện hành, sau đó tiếp tục tư vấn cho khách.",
	"history_refs": ["S000001"],
	"generated_at": "2026-10-26T08:05:00+07:00"
}
```

Các giá trị enum quan trọng theo schema hiện tại:

- `channel`: `hotline`, `chat_fanpage`, `zalo_oa`, `web_chat`, `other`.
- `escalation_reason`: `cau_hoi_y_te`, `ngoai_pham_vi_tai_lieu`, `khach_yeu_cau_gap_nguoi`, `khieu_nai_nghiem_trong`, `loi_he_thong`, `khach_mat_kien_nhan`, `khac`.
- `sentiment`: `binh_thuong`, `hai_long`, `kho_chiu`, `gian`.
- `conversation_summary` dài từ 20 đến 800 ký tự theo schema.

## 18. JSON mẫu theo `data/schemas/trace_log.schema.json`

Ví dụ một dòng JSONL tối giản nhưng có đủ các trường bắt buộc trong schema; dữ liệu latency là giả lập.

```json
{
	"run_id": "run-20261026-001",
	"config": "full",
	"scenario_id": "SC-01",
	"call": "call_2",
	"turn": 1,
	"customer_text": "Phòng nhà em khoảng 20m², giá AirPure X hiện tại thế nào?",
	"agent_text": "Dạ, em sẽ kiểm tra giá hiện tại cho mình ạ.",
	"questions": [
		{
			"slot": "current_need",
			"type": "confirm",
			"text": "Mình đang muốn kiểm tra giá AirPure X đúng không ạ?"
		}
	],
	"facts_used": ["room_area_m2"],
	"claims": [
		{
			"field": "list_price_vnd",
			"value": 4890000,
			"text": "Giá niêm yết AirPure X là 4.890.000đ."
		}
	],
	"tool_calls": [
		{
			"name": "catalog.search",
			"args": { "sku": "SKU-AP-X" },
			"result": { "items": [{ "sku": "SKU-AP-X", "list_price_vnd": 4890000 }] }
		}
	],
	"latency": { "ttft_ms": 520, "total_ms": 1700, "ttfa_ms": 800 },
	"call_brief_latency_ms": 140,
	"memory_writes": [
		{
			"key": "room_area_m2",
			"value": 20,
			"op": "set",
			"source": "call_2#turn1",
			"customer_id": "C031"
		}
	],
	"customer_input_mode": "clean"
}
```

Lưu ý schema `trace_log` quy định `config` là `baseline_no_memory` hoặc `full`; `call` là `call_1`, `call_2`, `call_3`; `turn >= 1`; `questions[].type` là `open` hoặc `confirm`; `customer_input_mode` (nếu có) là `clean`, `asr_transcript`, hoặc `chat_teencode`.

## 19. Ví dụ ID cho bản ghi mới sau khi đồng bộ sequence

| Đối tượng        | ID mẫu đề xuất                         | Ghi chú                                                                                                       |
| ---------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Customer mới     | `C051`                                 | Dùng sequence/ID generator atomic; không dùng `CUST_...`.                                                     |
| Customer kế tiếp | `C052`                                 | Không dùng riêng `MAX(id) + 1` ở mỗi request đồng thời.                                                       |
| Order mới        | `OD301178`                             | Ví dụ sau `OD301177`, chỉ dùng nếu preflight xác nhận không có ID lớn hơn hoặc collision.                     |
| Session mới      | `S000004`                              | Ví dụ sau khi `S-OLD-1` đến `S-OLD-3` đã được migrate thành `S000001` đến `S000003` và sequence được đồng bộ. |
| Turn ID          | `9fa19642-35c8-4cd3-9b6b-3c2906e0c12b` | TEXT; không cần áp cùng format session.                                                                       |
| Event ID         | `b2d5d3ef-0c3d-4c29-8f0e-68fb2c630b2d` | UUID.                                                                                                         |
| Episode ID       | `76db6358-b8d6-4f8c-9911-a7ae5aafe0c0` | UUID; nên để DB tự sinh.                                                                                      |
| Order item ID    | `b7e17c5c-5ad2-41c5-8a40-e37a6e0c5b21` | UUID; nên để DB tự sinh.                                                                                      |

## 20. Các điểm cần nhớ khi dùng sample

1. **Đừng đặt UNIQUE cho `customers.phone`.** Seed hiện tại có `C034` và `C035` dùng chung phone `0958421083`. Nhiều kết quả theo phone phải trả `ambiguous` nếu không có thông tin phân biệt đáng tin cậy.
2. **Không lưu `orders`/`sessions` dưới dạng danh sách JSON trong `customers` ở database.** Các list trong seed là format đầu vào; importer phải tạo các dòng quan hệ tương ứng.
3. **Giữ đúng nguồn dữ liệu.** Không tự điền địa chỉ, email, tên sản phẩm lịch sử hoặc giờ bắt đầu/kết thúc nếu seed không cung cấp.
4. **Giữ nguyên contract schema.** Validate CallBrief và HandoffBrief theo `data/schemas/*.schema.json`. Không thêm trường DB/internal state vào JSON contract nếu schema không quy định.
5. **Không insert checkpoint mẫu.** `checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations` do LangGraph checkpointer quản lý.
6. **Mọi migration dữ liệu/ID phải có mapping và preflight.** Không tự đổi ID lịch sử hoặc chạy `DROP`, `TRUNCATE`, `CASCADE` chỉ để dữ liệu khớp ví dụ.
7. **Đây là mẫu đối chiếu**, không phải file seed SQL và không khẳng định toàn bộ schema mục tiêu đã có trên Supabase live.
