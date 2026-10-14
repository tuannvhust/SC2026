# Tổng hợp yêu cầu dự án SUDO CODE 2026 — Vòng 1
## Harness Agent hỗ trợ Call Center E-commerce (Telesale)

> **Mục đích tài liệu:** Tổng hợp yêu cầu M1 (cơ bản, bắt buộc) và M2 (nâng cao, khuyến khích) từ đề bài chính, `DIEU-CHINH-DE.md`, `GIAI-DAP-MENTOR.md` và `README.md` của gói dữ liệu BTC.  
> **Nguyên tắc ưu tiên:** M1 phải chạy ổn định trước khi đầu tư M2. Các tên tool, schema, trace và cách tính chỉ số phải theo gói dữ liệu BTC; không tự thay bằng quy ước khác.

---

## 1. Mục tiêu và phạm vi bài toán

Xây dựng một **Harness Agent hỗ trợ telesale e-commerce**, có khả năng:

1. Xử lý hội thoại tiếng Việt từ **chat/text** và **file ghi âm cuộc gọi** thành thông tin có cấu trúc, truy vấn được.
2. Duy trì bộ nhớ khách hàng xuyên nhiều cuộc gọi/phiên và nhiều kênh; nhận diện khách quay lại, nạp đúng ngữ cảnh, tiếp tục cuộc hội thoại thay vì hỏi lại từ đầu.
3. Thực hiện vòng lặp harness: nhận thức → truy hồi ngữ cảnh → lập kế hoạch → gọi tool → quan sát kết quả → cập nhật bộ nhớ; có guardrail và fallback.
4. Tự đánh giá bằng script tái lập được, so sánh với baseline không có bộ nhớ.
5. Cải thiện từ feedback mà **không huấn luyện lại hoặc fine-tune mô hình**.

### Bốn vấn đề nghiệp vụ cần giải quyết

- **Khách quay lại:** không yêu cầu khách cung cấp lại những dữ kiện đã có; chuẩn bị Call Brief trước khi agent phản hồi.
- **Đa kênh:** hợp nhất danh tính và lịch sử từ hotline, chat, Fanpage, Zalo…; xử lý mâu thuẫn nguồn một cách an toàn.
- **Bàn giao:** khi chuyển cho người thật hoặc ca/agent khác, truyền đủ thông tin đã khai thác qua handoff brief.
- **Cải tiến:** dùng kết quả cuộc gọi và feedback để cải thiện tài liệu, bộ nhớ, ví dụ mẫu hoặc kịch bản; phải đo trước/sau.

### Những điều không phải trọng tâm của M1

- Không bắt buộc voicebot real-time.
- Không cần huấn luyện mô hình.
- Không cần hệ thống tổng đài thật; mock tools có schema rõ ràng được chấp nhận.
- Không cần giao diện đẹp; cần đủ chức năng để trình diễn.
- Không nên hy sinh memory và evaluation để tập trung ghép voice pipeline.

---

## 2. M1 và M2 — phân biệt mức độ hoàn thành

| Phân hệ | M1 — bắt buộc | M2 — nâng cao |
|---|---|---|
| Chế độ tương tác | Agent chat text trực tiếp với khách; xử lý file ghi âm offline qua ASR | Voice gần real-time; có thể thêm copilot cho nhân viên |
| Dữ liệu | Dataset tối thiểu theo bảng ở mục 3 | Dataset lớn hơn, nhiều ngành/miền, có nhiễu |
| Bộ nhớ | Working, Episodic, Profile; xử lý ghi/không ghi và khách đổi ý | Semantic/KB, TTL, provenance, chống memory poisoning |
| Nhận diện khách | Nhận diện khách quay lại qua số điện thoại; Call Brief và tiếp nối hội thoại | Phát hiện khuyến mãi hết hạn/hết hàng; xử lý số lạ, hợp nhất sâu đa kênh |
| Tools | Tích hợp ít nhất 3 tool; dùng đúng tên/schema BTC yêu cầu | Thêm tool nghiệp vụ, kiểm soát quyền ghi |
| MCP/A2A | Chọn MCP hoặc A2A; triển khai mức tối thiểu theo nhánh đã chọn | Mở rộng server/agent chuyên biệt |
| Evaluation | ≥20 kịch bản đa phiên + ≥5 ca khó; 5 chỉ số bắt buộc; baseline không bộ nhớ | ≥40 kịch bản; simulator, LLM-as-a-judge và metric mở rộng |
| Cải tiến | Thu ít nhất 2 loại feedback; có ít nhất 1 cơ chế cải tiến; đo 2 vòng | Ít nhất 2 cơ chế cải tiến; ≥3 vòng và phân tích trường hợp gây hại |
| Hiệu năng | Call Brief ≤5s; TTFT p95 ≤3s; total latency p95 ≤8s; 1 phiên đồng thời | Call Brief ≤3s; TTFA p95 ≤2,5s; ≥2 phiên đồng thời |
| UI/demo | Khung hội thoại, Call Brief, timeline bộ nhớ; demo 2 cuộc gọi cùng khách | Copilot, cảnh báo cam kết sai, dashboard metric; demo nâng cao |
| Báo cáo | Đầy đủ bảng đo, baseline, cải tiến trước/sau, ≥10 lỗi phân tích | Metric mở rộng, đánh giá judge/simulator, nhiều vòng cải tiến |

---

## 3. Yêu cầu dữ liệu và xử lý tiếng Việt

### 3.1. Quy mô dataset tự xây

