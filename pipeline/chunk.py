"""Chia tài liệu đã tải thành các đoạn (chunk) có metadata → data/processed/chunks.jsonl.

- Đọc danh mục `data/catalog/documents.csv`, chỉ xử lý tài liệu `collected` / `pending_review` / `approved`.
- Trích văn bản bằng `extract.py`, chia theo mục: hết mục thì cắt (nếu đoạn đã đủ dài),
  mục dài thì cắt ở khoảng MAX_WORDS từ, hai đoạn liền nhau trong cùng mục chồng nhau ~OVERLAP_WORDS từ.
- `chunk_id` = `<document_id>#c<số thứ tự 4 chữ số>` – dùng chung cho Elasticsearch và Milvus.
- Ghi thêm `chunk_report.csv` (thống kê theo tài liệu) và đánh dấu đoạn đáng ngờ trong trường `flags`.

Cách chạy (từ thư mục gốc dự án):
    .venv/Scripts/python pipeline/chunk.py
    .venv/Scripts/python pipeline/chunk.py --ids MOH-QD3087-2020   # chỉ in thử, không ghi file
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from extract import Block, extract

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CATALOG = DATA / "catalog" / "documents.csv"
ORGANIZATIONS = DATA / "catalog" / "organizations.csv"
OUT_DIR = DATA / "processed"

CHUNKABLE = {"collected", "pending_review", "approved"}
MAX_WORDS = 450       # trần độ dài một đoạn
MIN_WORDS = 120       # hết mục mà đoạn còn ngắn hơn mức này thì gộp tiếp với mục sau
OVERLAP_WORDS = 50    # phần chồng giữa hai đoạn liền nhau trong cùng mục
METADATA_FIELDS = (
    "document_id", "title", "issuing_organization", "organization_id", "document_type",
    "jurisdiction", "target_population", "language", "publication_date", "source_url",
)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def find_file(folder: Path, doc_id: str) -> Path | None:
    for ext in ("pdf", "xml", "html"):
        path = folder / f"{doc_id}.{ext}"
        if path.exists():
            return path
    return None


def word_count(text: str) -> int:
    return len(text.split())


def split_long(text: str) -> list[str]:
    """Khối dài hơn MAX_WORDS → cắt theo câu (bảng thì theo dòng)."""
    parts = text.split("\n") if "\n" in text else re.split(r"(?<=[.!?;])\s+", text)
    pieces, current = [], []
    for part in parts:
        if current and word_count(" ".join(current + [part])) > MAX_WORDS:
            pieces.append(" ".join(current))
            current = []
        current.append(part)
    if current:
        pieces.append(" ".join(current))
    # câu quá dài (không có dấu câu) → cắt cứng theo số từ
    result = []
    for piece in pieces:
        words = piece.split()
        result.extend(" ".join(words[i:i + MAX_WORDS]) for i in range(0, len(words), MAX_WORDS))
    return result


def tail_overlap(text: str) -> str:
    """Lấy các câu cuối của đoạn trước, tổng khoảng OVERLAP_WORDS từ, để mở đầu đoạn sau."""
    sentences = re.split(r"(?<=[.!?;])\s+", text)
    taken: list[str] = []
    while sentences and word_count(" ".join(taken)) < OVERLAP_WORDS:
        taken.insert(0, sentences.pop())
    overlap = " ".join(taken)
    return overlap if word_count(overlap) <= OVERLAP_WORDS * 2 else ""


def build_chunks(blocks: list[Block]) -> list[dict]:
    chunks: list[dict] = []
    parts: list[str] = []
    meta = {"section": "", "page": None, "page_end": None, "new": True}

    def flush(keep_overlap: bool) -> None:
        body = "\n".join(parts).strip()
        # bỏ đoạn chỉ gồm tiêu đề (không có nội dung)
        if body and not all(p.endswith(":") or word_count(p) < 4 for p in parts):
            chunks.append({"text": body, "section_title": meta["section"],
                           "page_number": meta["page"], "page_end": meta["page_end"]})
        parts.clear()
        meta["new"] = True
        if keep_overlap and body:
            overlap = tail_overlap(body)
            if overlap:
                parts.append(overlap)

    for block in blocks:
        pieces = split_long(block.text) if word_count(block.text) > MAX_WORDS else [block.text]
        for piece in pieces:
            if block.is_heading and word_count("\n".join(parts)) >= MIN_WORDS:
                flush(keep_overlap=False)
            if parts and word_count("\n".join(parts + [piece])) > MAX_WORDS:
                flush(keep_overlap=not block.is_heading)
            if meta["new"]:  # khối đầu tiên của đoạn mới quyết định mục và trang
                meta.update(section=block.section, page=block.page, new=False)
            parts.append(piece)
            meta["page_end"] = block.page
    flush(keep_overlap=False)
    return chunks


GARBLED = re.compile("[\\u0250-\\u0390\\ufffd]")  # chừa chữ Hy Lạp (β, α) hợp lệ


def flags_for(text: str) -> list[str]:
    flags = []
    words = text.split()
    if len(words) < 60:
        flags.append("ngắn")
    numeric = sum(bool(re.search(r"\d", w)) for w in words)
    if "[Bảng]" in text or (words and numeric / len(words) > 0.3):
        flags.append("bảng/nhiều số")
    if len(GARBLED.findall(text)) >= 3:
        flags.append("ký tự lạ")
    return flags


def process(doc: dict, folder: Path) -> tuple[list[dict], str | None]:
    path = find_file(folder, doc["document_id"])
    if path is None:
        return [], "không tìm thấy file"
    blocks = extract(path, doc["organization_id"], doc.get("page_range", ""), doc["language"])
    records = []
    for i, chunk in enumerate(build_chunks(blocks), start=1):
        record = {"chunk_id": f"{doc['document_id']}#c{i:04d}"}
        record.update({k: doc.get(k, "") for k in METADATA_FIELDS})
        record["topic"] = [t for t in doc["topic"].split(";") if t]
        record.update(chunk)
        record["word_count"] = word_count(chunk["text"])
        record["flags"] = flags_for(chunk["text"])
        records.append(record)
    return records, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", nargs="*", help="chỉ xử lý các document_id này và in thử ra màn hình (không ghi file)")
    args = parser.parse_args()

    folders = {o["organization_id"]: DATA / o["raw_folder"] for o in read_csv(ORGANIZATIONS)}
    docs = [d for d in read_csv(CATALOG) if d["review_status"] in CHUNKABLE]
    if args.ids:
        docs = [d for d in docs if d["document_id"] in args.ids]

    all_records, report = [], []
    for doc in docs:
        records, error = process(doc, folders[doc["organization_id"]])
        if error:
            print(f"LỖI  {doc['document_id']}: {error}")
            continue
        sizes = [r["word_count"] for r in records] or [0]
        flagged = sum(bool(r["flags"]) for r in records)
        report.append({"document_id": doc["document_id"], "chunks": len(records), "min_words": min(sizes),
                       "avg_words": sum(sizes) // len(sizes), "max_words": max(sizes), "flagged": flagged})
        print(f"{doc['document_id']:26} {len(records):4} đoạn  từ: {min(sizes):3}–{max(sizes):3} (tb {sum(sizes) // len(sizes)})  đáng ngờ: {flagged}")
        all_records.extend(records)

    print(f"\nTổng: {len(all_records)} đoạn từ {len(report)} tài liệu.")
    if args.ids:
        for r in all_records:
            print(f"\n--- {r['chunk_id']} | {r['section_title'][:60]} | tr.{r['page_number']} | {r['word_count']} từ {r['flags']}")
            print(r["text"])
        return 0

    OUT_DIR.mkdir(exist_ok=True)
    with (OUT_DIR / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (OUT_DIR / "chunk_report.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(report)
    print(f"Đã ghi {(OUT_DIR / 'chunks.jsonl').relative_to(ROOT)} và chunk_report.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
