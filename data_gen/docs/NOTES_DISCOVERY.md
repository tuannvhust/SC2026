# BTC data discovery

Ngày discovery: 2026-10-08. `BTC_DIR` hiện được resolve mặc định thành `./data/source/btc`. Các file dưới `data/source/btc/` được xem là read-only; pipeline chỉ đọc chúng.

## 1. Scenario format

Nguồn: `data/schemas/scenario_format.md` và 7 file `data/test_set/public_sample/*.json`.

Top-level schema thực tế:

| Field | Required theo tài liệu | Type thực tế | Ý nghĩa | Ví dụ verbatim |
|---|---:|---|---|---|
| `scenario_id` | Có | string | ID scenario | `"SAMPLE-01"` |
| `level` | Có | `"M1"` hoặc `"M2"` | level bài | `"M1"` |
| `persona` | Có | string | phải trùng `persona_id` trong simulator | `"khach_do_du_hoi_nguoi_nha"` |
| `hard_case` | Có theo mô tả; sample có thể null | string/null | tag ca khó | `"doi_khuyen_mai_het_han"` |
| `customer_phone` | Có | string | identity/tool input; phải mask khi log | `"0984726714"` |
| `customer_name` | Có | string | tên CRM | `"Hoa"` |
| `honorific` | Có | string | xưng hô | `"chị"` |
| `notes` | Có theo mô tả; samples đều có | string | ghi chú cho evaluator/reviewer | `"Kịch bản lõi Case 1..."` |
| `calls` | Có | object | map `call_1`…`call_3` | `{"call_1": {...}}` |

Call object có các field sau; đây là field set quan sát được từ schema/samples, không phải mọi field đều xuất hiện ở mọi call:

| Field | Type | Ý nghĩa |
|---|---|---|
| `channel` | string | `hotline`, `chat_fanpage`, `zalo_oa`; sample call không ghi thì agent mặc định phải xử lý theo contract |
| `channel_identity` | string | định danh kênh, ví dụ `fb.hạnh.274` |
| `call_date` | ISO date string | ngày gọi; ưu tiên field này |
| `days_later` | non-negative integer | số ngày cộng từ call trước; call đầu tính từ reference date |
| `input_mode` | string | `clean`, `asr_transcript`, `chat_teencode` |
| `customer_goal` | string | mục tiêu call |
| `customer_turns` | array[string] | clean customer input, deterministic |
| `customer_turns_asr` | array[string] | input nhiễu; hệ thống nhận bản này khi `input_mode=asr_transcript` |
| `facts_established` | object | facts khách nói trong call, dùng cho memory/CCR |
| `seed_history` | array/object | history CRM cần nạp trước call, nếu cần |
| `must_carry_over` | array[string] | slot/state bắt buộc được dùng tiếp |
| `must_not_ask` | array[string] | slot không được hỏi mở lại |
| `success_if` | object/null | điều kiện task success |
| `ground_truth_facts` | object | sự thật để đối chiếu claim |
| `memory_expectation` | object | trạng thái memory kỳ vọng |
| `expected_outcome` | enum | `hen_goi_lai`, `chot_don`, `chuyen_may`, `tu_choi` |

`success_if` hỗ trợ `tool_called`, `args_match`, `also_ordered`, `total_match_vnd`, `brief_must_contain`, `must_say_any`, `agent_must_say`, `must_not_call_tools`, `forbidden_claims`, `trace_must_not_match`, `max_agent_questions`.

Ví dụ verbatim từ `SAMPLE-06`:

```json
"success_if": {
  "tool_called": "order.create",
  "args_match": {
    "sku": "SKU-XM-4P",
    "price_vnd": 5490000,
    "payment": "COD"
  }
}
```

7 samples: `SAMPLE-01`…`SAMPLE-06` có 2 calls; `SAMPLE-07` có 1 call. Các persona sử dụng là `khach_do_du_hoi_nguoi_nha`, `khach_so_gia`, `khach_da_mua_doi_size`, `khach_da_kenh_fb_hotline`, `khach_hoi_ngoai_tai_lieu`. Samples chứng minh rằng nhiều facts trong scenario mẫu là dữ kiện grading, không được lấy nguyên xi làm format brief mới.

## 2. Mock tools

Nguồn duy nhất cho nghiệp vụ là `data/eval/mock_tools.py`. Public function và ví dụ từ self-test:

