# Pipeline sinh scenario cho Call-Center E-commerce

`data_gen` là pipeline độc lập để tạo scenario hội thoại nhiều cuộc gọi cho cùng một khách hàng, theo format BTC. Pipeline chỉ đọc dữ liệu trong `data/` và không phụ thuộc vào `langgraph_agent/`.

Nguyên tắc quan trọng:

- `data/` là BTC_DIR, chỉ đọc; không sửa, thêm hoặc xoá file trong đó.
- Giá, khuyến mãi, tồn kho, CRM, COD và các factual value phải đến từ BTC data hoặc `data/eval/mock_tools.py`.
- LLM chỉ sinh lời thoại. LLM không sinh `ground_truth_facts`, `success_if`, `must_not_ask` hoặc `must_carry_over`.
- Full dialogue được lưu ở `raw/` để review. Scenario BTC chính thức chứa các field theo `scenario_format.md`; pipeline giữ thêm `customer_id` ở top-level như metadata truy xuất CRM, để reviewer phân biệt đúng customer trong brief (đặc biệt với shared-phone).
- Không ghi số điện thoại, địa chỉ hoặc PII chưa mask vào prompt, log, manifest hay report. `customer_phone` chỉ xuất hiện trong scenario nếu schema BTC bắt buộc.

## 0. Cài đặt API key bằng `.env`

Mọi thành viên dùng cùng quy ước: lưu Gemini API key trong file `.env` ở repository root. File `.env` đã được gitignore và không được commit. Không đặt key trong brief, prompt, source code, report hoặc manifest.

Tạo file local từ template:

```powershell
Copy-Item .env.example .env
```

Mở `.env` và thay giá trị mẫu:

```dotenv
GEMINI_API_KEY=your_real_gemini_api_key
HARNESS_GEN_MODEL=gemini-3.5-flash-lite
GEMINI_MIN_INTERVAL_SECONDS=2.0
BTC_DIR=./data
```

Pipeline tự động load `.env` khi import `data_gen.config`, vì vậy không cần đặt key thủ công trong từng terminal. Mỗi thành viên chỉ sửa file `.env` local của mình; không commit file này.

Lưu ý: `langgraph_agent` hiện vẫn đọc các biến legacy `ANTHROPIC_API_KEY`, `HARNESS_MODEL` và `HARNESS_DB`. Các biến này được giữ trong `.env.example` để agent không bị hỏng; chúng không được `data_gen` dùng khi đã có `HARNESS_GEN_MODEL`.

Kiểm tra trước khi commit:

```powershell
git status --short
git check-ignore .env
```

Lệnh thứ hai phải trả về `.env`. Nếu key đã từng bị commit hoặc bị lộ, cần thu hồi key trên Google AI Studio và tạo key mới; chỉ xóa file khỏi working tree là chưa đủ.

Nếu gặp lỗi `Install the Gemini SDK with: pip install google-genai` hoặc `cannot import name 'genai' from 'google'`, môi trường chưa cài đúng SDK. Package `google-generativeai` cũ không thay thế được package mới. Cài dependency từ repository root:

```powershell
python -m pip install -r requirements.txt
```

Kiểm tra:

```powershell
python -c "from google import genai; print('google-genai OK')"
```

Nếu API trả lỗi model không tồn tại hoặc không được phép sử dụng, kiểm tra `HARNESS_GEN_MODEL` trong `.env`. Có thể bắt đầu bằng `gemini-2.5-flash`, sau đó đổi sang model khác đang khả dụng trong tài khoản/API của nhóm.

## 0.1 Chạy thử bằng demo có sẵn

Repo có hai demo brief:

- `SC-DEMO-01`: khách còn do dự, cần hỏi thêm gia đình, gồm 2 cuộc gọi và promotion conditional.
- `SC-DEMO-02`: case promotion hết hạn, gồm 2 cuộc gọi.

Từ repository root, chạy lint trước:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
```

### Demo dry-run — không cần API key

Lệnh dưới đây chạy hai demo đầu tiên theo thứ tự tên file, không gọi Gemini và không tốn quota:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios_dryrun/ `
  --dry-run `
  --limit 2 `
  --seed 7 `
  --force
```

Sau khi chạy, kiểm tra các output:

```powershell
Get-ChildItem data_gen/fact_packs/SC-DEMO-*.json
Get-ChildItem data_gen/raw/SC-DEMO-*.json
Get-ChildItem data_gen/scenarios_dryrun/SC-DEMO-*.json

python -m data_gen.auto_check `
  --scenarios data_gen/scenarios_dryrun/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/
