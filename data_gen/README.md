# Hướng dẫn sinh dataset hội thoại

> Hướng dẫn này dành cho thành viên thiết kế, sinh và review dataset trong `data_gen/`. Làm theo thứ tự từng bước; không chạy batch Gemini trên brief chưa review.

## 1. Phạm vi hiện tại

- Đợt hiện tại tập trung vào **M1, hội thoại text**. Mục tiêu M1 trong `dataset_config.json`: tối thiểu 120 transcript, 30 khách đa phiên, 10 khách đa kênh, một ngành hàng (`thoi-trang`) và hai miền (`bac`, `nam`). Audio is not generated in this phase; clean `customer_turns` and text `customer_turns_asr` are still generated, so M1 remains incomplete. M2 chưa được bật.
- Coverage matrix hiện là kế hoạch, không phải dataset đã sinh hay đã được duyệt. Mỗi dòng là một scenario; `num_calls` là số transcript/cuộc trong scenario.
- Lượt khách được sinh bằng LLM hoặc dry-run. Agent không được sinh trong dataset: scenario chỉ chứa `customer_turns` cùng facts và điều kiện chấm do pipeline tạo từ brief/mock tools.
- Giá, khuyến mãi, tồn kho, chính sách, ngày và dữ kiện CRM phải khớp dữ liệu BTC. Thư mục `data/` chỉ đọc; không sửa hoặc đưa PII thật vào brief, prompt, log hay báo cáo.

## 2. Luồng công việc

```text
Kiểm tra môi trường và dữ liệu BTC
  → review coverage_matrix.csv
  → tạo/review brief
  → lint brief
  → dry-run + auto-check
  → sinh thử bằng Gemini
  → review scenario và chốt
  → track coverage, lưu manifest và bàn giao
```

Mọi lệnh dưới đây chạy từ **repository root** trong PowerShell.

## 3. Chuẩn bị môi trường (mỗi thành viên làm một lần)

Cài dependencies nếu môi trường chưa có:

```powershell
python -m pip install -r requirements.txt
```

Tạo `.env` local từ template, điền API key của mình; không commit `.env` hoặc chia sẻ key:

```powershell
Copy-Item .env.example .env
```

Các giá trị data generation thường dùng:

```dotenv
GEMINI_API_KEY=your_key
HARNESS_GEN_MODEL=gemini-3.5-flash-lite
GEMINI_MIN_INTERVAL_SECONDS=4.0
BTC_DIR=./data
```

## 4. Review coverage matrix

File làm việc hiện tại: `data_gen/reports/coverage_matrix.csv`. Matrix được quản lý trực tiếp và có thể có quyết định biên tập đã review; **không tự chạy lệnh `generate` hoặc `pipeline --regenerate-matrix`**, vì chúng tạo lại kế hoạch.

Lọc theo `owner`. Kiểm tra tối thiểu:

- `level`, `case_number`, `slot_id`: đúng M1, ID duy nhất và thứ tự liên tục.
- `persona_id`: đúng mục tiêu tâm lý/hành vi; prompt persona lấy từ `data/simulator/personas.json`.
- `nganh`, `mien`: đúng phạm vi M1 và category thực tế trong catalog.
- `num_calls`, `channel_pattern`: số kênh phải khớp số cuộc; mỗi phần tử là một kênh (`hotline`, `chat_fanpage`, `zalo_oa`). Đa kênh chỉ ghi khi có chuyển kênh thật.
- `hard_case_tag`, `special_customer`, `customer_id`: phải phù hợp nhau. Case cần lịch sử/đơn đặc biệt phải dùng đúng CRM customer; case không cần lịch sử nên dùng customer bình thường.
- `promo_*`, `policy_*`, `story_hints`: nêu dữ kiện/diễn biến khiến case kiểm thử được. `story_hints` được truyền vào `calls[].story_hint` và system prompt của persona; phân tách diễn biến từng cuộc bằng `Call 1: ... || Call 2: ...`.
- `owner`, `status`: cập nhật tiến độ; không xóa slot đã thống nhất. Nếu cần bỏ, đặt `status=dropped`; không ghi lý do vào `story_hints` vì nội dung này được đưa cho LLM.

