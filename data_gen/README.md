# Pipeline sinh scenario cho Call-Center E-commerce

`data_gen` là pipeline độc lập để tạo scenario hội thoại nhiều cuộc gọi cho cùng một khách hàng, theo format BTC. Pipeline chỉ đọc dữ liệu trong `data/` và không phụ thuộc vào `langgraph_agent/`.

Nguyên tắc quan trọng:

- `data/` là BTC_DIR, chỉ đọc; không sửa, thêm hoặc xoá file trong đó.
- Giá, khuyến mãi, tồn kho, CRM, COD và các factual value phải đến từ BTC data hoặc `data/eval/mock_tools.py`.
- LLM chỉ sinh lời thoại. LLM không sinh `ground_truth_facts`, `success_if`, `must_not_ask` hoặc `must_carry_over`.
- Full dialogue được lưu ở `raw/` để review. Scenario BTC chính thức chỉ chứa các field theo `scenario_format.md`.
- Không ghi số điện thoại, địa chỉ hoặc PII chưa mask vào prompt, log, manifest hay report. `customer_phone` chỉ xuất hiện trong scenario nếu schema BTC bắt buộc.

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
│   └── dialogue_v1.txt
├── briefs/
├── fact_packs/
├── raw/
├── scenarios/
├── scenarios_dryrun/
├── reports/
└── tests/
```

### 1.1 Folder dữ liệu đầu vào và kết quả

| Folder | Nội dung | Ai sử dụng |
|---|---|---|
| `briefs/` | Brief nội bộ do thành viên thiết kế; không phải schema BTC cuối cùng | SV1/content |
| `fact_packs/` | Fact pack deterministic cho từng cuộc gọi, có source trace | SV2/pipeline, reviewer |
| `raw/` | Full dialogue gồm `customer` và `agent` do LLM hoặc dry-run sinh ra | reviewer ngôn ngữ |
| `scenarios/` | Scenario production sinh bằng LLM API | agent/evaluation |
| `scenarios_dryrun/` | Scenario sinh bằng template offline | test pipeline/schema |
| `reports/` | Inventory, lint report, auto-check, manifest và các báo cáo chạy | cả nhóm |
| `prompts/` | Prompt có version cho dialogue generator | người quản lý prompt |
| `tests/` | Unit test cho fact builder, linter và auto-check | developer/CI |
| `coverage_matrix/` | Lập kế hoạch độ phủ persona/ngành/miền/hard case trước khi viết nhiều brief | SV1/content, cả nhóm |

Không copy dữ liệu BTC vào các folder trên. Pipeline đọc trực tiếp từ `../data` thông qua `BTC_DIR`.

### 1.2 File mã nguồn

| File | Chức năng |
|---|---|
| `config.py` | Khai báo `BTC_DIR`, các output directory, model, prompt version và reference date. Có thể đổi `BTC_DIR`/model bằng environment variable. |
| `explore_data.py` | Khảo sát catalog, CRM, promotion, policy và persona; ghi `reports/data_inventory.csv`. |
| `lint_briefs.py` | Kiểm tra brief trước khi tạo fact pack: persona, customer, SKU, variant, promotion, policy chunk, call index và forbidden facts. |
| `facts.py` | Tính ngày gọi, gọi mock tools, đọc CRM/catalog/policy và tạo fact pack. Đây là nguồn factual duy nhất được đưa vào prompt. |
| `llm_client.py` | Interface `complete()`. Production gọi Anthropic API; dry-run dùng template deterministic. Có retry cho lỗi API. |
| `gen_dialogue.py` | Đọc brief + fact pack + persona + previous-call summary, gọi LLM, parse full dialogue và ghi vào `raw/`. |
| `assemble_scenario.py` | Mapping duy nhất từ brief/raw/fact pack sang BTC scenario. Metadata grading được tạo tại đây bằng code. |
| `auto_check.py` | Kiểm tra numeric consistency, PII, internal policy leakage, re-ask heuristic và đối chiếu ground truth với mock tools. |
| `run_batch.py` | Chạy toàn bộ pipeline theo batch, hỗ trợ `--dry-run`, `--limit`, `--force`, skip output hợp lệ và ghi manifest. |
| `slot_keywords.json` | Từ khoá phục vụ heuristic phát hiện agent hỏi lại slot đã biết. |
| `prompts/dialogue_v1.txt` | Prompt version `dialogue_v1`; thay đổi prompt phải cập nhật version trong `config.py`. |
| `NOTES_DISCOVERY.md` | Kết quả khảo sát BTC data, schema, mock tools, policy và các mâu thuẫn đã phát hiện. |

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
        {"sku": "<SKU từ catalog>", "variant_id": "<variant_sku nếu có>", "qty": 1}
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

Production hiện dùng Anthropic API:

```powershell
$env:ANTHROPIC_API_KEY = "..."
$env:HARNESS_GEN_MODEL = "claude-sonnet-4-6"

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

