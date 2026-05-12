from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

from backend.config import MEDIA_IMAGE_UPLOAD_MAX_BYTES

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
IMAGE_CONTENT_TYPE_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
}
IMAGE_UPLOAD_CHUNK_SIZE = 1024 * 1024


def sanitize_upload_filename(value: str, *, fallback_stem: str = "image") -> str:
    raw = Path(value or f"{fallback_stem}.bin").name
    stem = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", Path(raw).stem).strip("-")
    suffix = Path(raw).suffix.lower()
    return f"{stem[:80] or fallback_stem}{suffix}"


def _normalize_image_filename(filename: str, content_type: str | None = None) -> str:
    safe_name = sanitize_upload_filename(filename, fallback_stem="image")
    suffix = Path(safe_name).suffix.lower()
    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        return safe_name
    inferred_suffix = IMAGE_CONTENT_TYPE_SUFFIX.get(str(content_type or "").strip().lower())
    if inferred_suffix:
        stem = Path(safe_name).stem or "image"
        return f"{stem[:80] or 'image'}{inferred_suffix}"
    raise HTTPException(status_code=400, detail="Unsupported cover image type")


async def _peek_upload_header(upload_file: UploadFile, size: int = 64) -> bytes:
    await upload_file.seek(0)
    header = await upload_file.read(size)
    await upload_file.seek(0)
    return header


def _image_signature_matches(suffix: str, header: bytes) -> bool:
    if suffix in {".jpg", ".jpeg"}:
        return header.startswith(b"\xff\xd8\xff")
    if suffix == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".bmp":
        return header.startswith(b"BM")
    if suffix == ".webp":
        return len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if suffix == ".avif":
        return len(header) >= 12 and b"ftyp" in header[4:16] and b"avif" in header[8:32]
    return False


async def save_image_upload(
    *,
    upload_file: UploadFile,
    target_dir: Path,
    filename: str,
    content_type: str | None = None,
) -> dict:
    final_safe_name = _normalize_image_filename(filename, content_type)
    suffix = Path(final_safe_name).suffix.lower()
    header = await _peek_upload_header(upload_file)
    if not header:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty")
    if not _image_signature_matches(suffix, header):
        raise HTTPException(status_code=400, detail="Uploaded image content does not match its file type")
    timestamp = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
    final_name = f"{timestamp}-{Path(final_safe_name).stem[:80] or 'image'}{suffix}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / final_name
    total_bytes = 0
    await upload_file.seek(0)
    try:
        with target_path.open("wb") as handle:
            while True:
                chunk = await upload_file.read(IMAGE_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MEDIA_IMAGE_UPLOAD_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Uploaded image is too large")
                handle.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    await upload_file.seek(0)
    if total_bytes <= 0:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty")
    return {
        "filename": final_name,
        "path": target_path,
        "size_bytes": total_bytes,
        "content_type": content_type,
    }
