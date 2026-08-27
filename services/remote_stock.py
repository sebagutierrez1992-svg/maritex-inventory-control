from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import pandas as pd


STOCK_URL = "https://grupo-maritex.github.io/Llegadas_OK/data/stock.json"

WAREHOUSES = {
    "cd": "CD",
    "cm": "CASA MATRIZ",
    "patronato": "PATRONATO",
    "concepcion": "CONCEPCION",
}


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


def load_remote_stock(timeout: int = 15) -> tuple[pd.DataFrame, dict]:
    """Carga stock automático de Llegadas_OK y lo adapta al contrato ERP Stock.

    La salida tiene una fila por SKU/local para que el resto del dashboard siga
    usando stock_view() y consolidate_inventory() sin cambios.
    """
    payload = _fetch_json(STOCK_URL, timeout=timeout)
    items = payload.get("items") or []

    rows: list[dict] = []
    for item in items:
        sku = str(item.get("sku") or "").strip()
        if not sku:
            continue

        product = str(item.get("producto") or sku).strip()

        for key, warehouse in WAREHOUSES.items():
            value = pd.to_numeric(item.get(key, 0), errors="coerce")
            stock = 0 if pd.isna(value) else float(value)
            rows.append(
                {
                    "Producto": sku,
                    "Descripción": product,
                    "Bodega": warehouse,
                    "Stock": stock,
                    "Stock Proyectado": stock,
                    "Por Llegar": 0,
                    "Por Despachar": 0,
                }
            )

    df = pd.DataFrame(rows)
    generated_at = payload.get("generatedAt")

    meta = {
        "filename": "Stock automático · Llegadas_OK",
        "loaded_at": generated_at or "actualización automática",
        "generated_at": generated_at,
        "source": "Llegadas_OK / flexline-dashboard-api",
        "mode": "auto",
        "sku_count": len(items),
        "url": STOCK_URL,
    }
    return df, meta
