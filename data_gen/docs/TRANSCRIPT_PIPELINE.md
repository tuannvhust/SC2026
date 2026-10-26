# Bộ dữ liệu hội thoại theo cặp lượt (Paired Transcript Corpus)

## 1. Các đầu ra dữ liệu riêng biệt

Thư mục `scenarios/` tiếp tục giữ cấu trúc theo BTC, là dữ liệu đánh giá đầu vào của khách hàng. Các cuộc gọi trong đó bao gồm lượt thoại của khách hàng, đáp án chuẩn (ground truth) và tiêu chí thành công. Các cuộc gọi thuộc `scenarios/` không được tính là sản phẩm bàn giao transcript.

Thư mục `transcripts/` là bộ dữ liệu riêng biệt, chứa các lượt thoại theo cặp giữa `customer` (khách hàng) và `agent` (tác nhân AI), với schema được định nghĩa tại `schemas/transcript.schema.json`.

Transcript được sinh ra sẽ được đưa vào trạng thái `pending_review` (chờ duyệt). Chỉ người đánh giá mới có quyền chuyển trạng thái thành `accepted` (được chấp nhận). Transcript không vượt qua bước kiểm định hợp lệ (validation) không được phép chấp nhận.

Gói BTC trong repository hiện tại không có schema hoặc validator dành cho paired transcript. Vì vậy, khả năng tương thích với validator transcript của BTC vẫn ở trạng thái chưa được xác minh. Không được trình bày kết quả kiểm tra cục bộ như thể đó là kết quả xác thực của BTC.

## 2. Các mục tiêu M1 đã cấu hình

Các ngưỡng tối thiểu chính thức và mức dự phòng nội bộ được lưu trong `dataset_config.json`.

| Yêu cầu                            | Mục tiêu                                                                                                              |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Transcript theo cặp được chấp nhận | Tối thiểu 120; mục tiêu nội bộ 140                                                                                    |
| Transcript có audio thực tế        | Tối thiểu 40 transcript được chấp nhận, có file audio thực tế và tổng thời lượng audio đã xác minh ít nhất 3.600 giây |
| Khách hàng có nhiều phiên          | 30 khách hàng có ít nhất hai giá trị `session_id` khác nhau                                                           |
| Khách hàng sử dụng đa kênh         | 10 khách hàng có cả kênh hotline và chat                                                                              |
| Độ phủ ngành hàng và khu vực       | 1 ngành hàng, 2 khu vực                                                                                               |
| Persona bắt buộc                   | 3 persona theo yêu cầu M1                                                                                             |
| Catalog sản phẩm                   | Ít nhất 30 SKU                                                                                                        |
| Đánh giá ASR                       | Tính WER/CER/Entity Accuracy trên audio do BTC cung cấp, đồng thời có ít nhất 20 file audio do nhóm tự tạo            |

Các yêu cầu ASR bổ sung được nêu trong tài liệu BTC `data/DIEU-CHINH-DE.md`. Audio BTC trong `data/asr/` chỉ được đọc, không chỉnh sửa. Audio do nhóm tạo và ground truth tương ứng phải được lưu riêng trong `generated/scenario-dataset/audio/`.

| Yêu cầu BTC                                                                                    | Nguồn                                                  | Cấu hình / cách triển khai                                                                                                                   | Bằng chứng hiện tại                                                                          |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Ít nhất 120 transcript; mục tiêu an toàn nội bộ 140                                            | Đề bài chính thức, mục C.1; mục tiêu nội bộ của nhóm   | `milestones.M1.transcripts_min` / `transcripts_target`; chỉ tính các bản ghi transcript theo cặp đã được chấp nhận                           | 0 transcript được chấp nhận; 81 cuộc gọi scenario trước đó không phải transcript             |
| Ít nhất 40 cuộc hội thoại có audio / ít nhất 1 giờ                                             | Đề bài chính thức, mục C.1                             | Đếm các file WAV đã xác minh hash, được liên kết với ID transcript đã chấp nhận; cộng thời lượng thực tế của các file WAV                    | 0 cuộc / 0 giây                                                                              |
| Ít nhất 30 khách hàng có từ 2 cuộc gọi trở lên                                                 | Đề bài chính thức, mục C.1                             | Nhóm các `session_id` khác nhau theo `customer_id` trong các bản ghi đã chấp nhận                                                            | 0; kế hoạch có 33 khách hàng nhưng kế hoạch không đồng nghĩa với dữ liệu đã được chấp nhận   |
| Ít nhất 10 khách hàng sử dụng cả hotline và chat                                               | Đề bài chính thức, mục C.1; giải đáp mentor Q&A số 1   | Nhóm các bản ghi kênh thực tế theo ID khách hàng ổn định                                                                                     | 0; kế hoạch có 10 khách hàng                                                                 |
| Một ngành hàng, hai khu vực; ba persona cụ thể; ít nhất 30 SKU                                 | Đề bài chính thức, mục C.1                             | Giá trị cấu hình và metadata `coverage` thực tế của các transcript đã chấp nhận                                                              | Độ phủ thực tế bằng 0; kế hoạch có 1 ngành hàng, 3 khu vực và 12 persona                     |
| ASR chạy cục bộ; WER/CER và Entity Accuracy chính xác trên ít nhất 20 file, cộng với audio BTC | Đề bài chính thức, mục C.1; `DIEU-CHINH-DE.md`, mục 2  | `group_generated_asr_evaluation_files_min=20`; ground truth của nhóm sử dụng cấu trúc hội thoại/lượt thoại của BTC                           | Chưa có audio do nhóm tạo; thư mục BTC hiện chỉ có JSON ground truth; chưa chạy đánh giá ASR |
| Con người phê duyệt; không tạo dữ liệu giả được đánh dấu chấp nhận                             | Quy trình vòng đời dữ liệu được bổ sung rõ ràng        | Hàng đợi `pending_review`, thông tin người duyệt, thời gian và ghi chú; chỉ chấp nhận khi không có lỗi validation hoặc bản ghi gần trùng lặp | Chưa có mục trong hàng đợi trước khi sinh dữ liệu; chưa có transcript được chấp nhận         |
| Khả năng tương thích với validator transcript chính thức                                       | Gói BTC hiện có không chứa schema/validator transcript | Trạng thái validator được theo dõi riêng                                                                                                     | Chưa xác minh; không có validator BTC trong gói hiện tại                                     |

