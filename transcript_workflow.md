# Workflow sinh transcript và scenario cho BTC

Tài liệu này định nghĩa một pipeline sinh transcript **độc lập với thiết kế LangGraph**. Mục tiêu không phải tạo một bộ hội thoại “hay” theo cảm tính, mà tạo được scenario hội thoại có sự thật nghiệp vụ khớp với dữ liệu BTC, có thể tái lập, kiểm tra và bàn giao cho agent ở giai đoạn sau.

Pipeline không import, không gọi và không phụ thuộc vào `langgraph_agent/`. Graph hiện tại chưa hoàn thiện nên chỉ được tích hợp sau khi transcript đã được freeze.

## 1. Kết luận thiết kế cần thống nhất

### 1.1 Persona và scenario không phải một thứ

- **Persona** mô tả kiểu khách hàng: cách nói, mức kiên nhẫn, mục tiêu và phản ứng.
- **Scenario** mô tả một ca kiểm thử cụ thể: khách nào, kênh nào, ngày nào, sản phẩm nào, dữ kiện nào đã nói, agent cần làm gì và điều kiện thành công là gì.
- Một persona có thể được dùng trong nhiều scenario; mỗi scenario nên có một mục tiêu chính và một nhóm ca khó rõ ràng.

Persona bắt buộc lấy từ `data/simulator/personas.json`. Repository hiện có **12 persona**, không tự tạo thêm:

```text
khach_do_du_hoi_nguoi_nha
khach_so_gia
khach_da_mua_doi_size
khach_hoi_nhieu_khong_mua
khach_goi_lan_3_het_kien_nhan
khach_da_kenh_fb_hotline
khach_ngoai_pham_vi_chuyen_may
khach_hoi_ngoai_tai_lieu
khach_da_kenh_mau_thuan
hai_nguoi_chung_sdt
khach_quay_lai_sau_8_thang
khach_mua_nhieu_mon
```

### 1.2 “Transcript” phải được hiểu đúng trong bài BTC

Có hai loại dữ liệu cần tách riêng:

1. **Scenario dùng để chấm**: file JSON theo `data/schemas/scenario_format.md`, trong đó các lượt khách nằm ở `customer_turns` và, khi cần, `customer_turns_asr`. Đây là input deterministic để BTC so sánh agent.
2. **Transcript phát triển/kiểm thử**: hội thoại đầy đủ gồm customer và agent, dùng để đọc tự nhiên, regression test và minh họa. Nó không tự động là ground truth cho giá, KM, tồn kho hay chính sách.

Agent không nên học thuộc câu agent từ transcript sinh ra. Khi chạy thật, agent phải tự gọi tool và sinh câu trả lời dựa trên tool result. Nếu dùng full transcript làm dữ liệu huấn luyện mà không tách sự thật khỏi câu chữ, rất dễ tạo leakage và giá sai.

### 1.3 Nguồn sự thật

Mọi dữ kiện nghiệp vụ phải lấy từ `data/catalog/products.json`, `inventory_timeline.json`, `promotions.json`, `data/catalog/crm_seed.json`, `data/policy/*.md` và logic tham chiếu trong `data/eval/mock_tools.py`.

LLM chỉ viết lại dữ kiện đã có thành lời thoại tự nhiên. LLM không được tự tính giá sau KM, tự quyết KM còn hiệu lực, tự đoán tồn kho/ngày giao, tự chọn phiên bản policy đúng hoặc tự tạo hồ sơ CRM.

Ngày chuẩn của dữ liệu là `2026-10-15`. Mỗi cuộc gọi phải có `call_date`; khi gọi tool, truyền ngày đó qua tham số `on` nếu tool hỗ trợ. Không dùng ngày hệ thống hiện tại.

## 2. Phân chia công việc cho 2 sinh viên

