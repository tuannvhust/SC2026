# Coverage matrix cho data generation

## Scenario / call matrix (current contract)

`reports/coverage_matrix.csv` contains scenario-level metadata only. Per-call assignments live in `reports/coverage_calls.csv`; each `slot_id` plus `call_index` identifies a call. The call table is the source of truth for CRM customer, channel, products, story, expected outcome, promotion timing/condition, and policy references. `stubs` reads these assignments directly.

The old combined matrix can be migrated once, preserving reviewed IDs and using existing briefs where available:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix migrate `
  --matrix data_gen/reports/coverage_matrix.csv `
  --briefs data_gen/briefs/
```

Then validate the CRM/catalog/policy links, continuous call indexes, shared-phone pairs, and the M1 outcome floor:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix validate
python -m data_gen.coverage_matrix.make_coverage_matrix report --defer-audio
```

Outcome counts are reported by level, layer, hard-case tag, and call. The configured floor is 10 calls per outcome in each enabled level. M2 remains disabled in `dataset_config.json` until the M1 gate is met; M2 planning rows do not cause M2 artifacts to be generated.

## Contract đang chạy

Matrix là kế hoạch theo số lượng slot. `stubs` chuyển hard-case tag thành brief có tình huống, facts và điều kiện chấm; `lint_briefs` kiểm tra nội dung cấu trúc đó. Một tag được đếm trong matrix chưa có nghĩa scenario đã thể hiện đúng case.

Các case đặc biệt hiện có gồm callback ngày nghỉ, ba kênh báo giá, giỏ bốn món vượt giới hạn COD/ngân sách, size bị loại khỏi khuyến mãi, shared phone, lịch sử 8 tháng, và SKU hết tồn giữa hai cuộc. Ca bốn món có thể chọn ngành hàng khác ngành M1 mặc định để đủ tổng giá trị; ngành ở matrix phản ánh đúng catalog đã chọn.

Persona được gán trong matrix sẽ dùng `system_prompt` tương ứng từ BTC khi sinh lượt khách. Chỉ dẫn an toàn và giới hạn dữ kiện trong prompt chung `customer_turns_v4.txt` luôn áp dụng.

Folder này lập kế hoạch độ phủ trước khi viết nhiều brief. Mỗi dòng trong matrix là một scenario dự kiến, không phải một ô nhân chéo persona × ngành × miền.

## Vì sao cần coverage matrix?

Coverage matrix giúp nhóm tránh chỉ sinh nhiều scenario giống nhau. Nó theo dõi đồng thời:

- đủ 12 persona trong `data/simulator/personas.json`;
- đủ 3 nhóm ngành thực tế lấy từ `catalog/products.json`;
- đủ miền `bac`, `trung`, `nam`;
- khách nhiều cuộc gọi và nhiều kênh;
- các ca khó: shared phone, TTL/history, đơn đang giao, policy cũ, unanswerable, restricted, numeric, multi-hop, teencode và promotion theo trạng thái/điều kiện;
- người phụ trách và trạng thái của từng slot.

Script không hard-code persona, SKU, customer ID hoặc promotion ID. Các giá trị được discovery trực tiếp từ BTC data. Customer đặc biệt được chọn theo cấu trúc CRM, không tự tạo hồ sơ.

## File trong folder

| File | Chức năng |
|---|---|
| `matrix_config.json` | Chứa owner, thứ tự ngành và quota nội bộ. Không chứa placeholder persona/ngành. |
| `../dataset_config.json` | Mục tiêu chính thức M1/M2, thứ tự level và số slot nền cho matrix. |
| `make_coverage_matrix.py` | CLI generate/report/stubs. Đọc BTC data qua `data_gen.config.BTC_DIR`. |
| `README.md` | Hướng dẫn vận hành. |
| `__init__.py` | Cho phép chạy script bằng `python -m data_gen.coverage_matrix...`. |