Ma trận kế hoạch hiện có 99 slot M1 / 161 cuộc gọi dự kiến, với độ phủ dự kiến gồm 33 khách hàng có nhiều phiên và 10 khách hàng đa kênh. Hiện chỉ có 49 scenario / 81 cuộc gọi đã được xây dựng brief và sinh dữ liệu.

Vì vậy, vẫn còn công việc theo kế hoạch cần hoàn thành trước khi bộ dữ liệu đạt mục tiêu. Các số liệu trên được tách biệt có chủ đích, không cộng gộp dữ liệu kế hoạch với dữ liệu đã được chấp nhận.

## 3. Quy trình sinh dữ liệu, đánh giá, audio và đóng gói

Chạy các lệnh sau từ thư mục gốc của repository bằng PowerShell.

### 3.1. Hoàn thiện brief và sinh scenario

```
# Bổ sung các brief scenario còn thiếu mà không ghi đè brief hiện có.
python -m data_gen.coverage_matrix.make_coverage_matrix stubs --matrix data_gen/coverage_matrix/coverage_matrix.csv --out generated/scenario-dataset/briefs
python -m data_gen.validation.lint_briefs generated/scenario-dataset/briefs

# Tiếp tục sinh đầu vào khách hàng cho scenario (có sử dụng LLM; chỉ chạy sau khi brief đã được duyệt).
python -m data_gen.generation.run_batch --briefs generated/scenario-dataset/briefs --out generated/scenario-dataset/scenarios --level M1 --seed 7
```

### 3.2. Sinh transcript theo cặp

```
# Sinh hai transcript theo cặp từ các scenario hiện có.
# Lệnh này gọi LLM đã được cấu hình.
python -m data_gen.transcripts generate --scenarios generated/scenario-dataset/scenarios --briefs generated/scenario-dataset/briefs --limit 2

# Mẫu kiểm tra nhanh vòng đời dữ liệu chỉ chạy cục bộ.
# Tuyệt đối không chấp nhận mẫu này làm dữ liệu đánh giá chất lượng.
python -m data_gen.transcripts generate --scenarios generated/scenario-dataset/scenarios --briefs generated/scenario-dataset/briefs --limit 1 --dry-run
```

### 3.3. Kiểm định và xem hàng đợi duyệt

```
# Kiểm tra tính hợp lệ và xem số lượng artifact thực tế / hàng đợi duyệt.
python -m data_gen.transcripts validate
python -m data_gen.transcripts coverage
Get-Content generated/scenario-dataset/reviews/queue.json

# Đưa ra quyết định duyệt rõ ràng cho từng transcript đã đánh giá.
python -m data_gen.transcripts review SC-002_call_1 --decision accepted --reviewer reviewer-name --notes "Reviewed paired turns, consistency, facts, privacy and language"
```

Lệnh duyệt ở trên là ví dụ cho một transcript. Cần thực hiện riêng cho từng transcript được đánh giá.

### 3.4. Sinh audio và tạo manifest

```
# Sinh audio chỉ khi đã cấu hình rõ lệnh TTS cục bộ.
$env:DATASET_TTS_COMMAND = 'my-local-tts --input {text_file} --output {wav_file} --speaker {speaker}'
python -m data_gen.transcripts audio

# Xây dựng lại manifest và báo cáo độ phủ dựa trên artifact thực tế.
python -m data_gen.transcripts manifest
```

