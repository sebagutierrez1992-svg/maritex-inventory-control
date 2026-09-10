from __future__ import annotations

from html import escape
from pathlib import Path
import textwrap
import re
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from analytics.stock_metrics import consolidate_inventory
from ui.components import render_html
from utils.excel import dataframe_to_excel_bytes


# ============================================================
# HELPERS
# ============================================================

CHILE_TZ = ZoneInfo("America/Santiago")


def _safe_int(value) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def _fmt_int(value) -> str:
    return f"{_safe_int(value):,}".replace(",", ".")


def _friendly_datetime(value) -> str:
    if value is None:
        return "Sesión actual"

    text = str(value).strip()
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


def _series_num(
    df: pd.DataFrame | None,
    column: str,
) -> pd.Series:
    if df is None:
        return pd.Series(dtype="float64")

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


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


BOX_QTY_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "cantidad_caja_sku.csv"
)


@st.cache_data(show_spinner=False)
def _load_box_qty_catalog() -> pd.DataFrame:
    """
    Catálogo SKU -> Cantidad por caja.

    Cuando el reporte WMS contiene más de un embalaje para el mismo SKU,
    se conservan todos los valores (ej. "15 / 30") en lugar de inventar
    una única cantidad.
    """
    if not BOX_QTY_FILE.exists():
        return pd.DataFrame(
            columns=["Código", "Cant. por caja"]
        )

    try:
        catalog = pd.read_csv(
            BOX_QTY_FILE,
            sep=";",
            dtype=str,
            encoding="utf-8-sig",
        )
    except Exception:
        return pd.DataFrame(
            columns=["Código", "Cant. por caja"]
        )

    if (
        "Código" not in catalog.columns
        or "Cant. por caja" not in catalog.columns
    ):
        return pd.DataFrame(
            columns=["Código", "Cant. por caja"]
        )

    catalog["Código"] = (
        catalog["Código"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    catalog["Cant. por caja"] = (
        catalog["Cant. por caja"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    return (
        catalog[
            catalog["Código"].ne("")
        ][["Código", "Cant. por caja"]]
        .drop_duplicates("Código")
        .reset_index(drop=True)
    )


def _add_box_qty(
    df: pd.DataFrame | None,
) -> pd.DataFrame | None:
    if (
        df is None
        or df.empty
        or "Código" not in df.columns
    ):
        return df

    catalog = _load_box_qty_catalog()
    if catalog.empty:
        out = df.copy()
        if "Cant. por caja" not in out.columns:
            out["Cant. por caja"] = "—"
        return out

    out = df.copy()
    out["Código"] = (
        out["Código"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Evitar duplicar columna si en el futuro la fuente ya la trae.
    if "Cant. por caja" in out.columns:
        out = out.drop(columns=["Cant. por caja"])

    out = out.merge(
        catalog,
        on="Código",
        how="left",
    )

    out["Cant. por caja"] = (
        out["Cant. por caja"]
        .fillna("—")
        .replace("", "—")
    )

    return out


def _options(
    df: pd.DataFrame,
    column: str,
) -> list[str]:
    if (
        df is None
        or df.empty
        or column not in df.columns
    ):
        return []

    values = (
        df[column]
        .replace("", pd.NA)
        .dropna()
        .astype(str)
        .str.strip()
    )

    return sorted(
        value
        for value in values.unique().tolist()
        if value
    )


def _prepare_search_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    out = df.copy()

    out["_search_codigo"] = (
        out.get(
            "Código",
            pd.Series("", index=out.index),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    out["_search_producto"] = (
        out.get(
            "Producto",
            pd.Series("", index=out.index),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    return out


def _build_summary(
    inventory: pd.DataFrame,
    consolidated: pd.DataFrame,
) -> dict:
    if (
        consolidated is None
        or consolidated.empty
    ):
        return {
            "sku_total": 0,
            "units_available": 0,
            "available": 0,
            "low": 0,
            "zero": 0,
            "negative": 0,
            "risk": 0,
            "incoming_sku": 0,
            "warehouses": 0,
        }

    states = (
        consolidated.get(
            "Estado",
            pd.Series(
                "",
                index=consolidated.index,
            ),
        )
        .fillna("")
        .astype(str)
    )

    warehouses = (
        int(
            inventory["Bodega"]
            .replace("", pd.NA)
            .dropna()
            .astype(str)
            .str.strip()
            .nunique()
        )
        if (
            inventory is not None
            and not inventory.empty
            and "Bodega" in inventory.columns
        )
        else 0
    )

    return {
        "sku_total": (
            int(
                consolidated[
                    "Código"
                ].nunique()
            )
            if "Código" in consolidated.columns
            else len(consolidated)
        ),
        "units_available": _safe_int(
            _series_num(
                consolidated,
                "Disponible",
            ).clip(lower=0).sum()
        ),
        "available": int(
            states.eq("🟢 Disponible").sum()
        ),
        "low": int(
            states.eq("🟡 Stock bajo").sum()
        ),
        "zero": int(
            states.eq("🔴 Sin stock").sum()
        ),
        "negative": int(
            states.eq("🔴 Negativo").sum()
        ),
        "risk": int(
            states.eq(
                "🟠 Riesgo despacho"
            ).sum()
        ),
        "incoming_sku": int(
            states.eq("🔵 Por llegar").sum()
        ),
        "warehouses": warehouses,
    }


def _warehouse_summary(
    inventory: pd.DataFrame,
) -> pd.DataFrame:
    if (
        inventory is None
        or inventory.empty
        or "Bodega" not in inventory.columns
        or "Disponible" not in inventory.columns
    ):
        return pd.DataFrame(
            columns=["Bodega", "Disponible"]
        )

    work = inventory.copy()

    work["Bodega"] = (
        work["Bodega"]
        .replace("", pd.NA)
        .fillna("Sin bodega")
        .astype(str)
        .str.strip()
    )

    work["Disponible"] = (
        pd.to_numeric(
            work["Disponible"],
            errors="coerce",
        )
        .fillna(0)
        .clip(lower=0)
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
        .reset_index(drop=True)
    )


def _critical_products(
    consolidated: pd.DataFrame,
    limit: int = 6,
) -> pd.DataFrame:
    if (
        consolidated is None
        or consolidated.empty
    ):
        return pd.DataFrame()

    required = {
        "Código",
        "Producto",
        "Disponible",
    }

    if not required.issubset(
        consolidated.columns
    ):
        return pd.DataFrame()

    work = consolidated.copy()

    work["Disponible"] = pd.to_numeric(
        work["Disponible"],
        errors="coerce",
    ).fillna(0)

    states = (
        work.get(
            "Estado",
            pd.Series(
                "",
                index=work.index,
            ),
        )
        .fillna("")
        .astype(str)
    )

    work["_priority"] = 99

    work.loc[
        states.isin(
            [
                "🔴 Sin stock",
                "🔴 Negativo",
            ]
        ),
        "_priority",
    ] = 1

    work.loc[
        states.eq("🟡 Stock bajo"),
        "_priority",
    ] = 2

    work.loc[
        states.eq(
            "🟠 Riesgo despacho"
        ),
        "_priority",
    ] = 3

    work = (
        work[
            work["_priority"] < 99
        ]
        .sort_values(
            [
                "_priority",
                "Disponible",
            ],
            ascending=True,
        )
        .head(limit)
        .copy()
    )

    if work.empty:
        return work

    if "Por llegar" not in work.columns:
        work["Por llegar"] = 0

    return work[
        [
            col
            for col in [
                "Código",
                "Producto",
                "Disponible",
                "Por llegar",
                "Estado",
            ]
            if col in work.columns
        ]
    ].reset_index(drop=True)


def _product_options(
    inventory: pd.DataFrame,
) -> list[str]:
    if (
        inventory is None
        or inventory.empty
        or "Código" not in inventory.columns
    ):
        return []

    work = inventory.copy()

    work["Código"] = (
        work["Código"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if "Producto" not in work.columns:
        work["Producto"] = work["Código"]

    work["Producto"] = (
        work["Producto"]
        .fillna(work["Código"])
        .astype(str)
        .str.strip()
    )

    work = (
        work[
            work["Código"].ne("")
        ][
            [
                "Código",
                "Producto",
            ]
        ]
        .drop_duplicates(
            "Código"
        )
        .sort_values(
            [
                "Producto",
                "Código",
            ]
        )
    )

    return [
        f"{row.Código} · {row.Producto}"
        for row in work.itertuples(
            index=False
        )
    ]


def _sku_from_option(
    option: str,
) -> str:
    if not option:
        return ""

    return (
        str(option)
        .split(" · ", 1)[0]
        .strip()
    )


def _selected_product_detail(
    inventory: pd.DataFrame,
    sku: str,
) -> pd.DataFrame:
    if (
        inventory is None
        or inventory.empty
        or not sku
        or "Código" not in inventory.columns
    ):
        return pd.DataFrame()

    work = inventory[
        inventory["Código"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq(str(sku).strip())
    ].copy()

    if work.empty:
        return work

    for col in [
        "Stock físico",
        "Disponible",
        "Por llegar",
        "Por despachar",
    ]:
        if col in work.columns:
            work[col] = (
                pd.to_numeric(
                    work[col],
                    errors="coerce",
                )
                .fillna(0)
                .round()
                .astype("Int64")
            )

    keep = [
        col
        for col in [
            "Bodega",
            "Cant. por caja",
            "Stock físico",
            "Disponible",
            "Por llegar",
            "Por despachar",
            "Estado",
        ]
        if col in work.columns
    ]

    return (
        work[keep]
        .sort_values(
            "Disponible",
            ascending=False,
        )
        .reset_index(drop=True)
    )


def _filter_inventory(
    inventory: pd.DataFrame,
    search: str,
    warehouse: str,
    family: str,
    subfamily: str,
    status: str,
) -> pd.DataFrame:
    filtered = _prepare_search_columns(
        inventory
    )

    if search:
        term = search.lower().strip()

        mask = (
            filtered[
                "_search_codigo"
            ].str.contains(
                term,
                regex=False,
            )
            |
            filtered[
                "_search_producto"
            ].str.contains(
                term,
                regex=False,
            )
        )

        filtered = filtered[
            mask
        ].copy()

    if (
        warehouse != "Todas"
        and "Bodega" in filtered.columns
    ):
        filtered = filtered[
            filtered["Bodega"].astype(
                str
            ).eq(warehouse)
        ].copy()

    if (
        family != "Todas"
        and "Familia" in filtered.columns
    ):
        filtered = filtered[
            filtered["Familia"].astype(
                str
            ).eq(family)
        ].copy()

    if (
        subfamily != "Todas"
        and "Subfamilia" in filtered.columns
    ):
        filtered = filtered[
            filtered[
                "Subfamilia"
            ].astype(str).eq(
                subfamily
            )
        ].copy()

    status_map = {
        "Disponible": "🟢 Disponible",
        "Stock bajo": "🟡 Stock bajo",
        "Sin stock": "🔴 Sin stock",
        "Negativo": "🔴 Negativo",
        "Riesgo despacho": (
            "🟠 Riesgo despacho"
        ),
        "Por llegar": "🔵 Por llegar",
    }

    if (
        status != "Todos"
        and "Estado" in filtered.columns
    ):
        filtered = filtered[
            filtered["Estado"].eq(
                status_map[status]
            )
        ].copy()

    return filtered.drop(
        columns=[
            "_search_codigo",
            "_search_producto",
        ],
        errors="ignore",
    )


def _kpi_card(
    label: str,
    value: str,
    helper: str,
    icon: str,
    tone: str,
) -> str:
    return f"""
    <div class="sgx-kpi">
        <div class="sgx-kpi-icon {escape(tone)}">
            {escape(icon)}
        </div>
        <div class="sgx-kpi-copy">
            <span>{escape(label)}</span>
            <strong>{escape(value)}</strong>
            <small class="{escape(tone)}">
                {escape(helper)}
            </small>
        </div>
    </div>
    """


# ============================================================
# CSS
# ============================================================

def _inject_css():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1660px;
            padding-top: 1.0rem;
            padding-bottom: 2rem;
        }

        div[data-testid="stVerticalBlock"] {
            gap: .72rem;
        }

        .sgx-head {
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:20px;
            margin-bottom:8px;
        }

        .sgx-title {
            color:#141a21;
            font-size:28px;
            font-weight:850;
            letter-spacing:-.8px;
            line-height:1;
        }

        .sgx-subtitle {
            margin-top:7px;
            font-size:12px;
            color:#7d8791;
        }

        .sgx-update {
            display:flex;
            align-items:center;
            gap:8px;
            white-space:nowrap;
            font-size:11px;
            color:#747e88;
            padding-top:5px;
        }

        .sgx-update i {
            width:8px;
            height:8px;
            border-radius:999px;
            background:#22c55e;
            box-shadow:0 0 0 4px rgba(34,197,94,.10);
        }

        .sgx-filter-label {
            font-size:9px;
            font-weight:800;
            color:#9199a1;
            letter-spacing:.42px;
            text-transform:uppercase;
            margin-bottom:2px;
        }

        .sgx-search-card {
            background:#fff;
            border:1px solid #e7ebef;
            border-radius:12px;
            padding:13px 14px 10px 14px;
            box-shadow:0 3px 12px rgba(20,30,45,.025);
            margin-top:2px;
        }

        .sgx-search-head {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:15px;
            margin-bottom:8px;
        }

        .sgx-search-head strong {
            display:block;
            color:#20272e;
            font-size:12px;
        }

        .sgx-search-head span {
            display:block;
            margin-top:2px;
            color:#8b949d;
            font-size:9.5px;
        }

        .sgx-product-meta {
            display:grid;
            grid-template-columns:repeat(4,minmax(0,1fr));
            gap:8px;
            margin-top:8px;
        }

        .sgx-product-meta > div {
            background:#f8fafb;
            border:1px solid #edf0f2;
            border-radius:8px;
            padding:8px 10px;
        }

        .sgx-product-meta span {
            display:block;
            color:#9aa2aa;
            font-size:8px;
            text-transform:uppercase;
            letter-spacing:.35px;
        }

        .sgx-product-meta strong {
            display:block;
            margin-top:3px;
            color:#232a31;
            font-size:10.5px;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }

        .sgx-kpis {
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:11px;
            margin:4px 0 1px 0;
        }

        .sgx-kpi {
            display:flex;
            align-items:center;
            gap:12px;
            min-height:92px;
            padding:15px;
            border:1px solid #e8ecef;
            border-radius:12px;
            background:#fff;
            box-shadow:0 3px 12px rgba(20,30,45,.03);
        }

        .sgx-kpi-icon {
            width:42px;
            height:42px;
            flex:0 0 42px;
            display:flex;
            align-items:center;
            justify-content:center;
            border-radius:50%;
            font-size:18px;
            font-weight:850;
        }

        .sgx-kpi-icon.neutral {
            background:#f1f3f5;
            color:#56616d;
        }

        .sgx-kpi-icon.green {
            background:#eaf7eb;
            color:#2d9f4a;
        }

        .sgx-kpi-icon.yellow {
            background:#fff6d8;
            color:#dea300;
        }

        .sgx-kpi-icon.red {
            background:#fff0ed;
            color:#df5147;
        }

        .sgx-kpi-copy {
            min-width:0;
        }

        .sgx-kpi-copy > span {
            display:block;
            color:#505a64;
            font-size:10px;
            font-weight:650;
        }

        .sgx-kpi-copy > strong {
            display:block;
            color:#151b21;
            font-size:22px;
            font-weight:850;
            line-height:1;
            margin-top:5px;
            letter-spacing:-.45px;
        }

        .sgx-kpi-copy > small {
            display:block;
            margin-top:6px;
            font-size:8.8px;
            color:#8c959e;
            font-weight:650;
        }

        .sgx-kpi-copy > small.green {
            color:#27a648;
        }

        .sgx-kpi-copy > small.yellow {
            color:#d39600;
        }

        .sgx-kpi-copy > small.red {
            color:#d95046;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color:#e7ebef !important;
            border-radius:12px !important;
            background:#fff !important;
            box-shadow:0 3px 12px rgba(20,30,45,.025);
        }

        .sgx-card-title {
            font-size:12.5px;
            font-weight:820;
            color:#20272e;
        }

        .sgx-card-sub {
            color:#9099a2;
            font-size:9.5px;
            margin-top:2px;
        }

        .sgx-health {
            display:grid;
            grid-template-columns:120px 1fr;
            gap:16px;
            align-items:center;
            margin-top:14px;
        }

        .sgx-ring {
            --p:0%;
            width:112px;
            height:112px;
            border-radius:50%;
            background:
                radial-gradient(circle at center,#fff 57%,transparent 58%),
                conic-gradient(#8fc267 var(--p),#ffc400 var(--p),#eef1f3 0);
            display:flex;
            align-items:center;
            justify-content:center;
        }

        .sgx-ring div {
            text-align:center;
        }

        .sgx-ring strong {
            display:block;
            font-size:27px;
            color:#12181e;
            font-weight:880;
            line-height:1;
        }

        .sgx-ring span {
            display:block;
            color:#79838c;
            font-size:9.5px;
            margin-top:5px;
        }

        .sgx-status {
            display:flex;
            flex-direction:column;
            gap:10px;
        }

        .sgx-status-row {
            display:grid;
            grid-template-columns:10px minmax(0,1fr) auto;
            gap:8px;
            align-items:center;
            font-size:9.8px;
        }

        .sgx-status-row i {
            width:8px;
            height:8px;
            border-radius:999px;
        }

        .sgx-status-row i.green { background:#8fc267; }
        .sgx-status-row i.yellow { background:#ffc400; }
        .sgx-status-row i.orange { background:#f3a44c; }
        .sgx-status-row i.red { background:#eb5b50; }

        .sgx-status-row span {
            color:#5d6770;
        }

        .sgx-status-row strong {
            color:#252c33;
            font-size:10px;
        }

        .sgx-healthy-note {
            margin-top:14px;
            padding:9px 10px;
            border-radius:7px;
            background:#eef8eb;
            color:#43853b;
            font-size:9px;
        }

        .sgx-wh-list {
            display:flex;
            flex-direction:column;
            gap:12px;
            margin-top:14px;
        }

        .sgx-wh-row {
            display:grid;
            grid-template-columns:92px minmax(0,1fr) 73px;
            align-items:center;
            gap:9px;
        }

        .sgx-wh-name {
            color:#59636d;
            font-size:9.8px;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }

        .sgx-wh-track {
            height:13px;
            border-radius:999px;
            background:#f1f3f5;
            overflow:hidden;
        }

        .sgx-wh-fill {
            height:100%;
            min-width:3px;
            border-radius:999px;
            background:linear-gradient(90deg,#ffc400,#ffd85e);
        }

        .sgx-wh-value {
            text-align:right;
            font-size:9.8px;
            color:#252d34;
            font-weight:780;
        }

        .sgx-wh-total {
            display:flex;
            justify-content:space-between;
            gap:10px;
            margin-top:15px;
            padding:9px 10px;
            border-radius:7px;
            border:1px solid #edf0f2;
            background:#f9fafb;
            font-size:9.2px;
            color:#747e87;
        }

        .sgx-wh-total strong {
            color:#20272e;
        }

        .sgx-alert-list {
            display:flex;
            flex-direction:column;
            gap:0;
            margin-top:7px;
        }

        .sgx-alert-row {
            display:grid;
            grid-template-columns:30px minmax(0,1fr) auto;
            gap:9px;
            align-items:center;
            min-height:48px;
            border-bottom:1px solid #edf0f2;
        }

        .sgx-alert-row:last-child {
            border-bottom:0;
        }

        .sgx-alert-icon {
            width:28px;
            height:28px;
            display:flex;
            align-items:center;
            justify-content:center;
            border-radius:8px;
            font-size:12px;
            font-weight:850;
        }

        .sgx-alert-icon.red {
            background:#fff0ed;
            color:#e35348;
        }

        .sgx-alert-icon.yellow {
            background:#fff7dc;
            color:#e1a200;
        }

        .sgx-alert-icon.blue {
            background:#eef5ff;
            color:#3b80d1;
        }

        .sgx-alert-icon.green {
            background:#eef8ec;
            color:#3da250;
        }

        .sgx-alert-row strong {
            display:block;
            font-size:10px;
            color:#26313d;
        }

        .sgx-alert-row span {
            display:block;
            margin-top:2px;
            font-size:8.7px;
            color:#939ca5;
        }

        .sgx-alert-value {
            font-size:9.5px;
            color:#56616a;
            font-weight:720;
        }

        .sgx-critical-table,
        .sgx-product-table {
            width:100%;
            border-collapse:collapse;
            font-size:9.7px;
            margin-top:8px;
        }

        .sgx-critical-table th,
        .sgx-product-table th {
            text-align:left;
            padding:8px 9px;
            color:#6d7780;
            font-size:8.5px;
            text-transform:uppercase;
            letter-spacing:.25px;
            border-bottom:1px solid #e7ebef;
        }

        .sgx-critical-table td,
        .sgx-product-table td {
            padding:9px;
            color:#2c343b;
            border-bottom:1px solid #edf0f2;
        }

        .sgx-critical-table tr:last-child td,
        .sgx-product-table tr:last-child td {
            border-bottom:0;
        }

        .sgx-badge {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            min-width:52px;
            border-radius:999px;
            padding:4px 8px;
            font-size:7.8px;
            font-weight:850;
        }

        .sgx-badge.green {
            background:#dff2dc;
            color:#3b8640;
        }

        .sgx-badge.yellow {
            background:#fff0bf;
            color:#9f6c00;
        }

        .sgx-badge.orange {
            background:#ffe8d5;
            color:#b85e17;
        }

        .sgx-badge.red {
            background:#ffdeda;
            color:#bf463e;
        }

        .sgx-detail-hero {
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:15px;
            padding:12px 0 2px 0;
        }

        .sgx-detail-hero span {
            display:block;
            color:#9aa2aa;
            font-size:8.5px;
            text-transform:uppercase;
            letter-spacing:.35px;
        }

        .sgx-detail-hero strong {
            display:block;
            color:#181e24;
            font-size:15px;
            margin-top:3px;
        }

        .sgx-detail-total {
            text-align:right;
        }

        .sgx-detail-total span {
            font-size:8px;
        }

        .sgx-detail-total strong {
            font-size:20px;
        }

        .sgx-detail-note {
            padding:11px 12px;
            background:#fff9e8;
            border:1px solid #f2e6b9;
            border-radius:9px;
            font-size:9px;
            color:#7c7358;
            line-height:1.5;
        }

        .sgx-section-head {
            margin-top:8px;
            margin-bottom:2px;
        }

        .sgx-section-head strong {
            display:block;
            font-size:13px;
            color:#1e252c;
        }

        .sgx-section-head span {
            display:block;
            margin-top:2px;
            font-size:9.5px;
            color:#8f98a1;
        }

        .sgx-result {
            display:flex;
            justify-content:space-between;
            gap:12px;
            padding:10px 12px;
            background:#f8fafb;
            border:1px solid #edf0f2;
            border-radius:9px;
        }

        .sgx-result span {
            display:block;
            font-size:8px;
            color:#929aa2;
            text-transform:uppercase;
            letter-spacing:.35px;
        }

        .sgx-result strong {
            display:block;
            margin-top:3px;
            font-size:10.5px;
            color:#252d34;
        }

        .stButton > button,
        .stDownloadButton > button {
            border-radius:9px !important;
            min-height:40px !important;
            font-size:10.5px !important;
            font-weight:720 !important;
        }

        @media(max-width:1100px) {
            .sgx-kpis {
                grid-template-columns:repeat(2,minmax(0,1fr));
            }

            .sgx-product-meta {
                grid-template-columns:repeat(2,minmax(0,1fr));
            }
        }

        @media(max-width:700px) {
            .sgx-head {
                flex-direction:column;
            }

            .sgx-kpis {
                grid-template-columns:1fr;
            }

            .sgx-health {
                grid-template-columns:1fr;
            }

            .sgx-product-meta {
                grid-template-columns:1fr;
            }
        }
        
        /* =========================================================
           MARITEX · STOCK GENERAL DARK HIGH CONTRAST
           ========================================================= */

        .stApp .main .block-container {
            background:#071018 !important;
            color:#f4f7f9 !important;
        }

        .stApp .main .sgx-head {
            margin:2px 0 14px 0 !important;
        }

        .stApp .main .sgx-title {
            color:#ffffff !important;
            font-size:34px !important;
            font-weight:900 !important;
            letter-spacing:-1px !important;
        }

        .stApp .main .sgx-subtitle {
            color:#a9bac6 !important;
            font-size:13px !important;
            font-weight:600 !important;
        }

        .stApp .main .sgx-update {
            color:#d7e0e6 !important;
            font-size:11px !important;
            border:1px solid #2b4453 !important;
            border-radius:10px !important;
            background:#0b151d !important;
            padding:9px 12px !important;
        }

        .stApp .main .sgx-search-card,
        .stApp .main div[data-testid="stVerticalBlockBorderWrapper"] {
            background:#0a141c !important;
            border-color:#2a414f !important;
            box-shadow:none !important;
        }

        .stApp .main .sgx-search-head strong,
        .stApp .main .sgx-card-title,
        .stApp .main .sgx-section-head strong {
            color:#ffffff !important;
            font-weight:850 !important;
        }

        .stApp .main .sgx-search-head span,
        .stApp .main .sgx-card-sub,
        .stApp .main .sgx-section-head span {
            color:#9fb2bf !important;
        }

        .stApp .main .sgx-product-meta > div {
            background:#0e1b25 !important;
            border-color:#29414f !important;
        }

        .stApp .main .sgx-product-meta span {
            color:#8da4b3 !important;
        }

        .stApp .main .sgx-product-meta strong {
            color:#ffffff !important;
        }

        .stApp .main .sgx-kpis {
            gap:12px !important;
            margin:8px 0 10px 0 !important;
        }

        .stApp .main .sgx-kpi {
            min-height:96px !important;
            background:#0c1821 !important;
            border:1px solid #2d4554 !important;
            border-radius:13px !important;
            box-shadow:none !important;
        }

        .stApp .main .sgx-kpi-copy > span {
            color:#b7c5ce !important;
            font-size:10px !important;
            font-weight:800 !important;
            text-transform:uppercase !important;
            letter-spacing:.35px !important;
        }

        .stApp .main .sgx-kpi-copy > strong {
            color:#ffffff !important;
            font-size:24px !important;
            font-weight:900 !important;
        }

        .stApp .main .sgx-kpi-copy > small {
            color:#9aacb7 !important;
            font-size:9px !important;
        }

        .stApp .main .sgx-kpi-icon.neutral {
            background:#172632 !important;
            color:#dbe5eb !important;
        }

        .stApp .main .sgx-kpi-icon.green {
            background:#0b3b2a !important;
            color:#38dc8a !important;
        }

        .stApp .main .sgx-kpi-icon.yellow {
            background:#443700 !important;
            color:#ffd000 !important;
        }

        .stApp .main .sgx-kpi-icon.red {
            background:#431d20 !important;
            color:#ff676f !important;
        }

        .stApp .main .sgx-health,
        .stApp .main .sgx-critical-table,
        .stApp .main .sgx-product-table {
            background:#09141c !important;
            border-color:#2a4250 !important;
        }

        .stApp .main .sgx-status-row,
        .stApp .main .sgx-alert-row {
            border-color:#243946 !important;
            color:#e9f0f4 !important;
        }

        .stApp .main .sgx-status-row span,
        .stApp .main .sgx-alert-row span {
            color:#dce6eb !important;
        }

        .stApp .main .sgx-wh-name {
            color:#dbe5eb !important;
            font-weight:750 !important;
        }

        .stApp .main .sgx-wh-value {
            color:#ffffff !important;
            font-weight:800 !important;
        }

        .stApp .main .sgx-wh-track {
            background:#20313d !important;
        }

        .stApp .main .sgx-wh-fill {
            background:#ffc800 !important;
        }

        .stApp .main .sgx-wh-total {
            background:#101e28 !important;
            border-color:#29414f !important;
            color:#f5f8fa !important;
        }

        .stApp .main .sgx-detail-hero,
        .stApp .main .sgx-detail-note,
        .stApp .main .sgx-result {
            background:#0e1b24 !important;
            border-color:#2b4351 !important;
            color:#eef4f7 !important;
        }

        .stApp .main .sgx-detail-hero span,
        .stApp .main .sgx-detail-note,
        .stApp .main .sgx-result span {
            color:#9fb2be !important;
        }

        .stApp .main .sgx-detail-hero strong,
        .stApp .main .sgx-detail-total strong,
        .stApp .main .sgx-result strong {
            color:#ffffff !important;
        }

        .stApp .main label,
        .stApp .main [data-testid="stWidgetLabel"] p,
        .stApp .main [data-testid="stSelectbox"] label,
        .stApp .main [data-testid="stTextInput"] label {
            color:#e8eef2 !important;
            font-weight:750 !important;
        }

        .stApp .main [data-baseweb="select"] > div,
        .stApp .main [data-testid="stTextInput"] input {
            background:#0d1a23 !important;
            color:#f7fafc !important;
            border-color:#304957 !important;
        }

        .stApp .main [data-testid="stTextInput"] input::placeholder {
            color:#738997 !important;
        }

        .stApp .main [data-testid="stExpander"] {
            background:#09141c !important;
            border:1px solid #2c4350 !important;
            border-radius:12px !important;
        }

        .stApp .main [data-testid="stExpander"] summary,
        .stApp .main [data-testid="stExpander"] summary p {
            color:#ffffff !important;
            font-weight:800 !important;
        }

        .stApp .main .stButton > button,
        .stApp .main .stDownloadButton > button {
            background:#0d1a23 !important;
            color:#ffffff !important;
            border:1px solid #334e5d !important;
            min-height:42px !important;
            font-weight:800 !important;
        }

        .stApp .main .stButton > button:hover,
        .stApp .main .stDownloadButton > button:hover {
            border-color:#ffc800 !important;
            color:#ffc800 !important;
        }

        .stApp .main button[kind="primary"],
        .stApp .main button[data-testid="stBaseButton-primary"] {
            background:#ffc800 !important;
            color:#070707 !important;
            border-color:#ffc800 !important;
        }

        .stApp .main div[data-testid="stDataFrame"] {
            border:1px solid #2a4250 !important;
            border-radius:10px !important;
            overflow:hidden !important;
            --gdg-bg-cell:#0c1720;
            --gdg-bg-header:#101f29;
            --gdg-text-dark:#f5f8fa;
            --gdg-text-medium:#dbe5ea;
            --gdg-border-color:#29404d;
            --gdg-accent-color:#ffc800;
            background:#0c1720 !important;
        }

        .stApp .main div[data-testid="stDataFrame"] > div,
        .stApp .main div[data-testid="stDataFrame"] canvas {
            background:#0c1720 !important;
        }

        .stApp .main .sgx-critical-table table,
        .stApp .main .sgx-product-table table {
            color:#eaf1f5 !important;
        }

        .stApp .main .sgx-critical-table th,
        .stApp .main .sgx-product-table th {
            color:#a9bdc9 !important;
            background:#101f29 !important;
            border-color:#2a414e !important;
        }

        .stApp .main .sgx-critical-table td,
        .stApp .main .sgx-product-table td {
            color:#e4edf2 !important;
            border-color:#243945 !important;
        }

        .stApp .main .sgx-healthy-note {
            background:#0d3827 !important;
            border-color:#1b6548 !important;
            color:#5be49f !important;
        }

        .stApp .main .sgx-badge,
        .stApp .main .sgx-badge.low {
            color:#080808 !important;
            background:#ffc800 !important;
            border-color:#ffc800 !important;
            font-weight:850 !important;
        }

        .stApp .main .sgx-badge.zero,
        .stApp .main .sgx-badge.negative {
            color:#ffffff !important;
            background:#7a252b !important;
            border-color:#a83a43 !important;
        }

        .stApp .main .sgx-badge.risk {
            color:#ffffff !important;
            background:#70431d !important;
            border-color:#99602b !important;
        }

        .stApp .main .sgx-badge.incoming {
            color:#dbeaff !important;
            background:#153c67 !important;
            border-color:#23568c !important;
        }

        .stApp .main .stCaption,
        .stApp .main small,
        .stApp .main p {
            color:#a8bac5;
        }

        .stApp .main h1,
        .stApp .main h2,
        .stApp .main h3,
        .stApp .main h4,
        .stApp .main h5 {
            color:#ffffff !important;
        }


/* V11 mockup-specific */
.stApp .main .block-container{
    max-width:1680px !important;
    padding-top:.6rem !important;
}
.stApp .main .sgx-kpis{
    margin-top:8px !important;
    margin-bottom:8px !important;
}
.stApp .main .sgx-kpi{
    min-height:88px !important;
}
.stApp .main [data-testid="stVerticalBlockBorderWrapper"]{
    padding-top:0 !important;
}
.stApp .main [data-testid="stExpander"]{
    margin-top:2px !important;
}
.stApp .main .sgx-critical-table td,
.stApp .main .sgx-critical-table th{
    font-size:9.5px !important;
}


/* =========================================================
   V12 · MARITEX STOCK GENERAL · MOCKUP EXACTO / HIGH CONTRAST
   ========================================================= */
.stApp .main .block-container{
    max-width:1740px !important;
    padding:12px 18px 28px !important;
    background:
      radial-gradient(circle at 78% 0%, rgba(255,200,0,.035), transparent 24%),
      #050b10 !important;
}

.stApp .main div[data-testid="stVerticalBlock"]{gap:.55rem !important}

/* Header */
.stApp .main .sgx-title{
    color:#fff !important;
    font-size:38px !important;
    line-height:1 !important;
    font-weight:950 !important;
    letter-spacing:-1.4px !important;
}
.stApp .main .sgx-subtitle{
    color:#a8b8c2 !important;
    font-size:14px !important;
    margin-top:8px !important;
}
.stApp .main .sgx-update{
    background:#071119 !important;
    border:1px solid #304653 !important;
    border-radius:11px !important;
    padding:10px 13px !important;
    color:#dbe6ec !important;
}
.stApp .main .sgx-update i{
    background:#ffc800 !important;
    box-shadow:0 0 0 4px rgba(255,200,0,.10) !important;
}

/* KPI row */
.stApp .main .sgx-kpis{
    display:grid !important;
    grid-template-columns:repeat(5,minmax(0,1fr)) !important;
    gap:10px !important;
    margin:10px 0 2px !important;
}
.stApp .main .sgx-kpi{
    min-height:104px !important;
    padding:17px 16px !important;
    border:1px solid #2a414e !important;
    border-radius:12px !important;
    background:linear-gradient(180deg,#0b151d 0%,#081119 100%) !important;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.018) !important;
}
.stApp .main .sgx-kpi-copy > span{
    color:#b9c8d1 !important;
    font-size:10px !important;
}
.stApp .main .sgx-kpi-copy > strong{
    color:#fff !important;
    font-size:25px !important;
}
.stApp .main .sgx-kpi-copy > small{
    color:#93a7b3 !important;
}

/* Actual Streamlit bordered cards */
.stApp .main div[data-testid="stVerticalBlockBorderWrapper"]{
    background:linear-gradient(180deg,#071119,#060e14) !important;
    border:1px solid #29404d !important;
    border-radius:12px !important;
    box-shadow:none !important;
}
.stApp .main div[data-testid="stVerticalBlockBorderWrapper"] > div{
    background:transparent !important;
}

/* Panel headings */
.stApp .main .sgx-card-title{
    color:#fff !important;
    font-size:15px !important;
    font-weight:900 !important;
}
.stApp .main .sgx-card-sub{
    color:#91a7b4 !important;
    font-size:10.5px !important;
}

/* Donut */
.stApp .main .sgx-ring{
    width:126px !important;
    height:126px !important;
    background:
      radial-gradient(circle at center,#071119 56%,transparent 57%),
      conic-gradient(#79c653 var(--p),#ffc800 var(--p),#1d2c35 0) !important;
}
.stApp .main .sgx-ring strong{
    color:#fff !important;
    font-size:31px !important;
}
.stApp .main .sgx-ring span{color:#9bb0bc !important}
.stApp .main .sgx-status-row span{color:#d4e0e6 !important}
.stApp .main .sgx-status-row strong{color:#fff !important}
.stApp .main .sgx-healthy-note{
    background:#0a3824 !important;
    border:1px solid #145d3c !important;
    color:#50e693 !important;
}

/* Warehouse */
.stApp .main .sgx-wh-name{color:#d3dfe5 !important}
.stApp .main .sgx-wh-track{background:#1a2a34 !important}
.stApp .main .sgx-wh-fill{
    background:linear-gradient(90deg,#ffc400,#ffd85a) !important;
}
.stApp .main .sgx-wh-value{color:#fff !important}
.stApp .main .sgx-wh-total{
    background:#0d1922 !important;
    border:1px solid #29404d !important;
    color:#b7c6cf !important;
}
.stApp .main .sgx-wh-total strong{color:#fff !important}

/* Alerts */
.stApp .main .sgx-alert-row{
    border-bottom:1px solid #253946 !important;
}
.stApp .main .sgx-alert-row strong{color:#eef4f7 !important}
.stApp .main .sgx-alert-row span{color:#93a8b4 !important}
.stApp .main .sgx-alert-value{color:#fff !important}

/* Critical table */
.stApp .main .sgx-critical-table{
    background:transparent !important;
}
.stApp .main .sgx-critical-table th{
    color:#8299a6 !important;
    background:#0d1b24 !important;
    border-bottom:1px solid #314954 !important;
}
.stApp .main .sgx-critical-table td{
    color:#dce6eb !important;
    border-bottom:1px solid #22343f !important;
}
.stApp .main .sgx-critical-table td:nth-child(2){
    color:#f1f5f7 !important;
}

/* Summary operational */
.stApp .main .sgx-result{
    border-radius:11px !important;
}
.stApp .main .sgx-result span{color:#a9bac5 !important}
.stApp .main .sgx-result strong{color:#fff !important}

/* Inventory expander */
.stApp .main div[data-testid="stExpander"]{
    background:#061018 !important;
    border:1px solid #2a414e !important;
    border-radius:12px !important;
    overflow:hidden !important;
}
.stApp .main div[data-testid="stExpander"] summary{
    min-height:48px !important;
    background:#08141c !important;
}
.stApp .main div[data-testid="stExpander"] summary p{
    color:#fff !important;
    font-size:15px !important;
    font-weight:900 !important;
}

/* Filters */
.stApp .main label p{
    color:#dce7ec !important;
    font-weight:800 !important;
}
.stApp .main [data-baseweb="select"] > div,
.stApp .main [data-testid="stTextInput"] input{
    background:#0a1720 !important;
    border:1px solid #314955 !important;
    color:#fff !important;
    min-height:42px !important;
}
.stApp .main [data-testid="stTextInput"] input::placeholder{
    color:#6f8794 !important;
}

/* Buttons */
.stApp .main button[kind="primary"],
.stApp .main button[data-testid="stBaseButton-primary"]{
    background:#ffc400 !important;
    color:#050505 !important;
    border:1px solid #ffc400 !important;
    font-weight:900 !important;
    min-height:46px !important;
}
.stApp .main .stDownloadButton button{
    background:#ffc400 !important;
    color:#050505 !important;
    border-color:#ffc400 !important;
    font-weight:900 !important;
}

/* Dataframe shell */
.stApp .main div[data-testid="stDataFrame"]{
    border:1px solid #2a414e !important;
    border-radius:10px !important;
    overflow:hidden !important;
    background:#08131b !important;
}

/* Hide excessive empty spacing around generated cards */
.stApp .main .element-container:has(.sgx-kpis),
.stApp .main .element-container:has(.sgx-health),
.stApp .main .element-container:has(.sgx-alert-list){
    margin-bottom:0 !important;
}

@media(max-width:1200px){
  .stApp .main .sgx-kpis{grid-template-columns:repeat(2,minmax(0,1fr)) !important}
}


/* =========================================================
   V13 CUSTOM HTML DASHBOARD
   ========================================================= */
.v13-dashboard{
    color:#fff;
    font-family:inherit;
    padding:2px 0 4px;
}
.v13-head{
    display:flex;justify-content:space-between;align-items:flex-start;
    gap:20px;margin-bottom:14px;
}
.v13-head h1{
    margin:0;color:#fff;font-size:36px;line-height:1;
    font-weight:950;letter-spacing:-1.2px;
}
.v13-head p{
    margin:8px 0 0;color:#a4b6c1;font-size:13px;
}
.v13-datebox{
    min-width:210px;border:1px solid #2b414e;border-radius:10px;
    background:#071119;padding:10px 13px;
}
.v13-datebox span{
    display:block;font-size:8px;letter-spacing:.06em;
    color:#8298a6;font-weight:800;
}
.v13-datebox strong{
    display:block;margin-top:4px;color:#fff;font-size:11px;
}
.v13-kpis{
    display:grid;grid-template-columns:repeat(5,minmax(0,1fr));
    gap:10px;margin-bottom:10px;
}
.v13-kpi{
    min-height:88px;border:1px solid #2a414e;border-radius:11px;
    background:linear-gradient(180deg,#0b151d,#081119);
    display:flex;align-items:center;gap:13px;padding:13px 15px;
}
.v13-kpi span{
    display:block;color:#9fb0bb;font-size:9px;font-weight:800;
}
.v13-kpi strong{
    display:block;color:#fff;font-size:23px;font-weight:900;
    margin-top:3px;
}
.v13-kpi small{
    display:block;color:#8ca0ac;font-size:8px;margin-top:4px;
}
.v13-icon{
    width:40px;height:40px;border-radius:50%;display:flex;
    align-items:center;justify-content:center;font-size:17px;font-weight:900;
    flex:0 0 40px;
}
.v13-icon.yellow{background:#3e3300;color:#ffc800}
.v13-icon.neutral{background:#192833;color:#d9e4ea}
.v13-icon.green{background:#093a27;color:#39e38c}
.v13-icon.red{background:#401d21;color:#ff666d}
.v13-main-grid{
    display:grid;grid-template-columns:1fr 1.18fr 1.08fr;
    gap:10px;margin-bottom:10px;
}
.v13-lower-grid{
    display:grid;grid-template-columns:1.7fr 1fr;
    gap:10px;margin-bottom:8px;
}
.v13-panel{
    border:1px solid #2a414e;border-radius:11px;
    background:linear-gradient(180deg,#071119,#060e14);
    padding:14px 15px;
}
.v13-panel-title{font-size:14px;font-weight:900;color:#fff}
.v13-panel-sub{font-size:9px;color:#8ea4b1;margin-top:3px}
.v13-health{
    display:grid;grid-template-columns:132px 1fr;gap:16px;
    align-items:center;margin-top:14px;
}
.v13-ring{
    --p:0%;width:122px;height:122px;border-radius:50%;
    background:
      radial-gradient(circle at center,#071119 56%,transparent 57%),
      conic-gradient(#78c653 var(--p),#ffc800 var(--p),#1d2c35 0);
    display:flex;align-items:center;justify-content:center;
}
.v13-ring div{text-align:center}
.v13-ring strong{display:block;color:#fff;font-size:29px}
.v13-ring span{display:block;color:#9cb0bb;font-size:9px;margin-top:4px}
.v13-status-list{display:flex;flex-direction:column;gap:11px}
.v13-status-list>div{
    display:grid;grid-template-columns:10px 1fr auto;gap:8px;
    align-items:center;color:#dce6eb;font-size:9px;
}
.v13-status-list i{width:8px;height:8px;border-radius:50%}
.v13-status-list i.green{background:#78c653}
.v13-status-list i.yellow{background:#ffc800}
.v13-status-list i.orange{background:#f4a340}
.v13-status-list i.red{background:#ef5b58}
.v13-status-list b{color:#fff}
.v13-success{
    margin-top:14px;padding:9px 10px;border-radius:7px;
    background:#0b3825;border:1px solid #155e3d;color:#53e595;
    font-size:8.5px;
}
.v13-wh-list{display:flex;flex-direction:column;gap:12px;margin-top:15px}
.v13-wh-row{
    display:grid;grid-template-columns:95px 1fr 92px;gap:10px;
    align-items:center;
}
.v13-wh-name{font-size:9px;color:#cbd7dd;white-space:nowrap}
.v13-wh-track{
    height:13px;border-radius:99px;background:#1c2d37;overflow:hidden;
}
.v13-wh-fill{
    height:100%;border-radius:99px;
    background:linear-gradient(90deg,#ffc400,#ffd85a);
}
.v13-wh-value{text-align:right;color:#fff;font-size:9px;font-weight:800}
.v13-wh-value span{color:#7f95a2;font-weight:500}
.v13-total{
    display:flex;justify-content:space-between;margin-top:15px;
    padding:9px 10px;border-radius:7px;border:1px solid #2a414e;
    background:#0d1922;color:#aabac4;font-size:9px;
}
.v13-total strong{color:#fff}
.v13-alerts{margin-top:10px}
.v13-alert{
    display:grid;grid-template-columns:31px 1fr auto;gap:9px;
    align-items:center;min-height:46px;border-bottom:1px solid #243844;
}
.v13-alert:last-child{border-bottom:0}
.v13-alert-icon{
    width:28px;height:28px;border-radius:8px;display:flex;
    align-items:center;justify-content:center;font-weight:900;
}
.v13-alert-icon.red{background:#401d21;color:#ff686f}
.v13-alert-icon.yellow{background:#3e3300;color:#ffc800}
.v13-alert-icon.blue{background:#122f4f;color:#69a9ff}
.v13-alert-icon.green{background:#093a27;color:#39e38c}
.v13-alert strong{display:block;color:#eef4f7;font-size:9.5px}
.v13-alert span{display:block;color:#8ea4b1;font-size:8px;margin-top:2px}
.v13-alert>b{color:#fff;font-size:9px}
.v13-table{
    width:100%;border-collapse:collapse;margin-top:12px;font-size:9px;
}
.v13-table th{
    text-align:left;padding:8px;color:#8197a5;font-size:8px;
    background:#0d1a23;border-bottom:1px solid #314854;
}
.v13-table td{
    padding:8px;color:#dce6eb;border-bottom:1px solid #21333e;
}
.v13-table td:nth-child(2){color:#f1f5f7}
.v13-table .num{text-align:right}
.v13-badge{
    display:inline-flex;align-items:center;justify-content:center;
    min-width:56px;border-radius:99px;padding:4px 8px;
    font-size:7px;font-weight:900;
}
.v13-badge.yellow{background:#ffc800;color:#050505}
.v13-badge.red{background:#7a272e;color:#fff}
.v13-badge.orange{background:#75431c;color:#fff}
.v13-summary-grid{
    display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px;
}
.v13-summary-card{
    min-height:105px;border-radius:10px;padding:14px;
    position:relative;
}
.v13-summary-card span{display:block;font-size:8px;color:#b6c4cd}
.v13-summary-card strong{
    display:block;font-size:27px;color:#fff;margin-top:14px;font-weight:900;
}
.v13-summary-card>b{
    position:absolute;right:14px;bottom:14px;font-size:24px;
}
.v13-summary-card.attention{
    background:#332900;border:1px solid #6e5900;
}
.v13-summary-card.attention>b{color:#ffc800}
.v13-summary-card.healthy{
    background:#07361f;border:1px solid #11623c;
}
.v13-summary-card.healthy>b{color:#39e38c}
.v13-note{
    margin-top:10px;background:#0e1a22;border:1px solid #2a414e;
    color:#9fb1bc;border-radius:8px;padding:10px;font-size:8px;
}
@media(max-width:1200px){
    .v13-kpis{grid-template-columns:repeat(2,1fr)}
    .v13-main-grid,.v13-lower-grid{grid-template-columns:1fr}
}


/* =========================================================
   V16 · CONSULTA DE PRODUCTO POR BODEGA
   ========================================================= */
.v16-lookup-shell{
    border:1px solid #2a414e;
    border-radius:12px;
    background:linear-gradient(180deg,#071119,#060e14);
    padding:15px;
    margin:10px 0;
}
.v16-lookup-title{
    color:#fff;font-size:14px;font-weight:900;
}
.v16-lookup-sub{
    color:#8ea4b1;font-size:9.5px;margin-top:3px;
}
.v16-product-meta{
    display:grid;
    grid-template-columns:1fr 2fr 1.45fr .9fr;
    gap:9px;
    margin-top:10px;
}
.v16-product-meta>div{
    border:1px solid #29404d;
    border-radius:10px;
    background:#0b171f;
    padding:10px 12px;
}
.v16-product-meta span{
    display:block;
    color:#7f95a2;
    font-size:8px;
    letter-spacing:.05em;
    text-transform:uppercase;
    font-weight:800;
}
.v16-product-meta strong{
    display:block;
    color:#fff;
    font-size:11px;
    margin-top:4px;
    font-weight:850;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
}
.v16-stock-title{
    color:#fff;
    font-size:11px;
    font-weight:900;
    margin:12px 0 8px;
}
.v16-stock-grid{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:9px;
}
.v16-stock-card{
    border:1px solid #29404d;
    border-radius:10px;
    background:#0b171f;
    padding:12px;
    min-height:96px;
}
.v16-stock-card.total{
    background:linear-gradient(180deg,#0d1b24,#0a151d);
}
.v16-stock-card .top{
    display:flex;
    align-items:center;
    gap:8px;
}
.v16-stock-card .dot{
    width:22px;height:22px;border-radius:7px;
    display:flex;align-items:center;justify-content:center;
    background:#07361f;color:#3ce58f;
    font-size:12px;font-weight:900;
}
.v16-stock-card span{
    color:#aebfc8;
    font-size:8.5px;
    font-weight:800;
}
.v16-stock-card strong{
    display:block;
    color:#fff;
    font-size:23px;
    line-height:1;
    margin-top:12px;
    font-weight:900;
}
.v16-stock-card small{
    display:block;
    color:#8196a3;
    font-size:8px;
    margin-top:4px;
}
.v16-stock-bar{
    margin-top:10px;
    height:7px;
    border-radius:99px;
    background:#20323d;
    overflow:hidden;
}
.v16-stock-fill{
    height:100%;
    border-radius:99px;
    background:#ffc800;
    min-width:2px;
}
@media(max-width:1100px){
    .v16-product-meta{grid-template-columns:repeat(2,1fr)}
    .v16-stock-grid{grid-template-columns:repeat(2,1fr)}
}


/* =========================================================
   V17 · STOCK GENERAL · MOCKUP APROBADO
   ========================================================= */
.stApp .main .block-container{
    max-width:1720px !important;
    padding:10px 16px 28px !important;
    background:#050b10 !important;
}
.sg17-head{
    display:grid;
    grid-template-columns:1fr 390px;
    gap:18px;
    align-items:start;
    margin-bottom:10px;
}
.sg17-title{
    color:#fff;
    font-size:34px;
    line-height:1;
    font-weight:950;
    letter-spacing:-1.2px;
}
.sg17-sub{
    margin-top:7px;
    color:#9eb0bb;
    font-size:12px;
}
.sg17-date{
    border:1px solid #293f4c;
    background:#071119;
    border-radius:10px;
    padding:9px 12px;
    min-height:48px;
}
.sg17-date span{
    display:block;
    color:#8298a5;
    font-size:8px;
    font-weight:850;
    letter-spacing:.05em;
}
.sg17-date strong{
    display:block;
    color:#fff;
    font-size:11px;
    margin-top:3px;
}
.sg17-kpis{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:9px;
    margin:8px 0 9px;
}
.sg17-kpi{
    min-height:76px;
    border:1px solid #263d49;
    border-radius:10px;
    background:linear-gradient(180deg,#09141c,#071018);
    display:flex;
    align-items:center;
    gap:12px;
    padding:12px 14px;
}
.sg17-kpi-icon{
    width:40px;height:40px;border-radius:50%;
    display:flex;align-items:center;justify-content:center;
    font-size:18px;font-weight:950;flex:0 0 40px;
}
.sg17-kpi-icon.y{background:#3c3100;color:#ffc800}
.sg17-kpi-icon.n{background:#182833;color:#d7e4ea}
.sg17-kpi-icon.g{background:#073721;color:#34e58b}
.sg17-kpi-icon.r{background:#401c21;color:#ff626a}
.sg17-kpi span{
    display:block;color:#9baeb9;font-size:8.5px;font-weight:850;
}
.sg17-kpi strong{
    display:block;color:#fff;font-size:22px;line-height:1;margin-top:4px;font-weight:950;
}
.sg17-kpi small{
    display:block;color:#879ba7;font-size:8px;margin-top:5px;
}
.sg17-topgrid{
    display:grid;
    grid-template-columns:1.05fr 1.12fr .95fr;
    gap:9px;
    margin-bottom:9px;
}
.sg17-panel{
    border:1px solid #263d49;
    border-radius:10px;
    background:linear-gradient(180deg,#071119,#060e14);
    padding:13px 14px;
}
.sg17-panel-title{color:#fff;font-size:14px;font-weight:900}
.sg17-panel-sub{color:#8da3af;font-size:9.5px;margin-top:3px}
.sg17-health{
    display:grid;grid-template-columns:125px 1fr;gap:14px;align-items:center;
    margin-top:14px;
}
.sg17-ring{
    --p:0%;
    width:116px;height:116px;border-radius:50%;
    background:
      radial-gradient(circle at center,#071119 57%,transparent 58%),
      conic-gradient(#77c653 var(--p),#ffc800 var(--p),#1b2b35 0);
    display:flex;align-items:center;justify-content:center;
}
.sg17-ring div{text-align:center}
.sg17-ring strong{display:block;color:#fff;font-size:28px;line-height:1}
.sg17-ring span{display:block;color:#9db0ba;font-size:8.5px;margin-top:5px}
.sg17-status{display:flex;flex-direction:column;gap:9px}
.sg17-status-row{
    display:grid;grid-template-columns:10px 1fr auto;gap:8px;align-items:center;
    color:#dce6eb;font-size:9px;
}
.sg17-status-row i{width:8px;height:8px;border-radius:50%}
.sg17-status-row i.g{background:#77c653}
.sg17-status-row i.y{background:#ffc800}
.sg17-status-row i.o{background:#f5a241}
.sg17-status-row i.r{background:#ef5c59}
.sg17-status-row b{color:#fff}
.sg17-ok{
    margin-top:13px;padding:8px 9px;border-radius:7px;
    background:#093822;border:1px solid #12603b;color:#45e48b;font-size:8.5px;
}
.sg17-wh{display:flex;flex-direction:column;gap:11px;margin-top:14px}
.sg17-wh-row{
    display:grid;grid-template-columns:88px 1fr 90px;gap:9px;align-items:center;
}
.sg17-wh-name{color:#d4dfe4;font-size:9px}
.sg17-wh-track{height:12px;border-radius:99px;background:#1a2a34;overflow:hidden}
.sg17-wh-fill{height:100%;background:#ffc800;border-radius:99px}
.sg17-wh-val{text-align:right;color:#fff;font-size:9px;font-weight:850}
.sg17-wh-val span{color:#8196a2;font-weight:500}
.sg17-wh-total{
    display:flex;justify-content:space-between;margin-top:14px;padding:9px 10px;
    border-radius:7px;border:1px solid #273e4a;background:#0d1922;
    color:#9eb0ba;font-size:9px;
}
.sg17-wh-total strong{color:#fff}
.sg17-alerts{margin-top:8px}
.sg17-alert{
    display:grid;grid-template-columns:30px 1fr auto;gap:8px;align-items:center;
    min-height:44px;border-bottom:1px solid #213541;
}
.sg17-alert:last-child{border-bottom:0}
.sg17-alert-icon{
    width:27px;height:27px;border-radius:8px;display:flex;align-items:center;
    justify-content:center;font-weight:950;
}
.sg17-alert-icon.r{background:#421d22;color:#ff666d}
.sg17-alert-icon.y{background:#3f3300;color:#ffc800}
.sg17-alert-icon.b{background:#102f51;color:#6caaff}
.sg17-alert-icon.g{background:#083821;color:#38e58d}
.sg17-alert strong{display:block;color:#edf3f6;font-size:9px}
.sg17-alert span{display:block;color:#879ca8;font-size:7.8px;margin-top:2px}
.sg17-alert>b{color:#fff;font-size:9px}

/* lookup */
.sg17-lookup-head{
    border:1px solid #263d49;border-bottom:0;
    border-radius:10px 10px 0 0;
    background:#071119;padding:12px 14px 5px;
}
.sg17-lookup-head strong{display:block;color:#fff;font-size:14px}
.sg17-lookup-head span{display:block;color:#8fa4b0;font-size:9px;margin-top:3px}
.sg17-lookup-body{
    border:1px solid #263d49;border-top:0;
    border-radius:0 0 10px 10px;
    background:#071119;padding:3px 14px 10px;margin-bottom:9px;
}
.sg17-productmeta{
    display:grid;grid-template-columns:1fr 2fr 1.45fr .9fr;gap:8px;margin-top:5px;
}
.sg17-productmeta>div{
    border:1px solid #293f4c;border-radius:9px;background:#0a1720;padding:7px 10px;
}
.sg17-productmeta span{
    display:block;color:#7f95a2;font-size:7.5px;font-weight:850;text-transform:uppercase;
}
.sg17-productmeta strong{
    display:block;color:#fff;font-size:10px;margin-top:4px;font-weight:850;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.sg17-stock-title{color:#fff;font-size:10px;font-weight:900;margin:7px 0 6px}
.sg17-stockgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}
.sg17-stockcard{
    border:1px solid #293f4c;border-radius:9px;background:#0a1720;padding:10px;
    min-height:86px;
}
.sg17-stockcard .top{display:flex;align-items:center;gap:7px}
.sg17-stockcard .ico{
    width:21px;height:21px;border-radius:6px;background:#073721;color:#38e58d;
    display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:950;
}
.sg17-stockcard span{color:#afbdc5;font-size:8px;font-weight:850}
.sg17-stockcard strong{display:block;color:#fff;font-size:22px;margin-top:10px;line-height:1}
.sg17-stockcard small{display:block;color:#8196a2;font-size:7.7px;margin-top:4px}
.sg17-stockbar{height:6px;border-radius:99px;background:#1f313c;margin-top:9px;overflow:hidden}
.sg17-stockfill{height:100%;background:#ffc800;border-radius:99px;min-width:2px}
.sg17-stockcard.total{background:#0d1a23}

/* lower */
.sg17-lower{display:grid;grid-template-columns:1.65fr 1fr;gap:9px;margin-bottom:9px}
.sg17-table{width:100%;border-collapse:collapse;margin-top:10px;font-size:8.5px}
.sg17-table th{
    padding:7px;color:#879ca8;background:#0d1a23;text-align:left;font-size:7.5px;
    border-bottom:1px solid #2b424e;
}
.sg17-table td{
    padding:7px;color:#dce6eb;border-bottom:1px solid #20323d;
}
.sg17-table td:nth-child(2){color:#f1f5f7}
.sg17-badge{
    display:inline-flex;min-width:50px;justify-content:center;border-radius:99px;
    padding:3px 7px;background:#ffc800;color:#050505;font-size:7px;font-weight:950;
}
.sg17-summary{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin-top:12px}
.sg17-summary-card{
    min-height:90px;border-radius:9px;padding:12px;position:relative;
}
.sg17-summary-card.a{background:#322900;border:1px solid #6c5900}
.sg17-summary-card.h{background:#07351f;border:1px solid #12613c}
.sg17-summary-card span{display:block;color:#b6c4cd;font-size:7.5px;font-weight:850}
.sg17-summary-card strong{display:block;color:#fff;font-size:25px;margin-top:12px}
.sg17-summary-card b{position:absolute;right:12px;bottom:12px;font-size:22px}
.sg17-summary-card.a b{color:#ffc800}
.sg17-summary-card.h b{color:#39e38c}
.sg17-note{
    margin-top:9px;border:1px solid #263d49;border-radius:8px;background:#0d1922;
    padding:9px;color:#91a6b2;font-size:7.8px;
}

/* Native controls inside lookup/inventory */
.stApp .main [data-testid="stTextInput"] input,
.stApp .main [data-baseweb="select"] > div{
    background:#0a1720 !important;
    color:#fff !important;
    border:1px solid #2c4350 !important;
    border-radius:8px !important;
    min-height:38px !important;
}
.stApp .main [data-testid="stWidgetLabel"] p{
    color:#dce6eb !important;font-size:9px !important;font-weight:850 !important;
}
.stApp .main button[kind="primary"],
.stApp .main button[data-testid="stBaseButton-primary"]{
    background:#ffc800 !important;color:#050505 !important;border-color:#ffc800 !important;
    font-weight:900 !important;
}
.stApp .main div[data-testid="stExpander"]{
    background:#071119 !important;border:1px solid #263d49 !important;border-radius:10px !important;
}
@media(max-width:1100px){
    .sg17-head{grid-template-columns:1fr}
    .sg17-kpis{grid-template-columns:repeat(2,1fr)}
    .sg17-topgrid,.sg17-lower{grid-template-columns:1fr}
    .sg17-productmeta,.sg17-stockgrid{grid-template-columns:repeat(2,1fr)}
}


/* V19 · Inventario completo más compacto */
.stApp .main [data-testid="stDataFrame"]{
    border:1px solid #263d49 !important;
    border-radius:9px !important;
    overflow:hidden !important;
}
.stApp .main [data-testid="stDataFrame"] [role="columnheader"]{
    font-size:12px !important;
}
.stApp .main [data-testid="stDataFrame"] [role="gridcell"]{
    font-size:12px !important;
}


/* =========================================================
   V20 · INVENTARIO COMPLETO
   Botón Excel amarillo + tabla negra integrada al dashboard
   ========================================================= */

/* Botón Exportar Excel */
.stApp .main div[data-testid="stDownloadButton"] > button {
    background: linear-gradient(180deg, #ffd51a 0%, #ffc400 100%) !important;
    color: #070707 !important;
    border: 1px solid #ffc400 !important;
    border-radius: 9px !important;
    font-weight: 900 !important;
    min-height: 42px !important;
    box-shadow: none !important;
}

.stApp .main div[data-testid="stDownloadButton"] > button p,
.stApp .main div[data-testid="stDownloadButton"] > button span,
.stApp .main div[data-testid="stDownloadButton"] > button svg {
    color: #070707 !important;
    fill: #070707 !important;
}

.stApp .main div[data-testid="stDownloadButton"] > button:hover {
    background: #ffdc38 !important;
    border-color: #ffdc38 !important;
    color: #070707 !important;
    transform: none !important;
}

/* Contenedor de la tabla */
.stApp .main div[data-testid="stDataFrame"] {
    background: #050b10 !important;
    border: 1px solid #263d49 !important;
    border-radius: 10px !important;
    overflow: hidden !important;
    box-shadow: none !important;

    --gdg-bg-cell: #050b10;
    --gdg-bg-header: #0b151d;
    --gdg-bg-header-has-focus: #101d26;
    --gdg-bg-cell-medium: #081119;
    --gdg-bg-bubble: #0b151d;

    --gdg-text-dark: #f4f7f9;
    --gdg-text-medium: #d5e0e6;
    --gdg-text-light: #8fa4b0;
    --gdg-border-color: #223742;
    --gdg-horizontal-border-color: #223742;
    --gdg-accent-color: #ffc400;
    --gdg-accent-light: rgba(255,196,0,.12);
}

/* Fondo real interno del dataframe */
.stApp .main div[data-testid="stDataFrame"] > div,
.stApp .main div[data-testid="stDataFrame"] canvas,
.stApp .main div[data-testid="stDataFrame"] [role="grid"],
.stApp .main div[data-testid="stDataFrame"] [role="rowgroup"] {
    background: #050b10 !important;
}

/* Encabezados */
.stApp .main div[data-testid="stDataFrame"] [role="columnheader"] {
    background: #0b151d !important;
    color: #b9c8d1 !important;
    border-color: #263d49 !important;
    font-weight: 850 !important;
}

/* Celdas */
.stApp .main div[data-testid="stDataFrame"] [role="gridcell"] {
    background: #050b10 !important;
    color: #edf3f6 !important;
    border-color: #20333e !important;
}

/* Hover */
.stApp .main div[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
    background: #0a151d !important;
}

/* Scrollbars del dataframe */
.stApp .main div[data-testid="stDataFrame"] ::-webkit-scrollbar {
    width: 8px !important;
    height: 8px !important;
}

.stApp .main div[data-testid="stDataFrame"] ::-webkit-scrollbar-track {
    background: #071018 !important;
}

.stApp .main div[data-testid="stDataFrame"] ::-webkit-scrollbar-thumb {
    background: #344b58 !important;
    border-radius: 999px !important;
}

.stApp .main div[data-testid="stDataFrame"] ::-webkit-scrollbar-thumb:hover {
    background: #4a6270 !important;
}


/* V21 · Tabla HTML negra Maritex */
.v21-table-shell{width:100%;margin-top:10px;background:#03080c;border:1px solid #263b46;border-radius:10px;overflow:hidden}
.v21-table-scroll{width:100%;overflow-x:auto;background:#03080c}
.v21-table{width:100%;min-width:1000px;border-collapse:collapse;background:#03080c;color:#f4f7f8}
.v21-table thead th{background:#0b151c;color:#aebdc5;padding:11px 12px;font-size:12px;font-weight:800;text-align:left;white-space:nowrap;border-right:1px solid #20343e;border-bottom:1px solid #314954}
.v21-table tbody td{background:#03080c;color:#f5f7f8;padding:10px 12px;font-size:13px;border-right:1px solid #182a33;border-bottom:1px solid #1c3039;vertical-align:middle}
.v21-table tbody tr:nth-child(even) td{background:#061016}
.v21-table tbody tr:hover td{background:#0a171f}
.v21-table th.num,.v21-table td.num{text-align:right}
.v21-table th:first-child,.v21-table td:first-child{width:105px;white-space:nowrap}
.v21-table th:nth-child(2),.v21-table td:nth-child(2){min-width:330px}
.v21-status{display:inline-flex;align-items:center;gap:7px;color:#f5f7f8;font-weight:700;white-space:nowrap}
.v21-status i{font-style:normal;font-size:17px}
.v21-status.ok i{color:#25df86}.v21-status.low i{color:#ffc400}.v21-status.out i{color:#ff4d5f}
.v21-page-info{height:42px;display:flex;align-items:center;justify-content:center;color:#9eb0ba;font-size:12px}
.v21-page-info b{color:#fff}

/* Fuerza amarillo Maritex en Exportar Excel */
.stApp .main [data-testid="stDownloadButton"] button{
 background:#FFC400!important;background-color:#FFC400!important;color:#080808!important;
 border:1px solid #FFC400!important;border-radius:8px!important;font-weight:900!important;box-shadow:none!important
}
.stApp .main [data-testid="stDownloadButton"] button *{color:#080808!important;fill:#080808!important}
.stApp .main [data-testid="stDownloadButton"] button:hover{background:#FFD52A!important;background-color:#FFD52A!important;border-color:#FFD52A!important}


/* V23 · Estado sin icono duplicado */
.v21-status{
    display:inline-flex;
    align-items:center;
    gap:8px;
    color:#F5F7F8 !important;
    font-weight:700;
    white-space:nowrap;
}
.v21-status i{
    display:inline-block;
    width:10px;
    height:10px;
    min-width:10px;
    border-radius:999px;
    font-size:0 !important;
    line-height:0 !important;
}
.v21-status.ok i{background:#35D889 !important}
.v21-status.low i{background:#FFC400 !important}
.v21-status.out i{background:#FF4D5F !important}
.v21-status.incoming i{background:#5EA2FF !important}

</style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# RENDER
# ============================================================





def render(ctx):
    _inject_css()

    df = ctx.get("stock_df")
    inventory = _add_box_qty(ctx.get("stock_normalized"))
    consolidated = _add_box_qty(ctx.get("stock_consolidated"))
    meta = ctx.get("stock_meta") or {}

    if (
        df is None or df.empty
        or inventory is None or inventory.empty
        or consolidated is None or consolidated.empty
    ):
        st.info("No hay inventario disponible.")
        return

    summary = _build_summary(inventory, consolidated)
    unavailable = summary["zero"] + summary["negative"]
    total_states = max(
        summary["available"] + summary["low"] + summary["risk"]
        + unavailable + summary["incoming_sku"], 1
    )
    healthy_pct = summary["available"] / total_states * 100

    # ---------- HEADER ----------
    h1, h2 = st.columns([4.6, 1.4], gap="small")
    with h1:
        render_html(
            """
            <div class="sg17-title">Stock General</div>
            <div class="sg17-sub">
                Visión completa del inventario por bodega, familia, subfamilia y estado.
            </div>
            """
        )
    with h2:
        render_html(
            f"""
            <div class="sg17-date">
                <span>ÚLTIMA ACTUALIZACIÓN</span>
                <strong>{_friendly_datetime(meta.get("generatedAt") or meta.get("loaded_at"))}</strong>
            </div>
            """
        )
        if st.button(
            "↻  Actualizar datos",
            key="sg17_refresh",
            type="primary",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.rerun()

    # ---------- KPI ----------
    render_html(
        f"""
        <div class="sg17-kpis">
            <div class="sg17-kpi"><div class="sg17-kpi-icon y">⬡</div><div><span>SKU TOTALES</span><strong>{_fmt_int(summary["sku_total"])}</strong><small>Activos</small></div></div>
            <div class="sg17-kpi"><div class="sg17-kpi-icon n">▤</div><div><span>UNIDADES TOTALES</span><strong>{_fmt_int(summary["units_available"])}</strong><small>En inventario</small></div></div>
            <div class="sg17-kpi"><div class="sg17-kpi-icon g">✓</div><div><span>STOCK SALUDABLE</span><strong>{healthy_pct:.0f}%</strong><small>{_fmt_int(summary["available"])} SKU</small></div></div>
            <div class="sg17-kpi"><div class="sg17-kpi-icon y">△</div><div><span>STOCK BAJO</span><strong>{_fmt_int(summary["low"])}</strong><small>Requieren atención</small></div></div>
            <div class="sg17-kpi"><div class="sg17-kpi-icon r">×</div><div><span>SIN STOCK</span><strong>{_fmt_int(unavailable)}</strong><small>Sin disponibilidad</small></div></div>
        </div>
        """
    )

    # ---------- TOP GRID ----------
    wh = _warehouse_summary(inventory).head(8)
    total_wh = float(wh["Disponible"].sum()) if not wh.empty else 0
    max_wh = max(float(wh["Disponible"].max()), 1.0) if not wh.empty else 1.0
    wh_rows = ""
    for _, row in wh.iterrows():
        units = max(float(row["Disponible"]), 0)
        width = min(units / max_wh * 100, 100)
        share = units / total_wh * 100 if total_wh > 0 else 0
        wh_rows += f"""
        <div class="sg17-wh-row">
            <div class="sg17-wh-name">{escape(str(row["Bodega"]))}</div>
            <div class="sg17-wh-track"><div class="sg17-wh-fill" style="width:{width:.1f}%"></div></div>
            <div class="sg17-wh-val">{_fmt_int(units)} <span>({share:.0f}%)</span></div>
        </div>
        """

    render_html(
        f"""
        <div class="sg17-topgrid">
            <section class="sg17-panel">
                <div class="sg17-panel-title">Estado del Inventario</div>
                <div class="sg17-panel-sub">Distribución de SKU por condición de stock</div>
                <div class="sg17-health">
                    <div class="sg17-ring" style="--p:{healthy_pct:.1f}%">
                        <div><strong>{healthy_pct:.0f}%</strong><span>Saludable</span></div>
                    </div>
                    <div class="sg17-status">
                        <div class="sg17-status-row"><i class="g"></i><span>Saludable</span><b>{_fmt_int(summary["available"])}</b></div>
                        <div class="sg17-status-row"><i class="y"></i><span>Stock bajo</span><b>{_fmt_int(summary["low"])}</b></div>
                        <div class="sg17-status-row"><i class="o"></i><span>Riesgo</span><b>{_fmt_int(summary["risk"])}</b></div>
                        <div class="sg17-status-row"><i class="r"></i><span>Sin stock</span><b>{_fmt_int(unavailable)}</b></div>
                    </div>
                </div>
                <div class="sg17-ok">✓ El {healthy_pct:.0f}% de los SKU se encuentra en estado saludable.</div>
            </section>

            <section class="sg17-panel">
                <div class="sg17-panel-title">Distribución por Bodega</div>
                <div class="sg17-panel-sub">Stock disponible por ubicación</div>
                <div class="sg17-wh">{wh_rows}</div>
                <div class="sg17-wh-total"><span>Total unidades</span><strong>{_fmt_int(total_wh)} UND</strong></div>
            </section>

            <section class="sg17-panel">
                <div class="sg17-panel-title">Alertas y Oportunidades</div>
                <div class="sg17-panel-sub">Productos que requieren atención</div>
                <div class="sg17-alerts">
                    <div class="sg17-alert"><div class="sg17-alert-icon r">!</div><div><strong>Productos sin stock</strong><span>Sin disponibilidad actual</span></div><b>{_fmt_int(unavailable)}</b></div>
                    <div class="sg17-alert"><div class="sg17-alert-icon y">△</div><div><strong>Productos con stock bajo</strong><span>Requieren revisión</span></div><b>{_fmt_int(summary["low"])}</b></div>
                    <div class="sg17-alert"><div class="sg17-alert-icon b">↻</div><div><strong>Productos por llegar</strong><span>Stock informado en tránsito</span></div><b>{_fmt_int(summary["incoming_sku"])}</b></div>
                    <div class="sg17-alert"><div class="sg17-alert-icon g">⬡</div><div><strong>Bodegas activas</strong><span>Ubicaciones con inventario</span></div><b>{_fmt_int(summary["warehouses"])}</b></div>
                </div>
            </section>
        </div>
        """
    )

    # ---------- LOOKUP ----------
    render_html(
        """
        <div class="sg17-lookup-head">
            <strong>Consulta de producto por bodega</strong>
            <span>Selecciona un SKU y revisa su disponibilidad en todas las bodegas de Llegadas_OK.</span>
        </div>
        """
    )

    warehouses = _options(inventory, "Bodega")
    families = _options(inventory, "Familia")
    subfamilies = _options(inventory, "Subfamilia")

    l1, l2, l3, l4, l5 = st.columns([1.5, .8, .85, .9, .8], gap="small")

    with l1:
        product_options = _product_options(inventory)
        selected_product = st.selectbox(
            "Buscar producto (SKU o nombre)",
            ["Selecciona un producto"] + product_options,
            index=0,
            key="sg17_product",
        )
    with l2:
        lookup_wh = st.selectbox("Bodega", ["Todas"] + warehouses, key="sg17_lwh")
    with l3:
        lookup_family = st.selectbox("Familia", ["Todas"] + families, key="sg17_lfam", disabled=not bool(families))
    with l4:
        lookup_subfamily = st.selectbox("Subfamilia", ["Todas"] + subfamilies, key="sg17_lsub", disabled=not bool(subfamilies))
    with l5:
        lookup_status = st.selectbox(
            "Estado",
            ["Todos","Disponible","Stock bajo","Sin stock","Negativo","Riesgo despacho","Por llegar"],
            key="sg17_lstatus",
        )

    selected_sku = _sku_from_option(selected_product) if selected_product != "Selecciona un producto" else ""
    selected_rows = (
        inventory[
            inventory["Código"].fillna("").astype(str).str.strip().eq(selected_sku)
        ].copy()
        if selected_sku else pd.DataFrame()
    )

    selected_name = "—"
    selected_family = "—"
    selected_subfamily = "—"
    selected_box_qty = "—"
    selected_total = 0

    if not selected_rows.empty:
        selected_name = _clean_text(selected_rows["Producto"].iloc[0]) if "Producto" in selected_rows.columns else "—"
        selected_family = _clean_text(selected_rows["Familia"].iloc[0]) if "Familia" in selected_rows.columns else "—"
        selected_subfamily = _clean_text(selected_rows["Subfamilia"].iloc[0]) if "Subfamilia" in selected_rows.columns else "—"
        selected_box_qty = _clean_text(selected_rows["Cant. por caja"].iloc[0]) if "Cant. por caja" in selected_rows.columns else "—"
        selected_total = _safe_int(_series_num(selected_rows, "Disponible").clip(lower=0).sum())

    render_html(
        f"""
        <div class="sg17-lookup-body">
            <div class="sg17-productmeta">
                <div><span>SKU</span><strong>{escape(selected_sku or "—")}</strong></div>
                <div><span>PRODUCTO</span><strong>{escape(selected_name or "—")}</strong></div>
                <div><span>FAMILIA / SUBFAMILIA</span><strong>{escape(selected_family or "—")} / {escape(selected_subfamily or "—")}</strong></div>
                <div><span>CANT. POR CAJA</span><strong>{escape(selected_box_qty or "—")}</strong></div>
            </div>
        """
    )

    if selected_sku:
        product_detail = _selected_product_detail(inventory, selected_sku)
        stock_map = {}
        if not product_detail.empty:
            for _, r in product_detail.iterrows():
                stock_map[str(r.get("Bodega","")).strip().upper()] = max(0, _safe_int(r.get("Disponible", 0)))

        canonical = [
            ("CD", "CD"),
            ("CASA MATRIZ", "CASA MATRIZ"),
            ("PATRONATO", "PATRONATO"),
            ("CONCEPCION", "CONCEPCION"),
        ]
        max_stock = max([stock_map.get(k, 0) for k, _ in canonical] + [1])

        cards = ""
        for key, label in canonical:
            qty = stock_map.get(key, 0)
            pct = min(qty / max_stock * 100, 100)
            cards += f"""
            <div class="sg17-stockcard">
                <div class="top"><div class="ico">⬡</div><span>{label}</span></div>
                <strong>{_fmt_int(qty)}</strong><small>unidades</small>
                <div class="sg17-stockbar"><div class="sg17-stockfill" style="width:{pct:.1f}%"></div></div>
            </div>
            """

        cards += f"""
        <div class="sg17-stockcard total">
            <div class="top"><span>STOCK TOTAL DISPONIBLE</span></div>
            <strong>{_fmt_int(selected_total)}</strong><small>unidades</small>
        </div>
        """

        render_html(
            f"""
            <div class="sg17-stock-title">Stock por bodega</div>
            <div class="sg17-stockgrid">{cards}</div>
            </div>
            """
        )
    else:
        render_html("</div>")

    # ---------- LOWER ----------
    critical = _critical_products(consolidated, limit=5)
    rows = ""
    if not critical.empty:
        for _, row in critical.iterrows():
            rows += f"""
            <tr>
                <td>{escape(str(row["Código"]))}</td>
                <td>{escape(str(row["Producto"])[:52])}</td>
                <td>{_fmt_int(row["Disponible"])}</td>
                <td>{_fmt_int(row.get("Por llegar",0))}</td>
                <td><span class="sg17-badge">BAJO</span></td>
            </tr>
            """

    attention = summary["low"] + summary["risk"] + unavailable
    render_html(
        f"""
        <div class="sg17-lower">
            <section class="sg17-panel">
                <div class="sg17-panel-title">Productos Críticos</div>
                <div class="sg17-panel-sub">Productos que requieren atención inmediata</div>
                <table class="sg17-table">
                    <thead><tr><th>SKU</th><th>PRODUCTO</th><th>DISPONIBLE</th><th>POR LLEGAR</th><th>ESTADO</th></tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </section>
            <section class="sg17-panel">
                <div class="sg17-panel-title">Resumen Operacional</div>
                <div class="sg17-panel-sub">Indicadores de atención del inventario</div>
                <div class="sg17-summary">
                    <div class="sg17-summary-card a"><span>REQUIEREN ATENCIÓN</span><strong>{_fmt_int(attention)}</strong><b>△</b></div>
                    <div class="sg17-summary-card h"><span>SALUDABLES</span><strong>{_fmt_int(summary["available"])}</strong><b>✓</b></div>
                </div>
                <div class="sg17-note">
                    Stock General utiliza la disponibilidad informada por Llegadas_OK y mantiene el detalle separado por bodega.
                </div>
            </section>
        </div>
        """
    )

    # ---------- INVENTARIO COMPLETO ----------
    with st.expander("Ver inventario completo", expanded=False):
        st.caption("Filtra y consulta todo el inventario. Incluye cantidad por caja según SKU.")

        q1, q2, q3, q4, q5 = st.columns([1.45,.8,.8,.9,.8], gap="small")
        with q1:
            search = st.text_input("Buscar producto o SKU", key="sg17_search", placeholder="Ej: PARKA TAURUS, SIMOS, 100008...")
        with q2:
            warehouse = st.selectbox("Bodega", ["Todas"] + warehouses, key="sg17_wh")
        with q3:
            family = st.selectbox("Familia", ["Todas"] + families, key="sg17_fam", disabled=not bool(families))
        with q4:
            subfamily = st.selectbox("Subfamilia", ["Todas"] + subfamilies, key="sg17_sub", disabled=not bool(subfamilies))
        with q5:
            status = st.selectbox(
                "Estado",
                ["Todos","Disponible","Stock bajo","Sin stock","Negativo","Riesgo despacho","Por llegar"],
                key="sg17_status",
            )

        filtered = _filter_inventory(inventory, search, warehouse, family, subfamily, status)
        filtered_available = _safe_int(_series_num(filtered, "Disponible").clip(lower=0).sum())

        # V24 · columnas visibles de Inventario completo.
        # Deben definirse antes de construir la tabla HTML.
        visible_columns = [
            col
            for col in [
                "Código",
                "Producto",
                "Bodega",
                "Cant. por caja",
                "Disponible",
                "Por llegar",
                "Por despachar",
                "Estado",
            ]
            if col in filtered.columns
        ]

        i1, i2, ex = st.columns([1.4,1.3,.8], gap="small")
        with i1:
            st.caption(
                f"Resultados: {_fmt_int(len(filtered))} registros · "
                f"{_fmt_int(filtered['Código'].nunique() if 'Código' in filtered.columns else 0)} productos"
            )
        with i2:
            st.caption(f"Total disponible (filtrado): {_fmt_int(filtered_available)} UND")
        with ex:
            export_bytes = dataframe_to_excel_bytes(
                filtered,
                sheet_name="Stock_Filtrado",
            )
            st.download_button(
                label="↓  Exportar Excel",
                data=export_bytes,
                file_name="Stock_General_Filtrado.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="sg23_export_excel",
                type="primary",
                use_container_width=True,
            )


        # V21 · tabla HTML negra paginada.
        _table_df = filtered[visible_columns].copy()
        _page_size = 12
        _total_rows = len(_table_df)
        _total_pages = max(1, (_total_rows + _page_size - 1) // _page_size)
        _page_key = "stock_general_inventory_page_v21"

        if _page_key not in st.session_state:
            st.session_state[_page_key] = 1

        _page = min(max(1, int(st.session_state[_page_key])), _total_pages)
        st.session_state[_page_key] = _page
        _start_row = (_page - 1) * _page_size
        _page_df = _table_df.iloc[_start_row:_start_row + _page_size]

        import html as _html

        def _v21_text(value):
            if value is None:
                return "—"
            try:
                if pd.isna(value):
                    return "—"
            except Exception:
                pass
            return _html.escape(str(value))

        def _v21_number(value):
            try:
                number = float(value)
                if number.is_integer():
                    return f"{int(number):,}".replace(",", ".")
                return f"{number:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
            except Exception:
                return _v21_text(value)

        def _v21_state(value):
            text = str(value or "").strip()

            clean_text = re.sub(
                r"^[🟢🟡🔴🟠🔵]\s*",
                "",
                text,
            ).strip()

            low = clean_text.lower()

            if "sin stock" in low or "negativo" in low:
                css_class = "out"
            elif "bajo" in low or "riesgo" in low:
                css_class = "low"
            elif "por llegar" in low:
                css_class = "incoming"
            else:
                css_class = "ok"

            return (
                f'<span class="v21-status {css_class}">'
                f'<i></i>{_v21_text(clean_text or text)}'
                f'</span>'
            )

        _numeric_cols = {"Cant. por caja", "Disponible", "Stock físico", "Por llegar", "Por despachar"}

        _header_html = "".join(
            f'<th class="{"num" if col in _numeric_cols else ""}">{_v21_text(col)}</th>'
            for col in visible_columns
        )

        _body_rows = []
        for _, record in _page_df.iterrows():
            cells = []
            for col in visible_columns:
                value = record.get(col, "")
                if col == "Estado":
                    content = _v21_state(value)
                elif col in _numeric_cols:
                    content = _v21_number(value)
                else:
                    content = _v21_text(value)
                cls = "num" if col in _numeric_cols else ""
                cells.append(f'<td class="{cls}">{content}</td>')
            _body_rows.append("<tr>" + "".join(cells) + "</tr>")

        st.markdown(
            f"""
            <div class="v21-table-shell">
                <div class="v21-table-scroll">
                    <table class="v21-table">
                        <thead><tr>{_header_html}</tr></thead>
                        <tbody>{"".join(_body_rows)}</tbody>
                    </table>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        _prev_col, _page_col, _next_col = st.columns([1, 2, 1])
        with _prev_col:
            if st.button("← Anterior", key="v21_prev", disabled=_page <= 1, use_container_width=True):
                st.session_state[_page_key] = _page - 1
                st.rerun()

        with _page_col:
            _page_text = f"{_total_rows:,}".replace(",", ".")
            st.markdown(
                f'<div class="v21-page-info">Página <b>{_page}</b> de <b>{_total_pages}</b> · {_page_text} registros</div>',
                unsafe_allow_html=True,
            )

        with _next_col:
            if st.button("Siguiente →", key="v21_next", disabled=_page >= _total_pages, use_container_width=True):
                st.session_state[_page_key] = _page + 1
                st.rerun()

