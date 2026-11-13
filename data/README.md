# Dữ liệu tri thức

Phạm vi: **102 bệnh thường gặp ở người trưởng thành** (danh sách trong `catalog/topics.csv`) – tim mạch, chuyển hoá – nội tiết, hô hấp, truyền nhiễm, tiêu hoá, thận – tiết niệu, cơ xương khớp, thần kinh – tâm thần, ung thư, da liễu, mắt – tai – răng, sản phụ khoa…

Hiện có (12/11/2026): **372 tài liệu** đang dùng → **3.177 đoạn** (chunk) có metadata (2.234 đoạn tiếng Việt, 943 đoạn tiếng Anh); 102/102 bệnh có tài liệu tiếng Việt.

| Nguồn (`organization_id`) | Phạm vi | Số tài liệu |
|---|---|---:|
| Bộ Y tế / Cục Quản lý Khám chữa bệnh (`moh`) | VN | 52 |
| Báo Sức khỏe & Đời sống – cơ quan ngôn luận của Bộ Y tế (`skds`) | VN | 137 |
| Bệnh viện trung ương trực thuộc Bộ Y tế (`bvtw`) | VN | 20 |
| Phân hội Tăng huyết áp Việt Nam (`vsh`) | VN | 1 |
| WHO (`who`) | INT | 56 |
| MedlinePlus – NLM (`medlineplus`) | US | 106 |

Tài liệu chuyên môn (phác đồ, hướng dẫn chẩn đoán – điều trị) chủ yếu đến từ Bộ Y tế và WHO; bài báo SKĐS và bệnh viện bổ sung kiến thức phổ thông tiếng Việt cho các bệnh chưa có phác đồ truy cập được.

## Cấu trúc

```
data/
  catalog/documents.csv      # metadata từng tài liệu (1 dòng / tài liệu)
  catalog/organizations.csv  # cơ quan ban hành: jurisdiction, mức ưu tiên, thư mục raw
  catalog/topics.csv         # danh sách chủ đề (bệnh) hệ thống hỗ trợ
  raw/moh/                # Bộ Y tế, Cục Quản lý KCB, Cục Quản lý Dược   (jurisdiction = VN)
  raw/who/                # WHO (IRIS, guidelines)                        (jurisdiction = INT)
  raw/medlineplus/        # MedlinePlus / NLM                             (jurisdiction = US)
  raw/vsh/                # Hội Tim mạch / Phân hội THA Việt Nam          (jurisdiction = VN)
  raw/skds/               # Báo Sức khỏe & Đời sống (Bộ Y tế)             (jurisdiction = VN)
  raw/bvtw/               # Bệnh viện trung ương trực thuộc Bộ Y tế       (jurisdiction = VN)
  processed/              # văn bản đã trích xuất + chunks.jsonl (sinh tự động)
```

## Quy tắc

- Chỉ tải từ website của cơ quan ban hành. Không lấy bản sao trên trang khác.
- Tên file: `<document_id>.pdf`, ví dụ `MOH-QD5481-2020.pdf`.
- Ghi đủ các cột trong `documents.csv`; `file_hash` = SHA-256 của file gốc.
- `organization_id`: khoá sang `organizations.csv` (quyết định thư mục `raw/` và mức ưu tiên khi các nguồn mâu thuẫn).
- `topic`: một hoặc nhiều `topic_id` trong `topics.csv`, ngăn cách bằng `;` (ví dụ `diabetes_t2;hypertension`).
- `jurisdiction`: `VN` | `INT` | `US`
- `document_type`: `guideline` | `policy` | `technical_report` | `statistics` | `handbook` | `patient_information` | `legal`
- `target_population`: `health_workers` (tài liệu chuyên môn) | `general_public` (thông tin phổ thông)
- Ngày: `YYYY-MM-DD`; nếu chưa xác minh được ngày cụ thể thì ghi `YYYY-MM` hoặc `YYYY`.
- `review_status`: `planned` (đã vào danh mục, chưa tải) → `collected` → `pending_review` → `approved` / `rejected`; khi bị thay thế: `superseded` → `archived`. Bản chính thức chỉ lập chỉ mục tài liệu `approved` (`index.py --approved-only`); trong lúc phát triển đang lập chỉ mục cả tài liệu `collected` (chưa tài liệu nào được duyệt).
- Kiểm tra hiệu lực văn bản Bộ Y tế trên https://vbpl.vn/boyte/ trước khi duyệt.

## Mở rộng dữ liệu

Code không gắn cứng tên bệnh hay tên cơ quan; mọi thứ đọc từ 3 file trong `catalog/`.