Matrix CSV mặc định được ghi vào `data_gen/reports/coverage_matrix.csv`; brief stub mặc định được ghi vào `data_gen/briefs/`. Matrix mới có `level`, `case_number` global và `slot_id` dạng `SC-001`, `SC-002`, ...`. Generation config hiện bật M1; M2 chỉ được mở lại khi chủ động đổi cấu hình. M1 hiện dùng `thoi-trang` và miền `bac`, `nam` theo `dataset_config.json`.

## Ý nghĩa cột `layer`

`layer` là nhãn lập kế hoạch, không phải field của brief hoặc scenario BTC và hiện không làm thay đổi logic generate dialogue:

- `A` — **hard-case/trap coverage**: các ca bắt buộc để kiểm thử biên như shared phone, policy cũ, promotion hết hạn, unanswerable, restricted, numeric và teencode. Các dòng này phải được ưu tiên viết và review.
- `B` — **baseline diversity coverage**: các ca nền để trải đều persona, ngành hàng, miền, promotion và kênh mà không gắn hard-case cụ thể.

`layer` và các trường phân loại coverage được giữ trong CSV để reviewer biết lý do slot tồn tại và ưu tiên xử lý. Brief chỉ giữ dữ liệu cần cho sinh và kiểm tra scenario; channel được đọc trực tiếp từ từng call, ngành hàng suy ra từ SKU, vùng suy ra từ CRM. Không lưu bản sao các trường matrix trong brief.

## Quy trình làm việc

### 1. Khảo sát dữ liệu

Từ repository root chạy:

```powershell
python -m data_gen.explore_data
```

Đọc `data_gen/reports/data_inventory.csv` và [NOTES_DISCOVERY.md](../NOTES_DISCOVERY.md) để biết các customer đặc biệt, promotion và policy thực tế.

### 2. Sinh matrix

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix generate
```

Lệnh này sinh các level đang bật trong `dataset_config.json`. M1 hiện có 42 slot nền cùng hard-case traps; số transcript kế hoạch được tính từ tổng `num_calls`, không phải số transcript đã sinh.

Lệnh này tự lấy:

- 12 persona từ `data/simulator/personas.json`;
- ngành từ prefix category trong `data/catalog/products.json`;
- miền chuẩn `bac`, `trung`, `nam` theo BTC;
- customer shared phone, long history và order đang shipping từ CRM.

Có thể chỉ định file khác:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix generate `
  --config data_gen/coverage_matrix/matrix_config.json `
  --out data_gen/reports/coverage_matrix.csv
```

### 3. Review và phân công

Mở CSV bằng spreadsheet. Mỗi dòng cần review các cột:

- `persona_id`, `nganh`, `mien`;
- `layer` (`A` hard-case/trap hoặc `B` baseline diversity);
- `hard_case_tag`, `special_customer`, `promo_situation`, `policy_situation`;
- `customer_id` nếu là ca đặc biệt;
- `owner`, `status`, `story_hints`.

### Quy tắc chọn `customer_id`

- Nếu cột `customer_id` đã có giá trị, brief của slot đó **phải dùng đúng customer này**. Đây là customer được pipeline phát hiện từ CRM để tái hiện một trường hợp đặc biệt, ví dụ shared phone, long history hoặc order đang shipping.
- Nếu cột `customer_id` để trống, slot chưa khóa vào customer cụ thể. Thành viên phụ trách phải chọn một customer hợp lệ từ `data/catalog/crm_seed.json` phù hợp với câu chuyện và điền vào brief; không được tự bịa ID.
- Với scenario khách mới, chỉ dùng dạng `NEW:<id>` khi story thực sự cần khách chưa có CRM record và toàn bộ pipeline/mock tools đã hỗ trợ trường hợp đó. Không dùng `TODO` khi commit brief.
- `customer_id` trong CSV là hướng dẫn cho brief, không phải factual data để LLM tự quyết định. Sau khi điền brief, chạy `lint_briefs` để kiểm tra ID.
- Với hard case `shared_phone` có nhiều cuộc gọi và hai người thật sự dùng chung số, `customer_id` ở brief là thành viên gốc của slot; mỗi `calls[]` phải gắn `customer_id` của đúng người gọi trong cuộc đó. Dùng cùng số điện thoại nhưng nhu cầu/facts tách theo người. Chỉ carry over facts khi hai cuộc thuộc cùng `customer_id`; không kế thừa profile hoặc nhu cầu của người kia.

Quy tắc cộng tác:

1. Chỉ sửa dòng có `owner` của mình.
2. Không xoá dòng; dùng `status=dropped`. Không ghi lý do loại bỏ vào `story_hints`, vì nội dung cột này được đưa vào prompt sinh lượt khách.
3. Sau khi tạo brief không đổi persona hoặc hard-case của slot; nếu cần đổi, drop slot cũ và thêm slot mới.
4. Không tự tạo customer ID, SKU, promotion code hoặc policy chunk ID.
5. Matrix là kế hoạch coverage; `lint_briefs.py` mới là kiểm tra brief thực tế.

### 4. Tạo brief stub

Sau khi review CSV:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix stubs `
  --matrix data_gen/reports/coverage_matrix.csv `
  --out data_gen/briefs/
```