Không tạo customer ID, SKU, promo code hoặc policy chunk bằng suy đoán. `customer_id` phải tồn tại trong CRM; `NEW:<id>` chỉ dùng khi brief/linter/mock tools hỗ trợ và case thực sự cần khách mới.

## 5. Tạo và hoàn thiện brief

Một brief JSON trong `data_gen/briefs/` là đặc tả đầu vào cho **một scenario**, có một hoặc nhiều cuộc gọi. Tên/ID brief phải khớp `slot_id` trong matrix. Có thể tạo khung ban đầu từ CSV:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix stubs `
  --matrix data_gen/reports/coverage_matrix.csv `
  --out data_gen/briefs/
```

Lệnh này giúp điền thông tin vào trong cấu trúc brief và không ghi đè brief đã tồn tại. Chỉ dùng `--force` khi chủ động muốn tạo lại stub và đã lưu phần biên tập cần giữ. Stub là bản nháp, không phải brief đã sẵn sàng sinh.

Người phụ trách cần đọc và hoàn thiện từng brief, bảo đảm:

1. `level`, `case_number`, `brief_id`, `persona_id`, `customer_id` khớp matrix.
2. Mệi call có `call_index` liên tục, `days_later`, `channel`, `products`/variant và `expected_outcome` hợp lý. Pipeline sinh `customer_goal` sau khi có customer turns và chỉ đặt ở `call_1`.
3. Dữ kiện khách nói nằm trong `facts_to_establish`; không tự điền giá cuối, kết quả tồn kho/khuyến mãi hay nội dung policy. Pipeline lấy factual values từ catalog/mock tools.
4. `story_hint`/diễn biến call làm cho hard case xảy ra rõ ràng. Ví dụ: callback nêu đúng thời điểm; hàng hết giữa các cuộc phải có mốc ngày; shared phone phải xác minh người gọi; khách thiếu kiên nhẫn phải giới hạn câu hỏi; đổi hàng cần có lịch sử mua và SKU cụ thể.
5. `success_if` kiểm thử đúng hành vi mong đợi. `story_hints` chỉ hướng dẫn diễn biến phía khách, không thay thế điều kiện chấm hoặc danh sách tool bị cấm.
6. Không có PII thật, giá nội bộ, giá nhập, thông tin nhà cung cấp hoặc dữ kiện khuyến mãi chưa bắt đầu bị lộ cho khách.

Brief cần đủ dữ kiện để khách simulator bám kịch bản. `gen_dialogue` kết hợp `system_prompt` của persona trong BTC `personas.json` với prompt chung `data_gen/prompts/customer_turns_v5.txt`; mỗi call nhận `story_hint` trực tiếp từ coverage matrix, cùng `style`, vị trí `call_index/scenario_num_calls` và `patience_initial`. Sau khi sinh turns, pipeline tổng hợp `notes` và `customer_goal` từ persona, hard case và lời khách, lưu kết quả vào `data_gen/raw/<SC-ID>_scenario_metadata.json` để tái sử dụng. Brief quy định facts và diễn biến; không dựa vào persona để tự tạo facts còn thiếu.

## 6. Lint brief trước khi sinh

Sau khi hoàn thiện brief, chạy lint trên thư mục:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
```

Chỉ tiếp tục khi tất cả brief được đưa vào batch đều pass. Linter kiểm tra schema/field, persona và customer trong nguồn BTC, SKU/variant, promotion, policy, chuỗi call và các yêu cầu cấu trúc theo hard-case tag. Lint không thay review nội dung của con người.

## 7. Dry-run offline

Dry-run không gọi Gemini và không dùng để đánh giá chất lượng hội thoại. Chạy một vài brief để kiểm tra đường đi và schema:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios_dryrun/ `
  --dry-run `
  --level M1 `
  --limit 3 `
  --seed 7
```

Sau đó chạy kiểm tra tự động:

```powershell
python -m data_gen.auto_check `
  --scenarios data_gen/scenarios_dryrun/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/ `
  --raw data_gen/raw/
