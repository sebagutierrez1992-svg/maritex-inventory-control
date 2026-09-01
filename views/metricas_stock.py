from __future__ import annotations

from datetime import date
from html import escape
from zoneinfo import ZoneInfo
import math

import altair as alt
import pandas as pd
import streamlit as st

from analytics.stock_metrics import consolidate_inventory
from services.remote_stock import load_remote_imports
from services.movimientos_cm import load_cm_movements, build_cm_rotation_metrics
from ui.components import render_html


# ============================================================
# HELPERS
# ============================================================

CHILE_TZ = ZoneInfo("America/Santiago")

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

        chile_dt = dt.tz_convert(CHILE_TZ)
        return chile_dt.strftime(
            "%d/%m/%Y · %H:%M"
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
# MOVIMIENTOS FÍSICOS CM / ROTACIÓN / COBERTURA
# ============================================================

def _movement_intelligence(
    inventory: pd.DataFrame,
    rotation_df: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    """
    Construye la inteligencia de cobertura usando SALIDAS físicas
    de Casa Matriz. No interpreta las salidas como ventas.
    """
    empty_meta = {
        "enabled": False,
        "reason": "Histórico de movimientos Casa Matriz no disponible.",
        "source": "Movimientos CM",
        "max_date": pd.NaT,
    }

    if (
        inventory is None
        or inventory.empty
        or rotation_df is None
        or rotation_df.empty
    ):
        return inventory.copy(), empty_meta

    rot = rotation_df.copy()
    rot["SKU"] = _normalize_key(rot["SKU"])

    out = inventory.copy()
    out["_sku_key"] = _normalize_key(out["Código"])

    keep = [
        col
        for col in [
            "SKU",
            "Salidas_30d",
            "Salidas_60d",
            "Salidas_90d",
            "Frecuencia_30d",
            "Frecuencia_60d",
            "Frecuencia_90d",
            "Última_salida",
            "Días_sin_salida",
            "Último_saldo_CM",
            "Tendencia_movimiento",
            "Estado_rotación",
            "Salidas_mes_-2",
            "Salidas_mes_-1",
            "Salidas_mes_actual",
            "Fecha_inicio_histórico",
            "Fecha_fin_histórico",
        ]
        if col in rot.columns
    ]

    rot = rot[keep].rename(columns={"SKU": "_sku_key"})
    rot["Tiene_historial_CM"] = True

    out = out.merge(
        rot,
        on="_sku_key",
        how="left",
    )

    out["Tiene_historial_CM"] = (
        out["Tiene_historial_CM"]
        .fillna(False)
        .astype(bool)
    )

    numeric_defaults = [
        "Salidas_30d",
        "Salidas_60d",
        "Salidas_90d",
        "Frecuencia_30d",
        "Frecuencia_60d",
        "Frecuencia_90d",
        "Último_saldo_CM",
        "Salidas_mes_-2",
        "Salidas_mes_-1",
        "Salidas_mes_actual",
    ]

    for col in numeric_defaults:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(
            out[col],
            errors="coerce",
        ).fillna(0.0)

    if "Días_sin_salida" not in out.columns:
        out["Días_sin_salida"] = pd.NA

    out["Días_sin_salida"] = pd.to_numeric(
        out["Días_sin_salida"],
        errors="coerce",
    )

    # 9999 era un sentinel técnico. Para presentación y análisis,
    # los SKU sin historial deben quedar como dato desconocido.
    no_history = ~out["Tiene_historial_CM"]
    out.loc[no_history, "Días_sin_salida"] = pd.NA

    if "Última_salida" not in out.columns:
        out["Última_salida"] = pd.NaT
    out["Última_salida"] = pd.to_datetime(
        out["Última_salida"],
        errors="coerce",
    )

    for col, default in [
        ("Tendencia_movimiento", "⚪ Sin movimiento"),
        ("Estado_rotación", "⚪ Sin movimiento 90d"),
    ]:
        if col not in out.columns:
            out[col] = default
        out[col] = out[col].fillna(default).astype(str)

    out.loc[
        ~out["Tiene_historial_CM"],
        "Tendencia_movimiento",
    ] = "⚫ Sin historial"

    out.loc[
        ~out["Tiene_historial_CM"],
        "Estado_rotación",
    ] = "⚫ Sin historial CM"

    # Compatibilidad con el motor de decisión existente.
    # Estas columnas representan unidades de MOVIMIENTO, no ventas.
    out["Unidades_30d"] = out["Salidas_30d"].clip(lower=0)
    out["Unidades_90d"] = out["Salidas_90d"].clip(lower=0)
    out["Unidades_30d_demanda"] = out["Salidas_30d"].clip(lower=0)

    # Mantener columnas históricas que espera la vista.
    # Para el ABC físico, Venta_90d_abc usa unidades de salida.
    out["Venta_30d"] = out["Salidas_30d"].clip(lower=0)
    out["Venta_90d"] = out["Salidas_90d"].clip(lower=0)
    out["Venta_90d_abc"] = out["Salidas_90d"].clip(lower=0)

    daily = out["Unidades_30d_demanda"] / 30.0
    available = _num(out, "Disponible").clip(lower=0)

    out["Cobertura días"] = pd.Series(
        float("nan"),
        index=out.index,
        dtype="float64",
    )

    moving = daily > 0
    has_history = out["Tiene_historial_CM"]

    out.loc[
        moving & has_history,
        "Cobertura días",
    ] = (
        available[moving & has_history]
        / daily[moving & has_history]
    )

    # Para SKU con historial real pero sin salidas 30d,
    # mantenemos cobertura abierta como 9999 para el motor.
    out.loc[
        (~moving)
        & has_history
        & (available > 0),
        "Cobertura días",
    ] = 9999.0

    def coverage_label(days, units_30, has_history):
        if not has_history:
            return "Sin historial"
        if units_30 <= 0:
            return "Sin salida 30d"
        if days < 15:
            return "< 15 días"
        if days < 30:
            return "15-29 días"
        if days <= 90:
            return "30-90 días"
        return "> 90 días"

    out["Rango cobertura"] = [
        coverage_label(days, units, has_history)
        for days, units, has_history in zip(
            out["Cobertura días"],
            out["Unidades_30d_demanda"],
            out["Tiene_historial_CM"],
        )
    ]


    # Columnas de presentación: evitamos mostrar sentinels técnicos.
    observed_start = pd.to_datetime(
        out.get("Fecha_inicio_histórico"),
        errors="coerce",
    )
    observed_end = pd.to_datetime(
        out.get("Fecha_fin_histórico"),
        errors="coerce",
    )

    last_exit = pd.to_datetime(
        out["Última_salida"],
        errors="coerce",
    )

    no_exit_in_period = (
        out["Tiene_historial_CM"]
        & last_exit.isna()
    )

    out["Última salida visible"] = last_exit.dt.strftime("%d/%m/%Y")
    out.loc[
        no_exit_in_period,
        "Última salida visible",
    ] = "Sin salida en período"
    out.loc[
        ~out["Tiene_historial_CM"],
        "Última salida visible",
    ] = "Sin historial CM"

    out["Días sin salida visible"] = ""
    valid_days = pd.to_numeric(
        out["Días_sin_salida"],
        errors="coerce",
    )

    out.loc[
        valid_days.notna(),
        "Días sin salida visible",
    ] = valid_days[valid_days.notna()].round().astype(int).astype(str)

    observed_days = (
        observed_end - observed_start
    ).dt.days

    out.loc[
        no_exit_in_period & observed_days.notna(),
        "Días sin salida visible",
    ] = (
        "Sin salida en "
        + observed_days[
            no_exit_in_period & observed_days.notna()
        ].round().astype(int).astype(str)
        + " días observados"
    )

    out.loc[
        ~out["Tiene_historial_CM"],
        "Días sin salida visible",
    ] = "Sin historial CM"

    out["Cobertura visible"] = ""
    coverage_num = pd.to_numeric(
        out["Cobertura días"],
        errors="coerce",
    )

    finite_cov = (
        coverage_num.notna()
        & coverage_num.lt(9999)
    )

    out.loc[
        finite_cov,
        "Cobertura visible",
    ] = (
        coverage_num[finite_cov]
        .round(1)
        .astype(str)
        + " días"
    )

    out.loc[
        no_exit_in_period,
        "Cobertura visible",
    ] = "Sin consumo reciente"

    out.loc[
        ~out["Tiene_historial_CM"],
        "Cobertura visible",
    ] = "Sin historial CM"

    abc_base = out.sort_values(
        "Venta_90d_abc",
        ascending=False,
    ).copy()

    total_moves = float(abc_base["Venta_90d_abc"].sum())

    if total_moves > 0:
        abc_base["_cum"] = (
            abc_base["Venta_90d_abc"].cumsum()
            / total_moves
        )

        abc_base["ABC"] = "C"
        abc_base.loc[abc_base["_cum"] <= 0.80, "ABC"] = "A"
        abc_base.loc[
            (abc_base["_cum"] > 0.80)
            & (abc_base["_cum"] <= 0.95),
            "ABC",
        ] = "B"

        first_over = abc_base.index[
            abc_base["_cum"] > 0.80
        ]
        if len(first_over):
            abc_base.loc[first_over[0], "ABC"] = "A"
    else:
        abc_base["ABC"] = "Sin clasificación"

    out = (
        out.drop(columns=["ABC"], errors="ignore")
        .merge(
            abc_base[["_sku_key", "ABC"]],
            on="_sku_key",
            how="left",
        )
    )

    max_exit = out["Última_salida"].max()

    hist_dates = pd.to_datetime(
        rotation_df.get(
            "Última_salida",
            pd.Series(dtype="datetime64[ns]"),
        ),
        errors="coerce",
    )

    observed_start = pd.to_datetime(
        rotation_df.get(
            "Fecha_inicio_histórico",
            pd.Series(dtype="datetime64[ns]"),
        ),
        errors="coerce",
    ).min() if "Fecha_inicio_histórico" in rotation_df.columns else pd.NaT

    observed_end = pd.to_datetime(
        rotation_df.get(
            "Fecha_fin_histórico",
            pd.Series(dtype="datetime64[ns]"),
        ),
        errors="coerce",
    ).max() if "Fecha_fin_histórico" in rotation_df.columns else pd.NaT

    meta = {
        "enabled": True,
        "reason": "",
        "source": "Movimientos CM",
        "max_date": max_exit,
        "observed_start": observed_start,
        "observed_end": observed_end,
    }

    return (
        out.drop(columns=["_sku_key"], errors="ignore"),
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
# PLAN DE ACCIÓN EJECUTIVO
# ============================================================

def _build_action_plan(
    decision_df: pd.DataFrame,
    movement: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convierte el análisis técnico en acciones operativas.

    Prioridad:
    1) TRASLADAR desde CD si existe movimiento factible.
    2) ESPERAR IMPORTACIÓN si la llegada cubre el riesgo.
    3) COMPRAR si la cobertura sigue insuficiente.
    4) SOBRESTOCK / SIN ROTACIÓN / SALUDABLE.

    Compra sugerida:
        demanda 30d - stock disponible - importación
    """
    if decision_df is None or decision_df.empty:
        return pd.DataFrame()

    out = decision_df.copy()
    out["Código"] = _normalize_key(out["Código"])

    if "Mover sugerido" not in out.columns:
        out["Mover sugerido"] = 0
    if "Destino traslado" not in out.columns:
        out["Destino traslado"] = ""

    if movement is not None and not movement.empty:
        mv = movement.copy()
        mv["Código"] = _normalize_key(mv["Código"])

        mv_summary = (
            mv.groupby("Código", as_index=False)
            .agg(
                **{
                    "Mover sugerido": ("Mover sugerido", "sum"),
                    "Destino traslado": (
                        "Destino",
                        lambda s: ", ".join(
                            sorted({str(v).strip() for v in s if str(v).strip()})
                        ),
                    ),
                }
            )
        )

        out = out.drop(
            columns=["Mover sugerido", "Destino traslado"],
            errors="ignore",
        ).merge(
            mv_summary,
            on="Código",
            how="left",
        )

        out["Mover sugerido"] = pd.to_numeric(
            out["Mover sugerido"],
            errors="coerce",
        ).fillna(0).clip(lower=0)

        out["Destino traslado"] = (
            out["Destino traslado"]
            .fillna("")
            .astype(str)
        )

        transfer_mask = (
            out["Mover sugerido"].gt(0)
            & out["Recomendación"].isin(
                ["🔴 COMPRAR", "🟠 ESPERAR IMPORTACIÓN"]
            )
        )

        # _priority viene como int64 desde _decision_engine.
        # Lo convertimos explícitamente a float para poder usar 1.5
        # y mantener TRASLADAR entre COMPRAR (1) y ESPERAR IMPORTACIÓN (2).
        out["_priority"] = pd.to_numeric(
            out["_priority"],
            errors="coerce",
        ).fillna(99).astype(float)

        out.loc[transfer_mask, "Recomendación"] = "🟡 TRASLADAR"
        out.loc[transfer_mask, "Acción sugerida"] = out.loc[
            transfer_mask
        ].apply(
            lambda row: (
                f"Trasladar {_safe_int(row['Mover sugerido'])} UND "
                f"desde CD → {row['Destino traslado']}"
            ),
            axis=1,
        )
        out.loc[transfer_mask, "_priority"] = 1.5

    demand = pd.to_numeric(
        out.get("Unidades_30d_demanda", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    available = pd.to_numeric(
        out.get("Disponible", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    incoming = pd.to_numeric(
        out.get("Importación_unidades", 0),
        errors="coerce",
    ).fillna(0).clip(lower=0)

    need = (demand - available - incoming).clip(lower=0)

    out["Compra sugerida"] = 0
    buy_mask = out["Recomendación"].eq("🔴 COMPRAR")
    out.loc[buy_mask, "Compra sugerida"] = need[buy_mask].apply(
        lambda value: int(math.ceil(float(value)))
    )

    out["Compra sugerida"] = pd.to_numeric(
        out["Compra sugerida"],
        errors="coerce",
    ).fillna(0).astype(int)

    return out.sort_values(
        ["_priority", "Cobertura días", "Disponible"],
        ascending=[True, True, True],
    ).reset_index(drop=True)


def _action_plan_export(
    action_plan: pd.DataFrame,
) -> bytes:
    if action_plan is None or action_plan.empty:
        return b""

    cols = [
        col
        for col in [
            "Código",
            "Producto",
            "Recomendación",
            "Acción sugerida",
            "Disponible",
            "Unidades_30d_demanda",
            "Cobertura días",
            "Importación_unidades",
            "ETA_más_próxima",
            "Mover sugerido",
            "Destino traslado",
            "Compra sugerida",
            "Cobertura proyectada",
            "Días hasta ETA",
            "Stock antes ETA",
            "Stock después ETA",
            "Cobertura post ETA",
            "Estado importación ETA",
            "Timing importación",
            "Cantidad importación",
            "Fecha estimada quiebre",
            "Compra adicional post ETA",
            "ABC",
        ]
        if col in action_plan.columns
    ]

    export = action_plan[cols].copy()

    if "ETA_más_próxima" in export.columns:
        export["ETA_más_próxima"] = pd.to_datetime(
            export["ETA_más_próxima"],
            errors="coerce",
        ).dt.strftime("%d/%m/%Y")

    return export.to_csv(index=False, sep=";").encode("utf-8-sig")



# ============================================================
# PRIORIDAD EJECUTIVA / INVENTARIO INMOVILIZADO
# ============================================================

def _priority_score(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    coverage = pd.to_numeric(
        out.get("Cobertura días", 0), errors="coerce"
    ).fillna(0.0)

    demand30 = pd.to_numeric(
        out.get("Unidades_30d_demanda", 0), errors="coerce"
    ).fillna(0.0).clip(lower=0)

    available = pd.to_numeric(
        out.get("Disponible", 0), errors="coerce"
    ).fillna(0.0).clip(lower=0)

    incoming = pd.to_numeric(
        out.get("Importación_unidades", 0), errors="coerce"
    ).fillna(0.0).clip(lower=0)

    days_without = pd.to_numeric(
        out.get("Días_sin_salida", pd.Series(index=out.index, dtype="float64")),
        errors="coerce",
    )

    has_history = out.get(
        "Tiene_historial_CM",
        pd.Series(True, index=out.index),
    ).fillna(False).astype(bool)

    score = pd.Series(0.0, index=out.index)

    score += (coverage.lt(7) & demand30.gt(0)).astype(float) * 40
    score += (
        coverage.ge(7) & coverage.lt(15) & demand30.gt(0)
    ).astype(float) * 30
    score += (
        coverage.ge(15) & coverage.lt(30) & demand30.gt(0)
    ).astype(float) * 15

    score += demand30.clip(upper=100) / 100 * 20
    score -= incoming.gt(0).astype(float) * 10

    immobile = (
        has_history
        & days_without.ge(60)
        & available.gt(0)
    )
    score += immobile.astype(float) * 20

    over = (
        has_history
        & coverage.gt(90)
        & available.gt(0)
    )
    score += over.astype(float) * 10

    rec = out.get(
        "Recomendación",
        pd.Series("", index=out.index),
    ).astype(str)

    score += rec.eq("🔴 COMPRAR").astype(float) * 20
    score += rec.eq("🟡 TRASLADAR").astype(float) * 15
    score += rec.eq("🟠 ESPERAR IMPORTACIÓN").astype(float) * 8
    score += rec.eq("🔵 SOBRESTOCK").astype(float) * 10
    score += rec.eq("⚪ SIN ROTACIÓN").astype(float) * 10

    out["Prioridad"] = score.clip(lower=0, upper=100).round().astype(int)

    def priority_label(value: int) -> str:
        if value >= 75:
            return "🔴 Muy alta"
        if value >= 50:
            return "🟠 Alta"
        if value >= 25:
            return "🟡 Media"
        return "🟢 Baja"

    out["Nivel prioridad"] = out["Prioridad"].map(priority_label)
    return out


def _immobilized_inventory(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    out["Disponible"] = pd.to_numeric(
        out.get("Disponible", 0), errors="coerce"
    ).fillna(0).clip(lower=0)

    out["Días_sin_salida"] = pd.to_numeric(
        out.get(
            "Días_sin_salida",
            pd.Series(index=out.index, dtype="float64"),
        ),
        errors="coerce",
    )

    has_history = out.get(
        "Tiene_historial_CM",
        pd.Series(True, index=out.index),
    ).fillna(False).astype(bool)

    s30 = pd.to_numeric(
        out.get("Salidas_30d", 0), errors="coerce"
    ).fillna(0)

    s90 = pd.to_numeric(
        out.get("Salidas_90d", 0), errors="coerce"
    ).fillna(0)

    mask = (
        has_history
        & out["Disponible"].gt(0)
        & (
            out["Días_sin_salida"].ge(60)
            | s90.le(0)
            | (
                s30.le(0)
                & out["Días_sin_salida"].ge(30)
            )
        )
    )

    imm = out.loc[mask].copy()
    if imm.empty:
        return imm

    imm["Sin_salida_todo_periodo"] = (
        imm.get(
            "Última_salida",
            pd.Series(pd.NaT, index=imm.index),
        ).isna()
        & imm.get(
            "Tiene_historial_CM",
            pd.Series(False, index=imm.index),
        ).fillna(False).astype(bool)
    )

    imm["Severidad inmovilizado"] = "🟡 Revisar"
    imm.loc[
        imm["Días_sin_salida"].ge(90),
        "Severidad inmovilizado",
    ] = "🔴 Alto"
    imm.loc[
        imm["Días_sin_salida"].between(60, 89),
        "Severidad inmovilizado",
    ] = "🟠 Medio"

    return imm.sort_values(
        ["Días_sin_salida", "Disponible"],
        ascending=[False, False],
    )


# ============================================================
# PROYECCIÓN DE STOCK A ETA
# ============================================================

def _eta_projection(
    df: pd.DataFrame,
    reference_date=None,
) -> pd.DataFrame:
    """
    Proyecta el stock hasta la ETA usando la salida física media
    de los últimos 30 días.

    Stock antes ETA =
        max(stock actual - salida diaria * días hasta ETA, 0)

    Stock después ETA =
        stock antes ETA + unidades de importación

    Cobertura post ETA =
        stock después ETA / salida diaria

    La proyección es operativa, no una predicción de ventas.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if reference_date is None:
        reference_date = pd.Timestamp.now(
            tz=CHILE_TZ
        ).tz_localize(None).normalize()
    else:
        reference_date = pd.Timestamp(reference_date)
        if reference_date.tzinfo is not None:
            reference_date = (
                reference_date
                .tz_convert(CHILE_TZ)
                .tz_localize(None)
            )
        reference_date = reference_date.normalize()

    stock = pd.to_numeric(
        out.get("Disponible", 0),
        errors="coerce",
    ).fillna(0.0).clip(lower=0)

    demand30 = pd.to_numeric(
        out.get("Unidades_30d_demanda", 0),
        errors="coerce",
    ).fillna(0.0).clip(lower=0)

    incoming = pd.to_numeric(
        out.get("Importación_unidades", 0),
        errors="coerce",
    ).fillna(0.0).clip(lower=0)

    eta = pd.to_datetime(
        out.get(
            "ETA_más_próxima",
            pd.Series(pd.NaT, index=out.index),
        ),
        errors="coerce",
    )

    daily = demand30 / 30.0

    days_to_eta = (
        eta.dt.normalize() - reference_date
    ).dt.days

    out["Días hasta ETA"] = days_to_eta

    future_eta = eta.notna() & days_to_eta.ge(0)
    expired_eta = eta.notna() & days_to_eta.lt(0)
    has_import = incoming.gt(0)

    consumption_to_eta = pd.Series(
        0.0,
        index=out.index,
        dtype="float64",
    )

    consumption_to_eta.loc[future_eta] = (
        daily.loc[future_eta]
        * days_to_eta.loc[future_eta]
    )

    out["Consumo estimado hasta ETA"] = (
        consumption_to_eta.clip(lower=0)
    )

    out["Stock antes ETA"] = (
        stock - out["Consumo estimado hasta ETA"]
    ).clip(lower=0)

    out["Stock después ETA"] = out["Stock antes ETA"]

    valid_arrival = has_import & future_eta

    out.loc[
        valid_arrival,
        "Stock después ETA",
    ] = (
        out.loc[valid_arrival, "Stock antes ETA"]
        + incoming.loc[valid_arrival]
    )

    out["Cobertura post ETA"] = pd.Series(
        float("nan"),
        index=out.index,
        dtype="float64",
    )

    moving = daily.gt(0)

    out.loc[
        moving & valid_arrival,
        "Cobertura post ETA",
    ] = (
        out.loc[moving & valid_arrival, "Stock después ETA"]
        / daily.loc[moving & valid_arrival]
    )

    out.loc[
        (~moving) & valid_arrival,
        "Cobertura post ETA",
    ] = 9999.0

    current_coverage = pd.to_numeric(
        out.get("Cobertura días", 0),
        errors="coerce",
    )

    # ¿Se agotaría el stock antes de la llegada?
    out["Quiebre antes ETA"] = False

    out.loc[
        valid_arrival & moving,
        "Quiebre antes ETA",
    ] = (
        consumption_to_eta.loc[valid_arrival & moving]
        > stock.loc[valid_arrival & moving]
    )

    status = pd.Series(
        "⚪ SIN IMPORTACIÓN",
        index=out.index,
        dtype="object",
    )

    status.loc[
        has_import & eta.isna(),
    ] = "⚫ ETA NO DISPONIBLE"

    status.loc[
        has_import & expired_eta,
    ] = "🔴 ETA VENCIDA"

    # Llegada futura, pero existe riesgo de quiebre antes de recibirla.
    status.loc[
        valid_arrival
        & out["Quiebre antes ETA"],
    ] = "🟠 LLEGADA TARDÍA"

    # Si no quiebra antes de ETA, evaluar cobertura posterior.
    post_cov = pd.to_numeric(
        out["Cobertura post ETA"],
        errors="coerce",
    )

    enough = (
        valid_arrival
        & ~out["Quiebre antes ETA"]
        & (
            post_cov.ge(30)
            | (~moving)
        )
    )

    insufficient = (
        valid_arrival
        & ~out["Quiebre antes ETA"]
        & moving
        & post_cov.lt(30)
    )

    status.loc[enough] = "🟢 CUBIERTO"
    status.loc[insufficient] = "🟡 LLEGADA INSUFICIENTE"

    out["Estado importación ETA"] = status

    # --------------------------------------------------------
    # V13.1 · Separar oportunidad (timing) y suficiencia
    # --------------------------------------------------------
    timing = pd.Series(
        "⚪ SIN IMPORTACIÓN",
        index=out.index,
        dtype="object",
    )

    timing.loc[
        has_import & eta.isna()
    ] = "⚫ ETA NO DISPONIBLE"

    timing.loc[
        has_import & expired_eta
    ] = "🔴 ETA VENCIDA"

    timing.loc[
        valid_arrival & ~out["Quiebre antes ETA"]
    ] = "🟢 A TIEMPO"

    timing.loc[
        valid_arrival & out["Quiebre antes ETA"]
    ] = "🟠 QUIEBRE ANTES ETA"

    out["Timing importación"] = timing

    quantity = pd.Series(
        "⚪ SIN IMPORTACIÓN",
        index=out.index,
        dtype="object",
    )

    quantity.loc[
        has_import & eta.isna()
    ] = "⚫ NO EVALUABLE"

    quantity.loc[
        has_import & expired_eta
    ] = "⚫ NO EVALUABLE"

    quantity.loc[
        valid_arrival & (~moving)
    ] = "🟢 SUFICIENTE"

    quantity.loc[
        valid_arrival & moving & post_cov.ge(30)
    ] = "🟢 SUFICIENTE"

    quantity.loc[
        valid_arrival & moving & post_cov.lt(30)
    ] = "🟡 INSUFICIENTE"

    out["Cantidad importación"] = quantity

    # Fecha estimada de quiebre basada en velocidad física 30d.
    out["Fecha estimada quiebre"] = pd.NaT

    days_until_stockout = pd.Series(
        float("nan"),
        index=out.index,
        dtype="float64",
    )

    stockout_mask = moving & stock.gt(0)

    days_until_stockout.loc[stockout_mask] = (
        stock.loc[stockout_mask]
        / daily.loc[stockout_mask]
    )

    stockout_dates = pd.Series(
        pd.NaT,
        index=out.index,
        dtype="datetime64[ns]",
    )

    if stockout_mask.any():
        stockout_dates.loc[stockout_mask] = (
            reference_date
            + pd.to_timedelta(
                days_until_stockout.loc[stockout_mask],
                unit="D",
            )
        ).dt.normalize()

    # Stock cero con movimiento: quiebre actual.
    zero_stock_mask = moving & stock.le(0)
    stockout_dates.loc[zero_stock_mask] = reference_date

    out["Fecha estimada quiebre"] = stockout_dates

    out["Quiebre visible"] = (
        out["Fecha estimada quiebre"]
        .dt.strftime("%d/%m/%Y")
    )

    out.loc[
        out["Fecha estimada quiebre"].isna(),
        "Quiebre visible",
    ] = "—"

    out["Resultado ETA"] = (
        out["Timing importación"].astype(str)
        + " · "
        + out["Cantidad importación"].astype(str)
    )

    # Compra adicional para llegar a 30 días de cobertura DESPUÉS de ETA.
    target_units = daily * 30.0

    out["Compra adicional post ETA"] = 0

    need = (
        target_units - out["Stock después ETA"]
    ).clip(lower=0)

    need_mask = (
        valid_arrival
        & moving
        & post_cov.lt(30)
    )

    out.loc[
        need_mask,
        "Compra adicional post ETA",
    ] = (
        need.loc[need_mask]
        .apply(lambda value: int(math.ceil(float(value))))
    )

    out["Compra adicional post ETA"] = pd.to_numeric(
        out["Compra adicional post ETA"],
        errors="coerce",
    ).fillna(0).astype(int)

    # Columnas limpias para presentación.
    out["ETA visible"] = eta.dt.strftime("%d/%m/%Y")
    out.loc[eta.isna(), "ETA visible"] = "—"

    out["Días ETA visible"] = ""
    out.loc[
        future_eta,
        "Días ETA visible",
    ] = (
        days_to_eta.loc[future_eta]
        .round()
        .astype(int)
        .astype(str)
        + " días"
    )
    out.loc[
        expired_eta,
        "Días ETA visible",
    ] = "Vencida"

    out["Cobertura post ETA visible"] = "—"

    finite_post = (
        post_cov.notna()
        & post_cov.lt(9999)
    )

    out.loc[
        finite_post,
        "Cobertura post ETA visible",
    ] = (
        post_cov.loc[finite_post]
        .round(1)
        .astype(str)
        + " días"
    )

    out.loc[
        valid_arrival & (~moving),
        "Cobertura post ETA visible",
    ] = "Sin consumo reciente"

    out["Stock antes ETA"] = (
        pd.to_numeric(
            out["Stock antes ETA"],
            errors="coerce",
        )
        .fillna(0)
        .round()
        .astype(int)
    )

    out["Stock después ETA"] = (
        pd.to_numeric(
            out["Stock después ETA"],
            errors="coerce",
        )
        .fillna(0)
        .round()
        .astype(int)
    )

    out["Consumo estimado hasta ETA"] = (
        pd.to_numeric(
            out["Consumo estimado hasta ETA"],
            errors="coerce",
        )
        .fillna(0)
        .round(1)
    )

    return out

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
    st.markdown(
        """
        <style>
        .ms-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:14px}
        .ms-eyebrow{color:#FFC400!important;font-size:10px!important;font-weight:850!important;letter-spacing:.8px!important}
        .ms-title{color:#F7F8FA!important;font-size:30px!important;font-weight:850!important}
        .ms-subtitle,.ms-head-badge{color:#9FB0C0!important}
        .ms-head-badge{background:#151F28!important;border:1px solid #34414D!important;border-radius:999px!important;padding:8px 12px!important}
        .ms-head-badge i{display:inline-block;width:8px;height:8px;border-radius:50%;background:#22C55E;margin-right:7px}

        .ms-source,.ms-kpi,.ms-import-mini,.ms-movement-summary>div,.ms-info-box{
            background:linear-gradient(145deg,#18242E,#121B23)!important;
            border:1px solid #34414D!important;
            box-shadow:none!important;
        }
        .ms-source-item strong,.ms-source-update strong,.ms-kpi-value,.ms-import-mini strong,
        .ms-movement-summary strong,.ms-section-head strong,.ms-card-head strong{
            color:#F7F8FA!important;
        }
        .ms-source-item small,.ms-source-update small,.ms-kpi-label,.ms-kpi-helper,
        .ms-import-mini span,.ms-import-mini small,.ms-movement-summary span,
        .ms-movement-summary small,.ms-section-head span,.ms-card-head span{
            color:#9FB0C0!important;
        }

        .ms-source-item,.ms-source-update,.ms-risk-strip>div{
            background:linear-gradient(145deg,#18242E,#121B23)!important;
            border:1px solid #34414D!important;
            box-shadow:none!important;
            color:#F7F8FA!important;
        }
        .ms-risk-strip{
            display:grid!important;
            grid-template-columns:repeat(2,minmax(0,1fr))!important;
            gap:11px!important;
            margin:10px 0 14px!important;
        }
        .ms-risk-strip>div{
            border-radius:12px!important;
            padding:14px!important;
        }
        .ms-risk-strip span,.ms-risk-strip small{
            color:#9FB0C0!important;
        }
        .ms-risk-strip strong{
            color:#F7F8FA!important;
            display:block!important;
            font-size:24px!important;
            margin:6px 0!important;
        }
        .ms-risk-strip .danger{
            border-color:#713434!important;
        }

        .ms-priority-grid{
            display:grid!important;
            grid-template-columns:repeat(5,minmax(0,1fr))!important;
            gap:11px!important;
            margin:10px 0 14px!important;
        }
        .ms-priority-card{
            background:linear-gradient(145deg,#18242E,#121B23)!important;
            border:1px solid #34414D!important;
            border-radius:14px!important;
            padding:14px 15px!important;
            min-height:104px!important;
        }
        .ms-priority-card span{
            color:#9FB0C0!important;
            font-size:11px!important;
            font-weight:800!important;
            letter-spacing:.08em!important;
        }
        .ms-priority-card strong{
            display:block!important;
            color:#F7F8FA!important;
            font-size:27px!important;
            margin:5px 0 2px!important;
        }
        .ms-priority-card small{
            color:#9FB0C0!important;
            font-size:12px!important;
        }
        @media(max-width:1100px){
            .ms-priority-grid{
                grid-template-columns:repeat(2,minmax(0,1fr))!important;
            }
        }

        .ms-eta-grid{
            display:grid!important;
            grid-template-columns:repeat(4,minmax(0,1fr))!important;
            gap:11px!important;
            margin:10px 0 14px!important;
        }
        .ms-eta-card{
            background:linear-gradient(145deg,#18242E,#121B23)!important;
            border:1px solid #34414D!important;
            border-radius:14px!important;
            padding:14px 15px!important;
            min-height:105px!important;
        }
        .ms-eta-card span{
            color:#9FB0C0!important;
            font-size:11px!important;
            font-weight:800!important;
            letter-spacing:.07em!important;
        }
        .ms-eta-card strong{
            display:block!important;
            color:#F7F8FA!important;
            font-size:27px!important;
            margin:5px 0 2px!important;
        }
        .ms-eta-card small{
            color:#9FB0C0!important;
            font-size:12px!important;
        }
        .ms-eta-card.covered{
            border-color:#24583B!important;
        }
        .ms-eta-card.insufficient{
            border-color:#6B5A27!important;
        }
        .ms-eta-card.late{
            border-color:#714B2E!important;
        }
        .ms-eta-card.expired{
            border-color:#713434!important;
        }
        @media(max-width:1000px){
            .ms-eta-grid{
                grid-template-columns:repeat(2,minmax(0,1fr))!important;
            }
        }

        .ms-exec-grid{
            display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
            gap:11px;margin:10px 0 14px;
        }
        .ms-exec-card{
            background:linear-gradient(145deg,#1A2530,#141E27);
            border:1px solid #34414D;border-radius:12px;padding:14px;
        }
        .ms-exec-card span{
            display:block;color:#9FB0C0;font-size:9px;font-weight:800;
            text-transform:uppercase;letter-spacing:.45px;
        }
        .ms-exec-card strong{
            display:block;color:#FFF;font-size:24px;font-weight:850;
            margin-top:7px;line-height:1;
        }
        .ms-exec-card small{display:block;color:#8FA2B3;margin-top:7px;font-size:9px}
        .ms-exec-card.buy{border-color:#713434}
        .ms-exec-card.transfer{border-color:#7A640A}
        .ms-exec-card.wait{border-color:#815924}
        .ms-exec-card.over{border-color:#55427A}
        .ms-exec-card.saved{border-color:#28603E}

        .ms-action-strip{
            display:flex;justify-content:space-between;align-items:center;gap:15px;
            background:#111B24;border:1px solid #34414D;border-radius:11px;
            padding:12px 14px;margin:8px 0 12px;
        }
        .ms-action-strip strong{color:#F7F8FA!important}
        .ms-action-strip span{color:#9FB0C0!important;font-size:10px}

        div[data-testid="stVerticalBlockBorderWrapper"]{
            background:#111B24!important;border-color:#34414D!important;box-shadow:none!important;
        }
        [data-testid="stDataFrame"]{
            background:#111B24!important;border:1px solid #34414D!important;border-radius:10px!important;
        }
        [data-testid="stVegaLiteChart"],[data-testid="stVegaLiteChart"]>div{
            background:#111B24!important;
        }
        [data-testid="stTextInput"] input,
        [data-testid="stMultiSelect"]>div>div{
            background:#141E27!important;color:#F7F8FA!important;border-color:#3A4955!important;
        }
        .main .stDownloadButton>button{
            background:#FFC400!important;color:#111820!important;border-color:#FFC400!important;font-weight:800!important;
        }
        @media(max-width:1100px){.ms-exec-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media(max-width:700px){.ms-exec-grid{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )
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

    # Histórico físico Casa Matriz.
    # El CSV consolidado evita procesar los PDF en cada ejecución.
    try:
        cm_movements, cm_meta = load_cm_movements()
        cm_rotation = (
            build_cm_rotation_metrics(cm_movements)
            if cm_meta.get("enabled")
            else pd.DataFrame()
        )

        if not cm_rotation.empty and not cm_movements.empty:
            cm_rotation["Fecha_inicio_histórico"] = pd.to_datetime(
                cm_movements["Fecha"],
                errors="coerce",
            ).min()
            cm_rotation["Fecha_fin_histórico"] = pd.to_datetime(
                cm_movements["Fecha"],
                errors="coerce",
            ).max()
    except Exception as exc:
        cm_movements = pd.DataFrame()
        cm_rotation = pd.DataFrame()
        cm_meta = {
            "enabled": False,
            "reason": str(exc),
            "rows": 0,
            "min_date": None,
            "max_date": None,
        }

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
                    <small>MOVIMIENTOS CM</small>
                    <strong>
                        {
                            f"{_fmt_int(cm_meta.get('rows', 0))} movimientos"
                            if cm_meta.get("enabled")
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
    # ROTACIÓN / COBERTURA
    # --------------------------------------------------------
    # Fuente primaria: movimientos físicos Casa Matriz.
    # ERP Ventas queda como respaldo cuando no existe histórico CM.
    if cm_meta.get("enabled") and not cm_rotation.empty:
        intel, sales_meta = _movement_intelligence(
            filtered,
            cm_rotation,
        )
    else:
        intel, sales_meta = _sales_intelligence(
            filtered,
            sales_df,
        )
        sales_meta["source"] = "ERP Ventas"

    # --------------------------------------------------------
    # IMPORT INTELLIGENCE
    # --------------------------------------------------------
    imports, intel_imports = (
        _prepare_imports(
            imports_df,
            intel,
        )
    )

    # Movimientos internos se calculan antes del motor de decisión para
    # priorizar redistribución desde CD antes de sugerir una compra.
    movement = _transfer_recommendations(
        fr_clean,
        intel_imports,
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
    decision_preview = _build_action_plan(
        _decision_engine(
            intel_imports
        ),
        movement,
    )

    decision_preview = _priority_score(
        decision_preview
    )

    decision_preview = _eta_projection(
        decision_preview
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

    buy_count = int(
        decision_preview["Recomendación"].eq("🔴 COMPRAR").sum()
    ) if not decision_preview.empty else 0

    transfer_count = int(
        decision_preview["Recomendación"].eq("🟡 TRASLADAR").sum()
    ) if not decision_preview.empty else 0

    wait_count = int(
        decision_preview["Recomendación"].eq("🟠 ESPERAR IMPORTACIÓN").sum()
    ) if not decision_preview.empty else 0

    purchase_units = _safe_int(
        decision_preview.get(
            "Compra sugerida",
            pd.Series(dtype="float64"),
        ).sum()
    ) if not decision_preview.empty else 0

    movement_units_exec = (
        _safe_int(
            pd.to_numeric(
                decision_preview.loc[
                    decision_preview["Recomendación"].eq("🟡 TRASLADAR"),
                    "Mover sugerido",
                ],
                errors="coerce",
            ).fillna(0).sum()
        )
        if (
            not decision_preview.empty
            and "Mover sugerido" in decision_preview.columns
        )
        else 0
    )

    saved_by_import = 0
    still_risk_after_import = 0

    if not decision_preview.empty:
        current_risk = (
            (decision_preview["Cobertura días"] < 15)
            & (decision_preview["Unidades_30d_demanda"] > 0)
        )
        projected_risk = (
            (decision_preview["Cobertura proyectada"] < 15)
            & (decision_preview["Unidades_30d_demanda"] > 0)
        )
        has_import = decision_preview["Importación_unidades"] > 0

        saved_by_import = int(
            (current_risk & has_import & ~projected_risk).sum()
        )
        still_risk_after_import = int(
            (current_risk & projected_risk).sum()
        )

    # ========================================================
    # PRIORIDADES DE HOY
    # ========================================================
    if not decision_preview.empty:
        critical_count = int(
            decision_preview["Nivel prioridad"].eq("🔴 Muy alta").sum()
        )
        transfer_exec = int(
            decision_preview["Recomendación"].eq("🟡 TRASLADAR").sum()
        )
        import_exec = int(
            decision_preview["Recomendación"].eq("🟠 ESPERAR IMPORTACIÓN").sum()
        )
        over_exec = int(
            decision_preview["Recomendación"].eq("🔵 SOBRESTOCK").sum()
        )

        immobile_df = _immobilized_inventory(decision_preview)
        immobile_count = (
            int(immobile_df["Código"].nunique())
            if not immobile_df.empty
            else 0
        )

        no_history_count = int(
            (
                ~decision_preview.get(
                    "Tiene_historial_CM",
                    pd.Series(True, index=decision_preview.index),
                ).fillna(False).astype(bool)
            ).sum()
        )

        render_html(
            f"""
            <div class="ms-section-head">
                <div>
                    <strong>Prioridades de hoy</strong>
                    <span>
                        Orden ejecutivo según cobertura, movimiento, importaciones y acción recomendada
                    </span>
                </div>
            </div>

            <div class="ms-priority-grid">
                <div class="ms-priority-card">
                    <span>CRÍTICOS</span>
                    <strong>{_fmt_int(critical_count)}</strong>
                    <small>prioridad muy alta</small>
                </div>
                <div class="ms-priority-card">
                    <span>TRASLADAR</span>
                    <strong>{_fmt_int(transfer_exec)}</strong>
                    <small>SKU con acción desde CD</small>
                </div>
                <div class="ms-priority-card">
                    <span>CUBIERTOS POR IMPORTACIÓN</span>
                    <strong>{_fmt_int(import_exec)}</strong>
                    <small>esperar llegada</small>
                </div>
                <div class="ms-priority-card">
                    <span>SOBRESTOCK</span>
                    <strong>{_fmt_int(over_exec)}</strong>
                    <small>revisar exceso</small>
                </div>
                <div class="ms-priority-card">
                    <span>SIN MOVIMIENTO</span>
                    <strong>{_fmt_int(immobile_count)}</strong>
                    <small>stock inmovilizado</small>
                </div>
            </div>

            <div class="ms-info-box" style="margin-top:10px">
                <strong>Calidad del histórico</strong>
                <span>
                    {_fmt_int(no_history_count)} SKU del stock actual no aparecen en el histórico CM Jun-Jul-Ago.
                    No se clasifican como inmovilizados ni se les asignan 9.999 días de cobertura.
                </span>
            </div>
            """
        )

        priority_cols = [
            col for col in [
                "Código",
                "Producto",
                "Disponible",
                "Salidas_30d",
                "Salidas_90d",
                "Cobertura días",
                "Días_sin_salida",
                "Estado_rotación",
                "Importación_unidades",
                "ETA_más_próxima",
                "Recomendación",
                "Acción sugerida",
                "Prioridad",
                "Nivel prioridad",
            ]
            if col in decision_preview.columns
        ]

        top_priority = decision_preview[priority_cols].copy()

        top_priority["_coverage_sort"] = pd.to_numeric(
            top_priority.get("Cobertura días"),
            errors="coerce",
        ).fillna(float("inf"))

        top_priority = (
            top_priority
            .sort_values(
                ["Prioridad", "_coverage_sort"],
                ascending=[False, True],
            )
            .drop(columns=["_coverage_sort"], errors="ignore")
            .head(20)
        )

        with st.container(border=True):
            render_html(
                """
                <div class="ms-card-head">
                    <div>
                        <strong>Top 20 prioridades</strong>
                        <span>SKU que requieren atención primero</span>
                    </div>
                </div>
                """
            )

            st.dataframe(
                top_priority,
                hide_index=True,
                use_container_width=True,
                height=420,
                column_config={
                    "Código": st.column_config.TextColumn("SKU", width="small"),
                    "Producto": st.column_config.TextColumn("Producto", width="large"),
                    "Disponible": st.column_config.NumberColumn("Stock", format="%d"),
                    "Salidas_30d": st.column_config.NumberColumn("Salidas 30d", format="%d"),
                    "Salidas_90d": st.column_config.NumberColumn("Salidas 90d", format="%d"),
                    "Cobertura días": st.column_config.NumberColumn("Cobertura", format="%.1f días"),
                    "Días_sin_salida": st.column_config.NumberColumn("Días sin salida", format="%d"),
                    "Importación_unidades": st.column_config.NumberColumn("Importación", format="%d"),
                    "ETA_más_próxima": st.column_config.DateColumn("ETA", format="DD/MM/YYYY"),
                    "Recomendación": st.column_config.TextColumn("Acción", width="medium"),
                    "Acción sugerida": st.column_config.TextColumn("Detalle", width="large"),
                    "Prioridad": st.column_config.ProgressColumn(
                        "Prioridad",
                        min_value=0,
                        max_value=100,
                        format="%d",
                    ),
                    "Nivel prioridad": st.column_config.TextColumn("Nivel", width="small"),
                },
            )

    render_html(
        f"""
        <div class="ms-section-head">
            <div>
                <strong>Plan de acción</strong>
                <span>
                    Qué hacer con el stock: comprar, trasladar, esperar o corregir exceso
                </span>
            </div>
        </div>

        <div class="ms-exec-grid">
            <div class="ms-exec-card buy">
                <span>COMPRAR</span>
                <strong>{_fmt_int(buy_count)}</strong>
                <small>{_fmt_int(purchase_units)} UND sugeridas</small>
            </div>
            <div class="ms-exec-card transfer">
                <span>TRASLADAR DESDE CD</span>
                <strong>{_fmt_int(transfer_count)}</strong>
                <small>{_fmt_int(movement_units_exec)} UND redistribuibles</small>
            </div>
            <div class="ms-exec-card wait">
                <span>ESPERAR IMPORTACIÓN</span>
                <strong>{_fmt_int(wait_count)}</strong>
                <small>{_fmt_int(saved_by_import)} SKU cubiertos por llegada</small>
            </div>
            <div class="ms-exec-card over">
                <span>SOBRESTOCK</span>
                <strong>{_fmt_int(overstock_count)}</strong>
                <small>más de 90 días de cobertura</small>
            </div>
            <div class="ms-exec-card saved">
                <span>RIESGO RESIDUAL</span>
                <strong>{_fmt_int(still_risk_after_import)}</strong>
                <small>siguen bajo 15 días aun proyectando llegada</small>
            </div>
        </div>
        """
    )

    export_bytes = _action_plan_export(
        decision_preview
    )

    action_left, action_right = st.columns(
        [3.2, 1.0],
        gap="small",
    )

    with action_left:
        render_html(
            f"""
            <div class="ms-action-strip">
                <div>
                    <strong>Stock General muestra qué hay.</strong>
                    <span>
                        Métricas Stock recomienda qué hacer con cada SKU.
                    </span>
                </div>
                <div>
                    <strong>{_fmt_int(buy_count + transfer_count + wait_count)}</strong>
                    <span>SKU con acción prioritaria</span>
                </div>
            </div>
            """
        )

    with action_right:
        st.download_button(
            "Descargar plan de acción",
            data=export_bytes,
            file_name="plan_accion_stock.csv",
            mime="text/csv",
            use_container_width=True,
            icon=":material/download:",
            key="ms_action_plan_download_v10",
            disabled=not bool(export_bytes),
        )


    # ========================================================
    # SALUD DEL INVENTARIO / MOTOR DE DECISIÓN
    # ========================================================
    if not decision_preview.empty:
        health_order = [
            "🔴 COMPRAR",
            "🟡 TRASLADAR",
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
                                labelColor="#AEBBC6",
                                domain=False,
                                ticks=False,
                                labelLimit=180,
                            ),
                        ),
                        x=alt.X(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9FB0C0",
                                domain=False,
                                gridColor="#34414D",
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
                        "Mover sugerido",
                        "Destino traslado",
                        "Compra sugerida",
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
                            "Mover sugerido": st.column_config.NumberColumn(
                                "Trasladar",
                                format="%d",
                            ),
                            "Destino traslado": st.column_config.TextColumn(
                                "Destino",
                                width="medium",
                            ),
                            "Compra sugerida": st.column_config.NumberColumn(
                                "Comprar",
                                format="%d",
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
                                    labelColor="#AEBBC6",
                                    domain=False,
                                    ticks=False,
                                ),
                            ),
                            x=alt.X(
                                "Unidades:Q",
                                title=None,
                                axis=alt.Axis(
                                    labelColor="#9FB0C0",
                                    domain=False,
                                    gridColor="#34414D",
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
                                labelColor="#AEBBC6",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "Disponible:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9FB0C0",
                                domain=False,
                                gridColor="#34414D",
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
                                labelColor="#AEBBC6",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9FB0C0",
                                domain=False,
                                gridColor="#34414D",
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
    # ROTACIÓN + COBERTURA
    # ========================================================
    intelligence_source = sales_meta.get("source", "ERP Ventas")

    render_html(
        f"""
        <div class="ms-section-head">
            <div>
                <strong>Rotación y cobertura</strong>
                <span>
                    {
                        "Salidas físicas Casa Matriz · histórico Jun-Jul-Ago"
                        if intelligence_source == "Movimientos CM"
                        else "Inteligencia construida con ERP Ventas"
                    }
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
            with st.container(border=True):
                render_html(
                    f"""
                    <div class="ms-card-head">
                        <div>
                            <strong>Cobertura estimada</strong>
                            <span>
                                {
                                    "Días de stock según salidas físicas últimos 30 días"
                                    if intelligence_source == "Movimientos CM"
                                    else "Días de stock según venta últimos 30 días"
                                }
                            </span>
                        </div>
                    </div>
                    """
                )

                coverage = (
                    intel.groupby(
                        "Rango cobertura",
                        as_index=False,
                    )
                    .agg(SKU=("Código", "nunique"))
                )

                order = [
                    "< 15 días",
                    "15-29 días",
                    "30-90 días",
                    "> 90 días",
                    (
                        "Sin salida 30d"
                        if intelligence_source == "Movimientos CM"
                        else "Sin venta 30d"
                    ),
                    "Sin historial",
                ]

                chart = (
                    alt.Chart(coverage)
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
                                labelColor="#AEBBC6",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9FB0C0",
                                domain=False,
                                gridColor="#34414D",
                            ),
                        ),
                        tooltip=[
                            "Rango cobertura:N",
                            alt.Tooltip("SKU:Q", format=","),
                        ],
                    )
                    .properties(height=270)
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

        with r2:
            with st.container(border=True):
                render_html(
                    f"""
                    <div class="ms-card-head">
                        <div>
                            <strong>Clasificación ABC</strong>
                            <span>
                                {
                                    "Concentración según salidas físicas últimos 90 días"
                                    if intelligence_source == "Movimientos CM"
                                    else "Concentración según venta últimos 90 días"
                                }
                            </span>
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
                        SKU=("Código", "nunique"),
                        Movimiento_90d=("Venta_90d", "sum"),
                    )
                )

                chart = (
                    alt.Chart(abc)
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
                                labelColor="#AEBBC6",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        y=alt.Y(
                            "SKU:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9FB0C0",
                                domain=False,
                                gridColor="#34414D",
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
                                "Movimiento_90d:Q",
                                title=(
                                    "Salidas 90d"
                                    if intelligence_source == "Movimientos CM"
                                    else "Venta 90d"
                                ),
                                format=",.0f",
                            ),
                        ],
                    )
                    .properties(height=270)
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

        if intelligence_source == "Movimientos CM":
            movement_cols = [
                col
                for col in [
                    "Código",
                    "Producto",
                    "Disponible",
                    "Salidas_30d",
                    "Salidas_60d",
                    "Salidas_90d",
                    "Frecuencia_30d",
                    "Última_salida",
                    "Días_sin_salida",
                    "Tendencia_movimiento",
                    "Estado_rotación",
                    "Cobertura días",
                    "ABC",
                ]
                if col in intel.columns
            ]

            movement_detail = intel[movement_cols].copy()

            movement_detail = movement_detail.sort_values(
                [
                    "Salidas_30d",
                    "Salidas_90d",
                ],
                ascending=[False, False],
            ).head(100)

            render_html(
                """
                <div class="ms-card-head" style="margin-top:12px">
                    <div>
                        <strong>Comportamiento físico por SKU</strong>
                        <span>
                            Salidas de inventario; no se asumen como ventas comerciales
                        </span>
                    </div>
                </div>
                """
            )

            st.dataframe(
                movement_detail,
                hide_index=True,
                use_container_width=True,
                height=430,
                column_config={
                    "Código": st.column_config.TextColumn("SKU", width="small"),
                    "Producto": st.column_config.TextColumn("Producto", width="large"),
                    "Disponible": st.column_config.NumberColumn("Stock", format="%d"),
                    "Salidas_30d": st.column_config.NumberColumn("Salidas 30d", format="%d"),
                    "Salidas_60d": st.column_config.NumberColumn("Salidas 60d", format="%d"),
                    "Salidas_90d": st.column_config.NumberColumn("Salidas 90d", format="%d"),
                    "Frecuencia_30d": st.column_config.NumberColumn("Días con salida 30d", format="%d"),
                    "Última salida visible": st.column_config.TextColumn("Última salida", width="medium"),
                    "Días sin salida visible": st.column_config.TextColumn("Días sin salida", width="medium"),
                    "Tendencia_movimiento": st.column_config.TextColumn("Tendencia", width="medium"),
                    "Estado_rotación": st.column_config.TextColumn("Rotación", width="medium"),
                    "Cobertura visible": st.column_config.TextColumn("Cobertura", width="medium"),
                    "ABC": st.column_config.TextColumn("ABC", width="small"),
                },
            )

            render_html(
                f"""
                <div class="ms-info-box">
                    <strong>Ventana histórica disponible</strong>
                    <span>
                        {escape(str(cm_meta.get("min_date", "")))[:10]}
                        →
                        {escape(str(cm_meta.get("max_date", "")))[:10]}
                        · {_fmt_int(cm_meta.get("rows", 0))} movimientos físicos procesados.
                    </span>
                </div>
                """
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
    # PROYECCIÓN DE IMPORTACIONES A ETA
    # ========================================================
    render_html(
        """
        <div class="ms-section-head">
            <div>
                <strong>Proyección de importaciones por ETA</strong>
                <span>
                    Evalúa por separado oportunidad y cantidad · incluye fecha estimada de quiebre
                    según salidas físicas de los últimos 30 días
                </span>
            </div>
        </div>
        """
    )

    if not decision_preview.empty:
        eta_status = decision_preview[
            "Estado importación ETA"
        ].astype(str)

        timing_status = decision_preview[
            "Timing importación"
        ].astype(str)

        quantity_status = decision_preview[
            "Cantidad importación"
        ].astype(str)

        eta_on_time = int(
            timing_status.eq("🟢 A TIEMPO").sum()
        )
        eta_stockout = int(
            timing_status.eq("🟠 QUIEBRE ANTES ETA").sum()
        )
        eta_expired = int(
            timing_status.eq("🔴 ETA VENCIDA").sum()
        )
        eta_no_date = int(
            timing_status.eq("⚫ ETA NO DISPONIBLE").sum()
        )

        qty_enough = int(
            quantity_status.eq("🟢 SUFICIENTE").sum()
        )
        qty_insufficient = int(
            quantity_status.eq("🟡 INSUFICIENTE").sum()
        )

        both_risk = int(
            (
                timing_status.eq("🟠 QUIEBRE ANTES ETA")
                & quantity_status.eq("🟡 INSUFICIENTE")
            ).sum()
        )

        render_html(
            f"""
            <div class="ms-eta-grid">
                <div class="ms-eta-card covered">
                    <span>A TIEMPO</span>
                    <strong>{_fmt_int(eta_on_time)}</strong>
                    <small>sin quiebre antes de la ETA</small>
                </div>

                <div class="ms-eta-card late">
                    <span>QUIEBRE ANTES ETA</span>
                    <strong>{_fmt_int(eta_stockout)}</strong>
                    <small>stock proyectado se agota antes</small>
                </div>

                <div class="ms-eta-card covered">
                    <span>CANTIDAD SUFICIENTE</span>
                    <strong>{_fmt_int(qty_enough)}</strong>
                    <small>al menos 30 días post llegada</small>
                </div>

                <div class="ms-eta-card insufficient">
                    <span>CANTIDAD INSUFICIENTE</span>
                    <strong>{_fmt_int(qty_insufficient)}</strong>
                    <small>menos de 30 días post llegada</small>
                </div>
            </div>

            <div class="ms-risk-strip">
                <div>
                    <strong>{_fmt_int(both_risk)}</strong>
                    <span>SKU combinan quiebre antes de ETA + cantidad insuficiente</span>
                </div>
                <div class="danger">
                    <strong>{_fmt_int(eta_expired)}</strong>
                    <span>ETA vencidas</span>
                </div>
            </div>
            """
        )

        if eta_no_date > 0:
            render_html(
                f"""
                <div class="ms-info-box">
                    <strong>ETA pendiente</strong>
                    <span>
                        {_fmt_int(eta_no_date)} SKU tienen unidades de importación,
                        pero no cuentan con una ETA válida para proyectar.
                    </span>
                </div>
                """
            )

        eta_mask = ~timing_status.eq(
            "⚪ SIN IMPORTACIÓN"
        )

        eta_table = decision_preview.loc[
            eta_mask
        ].copy()

        if not eta_table.empty:
            timing_priority = {
                "🟠 QUIEBRE ANTES ETA": 1,
                "🔴 ETA VENCIDA": 2,
                "⚫ ETA NO DISPONIBLE": 3,
                "🟢 A TIEMPO": 4,
            }

            quantity_priority = {
                "🟡 INSUFICIENTE": 1,
                "⚫ NO EVALUABLE": 2,
                "🟢 SUFICIENTE": 3,
            }

            eta_table["_eta_priority"] = (
                eta_table["Timing importación"]
                .map(timing_priority)
                .fillna(99)
            )

            eta_table["_qty_priority"] = (
                eta_table["Cantidad importación"]
                .map(quantity_priority)
                .fillna(99)
            )

            eta_table = eta_table.sort_values(
                [
                    "_eta_priority",
                    "_qty_priority",
                    "Cobertura post ETA",
                ],
                ascending=[True, True, True],
                na_position="last",
            )

            eta_cols = [
                col
                for col in [
                    "Código",
                    "Producto",
                    "Disponible",
                    "Salidas_30d",
                    "Importación_unidades",
                    "ETA visible",
                    "Días ETA visible",
                    "Quiebre visible",
                    "Stock antes ETA",
                    "Stock después ETA",
                    "Cobertura post ETA visible",
                    "Timing importación",
                    "Cantidad importación",
                    "Compra adicional post ETA",
                ]
                if col in eta_table.columns
            ]

            with st.container(border=True):
                render_html(
                    """
                    <div class="ms-card-head">
                        <div>
                            <strong>Detalle de cobertura a la llegada</strong>
                            <span>
                                Prioriza llegadas tardías e insuficientes
                            </span>
                        </div>
                    </div>
                    """
                )

                st.dataframe(
                    eta_table[eta_cols].head(150),
                    hide_index=True,
                    use_container_width=True,
                    height=470,
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
                            "Stock actual",
                            format="%d",
                        ),
                        "Salidas_30d": st.column_config.NumberColumn(
                            "Salidas 30d",
                            format="%d",
                        ),
                        "Importación_unidades": st.column_config.NumberColumn(
                            "Importación",
                            format="%d",
                        ),
                        "ETA visible": st.column_config.TextColumn(
                            "ETA",
                            width="small",
                        ),
                        "Días ETA visible": st.column_config.TextColumn(
                            "Hasta ETA",
                            width="small",
                        ),
                        "Quiebre visible": st.column_config.TextColumn(
                            "Quiebre estimado",
                            width="small",
                        ),
                        "Stock antes ETA": st.column_config.NumberColumn(
                            "Stock antes ETA",
                            format="%d",
                        ),
                        "Stock después ETA": st.column_config.NumberColumn(
                            "Stock post ETA",
                            format="%d",
                        ),
                        "Cobertura post ETA visible": st.column_config.TextColumn(
                            "Cobertura post ETA",
                            width="medium",
                        ),
                        "Timing importación": st.column_config.TextColumn(
                            "Timing",
                            width="medium",
                        ),
                        "Cantidad importación": st.column_config.TextColumn(
                            "Cantidad",
                            width="medium",
                        ),
                        "Compra adicional post ETA": st.column_config.NumberColumn(
                            "Compra adicional",
                            format="%d",
                        ),
                    },
                )

            # Solo riesgos de importación para una lectura ejecutiva rápida.
            risk_eta = eta_table[
                eta_table["Timing importación"].isin(
                    [
                        "🟠 QUIEBRE ANTES ETA",
                        "🔴 ETA VENCIDA",
                    ]
                )
                | eta_table["Cantidad importación"].eq(
                    "🟡 INSUFICIENTE"
                )
            ].copy()

            if not risk_eta.empty:
                additional_units = _safe_int(
                    pd.to_numeric(
                        risk_eta[
                            "Compra adicional post ETA"
                        ],
                        errors="coerce",
                    ).fillna(0).sum()
                )

                render_html(
                    f"""
                    <div class="ms-action-strip">
                        <div>
                            <strong>Importaciones que requieren revisión</strong>
                            <span>
                                {_fmt_int(len(risk_eta))} SKU presentan riesgo por fecha
                                o cantidad de llegada.
                            </span>
                        </div>
                        <div>
                            <strong>{_fmt_int(additional_units)}</strong>
                            <span>UND adicionales para objetivo de 30 días</span>
                        </div>
                    </div>
                    """
                )

        else:
            render_html(
                """
                <div class="ms-info-box">
                    <strong>Sin importaciones para proyectar</strong>
                    <span>
                        No hay SKU con unidades de importación en el filtro actual.
                    </span>
                </div>
                """
            )

    # ========================================================
    # INVENTARIO INMOVILIZADO
    # ========================================================
    immobile = _immobilized_inventory(decision_preview)

    observed_start_label = (
        pd.to_datetime(cm_meta.get("min_date"), errors="coerce")
        .strftime("%d/%m/%Y")
        if pd.notna(pd.to_datetime(cm_meta.get("min_date"), errors="coerce"))
        else "—"
    )
    observed_end_label = (
        pd.to_datetime(cm_meta.get("max_date"), errors="coerce")
        .strftime("%d/%m/%Y")
        if pd.notna(pd.to_datetime(cm_meta.get("max_date"), errors="coerce"))
        else "—"
    )

    render_html(
        f"""
        <div class="ms-section-head">
            <div>
                <strong>Inventario inmovilizado</strong>
                <span>
                    Stock con baja o nula salida física reciente · período observado
                    {observed_start_label} → {observed_end_label}
                </span>
            </div>
        </div>
        """
    )

    if not immobile.empty:
        imm_units = _safe_int(
            pd.to_numeric(
                immobile["Disponible"],
                errors="coerce",
            ).fillna(0).sum()
        )

        imm_full_period = int(
            immobile.get(
                "Sin_salida_todo_periodo",
                pd.Series(False, index=immobile.index),
            ).fillna(False).astype(bool).sum()
        )

        no_history_total = int(
            (
                ~decision_preview.get(
                    "Tiene_historial_CM",
                    pd.Series(True, index=decision_preview.index),
                ).fillna(False).astype(bool)
            ).sum()
        )

        a, b, c, d = st.columns(4, gap="small")
        a.metric(
            "SKU inmovilizados",
            _fmt_int(immobile["Código"].nunique()),
        )
        b.metric(
            "Unidades inmovilizadas",
            _fmt_int(imm_units),
        )
        c.metric(
            "Sin salida en período",
            _fmt_int(imm_full_period),
        )
        d.metric(
            "Sin historial CM",
            _fmt_int(no_history_total),
        )

        imm_cols = [
            col for col in [
                "Código",
                "Producto",
                "Disponible",
                "Salidas_30d",
                "Salidas_90d",
                "Última salida visible",
                "Días sin salida visible",
                "Cobertura visible",
                "Tendencia_movimiento",
                "Severidad inmovilizado",
            ]
            if col in immobile.columns
        ]

        render_html(
            """
            <div class="ms-info-box">
                <strong>Criterio</strong>
                <span>
                    Solo se consideran inmovilizados los SKU con evidencia en el histórico CM.
                    Si un SKU existe en el período pero nunca registra salida, se muestra como
                    "Sin salida en período" en lugar de asignarle 9.999 días.
                </span>
            </div>
            """
        )

        st.dataframe(
            immobile[imm_cols].head(100),
            hide_index=True,
            use_container_width=True,
            height=430,
            column_config={
                "Código": st.column_config.TextColumn("SKU", width="small"),
                "Producto": st.column_config.TextColumn("Producto", width="large"),
                "Disponible": st.column_config.NumberColumn("Stock", format="%d"),
                "Salidas_30d": st.column_config.NumberColumn("Salidas 30d", format="%d"),
                "Salidas_90d": st.column_config.NumberColumn("Salidas 90d", format="%d"),
                "Última salida visible": st.column_config.TextColumn("Última salida", width="medium"),
                "Días sin salida visible": st.column_config.TextColumn("Días sin salida", width="medium"),
                "Cobertura visible": st.column_config.TextColumn("Cobertura", width="medium"),
                "Tendencia_movimiento": st.column_config.TextColumn("Tendencia", width="medium"),
                "Severidad inmovilizado": st.column_config.TextColumn("Severidad", width="small"),
            },
        )
    else:
        render_html(
            """
            <div class="ms-info-box">
                <strong>Sin inventario inmovilizado relevante</strong>
                <span>
                    No se detectaron SKU con stock y baja o nula salida según los criterios actuales.
                </span>
            </div>
            """
        )

    # ========================================================
    # MOVIMIENTOS ENTRE BODEGAS · CD ABASTECE DESTINOS
    # ========================================================
    # movement ya fue calculado antes del motor de decisión.

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
                                labelColor="#AEBBC6",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "Unidades:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9FB0C0",
                                domain=False,
                                gridColor="#34414D",
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
