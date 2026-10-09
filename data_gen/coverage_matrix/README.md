# Coverage matrix cho data generation

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
| `matrix_config.json` | Chỉ chứa owner, số slot nền và quota. Không chứa placeholder persona/ngành. |
| `make_coverage_matrix.py` | CLI generate/report/stubs. Đọc BTC data qua `data_gen.config.BTC_DIR`. |
| `README.md` | Hướng dẫn vận hành. |
| `__init__.py` | Cho phép chạy script bằng `python -m data_gen.coverage_matrix...`. |

Matrix CSV mặc định được ghi vào `data_gen/reports/coverage_matrix.csv`; brief stub mặc định được ghi vào `data_gen/briefs/`.

## Ý nghĩa cột `layer`

`layer` là nhãn lập kế hoạch, không phải field của brief hoặc scenario BTC và hiện không làm thay đổi logic generate dialogue:

- `A` — **hard-case/trap coverage**: các ca bắt buộc để kiểm thử biên như shared phone, policy cũ, promotion hết hạn, unanswerable, restricted, numeric và teencode. Các dòng này phải được ưu tiên viết và review.
- `B` — **baseline diversity coverage**: các ca nền để trải đều persona, ngành hàng, miền, promotion và kênh mà không gắn hard-case cụ thể.

`layer` được giữ trong CSV để reviewer biết lý do slot tồn tại và ưu tiên xử lý. Khi tạo brief stub, thông tin này được lưu lại trong `_matrix_hints.layer` để không mất trace; field này không được đưa vào output scenario BTC.

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
- `owner`, `status`, `notes`.

### Quy tắc chọn `customer_id`

- Nếu cột `customer_id` đã có giá trị, brief của slot đó **phải dùng đúng customer này**. Đây là customer được pipeline phát hiện từ CRM để tái hiện một trường hợp đặc biệt, ví dụ shared phone, long history hoặc order đang shipping.
- Nếu cột `customer_id` để trống, slot chưa khóa vào customer cụ thể. Thành viên phụ trách phải chọn một customer hợp lệ từ `data/catalog/crm_seed.json` phù hợp với câu chuyện và điền vào brief; không được tự bịa ID.
- Với scenario khách mới, chỉ dùng dạng `NEW:<id>` khi story thực sự cần khách chưa có CRM record và toàn bộ pipeline/mock tools đã hỗ trợ trường hợp đó. Không dùng `TODO` khi commit brief.
- `customer_id` trong CSV là hướng dẫn cho brief, không phải factual data để LLM tự quyết định. Sau khi điền brief, chạy `lint_briefs` để kiểm tra ID.

Quy tắc cộng tác:

1. Chỉ sửa dòng có `owner` của mình.
2. Không xoá dòng; dùng `status=dropped` và ghi lý do vào `notes`.
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

Script không ghi đè brief đã tồn tại. Các giá trị `TODO` là chủ ý: thành viên phải điền goal, sản phẩm, policy, outcome và story hint dựa trên BTC data.

Lưu ý: brief stub là khung nội bộ, không phải scenario BTC. Sau khi điền xong, chạy:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
```

Không chạy batch khi brief còn `TODO`.

### 5. Kiểm tra coverage

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix report `
  --matrix data_gen/reports/coverage_matrix.csv
```

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
todo → briefed → generated → validated
  └────────────────────────→ dropped
```

- `todo`: chưa có brief.
- `briefed`: brief đã viết, cần lint.
- `generated`: đã có raw/scenario.
- `validated`: đã qua auto-check và review thủ công.
- `dropped`: loại khỏi batch, phải có lý do.

## Giới hạn

- Matrix chỉ kiểm tra độ phủ theo kế hoạch, không kiểm tra factual correctness.
- Các tag như `numeric`, `restricted` hoặc `promo_condition_fail` là planning tags; người viết brief vẫn phải chọn dữ liệu cụ thể hợp lệ từ BTC.
- BTC checkout hiện thiếu `data/eval/validate_scenarios.py`; matrix/report không thể thay thế validator chính thức.
- Script không sửa `data/`; mọi thay đổi chỉ nằm trong `data_gen/briefs/`, `data_gen/reports/` và các output pipeline.