```

Đọc log terminal để xác nhận mỗi demo có `START`, từng `CALL` và `OK`. Kiểm tra thêm `data_gen/reports/manifest.jsonl` và `data_gen/reports/auto_check_report.csv`. Dry-run chỉ kiểm tra luồng và schema; hội thoại chưa đại diện cho chất lượng Gemini.

### Demo production bằng Gemini

Đảm bảo `.env` có `GEMINI_API_KEY` và model hợp lệ, sau đó chạy riêng vào folder production:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios/ `
  --limit 2 `
  --seed 7 `
  --force
```

Ở production, mỗi call sẽ tạo raw dialogue bằng Gemini rồi assemble scenario. `--force` trong lần demo đầu tiên giúp không reuse raw/scenario cũ từ lần dry-run hoặc prompt version cũ. Không dùng `--dry-run` trong lệnh này.

Kiểm tra production output:

```powershell
Get-ChildItem data_gen/scenarios/SC-DEMO-*.json

python -m data_gen.auto_check `
  --scenarios data_gen/scenarios/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/
```

Nếu hai demo chạy đúng, bỏ `--limit 2` để chạy toàn bộ brief đã pass lint. Không chạy đồng thời nhiều production batch bằng cùng API key; nếu gặp `429`, tăng `GEMINI_MIN_INTERVAL_SECONDS` trong `.env` lên `4.0` hoặc `5.0`.

## 1. Cấu trúc thư mục

Toàn bộ file thuộc workflow đều nằm bên trong `data_gen/`:

```text
data_gen/
├── __init__.py
├── config.py
├── NOTES_DISCOVERY.md
├── README.md
├── explore_data.py
├── lint_briefs.py
├── facts.py
├── llm_client.py
├── gen_dialogue.py
├── assemble_scenario.py
├── auto_check.py
├── run_batch.py
├── slot_keywords.json
├── coverage_matrix/
│   ├── matrix_config.json
│   ├── make_coverage_matrix.py
│   └── README.md
├── prompts/
│   ├── dialogue_v1.txt
│   └── dialogue_v2.txt
├── briefs/
├── fact_packs/
├── raw/
├── scenarios/
├── scenarios_dryrun/
├── reports/
└── tests/
```

### 1.1 Folder dữ liệu đầu vào và kết quả

| Folder              | Nội dung                                                                                                                                            | Ai sử dụng             |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| `briefs/`           | Brief nội bộ do thành viên thiết kế; không phải schema BTC cuối cùng                                                                                | SV1/content            |
| `fact_packs/`       | Fact pack deterministic cho từng cuộc gọi, có source trace                                                                                          | SV2/pipeline, reviewer |
| `raw/`              | Full dialogue gồm `customer` và `agent` do LLM hoặc dry-run sinh ra                                                                                 | reviewer ngôn ngữ      |
| `scenarios/`        | Scenario production sinh bằng LLM API                                                                                                               | agent/evaluation       |
| `scenarios_dryrun/` | Scenario sinh bằng template offline                                                                                                                 | test pipeline/schema   |
| `reports/`          | Inventory, lint report, auto-check, manifest và các báo cáo chạy                                                                                    | cả nhóm                |
| `prompts/`          | Prompt có version cho dialogue generator                                                                                                            | người quản lý prompt   |
| `tests/`            | Unit test cho fact builder, linter và auto-check                                                                                                    | developer/CI           |
| `coverage_matrix/`  | Lập kế hoạch độ phủ persona/ngành/miền/hard case trước khi viết nhiều brief. `layer=A` là hard-case/trap bắt buộc; `layer=B` là baseline diversity. | SV1/content, cả nhóm   |

Không copy dữ liệu BTC vào các folder trên. Pipeline đọc trực tiếp từ `../data` thông qua `BTC_DIR`.

### 1.2 File mã nguồn

