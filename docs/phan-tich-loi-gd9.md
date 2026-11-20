# Phân tích lỗi GĐ 9 – bộ 50 câu test (20/11/2026)

Nguồn số liệu: `eval/results/gd9_test50_{qwen,llama,gemini35lite}.jsonl` (câu trả lời, 400/400 lượt),
`eval/results/ragas_gd9.jsonl` + `ragas_gd9_summary.csv` (RAGAS, 448 mục, giám khảo `gemini-3.1-flash-lite`).
Chỉ xét 32 câu `expected_behavior = answer`. Bảng RAGAS chính: xem PROGRESS.md (20/11 18:20).

## 1. Từ chối nhầm câu lẽ ra phải trả lời

| Câu | Nội dung | Bị từ chối ở | Nguyên nhân |
|---|---|---|---|
| Q029 | WHO khuyến cáo gì về muối thay thế ít natri? | Qwen + Guard, Llama + Guard | **G1 xếp `out_of_scope`** |
| Q123 | Mỗi năm bao nhiêu ca tử vong do ăn quá nhiều natri? | Guard của cả 3 LLM | **G1 xếp `out_of_scope`** |
| Q126 | Theo WHO nên bổ sung kali từ nguồn nào? | Guard của cả 3 LLM | **G1 xếp `out_of_scope`** |
| Q125 | Phụ nữ mang thai có nên dùng muối thay thế ít natri? | Guard của cả 3 LLM (G1); Qwen vector / hybrid (LLM trả "không có thông tin") | G1 + câu hỏi mập mờ |
| Q001 | Huyết áp bao nhiêu là THA độ 2? | Qwen + Guard (`no_info`) | LLM tự trả "không có thông tin" dù tài liệu có (lần sinh lại sau G3 0,75) |
| Q150 | Vì sao kiểm soát HA giúp phòng biến chứng mắt, bàn chân ở người ĐTĐ? | Gemini + Guard (`no_info`) | Tìm kiếm thiếu đoạn đúng (mục 3) |

- **Nguyên nhân chính (4/6 câu, 12/16 lượt từ chối nhầm): bộ phân loại đầu vào G1 coi câu hỏi về muối / natri / kali là
  "ngoài phạm vi"**: câu không nhắc tên bệnh nào, chỉ nói về dinh dưỡng, dù tài liệu WHO về giảm muối (`WHO-LSSS-2025`)
  nằm trong kho và đây là nội dung phòng ngừa tăng huyết áp. Cấu hình không có Guardrails trả lời được (trừ Q125).
- Q125: đáp án mẫu là "chưa có nghiên cứu nên không kết luận được". LLM trả "tài liệu không đủ thông tin" thì về ý
  gần giống đáp án mẫu, nhưng vẫn bị tính là từ chối. Có thể xem đây là câu gán nhãn chưa rõ.
- **Hướng sửa (chưa làm – không chỉnh hệ thống theo bộ test):** bổ sung vào câu lệnh của G1 rằng câu hỏi về lối sống /
  dinh dưỡng liên quan tới phòng và điều trị 102 bệnh (muối, natri, kali, hút thuốc, rượu bia…) là trong phạm vi; kiểm
  tra trên bộ dev trước, nếu chạy lại bộ test thì báo cáo riêng là kết quả "sau khi sửa".

## 2. Faithfulness thấp: G3 và RAGAS chấm khác nhau

| Mô hình (Hybrid + Guard) | Số câu | G3 trung bình | RAGAS trung bình | RAGAS < 0,8 | G3 < 1 |
|---|---|---|---|---|---|
| Qwen | 27 | 0,982 | 0,978 | 1 | 4 |
| Llama 3 | 28 | **1,000** | **0,919** | 4 | 0 |
| Gemini 3.5 Lite | 28 | 0,993 | 0,996 | 0 | 2 |

