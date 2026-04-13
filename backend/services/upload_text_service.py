from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import HTTPException


def decode_text_bytes(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def html_to_markdown_like(content: str) -> str:
    text = content.replace("\r\n", "\n")
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<\s*/p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(
        r"<\s*h1[^>]*>(.*?)<\s*/h1\s*>",
        lambda m: f"# {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<\s*h2[^>]*>(.*?)<\s*/h2\s*>",
        lambda m: f"## {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<\s*h3[^>]*>(.*?)<\s*/h3\s*>",
        lambda m: f"### {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<\s*li[^>]*>(.*?)<\s*/li\s*>",
        lambda m: f"- {re.sub(r'<[^>]+>', '', m.group(1)).strip()}\n",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<\s*(strong|b)[^>]*>(.*?)<\s*/\1\s*>",
        lambda m: f"**{re.sub(r'<[^>]+>', '', m.group(2)).strip()}**",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(
        r"<\s*(em|i)[^>]*>(.*?)<\s*/\1\s*>",
        lambda m: f"*{re.sub(r'<[^>]+>', '', m.group(2)).strip()}*",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def docx_to_markdown_like(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
        try:
            document_xml = archive.read("word/document.xml")
        except KeyError as exc:
            raise HTTPException(status_code=400, detail="DOCX document.xml is missing") from exc

    root = ET.fromstring(document_xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        style_value = ""
        style = paragraph.find("./w:pPr/w:pStyle", namespace)
        if style is not None:
            style_value = str(style.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val") or "")
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if not text:
            continue
        if style_value.startswith("Heading1"):
            paragraphs.append(f"# {text}")
        elif style_value.startswith("Heading2"):
            paragraphs.append(f"## {text}")
        elif style_value.startswith("Heading3"):
            paragraphs.append(f"### {text}")
        else:
            paragraphs.append(text)
    return "\n\n".join(paragraphs).strip()


def extract_upload_content(filename: str, raw_bytes: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return docx_to_markdown_like(raw_bytes)
    content = decode_text_bytes(raw_bytes)
    normalized = content.replace("\r\n", "\n").strip()
    if suffix in {".html", ".htm"}:
        return html_to_markdown_like(normalized)
    return normalized