| Hạng mục | M1 — bắt buộc | M2 — nâng cao |
|---|---:|---:|
| Transcript hội thoại | ≥120 cuộc | ≥250 cuộc |
| Có audio (thu thật hợp lệ hoặc sinh TTS) | ≥40 cuộc, tổng ≥1 giờ | ≥100 cuộc, tổng ≥3 giờ |
| Khách có ≥2 cuộc gọi | ≥30 khách | ≥60 khách, trong đó có khách ≥3 phiên |
| Khách có cả gọi và chat | ≥10 khách | ≥30 khách |
| Ngành hàng / giọng vùng miền | 1 ngành / 2 miền | 3 ngành / 3 miền |
| Audio nhiễu (đường phố, sóng yếu…) | Không bắt buộc | ≥20% |
| Catalog sản phẩm | ≥30 SKU | ≥100 SKU |

**Persona bắt buộc ở M1 (ít nhất 3):**
- Khách do dự, cần hỏi người nhà.
- Khách so sánh giá.
- Khách đã mua, gọi lại đổi size hoặc khiếu nại.

**M2 bổ sung:** khách hỏi nhiều nhưng không mua; khách gọi lần thứ ba và đã hết kiên nhẫn.

### 3.2. Nguồn và nguyên tắc dữ liệu

- Team **tự tạo dataset hội thoại**, có thể dùng LLM đóng vai khách hàng và TTS. Không cần đợi bộ dữ liệu hội thoại chung.
- Dataset tự tạo phải dùng catalog, khuyến mãi, CRM seed và chính sách BTC phát để giá/chính sách khớp ground truth.
- BTC có `test_set/public_sample/` để kiểm tra định dạng và phát triển evaluator. Bộ test ẩn được dùng khi chấm.
- Nghiêm cấm dùng ghi âm khách hàng thật nếu chưa ẩn danh và chưa có sự đồng ý; vi phạm có thể bị loại.
- Gói BTC có dữ liệu tham chiếu gồm: 40 sản phẩm thuộc 3 ngành, 96 biến thể, 14 chương trình khuyến mãi, 50 CRM seed, 14 tài liệu chính sách/99 chunks, 60 câu hỏi RAG gán nhãn, 7 kịch bản mẫu và 12 hội thoại ASR ground truth (86 lượt, khoảng 12 phút, 4 hội thoại có nhiễu). Kiểm tra lại README/gói dữ liệu hiện hành nếu nội dung được cập nhật.

### 3.3. Pipeline xử lý

#### Voice — M1 bắt buộc

- Dùng ASR tiếng Việt có sẵn và chạy **local**: Whisper, PhoWhisper hoặc faster-whisper; không cần train.
- Chuyển file ghi âm thành transcript; transcript sau ASR đi qua cùng pipeline harness như chat text.
- Đánh giá WER, CER và Entity Accuracy; bắt buộc có độ chính xác riêng cho số tiền và số điện thoại.
- Chuẩn hóa cách đọc số thành giá trị chuẩn, ví dụ:
  - “bốn triệu tám trăm chín mươi” → `4.890.000`
  - “hai trăm bốn chín k” → `249.000`
  - Chuẩn hóa số điện thoại, ngày/giờ hẹn gọi lại.
- Đo trên audio BTC phát **cộng thêm ít nhất 20 file của team**. Dùng quy tắc `normalization_rule` trong `asr/ground_truth.json`.

#### Voice — M2 bổ sung

- Diarization/tách người nói (agent và khách).
- Sửa lỗi ASR bằng từ điển tên sản phẩm/thuật ngữ, ví dụ “Xiao Mi” → Xiaomi.
- Xử lý audio nhiễu và streaming/gần real-time.
- Diarization được đánh giá theo `audio/<id>.segments.json` khi BTC cung cấp đầy đủ bộ audio.

#### Text — M1

- Chuẩn hóa teencode, viết tắt, văn bản không dấu và code-switching Việt–Anh.
- Ví dụ: `sp nay co ship cod k a`, các từ `size`, `ship`, `sale`, `order`, `inbox`.
- Chuẩn hóa đầu vào nhưng không làm mất ý nghĩa nghiệp vụ.

#### Trích xuất thông tin có cấu trúc — M1

Tối thiểu trích xuất được:
- Intent/mục đích liên hệ.
- Sản phẩm/SKU quan tâm.
- Size, màu hoặc biến thể.
- Giá và khuyến mãi đã báo.
- Thời điểm hẹn gọi lại.
- Người ra quyết định hoặc rào cản mua hàng (ví dụ “để hỏi chồng”).
- Kết quả cuộc gọi: chốt / hẹn lại / từ chối.

**M2 bổ sung:** loại phản đối, cách xử lý, sentiment, cam kết đã hứa với khách.

#### PII và quyền riêng tư

- **M1:** che/mask số điện thoại, CCCD, địa chỉ khi lưu log và khi gửi dữ liệu ra model ngoài; regex là đủ.
- **M2:** có thể tokenization để nghiệp vụ vẫn dùng được; hỗ trợ xóa toàn bộ dữ liệu của một khách theo yêu cầu.
- Không được lộ PII trong trace/log hoặc phản hồi cho khách không có quyền xem.

---

## 4. Thiết kế bộ nhớ khách hàng

Đây là phần cốt lõi của bài toán.

### 4.1. Các tầng bộ nhớ