| Người                  | Trách nhiệm                                                                                                   | Sản phẩm bàn giao                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| SV1 — Scenario/Content | Chọn persona và khách seed, thiết kế mục tiêu, ca khó, chuỗi 2–3 cuộc gọi, dàn ý lượt khách                   | `scenario_briefs/*.json`, ma trận coverage, báo cáo review câu chữ                                     |
| SV2 — Data/Pipeline    | Viết loader độc lập, gọi `mock_tools.py`, dựng fact pack, gọi LLM API, parse JSON, validate và log model/seed | `scripts/generate_transcripts.py`, `scripts/validate_generated.py`, output JSON/JSONL, README chạy lại |
| Cả hai                 | Chốt 3–5 ca mẫu, review bằng tay, quyết định loại/bổ sung dữ liệu                                             | `data_generation_contract.md`, biên bản QA                                                             |

SV1 không ghi số giá cuối cùng bằng tay nếu số đó có thể tính bằng tool. SV2 không tự sửa mục tiêu scenario để làm validator pass; nếu brief sai thì trả lại SV1.

## 3. Bước 0 — đọc contract và lập coverage

Trước khi sinh lượt thoại, cả hai đọc `data/DIEU-CHINH-DE.md`, `data/GIAI-DAP-MENTOR.md`, các schema, bảy file trong `data/test_set/public_sample/`, `data/simulator/`, `data/eval/mock_tools.py`, catalog, CRM, policy và `data/rag/qa_labeled.json`. `reference_eval.py` chỉ tham khảo để hiểu yêu cầu đầu ra; không phải dependency của pipeline sinh transcript.

Tạo `data_generation_contract.md`, ghi:

- field bắt buộc trong scenario;
- cách tính `call_date` từ `days_later`;
- tool nào cần tham số `on`;
- rule không lộ PII/tài liệu nội bộ;
- cách xử lý ASR và teencode;
- cách đặt `success_if`, `ground_truth_facts`, `facts_established`, `must_carry_over`, `must_not_ask`;
- model, temperature, seed và phiên bản prompt.

Ma trận coverage tối thiểu:

| Nhóm                   | Mục tiêu                                                                  |
| ---------------------- | ------------------------------------------------------------------------- |
| 12 persona             | Mỗi persona ít nhất một lần; persona khó có nhiều scenario hơn            |
| 3 ngành hàng           | Phân bố tương đối đều                                                     |
| đa phiên               | Có scenario 2–3 cuộc, kiểm tra carry-over và không hỏi lại                |
| shared phone           | Dùng đúng hồ sơ CRM, buộc xác nhận danh tính                              |
| lịch sử 8 tháng        | Kiểm tra TTL và thông tin cũ                                              |
| đơn đang giao/đổi size | Kiểm tra `order.status`/`order.update` phù hợp                            |
| KM/tồn kho theo ngày   | Có KM hết hạn, chưa bắt đầu, loại trừ size, hết hàng rồi về hàng          |
| policy                 | Có single, multi-hop, version conflict, unanswerable, restricted, numeric |
| input lỗi              | Có `asr_transcript` và `chat_teencode`, giữ bản gốc và bản chuẩn hóa      |
| guardrail              | Không lộ giá nhập, nhà cung cấp, PII, hoặc nhận mình là người thật        |

## 4. Bước 1 — viết scenario brief, chưa viết lời thoại

Mỗi brief cần tối thiểu:

```json
{
	"scenario_id": "GEN-001",
	"level": "M1",
	"persona": "khach_so_gia",
	"customer_id": "CRM-...",
	"customer_phone": "...",
	"channel_plan": ["hotline", "zalo_oa"],
	"call_plan": [
		{
			"call": "call_1",
			"call_date": "2026-10-15",
			"goal": "...",
			"sku": "...",
			"qty": 1,
			"address": "...",
			"policy_chunk_ids": [],
			"hard_case": "numeric",
			"outcome": "hen_goi_lai"
		}
	]
}
```

