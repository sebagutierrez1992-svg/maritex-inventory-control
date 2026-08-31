from __future__ import annotations

from datetime import date
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from analytics.stock_metrics import consolidate_inventory
from services.remote_stock import load_remote_imports
from ui.components import render_html


# ============================================================
# HELPERS
# ============================================================

def _num(
    df: pd.DataFrame,
    column: str,
) -> pd.Series:
    if df is None:
        return pd.Series(
            dtype="float64"
        )

    if column not in df.columns:
        return pd.Series(
            0.0,
            index=df.index,
            dtype="float64",
        )

    return pd.to_numeric(
        df[column],
        errors="coerce",
    ).fillna(0.0)


def _safe_int(value) -> int:
    try:
        return int(
            round(
                float(value)
            )
        )
    except Exception:
        return 0


def _fmt_int(value) -> str:
    return (
        f"{_safe_int(value):,}"
        .replace(",", ".")
    )


def _friendly_datetime(
    value,
) -> str:
    if value is None:
        return "Sesión actual"

    text = str(
        value
    ).strip()

    if not text:
        return "Sesión actual"

    try:
        dt = pd.to_datetime(
            text,
            utc=True,
            errors="raise",
        )

        return dt.strftime(
            "%d/%m/%Y · %H:%M UTC"
        )

    except Exception:
        return text


def _normalize_key(
    series: pd.Series,
) -> pd.Series:
    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
    )


