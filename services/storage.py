from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


# ============================================================
# HELPERS
# ============================================================

def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_filename(filename: str) -> str:
    """Evita rutas accidentales y conserva solo el nombre del archivo."""
    return Path(str(filename or "archivo")).name


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    """
    Escritura segura:
    primero escribe un temporal y luego reemplaza el archivo final.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(raw)
    temp_path.replace(path)


def _atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """
    Escritura segura para archivos de texto/JSON.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding=encoding)
    temp_path.replace(path)


# ============================================================
# GUARDAR FUENTE
# ============================================================

def save_source(
    raw: bytes,
    filename: str,
    data_path: Path,
    meta_path: Path,
    metadata: dict | None = None,
    history_dir: Path | None = None,
    source_key: str | None = None,
):
    """
    Guarda una fuente ERP y su metadata.

    Si se entregan history_dir y source_key, además guarda una copia
    histórica bajo history_dir / source_key.
    """

    data_path = Path(data_path)
    meta_path = Path(meta_path)

    data_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    _atomic_write_bytes(data_path, raw)

    meta = {
        "filename": _safe_filename(filename),
        "loaded_at": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "sha256": _sha256(raw),
        "size": len(raw),
    }

    if metadata:
        meta.update(metadata)

    _atomic_write_text(
        meta_path,
        json.dumps(
            meta,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    if history_dir is not None:
        target_dir = Path(history_dir)

        if source_key:
            target_dir = target_dir / source_key

        save_history(
            raw=raw,
            filename=filename,
            history_dir=target_dir,
            prefix=source_key or "",
        )

    return meta


# ============================================================
# CARGAR FUENTE
# ============================================================

def load_source(
    data_path: Path,
    meta_path: Path,
):
    """Carga una fuente ERP previamente guardada."""

    data_path = Path(data_path)
    meta_path = Path(meta_path)

    if not data_path.exists():
        return None, None

    try:
        raw = data_path.read_bytes()
    except Exception:
        return None, None

    meta: dict[str, Any] = {}

    if meta_path.exists():
        try:
            meta = json.loads(
                meta_path.read_text(encoding="utf-8")
            )
        except Exception:
            meta = {}

    return raw, meta


# ============================================================
# HISTÓRICO
# ============================================================

def list_history(
    history_dir: Path,
    source_key: str | None = None,
    limit: int | None = None,
):
    """
    Lista archivos históricos desde el más reciente.

    Compatible con estas dos formas:
        list_history(HISTORY_DIR, "erp_sales")
        list_history(ERP_SALES_HISTORY_DIR)
    """

    history_dir = Path(history_dir)

    if source_key:
        history_dir = history_dir / source_key

    if not history_dir.exists():
        return []

    rows = []

    for path in history_dir.rglob("*"):
        if not path.is_file():
            continue

        try:
            stat = path.stat()

            rows.append(
                {
                    "name": path.name,
                    "filename": path.name,
                    "path": path,
                    "full_path": str(path),
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime
                    ).astimezone(),
                    "size": stat.st_size,
                }
            )
        except Exception:
            continue

    rows.sort(
        key=lambda x: x["modified_at"],
        reverse=True,
    )

    if limit is not None:
        rows = rows[: int(limit)]

    return rows


# ============================================================
# GUARDAR COPIA HISTÓRICA
# ============================================================

def save_history(
    raw: bytes,
    filename: str,
    history_dir: Path,
    prefix: str = "",
):
    """Guarda una copia histórica de un archivo."""

    history_dir = Path(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    original_name = _safe_filename(filename)

    if prefix:
        history_name = (
            f"{prefix}_{timestamp}_{original_name}"
        )
    else:
        history_name = (
            f"{timestamp}_{original_name}"
        )

    target = history_dir / history_name

    _atomic_write_bytes(target, raw)

    return target


# ============================================================
# ARCHIVOS NOMBRADOS / MOVIMIENTOS
# ============================================================

def save_named_file(
    raw: bytes,
    filename: str,
    directory: Path,
    *,
    overwrite: bool = True,
) -> Path:
    """
    Guarda un archivo conservando su nombre dentro de una carpeta.

    Se usa para archivos mensuales de movimientos Flexline.
    """

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(filename)
    target = directory / safe_name

    if target.exists() and not overwrite:
        raise FileExistsError(
            f"Ya existe {safe_name}"
        )

    _atomic_write_bytes(target, raw)

    return target


def list_named_files(
    directory: Path,
    suffixes: tuple[str, ...] | None = None,
):
    """Lista archivos guardados en una carpeta."""

    directory = Path(directory)

    if not directory.exists():
        return []

    normalized_suffixes = None

    if suffixes:
        normalized_suffixes = tuple(
            str(s).lower()
            for s in suffixes
        )

    rows = []

    for path in directory.iterdir():
        if not path.is_file():
            continue

        if (
            normalized_suffixes
            and path.suffix.lower()
            not in normalized_suffixes
        ):
            continue

        try:
            stat = path.stat()

            rows.append(
                {
                    "name": path.name,
                    "filename": path.name,
                    "path": path,
                    "full_path": str(path),
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime
                    ).astimezone(),
                    "size": stat.st_size,
                }
            )
        except Exception:
            continue

    rows.sort(
        key=lambda x: x["name"].lower()
    )

    return rows


def delete_named_file(
    directory: Path,
    filename: str,
) -> bool:
    """Elimina un archivo concreto de una carpeta controlada."""

    directory = Path(directory)
    target = directory / _safe_filename(filename)

    if not target.exists() or not target.is_file():
        return False

    target.unlink()

    return True