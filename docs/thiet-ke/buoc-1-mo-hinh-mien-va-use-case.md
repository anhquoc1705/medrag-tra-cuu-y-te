# ICONIX – Bước 1: Mô hình miền và Use case

Lập từ code hiện tại (kỹ nghệ ngược), ngày 03/11/2026. Sơ đồ: `01-mo-hinh-mien.puml`, `02-use-case.puml`.

## 1. Mô hình miền

| Lớp | Ý nghĩa | Nguồn trong code |
|---|---|---|
| Người dùng | Tài khoản đăng nhập bằng email/mật khẩu hoặc Google; có thể bị khoá | `backend/app/db.py: User` (bảng `users`) |
| Quản trị viên | Người dùng có email nằm trong danh sách quản trị | `backend/app/auth.py: is_admin()` (biến `ADMIN_EMAILS` trong `.env`) |
| Hội thoại | Một cuộc hỏi đáp của người đã đăng nhập (khách không được lưu) | `db.py: Conversation` (bảng `conversations`) |
| Lượt hỏi đáp | Một câu hỏi trong hội thoại cùng kết quả trả lời | `db.py: Message` (bảng `messages`) |
| Câu trả lời | Nội dung trả lời, cờ từ chối / cấp cứu, lời khuyến cáo | `backend/app/rag.py: answer()` – lưu trong `Message.result` |
| Nguồn trích dẫn | Đoạn văn bản được đưa cho LLM, đánh số [n] để trích dẫn | `rag.py: result["sources"]`, `result["cited"]` |
| Kết quả kiểm soát an toàn | Quyết định Guardrails, Faithfulness, số lần sinh lại | `rag.py: result["guard"]`, `backend/app/guardrails.py` |
| Nhật ký hỏi đáp | Bản ghi mọi câu hỏi (cả khách, ẩn danh) phục vụ thống kê | `db.py: ChatLog` (bảng `chat_logs`) |
| Cấu hình hệ thống | Cấu hình chạy do quản trị đổi (LLM, top-k, ngưỡng…) | `db.py: AppSetting`, `backend/app/settings_store.py: RuntimeSettings` |
| Tài liệu | Văn bản y tế chính thống trong kho tri thức | `data/catalog/documents.csv` |
| Đoạn văn bản | Phần nhỏ của tài liệu, đã lập chỉ mục BM25 + vector | `data/processed/chunks.jsonl`, chỉ mục Elasticsearch + Milvus (`backend/app/search.py`) |
| Cơ quan ban hành | Bộ Y tế, WHO, MedlinePlus, hội chuyên môn | `data/catalog/organizations.csv` |
| Chủ đề bệnh | Đái tháo đường típ 2, tăng huyết áp… | `data/catalog/topics.csv` |

## 2. Tác nhân

| Tác nhân | Mô tả | Nguồn trong code |
|---|---|---|
| Khách | Chưa đăng nhập: hỏi đáp được, lịch sử chỉ giữ tạm trên trình duyệt | `chat_api.py: chat()` với `user = None` |
| Người dùng | Đã đăng nhập: có lịch sử lưu trên máy chủ | `auth.py: require_user()` |
| Quản trị viên | Vào trang `/admin` | `auth.py: require_admin()` |
| Google | Xác thực đăng nhập Google | `auth.py: verify_google()` |
| Dịch vụ LLM | Qwen (Groq), Llama 3.3 (Cloudflare), Gemini | `backend/app/llm.py` |

## 3. Danh sách use case

| Mã | Tên | Tác nhân | Giao diện | API |
|---|---|---|---|---|
| UC01 | Đặt câu hỏi tra cứu | Khách | `ChatPage.tsx`, `AnswerCard.tsx` | `POST /chat` |
| UC02 | Xem nguồn trích dẫn (mở rộng UC01) | Khách | `SourcePanel.tsx` | – (dữ liệu có sẵn trong kết quả `/chat`) |
| UC03 | Đăng ký tài khoản | Khách | `LoginDialog.tsx` | `POST /auth/check-email`, `POST /auth/register` |
| UC04 | Đăng nhập (email hoặc Google) | Khách, Google | `LoginDialog.tsx` | `POST /auth/login`, `POST /auth/google` |
| UC05 | Đăng xuất | Người dùng | `ChatPage.tsx` (nút đăng xuất), `auth.tsx: signOut` | – (xoá token phía trình duyệt) |
| UC06 | Xem lịch sử hỏi đáp | Người dùng | `ChatPage.tsx` (thanh bên) | `GET /conversations`, `GET /conversations/{id}` |
| UC07 | Xoá cuộc hỏi đáp | Người dùng | `ChatPage.tsx: deleteConv` | `DELETE /conversations/{id}` |
| UC08 | Xem thống kê tổng quan | Quản trị viên | `admin/Overview.tsx` | `GET /admin/stats` |
| UC09 | Tra cứu nhật ký hỏi đáp | Quản trị viên | `admin/Logs.tsx` | `GET /admin/logs`, `GET /admin/logs/{id}` |
| UC10 | Xoá nhật ký hỏi đáp (mở rộng UC09) | Quản trị viên | `admin/Logs.tsx` | `POST /admin/logs/delete` |
| UC11 | Cấu hình hệ thống | Quản trị viên | `admin/Config.tsx` | `GET/PUT /admin/settings`, `POST /admin/settings/reset` |
| UC12 | So sánh cấu hình | Quản trị viên | `admin/Config.tsx` | `POST /admin/compare` |
| UC13 | Khoá / mở khoá người dùng | Quản trị viên | `admin/Users.tsx` | `GET /admin/users`, `PATCH /admin/users/{id}` |

Không đưa vào use case: `POST /search` (`search_api.py`) và `GET /health` – dùng cho đánh giá và kiểm tra kỹ thuật, không có trên giao diện.

## 4. Phát hiện cần SV quyết định

1. **Nạp / duyệt tài liệu không có giao diện** – làm bằng script (`pipeline/download.py`, chia đoạn, `pipeline/index.py`). Chọn: (a) thêm tác nhân "Người quản trị dữ liệu" + use case "Nạp và lập chỉ mục tài liệu" thực hiện qua script, hoặc (b) không đưa vào sơ đồ, chỉ mô tả ở phần cài đặt.
2. **Đề cương mục 5 nhắc "hỗ trợ bệnh nhân và bác sĩ"** – hệ thống không có vai trò bác sĩ riêng. Cần thống nhất cách gọi tác nhân (Người dùng chung) hoặc ghi vào phần sửa đề cương.
3. **Không có chức năng quên mật khẩu / đổi mật khẩu** – thêm vào code hay ghi vào hạn chế.
4. **Quản trị viên được chỉ định qua `.env`** (không có chức năng phân quyền trên giao diện) – ghi rõ trong đặc tả.
5. **Khách bắt đầu cuộc hỏi đáp mới / người dùng tiếp tục một cuộc cũ** đang gộp vào UC01 (luồng phụ), không tách use case riêng.