Đây là **brief nội bộ**, không phải output cuối của BTC. Pipeline phải chuyển brief thành schema chính thức, không dùng brief thay cho `scenario_format.md`.

Brief phải trả lời được: khách là ai và ở kênh nào; mục tiêu từng cuộc; dữ kiện nào được nói; dữ kiện nào phải carry-over/không được hỏi lại; tool call nào là điều kiện thành công; ground truth nào cần đối chiếu; và ca khó nào đang được kiểm thử.

Không đưa tài liệu nội bộ vào lời khách như thể khách biết giá nhập. Với ca `restricted`, brief chỉ mô tả khách hỏi; agent phải từ chối chia sẻ hoặc chuyển máy theo policy.

## 5. Bước 2 — dựng fact pack bằng code, không dùng LLM

Pipeline của SV2:

```text
brief → load catalog/CRM/policy → gọi mock_tools
      → tính ground_truth_facts → dựng fact_pack bất biến
      → prompt LLM viết customer turns → kiểm tra
      → đóng gói scenario theo schema BTC
```

`fact_pack` nên chứa `reference_date`, `call_date`, customer profile, SKU/variant, list/final price, promo active/expired/ineligible, tồn kho/ngày restock, order/session cũ được phép dùng, policy chunk ID/version, `facts_established`, `must_carry_over`, `must_not_ask`, `success_if` và danh sách thông tin cấm xuất hiện.

Fact pack được lưu để audit, nhưng prompt chỉ nhận PII tối thiểu. Số điện thoại thật chỉ dùng cho tool/identity test; log và transcript phát hành phải mask PII.

## 6. Phương pháp sinh transcript độc lập

### 6.1 Kiến trúc pipeline

Pipeline chỉ có các module sau:

```text
briefs/*.json
  → loader dữ liệu BTC
  → deterministic fact builder
  → prompt builder
  → LLM client
  → JSON parser/repair
  → transcript validator
  → scenario exporter
  → manifest + report
```

Mỗi module nhận input file và trả output file; không dùng shared state, memory của agent hay graph checkpoint. Có thể chạy trên máy cá nhân, CI hoặc một job batch.

Đề xuất cấu trúc độc lập:

```text
transcript_pipeline/
├── briefs/
├── prompts/
├── outputs/
├── quarantine/
├── generate_transcripts.py
├── build_fact_pack.py
├── validate_generated.py
└── manifest.json
```

`langgraph_agent/` không nằm trong dependency của pipeline.

### 6.2 Sinh hàng loạt bằng API

Không nên sinh bằng ChatGPT interface thủ công vì khó kiểm soát prompt version, batch, retry, JSON parse và audit. Dùng Python CLI độc lập gọi **Anthropic Messages API**. Không import client từ `langgraph_agent/src/llm.py`; pipeline phải có client riêng.

- Model chính: model Anthropic qua `HARNESS_MODEL` (repo mặc định `claude-sonnet-4-6`); nếu tên model không còn khả dụng, chốt một model Sonnet hiện hành và ghi vào manifest.
- Model rà soát rẻ: model Haiku tương thích, hoặc rule-based checker trước rồi mới gọi LLM checker.
- `temperature=0` hoặc thấp, `max_tokens` đủ cho 8–16 lượt.
- Yêu cầu JSON thuần, parse + retry khi JSON không hợp lệ.
- Ghi model, prompt version, temperature, seed/run id, timestamp và fact-pack hash.

Không fine-tune. LLM chỉ viết câu chữ; giá/KM/tồn kho do code xác lập.

### 6.3 Hai prompt riêng

**Prompt A — Customer-turn generator**

Input: persona chuẩn, mục tiêu, turn outline, facts được phép nói, previous call summary, channel/input mode, patience và hard case.

Output:

```json
{
	"customer_turns": ["...", "..."],
	"customer_turns_asr": null,
	"facts_referenced": ["room_area_m2", "budget_vnd"]
}
```

