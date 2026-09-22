from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from console_io import configure_utf8_stdout


configure_utf8_stdout()


def extract_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(node.text or "" for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def extract_xlsx(path: Path) -> str:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    lines: list[str] = []
    for sheet in workbook.worksheets:
        lines.append(f"[{sheet.title}]")
        for row in sheet.iter_rows(values_only=True):
            values = [str(value).strip() for value in row if value not in (None, "")]
            if values:
                lines.append(" | ".join(values))
            if len(lines) >= 2000:
                break
    return "\n".join(lines)


def extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("当前运行环境未安装PDF文本解析组件") from exc
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def extract(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path)
    if suffix in {".xlsx", ".xlsm"}:
        return extract_xlsx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix in {".txt", ".md", ".csv", ".json"}:
        return path.read_text(encoding="utf-8", errors="replace")
    raise RuntimeError(f"暂不支持的手卡格式：{suffix or '无扩展名'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from a brand brief for AIPR recognition.")
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    path = Path(args.file).resolve()
    if not path.exists():
        raise SystemExit(f"file not found: {path}")
    text = re.sub(r"\n{3,}", "\n\n", extract(path)).strip()
    print(json.dumps({"path": str(path), "name": path.name, "text": text[:50000]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