```

`auto_check` đối chiếu scenario với brief, raw customer turns và fact pack; kiểm tra số lượt (4–8), call/kênh/identity, giá và tồn kho bằng BTC mock tools, `success_if`/ground truth, PII và dữ kiện tiền không có căn cứ. Kết quả chi tiết ở `data_gen/reports/auto_check_report.csv`: lỗi `E*` là hard error (lệnh trả mã khác 0), `W*` là cảnh báo. `W9_MANUAL_REVIEW` luôn nhắc review giọng persona, mạch story hint và việc hard case có thực sự xuất hiện hay không.

Đây là kiểm tra artifact và phần lời khách được sinh, **không** đánh giá phản hồi của agent hay chứng minh scenario đạt nội dung chỉ nhờ tag. Những phần đó cần contract/eval và review thủ công; không gọi LLM judge trong bước auto-check để tránh chi phí, tính không ổn định và false positive trên dữ liệu không có lời agent.

Dry-run chỉ xác nhận pipeline có thể tạo output. Không đưa dry-run vào kết quả chất lượng, metric hoặc dataset freeze.

## 8. Sinh bằng Gemini

Chỉ sinh sau khi matrix và brief đã review, lint pass, và dry-run/auto-check không còn lỗi cần xử lý. Bắt đầu bằng một batch nhỏ vào thư mục production:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios/ `
  --level M1 `
  --limit 3 `
  --seed 7
```

Đọc log, `data_gen/reports/manifest.jsonl`, các file trong `data_gen/raw/` và `data_gen/scenarios/`. Nếu ổn, bỏ `--limit 3` để chạy toàn bộ brief M1 đã pass lint. Không chạy đồng thời nhiều batch dùng chung API key; nếu gặp giới hạn tốc độ, tăng `GEMINI_MIN_INTERVAL_SECONDS` trong `.env`.
| `data_gen/scenarios_metadata/` | Sidecar lưu customer IDs nội bộ theo call, case_number, teencode_level, `story_hints` từ brief và provenance summary. |

`run_batch` có thể reuse raw tương thích theo seed, prompt, model/provider và brief. Chỉ thêm `--force` khi muốn tái sinh có chủ đích; lệnh này có thể thay output hiện tại. Khi đổi brief/prompt, kiểm tra kỹ trước khi force để không mất artifact đã được review.

Chế độ `--assemble-only` dựng scenario từ artifact đã lưu mà không gọi LLM; raw turns, fact packs và summary artifact tương thích đều phải có sẵn. Nếu story_hints, customer turns hoặc prompt summary thay đổi, chạy batch thường để sinh lại artifact summary cần thiết:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios/ `
  --level M1 `
  --ready-only `
  --assemble-only
```

Chế độ này yêu cầu raw/fact pack có sẵn cho mọi call, không sinh lại lời khách; output digest và code digest vẫn được ghi vào manifest.

## 9. Review scenario

Sau khi sinh, chạy lại `auto_check` trên thư mục production:

```powershell
python -m data_gen.auto_check `
  --scenarios data_gen/scenarios/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/
```

Review thủ công ít nhất các hard case và một mẫu của từng persona/kênh. Xác nhận:

- khách chỉ nói những gì brief cho phép; giọng điệu và mức kiên nhẫn đúng persona;
- mạch giữa các call nhất quán, không nhắc lại dữ kiện không cần thiết, kênh đổi đúng kế hoạch;
- khách không nói thay agent, không bịa số liệu/giá/policy và không đưa PII thật;
- case thực sự tạo ra điều kiện kiểm thử và `success_if` tương ứng có ý nghĩa.

Nếu có lỗi, sửa brief/prompt/code/story_hints theo đúng nguồn, sinh lại scenario bị ảnh hưởng và review lại. Không sửa tay scenario JSON đã sinh để “làm cho pass”. Chỉ đánh dấu `validated` sau auto-check và review tay.

## 10. Checklist trước khi bàn giao/freeze