| Tầng | Mức | Nội dung |
|---|---|---|
| Working memory | M1 | Trạng thái lượt thoại/cuộc gọi hiện tại; khách vừa nói gì, đang chờ xác nhận gì. Phải cập nhật theo từng lượt, không chờ hết cuộc gọi nếu có thể chuyển máy giữa chừng. |
| Episodic memory | M1 | Tóm tắt từng cuộc gọi theo thời gian; ví dụ cuộc trước đã tư vấn SKU nào, báo giá nào, khách hẹn hỏi người nhà. |
| Customer Profile | M1 | Sự thật bền vững về khách: diện tích phòng, nhu cầu, ngân sách, sở thích… |
| Semantic memory / Knowledge Base | M2 | Tri thức về giá, tồn kho, khuyến mãi còn hiệu lực, chính sách đổi trả/FAQ; thường dùng RAG và dữ liệu nghiệp vụ có nguồn sự thật. |

### 4.2. Quy tắc bộ nhớ

**M1 phải:**
- Quy định rõ thông tin nào nên ghi và thông tin nào không nên ghi để tránh “nhồi rác”.
- Phân biệt dữ kiện bền vững với thông tin theo phiên.
- Hỗ trợ khách đổi ý: giá trị mới phải cập nhật/vô hiệu hóa giá trị cũ; không để hai giá trị mâu thuẫn cùng được xem là hiện hành.
- Khi nạp ngữ cảnh, chỉ đưa phần liên quan đến lượt hiện tại; không đọc vẹt toàn bộ hồ sơ khách trong lời chào.
- Ghi nhận trạng thái đủ sớm để có thể tạo handoff brief giữa cuộc gọi.

**M2 bổ sung:**
- TTL/hết hạn cho thông tin như khuyến mãi cũ, địa chỉ cũ, ý định mua đã nguội.
- Provenance: truy vết mỗi memory fact đến cuộc gọi/nguồn tạo ra nó.
- Chống memory poisoning, đặc biệt khi nhiều người dùng chung số điện thoại hoặc khách cung cấp thông tin sai.
- Hỗ trợ xóa dữ liệu khách theo yêu cầu.

### 4.3. Nhận diện và duy trì ngữ cảnh

**M1 — Session Continuity là yêu cầu bắt buộc:**
1. Nhận diện khách gọi lại qua số điện thoại.
2. Nạp Call Brief trước khi phản hồi.
3. Call Brief tối thiểu gồm: khách là ai; số lần liên hệ; sản phẩm đã tư vấn; giá/khuyến mãi đã báo; rào cản còn tồn đọng; hành động tiếp theo đề xuất.
4. Mở đầu bằng lời chào tiếp nối phù hợp.
5. Không hỏi mở lại những slot đã có giá trị hợp lệ; nếu cần thì hỏi xác nhận ngắn gọn.

Ví dụ hành vi mong muốn: “Dạ em chào chị Hoa, hôm trước bên em có tư vấn mẫu máy lọc X cho phòng 25m². Chị đã trao đổi với anh nhà chưa ạ, hay còn điểm nào em hỗ trợ thêm?” — chỉ nhắc dữ kiện cần cho bước tiếp theo.

**M2 bổ sung:**
- Phát hiện khuyến mãi đã hết hạn hoặc hàng hết; không lặp lại giá cũ như thể còn hiệu lực.
- Xử lý khách gọi từ số lạ.
- Xử lý danh tính đa kênh và trường hợp nhiều người chung số điện thoại.
- Kiểm tra thay đổi xảy ra sau phiên trước (giá, tồn kho, KM, tương tác kênh khác) trước khi dùng lại ngữ cảnh cũ.

**Precompute Call Brief:** được phép tính trước phần tóm tắt episodic ở cuối phiên trước và khai báo trong `precomputed_parts`. Tuy nhiên, kiểm tra dữ liệu mới nhất như khuyến mãi, tồn kho và tương tác kênh khác phải diễn ra khi nhận diện khách và vẫn tính vào latency.

---

## 5. Harness Agent, guardrail và tool

### 5.1. Vòng lặp harness cần thể hiện

Hệ thống cần có vòng lặp có kiểm soát, tối thiểu bao gồm:

1. Nhận input và kiểm tra đầu vào.
2. Chuẩn hóa transcript/chat.
3. Nhận diện khách và truy hồi bộ nhớ.
4. Tạo/nạp Call Brief.
5. Lập kế hoạch xử lý: trả lời, hỏi làm rõ, gọi tool hoặc chuyển máy.
6. Gọi tool với schema hợp lệ khi cần.
7. Quan sát/kiểm tra kết quả tool.
8. Tạo phản hồi hoặc handoff brief.
9. Ghi memory/trace và thu feedback phù hợp.
10. Fallback an toàn nếu tool, ASR hoặc LLM lỗi.

Cần giải thích rõ:
- Thông tin nào đưa vào prompt, thông tin nào cắt khi context dài.
- Khi nào cần gọi tool và khi nào không.
- Xử lý tool timeout, ASR rác, LLM trả sai định dạng.
- Khi nào phải chuyển cho người thật và thông tin nào cần bàn giao.
- Cách ngăn agent tự bịa giá/khuyến mãi/chính sách.

### 5.2. Tool nghiệp vụ

Tên tool và tham số bắt buộc phải tuân theo `schemas/tools.schema.json`. Có thể bổ sung tool/tham số riêng nhưng không được phá hợp đồng chung.

**M1 — các tool chuẩn:**
- `crm.get_customer`
- `catalog.search`
- `inventory.check`
- `order.create`
- `order.update`
- `schedule.callback`
- `handoff.transfer`

Đề chính yêu cầu tích hợp **ít nhất 3 tool**; mock có schema rõ ràng được chấp nhận. Nên ưu tiên những tool phục vụ trực tiếp cho luồng gọi lại và chốt đơn.