| Option | Chức năng |
|---|---|
| `--briefs` | Folder chứa brief |
| `--out` | Folder output scenario |
| `--dry-run` | Không gọi API, output vào folder dry-run |
| `--seed` | Seed ghi vào raw/manifest |
| `--limit N` | Chỉ chạy N brief đầu |
| `--force` | Sinh lại kể cả output đã tồn tại |

Batch idempotent: output hợp lệ sẽ được skip nếu không dùng `--force`. Một brief fail không làm dừng các brief còn lại. Manifest nằm ở `data_gen/reports/manifest.jsonl`.

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

## 4. Kiểm thử và giới hạn

Chạy:

```powershell
pytest -q data_gen/tests
```

Test hiện có kiểm tra fact pack với mock tools cho promotion conditional, promotion expired và inventory thay đổi theo ngày; kiểm tra linter và các nhóm lỗi auto-check.

BTC checkout hiện thiếu `data/eval/validate_scenarios.py`, dù BTC README có tham chiếu file này. Vì vậy `auto_check` ghi warning `BTC_VALIDATOR_MISSING`; warning này không có nghĩa official BTC validator đã pass. Khi BTC bổ sung file, cần chạy thêm validator chính thức trên `data_gen/scenarios/`.

## 5. Có nên đưa script vào `src/` không?

### Khuyến nghị hiện tại: không cần

Giữ cấu trúc hiện tại là hợp lý:

```text
data_gen/
├── config.py
├── facts.py
├── gen_dialogue.py
└── ...
```

Lý do:

- `data_gen` đã là Python package có `__init__.py`;
- các lệnh chạy rõ ràng bằng `python -m data_gen.<module>`;
- import tương đối như `from .config import ...` hoạt động trực tiếp;
- người mới dễ tìm CLI và đọc luồng pipeline;
- đây là application/research pipeline, chưa phải package cần publish lên PyPI.

Nếu chuyển sang `data_gen/src/`, Python path và packaging sẽ phức tạp hơn, trong khi chưa có lợi ích đáng kể.

### Khi nào nên dùng `src/`?

Chỉ nên cân nhắc `src/` nếu code được đóng gói thành thư viện độc lập, có `pyproject.toml`, CI build wheel, nhiều package con hoặc cần ngăn import nhầm source khi chưa cài package.

Nếu pipeline lớn hơn, phương án trung gian tốt hơn là:

```text
data_gen/
├── cli/
├── core/
│   ├── facts.py
│   ├── assemble.py
│   └── validation.py
├── providers/
│   ├── anthropic.py
│   └── ...
├── prompts/
└── tests/
```

Hiện tại chưa nên refactor sang cấu trúc này; flat package ít rủi ro và phù hợp với quy mô hiện tại.

## 6. Giải thích thuật ngữ

