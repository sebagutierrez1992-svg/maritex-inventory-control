import json
from datetime import datetime
from pathlib import Path


def save_source(raw: bytes, filename: str, data_path: Path, meta_path: Path, metadata: dict | None = None):
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(raw)

    meta = {
        "filename": filename,
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
    }
    if metadata:
        meta.update(metadata)

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_source(data_path: Path, meta_path: Path):
    if not data_path.exists():
        return None, None

    raw = data_path.read_bytes()
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    return raw, meta