**M2 bổ sung:**
- `pricing.get_quote`
- `order.status`

Các tool nhận tham số `on` theo ngày của cuộc gọi khi cần tính giá/tồn kho/chính sách theo thời gian. Logic tham chiếu là `eval/mock_tools.py`; hệ thống tự viết hoặc bọc MCP phải cho kết quả nghiệp vụ tương đương. BTC có thể kiểm tra bằng `eval/validate_scenarios.py`.

### 5.3. Giá, tồn kho và chính sách

- Agent **không được tự bịa giá hoặc khuyến mãi**; dữ liệu phải lấy từ tool/nguồn tri thức hợp lệ.
- Khuyến mãi có điều kiện, ngày hiệu lực, giới hạn theo size/vùng/số lượng/khách; cần kiểm tra điều kiện trước khi báo.
- Tồn kho thay đổi theo ngày; SKU có thể ngừng bán và có SKU thay thế.
- Không dùng bản chính sách cũ nếu không còn hiệu lực; cần đọc changelog và xem ngày áp dụng/đơn hàng liên quan.
- Tài liệu nội bộ (ví dụ giá nhập, nhà cung cấp) tuyệt đối không được lộ cho khách.
- Nếu không có căn cứ trả lời, agent phải nói rõ chưa có thông tin/xin kiểm tra/chuyển người phù hợp, không bịa.

### 5.4. Handoff

- Working memory nên được cập nhật theo từng lượt.
- Khi cần chuyển máy, gọi `handoff.transfer` với brief sinh từ trạng thái hiện tại theo `schemas/handoff_brief.schema.json`.
- `expected_outcome: "chuyen_may"` được tính Task Success khi gọi đúng tool và brief đủ các trường bắt buộc.
- Không bắt buộc routing đến một nhân viên cụ thể; trọng tâm là quyết định đúng lúc và bàn giao đủ ngữ cảnh.
- Nên đo thêm tỷ lệ chuyển máy thừa; không được chuyển máy mọi trường hợp để né xử lý.

### 5.5. Chọn MCP hoặc A2A — bắt buộc chọn ít nhất một

#### Hướng A — MCP (Model Context Protocol)

- **M1:** xây dựng ít nhất 2 MCP server, bắt buộc có `mcp-memory` (đọc/ghi bộ nhớ khách hàng); server còn lại tự chọn, ví dụ `mcp-catalog` hoặc `mcp-crm`.
- **M2:** thêm `mcp-order`, `mcp-knowledge` (RAG chính sách/FAQ) và phân quyền theo tool, đặc biệt tool nào được ghi dữ liệu.

#### Hướng B — A2A / Multi-agent

- **M1:** có Orchestrator/Router, Context & Memory Agent, Sales Advisor Agent.
- **M2:** thêm Policy & Compliance Agent và QA/Evaluator Agent.
- Các agent phải thực sự chia sẻ trạng thái và bàn giao nhiệm vụ. Một chuỗi prompt tuần tự chỉ đổi tên không được xem là phối hợp multi-agent.
- Cần trình bày ít nhất một tình huống cụ thể cho thấy tách agent giúp hệ thống tốt hơn.

Nhóm chọn MCP **hoặc** A2A; cần giải thích lý do phù hợp với bài toán.

---

## 6. Đánh giá hệ thống — yêu cầu bắt buộc

### 6.1. Bộ test

**M1:**
- Ít nhất **20 kịch bản đa phiên**, mỗi kịch bản gồm 2–3 cuộc gọi liên tiếp cùng một khách.
- Mỗi cuộc phải có mục tiêu/kỳ vọng rõ ràng, có thể kiểm tra bằng code.
- Ít nhất **5 kịch bản khó**, chọn từ: khách đổi ý; khách đưa thông tin mâu thuẫn; khách đòi áp khuyến mãi hết hạn; câu hỏi không có trong tài liệu (agent phải thừa nhận không biết, không bịa).

**M2:**
- Ít nhất **40 kịch bản**.
- Có customer simulator để chạy lặp lại tự động, với mức kiên nhẫn giảm dần khi bị hỏi lại.
- Theo spec BTC, simulator dùng persona chuẩn, 8 quy tắc phản ứng, chạy 3 seed và lưu log bắt buộc.

### 6.2. Năm chỉ số bắt buộc M1

1. **Repeat-Question Rate (RQR)** — tỷ lệ câu hỏi hỏi lại thông tin đã biết.
2. **Context Carryover Rate (CCR)** — tỷ lệ fact quan trọng từ phiên trước được dùng đúng ở phiên sau.
3. **Task Success Rate (TSR)** — tỷ lệ kịch bản hoàn thành mục tiêu.
4. **Hallucination Rate (HR)** — tỷ lệ claim sai về dữ kiện kiểm chứng được, đặc biệt giá/khuyến mãi/chính sách.
5. **WER / CER** — chất lượng ASR; báo cáo thêm Entity Accuracy, đặc biệt số tiền và số điện thoại.

#### Cách hiểu và tính metric

- `RQR = số câu hỏi thừa / tổng số câu hỏi agent đặt ra × 100%`.
  - Một câu hỏi được gán với slot như ngân sách, diện tích, size, màu, địa chỉ, sản phẩm.
  - Nếu slot đã có giá trị hợp lệ trước khi bắt đầu cuộc gọi, hỏi mở lại là thừa.
  - Câu xác nhận không tính là thừa, **trừ khi** xác nhận lại slot đã được xác nhận trong cùng phiên; từ lần xác nhận thứ hai trở đi tính là thừa.
  - Thông tin hết TTL hoặc thông tin thực sự mới không bị tính là câu hỏi thừa.
  - Đọc vẹt hàng loạt thông tin cũ trong câu chào bị trừ ở chất lượng trải nghiệm.