| File                      | Chức năng                                                                                                                                           |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config.py`               | Tự load `.env`, khai báo `BTC_DIR`, các output directory, provider/model, prompt version và reference date.                                         |
| `explore_data.py`         | Khảo sát catalog, CRM, promotion, policy và persona; ghi `reports/data_inventory.csv`.                                                              |
| `lint_briefs.py`          | Kiểm tra brief trước khi tạo fact pack: persona, customer, SKU, variant, promotion, policy chunk, call index và forbidden facts.                    |
| `facts.py`                | Tính ngày gọi, gọi mock tools, đọc CRM/catalog/policy và tạo fact pack. Đây là nguồn factual duy nhất được đưa vào prompt.                          |
| `llm_client.py`           | Interface `complete()`. Production gọi Gemini API qua `google-genai`; dry-run dùng template deterministic. Có retry cho lỗi API.                    |
| `gen_dialogue.py`         | Đọc brief + fact pack + persona + previous-call summary, gọi LLM, parse full dialogue và ghi vào `raw/`.                                            |
| `assemble_scenario.py`    | Mapping duy nhất từ brief/raw/fact pack sang BTC scenario. Metadata grading được tạo tại đây bằng code; `customer_id` được giữ lại để trace về CRM. |
| `auto_check.py`           | Kiểm tra numeric consistency, PII, internal policy leakage, re-ask heuristic và đối chiếu ground truth với mock tools.                              |
| `run_batch.py`            | Chạy toàn bộ pipeline theo batch, hỗ trợ `--dry-run`, `--limit`, `--force`, skip output hợp lệ và ghi manifest.                                     |
| `slot_keywords.json`      | Từ khoá phục vụ heuristic phát hiện agent hỏi lại slot đã biết.                                                                                     |
| `prompts/dialogue_v2.txt` | Prompt production hiện tại; bao phủ factual grounding, multi-call memory, promotion/policy traps, PII và JSON output. |
| `prompts/dialogue_v1.txt` | Prompt legacy để reproduce raw cũ; không dùng cho run mới. |
| `NOTES_DISCOVERY.md`      | Kết quả khảo sát BTC data, schema, mock tools, policy và các mâu thuẫn đã phát hiện.                                                                |

## 2. Brief cần viết như thế nào?

Mỗi scenario có một file JSON trong `data_gen/briefs/`:

```json
{
	"brief_id": "SC-DEMO-01",
	"persona_id": "<persona có trong data/simulator/personas.json>",
	"customer_id": "<customer_id có trong CRM>",
	"channel": "hotline",
	"hard_case_tags": ["multi_call"],
	"calls": [
		{
			"call_index": 1,
			"days_later": 0,
			"customer_goal": "...",
			"products": [
				{
					"sku": "<SKU từ catalog>",
					"variant_id": "<variant_sku nếu có>",
					"qty": 1
				}
			],
			"promo_codes_in_play": ["<promo_code từ promotions.json>"],
			"policy_chunk_ids": ["<chunk ID từ policy/*.md>"],
			"facts_to_establish": {
				"room_area_m2": 25,
				"blocker": "can hoi nguoi nha"
			},
			"expected_outcome": "hen_goi_lai",
			"story_hint": "Hướng dẫn ngắn cho cuộc hội thoại."
		}
	]
}
```

`facts_to_establish` chỉ chứa điều khách chủ động nói, ví dụ diện tích phòng, ngân sách hoặc lý do chưa mua. Không nhập thủ công `price_vnd`, `final_price_vnd`, `list_price_vnd`, kết quả promotion, inventory hoặc policy content vào brief.

Trước khi commit brief, cần kiểm tra:

1. Persona, customer, SKU, variant, promotion và policy chunk đều tồn tại trong BTC data.
2. `call_index` liên tục từ 1.
3. `days_later` không âm.
4. Các call sau mô tả rõ thông tin cần carry-over và outcome.
5. Brief không chứa phone, địa chỉ hoặc PII không cần thiết.

## 3. Quy trình generate data

### Bước 0 — Discovery và phân công

Đọc [NOTES_DISCOVERY.md](NOTES_DISCOVERY.md), `data/README.md`, `data/schemas/scenario_format.md`, simulator persona và mock tools.

SV1 phụ trách persona, goal, hard case, story hint và coverage. SV2 phụ trách fact builder, LLM adapter, validator và manifest. Cả hai cùng review ngôn ngữ và factual correctness.

### Bước 1 — Khảo sát BTC data

Chạy từ repository root:

```powershell
python -m data_gen.explore_data
```

Kết quả là `data_gen/reports/data_inventory.csv`. Dùng file này để chọn khách đặc biệt, promotion active/expired/not-started, policy current/old/internal và đủ 12 persona.

### Bước 2 — Tạo và lint brief

Đặt brief vào `data_gen/briefs/`, sau đó chạy:

```powershell
python -m data_gen.lint_briefs
```

Hoặc chỉ định folder khác:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
```

Kết quả ghi vào `data_gen/reports/lint_report.txt`. Nếu lint fail, sửa brief; không sửa fact pack hoặc scenario bằng tay để làm cho test pass.