| Function | Parameters | Return | Vai trò |
|---|---|---|---|
| `crm_get_customer` | `phone=None, zalo_id=None, fb_id=None` | dict | CRM identity, ambiguity, profile, orders, sessions |
| `catalog_search` | `query=None, category=None, sku=None, max_price_vnd=None, min_room_area_m2=None, include_discontinued=False` | `{"items": list, "total": int}` | catalog/SKU/variant lookup |
| `inventory_check` | `sku, on=REF` | dict | tồn kho theo ngày, restock, discontinued/successor |
| `pricing_get_quote` | `sku, on=REF, qty=1, customer_phone=None, address=None, basket_skus=None` | dict | list/final price, applied/expired/ineligible promos, freeship; có internal floor không được leak |
| `order_create` | `customer_phone, sku, qty=1, price_vnd=None, promo_code=None, payment="COD", address=None, on=REF, basket_skus=None` | dict | stock/price/COD validation và tạo order |
| `order_status` | `order_id=None, customer_phone=None` | `{"orders": list}` | lịch sử đơn |
| `order_update` | `order_id, action, new_variant_sku=None, reason=None, on=REF` | dict | exchange/return/address update |
| `schedule_callback` | `customer_phone, callback_at, note=None` | dict | callback, dời ngày nghỉ/ngoài giờ |
| `handoff_transfer` | `brief` | dict | validate required handoff brief, tạo ticket |
| `mask_pii` | `text` | string | mask CCCD/bank; phone regex được khai báo nhưng helper hiện chỉ thay CCCD/bank |

Module-level factual sources: `PRODUCTS`, `PROMOS`, `CRM`, `INV`, `REF`, `HOLIDAYS`; dispatch map là `TOOLS`.

Observed examples:

```text
pricing_get_quote("SKU-SN-RUN2-42-DEN")
=> list_price_vnd=1690000, final_price_vnd=1521000,
   applied_promos=[RUN-10], expired_promos=[RUN2-SALE]

inventory_check("SKU-XM-4P")
=> in_stock=false, qty=0, restock_expected="2026-10-19"

order_create(..., "SKU-AP-PRO", qty=2, payment="COD")
=> error="cod_limit_exceeded", limit_vnd=10000000

crm_get_customer(phone=<shared phone>)
=> ambiguous=true, candidates=[...]

schedule_callback(..., "2026-10-26T09:00")
=> callback_at="2026-10-27T09:00", moved_from="2026-10-26T09:00"
```

The tool returns internal fields such as `_internal_price_floor_vnd`; these can be retained in an audit fact pack but must never be passed to customer dialogue or output transcript.

## 3. Validation/evaluation

`data/eval/reference_eval.py` CLI:

```text
python reference_eval.py --scenarios <dir> --trace <full.jsonl> \
  --baseline <baseline.jsonl> --asr <asr_dir> --rag <rag_results.json> --out <report.json>
```

It loads all scenario JSON files by `scenario_id`, groups trace JSONL rows by `(scenario_id, call)`, and evaluates repeat-question rate, context-carryover rate, task-success rate, hallucination rate, average turns, calls-to-close, guardrail violations, memory checks and latency. `trace_must_not_match` is checked over agent text, memory writes and tool args. It does not generate scenarios.

`data/eval/validate_scenarios.py` is referenced by `data/README.md` and the task contract, but is **absent in this checkout** (`Test-Path` returned false). Therefore no validator CLI, error format, or exact implementation can be documented from source. The pipeline must detect this absence and report `BTC_VALIDATOR_MISSING`; it must not silently replace it with a guessed validator. If BTC supplies the file later, the batch should invoke it as a post-check.

## 4. Catalog / CRM

`catalog/products.json` has top-level `reference_date` and `products`. Each product contains `sku`, `name`, `category`, `brand`, `list_price_vnd`, `attributes`, `stock`, and optional `variants`. Variants use `variant_sku`, `size`, `color`, `price_delta_vnd`, `stock`. There are 40 products, 3 major categories, variants, discontinued products with successor SKUs, and bundles.

`catalog/promotions.json` has `reference_date` and `promotions`. Each promotion has `promo_code`, `name`, `applies_to`, `type`, dates, `stackable`, optional discount/gift fields and conditions. At reference date `2026-10-15`: 9 promotions are active, 3 expired (`AP-SEP`, `RUN2-SALE`, `PUMP-GIFT`), and 1 not started (`11-11`). Active promotions include conditional region, quantity, owned-SKU, once-per-customer and variant exclusions.

`catalog/crm_seed.json` has 50 customers. Special cases discovered: 2 shared-phone records (`C034`/`C035`), 2 customers with orders, 3 customers with sessions, one long-history record at 2026-02-17, and an active shipping order (`C032`). CRM records contain `customer_id`, name, honorific, phone, channel IDs, region, orders and sessions. Addresses and phone numbers are PII and must be masked in logs.

## 5. Policy

Policy chunks use bracket IDs in headings, e.g. `[DT-01]`, `[KM-05]`, `[PB-07]`, `[NB-01]`. Current files have titles/versions such as `phiên bản 2026-10`; old policy is explicitly marked `HẾT HIỆU LỰC từ 01/10/2026`; internal files are explicitly marked `NỘI BỘ — KHÔNG CUNG CẤP CHO KHÁCH HÀNG`.

