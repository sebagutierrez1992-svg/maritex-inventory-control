from __future__ import annotations

from html import escape
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
    inventory = ctx.get(
        "stock_normalized"
    )
    consolidated = ctx.get(
        "stock_consolidated"
    )
    meta = ctx.get("stock_meta") or {}

    render_html(
        f"""
        <div class="sgx-head">
            <div>
                <div class="sgx-title">
                    STOCK GENERAL
                </div>
                <div class="sgx-subtitle">
                    Control consolidado de inventario
                </div>
            </div>

            <div class="sgx-update">
                <i></i>
                Última actualización:
                {_friendly_datetime(
                    meta.get(
                        "generatedAt"
                    )
                    or meta.get(
                        "loaded_at"
                    )
                )}
            </div>
        </div>
        """
    )

    if (
        df is None
        or df.empty
        or inventory is None
        or inventory.empty
        or consolidated is None
        or consolidated.empty
    ):
        st.info(
            "No hay inventario disponible."
        )
        return

    # --------------------------------------------------------
    # FILTROS SUPERIORES
    # --------------------------------------------------------

    warehouses = _options(
        inventory,
        "Bodega",
    )

    families = _options(
        inventory,
        "Familia",
    )

    subfamilies = _options(
        inventory,
        "Subfamilia",
    )

    f1, f2, f3, f4 = st.columns(
        [1.0, 1.0, 1.0, 1.0],
        gap="small",
    )

    with f1:
        warehouse = st.selectbox(
            "Bodega",
            ["Todas"] + warehouses,
            key="sgx_wh",
        )

    with f2:
        family = st.selectbox(
            "Familia",
            ["Todas"] + families,
            key="sgx_family",
            disabled=not bool(
                families
            ),
        )

    with f3:
        subfamily = st.selectbox(
            "Subfamilia",
            ["Todas"] + subfamilies,
            key="sgx_subfamily",
            disabled=not bool(
                subfamilies
            ),
        )

    with f4:
        status = st.selectbox(
            "Estado de stock",
            [
                "Todos",
                "Disponible",
                "Stock bajo",
                "Sin stock",
                "Negativo",
                "Riesgo despacho",
                "Por llegar",
            ],
            key="sgx_status",
        )

    # --------------------------------------------------------
    # BUSCADOR / PRODUCTO
    # --------------------------------------------------------

    with st.container(border=True):
        render_html(
            """
            <div class="sgx-search-head">
                <div>
                    <strong>
                        Consulta de producto por bodega
                    </strong>
                    <span>
                        Selecciona un SKU y revisa su disponibilidad
                        en todas las bodegas de Llegadas_OK.
                    </span>
                </div>
            </div>
            """
        )

        product_options = _product_options(
            inventory
        )

        selected_product = st.selectbox(
            "Buscar producto (SKU o nombre)",
            ["Selecciona un producto"] + product_options,
            index=0,
            key="sgx_product_select_simple",
            help=(
                "Escribe dentro del selector para buscar por SKU "
                "o por nombre del producto."
            ),
        )

        selected_sku = (
            _sku_from_option(
                selected_product
            )
            if selected_product
            != "Selecciona un producto"
            else ""
        )

        selected_rows = (
            inventory[
                inventory["Código"]
                .fillna("")
                .astype(str)
                .str.strip()
                .eq(selected_sku)
            ].copy()
            if selected_sku
            else pd.DataFrame()
        )

        selected_name = "—"
        selected_family = "—"
        selected_subfamily = "—"
        selected_total = 0

        if not selected_rows.empty:
            if "Producto" in selected_rows.columns:
                selected_name = _clean_text(
                    selected_rows[
                        "Producto"
                    ].iloc[0]
                ) or "—"

            if "Familia" in selected_rows.columns:
                selected_family = _clean_text(
                    selected_rows[
                        "Familia"
                    ].iloc[0]
                ) or "—"

            if "Subfamilia" in selected_rows.columns:
                selected_subfamily = _clean_text(
                    selected_rows[
                        "Subfamilia"
                    ].iloc[0]
                ) or "—"

            selected_total = _safe_int(
                _series_num(
                    selected_rows,
                    "Disponible",
                ).clip(
                    lower=0
                ).sum()
            )

        render_html(
            f"""
            <div class="sgx-product-meta">
                <div>
                    <span>SKU</span>
                    <strong>
                        {escape(
                            selected_sku
                            or "—"
                        )}
                    </strong>
                </div>
                <div>
                    <span>Producto</span>
                    <strong>
                        {escape(
                            selected_name
                        )}
                    </strong>
                </div>
                <div>
                    <span>Familia / Subfamilia</span>
                    <strong>
                        {escape(
                            selected_family
                        )}
                        /
                        {escape(
                            selected_subfamily
                        )}
                    </strong>
                </div>
                <div>
                    <span>Stock total disponible</span>
                    <strong>
                        {_fmt_int(
                            selected_total
                        )} UND
                    </strong>
                </div>
            </div>
            """
        )

        # La disponibilidad por bodega forma parte de la misma consulta.
        if selected_sku:
            product_detail = _selected_product_detail(
                inventory,
                selected_sku,
            )

            render_html(
                """
                <div style="
                    margin-top:16px;
                    padding-top:14px;
                    border-top:1px solid #edf0f2;
                ">
                    <div class="sgx-card-title">
                        Disponibilidad por Bodega
                    </div>
                    <div class="sgx-card-sub">
                        Consulta exacta del SKU seleccionado en Llegadas_OK
                    </div>
                </div>
                """
            )

            if product_detail.empty:
                st.info(
                    "El producto no tiene detalle por bodega."
                )
            else:
                # Mostramos primero bodegas con stock y luego las que están en 0.
                if "Disponible" in product_detail.columns:
                    product_detail = product_detail.sort_values(
                        ["Disponible", "Bodega"],
                        ascending=[False, True],
                    ).reset_index(drop=True)

                st.dataframe(
                    product_detail,
                    hide_index=True,
                    width="stretch",
                    height=min(
                        300,
                        44 + len(product_detail) * 35,
                    ),
                    column_config={
                        "Bodega": st.column_config.TextColumn(
                            "Bodega",
                            width="large",
                        ),
                        "Stock físico": st.column_config.NumberColumn(
                            "Stock físico",
                            format="%d",
                        ),
                        "Disponible": st.column_config.NumberColumn(
                            "Disponible",
                            format="%d",
                        ),
                        "Por llegar": st.column_config.NumberColumn(
                            "Por llegar",
                            format="%d",
                        ),
                        "Por despachar": st.column_config.NumberColumn(
                            "Por despachar",
                            format="%d",
                        ),
                        "Estado": st.column_config.TextColumn(
                            "Estado",
                            width="medium",
                        ),
                    },
                )

    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------

    summary = _build_summary(
        inventory,
        consolidated,
    )

    unavailable = (
        summary["zero"]
        + summary["negative"]
    )

    total_states = max(
        summary["available"]
        + summary["low"]
        + summary["risk"]
        + unavailable
        + summary["incoming_sku"],
        1,
    )

    healthy_pct = (
        summary["available"]
        / total_states
        * 100
    )

    kpis = "".join(
        [
            _kpi_card(
                "SKU Totales",
                _fmt_int(
                    summary[
                        "sku_total"
                    ]
                ),
                "Activos",
                "◇",
                "neutral",
            ),
            _kpi_card(
                "Unidades Totales",
                _fmt_int(
                    summary[
                        "units_available"
                    ]
                ),
                "En inventario",
                "▤",
                "neutral",
            ),
            _kpi_card(
                "Stock Saludable",
                f"{healthy_pct:.0f}%",
                (
                    f"{_fmt_int(summary['available'])} SKU"
                ),
                "✓",
                "green",
            ),
            _kpi_card(
                "Stock Bajo",
                _fmt_int(
                    summary["low"]
                ),
                "Requieren atención",
                "△",
                "yellow",
            ),
            _kpi_card(
                "Sin Stock",
                _fmt_int(
                    unavailable
                ),
                "Sin disponibilidad",
                "×",
                "red",
            ),
        ]
    )

    render_html(
        f"""
        <div class="sgx-kpis">
            {kpis}
        </div>
        """
    )

    # --------------------------------------------------------
    # MAIN CARDS
    # --------------------------------------------------------

    c1, c2, c3 = st.columns(
        [1.0, 1.15, 1.15],
        gap="medium",
    )

    with c1:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="sgx-card-title">
                    Estado del Inventario
                </div>
                <div class="sgx-card-sub">
                    Resumen por condición de stock
                </div>
                """
            )

            render_html(
                f"""
                <div class="sgx-health">
                    <div
                        class="sgx-ring"
                        style="--p:{healthy_pct:.1f}%"
                    >
                        <div>
                            <strong>
                                {healthy_pct:.0f}%
                            </strong>
                            <span>
                                Saludable
                            </span>
                        </div>
                    </div>

                    <div class="sgx-status">
                        <div class="sgx-status-row">
                            <i class="green"></i>
                            <span>Saludable</span>
                            <strong>
                                {_fmt_int(
                                    summary[
                                        "available"
                                    ]
                                )}
                            </strong>
                        </div>

                        <div class="sgx-status-row">
                            <i class="yellow"></i>
                            <span>Stock bajo</span>
                            <strong>
                                {_fmt_int(
                                    summary[
                                        "low"
                                    ]
                                )}
                            </strong>
                        </div>

                        <div class="sgx-status-row">
                            <i class="orange"></i>
                            <span>Riesgo</span>
                            <strong>
                                {_fmt_int(
                                    summary[
                                        "risk"
                                    ]
                                )}
                            </strong>
                        </div>

                        <div class="sgx-status-row">
                            <i class="red"></i>
                            <span>Sin stock</span>
                            <strong>
                                {_fmt_int(
                                    unavailable
                                )}
                            </strong>
                        </div>
                    </div>
                </div>

                <div class="sgx-healthy-note">
                    El {healthy_pct:.0f}% de los SKU
                    se encuentra en estado saludable.
                </div>
                """
            )

    with c2:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="sgx-card-title">
                    Distribución por Bodega
                </div>
                <div class="sgx-card-sub">
                    Stock disponible por ubicación
                </div>
                """
            )

            wh = _warehouse_summary(
                inventory
            ).head(8)

            if wh.empty:
                st.info(
                    "No hay información de bodegas."
                )
            else:
                total_wh = float(
                    wh["Disponible"].sum()
                )
                max_wh = max(
                    float(
                        wh[
                            "Disponible"
                        ].max()
                    ),
                    1.0,
                )

                rows = ""

                for _, row in wh.iterrows():
                    units = max(
                        float(
                            row[
                                "Disponible"
                            ]
                        ),
                        0,
                    )
                    width = min(
                        units
                        / max_wh
                        * 100,
                        100,
                    )
                    share = (
                        units
                        / total_wh
                        * 100
                        if total_wh > 0
                        else 0
                    )

                    rows += f"""
                    <div class="sgx-wh-row">
                        <div class="sgx-wh-name">
                            {escape(
                                str(
                                    row[
                                        "Bodega"
                                    ]
                                )
                            )}
                        </div>
                        <div class="sgx-wh-track">
                            <div
                                class="sgx-wh-fill"
                                style="width:{width:.1f}%"
                            ></div>
                        </div>
                        <div class="sgx-wh-value">
                            {_fmt_int(units)}
                            <span style="
                                color:#9aa2aa;
                                font-weight:500;
                            ">
                                ({share:.0f}%)
                            </span>
                        </div>
                    </div>
                    """

                render_html(
                    f"""
                    <div class="sgx-wh-list">
                        {rows}
                    </div>
                    <div class="sgx-wh-total">
                        <span>Total unidades</span>
                        <strong>
                            {_fmt_int(
                                total_wh
                            )} UND
                        </strong>
                    </div>
                    """
                )

    with c3:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="sgx-card-title">
                    Alertas y Oportunidades
                </div>
                <div class="sgx-card-sub">
                    Prioridades operacionales
                </div>
                """
            )

            render_html(
                f"""
                <div class="sgx-alert-list">
                    <div class="sgx-alert-row">
                        <div class="sgx-alert-icon red">!</div>
                        <div>
                            <strong>
                                Productos sin stock
                            </strong>
                            <span>
                                Sin disponibilidad actual
                            </span>
                        </div>
                        <div class="sgx-alert-value">
                            {_fmt_int(
                                unavailable
                            )}
                        </div>
                    </div>

                    <div class="sgx-alert-row">
                        <div class="sgx-alert-icon yellow">△</div>
                        <div>
                            <strong>
                                Productos con stock bajo
                            </strong>
                            <span>
                                Requieren revisión
                            </span>
                        </div>
                        <div class="sgx-alert-value">
                            {_fmt_int(
                                summary[
                                    "low"
                                ]
                            )}
                        </div>
                    </div>

                    <div class="sgx-alert-row">
                        <div class="sgx-alert-icon blue">↻</div>
                        <div>
                            <strong>
                                Productos por llegar
                            </strong>
                            <span>
                                Stock informado en tránsito
                            </span>
                        </div>
                        <div class="sgx-alert-value">
                            {_fmt_int(
                                summary[
                                    "incoming_sku"
                                ]
                            )}
                        </div>
                    </div>

                    <div class="sgx-alert-row">
                        <div class="sgx-alert-icon green">✓</div>
                        <div>
                            <strong>
                                Bodegas activas
                            </strong>
                            <span>
                                Ubicaciones con inventario
                            </span>
                        </div>
                        <div class="sgx-alert-value">
                            {_fmt_int(
                                summary[
                                    "warehouses"
                                ]
                            )}
                        </div>
                    </div>
                </div>
                """
            )

    # --------------------------------------------------------
    # CRÍTICOS
    # --------------------------------------------------------

    lower_left, lower_right = st.columns(
        [1.7, 1.0],
        gap="medium",
    )

    with lower_left:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="sgx-card-title">
                    Productos Críticos
                </div>
                <div class="sgx-card-sub">
                    Productos que requieren atención inmediata
                </div>
                """
            )

            critical = _critical_products(
                consolidated,
                limit=6,
            )

            if critical.empty:
                st.success(
                    "No hay productos críticos."
                )
            else:
                rows = ""

                for _, row in critical.iterrows():
                    state = str(
                        row.get(
                            "Estado",
                            "",
                        )
                    )
                    low_state = state.lower()

                    if (
                        "sin stock"
                        in low_state
                        or "negativo"
                        in low_state
                    ):
                        badge_class = "red"
                        badge_text = "SIN STOCK"
                    elif (
                        "riesgo"
                        in low_state
                    ):
                        badge_class = (
                            "orange"
                        )
                        badge_text = "RIESGO"
                    else:
                        badge_class = (
                            "yellow"
                        )
                        badge_text = "BAJO"

                    rows += f"""
                    <tr>
                        <td>
                            {escape(
                                str(
                                    row[
                                        "Código"
                                    ]
                                )
                            )}
                        </td>
                        <td>
                            {escape(
                                str(
                                    row[
                                        "Producto"
                                    ]
                                )[:48]
                            )}
                        </td>
                        <td style="text-align:right">
                            {_fmt_int(
                                row[
                                    "Disponible"
                                ]
                            )}
                        </td>
                        <td style="text-align:right">
                            {_fmt_int(
                                row.get(
                                    "Por llegar",
                                    0,
                                )
                            )}
                        </td>
                        <td>
                            <span class="sgx-badge {badge_class}">
                                {badge_text}
                            </span>
                        </td>
                    </tr>
                    """

                render_html(
                    f"""
                    <table class="sgx-critical-table">
                        <thead>
                            <tr>
                                <th>SKU</th>
                                <th>Producto</th>
                                <th style="text-align:right">
                                    Disponible
                                </th>
                                <th style="text-align:right">
                                    Por llegar
                                </th>
                                <th>Estado</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows}
                        </tbody>
                    </table>
                    """
                )

    with lower_right:
        with st.container(
            border=True
        ):
            render_html(
                """
                <div class="sgx-card-title">
                    Resumen Operacional
                </div>
                <div class="sgx-card-sub">
                    Indicadores de atención del inventario
                </div>
                """
            )

            attention = (
                unavailable
                + summary["low"]
                + summary["risk"]
            )

            render_html(
                f"""
                <div style="
                    display:grid;
                    grid-template-columns:1fr 1fr;
                    gap:9px;
                    margin-top:12px;
                ">
                    <div style="
                        padding:12px;
                        border:1px solid #edf0f2;
                        border-radius:9px;
                        background:#fafbfc;
                    ">
                        <span style="
                            color:#929aa2;
                            font-size:8px;
                            text-transform:uppercase;
                        ">
                            Requieren atención
                        </span>
                        <strong style="
                            display:block;
                            margin-top:4px;
                            color:#1c2329;
                            font-size:21px;
                        ">
                            {_fmt_int(
                                attention
                            )}
                        </strong>
                    </div>

                    <div style="
                        padding:12px;
                        border:1px solid #edf0f2;
                        border-radius:9px;
                        background:#fafbfc;
                    ">
                        <span style="
                            color:#929aa2;
                            font-size:8px;
                            text-transform:uppercase;
                        ">
                            Saludables
                        </span>
                        <strong style="
                            display:block;
                            margin-top:4px;
                            color:#1c2329;
                            font-size:21px;
                        ">
                            {_fmt_int(
                                summary[
                                    "available"
                                ]
                            )}
                        </strong>
                    </div>
                </div>

                <div class="sgx-detail-note"
                     style="margin-top:12px;">
                    Stock General utiliza la disponibilidad
                    informada por Llegadas_OK y mantiene el
                    detalle separado por bodega.
                </div>
                """
            )

    # --------------------------------------------------------
    # INVENTARIO COMPLETO · COMPACTO
    # --------------------------------------------------------

    with st.expander(
        "Ver inventario completo",
        expanded=False,
    ):
        render_html(
            """
            <div class="sgx-card-sub" style="margin-bottom:8px;">
                La tabla respeta los filtros superiores de bodega,
                familia, subfamilia y estado.
            </div>
            """
        )

        search_col, table_info_col = st.columns(
            [1.55, 2.45],
            gap="small",
        )

        with search_col:
            inventory_product_query = st.text_input(
                "Filtrar por producto o SKU",
                placeholder=(
                    "Ej: PARKA TAURUS, SIMOS, 100008..."
                ),
                key="sgx_inventory_product_query",
                help=(
                    "Escribe parte del nombre del producto o del SKU. "
                    "La tabla mostrará todas las coincidencias, incluyendo "
                    "sus distintas tallas y bodegas."
                ),
            )

        with table_info_col:
            render_html(
                """
                <div style="
                    padding:8px 2px 0 2px;
                    color:#9099a2;
                    font-size:9.5px;
                ">
                    Busca por modelo o nombre para ver juntas todas sus tallas.
                    También puedes escribir un SKU completo o parcial.
                </div>
                """
            )

        filtered = _filter_inventory(
            inventory,
            inventory_product_query,
            warehouse,
            family,
            subfamily,
            status,
        )

        display = filtered.copy()

        for col in [
            "Stock físico",
            "Disponible",
            "Por llegar",
            "Por despachar",
            "Precio",
        ]:
            if col in display.columns:
                display[col] = (
                    pd.to_numeric(
                        display[col],
                        errors="coerce",
                    )
                    .fillna(0)
                    .round()
                    .astype("Int64")
                )

        result_products = (
            int(
                display["Código"].nunique()
            )
            if (
                not display.empty
                and "Código" in display.columns
            )
            else 0
        )

        result_available = (
            _safe_int(
                _series_num(
                    display,
                    "Disponible",
                ).sum()
            )
            if not display.empty
            else 0
        )

        summary_col, export_col = st.columns(
            [4.2, 1.1],
            gap="small",
        )

        with summary_col:
            render_html(
                f"""
                <div class="sgx-result">
                    <div>
                        <span>Resultados</span>
                        <strong>
                            {_fmt_int(len(display))}
                            registros ·
                            {_fmt_int(result_products)}
                            productos
                        </strong>
                    </div>
                    <div>
                        <span>Disponible filtrado</span>
                        <strong>
                            {_fmt_int(result_available)} UND
                        </strong>
                    </div>
                </div>
                """
            )

        with export_col:
            export_signature = (
                warehouse,
                family,
                subfamily,
                status,
                inventory_product_query,
                len(display),
                result_products,
                result_available,
            )

            if (
                st.session_state.get(
                    "sgx_export_signature_simple"
                )
                != export_signature
            ):
                st.session_state.pop(
                    "sgx_export_bytes_simple",
                    None,
                )
                st.session_state[
                    "sgx_export_signature_simple"
                ] = export_signature

            if st.button(
                "Preparar Excel",
                key="sgx_prepare_export_simple",
                width="stretch",
            ):
                with st.spinner(
                    "Preparando Excel..."
                ):
                    st.session_state[
                        "sgx_export_bytes_simple"
                    ] = dataframe_to_excel_bytes(
                        display,
                        sheet_name="Stock_Filtrado",
                    )

            export_bytes = st.session_state.get(
                "sgx_export_bytes_simple"
            )

            if export_bytes:
                st.download_button(
                    "⬇ Descargar",
                    data=export_bytes,
                    file_name="Stock_General_Filtrado.xlsx",
                    mime=(
                        "application/"
                        "vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    key="sgx_download_simple",
                    width="stretch",
                )

        visible_columns = [
            col
            for col in [
                "Código",
                "Producto",
                "Bodega",
                "Disponible",
                "Stock físico",
                "Por llegar",
                "Por despachar",
                "Estado",
            ]
            if col in display.columns
        ]

        st.dataframe(
            display[visible_columns],
            hide_index=True,
            width="stretch",
            height=470,
            column_config={
                "Código": st.column_config.TextColumn(
                    "SKU",
                    width="medium",
                ),
                "Producto": st.column_config.TextColumn(
                    "Producto",
                    width="large",
                ),
                "Bodega": st.column_config.TextColumn(
                    "Bodega",
                    width="medium",
                ),
                "Stock físico": st.column_config.NumberColumn(
                    "Stock físico",
                    format="%d",
                ),
                "Disponible": st.column_config.NumberColumn(
                    "Disponible",
                    format="%d",
                ),
                "Por llegar": st.column_config.NumberColumn(
                    "Por llegar",
                    format="%d",
                ),
                "Por despachar": st.column_config.NumberColumn(
                    "Por despachar",
                    format="%d",
                ),
                "Estado": st.column_config.TextColumn(
                    "Estado",
                    width="medium",
                ),
            },
        )