LLM không sinh lời agent ở bước này. Mỗi lượt chỉ 1–2 câu, không bịa entity/số liệu mới, không tự chốt đơn nếu outline chưa cho phép. Với teencode, chỉ biến đổi phần customer; với ASR, giữ bản clean làm ground truth và bản lỗi làm input test.

**Prompt B — Full-dialogue reviewer/simulator, tùy chọn**

Chạy sau khi scenario đã có customer turns. Prompt đưa fact pack và customer turns cho model đóng vai agent để tạo full transcript đọc kiểm tra. Đây chỉ là bản review, không ghi đè `customer_turns` deterministic nếu chưa được người duyệt.

##

## 7. Bước 3 — validate nhiều lớp

Mỗi batch 5 scenario đầu tiên, sau đó 10–20 scenario/batch, chạy:

### Lớp A — schema và dữ liệu

- parse JSON và đúng `scenario_format.md`;
- persona tồn tại trong `personas.json`;
- customer/SKU/promo/chunk tồn tại;
- `call_date`/`days_later` nhất quán;
- `success_if` khớp tool args và `ground_truth_facts`.

### Lớp B — nghiệp vụ

Chạy logic tương đương `data/eval/validate_scenarios.py` nếu validator được BTC cung cấp trong package đầy đủ. Trong checkout hiện tại, README có nhắc file này nhưng file không tồn tại; vì vậy giai đoạn hiện tại dùng `mock_tools.py` và local validator của SV2. `reference_eval.py` chỉ chạy ở bước tích hợp agent sau này. Khi nhận validator chính thức, chạy thêm validator BTC và chạy lại toàn bộ batch.

Kiểm tra final price/order price, KM hết hạn/chưa bắt đầu, tồn kho đúng ngày, COD limit, policy hiện hành, restricted/internal, PII, và carry-over/không hỏi lại.

### Lớp C — ngôn ngữ

Review thủ công tối thiểu 15–20 scenario: tiếng Việt tự nhiên; persona và patience đúng; không lặp máy móc; teencode/ASR đúng phạm vi; customer không nói ngoài facts/outline; cuộc gọi sau nối tiếp tự nhiên.

### Lớp D — kiểm tra độc lập sau sinh

Sau khi xuất scenario, pipeline chạy evaluator độc lập trên chính file output:

```powershell
python scripts/validate_generated.py `
  --input outputs/ `
  --catalog data/catalog `
  --policy data/policy `
  --crm data/catalog/crm_seed.json `
  --report outputs/validation_report.json