- `CCR = số fact được dùng đúng / số fact bắt buộc mang sang × 100%`.
  - Kịch bản khai báo `must_carry_over`; fact chỉ tính khi được dùng đúng chỗ, không đọc vẹt.
- `TSR = số kịch bản đạt / tổng số kịch bản × 100%`.
  - Ưu tiên assertion/tool-call/args có thể kiểm tra bằng code.
  - Ca cần chuyển máy được tính đạt nếu gọi `handoff.transfer` với brief hợp lệ và đủ trường.
- `HR = số claim sai / tổng số claim kiểm chứng được × 100%`.
  - Claim là phát ngôn có dữ kiện đối chiếu được như giá, KM, tồn kho, thời gian giao, chính sách.
  - Không tính câu xã giao, câu hỏi hoặc ý kiến chủ quan.
- `WER = (S + D + I) / N × 100%`; `CER` tương tự nhưng tính theo ký tự.
  - Công bố rõ normalization trước khi tính: chữ thường, dấu câu, chuẩn hóa số…
  - `Entity Accuracy = số thực thể trích xuất đúng hoàn toàn / tổng số thực thể × 100%`; số điện thoại/số tiền so khớp exact match sau chuẩn hóa.

### 6.3. Baseline — bắt buộc

- Phải chạy hai cấu hình trên **cùng bộ test, cùng model, cùng tham số và cùng môi trường**; chỉ khác việc nạp memory phiên trước hay không.
- Baseline là phiên bản không có bộ nhớ, mỗi cuộc gọi độc lập.
- Báo cáo bảng so sánh baseline và hệ thống có memory, kèm chênh lệch.

**Ngưỡng kỳ vọng M1:**
- RQR giảm **ít nhất 40% tương đối** so với baseline: `(RQR_baseline − RQR_system) / RQR_baseline × 100%`.
- TSR ≥70%.
- HR về giá ≤5%.

Không có baseline hoặc số liệu không tái lập bằng code sẽ mất điểm nặng.

### 6.4. M2 — metric và judge bổ sung

- Calls-to-Close.
- Tool-Call Accuracy.
- Recall@k của RAG: báo cáo `k=3` và `k=5` trên `rag/qa_labeled.json` với corpus `policy/`.
- Full-recall cho câu multi-hop; abstain rate và false-abstain rate.
- Latency p50/p95.
- Chi phí ước tính mỗi cuộc gọi.
- LLM-as-a-judge với rubric rõ ràng, không chấm điểm chung chung 1–10.
- Dùng rubric BTC `eval/llm_judge_rubric.json` (12 tiêu chí PASS/FAIL); nhóm tự chấm tay ít nhất 20 mẫu và báo mức đồng thuận với LLM bằng Cohen’s kappa.
- TSR phải báo riêng cho ca khó; theo yêu cầu bổ sung, theo dõi `guardrail_violations`, gồm PII bị lộ, chuyển máy thừa, nhận là người thật, lộ thông tin nội bộ.

### 6.5. Trace và chấm chéo BTC

- Phải xuất trace theo `schemas/trace_log.schema.json`.
- Trace cần có `questions[]` và `claims[]` để evaluator kiểm tra RQR/HR; extractor không được bỏ sót câu hỏi hoặc claim.
- README repo phải cung cấp lệnh tương đương:
  ```bash
  python run_eval.py --scenarios <dir> --config full --out trace.jsonl
  python run_eval.py --scenarios <dir> --config baseline_no_memory --out baseline.jsonl
  ```
- BTC sẽ dùng bộ test ẩn 41 kịch bản và `eval/reference_eval.py` để tính số liệu chính thức. Bộ test ẩn gồm 19 ca khó.
- BTC có thể kiểm tra thủ công ngẫu nhiên 20 lượt trong trace để kiểm tra extractor.
- Bảng kết quả riêng của nhóm vẫn cần có trên test set của nhóm; nêu rõ cách trích `questions` và `claims`.
- Đo latency tại ranh giới backend/harness, không tính thời gian render UI; bỏ 3 lượt warm-up. Đo trên toàn bộ lượt test, tối thiểu 100 lượt nếu cần báo p95.

---

## 7. Cải tiến theo feedback — không fine-tune

### 7.1. Ràng buộc

Không huấn luyện lại/fine-tune mô hình. Cải tiến chỉ đến từ dữ liệu, memory, prompt/kịch bản và cách điều phối.

### 7.2. Nguồn feedback

M1 thu ít nhất **2 nguồn** trong các nguồn sau:
- Kết quả cuộc gọi: chốt / hẹn lại / từ chối.
- Điểm chấm tự động của evaluator.
- Nhân viên bấm 👍/👎 cho từng gợi ý của hệ thống.
- Việc khách phải nhắc lại thông tin.

### 7.3. Cơ chế cải tiến

**M1 phải hiện thực ít nhất 1 cơ chế:**
1. **Knowledge Gap Loop:** câu hỏi agent không trả lời được được ghi thành danh sách thiếu; bổ sung tài liệu; tự động thêm câu hỏi đó vào bộ test để tránh tái phạm.
2. **Exemplar Bank:** lưu cuộc gọi chốt đơn thành công làm ví dụ; truy hồi làm few-shot khi gặp tình huống tương tự.

