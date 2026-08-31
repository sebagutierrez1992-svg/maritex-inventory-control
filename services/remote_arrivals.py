from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import pandas as pd


ARRIVALS_URL = "https://grupo-maritex.github.io/Llegadas_OK/data/llegadas.json"


def _fetch_json(url: str, timeout: int = 15) -> dict:
    separator = "&" if "?" in url else "?"
    cache_buster = int(datetime.now(timezone.utc).timestamp())
    request = Request(
        f"{url}{separator}t={cache_buster}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "Maritex-Inventory-Control/1.0",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_remote_arrivals(timeout: int = 15) -> tuple[pd.DataFrame, dict]:
    """Carga Llegadas_OK y devuelve una tabla normalizada de importaciones.

    Columnas de salida:
        SKU, Producto, Orden, ETA, Unidades, Situación

    No consolida los registros porque un mismo SKU puede estar presente en
    varias órdenes/ETA. La consolidación se hace en la vista según el análisis.
    """
    payload = _fetch_json(ARRIVALS_URL, timeout=timeout)
    items = payload.get("items") or []

    rows: list[dict] = []
    for item in items:
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue

        units = pd.to_numeric(item.get("unidades", 0), errors="coerce")
        units = 0.0 if pd.isna(units) else float(units)

        rows.append(
            {
                "SKU": sku,
                "Producto": str(item.get("producto") or "").strip(),
                "Orden": str(item.get("orden") or "").strip(),
                "ETA": pd.to_datetime(item.get("eta"), errors="coerce"),
                "Unidades": units,
                "Situación": str(item.get("situacion") or "").strip().upper(),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=["SKU", "Producto", "Orden", "ETA", "Unidades", "Situación"],
    )

    generated_at = payload.get("generatedAt")
    meta = {
        "filename": "Llegadas automáticas · Llegadas_OK",
        "loaded_at": generated_at or "actualización automática",
        "generated_at": generated_at,
        "source": "Llegadas_OK / flexline-dashboard-api",
        "mode": "auto",
        "row_count": len(df),
        "sku_count": int(df["SKU"].nunique()) if not df.empty else 0,
        "order_count": int(df["Orden"].replace("", pd.NA).dropna().nunique()) if not df.empty else 0,
        "url": ARRIVALS_URL,
    }
    return df, meta
