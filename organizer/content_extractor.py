import os
import html

from config import LARGE_FILE_CEILING, MAX_PEEK_CHARS

_TEXT_EXTS = {".txt", ".md", ".csv", ".rtf", ".json", ".yaml", ".yml", ".log"}


def extract_text(file_path: str) -> str:
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    try:
        if ext in _TEXT_EXTS:
            return _read_plain(file_path)
        if ext == ".pdf":
            return _read_pdf(file_path)
        if ext == ".docx":
            return _read_docx(file_path)
    except Exception:
        pass
    return ""


def extract_text_escaped(file_path: str) -> str:
    raw = extract_text(file_path)
    return html.escape(raw)


def _read_plain(path: str) -> str:
    with open(path, errors="ignore") as f:
        return f.read(MAX_PEEK_CHARS)


def _read_pdf(path: str) -> str:
    if os.path.getsize(path) > LARGE_FILE_CEILING:
        return ""
    import pypdf
    reader = pypdf.PdfReader(path)
    buf = ""
    for page in reader.pages:
        buf += page.extract_text() or ""
        if len(buf) >= MAX_PEEK_CHARS:
            break
    return buf[:MAX_PEEK_CHARS]


def _read_docx(path: str) -> str:
    if os.path.getsize(path) > LARGE_FILE_CEILING:
        return ""
    import docx
    doc = docx.Document(path)
    buf = ""
    for para in doc.paragraphs:
        buf += para.text + "\n"
        if len(buf) >= MAX_PEEK_CHARS:
            break
    return buf[:MAX_PEEK_CHARS]