- **Thêm tài liệu cho chủ đề đã có:** thêm 1 dòng vào `documents.csv` (`review_status = planned`) → chạy lại script tải + lập chỉ mục.
- **Thêm cơ quan ban hành mới:** thêm 1 dòng vào `organizations.csv` (đặt `priority`, `raw_folder`) → dùng `organization_id` đó trong `documents.csv`.
- **Thêm bệnh mới** (ví dụ bệnh thận mạn): thêm 1 dòng vào `topics.csv` → thêm tài liệu với `topic` mới → bổ sung câu hỏi đánh giá cho chủ đề đó. Bộ lọc chủ đề (G1), câu lệnh LLM và giao diện đọc `topics.csv` (từ 12/11/2026) nên không cần sửa code – chỉ khởi động lại backend; nếu bệnh có dấu hiệu cấp cứu riêng thì bổ sung `EMERGENCY_PATTERNS` trong `backend/app/guardrails.py`.

## Nguồn ưu tiên

1. Bộ Y tế / Cục Quản lý Khám, chữa bệnh: https://kcb.vn/phac-do , https://kcb.vn/thu-vien-tai-lieu
2. Cục Quản lý Dược: https://dav.gov.vn/
3. WHO: https://www.who.int/publications/who-guidelines , https://iris.who.int/
4. MedlinePlus: https://medlineplus.gov/ (phần giải thích phổ thông)
5. Khuyến cáo hội chuyên môn (VSH/VNHA): chỉ dùng bổ sung khi Bộ Y tế chưa có hướng dẫn mới
6. Báo Sức khỏe & Đời sống (https://suckhoedoisong.vn/) và bệnh viện trung ương trực thuộc Bộ Y tế: bài phổ biến kiến thức tiếng Việt, chỉ dùng cho bệnh chưa có phác đồ truy cập được; loại bài quảng cáo / tài trợ (có cụm "thực phẩm bảo vệ sức khỏe", "không phải là thuốc")

## Tải tài liệu

```
.venv/Scripts/python pipeline/download.py          # tải mọi tài liệu chưa tải (chạy lại nhiều lần được)
.venv/Scripts/python pipeline/download.py --local  # ghi nhận file tự tải bằng trình duyệt
```

- `download_url` (không bắt buộc): link trực tiếp tới file; `source_url` là trang để trích dẫn. Script ưu tiên `download_url`.
- Tài liệu chuyên môn phải là file (PDF/XML). Nếu link trả về trang web, script báo lỗi thay vì lưu trang giới thiệu. Chỉ `patient_information` được lưu dạng HTML.
- Trang chặn tải tự động: tải bằng trình duyệt, đặt vào `data/<raw_folder>/<document_id>.pdf`, rồi chạy `--local`.

## Trích văn bản và chia đoạn

```
.venv/Scripts/python pipeline/chunk.py                         # → data/processed/chunks.jsonl + chunk_report.csv
.venv/Scripts/python pipeline/chunk.py --ids MOH-QD3087-2020   # in thử các đoạn của 1 tài liệu, không ghi file
```

- Xử lý tài liệu `collected` / `pending_review` / `approved` (bỏ `superseded`, `rejected`).
- `page_range` (không bắt buộc, ví dụ `15-34;57-64`): chỉ lấy các trang này của PDF – dùng để bỏ phần ngoài phạm vi (bệnh khác, hồ sơ quốc gia, phụ lục hành chính).
- Tự bỏ: trang mục lục / ban biên soạn / chữ viết tắt / tài liệu tham khảo / trang quyết định ("Nơi nhận"), dòng lặp ở đầu–chân trang, dòng lỗi font, dãy số của biểu đồ.
- Sửa: Unicode NFC, "Ƣ/ƣ" → "Ư/ư", âm tiết tiếng Việt bị pypdf tách đôi ("đi ều" → "điều").
- Chia theo mục; tối đa ~450 từ/đoạn, mục ngắn hơn 120 từ gộp với mục sau, chồng ~50 từ giữa hai đoạn liền nhau trong cùng mục.
- `chunk_id` = `<document_id>#c<4 chữ số>`; `flags` đánh dấu đoạn cần xem kỹ (`ngắn`, `bảng/nhiều số`, `ký tự lạ`).

## Lập chỉ mục (Elasticsearch + Milvus)

Cần Docker đang chạy (`docker compose up -d elasticsearch milvus postgres`) và file `.env` (sao từ `.env.example`).

```
.venv/Scripts/python pipeline/index.py                   # lập chỉ mục mọi đoạn trong chunks.jsonl
.venv/Scripts/python pipeline/index.py --approved-only   # chỉ tài liệu approved (bản chính thức)
.venv/Scripts/python pipeline/index.py --query "Huyết áp mục tiêu là bao nhiêu?"   # thử tìm trên 2 kho
```

- Mỗi lần chạy xoá và tạo lại index Elasticsearch `medical_chunks` và collection Milvus `medical_chunks`; hai kho dùng chung `chunk_id`.
- Elasticsearch (BM25): trường `text`, `section_title`, `title` phân tích theo âm tiết, trường phụ `.shingle` lưu cặp âm tiết ("huyết áp"); metadata dạng keyword để lọc.
- Milvus: vector bge-m3 1024 chiều (chuẩn hoá, COSINE, chỉ mục HNSW) tạo từ "tên tài liệu + nội dung đoạn"; kèm `topic`, `jurisdiction`, `language`, `document_id`, `organization_id`, `target_population` để lọc.
- Mô hình bge-m3 tải một lần về thư mục `HF_HOME` trong `.env`. Tạo vector trên CPU (i5-1235U): 556 đoạn ~23 phút; 3.177 đoạn ~2 giờ 24 phút.

## Quá trình mở rộng dữ liệu

| Thời điểm | Số bệnh | Tài liệu | Đoạn | Nội dung |
|---|---:|---:|---:|---|
| 07/10/2026 | 2 | 30 | 556 | Đái tháo đường típ 2 + tăng huyết áp (phạm vi ban đầu) |
| 12/11/2026 – lần 1 | 52 | 107 → 192 | 897 → 2.195 | +50 bệnh phổ thông: MedlinePlus, WHO, sách hướng dẫn Bộ Y tế (tách theo chương), bài SKĐS / bệnh viện |
| 12/11/2026 – lần 2 | 102 | 372 | 3.177 | +50 bệnh (ung thư, truyền nhiễm, tâm thần, da liễu, sản phụ khoa…), cùng các nguồn trên |

Mỗi lần mở rộng, đoạn cũ giữ nguyên mã và nội dung nên bộ câu hỏi đánh giá vẫn trỏ đúng. Các mục dưới đây ghi chi tiết từng đợt.

### Mở rộng lần 1: 50 bệnh phổ thông (12/11/2026)

- `topics.csv`: 2 → **52 bệnh** (thêm 50: tim mạch – chuyển hoá – nội tiết, hô hấp, truyền nhiễm, tiêu hoá, thận – tiết niệu, cơ xương khớp, thần kinh – tâm thần, thiếu máu, chàm, đục thuỷ tinh thể, glôcôm).
- `documents.csv`: +77 tài liệu thông tin cho người bệnh – 50 trang MedlinePlus (mỗi bệnh 1 trang) + 27 tờ thông tin WHO (`WHO-FS-*`); `WHO-FS-OSTEOPOROSIS` bị `rejected` vì trang không có nội dung. Tổng 107 dòng.
- `chunks.jsonl`: 556 → **897 đoạn** (+341); 556 đoạn cũ giữ nguyên mã và nội dung (đã kiểm tra) nên bộ câu hỏi đánh giá vẫn trỏ đúng.
- Nhiều trang MedlinePlus chỉ có phần tóm tắt (150–300 từ) → 1 đoạn/bệnh: đủ cho thông tin cơ bản, chưa có phác đồ điều trị chi tiết như 2 bệnh gốc.
- 50 bệnh mới **chưa được đánh giá** (SV quyết định tạm bỏ qua) và chưa duyệt nội dung (`collected`).
- Phạm vi Guardrails (G1), câu lệnh và giao diện đọc danh sách bệnh từ `topics.csv` (`backend/app/prompts.py`, API `GET /topics`) – thêm bệnh không cần sửa code, chỉ cần khởi động lại backend.

### Danh mục ban đầu (07/10/2026)

30 dòng trong `catalog/documents.csv`: 9 Bộ Y tế (VN) + 1 bản cũ `superseded` (3319/QĐ-BYT, giữ để truy vết, không lập chỉ mục), 1 khuyến cáo VSH/VNHA 2022 (VN, bổ sung 06/10/2026 vì HD THA của Bộ Y tế mới nhất là 2010), 10 WHO (INT), 9 MedlinePlus (US).

Đã tải 27/30 (`collected`). Tất cả PDF đều có lớp chữ.

| document_id | Vấn đề |
|---|---|
| MOH-QD5481-2020, MOH-QD1353-2021 | Link PDF trên daithaoduong.kcb.vn lỗi (chuyển hướng 404). Có bản trên cổng Sở Y tế Bắc Giang (syt.bacgiang.gov.vn) nhưng máy không kết nối được → tải bằng trình duyệt + `--local` |
| MOH-QD3312-2024 | `rejected` (07/10/2026): không có bản PDF trên trang chính thức; cảnh báo đột quỵ dùng MLP-STROKE |
| MOH-QD5904-2019 | Bản sao trên cổng Sở Y tế Đắk Lắk (yte.daklak.gov.vn), sinh viên đã xem và chấp nhận 07/10/2026 (trang vncdc.gov.vn hết hạn chứng chỉ, không có file). Font cũ: chữ "Ư/ư" bị trích thành "Ƣ/ƣ" → chuẩn hoá khi trích văn bản |
| VSH-HTN-2022 | Bản tiếng Anh "Highlights" (open access, CC BY-NC); tải toàn văn XML qua Europe PMC (PMC chặn tải tự động) |
| MOH-QD1530-2023 | File PDF ký số không ghi ngày → xác minh ngày ban hành trên vbpl.vn |
| MOH-QD3798-2017, MOH-QD3192-2010 | Kiểm tra còn hiệu lực trên vbpl.vn (văn bản cũ) |
| WHO-DMMEDS-2018, WHO-LSSS-2025, WHO-DMCLASS-2019 | Bổ sung ISBN (có trong file đã tải) |