| Thuật ngữ | Giải thích |
|---|---|
| `BTC` | Ban tổ chức hoặc bộ dữ liệu/định dạng chuẩn mà bài yêu cầu. |
| `BTC_DIR` | Thư mục gốc chứa dữ liệu BTC; mặc định là `data/`. Đây là thư mục chỉ đọc. |
| `brief` | Bản mô tả nội bộ của một scenario: khách hàng nào, mục tiêu gì, sản phẩm nào và các cuộc gọi diễn ra như thế nào. Brief chưa phải output cuối của BTC. |
| `fact pack` | Gói dữ kiện được code tạo cho một cuộc gọi từ catalog, CRM, promotion, inventory, policy và mock tools. Đây là nguồn sự thật để LLM viết hội thoại. |
| `ground truth` | Dữ kiện đúng dùng để đối chiếu kết quả agent, ví dụ giá chính xác, trạng thái tồn kho hoặc ngày restock. |
| `ground_truth_facts` | Các factual value trong scenario dùng để kiểm tra agent có nói đúng hay không. Field này phải do code tạo. |
| `customer turns` | Các lượt lời của khách hàng. Đây là phần input deterministic quan trọng để BTC chấm agent. |
| `agent turns` | Các lượt lời của agent. Trong pipeline, chúng được lưu trong `raw/` để review, không dùng làm ground truth bắt buộc. |
| `raw dialogue` | Bản hội thoại thô gồm cả `customer` và `agent` trước khi assemble thành scenario BTC. |
| `scenario` | File JSON cuối cùng theo schema BTC, chứa metadata, các cuộc gọi, customer turns và điều kiện đánh giá. |
| `multi-call` | Scenario có nhiều cuộc gọi của cùng một khách hàng, thường dùng để kiểm tra memory và carry-over. |
| `call index` | Số thứ tự cuộc gọi: `1`, `2`, `3`. |
| `call date` | Ngày thực tế của một cuộc gọi. Giá, promotion và inventory phải được tính theo ngày này. |
| `days later` | Số ngày kể từ cuộc gọi trước để suy ra `call_date`. |
| `carry-over` | Thông tin cần được giữ lại và sử dụng ở cuộc gọi sau, ví dụ sản phẩm đã tư vấn hoặc vấn đề khách còn do dự. |
| `must_carry_over` | Danh sách slot mà agent bắt buộc phải nhớ và dùng đúng ở call hiện tại. |
| `must_not_ask` | Danh sách slot agent không được hỏi mở lại vì đã biết từ CRM hoặc cuộc gọi trước. |
| `slot` | Một đơn vị thông tin có tên, ví dụ `product_advised`, `budget_vnd`, `room_area_m2` hoặc `address`. |
| `persona` | Kiểu hành vi và phong cách giao tiếp của khách hàng, ví dụ khách so giá hoặc khách thiếu kiên nhẫn. |
| `hard case` | Ca kiểm thử khó, ví dụ promotion hết hạn, ASR lỗi, shared phone hoặc policy cũ. |
| `promotion` | Chương trình khuyến mãi. Promotion có thể active, expired, not started hoặc ineligible theo điều kiện. |
| `inventory` | Trạng thái tồn kho của sản phẩm/variant tại một ngày cụ thể. |
| `CRM` | Customer Relationship Management; dữ liệu hồ sơ, định danh, lịch sử đơn hàng và các phiên trước của khách. |
| `PII` | Personally Identifiable Information; thông tin có thể nhận diện một cá nhân như số điện thoại, địa chỉ, email hoặc CCCD. |
| `mask PII` | Che hoặc thay thế PII bằng giá trị an toàn trước khi ghi log, gửi prompt hoặc xuất report. |
| `policy chunk` | Một đoạn chính sách có mã định danh, ví dụ `[DT-01]` hoặc `[KM-05]`. |
| `current policy` | Chính sách đang có hiệu lực tại thời điểm gọi. |
| `old policy` | Chính sách cũ đã hết hiệu lực, không được dùng thay cho chính sách hiện tại. |
| `internal policy` | Tài liệu nội bộ như giá nhập hoặc KPI; không được tiết lộ cho khách hàng. |
| `mock tool` | Hàm mô phỏng công cụ nghiệp vụ của BTC, dùng để tra giá, tồn kho, CRM, tạo đơn hoặc callback. |
| `fact source` | Nguồn chứng minh một factual value, ví dụ `pricing_get_quote` hoặc `catalog/products.json`. |
| `LLM` | Large Language Model; mô hình ngôn ngữ dùng để sinh câu thoại. |
| `LLM API` | API cho phép chương trình gửi prompt đến LLM và nhận kết quả tự động. |
| `provider` | Nhà cung cấp LLM API, ví dụ Anthropic, OpenAI hoặc Google. |
| `prompt` | Nội dung hướng dẫn và dữ liệu đầu vào gửi cho LLM. |
| `prompt version` | Phiên bản prompt, ví dụ `dialogue_v1`, dùng để tái lập và so sánh các lần sinh dữ liệu. |
| `structured output` | Kết quả LLM theo format có cấu trúc, trong pipeline là JSON dialogue. |
| `dry-run` | Chế độ chạy thử không gọi API thật và không tốn chi phí; pipeline dùng template deterministic. |
| `production run` | Chế độ chạy thật bằng LLM API để tạo dữ liệu chất lượng dùng cho development/evaluation. |
| `deterministic` | Cùng input và cấu hình cho ra kết quả ổn định hoặc có thể tái lập. |
| `seed` | Giá trị dùng để tái lập một lần sinh dữ liệu hoặc ghi nhận cấu hình chạy. |
| `temperature` | Mức độ ngẫu nhiên khi LLM sinh output; giá trị thấp thường phù hợp với task có yêu cầu factual. |
| `retry` | Cơ chế gọi lại khi API lỗi, timeout hoặc trả về JSON không hợp lệ. |
| `parse` | Đọc và chuyển chuỗi JSON LLM trả về thành object để chương trình xử lý. |
| `assemble` | Bước ghép brief, fact pack và dialogue thành scenario BTC cuối cùng. |
| `validator` | Chương trình kiểm tra scenario có đúng schema và nghiệp vụ hay không. |
| `auto-check` | Nhóm kiểm tra tự động bổ sung như sai giá, leak PII, leak policy và hỏi lại slot đã biết. |
| `heuristic` | Quy tắc kiểm tra gần đúng, thường dựa trên regex/từ khoá; có thể cần review thủ công. |
| `manifest` | File nhật ký các lần chạy, thường chứa brief ID, model, seed, timestamp và status. |
| `idempotent` | Chạy lại cùng pipeline không tạo output trùng hoặc thay đổi output hợp lệ nếu không dùng `--force`. |
| `quarantine` | Nơi tạm giữ scenario lỗi hoặc chưa được duyệt, không đưa vào batch chính thức. |
| `freeze` | Trạng thái scenario đã qua kiểm tra và không được sửa thủ công thêm. |