Nếu cần tạo nhiều scenario, hãy lập coverage matrix trước:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix generate
python -m data_gen.coverage_matrix.make_coverage_matrix report
```

Xem hướng dẫn chi tiết tại [coverage_matrix/README.md](coverage_matrix/README.md). Matrix phải đạt coverage mục tiêu trước khi nhóm mở rộng batch.

### Bước 3 — Build fact pack

Tạo fact pack cho từng call:

```powershell
python -m data_gen.facts `
  --brief data_gen/briefs/SC-DEMO-01.json `
  --call 1
```

Fact builder sẽ tính `call_date`, resolve CRM customer, gọi catalog/pricing/inventory mock tools, lấy promotion states, đọc policy chunk theo ID, gắn source cho factual value và loại PII không cần thiết khỏi prompt-facing CRM profile.

Fact pack nằm ở `data_gen/fact_packs/<brief_id>_c<call_index>.json`.

### Bước 4 — Generate full dialogue

#### Dry-run, không tốn API

Dry-run dùng template deterministic, mục tiêu là kiểm tra pipeline, schema và assembler:

```powershell
python -m data_gen.gen_dialogue `
  --brief data_gen/briefs/SC-DEMO-01.json `
  --call 1 `
  --dry-run `
  --seed 7
```

Dry-run raw dialogue được ghi vào `data_gen/raw/`, còn scenario cuối phải ghi vào `data_gen/scenarios_dryrun/`.

#### LLM API

Production hiện dùng Gemini API:

```powershell
# Đặt GEMINI_API_KEY và HARNESS_GEN_MODEL trong .env ở repository root

python -m data_gen.gen_dialogue `
  --brief data_gen/briefs/SC-DEMO-01.json `
  --call 1 `
  --seed 7
```

LLM nhận persona, goal, fact pack, CRM profile đã lọc, các slot không được hỏi lại và summary của call trước. Summary call trước được tạo từ structured data bằng code, không nhờ LLM tự tóm tắt.

LLM phải chỉ trả về mảng dialogue gồm 8–16 lượt, mỗi lượt có `role` là `customer` hoặc `agent` và `text`. LLM không được tự đổi grading metadata hoặc factual ground truth.

### Bước 5 — Assemble scenario BTC

```powershell
python -m data_gen.assemble_scenario `
  --brief data_gen/briefs/SC-DEMO-01.json `
  --dry-run
```

`assemble_scenario.py` lấy customer turns từ raw dialogue và tạo bằng code `must_not_ask`, `must_carry_over`, `success_if`, `ground_truth_facts`, ngày gọi, outcome và channel. Không copy agent turns vào scenario BTC; agent turns chỉ nằm trong `raw/` để reviewer đọc.

### Bước 6 — Chạy batch

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios_dryrun/ `
  --dry-run `
  --seed 7
```

Các option chính:

| Option      | Chức năng                                |
| ----------- | ---------------------------------------- |
| `--briefs`  | Folder chứa brief                        |
| `--out`     | Folder output scenario                   |
| `--dry-run` | Không gọi API, output vào folder dry-run |
| `--seed`    | Seed ghi vào raw/manifest                |
| `--limit N` | Chỉ chạy N brief đầu                     |
| `--force`   | Sinh lại kể cả output đã tồn tại         |

Khi chạy batch, terminal sẽ log từng brief và từng call với các trạng thái `START`, `CALL`, `OK`, `SKIP` hoặc `FAIL`. Log chỉ chứa brief ID/call index và đường dẫn output, không chứa API key hay PII.

Batch idempotent: output hợp lệ sẽ được skip nếu không dùng `--force`. Raw dialogue chỉ được reuse khi cùng mode (`dry-run` hoặc Gemini production), seed và model/provider; raw dry-run sẽ tự động được sinh lại khi chạy production. Một brief fail không làm dừng các brief còn lại. Manifest nằm ở `data_gen/reports/manifest.jsonl`.

Để giảm rate limit, mỗi request Gemini có khoảng nghỉ tối thiểu theo `GEMINI_MIN_INTERVAL_SECONDS` (mặc định `2.0` giây). Khi gặp lỗi tạm thời/rate limit, pipeline retry tối đa 3 lần với exponential backoff và jitter; nếu response có `Retry-After` thì ưu tiên thời gian đó. Có thể tăng lên `4.0` hoặc `5.0` nếu quota/provider vẫn trả `429`:

```dotenv
GEMINI_MIN_INTERVAL_SECONDS=4.0
```

### Bước 7 — Auto-check và review thủ công

```powershell
python -m data_gen.auto_check `
  --scenarios data_gen/scenarios_dryrun/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/
```

Report nằm ở `data_gen/reports/auto_check_report.csv`. Cần xử lý hard failure trước khi freeze. `E8_REASK_REVIEW` chỉ là cảnh báo heuristic, cần review bằng người.