**M2 phải có ít nhất 2 cơ chế**, có thể bổ sung:
3. **Reflection:** agent tạo bài học có cấu trúc sau cuộc gọi; phải kiểm tra trước khi ghi vào memory.
4. **A/B testing kịch bản:** chạy hai biến thể xử lý phản đối, so sánh tỷ lệ chốt và giữ phương án tốt hơn.

### 7.4. Chứng minh cải tiến

- **M1:** chạy vòng 0, thu feedback, áp dụng cải tiến, chạy vòng 1 trên **cùng bộ test giữ nguyên**; báo cáo chênh lệch.
- **M2:** ít nhất 3 vòng; phân tích cả trường hợp cải tiến gây hại.
- Nêu thay đổi nào cần người duyệt trước khi áp dụng.
- **M2:** chống học nhầm chiến lược như “hứa đại cho khách để chốt đơn”; có cơ chế rollback khi metric tụt.

---

## 8. Sản phẩm, UI, hiệu năng và demo

### 8.1. UI

**M1 tối thiểu:**
- Khung hội thoại chat text.
- Call Brief hiện ra khi khách gọi/nhắn lại.
- Timeline bộ nhớ: khách đã tương tác gì và khi nào.
- File ghi âm được đưa qua ASR rồi dùng chung harness.
- Agent trả lời trực tiếp cho khách ở chế độ chat; copilot gợi ý cho nhân viên là M2.

**M2 bổ sung:**
- Chế độ copilot gợi ý câu trả lời cho nhân viên.
- Cảnh báo khi agent sắp cam kết sai chính sách.
- Dashboard hiển thị metric ở mục evaluation.

### 8.2. Chỉ tiêu hiệu năng (theo file điều chỉnh mới nhất)

| Chỉ tiêu | M1 | M2 |
|---|---:|---:|
| Thời gian từ nhận diện khách đến Call Brief sẵn sàng | ≤5 giây | ≤3 giây |
| TTFT p95 (chat: gửi lượt đến token đầu tiên) | ≤3 giây | — |
| Total latency p95 (chat: đến khi sinh xong câu trả lời) | ≤8 giây | — |
| TTFA (từ lúc khách dừng nói đến audio đầu tiên) | — | p95 ≤2,5 giây |
| Phiên đồng thời trong demo | 1 | ≥2 |

Cách đo chính thức: `eval/huong-dan-do-latency.md`. Với Call Brief, thời gian tính từ lúc nhận diện số điện thoại đến khi brief sẵn sàng/hiển thị, bao gồm DB và LLM. Nếu precompute episodic thì vẫn phải tính bước kiểm tra tính mới vào latency.

### 8.3. Demo bắt buộc

**M1:** demo trực tiếp kịch bản 2 cuộc gọi:
1. Cuộc 1: khách mới, tư vấn sản phẩm, báo giá/khuyến mãi hợp lệ, khách hẹn “để hỏi người nhà”.
2. Cuộc 2 sau vài ngày, cùng khách: hệ thống nhận diện, nạp Call Brief, tiếp nối hội thoại, không hỏi lại thông tin đã có và tiến tới chốt đơn.

Kèm script evaluation để cho thấy số liệu so với baseline.

**M2:** có thể mở rộng cuộc 3 sau khi khách đặt hàng để đổi size/hỏi vận đơn; hệ thống phải biết đơn nào và cập nhật memory phù hợp.

### 8.4. Tài liệu/sản phẩm phải nộp

1. **Source code/repository:** có README, hướng dẫn cài đặt/chạy và script khởi tạo dữ liệu.
2. **Dataset:** dữ liệu + mô tả cách sinh, phân bố, hạn chế và cách xử lý PII.
3. **Tài liệu kiến trúc:** sơ đồ hệ thống/harness loop, thiết kế memory, danh sách tool, quyết định thiết kế và lý do.
4. **Báo cáo evaluation:** bảng metric, so sánh baseline không memory, trước/sau cải tiến, phân tích ít nhất 10 trường hợp hệ thống sai.
5. **Video demo:** 5–8 phút, bắt buộc có kịch bản 2 cuộc gọi ở trên.
6. **Website/UI:** có đầy đủ chức năng bắt buộc.
7. **Slide:** tối đa 15 slide.

### 8.5. Ràng buộc chung

- Dùng model có sẵn; LLM được phép gọi API.
- ASR phải chạy local ở M1; Whisper bản nhỏ trên laptop/Colab miễn phí là chấp nhận được.
- Trải nghiệm bằng tiếng Việt tự nhiên, đúng ngữ điệu telesale (dạ/vâng/ạ, xưng hô anh/chị/em theo ngữ cảnh).
- Mã nguồn phải chạy được theo README.
- Agent không được giả vờ là người thật nếu khách hỏi trực tiếp.
- Phải ước tính chi phí/cuộc gọi (tiêu chí mở rộng/chi phí).
- Chạy toàn bộ local là điểm thưởng, không phải điều kiện bắt buộc.

---

## 9. Gói dữ liệu BTC và các bẫy cần xử lý

Ngày quy ước `reference_date` trong README của gói dữ liệu là **2026-10-15**; dùng `call_date`/`days_later` của kịch bản khi đánh giá theo thời điểm. Không hard-code “hôm nay” theo thời gian máy chạy.

### 9.1. Dữ liệu nghiệp vụ dùng chung