Giai đoạn sinh audio chỉ sử dụng transcript đã được chấp nhận. Quy trình xác minh thời lượng WAV và hash của file, sau đó ghi ground truth ASR của nhóm vào `audio/team_asr_ground_truth.json`, theo cấu trúc hội thoại/lượt thoại của BTC tại `asr/ground_truth.json`.

Quy trình này không tạo dự đoán ASR. Ground truth không phải là giả thuyết nhận dạng của ASR (ASR hypothesis).

Công cụ TTS bên ngoài và giọng đọc là cấu hình do nhóm tự lựa chọn. Không có công cụ nào được gọi cho đến khi lệnh `audio` được thực thi một cách tường minh với command đã cấu hình.

### 3.5. Đánh giá ASR

Cài đặt `faster-whisper` và cung cấp đường dẫn đến thư mục chứa model cục bộ. Bộ đánh giá không tự tải model xuống.

```
python -m data_gen.transcripts.asr_eval --model-path .models/faster-whisper-small --btc-audio-dir data/asr --team-audio-dir generated/scenario-dataset/audio
```

Script tạo hai file:

- `generated/scenario-dataset/reports/asr_metrics.json`: các chỉ số đánh giá ASR.
- `generated/scenario-dataset/reports/asr_hypotheses.json`: kết quả nhận dạng ASR.

Script phân tách tập BTC và tập do nhóm tạo, liệt kê các ID audio bị thiếu, đồng thời báo cáo WER/CER và Entity Accuracy chính xác.

Quy tắc chuẩn hóa văn bản bao gồm:

- Chuẩn hóa Unicode NFC.
- Chuyển chữ thành chữ thường.
- Loại bỏ dấu câu.
- Chuẩn hóa khoảng trắng.
- Chuẩn hóa các dạng số theo quy tắc chuẩn tắc của thực thể được khai báo trong ground truth của từng hội thoại.

Các giả thuyết ASR chỉ được sinh bởi model ASR cục bộ. Bộ đánh giá không đưa giá trị thực thể tham chiếu vào phần giả thuyết đầu ra.

Các báo cáo ASR là sản phẩm do nhóm tạo ra; chúng không được dùng để chỉnh sửa file BTC.

### 3.6. Cách hoạt động của bộ sinh transcript

Bộ sinh transcript sử dụng các dữ kiện xác định trước (deterministic facts) và lượt thoại khách hàng đã có. Nó sinh riêng các câu trả lời của agent theo từng cặp, tách biệt với scenario đánh giá, rồi lưu kết quả sinh thô ở vị trí riêng.

Sau đó, dữ liệu được kiểm định và đưa vào hàng đợi chờ duyệt.

Quy trình ghi nhận:

- Model được sử dụng.
- Seed.
- Thời điểm sinh dữ liệu.
- Digest của các nguồn dữ liệu.
- Trạng thái của artifact.

Quy trình này không chứng minh hiệu năng của agent khi chạy thực tế.

## 4. Các yêu cầu đã xác minh và giới hạn hiện tại

- Đề bài chính thức yêu cầu 120 transcript, 40 cuộc hội thoại có audio với tổng thời lượng ít nhất 1 giờ, 30 khách hàng có nhiều phiên, 10 khách hàng sử dụng cả hotline và chat, một ngành hàng trên hai khu vực, ba persona M1 được chỉ định, ít nhất 30 SKU và đánh giá ASR bằng WER/CER cùng Entity Accuracy trên ít nhất 20 file.
- Tài liệu điều chỉnh yêu cầu 20 file ASR do nhóm tạo, bổ sung ngoài tập audio ASR được BTC cung cấp.
- Scenario đánh giá hiện tại chỉ chứa lượt thoại khách hàng, không được tính vào số lượng transcript theo cặp. Các số liệu trong báo cáo trước đây — 81 cuộc gọi scenario, 17 khách hàng nhiều phiên và 9 khách hàng đa kênh — chỉ phản ánh độ phủ scenario trong quá khứ, không phải bằng chứng về corpus đã được chấp nhận.
- Một transcript chỉ được chấp nhận sau khi vượt qua kiểm tra cục bộ về cấu trúc, quyền riêng tư, tính chính xác của dữ kiện và được con người ghi nhận quyết định duyệt. Việc kiểm tra dữ kiện nghiệp vụ cục bộ được thực hiện theo hướng thận trọng; khả năng tương thích với validator BTC vẫn chưa được xác minh.
- Các dữ kiện hiện tại về catalog, CRM và chính sách lấy từ dữ liệu nguồn của BTC. Pipeline không sửa đổi các file nguồn đó.
