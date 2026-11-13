"""Tải tài liệu gốc theo danh mục data/catalog/documents.csv.

- Lấy link từ `download_url` (link file trực tiếp), nếu trống thì dùng `source_url`.
- Lưu vào `data/<raw_folder của cơ quan>/<document_id>.<pdf|xml|html>`.
- Ghi `downloaded_at`, `file_hash` (SHA-256) và chuyển `planned` → `collected`.
- Chạy lại nhiều lần được: tài liệu đã tải và còn đúng hash thì bỏ qua.

Cách chạy (từ thư mục gốc dự án):
    .venv/Scripts/python pipeline/download.py              # tải mọi tài liệu chưa tải
    .venv/Scripts/python pipeline/download.py --ids WHO-PEN-2020 MLP-DASH
    .venv/Scripts/python pipeline/download.py --force      # tải lại cả tài liệu đã có
    .venv/Scripts/python pipeline/download.py --local      # ghi nhận file tự tải bằng trình duyệt

Với trang chặn tải tự động: tải file bằng trình duyệt, đặt vào `data/<raw_folder>/<document_id>.pdf`
rồi chạy `--local` để tính hash và cập nhật danh mục.
"""

import argparse
import csv
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATALOG = DATA / "catalog" / "documents.csv"
ORGANIZATIONS = DATA / "catalog" / "organizations.csv"

# Trạng thái được phép tải. `superseded` vẫn tải để lưu vết, nhưng giữ nguyên trạng thái.
DOWNLOADABLE = {"planned", "collected", "superseded"}
# Chỉ thông tin phổ thông mới được lưu ở dạng trang web; tài liệu chuyên môn mà nhận về HTML
# thường là trang giới thiệu → cần điền `download_url` trỏ thẳng tới file.
HTML_ALLOWED_TYPES = {"patient_information"}
EXTENSIONS = ("pdf", "xml", "html")
HEADERS = {"User-Agent": "Mozilla/5.0 (MedRAG thesis downloader; contact: student project)"}
TIMEOUT = 120


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def detect_extension(content_type: str, body: bytes) -> str | None:
    if body.startswith(b"%PDF") or "application/pdf" in content_type:
        return "pdf"
    if "text/html" in content_type:
        return "html"
    if "xml" in content_type:
        return "xml"
    return None


def existing_file(folder: Path, doc_id: str) -> Path | None:
    for ext in EXTENSIONS:
        path = folder / f"{doc_id}.{ext}"
        if path.exists():
            return path
    return None


def record(row: dict, path: Path) -> None:
    row["file_hash"] = sha256(path)
    row["downloaded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if row["review_status"] == "planned":
        row["review_status"] = "collected"


def register_local(row: dict, folder: Path) -> str:
    """Ghi nhận file đã có sẵn trong thư mục raw (tự tải bằng trình duyệt)."""
    doc_id = row["document_id"]
    path = existing_file(folder, doc_id)
    if path is None:
        return f"BỎ QUA  {doc_id}: chưa có file trong {folder.relative_to(ROOT)}"
    if row["file_hash"] == sha256(path):
        return f"ĐÃ CÓ   {doc_id}: {path.relative_to(ROOT)}"
    record(row, path)
    return f"OK      {doc_id}: ghi nhận {path.relative_to(ROOT)}"


def download(row: dict, folder: Path, force: bool) -> str:
    """Tải một tài liệu, cập nhật `row` tại chỗ và trả về dòng thông báo."""
    doc_id = row["document_id"]
    url = row["download_url"] or row["source_url"]
    if not url:
        return f"BỎ QUA  {doc_id}: chưa có link"

    old = existing_file(folder, doc_id)
    if old and not force and row["file_hash"] == sha256(old):
        return f"ĐÃ CÓ   {doc_id}: {old.relative_to(ROOT)}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"LỖI     {doc_id}: {e}"

    ext = detect_extension(resp.headers.get("Content-Type", ""), resp.content)
    if ext is None:
        return f"LỖI     {doc_id}: không nhận ra loại file ({resp.headers.get('Content-Type')})"
    if ext == "html" and row["document_type"] not in HTML_ALLOWED_TYPES:
        return f"LỖI     {doc_id}: nhận về trang web thay vì file tài liệu → điền download_url"

    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{doc_id}.{ext}"
    path.write_bytes(resp.content)
    record(row, path)
    return f"OK      {doc_id}: {path.relative_to(ROOT)} ({len(resp.content) // 1024} KB)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", nargs="*", help="chỉ tải các document_id này")
    parser.add_argument("--force", action="store_true", help="tải lại cả tài liệu đã có")
    parser.add_argument("--local", action="store_true", help="không tải, chỉ ghi nhận file đã đặt sẵn trong data/raw")
    args = parser.parse_args()

    _, orgs = read_csv(ORGANIZATIONS)
    folders = {o["organization_id"]: DATA / o["raw_folder"] for o in orgs}
    fields, rows = read_csv(CATALOG)

    failed = 0
    for row in rows:
        if args.ids and row["document_id"] not in args.ids:
            continue
        if row["review_status"] not in DOWNLOADABLE:
            continue
        folder = folders.get(row["organization_id"])
        if folder is None:
            msg = f"LỖI     {row['document_id']}: organization_id '{row['organization_id']}' không có trong organizations.csv"
        elif args.local:
            msg = register_local(row, folder)
        else:
            msg = download(row, folder, args.force)
        failed += msg.startswith(("LỖI", "BỎ QUA"))
        print(msg, flush=True)
        write_csv(CATALOG, fields, rows)  # ghi sau mỗi tài liệu để không mất tiến độ khi bị ngắt

    print(f"\nXong. {failed} tài liệu chưa tải được.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
