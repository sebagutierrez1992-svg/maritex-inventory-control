from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


BASE_URL = "https://grupo-maritex.github.io/Llegadas_OK/data"
STOCK_URL = f"{BASE_URL}/stock.json"
IMPORTS_URL = f"{BASE_URL}/llegadas.json"

WAREHOUSES = {
    "cd": "CD",
    "cm": "CASA MATRIZ",
    "patronato": "PATRONATO",
    "concepcion": "CONCEPCION",
}


# ============================================================
# HTTP
# ============================================================

def _fetch_json(
    url: str,
    timeout: int = 15,
) -> dict:
    """
    Descarga JSON evitando reutilizar una copia antigua del navegador/CDN.
    """
    separator = "&" if "?" in url else "?"
    cache_buster = int(
        datetime.now(timezone.utc).timestamp()
    )

    request = Request(
        f"{url}{separator}t={cache_buster}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "Maritex-Inventory-Control/1.0",
        },
    )

    with urlopen(
        request,
        timeout=timeout,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


# ============================================================
# HELPERS
# ============================================================

def _clean_sku(value) -> str:
    return (
        str(value or "")
        .strip()
        .replace(".0", "")
    )


def _safe_number(value) -> float:
    parsed = pd.to_numeric(
        value,
        errors="coerce",
    )

    return (
        0.0
        if pd.isna(parsed)
        else float(parsed)
    )


# ============================================================
# STOCK ACTUAL
# ============================================================

@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def load_remote_stock(
    timeout: int = 15,
) -> tuple[pd.DataFrame, dict]:
    """
    Carga stock automático de Llegadas_OK.

    La salida mantiene una fila por SKU/bodega y respeta el contrato
    que ya consume analytics.stock_metrics.stock_view().
    """
    payload = _fetch_json(
        STOCK_URL,
        timeout=timeout,
    )

    items = payload.get("items") or []

    rows: list[dict] = []

    for item in items:
        sku = _clean_sku(
            item.get("sku")
        )

        if not sku:
            continue

        product = str(
            item.get("producto")
            or sku
        ).strip()

        for key, warehouse in WAREHOUSES.items():
            stock = _safe_number(
                item.get(
                    key,
                    0,
                )
            )

            rows.append(
                {
                    "Producto": sku,
                    "Descripción": product,
                    "Bodega": warehouse,
                    "Stock": stock,
                    "Stock Proyectado": stock,

                    # Llegadas_OK/stock.json no entrega estos campos.
                    # Se mantienen para conservar compatibilidad con
                    # stock_view(), pero NO deben interpretarse como
                    # datos reales de importación o despacho.
                    "Por Llegar": 0,
                    "Por Despachar": 0,
                }
            )

    df = pd.DataFrame(
        rows
    )

    generated_at = payload.get(
        "generatedAt"
    )

    meta = {
        "filename": "Stock automático · Llegadas_OK",
        "loaded_at": (
            generated_at
            or "actualización automática"
        ),
        "generated_at": generated_at,
        "source": "Llegadas_OK / stock.json",
        "mode": "auto",
        "sku_count": len(items),
        "url": STOCK_URL,
    }

    return df, meta


# ============================================================
# IMPORTACIONES / LLEGADAS
# ============================================================

@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def load_remote_imports(
    timeout: int = 15,
) -> tuple[pd.DataFrame, dict]:
    """
    Carga data/llegadas.json desde Llegadas_OK.

    Campos publicados por la fuente:
    - sku
    - producto
    - orden
    - eta
    - unidades
    - situacion

    La función devuelve una estructura estable para poder cruzar
    importaciones con stock actual y ERP Ventas.
    """
    payload = _fetch_json(
        IMPORTS_URL,
        timeout=timeout,
    )

    elements = (
        payload.get("elementos")
        or payload.get("items")
        or []
    )

    rows: list[dict] = []

    for item in elements:
        sku = _clean_sku(
            item.get("sku")
        )

        if not sku:
            continue

        eta_raw = item.get(
            "eta"
        )

        eta = pd.to_datetime(
            eta_raw,
            errors="coerce",
        )

        rows.append(
            {
                "SKU": sku,
                "Producto importación": str(
                    item.get("producto")
                    or ""
                ).strip(),
                "Orden": str(
                    item.get("orden")
                    or ""
                ).strip(),
                "ETA": eta,
                "Unidades importación": _safe_number(
                    item.get(
                        "unidades",
                        0,
                    )
                ),
                "Situación": str(
                    item.get("situacion")
                    or "SIN ESTADO"
                )
                .strip()
                .upper(),
            }
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "SKU",
            "Producto importación",
            "Orden",
            "ETA",
            "Unidades importación",
            "Situación",
        ],
    )

    generated_at = payload.get(
        "generatedAt"
    )

    meta = {
        "filename": "Importaciones · Llegadas_OK",
        "loaded_at": (
            generated_at
            or "actualización automática"
        ),
        "generated_at": generated_at,
        "source": "Llegadas_OK / llegadas.json",
        "mode": "auto",
        "row_count": len(df),
        "url": IMPORTS_URL,
    }

    return df, meta
