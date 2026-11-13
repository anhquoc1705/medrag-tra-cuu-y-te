# MedRAG – Chatbot tra cứu y tế có trích dẫn nguồn

Hệ thống hỗ trợ tư vấn và tra cứu y tế từ xa, tích hợp **Hybrid Search** (Elasticsearch BM25 + Milvus vector) và **vòng Guardrails** kiểm soát câu trả lời. Đây là đồ án tốt nghiệp ngành Công nghệ thông tin.

Hệ thống trả lời câu hỏi về **102 bệnh thường gặp**. Mỗi câu trả lời đều trích dẫn tài liệu y tế chính thống (Bộ Y tế, WHO, MedlinePlus…) và có thể bấm vào để xem đoạn gốc. Khi không đủ bằng chứng, hệ thống từ chối thay vì tự suy đoán.

> ⚠️ **Lưu ý y tế:** hệ thống chỉ cung cấp thông tin tham khảo từ tài liệu chính thống. Hệ thống **không** chẩn đoán, không kê đơn, không đưa liều thuốc cho từng người và không thay thế bác sĩ. Khi có dấu hiệu cấp cứu, hãy gọi **115** hoặc đến cơ sở y tế gần nhất.

## Tính năng chính

- **Hỏi đáp có trích dẫn:** câu trả lời gắn số [1], [2]… trỏ tới đoạn tài liệu gốc (tên tài liệu, cơ quan ban hành, mục, trang).
- **Hybrid Search:** kết hợp tìm theo từ khoá (BM25, có dịch câu hỏi sang tiếng Anh cho tài liệu tiếng Anh) và tìm theo ngữ nghĩa (vector bge-m3), ghép bằng Reciprocal Rank Fusion có trọng số.
- **Guardrails 3 lớp:**
  - **G1 – kiểm tra đầu vào:** phát hiện cấp cứu (luôn cảnh báo), câu hỏi ngoài phạm vi, đòi chẩn đoán/kê đơn, câu lách quy tắc (prompt injection).
  - **G2 – kiểm tra bằng chứng:** tài liệu tìm được không đủ gần câu hỏi thì từ chối.
  - **G3 – kiểm tra chéo đầu ra:** một LLM **khác** đối chiếu từng ý của câu trả lời với tài liệu được trích để tính Faithfulness; dưới ngưỡng thì sinh lại, vẫn không đạt thì từ chối.
- **Tài khoản:** đăng nhập bằng Google hoặc email. Người đăng nhập được lưu lịch sử hỏi đáp; khách vẫn hỏi được nhưng không lưu.
- **Trang quản trị:** thống kê, xem chi tiết từng hội thoại (quyết định G1/G2/G3), đổi cấu hình và mô hình lúc đang chạy, so sánh 2 cấu hình trên cùng câu hỏi, quản lý người dùng.

## Kiến trúc

```
Người dùng ── React (Vite) ──HTTP──► FastAPI
                                      │
             G1 kiểm tra đầu vào ◄────┤  (từ khoá cấp cứu + Llama Prompt Guard 2 + LLM phân loại)
                                      │
             Hybrid Search ◄──────────┤  Elasticsearch (BM25)  ┐
                                      │  Milvus (bge-m3)       ┴─► RRF
             G2 kiểm tra bằng chứng ◄─┤
                                      │
             LLM sinh câu trả lời ◄───┤  Qwen (Groq) | Llama 3.3 (Cloudflare) | Gemini
                                      │
             G3 kiểm tra chéo ◄───────┤  LLM khác LLM trả lời → Faithfulness → sinh lại / từ chối
                                      │
                                      └─► PostgreSQL (tài khoản, lịch sử, log Guardrails)
```

Sơ đồ chi tiết (PlantUML) nằm trong [docs/thiet-ke/](docs/thiet-ke/).

Có 4 cấu hình để so sánh trong phần đánh giá:

| Cấu hình | Mô tả |
|---|---|
| `llm_only` | LLM trả lời trực tiếp, không tìm tài liệu |
| `vector_rag` | RAG chỉ dùng tìm kiếm vector |
| `hybrid_rag` | RAG dùng Hybrid Search |
| `hybrid_rag_guard` | Hybrid Search + Guardrails G1/G2/G3 (cấu hình chính) |

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Giao diện | React 19, Vite, TypeScript |
| API | FastAPI (Python 3.14), SQLAlchemy |
| Tìm kiếm từ khoá | Elasticsearch 8.15 (BM25) |
| Tìm kiếm vector | Milvus 2.5 Standalone, mô hình nhúng BAAI/bge-m3 (chạy CPU) |
| Cơ sở dữ liệu | PostgreSQL 16 |
| LLM | Qwen 3.8 27B (Groq), Llama 3.3 70B (Cloudflare Workers AI), Gemini 3.8 Flash – qua LangChain, dùng gói miễn phí |
| Guardrails | Cross-Check nội bộ + Llama Prompt Guard 2 |
| Đánh giá | Bộ 150 câu hỏi (dev/test), Recall@k, MRR, nDCG, RAGAS |
| Hạ tầng | Docker Compose |

## Dữ liệu

