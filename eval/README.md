# Bộ câu hỏi đánh giá (150 câu)

File: `questions.jsonl` — mỗi dòng một câu hỏi.

| category | Số câu | Mục đích |
|---|---:|---|
| `direct` | 90 | Truy xuất cơ bản, độ bám nguồn |
| `synthesis` | 5 | Tổng hợp nhiều đoạn / nhiều tài liệu (ĐTĐ + THA) |
| `no_answer` | 20 | Từ chối khi kho không có (nhiều câu về bệnh khác) |
| `emergency` | 15 | Phát hiện và cảnh báo cấp cứu |
| `out_of_scope` | 10 | Chặn chẩn đoán / kê đơn / liều cá nhân |
| `adversarial` | 10 | Chống thao túng, ép bỏ quy tắc |

Theo hành vi mong đợi: 95 `answer` · 40 `refuse` · 15 `emergency_alert`.

## Bộ dev / test

Trường `split` chia 150 câu thành **dev (50)** để tinh chỉnh (GĐ 7) và **test (100)** để chấm điểm cuối (GĐ 9) – chia ngẫu nhiên phân tầng theo (`expected_behavior`, `category`), hạt giống 2026, mỗi nhóm ~1/3 vào dev. Không dùng câu test khi chỉnh prompt / ngưỡng.

```
.venv/Scripts/python eval/guard_eval.py --split dev        # đánh giá Guardrails trên bộ dev
.venv/Scripts/python eval/retrieval_eval.py --split test   # đo truy xuất trên bộ test
```

Lưu ý: 96 câu đầu (Q001–Q096) đã được dùng khi tinh chỉnh Guardrails ở GĐ 6, nên một phần bộ test không còn "chưa từng thấy"; 54 câu Q097–Q150 (thêm 26/10/2026) chưa dùng cho tinh chỉnh nào.

## Trường dữ liệu

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã câu hỏi, ví dụ `Q001` |
| `question` | Câu hỏi |
| `category` | Một trong 6 nhóm trên |
| `topic` | một hoặc nhiều `topic_id` trong `data/catalog/topics.csv`, ngăn cách bằng `;`; hoặc `other` (ngoài phạm vi) |
| `expected_behavior` | `answer` / `refuse` / `emergency_alert` |
| `expected_chunk_ids` | Các chunk chứa đáp án (rỗng nếu `refuse`) |
| `reference_answer` | Đáp án chuẩn ngắn gọn (để chấm Answer Relevance) |
| `reviewed_by` | Người rà soát chuyên môn |
| `split` | `dev` / `test` (xem bên dưới) |

Tất cả câu hỏi là dữ liệu tự tạo, không dùng câu hỏi/hồ sơ bệnh nhân thật.

## Đo chất lượng truy xuất (GĐ 4)

```
.venv/Scripts/python eval/retrieval_eval.py     # cần Docker chạy ES + Milvus
```

Đo Recall@5, Recall@10, MRR@10, nDCG@10 cho 3 chế độ `bm25` / `vector` / `hybrid` trên các câu có `expected_chunk_ids`; chi tiết từng câu ghi vào `eval/results/retrieval_<ngày giờ>.csv` (không lên GitHub).

`expected_chunk_ids` được gắn bằng cách tìm chuỗi đáp án trong nội dung đoạn (không dùng hệ thống tìm kiếm, tránh thiên lệch), sau đó loại tay các đoạn chỉ nhắc con số trong ngữ cảnh khác. Mọi đoạn chứa đáp án đều được gắn (một câu có thể có nhiều đoạn đúng ở nhiều tài liệu).

Q097–Q150 được soạn theo chiều ngược lại: chọn đoạn tài liệu **chưa có câu hỏi nào dùng tới** (ưu tiên tài liệu ít được hỏi: QĐ 1530 loét bàn chân, QĐ 2558 võng mạc, WHO muối thay thế, báo cáo THA toàn cầu, MedlinePlus), rồi viết câu hỏi và `reference_answer` chỉ từ nội dung đoạn đó; `expected_chunk_ids` là đoạn nguồn. Vì vậy các câu này có thể còn thiếu đoạn đúng ở tài liệu khác – cần rà soát.