- `catalog/products.json`, `products.csv`: 40 sản phẩm, 3 ngành, 96 biến thể, phụ thu size lớn, SKU ngừng bán và successor, combo.
- `catalog/inventory_timeline.json`: tồn kho thay đổi theo ngày.
- `catalog/promotions.json`: 14 chương trình; có chương trình hết hạn/chưa bắt đầu và nhiều điều kiện.
- `catalog/crm_seed.json`: 50 khách với SĐT/Zalo ID/Facebook ID; có khách lâu ngày, đơn đang giao, trường hợp hai người chung SĐT.
- `policy/`: 14 tài liệu/99 chunks; có chính sách hiện hành, chính sách cũ hết hiệu lực, changelog, tài liệu nội bộ hạn chế, lịch nghỉ, spec, playbook và tài liệu gây nhiễu.
- `rag/qa_labeled.json`: 60 câu hỏi, 6 loại: single, multi-hop, version conflict, unanswerable, restricted, numeric.
- `schemas/`: schema tool, CallBrief, HandoffBrief, trace log và format kịch bản.
- `eval/mock_tools.py`: logic tham chiếu nghiệp vụ.
- `eval/reference_eval.py`: evaluator tham chiếu.
- `eval/validate_scenarios.py`: kiểm tra tính nhất quán giữa kịch bản và catalog.
- `test_set/public_sample/`: 7 kịch bản mẫu.
- `asr/ground_truth.json`: ground truth ASR và quy tắc chuẩn hóa.
- `simulator/`: spec simulator và persona prompt.
- `eval/llm_judge_rubric.json`: rubric judge 12 tiêu chí PASS/FAIL.
- `eval/huong-dan-do-latency.md`: quy tắc đo latency.

### 9.2. Những ca khó trong bộ test ẩn cần thiết kế hệ thống để đối phó

Bộ test ẩn có 41 kịch bản, 19 ca khó; các tình huống được nêu trong điều chỉnh đề bao gồm:
- Ba kênh báo giá khác nhau.
- Hai người dùng chung một số điện thoại, có nguy cơ memory poisoning.
- Khách quay lại sau 8 tháng: TTL địa chỉ, SKU ngừng bán, thu cũ đổi mới.
- Khuyến mãi loại trừ một số size/biến thể.
- Transcript ASR sai hoặc có teencode.
- CCCD/STK phải được mask.
- Khách ép giá và dò giá nhập; không được lộ tài liệu nội bộ.
- Ba phiên có thông tin thay đổi và câu hỏi trạng thái đơn.
- Khách hỏi AI hay người và yêu cầu xóa dữ liệu.
- Hội thoại dài 16 lượt, 4 sản phẩm, đơn trên 10 triệu không COD/vượt ngân sách.
- Đổi sản phẩm và hoàn chênh lệch.
- Hỏi theo chính sách cũ.
- Hẹn gọi lại rơi vào ngày nghỉ; cần xử lý thời gian tương đối.
- Không bình luận giá đối thủ.
- Hết hàng đúng lúc khách quyết định mua.

Không nhất thiết tự tạo lại nguyên xi toàn bộ test ẩn; cần dùng chúng như checklist các rủi ro kiến trúc, đồng thời bảo đảm evaluator chạy đúng trên public sample.

---

## 10. Tiêu chí chấm điểm Vòng 1

| Tiêu chí | Trọng số |
|---|---:|
| Dữ liệu & xử lý tiếng Việt | 12% |
| Kiến trúc & Harness Agent | 22% |
| Áp dụng MCP/A2A | 15% |
| Đánh giá hệ thống | 15% |
| Cơ chế cải tiến | 13% |
| Trải nghiệm & demo | 13% |
| Khả năng mở rộng & chi phí | 5% |
| Trình bày & phản biện | 5% |
| **Tổng** | **100%** |

### Điểm thưởng (tối đa +5%, chỉ khi M1 hoàn chỉnh)

Có thể cân nhắc:
- Voicebot real-time có xử lý ngắt lời.
- Nhận diện bằng voiceprint/số lạ hoặc xử lý hai người dùng chung số.
- Toàn bộ hệ thống chạy local trên phần cứng phổ thông.
- Tối ưu prompt/kịch bản tự động; ablation cho thấy cơ chế nào tạo khác biệt.
- Playbook memory cho cách xử lý phản đối theo persona.
- Phát hiện realtime cam kết sai, dự đoán xác suất chốt/thời điểm gọi lại, phát hiện drift.
- Kết nối MCP server ngoài đời như Google Calendar, Google Sheets hoặc Notion.

### Các lỗi bị trừ nặng

- Không có Session Continuity: khách gọi lại vẫn bị hỏi từ đầu.
- Không có baseline không bộ nhớ.
- Số liệu trong báo cáo không tái lập được bằng code.
- Dùng ghi âm khách hàng thật trái phép/chưa ẩn danh.
- Lộ PII hoặc tài liệu nội bộ; giả vờ là người thật; bịa giá/KM/chính sách.
- Chỉ tạo dataset gồm các cuộc gọi rời rạc, không có khách đa phiên.

---

## 11. Lộ trình triển khai được đề xuất trong đề

| Tuần | Việc chính |
|---|---|
| Tuần 1 | Sinh dataset, ưu tiên khách đa phiên; dựng ASR và chuẩn hóa số; thiết kế schema memory |
| Tuần 2 | Harness loop, ít nhất 3 mock tools, Session Continuity và Call Brief |
| Tuần 3 | Bộ test, script evaluation, baseline không memory, lấy số liệu lần đầu |
| Tuần 4 | Hiện thực cơ chế cải tiến, đo vòng 2, UI, quay demo, viết báo cáo |

Lộ trình này là gợi ý tổ chức công việc; các yêu cầu M1 nêu ở trên mới là điều kiện hoàn thành cơ bản.

---

## 12. Checklist hoàn thành

### M1 — bắt buộc trước khi bắt đầu M2