Important categories:

- current: `chinh-sach-doi-tra.md`, `chinh-sach-bao-hanh.md`, `chinh-sach-van-chuyen-thanh-toan.md`, current FAQ/spec/playbook/COD files;
- old: `chinh-sach-doi-tra-v2026-06-HET-HIEU-LUC.md`, chunks `[DT-OLD-*]`;
- internal: `ghi-chu-nhap-hang-NOI-BO.md`, chunks `[NB-*]`, plus administrative internal rules `[NQ-*]`;
- other: changelog `[CL-*]`, product specs `[SP-*]`, holidays `[LN-*]`, FAQ `[FAQ-*]`, playbook `[PB-*]`, COD `[QT-*]`.

The fact builder must retrieve policy text by chunk ID from files, label current/old/internal from filename/title, and redact internal text from every LLM prompt intended to produce customer-facing dialogue.

## 6. Personas

All 12 IDs come from `data/simulator/personas.json`; no new persona may be invented.

| ID | Description / behavior |
|---|---|
| `khach_do_du_hoi_nguoi_nha` | lịch sự, hỏi kỹ, hay cần hỏi người nhà; chưa mua nếu outline không cho phép |
| `khach_so_gia` | thực dụng, nhắc giá đối thủ, đòi giảm; kiểm tra khi agent tự giảm |
| `khach_da_mua_doi_size` | khách cũ, kỳ vọng shop nhớ đơn; khó chịu nếu hỏi lại mã/sản phẩm |
| `khach_hoi_nhieu_khong_mua` | hỏi nhiều kỹ thuật, so sánh, chưa muốn mua; kiểm tra claim bịa |
| `khach_goi_lan_3_het_kien_nhan` | cộc, muốn xong nhanh; call 3 không muốn bị hỏi lại |
| `khach_da_kenh_fb_hotline` | chat teencode, gọi bình thường; kỳ vọng các kênh chia sẻ context |
| `khach_ngoai_pham_vi_chuyen_may` | hỏi y tế/an toàn; chấp nhận chuyển máy |
| `khach_hoi_ngoai_tai_lieu` | hỏi điều shop không có; chấp nhận honest no-information |
| `khach_da_kenh_mau_thuan` | bực vì các kênh báo giá khác nhau; cần giải thích theo thời điểm |
| `hai_nguoi_chung_sdt` | hai người dùng chung số; phải xác nhận đúng identity |
| `khach_quay_lai_sau_8_thang` | khách cũ nhớ mang máng; chú ý TTL và xác nhận địa chỉ |
| `khach_mua_nhieu_mon` | nói lan man, nhiều món, có thể đổi ý; cần tổng kết trước khi chốt |

## Giả định & điều chưa chắc

- Brief mới sẽ lưu `customer_id` nhưng scenario BTC vẫn cần `customer_phone`; pipeline resolve phone từ CRM và chỉ ghi phone vào scenario output, không ghi phone vào logs/manifest/prompts nếu không cần.
- `NEW:<id>` là quy ước brief của task, không phải format scenario BTC; cần map deterministic sang customer identity tối thiểu và không tự tạo CRM record trong BTC_DIR.
- `policy_chunk_ids` cần được parse từ headings; không đoán chunk nếu ID không tồn tại.
- `hard_case_tags` và channel enum ngoài các giá trị quan sát được chưa có schema JSON riêng; lint sẽ lấy danh sách từ BTC samples/schema hoặc báo unknown thay vì tự mở rộng.

## Mâu thuẫn giữa các tài liệu

1. `data/README.md` nói có `data/eval/validate_scenarios.py`, task yêu cầu chạy file này, nhưng file không tồn tại trong checkout. Đây là blocker cho việc khẳng định “pass validator BTC”; pipeline chỉ có thể ghi nhận thiếu validator và tiếp tục các check nội bộ.
2. Task brief format yêu cầu `products[].variant_id`, còn BTC catalog thực tế dùng `variant_sku`; assemble phải map `variant_id` sang `variant_sku` bằng catalog, không đưa field brief thẳng vào scenario.
3. Task muốn raw dialogue 8–16 turns gồm cả customer và agent, nhưng BTC scenario format chỉ định nghĩa `customer_turns`/`customer_turns_asr`; full dialogue phải lưu ở `raw/` hoặc metadata review, không được nhét vào scenario BTC.
4. Task yêu cầu “all factual information from mock_tools”, nhưng `mock_tools.py` không expose policy lookup function. Policy facts phải đọc read-only từ `data/policy/*.md` và được source-tagged; không được giả vờ rằng mock tool đã cung cấp policy text.
5. `mock_tools.mask_pii()` mask CCCD/bank nhưng không thay phone dù có regex phone; pipeline phải dùng helper bổ sung ở lớp log/manifest để đảm bảo phone không xuất hiện unmasked.