Review tối thiểu: giá/ngày/tồn kho khớp fact pack; promotion expired/not-started/ineligible không bị nói như active; call sau không hỏi lại slot đã biết; không leak policy nội bộ, giá nhập, PII; persona và tiếng Việt tự nhiên; scenario đúng `data/schemas/scenario_format.md`.

### Bước 8 — Freeze và bàn giao

Sau khi lint, fact check, auto-check và manual review đạt:

1. chuyển bản được duyệt vào `data_gen/scenarios/` nếu là production API;
2. lưu raw dialogue, fact pack và manifest cùng prompt version;
3. ghi lại model, seed, timestamp, provider và commit code;
4. chỉ sau đó mới đưa scenario vào `langgraph_agent` hoặc evaluation.

## 3.1 Quy trình nhóm để sinh full bộ data

`full bộ data` nghĩa là toàn bộ brief hợp lệ trong `data_gen/briefs/` đã được sinh thành scenario, có fact pack, raw dialogue, manifest và báo cáo auto-check tương ứng. Hai file `SC-DEMO-01` và `SC-DEMO-02` chỉ là mẫu kiểm tra pipeline, không phải toàn bộ dataset.

### Phân công đề xuất

| Vai trò             | Việc chính                                                           | Artifact phải bàn giao                     |
| ------------------- | -------------------------------------------------------------------- | ------------------------------------------ |
| Coverage owner      | Sinh matrix, cân bằng persona/ngành/miền/layer, phân owner           | `reports/coverage_matrix.csv`              |
| Brief owners        | Mỗi người chỉ sửa các row có `owner` của mình, viết brief từ BTC IDs | các file JSON trong `briefs/`              |
| Fact/pipeline owner | Kiểm tra lint, fact pack, cấu hình model/provider và chạy batch      | `fact_packs/`, `raw/`, `manifest.jsonl`    |
| Reviewers           | Review factual correctness, ngôn ngữ, carry-over, PII và hard cases  | `auto_check_report.csv`, trạng thái matrix |

Không để hai thành viên cùng sửa một brief. Nếu cần đổi persona, hard case hoặc customer của slot, đánh dấu slot cũ là `dropped`, ghi lý do ở `notes`, rồi tạo slot mới; không âm thầm đổi mục tiêu coverage.

### Giai đoạn A — Chuẩn bị một lần cho cả nhóm

Chạy từ repository root:

```powershell
python -m data_gen.explore_data
python -m data_gen.coverage_matrix.make_coverage_matrix generate
python -m data_gen.coverage_matrix.make_coverage_matrix report
```

Coverage owner commit matrix sau khi review. Thành viên khác không chạy lại `generate` lên file đã phân công vì lệnh này tạo lại các row. Chỉ chạy `report` để kiểm tra quota hiện tại.

Kiểm tra môi trường:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
pytest -q data_gen/tests
```

Nếu chỉ muốn tạo khung cho các slot mới:

```powershell
python -m data_gen.coverage_matrix.make_coverage_matrix stubs `
  --matrix data_gen/reports/coverage_matrix.csv `
  --out data_gen/briefs/
```

Không chạy `stubs` để ghi đè brief đã viết. Các giá trị `TODO` phải được thay bằng ID và outcome thật lấy từ BTC trước khi commit.

### Giai đoạn B — Mỗi thành viên viết brief

1. Mở `reports/coverage_matrix.csv` và lọc theo `owner`.
2. Với từng slot, điền một file `<slot_id>.json` trong `briefs/`.
3. Chỉ dùng persona, customer, SKU, variant, promotion và policy chunk có thật trong BTC.
4. Không điền giá, kết quả promotion, tồn kho hoặc policy content vào brief.
5. Giữ đúng `layer`: `A` phải thể hiện hard case tương ứng; `B` là scenario nền.
6. Nếu `customer_id` trong matrix đã có giá trị, phải dùng đúng ID đó. Nếu để trống, chọn một customer hợp lệ từ CRM phù hợp với story và điền vào brief; không tự bịa ID và không commit `TODO`.
7. Chạy lint trước khi tạo pull request:

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
```

Commit brief theo nhóm nhỏ, ví dụ `briefs: add SV1 slots SC-001 to SC-010`. Reviewer chỉ merge khi lint pass và nội dung brief khớp coverage row.

### Giai đoạn C — Dry-run toàn bộ trước khi tốn API

Sau khi tất cả brief đã được viết và lint pass:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios_dryrun/ `
  --dry-run `
  --seed 7

