"""Armazenamento de fotos de produto em disco (`product_images/` na raiz do projeto)."""

from __future__ import annotations

from pathlib import Path

from database.config import BASE_DIR

PRODUCT_IMAGES_SUBDIR = "product_images"
PRODUCT_IMAGES_DIR = BASE_DIR / PRODUCT_IMAGES_SUBDIR

_MAX_BYTES = 8 * 1024 * 1024


def normalize_image_extension(filename: str) -> str:
    """Devolve `.jpg`, `.png` ou `.webp` a partir do nome do ficheiro."""
    fn = (filename or "").strip().lower()
    if fn.endswith((".jpeg", ".jpg")):
        return ".jpg"
    if fn.endswith(".png"):
        return ".png"
    if fn.endswith(".webp"):
        return ".webp"
    return ""


def product_image_abs_path(relative_stored: str | None) -> Path | None:
    """Caminho absoluto se o ficheiro existir; caso contrário None."""
    if not relative_stored or not str(relative_stored).strip():
        return None
    p = (BASE_DIR / str(relative_stored).strip()).resolve()
    try:
        p.relative_to(BASE_DIR.resolve())
    except ValueError:
        return None
    if p.is_file():
        return p
    return None


def save_product_image_file(product_id: int, data: bytes, upload_filename: str) -> str:
    """Grava `product_images/{id}.ext`. Devolve caminho relativo guardado na BD."""
    ext = normalize_image_extension(upload_filename)
    if not ext:
        raise ValueError("Formato de imagem não suportado (use JPG, PNG ou WebP).")
    if len(data) > _MAX_BYTES:
        raise ValueError("Imagem muito grande (máx. 8 MB).")
    PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    pid = int(product_id)
    for old in PRODUCT_IMAGES_DIR.glob(f"{pid}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    rel = f"{PRODUCT_IMAGES_SUBDIR}/{pid}{ext}"
    dest = (BASE_DIR / rel).resolve()
    dest.write_bytes(data)
    return rel.replace("\\", "/")


def delete_product_image_file(relative_stored: str | None) -> None:
    if not relative_stored or not str(relative_stored).strip():
        return
    p = (BASE_DIR / str(relative_stored).strip().replace("\\", "/")).resolve()
    try:
        p.relative_to(BASE_DIR.resolve())
    except ValueError:
        return
    try:
        if p.is_file():
            p.unlink()
    except OSError:
        pass