Script không ghi đè brief đã tồn tại. Stub generator điền deterministic goal, SKU,
policy, outcome và story mặc định từ BTC data để pipeline có thể chạy end-to-end;
reviewer vẫn phải đọc và tinh chỉnh nội dung theo hard case trước khi freeze.

Lưu ý: brief stub là khung nội bộ, không phải scenario BTC. Sau khi điền xong, chạy:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
```

Không chạy batch khi brief còn `TODO` hoặc chưa qua lint.

### 5. Kiểm tra coverage

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix report `
  --matrix data_gen/reports/coverage_matrix.csv
```

Report đối chiếu các level đang bật với mục tiêu trong `dataset_config.json`. Dùng `--defer-audio` trong đợt text-only để đánh giá phần coverage ngoài audio; kết quả đó không chứng nhận yêu cầu audio đã đạt.

### 5.1 Track artifact đã sinh

Sau khi viết brief hoặc chạy batch, refresh trạng thái bằng:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix track `
  --matrix data_gen/reports/coverage_matrix.csv `
  --briefs data_gen/briefs/ `
  --scenarios data_gen/scenarios/ `
  --raw data_gen/raw/ `
  --audio data_gen/audio/ `
  --out data_gen/reports/coverage_tracking.csv
```

`track` không ghi đè matrix đã review. Nó xuất bản tracking riêng, cập nhật `todo → briefed → generated_dry_run | generated_llm`; chỉ giữ `validated` nếu brief, raw và prompt fingerprint vẫn khớp. Lệnh hiện tại đọc manifest audio tùy chọn `data_gen/audio/<slot_id>.json`:

```json
{"source": "tts", "hours": 0.03, "noisy": true}
```

Sau đó dùng `--matrix data_gen/reports/coverage_tracking.csv` khi chạy `report`.

Báo cáo cho biết tổng số call, số scenario multi-call/multi-channel, độ phủ persona/ngành/miền và hard case. Dòng `dropped` không được tính.

Quota trong `matrix_config.json` là mục tiêu nội bộ của nhóm, không phải thay thế yêu cầu chính thức của BTC. Nếu yêu cầu BTC thay đổi, cập nhật quota có chủ đích và ghi chú trong commit.

### 6. Generate và review

Sau khi coverage đạt và brief pass lint:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios_dryrun/ `
  --dry-run

python -m data_gen.auto_check `
  --scenarios data_gen/scenarios_dryrun/ `
  --briefs data_gen/briefs/
```

Chỉ chuyển scenario đã review sang `data_gen/scenarios/` khi dùng LLM API thật. Coverage matrix không thay thế fact pack, lint, auto-check hoặc review thủ công.

## Ý nghĩa các trạng thái

```text
todo → briefed → generated_dry_run | generated_llm → validated
  └────────────────────────→ dropped
```

- `todo`: chưa có brief.
- `briefed`: brief đã viết, cần lint.
- `generated_dry_run`: có raw/scenario sinh offline; chỉ xác nhận đường chạy và contract.
- `generated_llm`: có raw/scenario sinh bằng model đã cấu hình.
- `validated`: đã qua auto-check và review thủ công.
- `dropped`: loại khỏi batch, phải có lý do.

## Giới hạn

- Matrix chỉ kiểm tra độ phủ theo kế hoạch, không kiểm tra factual correctness.
- Matrix chỉ xác nhận quota theo kế hoạch. Các hard-case được hỗ trợ có kiểm tra cấu trúc trong brief; reviewer vẫn phải xác nhận hội thoại sinh ra thể hiện đúng tình huống.
- BTC checkout hiện thiếu `data/eval/validate_scenarios.py`; matrix/report không thể thay thế validator chính thức.
- Script không sửa `data/`; mọi thay đổi chỉ nằm trong `data_gen/briefs/`, `data_gen/reports/` và các output pipeline.