#### Data & Vietnamese processing
- [ ] Có ≥120 transcript; ≥40 cuộc có audio và ≥1 giờ audio.
- [ ] Có ≥30 khách đa phiên; ≥10 khách có cả call và chat.
- [ ] Đạt số ngành/miền/SKU tối thiểu.
- [ ] Có ít nhất 3 persona bắt buộc.
- [ ] ASR tiếng Việt chạy local; đánh giá trên audio BTC + ≥20 file team.
- [ ] Có WER, CER, Entity Accuracy; kiểm tra số tiền và số điện thoại.
- [ ] Chuẩn hóa teencode, không dấu, code-switching và số.
- [ ] Trích xuất thông tin nghiệp vụ có cấu trúc.
- [ ] Mask PII trong log và trước khi gửi ra model ngoài.

#### Memory & harness
- [ ] Có Working, Episodic và Profile memory.
- [ ] Có quy tắc ghi/không ghi và xử lý khách đổi ý.
- [ ] Nhận diện khách quay lại qua số điện thoại.
- [ ] Call Brief đúng schema, hiện trong giới hạn ≤5 giây.
- [ ] Mở đầu bằng xác nhận tiếp nối; không hỏi lại slot đã biết.
- [ ] Harness loop, guardrail và fallback được mô tả/kiểm thử.
- [ ] Ít nhất 3 tool mock dùng đúng tên/schema BTC.
- [ ] Giá/KM/tồn kho/chính sách lấy từ nguồn sự thật, không bịa.
- [ ] Chọn MCP hoặc A2A và hoàn thành cấu hình M1 của nhánh đó.
- [ ] Có handoff brief hợp lệ cho tình huống ngoài phạm vi.

#### Evaluation & improvement
- [ ] Có ≥20 kịch bản đa phiên + ≥5 ca khó.
- [ ] Script evaluation chạy bằng lệnh và sinh bảng chỉ số.
- [ ] Tính đủ RQR, CCR, TSR, HR, WER/CER; báo Entity Accuracy.
- [ ] Có baseline không memory chạy trên cùng bộ test/model/tham số.
- [ ] Kiểm tra ngưỡng kỳ vọng: giảm RQR tương đối ≥40%, TSR ≥70%, HR giá ≤5%.
- [ ] Thu ít nhất 2 nguồn feedback.
- [ ] Có ít nhất 1 cơ chế cải tiến.
- [ ] Chạy vòng 0 và vòng 1 trên cùng test; báo cáo chênh lệch.
- [ ] Trace tuân theo schema BTC; `questions[]`/`claims[]` có chất lượng.
- [ ] Đo latency theo hướng dẫn.

#### Product & submission
- [ ] UI có chat, Call Brief và memory timeline.
- [ ] Demo đủ 2 cuộc gọi cùng khách và chạy evaluator trực tiếp.
- [ ] README cài đặt/chạy và script khởi tạo dữ liệu.
- [ ] Nộp dataset + mô tả, tài liệu kiến trúc, báo cáo + ≥10 lỗi, video 5–8 phút, website và slide ≤15 trang.
- [ ] Ước tính chi phí mỗi cuộc gọi; kiểm tra riêng PII và tính trung thực của agent.

### M2 — chỉ triển khai sau khi M1 ổn định

- [ ] Dataset đạt ngưỡng M2: ≥250 transcript, ≥100 cuộc audio/≥3 giờ, ≥60 khách đa phiên, ≥30 khách đa kênh, 3 ngành/3 miền, ≥20% audio nhiễu, ≥100 SKU.
- [ ] Diarization, sửa lỗi ASR theo từ điển, xử lý nhiễu/streaming.
- [ ] Semantic/KB + RAG cho chính sách và dữ liệu nghiệp vụ.
- [ ] TTL, provenance, chống memory poisoning và xóa dữ liệu khách.
- [ ] Xử lý số lạ, KM hết hạn, hết hàng và cập nhật đa kênh.
- [ ] Thêm tool/server/agent M2 theo lựa chọn MCP/A2A.
- [ ] ≥40 test; customer simulator theo spec BTC, 3 seed.
- [ ] LLM-as-a-judge theo rubric; ≥20 mẫu chấm tay và Cohen’s kappa.
- [ ] Calls-to-Close, Tool-Call Accuracy, Recall@3/@5, abstain/false-abstain, latency p50/p95, chi phí.
- [ ] Ít nhất 2 cơ chế cải tiến; ≥3 vòng; phân tích cải tiến gây hại và có rollback.
- [ ] Voice gần real-time đạt TTFA p95 ≤2,5 giây, ≥2 phiên đồng thời.
- [ ] Copilot/dashboard/cảnh báo cam kết sai nếu có đủ thời gian.

---

## 13. Thứ tự ưu tiên khuyến nghị

1. **Đúng memory + Session Continuity + Call Brief.**
2. **Tools và guardrail cho giá/KM/tồn kho/chính sách.**
3. **Evaluator và baseline từ sớm**, không để đến tuần cuối.
4. **Vòng cải tiến có số liệu trước/sau.**
5. Dataset đủ cấu trúc và ASR local chạy được.
6. UI/demo và tài liệu nộp.
7. Chỉ sau khi các mục trên ổn định mới đầu tư voice real-time, multi-agent phức tạp hoặc điểm thưởng.

> **Nguyên tắc kiểm tra cuối:** Một tính năng chỉ được coi là hoàn thành khi chạy được, có trace/log hoặc test chứng minh, và có thể tái lập theo README. Không trình bày số liệu chép tay thay cho evaluator.
