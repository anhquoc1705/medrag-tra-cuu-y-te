"""Trích văn bản từ tài liệu gốc (PDF / HTML / XML) thành các khối có tiêu đề mục và số trang.

Mỗi khối (`Block`) là một đoạn văn liền mạch, kèm `section` (tiêu đề mục gần nhất) và `page`
(số trang PDF, tính từ 1; None với HTML/XML). Việc chia thành chunk nằm ở `chunk.py`.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf import _font as _pypdf_font

_FONTTOOLS_INSTALLED = _pypdf_font.HAS_FONTTOOLS  # fontTools có cài không (cài 12/11/2026 cho sách 3879/QĐ-BYT)


@dataclass
class Block:
    text: str
    section: str
    page: int | None
    is_heading: bool = False


# ---------------------------------------------------------------- làm sạch chung

# Font cũ trong một số PDF Bộ Y tế (ví dụ QĐ 5904) mã hoá "Ư/ư" thành "Ƣ/ƣ".
CHAR_FIXES = str.maketrans({"Ƣ": "Ư", "ƣ": "ư", " ": " ", "­": "", "ﬁ": "fi", "ﬂ": "fl"})


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(CHAR_FIXES)
    return re.sub(r"[ \t]+", " ", text).strip()


# pypdf hay chèn khoảng trắng giữa một âm tiết tiếng Việt có dấu: "đi ều", "huy ết", "l à".
_MARKED_VOWELS = "ăâêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
_VOWELS = "aeiouy" + _MARKED_VOWELS
_SPLIT_SYLLABLE = re.compile(rf"(\w+) ([{_MARKED_VOWELS}]\w*)", re.I)
_CONSONANT_ONLY = re.compile(r"^(ngh|ng|nh|ch|gh|gi|kh|ph|qu|th|tr|[bcdđghklmnpqrstvx])$", re.I)
# Từ bắt đầu bằng nguyên âm có dấu, đứng riêng được → không ghép vào từ trước ("hạ áp", "là ở").
_STANDALONE = {
    "ở", "ức", "ổn", "ứng", "ít", "ăn", "uống", "ông", "ấy", "ảnh", "ẩn", "ốm", "ưu", "ước", "ướt", "ấm",
    "ổ", "ống", "ớt", "ủ", "ồ", "ừ", "ạ", "ý", "ẩm", "ưa", "ồn", "ổi", "ứ", "ấn", "ắt", "ơn", "ấp", "ầm",
    "ẩu", "áp", "âm", "ánh", "ác", "áo", "ách", "ảo", "ẩy", "ải", "ối", "ỏi",
}


def repair_vietnamese_spacing(text: str) -> str:
    def join(m: re.Match) -> str:
        left, right = m.group(1), m.group(2)
        if _CONSONANT_ONLY.match(left):
            return left + right
        if (len(left) <= 4 and left.isalpha() and not left.isupper()
                and left[-1].lower() in _VOWELS and right.lower() not in _STANDALONE):
            return left + right
        return m.group(0)

    previous = None
    while previous != text:
        previous, text = text, _SPLIT_SYLLABLE.sub(join, text)
    return text


# Một số PDF (font CFF, ví dụ sách Nội tiết 3879/QĐ-BYT) bị trích thành "tuy ế n", "ch ẩ n": chế độ thường hỏng nặng.
# Khi đó đọc lại trang ở chế độ "layout" – chỉ còn lỗi tách trước chữ y ("tu yến", "su y") → ghép lại.
_LONE_CONSONANT = re.compile(r"(?<!\S)[bcdđghklmnpqrstvx](?!\S)", re.I)
_SPLIT_BEFORE_Y = re.compile(r"(?<!\S)((?:ngh|ng|nh|ch|kh|th|tr|ph|[bcdđghklmnpqrstvx])u|[bcdđghklmnpqrstvx]) (y\w*)", re.I)
BROKEN_PAGE_RATIO = 0.05  # > 5% từ là phụ âm đứng lẻ → trang bị tách âm tiết


def broken_ratio(text: str) -> float:
    tokens = text.split()
    return len(_LONE_CONSONANT.findall(text)) / len(tokens) if tokens else 0.0


def set_fonttools(enabled: bool) -> None:
    """pypdf chỉ dùng fontTools để giải mã font CFF khi cờ này bật. Mặc định TẮT: với một số PDF của WHO,
    fontTools giải mã sai chữ số ("≥25" → "≥2≥") – chỉ bật cho trang tiếng Việt hỏng nặng (xem bên dưới)."""
    _pypdf_font.HAS_FONTTOOLS = enabled and _FONTTOOLS_INSTALLED  # pypdf._cmap đọc cờ này mỗi lần giải mã font


def vietnamese_page_text(page, retry_page) -> str:
    """Chữ của 1 trang tiếng Việt. Trang hỏng nặng (phụ âm đứng lẻ > 5%) → đọc lại bằng `retry_page()`
    (cùng trang, mở bằng PdfReader khác với fontTools bật) ở chế độ thường và layout; giữ bản ít lỗi nhất."""
    text = repair_vietnamese_spacing(clean_text(page.extract_text() or ""))
    if broken_ratio(text) <= BROKEN_PAGE_RATIO:
        return text
    set_fonttools(True)
    try:
        other = retry_page()
        plain = repair_vietnamese_spacing(clean_text(other.extract_text() or ""))
        layout = other.extract_text(extraction_mode="layout") or ""
    finally:
        set_fonttools(False)
    layout = "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in layout.splitlines())
    layout = _SPLIT_BEFORE_Y.sub(r"\1\2", repair_vietnamese_spacing(clean_text(layout)))
    return min((text, plain, layout), key=broken_ratio)


# ---------------------------------------------------------------- PDF

# Trang có các cụm này ở đầu trang là phần hành chính, không phải nội dung chuyên môn.
NOISE_PAGE_MARKERS = (
    "MỤC LỤC", "CONTENTS", "BIÊN SOẠN", "LỜI CẢM ƠN", "ACKNOWLEDG", "CHỮ VIẾT TẮT",
    "ABBREVIATIONS", "TÀI LIỆU THAM KHẢO", "REFERENCES",
)
CITATION_LINE = re.compile(r"(et al|doi|https?://|\(\d{4}\)|\b(19|20)\d{2}\b.*[;:]\s*\d)", re.I)

HEADING_PATTERNS = [
    re.compile(r"^(PHẦN|Phần|CHƯƠNG|Chương|BƯỚC|Bước|PHỤ LỤC|Phụ lục|ANNEX|Annex|Chapter|CHAPTER)\s+[\dIVXA-Z]+"),
    re.compile(r"^[IVX]{1,5}\.\s+\S"),          # I. II. III.
    re.compile(r"^\d{1,2}(\.\d{1,2}){0,3}\.?\s+[A-ZĐÀ-Ỹ]"),  # 1. / 2.1 / 3.2.1
    re.compile(r"^[A-H]\.\s+[A-ZĐÀ-Ỹ]"),          # A. B.
]
SENTENCE_END = (".", ";", "?", "!", ":")
BULLET = re.compile(r"^([•▪●○◦\-–+*]|\d{1,2}\)|[a-zđ]\))\s*")


def parse_page_range(spec: str, n_pages: int) -> list[int]:
    """'15-34;57-64' → [15..34, 57..64]. Trống = tất cả các trang."""
    if not spec.strip():
        return list(range(1, n_pages + 1))
    pages: list[int] = []
    for part in spec.split(";"):
        start, _, end = part.strip().partition("-")
        pages.extend(range(int(start), int(end or start) + 1))
    return [p for p in pages if 1 <= p <= n_pages]


def is_noise_page(lines: list[str]) -> bool:
    head = " ".join(lines[:6]).upper()
    if any(marker in head for marker in NOISE_PAGE_MARKERS):
        return True
    if "NƠI NHẬN" in " ".join(lines).upper():  # trang quyết định ban hành
        return True
    citations = sum(bool(CITATION_LINE.search(line)) for line in lines)
    return len(lines) >= 8 and citations / len(lines) > 0.5


# Một số PDF của WHO dùng font mã hoá lệch: chữ thường bị trích thành chữ hoa dịch 29 vị trí
# ("IRUWKHȴUVW" = "forthefirst") kèm ký tự lạ (ȴ, ΍, ȵ). Dòng như vậy không dùng được → bỏ.
_ODD_CHARS = re.compile("[\\u0250-\\u0390\\ufffd]")
_SHIFTED_WORD = re.compile(r"[A-Z]{12,}")


def is_garbled(line: str) -> bool:
    if _ODD_CHARS.search(line):
        return True
    for token in _SHIFTED_WORD.findall(line):
        decoded = "".join(chr(ord(c) + 29) if "D" <= c <= "]" else c for c in token)
        if sum(decoded.count(w) for w in ("the", "and", "ing", "tion", "for")) >= 2:
            return True
    return False


def is_numeric_dump(text: str) -> bool:
    """Bảng/biểu đồ bị trích thành dãy số dài (ví dụ biểu đồ nguy cơ tim mạch) → không có giá trị tra cứu."""
    tokens = text.split()
    return len(tokens) >= 40 and sum(bool(re.search(r"\d", t)) for t in tokens) / len(tokens) > 0.6


def is_heading(line: str) -> bool:
    if len(line) > 110 or line.endswith((".", ",", ";")) or not re.search(r"[A-Za-zÀ-ỹĐđ]{2}", line):
        return False
    if any(p.match(line) for p in HEADING_PATTERNS):
        return True
    letters = [c for c in line if c.isalpha()]
    # Dòng ngắn viết hoa toàn bộ (tiêu đề mục kiểu "ĐIỀU TRỊ", "TREATMENT GOAL").
    return (len(letters) >= 6 and 2 <= len(line.split()) <= 14 and not line.startswith("(")
            and sum(c.isupper() for c in letters) / len(letters) > 0.85)


def repeated_lines(pages: list[list[str]]) -> set[str]:
    """Dòng lặp lại ở nhiều trang (tiêu đề đầu trang, chân trang) → bỏ."""
    counts = Counter(line for lines in pages for line in set(lines) if len(line) < 120)
    threshold = max(3, len(pages) // 4)
    return {line for line, n in counts.items() if n >= threshold}


def extract_pdf(path: Path, page_range: str = "", language: str = "") -> list[Block]:
    set_fonttools(False)
    reader = PdfReader(path)
    retry_reader: list[PdfReader] = []  # mở lại file (fontTools bật) chỉ khi có trang hỏng

    def retry_page(number: int):
        if not retry_reader:
            retry_reader.append(PdfReader(path))
        return retry_reader[0].pages[number - 1]

    selected = parse_page_range(page_range, len(reader.pages))
    raw_pages = []
    for number in selected:
        if language == "vi":
            text = vietnamese_page_text(reader.pages[number - 1], lambda n=number: retry_page(n))
        else:
            text = clean_text(reader.pages[number - 1].extract_text() or "")
        lines = [clean_text(line) for line in text.splitlines()]
        raw_pages.append((number, [line for line in lines if line]))

    repeated = repeated_lines([lines for _, lines in raw_pages])
    blocks: list[Block] = []
    section = ""
    for number, lines in raw_pages:
        if is_noise_page(lines):
            continue
        lines = [l for l in lines if l not in repeated and not is_garbled(l)
                 and not re.fullmatch(r"[\divxlc\s\-–|/]+", l, re.I)]
        paragraph: list[str] = []

        def flush():
            if paragraph:
                text = join_lines(paragraph)
                if not is_numeric_dump(text):
                    blocks.append(Block(text, section, number))
                paragraph.clear()

        for line in lines:
            if is_heading(line):
                flush()
                section = line
                blocks.append(Block(line, section, number, is_heading=True))
            elif BULLET.match(line) or (paragraph and paragraph[-1].endswith(SENTENCE_END)):
                flush()
                paragraph.append(line)
            else:
                paragraph.append(line)
        flush()
    return blocks


def join_lines(lines: list[str]) -> str:
    text = ""
    for line in lines:
        if text.endswith("-") and line[:1].islower():
            text = text[:-1] + line  # từ bị ngắt bằng gạch nối cuối dòng
        else:
            text = f"{text} {line}" if text else line
    return text


# ---------------------------------------------------------------- HTML

# Vùng nội dung chính theo cơ quan; thử lần lượt, cái nào có trước thì dùng.
CONTENT_SELECTORS = {
    "medlineplus": ["#topic-summary", "article", "main"],
    "who": ["article", "main"],
    "skds": [".detail-content", "article"],         # Báo Sức khỏe & Đời sống (12/11/2026)
    "bvtw": [".entry-content", ".detail-content", "main"],  # bài kiến thức của bệnh viện trung ương
}
STOP_SECTIONS = re.compile(r"^(references|related|learn more|see,? play and learn|find an expert|clinical trials|start here"
                           r"|xem thêm|tin liên quan|bài viết liên quan|có thể bạn quan tâm|mời độc giả)", re.I)


def extract_html(path: Path, organization_id: str) -> list[Block]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "lxml")
    root = None
    for selector in CONTENT_SELECTORS.get(organization_id, ["main", "article", "body"]):
        root = soup.select_one(selector)
        if root:
            break
    if root is None:
        return []
    for tag in root.select("script, style, nav, form, button, figure, .share, .social"):
        tag.decompose()

    blocks: list[Block] = []
    section = ""
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = clean_text(el.get_text(" ", strip=True))
        if not text:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            if STOP_SECTIONS.match(text):
                break
            section = text
            blocks.append(Block(text, section, None, is_heading=True))
        elif el.name == "li" and el.find("p"):
            continue  # nội dung đã được lấy qua thẻ <p> bên trong
        elif "enable JavaScript" not in text:
            blocks.append(Block(("• " if el.name == "li" else "") + text, section, None))
    return blocks


# ---------------------------------------------------------------- XML (JATS – bài báo trên Europe PMC)

SKIP_XML_SECTIONS = re.compile(r"(conflict of interest|author contributions|acknowledg|working panel|funding)", re.I)


def extract_jats(path: Path) -> list[Block]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "xml")
    blocks: list[Block] = []
    abstract = soup.find("abstract")
    if abstract:
        blocks.append(Block("Abstract", "Abstract", None, is_heading=True))
        blocks.extend(Block(clean_text(p.get_text(" ", strip=True)), "Abstract", None) for p in abstract.find_all("p"))

    def walk(sec, parent_title: str):
        title_tag = sec.find("title", recursive=False)
        title = clean_text(title_tag.get_text(" ", strip=True)) if title_tag else parent_title
        if SKIP_XML_SECTIONS.search(title):
            return
        blocks.append(Block(title, title, None, is_heading=True))
        for child in sec.find_all(["p", "table-wrap", "sec"], recursive=False):
            if child.name == "sec":
                walk(child, title)
            elif child.name == "p":
                blocks.append(Block(clean_text(child.get_text(" ", strip=True)), title, None))
            else:
                blocks.append(Block(table_to_text(child), title, None))

    if soup.body:
        for sec in soup.body.find_all("sec", recursive=False):
            walk(sec, "")
    return [b for b in blocks if b.text]


def table_to_text(wrap) -> str:
    """Bảng JATS → văn bản: tiêu đề bảng + mỗi hàng một dòng, các ô ngăn bằng ' | '."""
    caption = clean_text(" ".join(t.get_text(" ", strip=True) for t in wrap.find_all(["label", "caption"])))
    rows = [
        " | ".join(clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"]))
        for tr in wrap.find_all("tr")
    ]
    return "\n".join([f"[Bảng] {caption}"] + rows)


# ---------------------------------------------------------------- điểm vào

def extract(path: Path, organization_id: str, page_range: str = "", language: str = "") -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path, page_range, language)
    if suffix == ".html":
        return extract_html(path, organization_id)
    if suffix == ".xml":
        return extract_jats(path)
    raise ValueError(f"Không hỗ trợ định dạng {suffix}")
