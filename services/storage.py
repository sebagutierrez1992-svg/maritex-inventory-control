from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_filename(filename: str) -> str:
    return Path(str(filename or "archivo")).name


def _ensure_writable(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        return
    try:
        path.chmod(path.stat().st_mode | stat.S_IWRITE)
    except Exception:
        pass


def _replace_file(
    temp_path: Path,
    final_path: Path,
    *,
    retries: int = 8,
    delay: float = 0.15,
) -> None:
    temp_path = Path(temp_path)
    final_path = Path(final_path)

    last_error: Exception | None = None

    for attempt in range(retries):
        try:
            _ensure_writable(final_path)
            os.replace(temp_path, final_path)
            return
        except (PermissionError, OSError) as exc:
            last_error = exc
            _ensure_writable(final_path)
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))

    raise PermissionError(
        f"No fue posible reemplazar '{final_path}'. "
        f"Windows mantiene el archivo bloqueado o sin permisos de escritura. "
        f"Último error: {last_error}"
    )


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_file.write(raw)
            temp_file.flush()
            try:
                os.fsync(temp_file.fileno())
            except OSError:
                pass
            temp_path = Path(temp_file.name)

        _replace_file(temp_path, path)

    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def _atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
            encoding=encoding,
            newline="",
        ) as temp_file:
            temp_file.write(text)
            temp_file.flush()
            try:
                os.fsync(temp_file.fileno())
            except OSError:
                pass
            temp_path = Path(temp_file.name)

        _replace_file(temp_path, path)

    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def save_source(
    raw: bytes,
    filename: str,
    data_path: Path,
    meta_path: Path,
    metadata: dict | None = None,
    history_dir: Path | None = None,
    source_key: str | None = None,
):
    data_path = Path(data_path)
    meta_path = Path(meta_path)

    data_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)

    _atomic_write_bytes(data_path, raw)

    meta = {
        "filename": _safe_filename(filename),
        "loaded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
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


def load_source(
    data_path: Path,
    meta_path: Path,
):
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
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    return raw, meta


def list_history(
    history_dir: Path,
    source_key: str | None = None,
    limit: int | None = None,
):
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
            stat_info = path.stat()
            rows.append(
                {
                    "name": path.name,
                    "filename": path.name,
                    "path": path,
                    "full_path": str(path),
                    "modified_at": datetime.fromtimestamp(stat_info.st_mtime).astimezone(),
                    "size": stat_info.st_size,
                }
            )
        except Exception:
            continue

    rows.sort(key=lambda x: x["modified_at"], reverse=True)

    if limit is not None:
        rows = rows[: int(limit)]

    return rows


def save_history(
    raw: bytes,
    filename: str,
    history_dir: Path,
    prefix: str = "",
):
    history_dir = Path(history_dir)
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    original_name = _safe_filename(filename)

    if prefix:
        history_name = f"{prefix}_{timestamp}_{original_name}"
    else:
        history_name = f"{timestamp}_{original_name}"

    target = history_dir / history_name
    _atomic_write_bytes(target, raw)

    return target


def save_named_file(
    raw: bytes,
    filename: str,
    directory: Path,
    *,
    overwrite: bool = True,
) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    safe_name = _safe_filename(filename)
    target = directory / safe_name

    if target.exists() and not overwrite:
        raise FileExistsError(f"Ya existe {safe_name}")

    _atomic_write_bytes(target, raw)
    return target


def list_named_files(
    directory: Path,
    suffixes: tuple[str, ...] | None = None,
):
    directory = Path(directory)

    if not directory.exists():
        return []

    normalized_suffixes = None
    if suffixes:
        normalized_suffixes = tuple(str(s).lower() for s in suffixes)

    rows = []

    for path in directory.iterdir():
        if not path.is_file():
            continue

        if normalized_suffixes and path.suffix.lower() not in normalized_suffixes:
            continue

        try:
            stat_info = path.stat()
            rows.append(
                {
                    "name": path.name,
                    "filename": path.name,
                    "path": path,
                    "full_path": str(path),
                    "modified_at": datetime.fromtimestamp(stat_info.st_mtime).astimezone(),
                    "size": stat_info.st_size,
                }
            )
        except Exception:
            continue

    rows.sort(key=lambda x: x["name"].lower())
    return rows


def delete_named_file(
    directory: Path,
    filename: str,
) -> bool:
    directory = Path(directory)
    target = directory / _safe_filename(filename)

    if not target.exists() or not target.is_file():
        return False

    _ensure_writable(target)
    target.unlink()
    return True