python -m data_gen.auto_check `
  --scenarios data_gen/scenarios_dryrun/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/
```

Dry-run dùng template offline nên không đại diện cho chất lượng ngôn ngữ của LLM. Mục tiêu của bước này là phát hiện brief sai, fact pack lỗi, output sai cấu trúc, sai giá/ngày và lỗi privacy trước khi gọi API thật.

Kiểm tra:

- `reports/manifest.jsonl` không có `failed`;
- `reports/auto_check_report.csv` không có hard failure;
- cảnh báo `E8_REASK_REVIEW` đã được người review đọc;
- số file trong `scenarios_dryrun/` khớp số brief cần generate;
- coverage report vẫn đạt quota.

### Giai đoạn D — Cấu hình LLM API và sinh production data

Pipeline hiện tại gọi Gemini trong `llm_client.py` bằng SDK `google-genai`. Mỗi thành viên không commit API key; đặt key trong `.env` theo mục 0. Có thể tạo key từ Google AI Studio.

```powershell
Copy-Item .env.example .env
# Sau đó sửa GEMINI_API_KEY trong .env
```

Chạy thử một vài brief trước:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios/ `
  --limit 2 `
  --seed 7
```

Sau khi review thử đạt, chạy toàn bộ:

```powershell
python -m data_gen.run_batch `
  --briefs data_gen/briefs/ `
  --out data_gen/scenarios/ `
  --seed 7
```

Batch có tính idempotent: output đã tồn tại sẽ được skip. Chỉ dùng `--force` khi đã thống nhất regenerate toàn bộ hoặc một batch cụ thể; khi regenerate phải giữ lại seed, model, prompt version và ghi chú lý do trong commit/manifest.

Nếu nhóm dùng provider khác Gemini, không được chỉ đổi tên biến model. Cần bổ sung adapter trong `llm_client.py`, cơ chế đọc API key riêng, retry và kiểm tra output JSON; sau đó cập nhật README, test adapter và manifest để ghi provider/model chính xác. Cho tới khi adapter được merge, production run chính thức chỉ hỗ trợ Gemini.

### Giai đoạn E — Auto-check, review và freeze

Sau production run:

```powershell
python -m data_gen.auto_check `
  --scenarios data_gen/scenarios/ `
  --briefs data_gen/briefs/ `
  --fact-packs data_gen/fact_packs/