```

Evaluator phải kiểm tra schema, persona, SKU, ngày gọi, giá/KM/tồn kho, carry-over, PII và nội dung cấm. Khi BTC cung cấp `validate_scenarios.py` đầy đủ, chạy thêm validator đó như một bước hậu kiểm; nó không phải dependency để LLM sinh transcript.

Việc chạy agent, sinh trace, đo memory/guardrail/latency và đánh giá TSR là workflow tích hợp riêng sau này.

## 8. Các lỗi workflow cũ cần tránh

1. Ghi “12 persona” nhưng không lấy từ `data/simulator/personas.json`.
2. Dùng schema brief nội bộ làm schema BTC.
3. Gọi LangGraph hoặc validator runtime như điều kiện bắt buộc để sinh transcript.
4. Để LLM tự tính final price hoặc tự chọn policy đúng.
5. Sinh full agent transcript rồi coi là đáp án chuẩn.
6. Sinh audio/TTS khi M1 chỉ yêu cầu ASR local và text output.
7. Dùng ngày hệ thống thay cho `call_date`/`on`.
8. Đưa toàn bộ CRM/PII hoặc tài liệu nội bộ vào prompt/log.
9. Hỏi lại slot đã có ở cuộc trước.
10. Sinh hàng trăm scenario trước khi kiểm tra 3–5 ca đầu tiên.

## 9. Kế hoạch thực hiện

### Ngày 1 — contract và coverage

Cả hai đọc tài liệu, tạo `data_generation_contract.md`, lập ma trận persona × hard case × ngành hàng, xác định hồ sơ CRM đặc biệt.

### Ngày 2 — brief và fact pack

SV1 viết 5 brief đại diện. SV2 viết loader/tool adapter/fact pack. Cả hai kiểm tra thủ công giá, KM và ngày.

### Ngày 3 — generator và validator độc lập

SV2 tích hợp Anthropic API, JSON parser, retry, log và validator local; không phụ thuộc `langgraph_agent`. SV1 viết turn outline cho persona và ca khó.

### Ngày 4 — pilot

Sinh 5 scenario, chạy qua agent, sửa prompt/pipeline. Chỉ mở rộng khi schema, nghiệp vụ và ngôn ngữ đều đạt.

### Ngày 5–6 — batch

Sinh từng batch 10–20 scenario, validate ngay, bổ sung coverage thiếu. Output lỗi chuyển vào quarantine kèm lý do; không âm thầm ghi đè.

### Ngày 7 — freeze và báo cáo

Chạy regression public sample, review ngẫu nhiên, thống kê coverage, chi phí API, thời gian sinh, tỷ lệ retry và scenario bị loại. Commit prompt version, code và manifest output.

## 10. Ví dụ thực hiện end-to-end

Ví dụ dưới đây dùng `data/test_set/public_sample/SAMPLE-06.json`. Đây là ví dụ đối chiếu để hiểu workflow, không ghi đè file mẫu của BTC.

### Bước 1 — Đọc scenario và xác định mục tiêu

Từ `SAMPLE-06`, ta xác định:

- Persona: `khach_do_du_hoi_nguoi_nha`.
- Khách: Việt, xưng hô `anh`, số `0991280845`.
- Cuộc 1: ngày `2026-10-15`, hỏi Xiaomi 4 Pro cho phòng 35 m², ngân sách khoảng 5,5 triệu, chưa quyết vì cần hỏi vợ.
- Cuộc 2: sau 5 ngày, khách quay lại qua `zalo_oa`, dùng teencode, đồng ý mua và yêu cầu COD.
- Ca khó: cuộc 1 dùng `asr_transcript`; cuộc 2 dùng `chat_teencode`; tồn kho thay đổi giữa hai ngày.

Ở bước này chưa viết giá mới và chưa viết câu trả lời của agent. Chỉ xác định mục tiêu, persona, ngày và luồng thông tin.

### Bước 2 — Tạo brief nội bộ

SV1 tạo brief rút gọn như sau:

```json
{
	"scenario_id": "GEN-SAMPLE-06",
	"level": "M1",
	"persona": "khach_do_du_hoi_nguoi_nha",
	"customer_phone": "0991280845",
	"customer_name": "Việt",
	"honorific": "anh",
	"calls": [
		{
			"call": "call_1",
			"call_date": "2026-10-15",
			"channel": "hotline",
			"input_mode": "asr_transcript",
			"goal": "Hỏi giá máy lọc không khí Xiaomi 4 Pro cho phòng 35 m²",
			"sku": "SKU-XM-4P",
			"budget_vnd": 5500000,
			"outcome": "hen_goi_lai"
		},
		{
			"call": "call_2",
			"call_date": "2026-10-20",
			"channel": "zalo_oa",
			"input_mode": "chat_teencode",
			"goal": "Xác nhận mua sản phẩm đã tư vấn và đặt COD",
			"sku": "SKU-XM-4P",
			"carry_over": ["product_advised", "price_quoted_vnd", "room_area_m2"],
			"outcome": "chot_don"
		}
	]
}
```

Brief này chỉ là kế hoạch. Giá cuối, trạng thái kho, khuyến mãi và điều kiện tạo đơn vẫn phải do bước tiếp theo xác định.

### Bước 3 — Dựng fact pack bằng code

SV2 gọi dữ liệu/tool cho từng ngày. Kết quả kỳ vọng từ dữ liệu mẫu là:

```json
{
	"scenario_id": "GEN-SAMPLE-06",
	"call_1": {
		"call_date": "2026-10-15",
		"sku": "SKU-XM-4P",
		"final_price_vnd": 5490000,
		"in_stock": false,
		"restock_date": "2026-10-19",
		"facts_allowed": [
			"room_area_m2",
			"budget_vnd",
			"product_advised",
			"price_quoted_vnd"
		],
		"success_if": null
	},
	"call_2": {
		"call_date": "2026-10-20",
		"sku": "SKU-XM-4P",
		"final_price_vnd": 5490000,
		"in_stock": true,
		"promo_code": "NAM-SHIP0",
		"freeship": true,
		"success_if": {
			"tool_called": "order.create",
			"args_match": {
				"sku": "SKU-XM-4P",
				"price_vnd": 5490000,
				"payment": "COD"
			}
		}
	}
}
```

Điểm cần chú ý: cùng một SKU nhưng phải gọi kiểm tra theo **hai ngày khác nhau**. Không được lấy kết quả tồn kho của cuộc 2 để viết cuộc 1.

### Bước 4 — Viết customer turns bằng LLM

Prompt gửi cho model chỉ chứa persona, mục tiêu, outline và các facts được phép nói. Ví dụ rút gọn:

```text
Bạn là khách hàng theo persona khach_do_du_hoi_nguoi_nha.
Cuộc gọi: call_1, ngày 2026-10-15.
Mục tiêu: hỏi Xiaomi 4 Pro cho phòng 35 m², ngân sách khoảng 5,5 triệu,
chưa quyết mua vì cần hỏi vợ.
Facts được phép nói: sản phẩm Xiaomi 4 Pro, phòng 35 m², ngân sách 5,5 triệu.
Input mode: asr_transcript.
Sinh 3 lượt khách, mỗi lượt 1–2 câu. Không tự nói giá cuối,
không tự nói tồn kho, không tự tạo thông tin ngoài outline.
Chỉ trả JSON với key customer_turns.
```

Một output hợp lệ có thể là:

```json
{
	"customer_turns": [
		"a lô cho anh hỏi máy lọc không khí xiao mi bốn pờ rô giá bao nhiêu",
		"phòng anh ba mươi lăm mét vuông có được không",
		"ngân sách anh tầm năm triệu rưỡi thôi, để anh hỏi vợ đã"
	]
}
```

Ở đây model chỉ tạo lời khách. Giá `5.490.000đ`, hết hàng và ngày restock không được model tự thêm vào `customer_turns`; đó là thông tin agent phải tự tra khi chạy.

Với cuộc 2, prompt dùng `previous_call_summary` và `must_carry_over`, đồng thời yêu cầu văn phong teencode:

```json
{
	"customer_turns": [
		"e oi hom truoc a hoi cai xiaomi 4 pro",
		"vo a ok r, sp nay co ship cod k, a o q7 hcm",
		"ok len don cho a nhe"
	]
}
```

### Bước 5 — Đóng gói thành scenario BTC

Pipeline không dùng trực tiếp output thô của model. Nó ghép output đó với metadata và fact pack bằng code:

```json
{
	"scenario_id": "GEN-SAMPLE-06",
	"level": "M1",
	"persona": "khach_do_du_hoi_nguoi_nha",
	"customer_phone": "0991280845",
	"customer_name": "Việt",
	"honorific": "anh",
	"calls": {
		"call_1": {
			"call_date": "2026-10-15",
			"input_mode": "asr_transcript",
			"customer_turns_asr": [
				"a lô cho anh hỏi máy lọc không khí xiao mi bốn pờ rô giá bao nhiêu",
				"phòng anh ba mươi lăm mét vuông có được không",
				"ngân sách anh tầm năm triệu rưỡi thôi, để anh hỏi vợ đã"
			],
			"expected_outcome": "hen_goi_lai",
			"ground_truth_facts": {
				"price_vnd": 5490000,
				"in_stock": false,
				"restock_date": "2026-10-19"
			}
		},
		"call_2": {
			"days_later": 5,
			"channel": "zalo_oa",
			"input_mode": "chat_teencode",
			"customer_turns_asr": [
				"e oi hom truoc a hoi cai xiaomi 4 pro",
				"vo a ok r, sp nay co ship cod k, a o q7 hcm",
				"ok len don cho a nhe"
			],
			"must_carry_over": [
				"product_advised",
				"price_quoted_vnd",
				"room_area_m2"
			],
			"must_not_ask": ["product_advised", "room_area_m2", "budget_vnd"],
			"success_if": {
				"tool_called": "order.create",
				"args_match": {
					"sku": "SKU-XM-4P",
					"price_vnd": 5490000,
					"payment": "COD"
				}
			}
		}
	}
}
```

Trong output thực tế, giữ đầy đủ các field bắt buộc theo `scenario_format.md`; đoạn trên chỉ rút gọn để minh họa.
Nếu có `customer_turns_asr`, vẫn lưu `customer_turns` clean tương ứng để làm ground truth chuẩn hóa; hệ thống test sẽ nhận bản ASR theo `input_mode`.

### Bước 6 — Validate trước khi đưa vào batch

Validator độc lập kiểm tra:

1. `persona` có tồn tại không.
2. SKU và customer có tồn tại không.
3. `call_2` có dùng đúng `days_later = 5` không.
4. `ground_truth_facts.price_vnd` có khớp kết quả tool không.
5. Cuộc 1 có phản ánh hết hàng và ngày restock không.
6. Cuộc 2 có carry-over và không hỏi lại diện tích/sản phẩm không.
7. `order.create` có yêu cầu đúng SKU, giá và COD không.
8. Có PII hoặc thông tin nội bộ bị lộ trong transcript không.

Nếu một giá trị không khớp, đánh dấu scenario là `quarantine`, ghi nguyên nhân và sửa brief/fact builder; không sửa tay giá trong output LLM.

### Bước 7 — Review thủ công và freeze

Hai sinh viên đọc cả hai cuộc gọi và xác nhận:

- cuộc 1 nghe giống khách đang hỏi và cần hỏi vợ;
- cuộc 2 nghe giống khách quay lại, không lặp lại toàn bộ thông tin;
- ASR lỗi và teencode chỉ nằm ở input customer;
- không có câu agent giả lập nào được dùng làm ground truth bắt buộc;
- file cuối cùng có thể đưa vào adapter agent sau này mà không sửa dữ kiện.

Sau khi đạt, ghi file vào `outputs/`, cập nhật `manifest.json` và không chỉnh tay scenario đã freeze.

## 11. Checklist đóng gói

- [ ] Scenario khớp `data/schemas/scenario_format.md`.
- [ ] Dùng đúng 12 persona chuẩn.
- [ ] Có coverage đa phiên, shared phone, 8 tháng, đơn đang giao/đổi size, KM/tồn kho theo ngày, 6 nhãn RAG và ASR/teencode.
- [ ] Mọi giá/ngày/KM/tồn kho khớp `mock_tools.py`.
- [ ] Tool runtime truyền đúng `on=call_date`.
- [ ] Không lộ PII, giá nhập, nhà cung cấp hoặc tài liệu nội bộ.
- [ ] `customer_turns` deterministic; `customer_turns_asr` chỉ có khi cần.
- [ ] Có fact pack/manifest để audit và đã mask dữ liệu nhạy cảm khi phát hành.
- [ ] Đã chạy schema validator, validator nghiệp vụ độc lập và review thủ công.
- [ ] Đã ghi model, prompt version, seed, temperature, thời gian và chi phí.
- [ ] Có README hướng dẫn chạy lại bằng CLI/API, không phụ thuộc thao tác interface thủ công.