- [ ] Matrix có owner/status rõ, ID liên tục/duy nhất, quota M1 và channel/persona/customer nhất quán.
- [ ] Brief khớp matrix, không còn TODO, pass `lint_briefs`.
- [ ] Hard case có facts và điều kiện chấm rõ; review bằng người thật, không chỉ dựa vào tag.
- [ ] Production scenario sinh từ LLM, pass `auto_check`, pass contract và đã review thủ công.
- [ ] Có manifest và tracking report; chỉ artifact đã được review mới đánh dấu `validated`.
- [ ] Dry-run không được tính là dữ liệu production; audio/ASR và M2 không được báo là hoàn tất.
- [ ] Không commit `.env`, API key, PII thật, database hoặc artifact nhạy cảm.

## 11. Vai trò các artifact chính

| Đường dẫn                                           | Vai trò                                                              |
| --------------------------------------------------- | -------------------------------------------------------------------- |
| `data_gen/reports/coverage_matrix.csv`              | Kế hoạch scenario và phân công owner.                                |
| `data_gen/briefs/*.json`                            | Đặc tả nội bộ đã được review cho từng scenario.                      |
| `data_gen/fact_packs/`                              | Fact pack xác định bằng code từ dữ liệu BTC/mock tools, theo call.   |
| `data_gen/raw/`                                     | Lượt khách do LLM/dry-run sinh và metadata prompt/model/seed.        |
| `data_gen/scenarios/`                               | Scenario production theo contract BTC, dùng cho review/eval.         |
| `data_gen/scenarios_dryrun/`                        | Output offline để thử contract; không phải dữ liệu đánh giá.         |
| `data_gen/reports/manifest.jsonl`                   | Nhật ký batch, trạng thái, model/prompt/seed và digest.              |
| `data_gen/reports/coverage_tracking.csv`            | Trạng thái slot suy ra từ brief/raw/scenario; không thay matrix gốc. |
| `data_gen/prompts/customer_turns_v4.txt`            | Prompt chung hiện hành; kết hợp system prompt persona BTC.           |
| `data_gen/auto_check.py`, `data_gen/lint_briefs.py` | Kiểm tra cấu trúc brief và lỗi scenario tự động.                     |

## 12. Lệnh nhanh

```powershell
# 1. Xem dữ liệu BTC
python -m data_gen.explore_data

# 2. Kiểm tra coverage (không tính audio đợt này)
python -m data_gen.coverage_matrix.make_coverage_matrix report --matrix data_gen/reports/coverage_matrix.csv --defer-audio

# 3. Tạo stub còn thiếu; không ghi đè brief đã có
python -m data_gen.coverage_matrix.make_coverage_matrix stubs --matrix data_gen/reports/coverage_matrix.csv --out data_gen/briefs/

# 4. Lint brief
python -m data_gen.lint_briefs data_gen/briefs/

# 5. Dry-run một vài case rồi auto-check
python -m data_gen.run_batch --briefs data_gen/briefs/ --out data_gen/scenarios_dryrun/ --dry-run --level M1 --limit 3 --seed 7
python -m data_gen.auto_check --scenarios data_gen/scenarios_dryrun/ --briefs data_gen/briefs/ --fact-packs data_gen/fact_packs/

# 6. Sinh thử bằng Gemini sau khi review
python -m data_gen.run_batch --briefs data_gen/briefs/ --out data_gen/scenarios/ --level M1 --limit 3 --seed 7

# 7. Sinh riêng lẻ một call
python -m data_gen.gen_dialogue --brief data_gen/briefs/SC-001.json --call 1
python -m data_gen.gen_dialogue --brief data_gen/briefs/SC-001.json --call 2

# 8. Tong hop nhieu call thanh 1 scenario
python -m  data_gen.assemble_scenario --brief data_gen/briefs/SC-0o1.json --out data_gen/scenarios
```

Xem chi tiết về cách lập và đọc matrix tại [`coverage_matrix/README.md`](coverage_matrix/README.md). Mục tiêu M1/M2 và thứ tự level nằm trong [`dataset_config.json`](dataset_config.json); cấu hình hiện chỉ bật M1 trong batch mặc định.