- Với Qwen và Gemini, G3 (bên kiểm tra chéo trong hệ thống) và RAGAS gần như trùng nhau → G3 đáng tin.
- **Với Llama 3, G3 chấm 1,0 cho cả 28 câu nhưng RAGAS chỉ 0,919**: các câu Q027 (0,50), Q134 (0,58), Q146 (0,50),
  Q150 (0,14). Ví dụ Q150: Llama thêm các ý chung chung không có trong 5 đoạn ("bệnh lý thần kinh", "cải thiện chất
  lượng cuộc sống") và gắn số trích dẫn [2] [3] [4] cho các ý đó. G3 của Llama dùng Qwen (Groq) làm bên kiểm tra – chấm
  dễ hơn với các ý "nghe hợp lý" có kèm số trích dẫn. → Hạn chế của G3: một LLM kiểm tra, ngưỡng theo ý; nên nêu trong
  Chương 5, hướng phát triển: kiểm tra bằng 2 LLM hoặc mô hình NLI chuyên dụng.
- Các câu tổng hợp Q149, Q150 có Faithfulness thấp ở nhiều cấu hình (Qwen hybrid 0,70 / 0,75, Qwen + Guard Q150 0,67)
  do thiếu tài liệu (mục 3) → LLM bù bằng kiến thức chung.

## 3. Tìm kiếm không lấy được đoạn đúng (Context Precision thấp)

| Câu | Loại | Vector | Hybrid | Ghi chú |
|---|---|---|---|---|
| Q134 | direct | 0,00 | 0,00 | đoạn chuẩn `WHO-HTNREPORT-2023#c0002` không vào top 5; các đoạn khác cùng báo cáo chen lên |
| Q143 | direct | 0,00 | 0,00 | đoạn chuẩn là MedlinePlus (`MLP-HIGHBLOODPRESSURE`), top 5 toàn đoạn của QĐ 3192 Bộ Y tế |
| Q149 | synthesis | 0,00 | 0,00 | cần 3 đoạn từ 3 tài liệu (ĐTĐ, đột quỵ, nhồi máu cơ tim); hybrid lấy được 1/3 |
| Q150 | synthesis | 0,00 | 0,00 | cần 3 đoạn; cả hai chế độ lấy được 0/3 đoạn chuẩn |
| Q016 | direct | 0,33 | 0,00 | **hybrid kém hơn vector**: vector có `MOH-QD3192-2010#c0007`, BM25 đẩy các đoạn QĐ 5904 lên |
| Q018, Q100, Q145, Q146 | direct | 0,25–0,33 | 0,70–1,00 | hybrid tốt hơn rõ (BM25 khớp thuật ngữ / bản dịch tiếng Anh) |

- Tổng thể hybrid tốt hơn (0,742 so với 0,667) nhưng **không phải câu nào cũng tốt hơn** (Q016).
- **Câu tổng hợp nhiều bệnh** (synthesis) là điểm yếu: top_k = 5 không đủ chỗ cho đoạn từ nhiều tài liệu. Hướng phát
  triển: tách câu hỏi thành câu con (query decomposition) hoặc tăng top_k cho câu nhắc nhiều bệnh.
- Context Precision theo mã đoạn (IDBased, ~0,21) thấp do cách tính (số đoạn chuẩn / 5 đoạn lấy về, mỗi câu chỉ có 1–3
  đoạn chuẩn) – chỉ dùng để tham khảo; số chính là Context Precision do LLM chấm.

## 4. Answer Relevancy

Không có câu nào dưới 0,75; mọi cấu hình 0,919–0,949, kể cả LLM thuần. Chỉ số này đo câu trả lời có bám câu hỏi hay
không, **không đo đúng / sai** → không dùng để kết luận RAG tốt hơn LLM thuần. Độ đúng của LLM thuần cần so với đáp án
mẫu (chưa có chỉ số này trong đề cương; có thể thêm RAGAS `FactualCorrectness` nếu còn thời gian / hạn mức).

## 5. Hạn chế của chính phép đo

- Giám khảo là một LLM miễn phí (`gemini-3.1-flash-lite`), câu lệnh RAGAS bằng tiếng Anh chấm câu trả lời tiếng Việt.
- Đáp án mẫu và mã đoạn chuẩn do nhóm soạn, **chưa được chuyên gia y tế duyệt** (`reviewed_by` trống).
- Mẫu nhỏ: 50 câu test (32 câu cần trả lời) vì hạn mức API miễn phí; chênh lệch 0,01–0,02 giữa các cấu hình không có ý
  nghĩa thống kê.
- 5 đoạn tài liệu được dựng lại bằng cách tìm kiếm lại (khớp 374/379 = 98,7% đoạn được trích trong lần chạy thật).
