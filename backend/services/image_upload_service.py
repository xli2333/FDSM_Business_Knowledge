from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile

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


async def save_image_upload(
    *,
    upload_file: UploadFile,
    target_dir: Path,
    filename: str,
    content_type: str | None = None,
) -> dict:
    final_safe_name = _normalize_image_filename(filename, content_type)
    timestamp = datetime.now().replace(microsecond=0).isoformat().replace(":", "-")
    final_name = f"{timestamp}-{Path(final_safe_name).stem[:80] or 'image'}{Path(final_safe_name).suffix.lower()}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / final_name
    total_bytes = 0
    await upload_file.seek(0)
    with target_path.open("wb") as handle:
        while True:
            chunk = await upload_file.read(IMAGE_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            handle.write(chunk)
            total_bytes += len(chunk)
    await upload_file.seek(0)
    if total_bytes <= 0:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty")
    return {
        "filename": final_name,
        "path": target_path,
        "size_bytes": total_bytes,
        "content_type": content_type,
    }