def _first_existing(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    if df is None or df.empty:
        return None

    for col in candidates:
        if col in df.columns:
            return col

    return None


def _prepare_search(
    df: pd.DataFrame,
) -> pd.DataFrame:
    out = df.copy()

    out["_search_codigo"] = (
        out.get(
            "Código",
            pd.Series(
                "",
                index=out.index,
            ),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    out["_search_producto"] = (
        out.get(
            "Producto",
            pd.Series(
                "",
                index=out.index,
            ),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    return out


def _clp(
    value: float,
) -> str:
    value = float(
        value or 0
    )

    if abs(value) >= 1_000_000_000:
        return (
            f"${value / 1_000_000_000:,.1f} mil MM"
        )

    if abs(value) >= 1_000_000:
        return (
            f"${value / 1_000_000:,.1f} MM"
        )

    return (
        f"${value:,.0f}"
    )


# ============================================================
# VENTAS / ROTACIÓN / COBERTURA
# ============================================================

def _sales_intelligence(
    inventory: pd.DataFrame,
    sales_df: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    empty_meta = {
        "enabled": False,
        "reason": "ERP Ventas no disponible.",
        "sales_code_col": None,
        "sales_qty_col": None,
        "sales_amount_col": None,
        "sales_date_col": None,
    }

    if (
        sales_df is None
        or sales_df.empty
        or inventory is None
        or inventory.empty
    ):
        return inventory.copy(), empty_meta

    sales = sales_df.copy()

    code_col = _first_existing(
        sales,
        [
            "Código",
            "Codigo",
            "SKU",
            "Sku",
            "CodProducto",
            "CodArticulo",
            "CodigoProducto",
            "Código Producto",
            "Codigo Producto",
        ],
    )

    date_col = _first_existing(
        sales,
        [
            "Fecha_dt",
            "Fecha",
            "FechaEmision",
            "Fecha Emision",
            "Fecha emisión",
        ],
    )

    qty_col = _first_existing(
        sales,
        [
            "CantidadFirmada",
            "Cantidad",
            "Cantidad_num",
            "Unidades",
            "Qty",
            "Cantidad Vendida",
        ],
    )

    amount_col = _first_existing(
        sales,
        [
            "VentaFirmadaConIVA",
            "VentaFirmadaSinIVA",
            "Venta Neta",
            "VentaNeta",
            "Total",
            "Monto",
        ],
    )

    if code_col is None:
        meta = empty_meta.copy()
        meta["reason"] = (
            "ERP Ventas está disponible, pero no fue posible "
            "identificar una columna SKU compatible."
        )
        return inventory.copy(), meta

    sales["_sku_key"] = _normalize_key(
        sales[code_col]
    )

    if date_col is not None:
        sales["_fecha"] = pd.to_datetime(
            sales[date_col],
            errors="coerce",
        )
        max_date = sales["_fecha"].max()
    else:
        sales["_fecha"] = pd.NaT
        max_date = pd.NaT

    if qty_col is not None:
        sales["_qty"] = pd.to_numeric(
            sales[qty_col],
            errors="coerce",
        ).fillna(0.0)
    else:
        sales["_qty"] = 1.0

    if amount_col is not None:
        sales["_amount"] = pd.to_numeric(
            sales[amount_col],
            errors="coerce",
        ).fillna(0.0)
    else:
        sales["_amount"] = 0.0

    if pd.notna(max_date):
        start_30 = (
            max_date
            - pd.Timedelta(
                days=29
            )
        )
        start_90 = (
            max_date
            - pd.Timedelta(
                days=89
            )
        )

        s30 = sales[
            sales["_fecha"].between(
                start_30,
                max_date,
                inclusive="both",
            )
        ].copy()

        s90 = sales[
            sales["_fecha"].between(
                start_90,
                max_date,
                inclusive="both",
            )
        ].copy()
    else:
        s30 = sales.copy()
        s90 = sales.copy()

    g30 = (
        s30.groupby(
            "_sku_key",
            as_index=False,
        )
        .agg(
            Venta_30d=(
                "_amount",
                "sum",
            ),
            Unidades_30d=(
                "_qty",
                "sum",
            ),
        )
    )

    g90 = (
        s90.groupby(
            "_sku_key",
            as_index=False,
        )
        .agg(
            Venta_90d=(
                "_amount",
                "sum",
            ),
            Unidades_90d=(
                "_qty",
                "sum",
            ),
        )
    )

    out = inventory.copy()

    out["_sku_key"] = _normalize_key(
        out["Código"]
    )

    out = (
        out
        .merge(
            g30,
            on="_sku_key",
            how="left",
        )
        .merge(
            g90,
            on="_sku_key",
            how="left",
        )
    )

    for col in [
        "Venta_30d",
        "Unidades_30d",
        "Venta_90d",
        "Unidades_90d",
    ]:
        out[col] = pd.to_numeric(
            out[col],
            errors="coerce",
        ).fillna(0.0)

    out["Unidades_30d_demanda"] = (
        out["Unidades_30d"]
        .clip(
            lower=0
        )
    )

    out["Venta_90d_abc"] = (
        out["Venta_90d"]
        .clip(
            lower=0
        )
    )

    daily = (
        out["Unidades_30d_demanda"]
        / 30.0
    )

    available = _num(
        out,
        "Disponible",
    ).clip(
        lower=0
    )

    out["Cobertura días"] = 0.0

    moving = daily > 0

    out.loc[
        moving,
        "Cobertura días",
    ] = (
        available[moving]
        / daily[moving]
    )

    out.loc[
        ~moving
        & (available > 0),
        "Cobertura días",
    ] = 9999.0

    def coverage_label(
        days,
        units_30,
    ):
        if units_30 <= 0:
            return "Sin venta 30d"

        if days < 15:
            return "< 15 días"

        if days < 30:
            return "15-29 días"

        if days <= 90:
            return "30-90 días"

        return "> 90 días"

    out["Rango cobertura"] = [
        coverage_label(
            days,
            units,
        )
        for days, units in zip(
            out["Cobertura días"],
            out["Unidades_30d_demanda"],
        )
    ]

    abc_base = (
        out.sort_values(
            "Venta_90d_abc",
            ascending=False,
        )
        .copy()
    )

    total_sales = float(
        abc_base[
            "Venta_90d_abc"
        ].sum()
    )

    if total_sales > 0:
        abc_base["_cum"] = (
            abc_base[
                "Venta_90d_abc"
            ].cumsum()
            / total_sales
        )

        abc_base["ABC"] = "C"

        abc_base.loc[
            abc_base["_cum"] <= 0.80,
            "ABC",
        ] = "A"

        abc_base.loc[
            (
                abc_base["_cum"] > 0.80
            )
            & (
                abc_base["_cum"] <= 0.95
            ),
            "ABC",
        ] = "B"

        first_over = abc_base.index[
            abc_base["_cum"] > 0.80
        ]

        if len(first_over):
            abc_base.loc[
                first_over[0],
                "ABC",
            ] = "A"

    else:
        abc_base["ABC"] = (
            "Sin clasificación"
        )

    out = (
        out.drop(
            columns=["ABC"],
            errors="ignore",
        )
        .merge(
            abc_base[
                [
                    "_sku_key",
                    "ABC",
                ]
            ],
            on="_sku_key",
            how="left",
        )
    )

    meta = {
        "enabled": True,
        "reason": "",
        "sales_code_col": code_col,
        "sales_qty_col": qty_col,
        "sales_amount_col": amount_col,
        "sales_date_col": date_col,
        "max_date": max_date,
    }

    return (
        out.drop(
            columns=["_sku_key"],
            errors="ignore",
        ),
        meta,
    )


# ============================================================
# IMPORTACIONES
# ============================================================

def _prepare_imports(
    imports_df: pd.DataFrame | None,
    inventory: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if (
        imports_df is None
        or imports_df.empty
    ):
        return (
            pd.DataFrame(),
            inventory.copy(),
        )

    imports = imports_df.copy()

    imports["SKU"] = _normalize_key(
        imports["SKU"]
    )

    imports["ETA"] = pd.to_datetime(
        imports["ETA"],
        errors="coerce",
    )

    imports["Unidades importación"] = (
        pd.to_numeric(
            imports[
                "Unidades importación"
            ],
            errors="coerce",
        )
        .fillna(0.0)
        .clip(
            lower=0
        )
    )

    imports["Situación"] = (
        imports["Situación"]
        .fillna("SIN ESTADO")
        .astype(str)
        .str.strip()
        .str.upper()
        .replace(
            "",
            "SIN ESTADO",
        )
    )

    today = pd.Timestamp(
        date.today()
    )

    imports["Días a ETA"] = (
        imports["ETA"]
        - today
    ).dt.days

    inventory_out = (
        inventory.copy()
    )

    inventory_out["_sku_key"] = (
        _normalize_key(
            inventory_out["Código"]
        )
    )

    import_by_sku = (
        imports.groupby(
            "SKU",
            as_index=False,
        )
        .agg(
            Importación_unidades=(
                "Unidades importación",
                "sum",
            ),
            ETA_más_próxima=(
                "ETA",
                "min",
            ),
            Órdenes_importación=(
                "Orden",
                lambda s: (
                    ", ".join(
                        sorted(
                            {
                                str(v).strip()
                                for v in s
                                if str(v).strip()
                            }
                        )
                    )
                ),
            ),
            Situaciones_importación=(
                "Situación",
                lambda s: (
                    ", ".join(
                        sorted(
                            {
                                str(v).strip()
                                for v in s
                                if str(v).strip()
                            }
                        )
                    )
                ),
            ),
        )
        .rename(
            columns={
                "SKU": "_sku_key"
            }
        )
    )

    inventory_out = (
        inventory_out.merge(
            import_by_sku,
            on="_sku_key",
            how="left",
        )
    )

    inventory_out[
        "Importación_unidades"
    ] = pd.to_numeric(
        inventory_out[
            "Importación_unidades"
        ],
        errors="coerce",
    ).fillna(0.0)

    inventory_out[
        "ETA_más_próxima"
    ] = pd.to_datetime(
        inventory_out[
            "ETA_más_próxima"
        ],
        errors="coerce",
    )

    return (
        imports,
        inventory_out.drop(
            columns=["_sku_key"],
            errors="ignore",
        ),
    )


def _import_status_summary(
    imports: pd.DataFrame,
) -> pd.DataFrame:
    if imports is None or imports.empty:
        return pd.DataFrame()

    return (
        imports.groupby(
            "Situación",
            as_index=False,
        )
        .agg(
            SKU=(
                "SKU",
                "nunique",
            ),
            Unidades=(
                "Unidades importación",
                "sum",
            ),
            Órdenes=(
                "Orden",
                "nunique",
            ),
        )
        .sort_values(
            "Unidades",
            ascending=False,
        )
    )


def _next_arrivals(
    imports: pd.DataFrame,
    limit: int = 12,
) -> pd.DataFrame:
    if imports is None or imports.empty:
        return pd.DataFrame()

    work = imports[
        imports["ETA"].notna()
    ].copy()

    if work.empty:
        return work

    work = work.sort_values(
        [
            "ETA",
            "Orden",
            "SKU",
        ]
    )

    return work.head(
        limit
    )


# ============================================================
# STOCK ANALYTICS
# ============================================================

def _availability_ranges(
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    available = _num(
        inventory,
        "Disponible",
    )

    labels = pd.cut(
        available,
        bins=[
            -float("inf"),
            0,
            5,
            20,
            50,
            float("inf"),
        ],
        labels=[
            "0",
            "1-5",
            "6-20",
            "21-50",
            "+50",
        ],
        right=True,
    )

    temp = pd.DataFrame(
        {
            "Rango": labels.astype(str),
            "Código": inventory["Código"],
        }
    )

    order = [
        "0",
        "1-5",
        "6-20",
        "21-50",
        "+50",
    ]

    result = (
        temp.groupby(
            "Rango",
            as_index=False,
        )
        .agg(
            SKU=(
                "Código",
                "nunique",
            )
        )
    )

    result["Orden"] = (
        result["Rango"]
        .map(
            {
                name: idx
                for idx, name in enumerate(
                    order
                )
            }
        )
    )

    return (
        result.sort_values(
            "Orden"
        )
    )


def _warehouse_summary(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    if (
        raw is None
        or raw.empty
        or "Bodega" not in raw.columns
    ):
        return pd.DataFrame()

    work = raw.copy()

    work["Bodega"] = (
        work["Bodega"]
        .replace("", pd.NA)
        .fillna("Sin bodega")
        .astype(str)
    )

    work["Disponible"] = _num(
        work,
        "Disponible",
    )

    return (
        work.groupby(
            "Bodega",
            as_index=False,
        )["Disponible"]
        .sum()
        .sort_values(
            "Disponible",
            ascending=False,
        )
    )


def _transfer_opportunities(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    if (
        raw is None
        or raw.empty
        or "Bodega" not in raw.columns
    ):
        return pd.DataFrame()

    work = raw.copy()

    work["Bodega_norm"] = (
        work["Bodega"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    house = work[
        work[
            "Bodega_norm"
        ].str.contains(
            "CASA MATRIZ",
            regex=False,
        )
    ].copy()

    other = work[
        ~work.index.isin(
            house.index
        )
    ].copy()

    if (
        house.empty
        or other.empty
    ):
        return pd.DataFrame()

    house_cons = consolidate_inventory(
        house.drop(
            columns=["Bodega_norm"],
            errors="ignore",
        )
    )

    other_cons = consolidate_inventory(
        other.drop(
            columns=["Bodega_norm"],
            errors="ignore",
        )
    )

    if (
        house_cons.empty
        or other_cons.empty
    ):
        return pd.DataFrame()

    h = house_cons[
        [
            "Código",
            "Producto",
            "Disponible",
        ]
    ].rename(
        columns={
            "Disponible": "Casa Matriz"
        }
    )

    o = other_cons[
        [
            "Código",
            "Disponible",
        ]
    ].rename(
        columns={
            "Disponible": "Otras bodegas"
        }
    )

    result = h.merge(
        o,
        on="Código",
        how="left",
    )

    result[
        "Otras bodegas"
    ] = pd.to_numeric(
        result["Otras bodegas"],
        errors="coerce",
    ).fillna(0)

    result[
        "Casa Matriz"
    ] = pd.to_numeric(
        result["Casa Matriz"],
        errors="coerce",
    ).fillna(0)

    return (
        result[
            (
                result["Casa Matriz"] <= 0
            )
            & (
                result["Otras bodegas"] > 0
            )
        ]
        .sort_values(
            "Otras bodegas",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )



# ============================================================
# MOTOR DE RECOMENDACIONES
# ============================================================

LOW_STOCK_THRESHOLD = 5
TRANSFER_TARGET = 6
CD_RESERVE = 6


def _warehouse_pivot(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devuelve una fila por SKU con stock disponible por bodega.
    CD es la bodega abastecedora; CM, Patronato y Concepción son destinos.
    """
    if (
        raw is None
        or raw.empty
        or "Código" not in raw.columns
        or "Bodega" not in raw.columns
    ):
        return pd.DataFrame()

    work = raw.copy()

    work["Código"] = _normalize_key(
        work["Código"]
    )

    work["Disponible"] = _num(
        work,
        "Disponible",
    )

    work["Bodega"] = (
        work["Bodega"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.strip()
    )

    pivot = (
        work.pivot_table(
            index="Código",
            columns="Bodega",
            values="Disponible",
            aggfunc="sum",
            fill_value=0,
        )
        .reset_index()
    )

    rename_map = {
        "CD": "CD",
        "CASA MATRIZ": "CASA MATRIZ",
        "PATRONATO": "PATRONATO",
        "CONCEPCION": "CONCEPCION",
        "CONCEPCIÓN": "CONCEPCION",
    }

    pivot = pivot.rename(
        columns={
            col: rename_map.get(
                str(col).upper().strip(),
                col,
            )
            for col in pivot.columns
        }
    )

    for col in [
        "CD",
        "CASA MATRIZ",
        "PATRONATO",
        "CONCEPCION",
    ]:
        if col not in pivot.columns:
            pivot[col] = 0.0

        pivot[col] = pd.to_numeric(
            pivot[col],
            errors="coerce",
        ).fillna(0.0)

    return pivot


def _transfer_recommendations(
    raw: pd.DataFrame,
    imports_by_sku: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Detecta movimientos sugeridos SOLO desde CD hacia:
    - Casa Matriz
    - Patronato
    - Concepción

    Regla base:
    - destino con <= 5 unidades
    - CD debe conservar al menos 6 unidades
    - se intenta llevar el destino a 6 unidades
    """
    pivot = _warehouse_pivot(
        raw
    )

    if pivot.empty:
        return pd.DataFrame()

    product_map = (
        raw[
            [
                "Código",
                "Producto",
            ]
        ]
        .drop_duplicates(
            "Código"
        )
        .copy()
    )

    product_map["Código"] = _normalize_key(
        product_map["Código"]
    )

    base = pivot.merge(
        product_map,
        on="Código",
        how="left",
    )

    if (
        imports_by_sku is not None
        and not imports_by_sku.empty
        and "Código" in imports_by_sku.columns
    ):
        extra_cols = [
            col
            for col in [
                "Código",
                "Importación_unidades",
                "ETA_más_próxima",
                "Situaciones_importación",
            ]
            if col in imports_by_sku.columns
        ]

        imp = imports_by_sku[
            extra_cols
        ].copy()

        imp["Código"] = _normalize_key(
            imp["Código"]
        )

        base = base.merge(
            imp,
            on="Código",
            how="left",
        )

    for col in [
        "Importación_unidades",
    ]:
        if col not in base.columns:
            base[col] = 0.0

        base[col] = pd.to_numeric(
            base[col],
            errors="coerce",
        ).fillna(0.0)

    if "ETA_más_próxima" not in base.columns:
        base["ETA_más_próxima"] = pd.NaT

    if "Situaciones_importación" not in base.columns:
        base["Situaciones_importación"] = ""

    rows = []

    destinations = [
        ("CASA MATRIZ", "Casa Matriz"),
        ("PATRONATO", "Patronato"),
        ("CONCEPCION", "Concepción"),
    ]

    for row in base.itertuples(
        index=False
    ):
        data = row._asdict()

        sku = str(
            data.get("Código", "")
        )

        product = str(
            data.get("Producto", "")
        )

        cd_stock = float(
            data.get("CD", 0) or 0
        )

        movable_from_cd = max(
            cd_stock - CD_RESERVE,
            0,
        )

        if movable_from_cd <= 0:
            continue

        for destination_col, destination_name in destinations:
            destination_stock = float(
                data.get(
                    destination_col,
                    0,
                )
                or 0
            )

            if destination_stock > LOW_STOCK_THRESHOLD:
                continue

            need = max(
                TRANSFER_TARGET - destination_stock,
                0,
            )

            suggested = min(
                need,
                movable_from_cd,
            )

            if suggested <= 0:
                continue

            if destination_stock <= 0:
                priority = "🔴 Alta"
            elif destination_stock <= 2:
                priority = "🟠 Alta"
            else:
                priority = "🟡 Media"

            rows.append(
                {
                    "Prioridad": priority,
                    "Código": sku,
                    "Producto": product,
                    "Origen": "CD",
                    "Destino": destination_name,
                    "Stock CD": _safe_int(cd_stock),
                    "Stock destino": _safe_int(destination_stock),
                    "Mover sugerido": _safe_int(suggested),
                    "CD después": _safe_int(
                        cd_stock - suggested
                    ),
                    "Destino después": _safe_int(
                        destination_stock + suggested
                    ),
                    "Importación": _safe_int(
                        data.get(
                            "Importación_unidades",
                            0,
                        )
                    ),
                    "ETA": data.get(
                        "ETA_más_próxima",
                        pd.NaT,
                    ),
                    "Estado importación": str(
                        data.get(
                            "Situaciones_importación",
                            "",
                        )
                        or ""
                    ),
                }
            )

    result = pd.DataFrame(
        rows
    )

    if result.empty:
        return result

    priority_order = {
        "🔴 Alta": 1,
        "🟠 Alta": 2,
        "🟡 Media": 3,
    }

    result["_order"] = (
        result["Prioridad"]
        .map(
            priority_order
        )
        .fillna(99)
    )

    return (
        result.sort_values(
            [
                "_order",
                "Stock destino",
                "Stock CD",
            ],
            ascending=[
                True,
                True,
                False,
            ],
        )
        .drop(
            columns=["_order"]
        )
        .reset_index(
            drop=True
        )
    )


def _decision_engine(
    intel_imports: pd.DataFrame,
) -> pd.DataFrame:
    """
    Clasifica cada SKU en una acción ejecutiva:
    COMPRAR / ESPERAR IMPORTACIÓN / TRASLADAR / SALUDABLE /
    SOBRESTOCK / SIN ROTACIÓN.
    """
    if (
        intel_imports is None
        or intel_imports.empty
    ):
        return pd.DataFrame()

    out = intel_imports.copy()

    out["Disponible"] = _num(
        out,
        "Disponible",
    ).clip(
        lower=0
    )

    if "Unidades_30d_demanda" not in out.columns:
        out["Unidades_30d_demanda"] = 0.0

    if "Cobertura días" not in out.columns:
        out["Cobertura días"] = 0.0

    if "Importación_unidades" not in out.columns:
        out["Importación_unidades"] = 0.0

    out["Unidades_30d_demanda"] = pd.to_numeric(
        out["Unidades_30d_demanda"],
        errors="coerce",
    ).fillna(0.0).clip(
        lower=0
    )

    out["Cobertura días"] = pd.to_numeric(
        out["Cobertura días"],
        errors="coerce",
    ).fillna(0.0)

    out["Importación_unidades"] = pd.to_numeric(
        out["Importación_unidades"],
        errors="coerce",
    ).fillna(0.0).clip(
        lower=0
    )

    daily = (
        out["Unidades_30d_demanda"]
        / 30.0
    )

    out["Stock proyectado"] = (
        out["Disponible"]
        + out["Importación_unidades"]
    )

    out["Cobertura proyectada"] = 0.0

    moving = daily > 0

    out.loc[
        moving,
        "Cobertura proyectada",
    ] = (
        out.loc[
            moving,
            "Stock proyectado",
        ]
        / daily[moving]
    )

    out.loc[
        ~moving
        & (
            out["Stock proyectado"] > 0
        ),
        "Cobertura proyectada",
    ] = 9999.0

    def classify(
        row,
    ):
        available = float(
            row.get(
                "Disponible",
                0,
            )
            or 0
        )

        demand30 = float(
            row.get(
                "Unidades_30d_demanda",
                0,
            )
            or 0
        )

        coverage = float(
            row.get(
                "Cobertura días",
                0,
            )
            or 0
        )

        imports = float(
            row.get(
                "Importación_unidades",
                0,
            )
            or 0
        )

        projected = float(
            row.get(
                "Cobertura proyectada",
                0,
            )
            or 0
        )

        if demand30 <= 0 and available > 0:
            return (
                "⚪ SIN ROTACIÓN",
                "Revisar baja rotación",
                5,
            )

        if (
            demand30 > 0
            and coverage > 90
        ):
            return (
                "🔵 SOBRESTOCK",
                "Revisar exceso / redistribuir",
                4,
            )

        if (
            demand30 > 0
            and coverage < 15
        ):
            if imports > 0:
                return (
                    "🟠 ESPERAR IMPORTACIÓN",
                    (
                        "Importación cubre riesgo"
                        if projected >= 30
                        else "Importación parcial; revisar compra"
                    ),
                    2,
                )

            return (
                "🔴 COMPRAR",
                "Sin importación asociada",
                1,
            )

        return (
            "🟢 SALUDABLE",
            "Mantener",
            6,
        )

    classified = out.apply(
        classify,
        axis=1,
        result_type="expand",
    )

    out["Recomendación"] = classified[0]
    out["Acción sugerida"] = classified[1]
    out["_priority"] = classified[2]

    return out.sort_values(
        [
            "_priority",
            "Cobertura días",
            "Disponible",
        ],
        ascending=[
            True,
            True,
            True,
        ],
    )


# ============================================================
# COMPONENTES HTML
# ============================================================

def _kpi(
    label: str,
    value: str,
    helper: str,
    icon: str,
    tone: str,
) -> str:
    return f"""
    <div class="ms-kpi">
        <div class="ms-kpi-icon {tone}">
            {escape(icon)}
        </div>
        <div class="ms-kpi-label">
            {escape(label)}
        </div>
        <div class="ms-kpi-value">
            {escape(value)}
        </div>
        <div class="ms-kpi-helper">
            {escape(helper)}
        </div>
    </div>
    """


# ============================================================
# RENDER
# ============================================================

def render(ctx):
    raw = ctx.get(
        "stock_normalized"
    )

    cons = ctx.get(
        "stock_consolidated"
    )

    sales_df = ctx.get(
        "sales_df"
    )

    stock_meta = (
        ctx.get(
            "stock_meta"
        )
        or {}
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------
    render_html(
        """
        <div class="ms-head">
            <div>
                <div class="ms-eyebrow">
                    MARITEX · ANÁLISIS
                </div>
                <div class="ms-title">
                    Métricas de Stock
                </div>
                <div class="ms-subtitle">
                    Disponibilidad, cobertura, rotación,
                    redistribución e importaciones.
                </div>
            </div>
            <div class="ms-head-badge">
                <i></i>
                Fuentes conectadas
            </div>
        </div>
        """
    )

    if (
        raw is None
        or raw.empty
        or cons is None
        or cons.empty
    ):
        st.info(
            "No hay inventario disponible para analizar."
        )
        return

    # --------------------------------------------------------
    # IMPORTACIONES
    # --------------------------------------------------------
    imports_error = None

    try:
        imports_df, imports_meta = (
            load_remote_imports()
        )
    except Exception as exc:
        imports_df = pd.DataFrame()
        imports_meta = {}
        imports_error = str(exc)

    raw_search = _prepare_search(
        raw
    )

    # --------------------------------------------------------
    # SOURCE BAR
    # --------------------------------------------------------
    render_html(
        f"""
        <div class="ms-source">
            <div class="ms-source-item">
                <span class="dot green"></span>
                <div>
                    <small>STOCK ACTUAL</small>
                    <strong>
                        Llegadas_OK · stock.json
                    </strong>
                </div>
            </div>

            <div class="ms-source-item">
                <span class="dot blue"></span>
                <div>
                    <small>IMPORTACIONES</small>
                    <strong>
                        {
                            "Llegadas_OK · llegadas.json"
                            if imports_error is None
                            else "No disponible"
                        }
                    </strong>
                </div>
            </div>

            <div class="ms-source-item">
                <span class="dot purple"></span>
                <div>
                    <small>VENTAS</small>
                    <strong>
                        {
                            "ERP Ventas"
                            if sales_df is not None
                            and not sales_df.empty
                            else "No disponible"
                        }
                    </strong>
                </div>
            </div>

            <div class="ms-source-update">
                <small>STOCK ACTUALIZADO</small>
                <strong>
                    {_friendly_datetime(stock_meta.get("loaded_at"))}
                </strong>
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------
    filter_cols = st.columns(
        [1.8, 1.0, 1.0],
        gap="small",
    )

    with filter_cols[0]:
        search = st.text_input(
            "Buscar",
            placeholder="Buscar SKU o producto...",
            key="ms_search_v800",
            label_visibility="collapsed",
        )

    with filter_cols[1]:
        statuses = sorted(
            cons[
                "Estado"
            ]
            .fillna("")
            .astype(str)
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .unique()
            .tolist()
        )

        selected_status = st.multiselect(
            "Estado",
            statuses,
            placeholder="Todos los estados",
            key="ms_status_v800",
            label_visibility="collapsed",
        )

    with filter_cols[2]:
        warehouses = sorted(
            raw[
                "Bodega"
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_wh = st.multiselect(
            "Bodega",
            warehouses,
            placeholder="Todas las bodegas",
            key="ms_wh_v800",
            label_visibility="collapsed",
        )

    # --------------------------------------------------------
    # FILTER RAW
    # --------------------------------------------------------
    fr = raw_search.copy()

    if search:
        term = (
            search
            .lower()
            .strip()
        )

        fr = fr[
            fr[
                "_search_codigo"
            ].str.contains(
                term,
                regex=False,
            )
            |
            fr[
                "_search_producto"
            ].str.contains(
                term,
                regex=False,
            )
        ]

    if selected_wh:
        fr = fr[
            fr[
                "Bodega"
            ].fillna(
                ""
            ).astype(
                str
            ).isin(
                selected_wh
            )
        ]

    fr_clean = fr.drop(
        columns=[
            "_search_codigo",
            "_search_producto",
        ],
        errors="ignore",
    )

    has_base_filters = bool(
        search
        or selected_wh
    )

    filtered = (
        consolidate_inventory(
            fr_clean
        )
        if has_base_filters
        else cons.copy()
    )

    if selected_status:
        filtered = filtered[
            filtered[
                "Estado"
            ]
            .fillna("")
            .astype(str)
            .isin(
                selected_status
            )
        ].copy()

    if filtered.empty:
        st.info(
            "No existen registros para los filtros seleccionados."
        )
        return

    # --------------------------------------------------------
    # SALES INTELLIGENCE
    # --------------------------------------------------------
    intel, sales_meta = (
        _sales_intelligence(
            filtered,
            sales_df,
        )
    )

    # --------------------------------------------------------
    # IMPORT INTELLIGENCE
    # --------------------------------------------------------
    imports, intel_imports = (
        _prepare_imports(
            imports_df,
            intel,
        )
    )

    state = (
        filtered[
            "Estado"
        ]
        .fillna("")
        .astype(str)
    )

    sku = int(
        filtered[
            "Código"
        ].nunique()
    )

    units = _safe_int(
        _num(
            filtered,
            "Disponible",
        ).sum()
    )

    low = int(
        state.eq(
            "🟡 Stock bajo"
        ).sum()
    )

    zero = int(
        state.isin(
            [
                "🔴 Sin stock",
                "🔴 Negativo",
            ]
        ).sum()
    )

    ok = int(
        state.eq(
            "🟢 Disponible"
        ).sum()
    )

    healthy_pct = (
        ok / max(
            sku,
            1,
        ) * 100
    )

    if sales_meta["enabled"]:
        total_demand_30 = float(
            intel[
                "Unidades_30d_demanda"
            ].sum()
        )

        coverage_total = (
            units
            / (
                total_demand_30
                / 30.0
            )
            if total_demand_30 > 0
            else 0.0
        )
    else:
        coverage_total = 0.0

    # Import KPIs
    import_units = _safe_int(
        _num(
            imports,
            "Unidades importación",
        ).sum()
    )

    import_orders = (
        int(
            imports[
                "Orden"
            ]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        )
        if not imports.empty
        else 0
    )

    # --------------------------------------------------------
    # KPIs DE DECISIÓN
    # --------------------------------------------------------
    decision_preview = _decision_engine(
        intel_imports
    )

    risk_break = (
        int(
            (
                (decision_preview["Cobertura días"] < 15)
                & (decision_preview["Unidades_30d_demanda"] > 0)
            ).sum()
        )
        if not decision_preview.empty
        else 0
    )

    overstock_count = (
        int(
            decision_preview[
                "Recomendación"
            ].eq(
                "🔵 SOBRESTOCK"
            ).sum()
        )
        if not decision_preview.empty
        else 0
    )

    no_rotation_count = (
        int(
            decision_preview[
                "Recomendación"
            ].eq(
                "⚪ SIN ROTACIÓN"
            ).sum()
        )
        if not decision_preview.empty
        else 0
    )

    render_html(
        f"""
        <div class="ms-kpi-grid">
            {_kpi(
                "COBERTURA GLOBAL",
                (
                    f"{coverage_total:.0f} días"
                    if sales_meta["enabled"]
                    and coverage_total > 0
                    else "—"
                ),
                (
                    "stock actual según demanda 30d"
                    if sales_meta["enabled"]
                    else "requiere cruce con ventas"
                ),
                "↻",
                "blue",
            )}
            {_kpi(
                "RIESGO DE QUIEBRE",
                _fmt_int(risk_break),
                "SKU con menos de 15 días",
                "!",
                "orange",
            )}
            {_kpi(
                "SOBRESTOCK",
                _fmt_int(overstock_count),
                "SKU con más de 90 días",
                "↑",
                "purple",
            )}
            {_kpi(
                "SIN ROTACIÓN",
                _fmt_int(no_rotation_count),
                "SKU con stock y sin venta 30d",
                "—",
                "green",
            )}
            {_kpi(
                "IMPORTACIONES",
                _fmt_int(import_units),
                f"{_fmt_int(import_orders)} órdenes publicadas",
                "⇢",
                "lime",
            )}
        </div>
        """
    )


    # ========================================================
    # SALUD DEL INVENTARIO / MOTOR DE DECISIÓN
    # ========================================================
    if not decision_preview.empty:
        health_order = [
            "🔴 COMPRAR",
            "🟠 ESPERAR IMPORTACIÓN",
            "🔵 SOBRESTOCK",
            "⚪ SIN ROTACIÓN",
            "🟢 SALUDABLE",
        ]

        health = (
            decision_preview.groupby(
                "Recomendación",
                as_index=False,
            )
            .agg(
                SKU=(
                    "Código",
                    "nunique",
                )
            )
        )

        health["Orden"] = (
            health[
                "Recomendación"
            ].map(
                {
                    name: i
                    for i, name in enumerate(
                        health_order
                    )
                }
            )
        )

        health = health.sort_values(
            "Orden"
        )

        render_html(
            """
            <div class="ms-section-head">
                <div>
                    <strong>Salud del inventario</strong>
                    <span>
                        Clasificación automática orientada a decisiones
                    </span>
                </div>
            </div>
            """
        )

        h1, h2 = st.columns(
            [1.0, 1.4],
            gap="medium",
        )

        with h1:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Distribución por recomendación</strong>
                            <span>Qué acción requiere cada SKU</span>
                        </div>
                    </div>
                    """
                )

                chart = (
                    alt.Chart(
                        health
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#27313b",
                    )
                    .encode(
                        y=alt.Y(
                            "Recomendación:N",
                            sort=health_order,
                            title=None,
                            axis=alt.Axis(
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                                labelLimit=180,
                            ),
                        ),
                        x=alt.X(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#eef1f4",
                            ),
                        ),
                        tooltip=[
                            "Recomendación:N",
                            alt.Tooltip(
                                "SKU:Q",
                                format=",",
                            ),
                        ],
                    )
                    .properties(
                        height=250
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

        with h2:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Productos que requieren acción</strong>
                            <span>Prioridad según cobertura e importaciones</span>
                        </div>
                    </div>
                    """
                )

                action_table = (
                    decision_preview[
                        decision_preview[
                            "Recomendación"
                        ].ne(
                            "🟢 SALUDABLE"
                        )
                    ]
                    .head(
                        18
                    )
                    .copy()
                )

                cols = [
                    col
                    for col in [
                        "Código",
                        "Producto",
                        "Disponible",
                        "Unidades_30d",
                        "Cobertura días",
                        "Importación_unidades",
                        "ETA_más_próxima",
                        "Cobertura proyectada",
                        "Recomendación",
                        "Acción sugerida",
                    ]
                    if col in action_table.columns
                ]

                if action_table.empty:
                    render_html(
                        """
                        <div class="ms-empty">
                            No hay acciones pendientes.
                        </div>
                        """
                    )
                else:
                    st.dataframe(
                        action_table[
                            cols
                        ],
                        hide_index=True,
                        use_container_width=True,
                        height=310,
                        column_config={
                            "Código": st.column_config.TextColumn(
                                "SKU",
                                width="small",
                            ),
                            "Producto": st.column_config.TextColumn(
                                "Producto",
                                width="large",
                            ),
                            "Disponible": st.column_config.NumberColumn(
                                "Stock",
                                format="%d",
                            ),
                            "Unidades_30d": st.column_config.NumberColumn(
                                "Venta 30d",
                                format="%.0f",
                            ),
                            "Cobertura días": st.column_config.NumberColumn(
                                "Cobertura",
                                format="%.1f días",
                            ),
                            "Importación_unidades": st.column_config.NumberColumn(
                                "Importación",
                                format="%d",
                            ),
                            "ETA_más_próxima": st.column_config.DateColumn(
                                "ETA",
                                format="DD/MM/YYYY",
                            ),
                            "Cobertura proyectada": st.column_config.NumberColumn(
                                "Cob. proyectada",
                                format="%.1f días",
                            ),
                            "Recomendación": st.column_config.TextColumn(
                                "Estado",
                                width="medium",
                            ),
                            "Acción sugerida": st.column_config.TextColumn(
                                "Acción",
                                width="medium",
                            ),
                        },
                    )

    # ========================================================
    # IMPORTACIONES
    # ========================================================
    render_html(
        """
        <div class="ms-section-head">
            <div>
                <strong>Estado de importaciones</strong>
                <span>
                    Órdenes, unidades y ETA publicadas por Llegadas_OK
                </span>
            </div>
        </div>
        """
    )

    if imports_error:
        st.warning(
            "No fue posible cargar llegadas.json: "
            + imports_error
        )

    elif imports.empty:
        st.info(
            "Llegadas_OK no tiene importaciones publicadas actualmente."
        )

    else:
        status_summary = (
            _import_status_summary(
                imports
            )
        )

        today = pd.Timestamp(
            date.today()
        )

        future = imports[
            imports["ETA"].notna()
        ].copy()

        next_7 = _safe_int(
            future.loc[
                future["ETA"].between(
                    today,
                    today
                    + pd.Timedelta(
                        days=7
                    ),
                    inclusive="both",
                ),
                "Unidades importación",
            ].sum()
        )

        next_30 = _safe_int(
            future.loc[
                future["ETA"].between(
                    today,
                    today
                    + pd.Timedelta(
                        days=30
                    ),
                    inclusive="both",
                ),
                "Unidades importación",
            ].sum()
        )

        late_units = _safe_int(
            future.loc[
                future["ETA"] < today,
                "Unidades importación",
            ].sum()
        )

        import_kpis = st.columns(
            4,
            gap="small",
        )

        with import_kpis[0]:
            render_html(
                f"""
                <div class="ms-import-mini">
                    <span>ÓRDENES ACTIVAS</span>
                    <strong>{_fmt_int(import_orders)}</strong>
                    <small>{_fmt_int(import_units)} unidades</small>
                </div>
                """
            )

        with import_kpis[1]:
            render_html(
                f"""
                <div class="ms-import-mini">
                    <span>LLEGAN EN 7 DÍAS</span>
                    <strong>{_fmt_int(next_7)}</strong>
                    <small>unidades con ETA próxima</small>
                </div>
                """
            )

        with import_kpis[2]:
            render_html(
                f"""
                <div class="ms-import-mini">
                    <span>LLEGAN EN 30 DÍAS</span>
                    <strong>{_fmt_int(next_30)}</strong>
                    <small>unidades programadas</small>
                </div>
                """
            )

        with import_kpis[3]:
            render_html(
                f"""
                <div class="ms-import-mini">
                    <span>ETA VENCIDA</span>
                    <strong>{_fmt_int(late_units)}</strong>
                    <small>unidades por revisar</small>
                </div>
                """
            )

        i1, i2 = st.columns(
            [1.0, 1.55],
            gap="medium",
        )

        with i1:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Importaciones por estado</strong>
                            <span>Unidades publicadas</span>
                        </div>
                    </div>
                    """
                )

                if not status_summary.empty:
                    chart = (
                        alt.Chart(
                            status_summary
                        )
                        .mark_bar(
                            cornerRadiusEnd=5,
                            color="#27313b",
                        )
                        .encode(
                            y=alt.Y(
                                "Situación:N",
                                sort="-x",
                                title=None,
                                axis=alt.Axis(
                                    labelColor="#66717c",
                                    domain=False,
                                    ticks=False,
                                ),
                            ),
                            x=alt.X(
                                "Unidades:Q",
                                title=None,
                                axis=alt.Axis(
                                    labelColor="#7c8792",
                                    domain=False,
                                    gridColor="#eef1f4",
                                    format="~s",
                                ),
                            ),
                            tooltip=[
                                alt.Tooltip(
                                    "Situación:N",
                                    title="Estado",
                                ),
                                alt.Tooltip(
                                    "Unidades:Q",
                                    title="Unidades",
                                    format=",",
                                ),
                                alt.Tooltip(
                                    "Órdenes:Q",
                                    title="Órdenes",
                                    format=",",
                                ),
                                alt.Tooltip(
                                    "SKU:Q",
                                    title="SKU",
                                    format=",",
                                ),
                            ],
                        )
                        .properties(
                            height=260
                        )
                    )

                    st.altair_chart(
                        chart,
                        use_container_width=True,
                    )

        with i2:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Próximos arribos</strong>
                            <span>Primeros ETA informados por SKU</span>
                        </div>
                    </div>
                    """
                )

                upcoming = _next_arrivals(
                    imports,
                    limit=10,
                )

                if upcoming.empty:
                    render_html(
                        """
                        <div class="ms-empty">
                            No hay ETA disponibles.
                        </div>
                        """
                    )
                else:
                    table = upcoming[
                        [
                            "Orden",
                            "SKU",
                            "Producto importación",
                            "Situación",
                            "ETA",
                            "Unidades importación",
                        ]
                    ].copy()

                    st.dataframe(
                        table,
                        hide_index=True,
                        use_container_width=True,
                        height=300,
                        column_config={
                            "Orden": st.column_config.TextColumn(
                                "OC",
                                width="small",
                            ),
                            "SKU": st.column_config.TextColumn(
                                "SKU",
                                width="small",
                            ),
                            "Producto importación": st.column_config.TextColumn(
                                "Producto",
                                width="large",
                            ),
                            "Situación": st.column_config.TextColumn(
                                "Estado",
                                width="small",
                            ),
                            "ETA": st.column_config.DateColumn(
                                "ETA",
                                format="DD/MM/YYYY",
                            ),
                            "Unidades importación": st.column_config.NumberColumn(
                                "Unidades",
                                format="%d",
                            ),
                        },
                    )

    # ========================================================
    # DISTRIBUCIÓN ACTUAL
    # ========================================================
    render_html(
        """
        <div class="ms-section-head">
            <div>
                <strong>Distribución del inventario</strong>
                <span>
                    Stock actual y concentración por disponibilidad
                </span>
            </div>
        </div>
        """
    )

    d1, d2 = st.columns(
        [1.35, 1.0],
        gap="medium",
    )

    with d1:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="ms-card-head">
                    <div>
                        <strong>Stock por bodega</strong>
                        <span>Unidades disponibles</span>
                    </div>
                </div>
                """
            )

            wh = _warehouse_summary(
                fr_clean
            )

            if not wh.empty:
                chart = (
                    alt.Chart(
                        wh
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#242b32",
                    )
                    .encode(
                        y=alt.Y(
                            "Bodega:N",
                            sort="-x",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "Disponible:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#eef1f4",
                                format="~s",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Bodega:N",
                                title="Bodega",
                            ),
                            alt.Tooltip(
                                "Disponible:Q",
                                title="Disponible",
                                format=",",
                            ),
                        ],
                    )
                    .properties(
                        height=270
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

    with d2:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="ms-card-head">
                    <div>
                        <strong>Rangos de disponibilidad</strong>
                        <span>SKU agrupados por stock actual</span>
                    </div>
                </div>
                """
            )

            ranges = _availability_ranges(
                filtered
            )

            order = [
                "0",
                "1-5",
                "6-20",
                "21-50",
                "+50",
            ]

            if not ranges.empty:
                chart = (
                    alt.Chart(
                        ranges
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#6536f3",
                    )
                    .encode(
                        y=alt.Y(
                            "Rango:N",
                            sort=order,
                            title=None,
                            axis=alt.Axis(
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#eef1f4",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Rango:N",
                                title="Disponibilidad",
                            ),
                            alt.Tooltip(
                                "SKU:Q",
                                title="SKU",
                                format=",",
                            ),
                        ],
                    )
                    .properties(
                        height=270
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

    # ========================================================
    # STOCK BAJO + IMPORTACIONES
    # ========================================================
    render_html(
        """
        <div class="ms-section-head">
            <div>
                <strong>Stock bajo vs. importaciones</strong>
                <span>
                    Distingue SKU críticos con y sin mercadería en camino
                </span>
            </div>
        </div>
        """
    )

    action_base = (
        intel_imports.copy()
    )

    action_base[
        "Disponible"
    ] = _num(
        action_base,
        "Disponible",
    )

    low_mask = (
        action_base[
            "Estado"
        ]
        .fillna("")
        .astype(str)
        .isin(
            [
                "🟡 Stock bajo",
                "🔴 Sin stock",
                "🔴 Negativo",
            ]
        )
    )

    stock_low = (
        action_base[
            low_mask
        ]
        .copy()
    )

    if stock_low.empty:
        st.success(
            "No existen SKU con stock bajo o sin disponibilidad."
        )

    else:
        stock_low[
            "Importación_unidades"
        ] = pd.to_numeric(
            stock_low[
                "Importación_unidades"
            ],
            errors="coerce",
        ).fillna(0)

        stock_low[
            "Cobertura importación"
        ] = (
            stock_low[
                "Importación_unidades"
            ]
            > 0
        ).map(
            {
                True: "Con importación",
                False: "Sin importación",
            }
        )

        with_import = int(
            stock_low[
                "Cobertura importación"
            ].eq(
                "Con importación"
            ).sum()
        )

        without_import = int(
            stock_low[
                "Cobertura importación"
            ].eq(
                "Sin importación"
            ).sum()
        )

        render_html(
            f"""
            <div class="ms-risk-strip">
                <div>
                    <span>CRÍTICOS CON IMPORTACIÓN</span>
                    <strong>{_fmt_int(with_import)}</strong>
                    <small>SKU con unidades en camino</small>
                </div>
                <div class="danger">
                    <span>CRÍTICOS SIN IMPORTACIÓN</span>
                    <strong>{_fmt_int(without_import)}</strong>
                    <small>requieren revisión prioritaria</small>
                </div>
            </div>
            """
        )

        risk_table = stock_low[
            [
                col
                for col in [
                    "Código",
                    "Producto",
                    "Disponible",
                    "Importación_unidades",
                    "ETA_más_próxima",
                    "Órdenes_importación",
                    "Situaciones_importación",
                    "Cobertura importación",
                ]
                if col in stock_low.columns
            ]
        ].copy()

        risk_table = risk_table.sort_values(
            [
                "Cobertura importación",
                "Disponible",
            ],
            ascending=[
                False,
                True,
            ],
        ).head(
            30
        )

        st.dataframe(
            risk_table,
            hide_index=True,
            use_container_width=True,
            height=430,
            column_config={
                "Código": st.column_config.TextColumn(
                    "SKU",
                    width="small",
                ),
                "Producto": st.column_config.TextColumn(
                    "Producto",
                    width="large",
                ),
                "Disponible": st.column_config.NumberColumn(
                    "Stock",
                    format="%d",
                ),
                "Importación_unidades": st.column_config.NumberColumn(
                    "En importación",
                    format="%d",
                ),
                "ETA_más_próxima": st.column_config.DateColumn(
                    "ETA",
                    format="DD/MM/YYYY",
                ),
                "Órdenes_importación": st.column_config.TextColumn(
                    "OC",
                ),
                "Situaciones_importación": st.column_config.TextColumn(
                    "Estado importación",
                    width="medium",
                ),
                "Cobertura importación": st.column_config.TextColumn(
                    "Reposición",
                    width="small",
                ),
            },
        )

    # ========================================================
    # ROTACIÓN + ABC
    # ========================================================
    render_html(
        """
        <div class="ms-section-head">
            <div>
                <strong>Rotación y cobertura</strong>
                <span>
                    Inteligencia construida con ERP Ventas
                </span>
            </div>
        </div>
        """
    )

    if sales_meta["enabled"]:
        r1, r2 = st.columns(
            2,
            gap="medium",
        )

        with r1:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Cobertura estimada</strong>
                            <span>Días de stock según venta últimos 30 días</span>
                        </div>
                    </div>
                    """
                )

                coverage = (
                    intel.groupby(
                        "Rango cobertura",
                        as_index=False,
                    )
                    .agg(
                        SKU=(
                            "Código",
                            "nunique",
                        )
                    )
                )

                order = [
                    "< 15 días",
                    "15-29 días",
                    "30-90 días",
                    "> 90 días",
                    "Sin venta 30d",
                ]

                chart = (
                    alt.Chart(
                        coverage
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#4f7cd7",
                    )
                    .encode(
                        y=alt.Y(
                            "Rango cobertura:N",
                            sort=order,
                            title=None,
                            axis=alt.Axis(
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#eef1f4",
                            ),
                        ),
                        tooltip=[
                            "Rango cobertura:N",
                            alt.Tooltip(
                                "SKU:Q",
                                format=",",
                            ),
                        ],
                    )
                    .properties(
                        height=270
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

        with r2:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Clasificación ABC</strong>
                            <span>Concentración según venta últimos 90 días</span>
                        </div>
                    </div>
                    """
                )

                abc = (
                    intel.groupby(
                        "ABC",
                        as_index=False,
                    )
                    .agg(
                        SKU=(
                            "Código",
                            "nunique",
                        ),
                        Venta_90d=(
                            "Venta_90d",
                            "sum",
                        ),
                    )
                )

                chart = (
                    alt.Chart(
                        abc
                    )
                    .mark_bar(
                        cornerRadiusTopLeft=5,
                        cornerRadiusTopRight=5,
                        color="#7fc800",
                    )
                    .encode(
                        x=alt.X(
                            "ABC:N",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        y=alt.Y(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#eef1f4",
                            ),
                        ),
                        tooltip=[
                            "ABC:N",
                            alt.Tooltip(
                                "SKU:Q",
                                title="SKU",
                                format=",",
                            ),
                            alt.Tooltip(
                                "Venta_90d:Q",
                                title="Venta 90d",
                                format=",.0f",
                            ),
                        ],
                    )
                    .properties(
                        height=270
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

    else:
        render_html(
            f"""
            <div class="ms-info-box">
                <strong>Rotación no disponible</strong>
                <span>{escape(sales_meta["reason"])}</span>
            </div>
            """
        )

    # ========================================================
    # MOVIMIENTOS ENTRE BODEGAS · CD ABASTECE DESTINOS
    # ========================================================
    movement = _transfer_recommendations(
        fr_clean,
        intel_imports,
    )

    movement_units = (
        _safe_int(
            movement[
                "Mover sugerido"
            ].sum()
        )
        if not movement.empty
        else 0
    )

    movement_skus = (
        int(
            movement[
                "Código"
            ].nunique()
        )
        if not movement.empty
        else 0
    )

    render_html(
        f"""
        <div class="ms-section-head">
            <div>
                <strong>Posibilidad de movimiento entre bodegas</strong>
                <span>
                    CD abastece Casa Matriz, Patronato y Concepción
                </span>
            </div>
            <div class="ms-section-count">
                {_fmt_int(movement_skus)} SKU
            </div>
        </div>
        """
    )

    render_html(
        f"""
        <div class="ms-movement-summary">
            <div>
                <span>SKU CON POSIBILIDAD</span>
                <strong>{_fmt_int(movement_skus)}</strong>
                <small>productos que CD puede abastecer</small>
            </div>
            <div>
                <span>UNIDADES SUGERIDAS</span>
                <strong>{_fmt_int(movement_units)}</strong>
                <small>movimiento total recomendado</small>
            </div>
            <div>
                <span>REGLA</span>
                <strong>CD → sucursales</strong>
                <small>
                    destino ≤ {LOW_STOCK_THRESHOLD} · CD conserva {CD_RESERVE}
                </small>
            </div>
        </div>
        """
    )

    if movement.empty:
        st.success(
            "No se detectan movimientos recomendados desde CD con la regla actual."
        )
    else:
        # Resumen por destino
        by_destination = (
            movement.groupby(
                "Destino",
                as_index=False,
            )
            .agg(
                SKU=(
                    "Código",
                    "nunique",
                ),
                Unidades=(
                    "Mover sugerido",
                    "sum",
                ),
            )
        )

        m1, m2 = st.columns(
            [0.8, 1.7],
            gap="medium",
        )

        with m1:
            with st.container(
                border=True
            ):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Movimientos por destino</strong>
                            <span>Unidades sugeridas desde CD</span>
                        </div>
                    </div>
                    """
                )

                chart = (
                    alt.Chart(
                        by_destination
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#d8ff00",
                    )
                    .encode(
                        y=alt.Y(
                            "Destino:N",
                            sort="-x",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "Unidades:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#eef1f4",
                            ),
                        ),
                        tooltip=[
                            "Destino:N",
                            alt.Tooltip(
                                "SKU:Q",
                                format=",",
                            ),
                            alt.Tooltip(
                                "Unidades:Q",
                                format=",",
                            ),
                        ],
                    )
                    .properties(
                        height=220
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

        with m2:
            movement_display = (
                movement.head(
                    50
                )
                .copy()
            )

            st.dataframe(
                movement_display,
                hide_index=True,
                use_container_width=True,
                height=360,
                column_config={
                    "Prioridad": st.column_config.TextColumn(
                        "Prioridad",
                        width="small",
                    ),
                    "Código": st.column_config.TextColumn(
                        "SKU",
                        width="small",
                    ),
                    "Producto": st.column_config.TextColumn(
                        "Producto",
                        width="large",
                    ),
                    "Origen": st.column_config.TextColumn(
                        "Origen",
                        width="small",
                    ),
                    "Destino": st.column_config.TextColumn(
                        "Destino",
                        width="small",
                    ),
                    "Stock CD": st.column_config.NumberColumn(
                        "CD actual",
                        format="%d",
                    ),
                    "Stock destino": st.column_config.NumberColumn(
                        "Destino actual",
                        format="%d",
                    ),
                    "Mover sugerido": st.column_config.NumberColumn(
                        "Mover",
                        format="%d",
                    ),
                    "CD después": st.column_config.NumberColumn(
                        "CD después",
                        format="%d",
                    ),
                    "Destino después": st.column_config.NumberColumn(
                        "Destino después",
                        format="%d",
                    ),
                    "Importación": st.column_config.NumberColumn(
                        "Importación",
                        format="%d",
                    ),
                    "ETA": st.column_config.DateColumn(
                        "ETA",
                        format="DD/MM/YYYY",
                    ),
                    "Estado importación": st.column_config.TextColumn(
                        "Estado importación",
                        width="medium",
                    ),
                },
            )

    # ========================================================
    # DETALLE
    # ========================================================
    with st.expander(
        "Ver detalle completo",
        expanded=False,
    ):
        detail = fr_clean.copy()

        if selected_status:
            allowed = set(
                filtered[
                    "Código"
                ]
                .dropna()
                .astype(str)
                .tolist()
            )

            detail = detail[
                detail[
                    "Código"
                ]
                .fillna("")
                .astype(str)
                .isin(
                    allowed
                )
            ].copy()

        columns = [
            col
            for col in [
                "Estado",
                "Código",
                "Producto",
                "Bodega",
                "Stock físico",
                "Disponible",
            ]
            if col in detail.columns
        ]

        st.dataframe(
            detail[
                columns
            ],
            hide_index=True,
            use_container_width=True,
            height=520,
            column_config={
                "Código": st.column_config.TextColumn(
                    "SKU",
                ),
                "Producto": st.column_config.TextColumn(
                    "Producto",
                    width="large",
                ),
                "Bodega": st.column_config.TextColumn(
                    "Bodega",
                ),
                "Disponible": st.column_config.NumberColumn(
                    "Disponible",
                    format="%d",
                ),
                "Stock físico": st.column_config.NumberColumn(
                    "Stock físico",
                    format="%d",
                ),
            },
        )