- **102 bệnh** (danh sách trong [data/catalog/topics.csv](data/catalog/topics.csv)).
- **372 tài liệu** từ 6 nhóm nguồn: Bộ Y tế / Cục Quản lý Khám chữa bệnh, WHO, MedlinePlus (NLM), Phân hội Tăng huyết áp Việt Nam, Báo Sức khỏe & Đời sống (cơ quan ngôn luận của Bộ Y tế), các bệnh viện trung ương trực thuộc Bộ Y tế.
- **3.177 đoạn** (chunk), mỗi đoạn có metadata: tài liệu, cơ quan ban hành, mục, trang, chủ đề, phạm vi áp dụng (VN / quốc tế / Mỹ).

Repo chỉ chứa **danh mục** tài liệu ([data/catalog/](data/catalog/)), không chứa file gốc (PDF/HTML) vì bản quyền thuộc cơ quan ban hành. Có thể tải lại toàn bộ bằng `pipeline/download.py`.

## Cài đặt và chạy

### Yêu cầu

- Docker (Docker Desktop trên Windows, kèm WSL2)
- Python 3.14
- Node.js 24
- Khoảng 8 GB RAM trống. Lần chạy đầu tải mô hình bge-m3 (~2,3 GB).
- API key miễn phí: [Groq](https://console.groq.com/), [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/), [Google AI Studio](https://aistudio.google.com/) (Gemini)

### 1. Cấu hình

```bash
cp .env.example .env        # rồi điền API key, JWT_SECRET, ADMIN_EMAILS…
```

`.env` chứa key bí mật và **không** được đưa lên git.

### 2. Khởi động kho dữ liệu

```bash
docker compose up -d elasticsearch milvus postgres
```

### 3. Cài thư viện Python

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r backend/requirements.txt -r pipeline/requirements.txt
```

### 4. Chuẩn bị dữ liệu và lập chỉ mục

```bash
python pipeline/download.py     # tải tài liệu theo danh mục (chạy lại nhiều lần được)
python pipeline/chunk.py        # trích văn bản và chia đoạn → data/processed/chunks.jsonl
python pipeline/index.py        # lập chỉ mục vào Elasticsearch + Milvus (tạo vector trên CPU, mất vài giờ)
```

Một số trang chặn tải tự động: tải bằng trình duyệt rồi chạy `pipeline/download.py --local` (xem [data/README.md](data/README.md)).

### 5. Chạy backend và giao diện

```bash
cd backend && python -m uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev
```

Mở http://localhost:5173. Trang quản trị ở `/admin` (tài khoản có email nằm trong `ADMIN_EMAILS`). Tài liệu API tự sinh ở http://127.0.0.1:8000/docs.

## API chính

| Phương thức | Đường dẫn | Mô tả |
|---|---|---|
| `POST` | `/chat` | Hỏi đáp (trả câu trả lời, nguồn trích dẫn, quyết định Guardrails, thời gian từng bước) |
| `POST` | `/search` | Chỉ tìm kiếm (bm25 / vector / hybrid), có lọc metadata |
| `GET` | `/topics` | Danh sách bệnh hệ thống hỗ trợ |
| `GET` | `/health` | Kiểm tra kết nối Elasticsearch, Milvus, PostgreSQL |
| | `/auth/*` | Đăng ký, đăng nhập (email / Google), thông tin tài khoản |
| | `/conversations/*` | Lịch sử hỏi đáp của người dùng đã đăng nhập |
| | `/admin/*` | Thống kê, log, cấu hình, người dùng (chỉ quản trị viên) |

## Đánh giá

Bộ **150 câu hỏi** tự soạn ([eval/questions.jsonl](eval/questions.jsonl)) gồm câu cần trả lời, câu không có đáp án, câu cấp cứu, câu đòi chẩn đoán/kê đơn và câu lách quy tắc. Bộ câu hỏi được chia **dev (50)** để tinh chỉnh và **test (100)** để chấm điểm cuối. Không có câu hỏi hay hồ sơ bệnh nhân thật.

```bash
python eval/retrieval_eval.py --split test                                   # chất lượng truy xuất
python eval/guard_eval.py --split test --provider groq --configs hybrid_rag_guard   # đầu-cuối có Guardrails
```

Chi tiết trong [eval/README.md](eval/README.md). Kết quả đánh giá chính thức sẽ được cập nhật sau khi hoàn thành.

## Cấu trúc thư mục

```
backend/            API FastAPI
  app/search.py       Hybrid Search (BM25 + vector + RRF)
  app/rag.py          luồng RAG, 4 cấu hình
  app/guardrails.py   G1 / G2 / G3
  app/llm.py          gọi LLM (Groq, Cloudflare, Gemini), giới hạn thời gian chờ, yêu cầu dự phòng
  app/prompts.py      câu lệnh cho LLM
frontend/           giao diện React
pipeline/           tải → trích xuất → chia đoạn → lập chỉ mục
data/catalog/       danh mục tài liệu, cơ quan ban hành, chủ đề
eval/               bộ câu hỏi và script đánh giá
docs/thiet-ke/      sơ đồ kiến trúc, mô hình miền, use case
docker-compose.yml  Elasticsearch, Milvus, PostgreSQL, backend
```

## Tác giả

- **Nguyễn Anh Quốc**, lớp CNTT K22A
- GVHD: **Nguyễn Thu Phương**