python -m data_gen.coverage_matrix.make_coverage_matrix report
pytest -q data_gen/tests
```

Mỗi reviewer cần kiểm tra ít nhất một mẫu ở mỗi nhóm `layer`, hard case, persona và provider/model run. Đối với mỗi scenario, kiểm tra:

- customer và channel đúng brief;
- giá, promotion, inventory, ngày và policy khớp fact pack;
- promotion expired/not-started/ineligible không bị nói như đang active;
- call sau giữ đúng thông tin từ call trước và không hỏi lại slot đã biết;
- không lộ phone, địa chỉ, CCCD, email hoặc internal policy;
- customer turns tự nhiên, agent không hallucinate và outcome phù hợp `expected_outcome`;
- không còn `TODO`, `failed` hoặc hard failure.

Chỉ scenario đã review mới được coi là `validated`. Không sửa trực tiếp scenario để che lỗi; sửa brief/prompt/code, regenerate artifact liên quan và chạy lại các bước kiểm tra.

### Giai đoạn F — Bàn giao dataset

Một dataset được xem là sẵn sàng khi có đủ:

1. `reports/coverage_matrix.csv` đạt quota và các row đã có owner/status rõ ràng;
2. tất cả brief cần thiết pass lint;
3. fact pack và raw dialogue tồn tại cho từng call;
4. scenario production nằm trong `scenarios/`, scenario dry-run nằm riêng trong `scenarios_dryrun/`;
5. `auto_check_report.csv` không có hard failure;
6. `manifest.jsonl` ghi `brief_id`, provider/model, prompt version, seed, timestamp và status;
7. `pytest -q data_gen/tests` pass;
8. không có thay đổi ngoài ý muốn trong `data/` và không có API key/PII trong git diff.

Các artifact cần chia sẻ/commit theo chính sách của nhóm:

- nên commit: brief, coverage matrix, prompt, code, README, report không chứa PII;
- chỉ commit `fact_packs/`, `raw/`, `scenarios/` nếu repo cho phép lưu generated data;
- không commit API key, log request, phone/address chưa mask hoặc file tạm;
- nếu dataset lớn, lưu artifact ở nơi được nhóm thống nhất và commit manifest/hash thay vì tự ý đẩy lên repo.

### Lệnh kiểm tra nhanh trước khi báo hoàn tất

```powershell
python -m data_gen.lint_briefs data_gen/briefs/
python -m data_gen.coverage_matrix.make_coverage_matrix report
python -m data_gen.run_batch --briefs data_gen/briefs/ --out data_gen/scenarios_dryrun/ --dry-run --seed 7
python -m data_gen.auto_check --scenarios data_gen/scenarios_dryrun/ --briefs data_gen/briefs/ --fact-packs data_gen/fact_packs/
pytest -q data_gen/tests
```

Nếu một lệnh fail, dừng freeze và ghi lỗi vào issue/PR tương ứng; không chuyển scenario lỗi sang `scenarios/` hoặc evaluation.

## 4. Kiểm thử và giới hạn

Chạy:

```powershell
pytest -q data_gen/tests
```

Test hiện có kiểm tra fact pack với mock tools cho promotion conditional, promotion expired và inventory thay đổi theo ngày; kiểm tra linter và các nhóm lỗi auto-check.

BTC checkout hiện thiếu `data/eval/validate_scenarios.py`, dù BTC README có tham chiếu file này. Vì vậy `auto_check` ghi warning `BTC_VALIDATOR_MISSING`; warning này không có nghĩa official BTC validator đã pass. Khi BTC bổ sung file, cần chạy thêm validator chính thức trên `data_gen/scenarios/`.

## 5. Giải thích thuật ngữ

| Thuật ngữ            | Giải thích                                                                                                                                             |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `BTC`                | Ban tổ chức hoặc bộ dữ liệu/định dạng chuẩn mà bài yêu cầu.                                                                                            |
| `BTC_DIR`            | Thư mục gốc chứa dữ liệu BTC; mặc định là `data/`. Đây là thư mục chỉ đọc.                                                                             |
| `brief`              | Bản mô tả nội bộ của một scenario: khách hàng nào, mục tiêu gì, sản phẩm nào và các cuộc gọi diễn ra như thế nào. Brief chưa phải output cuối của BTC. |
| `fact pack`          | Gói dữ kiện được code tạo cho một cuộc gọi từ catalog, CRM, promotion, inventory, policy và mock tools. Đây là nguồn sự thật để LLM viết hội thoại.    |
| `ground truth`       | Dữ kiện đúng dùng để đối chiếu kết quả agent, ví dụ giá chính xác, trạng thái tồn kho hoặc ngày restock.                                               |
| `ground_truth_facts` | Các factual value trong scenario dùng để kiểm tra agent có nói đúng hay không. Field này phải do code tạo.                                             |
| `customer turns`     | Các lượt lời của khách hàng. Đây là phần input deterministic quan trọng để BTC chấm agent.                                                             |
| `agent turns`        | Các lượt lời của agent. Trong pipeline, chúng được lưu trong `raw/` để review, không dùng làm ground truth bắt buộc.                                   |
| `raw dialogue`       | Bản hội thoại thô gồm cả `customer` và `agent` trước khi assemble thành scenario BTC.                                                                  |
| `scenario`           | File JSON cuối cùng theo schema BTC, chứa metadata, các cuộc gọi, customer turns và điều kiện đánh giá.                                                |
| `multi-call`         | Scenario có nhiều cuộc gọi của cùng một khách hàng, thường dùng để kiểm tra memory và carry-over.                                                      |
| `call index`         | Số thứ tự cuộc gọi: `1`, `2`, `3`.                                                                                                                     |
| `call date`          | Ngày thực tế của một cuộc gọi. Giá, promotion và inventory phải được tính theo ngày này.                                                               |
| `days later`         | Số ngày kể từ cuộc gọi trước để suy ra `call_date`.                                                                                                    |
| `carry-over`         | Thông tin cần được giữ lại và sử dụng ở cuộc gọi sau, ví dụ sản phẩm đã tư vấn hoặc vấn đề khách còn do dự.                                            |
| `must_carry_over`    | Danh sách slot mà agent bắt buộc phải nhớ và dùng đúng ở call hiện tại.                                                                                |
| `must_not_ask`       | Danh sách slot agent không được hỏi mở lại vì đã biết từ CRM hoặc cuộc gọi trước.                                                                      |
| `slot`               | Một đơn vị thông tin có tên, ví dụ `product_advised`, `budget_vnd`, `room_area_m2` hoặc `address`.                                                     |
| `persona`            | Kiểu hành vi và phong cách giao tiếp của khách hàng, ví dụ khách so giá hoặc khách thiếu kiên nhẫn.                                                    |
| `hard case`          | Ca kiểm thử khó, ví dụ promotion hết hạn, ASR lỗi, shared phone hoặc policy cũ.                                                                        |
| `promotion`          | Chương trình khuyến mãi. Promotion có thể active, expired, not started hoặc ineligible theo điều kiện.                                                 |
| `inventory`          | Trạng thái tồn kho của sản phẩm/variant tại một ngày cụ thể.                                                                                           |
| `CRM`                | Customer Relationship Management; dữ liệu hồ sơ, định danh, lịch sử đơn hàng và các phiên trước của khách.                                             |
| `PII`                | Personally Identifiable Information; thông tin có thể nhận diện một cá nhân như số điện thoại, địa chỉ, email hoặc CCCD.                               |
| `mask PII`           | Che hoặc thay thế PII bằng giá trị an toàn trước khi ghi log, gửi prompt hoặc xuất report.                                                             |
| `policy chunk`       | Một đoạn chính sách có mã định danh, ví dụ `[DT-01]` hoặc `[KM-05]`.                                                                                   |
| `current policy`     | Chính sách đang có hiệu lực tại thời điểm gọi.                                                                                                         |
| `old policy`         | Chính sách cũ đã hết hiệu lực, không được dùng thay cho chính sách hiện tại.                                                                           |
| `internal policy`    | Tài liệu nội bộ như giá nhập hoặc KPI; không được tiết lộ cho khách hàng.                                                                              |
| `mock tool`          | Hàm mô phỏng công cụ nghiệp vụ của BTC, dùng để tra giá, tồn kho, CRM, tạo đơn hoặc callback.                                                          |
| `fact source`        | Nguồn chứng minh một factual value, ví dụ `pricing_get_quote` hoặc `catalog/products.json`.                                                            |
| `LLM`                | Large Language Model; mô hình ngôn ngữ dùng để sinh câu thoại.                                                                                         |
| `LLM API`            | API cho phép chương trình gửi prompt đến LLM và nhận kết quả tự động.                                                                                  |
| `provider`           | Nhà cung cấp LLM API; pipeline hiện tại dùng Google Gemini.                                                                                            |
| `prompt`             | Nội dung hướng dẫn và dữ liệu đầu vào gửi cho LLM.                                                                                                     |
| `prompt version`     | Phiên bản prompt, ví dụ `dialogue_v1`, dùng để tái lập và so sánh các lần sinh dữ liệu.                                                                |
| `structured output`  | Kết quả LLM theo format có cấu trúc, trong pipeline là JSON dialogue.                                                                                  |
| `dry-run`            | Chế độ chạy thử không gọi API thật và không tốn chi phí; pipeline dùng template deterministic.                                                         |
| `production run`     | Chế độ chạy thật bằng LLM API để tạo dữ liệu chất lượng dùng cho development/evaluation.                                                               |
| `deterministic`      | Cùng input và cấu hình cho ra kết quả ổn định hoặc có thể tái lập.                                                                                     |
| `seed`               | Giá trị dùng để tái lập một lần sinh dữ liệu hoặc ghi nhận cấu hình chạy.                                                                              |
| `temperature`        | Mức độ ngẫu nhiên khi LLM sinh output; giá trị thấp thường phù hợp với task có yêu cầu factual.                                                        |
| `retry`              | Cơ chế gọi lại khi API lỗi, timeout hoặc trả về JSON không hợp lệ.                                                                                     |
| `parse`              | Đọc và chuyển chuỗi JSON LLM trả về thành object để chương trình xử lý.                                                                                |
| `assemble`           | Bước ghép brief, fact pack và dialogue thành scenario BTC cuối cùng.                                                                                   |
| `validator`          | Chương trình kiểm tra scenario có đúng schema và nghiệp vụ hay không.                                                                                  |
| `auto-check`         | Nhóm kiểm tra tự động bổ sung như sai giá, leak PII, leak policy và hỏi lại slot đã biết.                                                              |
| `heuristic`          | Quy tắc kiểm tra gần đúng, thường dựa trên regex/từ khoá; có thể cần review thủ công.                                                                  |
| `manifest`           | File nhật ký các lần chạy, thường chứa brief ID, model, seed, timestamp và status.                                                                     |
| `idempotent`         | Chạy lại cùng pipeline không tạo output trùng hoặc thay đổi output hợp lệ nếu không dùng `--force`.                                                    |
| `quarantine`         | Nơi tạm giữ scenario lỗi hoặc chưa được duyệt, không đưa vào batch chính thức.                                                                         |
| `freeze`             | Trạng thái scenario đã qua kiểm tra và không được sửa thủ công thêm.                                                                                   |
