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



def _status_badge(value: object) -> str:
    text = _clean_text(value)
    low = text.lower()

    if "disponible" in low:
        tone = "green"
        label = "DISPONIBLE"
    elif "stock bajo" in low:
        tone = "yellow"
        label = "STOCK BAJO"
    elif "riesgo" in low:
        tone = "orange"
        label = "RIESGO"
    elif "sin stock" in low or "negativo" in low:
        tone = "red"
        label = "SIN STOCK" if "sin stock" in low else "NEGATIVO"
    elif "por llegar" in low:
        tone = "blue"
        label = "POR LLEGAR"
    else:
        tone = "neutral"
        label = text or "—"

    return (
        f'<span class="sgx-badge {tone}">'
        f'{escape(label)}'
        f'</span>'
    )


def _inventory_table_html(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    max_rows: int | None = None,
) -> str:
    """Tabla HTML negra para evitar el fondo azul nativo de Streamlit."""
    if df is None or df.empty:
        return '<div class="sgx-empty-table">Sin registros para mostrar.</div>'

    work = df.copy()

    if columns:
        visible = [column for column in columns if column in work.columns]
        work = work[visible]

    if max_rows is not None:
        work = work.head(max_rows)

    numeric_columns = {
        "Stock físico",
        "Disponible",
        "Por llegar",
        "Por despachar",
        "Precio",
    }

    header_map = {
        "Código": "SKU",
    }

    head = "".join(
        f'<th class="{"num" if column in numeric_columns else ""}">'
        f'{escape(header_map.get(column, column))}'
        f'</th>'
        for column in work.columns
    )

    body_rows = []
    for _, row in work.iterrows():
        cells = []
        for column in work.columns:
            value = row.get(column, "")

            if column == "Estado":
                cell = _status_badge(value)
                cells.append(f'<td>{cell}</td>')
                continue

            if column in numeric_columns:
                display = _fmt_int(value)
                cells.append(f'<td class="num">{escape(display)}</td>')
                continue

            display = _clean_text(value) or "—"
            cells.append(f'<td>{escape(display)}</td>')

        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return (
        '<div class="sgx-table-wrap">'
        '<table class="sgx-data-table">'
        f'<thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body_rows)}</tbody>'
        '</table>'
        '</div>'
    )


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
            color:#F7F8FA;
            font-size:28px;
            font-weight:850;
            letter-spacing:-.8px;
            line-height:1;
        }

        .sgx-subtitle {
            margin-top:7px;
            font-size:12px;
            color:#9FB0C0;
        }

        .sgx-update {
            display:flex;
            align-items:center;
            gap:8px;
            white-space:nowrap;
            font-size:11px;
            color:#8FA2B4;
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
            color:#8FA2B4;
            letter-spacing:.42px;
            text-transform:uppercase;
            margin-bottom:2px;
        }

        .sgx-search-card {
            background:#17232D;
            border:1px solid #34414D;
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
            color:#F7F8FA;
            font-size:12px;
        }

        .sgx-search-head span {
            display:block;
            margin-top:2px;
            color:#91A3B5;
            font-size:9.5px;
        }

        .sgx-product-meta {
            display:grid;
            grid-template-columns:repeat(4,minmax(0,1fr));
            gap:8px;
            margin-top:8px;
        }

        .sgx-product-meta > div {
            background:#111C25;
            border:1px solid #2C3A46;
            border-radius:8px;
            padding:8px 10px;
        }

        .sgx-product-meta span {
            display:block;
            color:#8FA2B4;
            font-size:8px;
            text-transform:uppercase;
            letter-spacing:.35px;
        }

        .sgx-product-meta strong {
            display:block;
            margin-top:3px;
            color:#F7F8FA;
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
            border:1px solid #34414D;
            border-radius:12px;
            background:#17232D;
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
            background:#24323D;
            color:#C4D0DA;
        }

        .sgx-kpi-icon.green {
            background:#173A2A;
            color:#2d9f4a;
        }

        .sgx-kpi-icon.yellow {
            background:#17232D6d8;
            color:#dea300;
        }

        .sgx-kpi-icon.red {
            background:#17232D0ed;
            color:#df5147;
        }

        .sgx-kpi-copy {
            min-width:0;
        }

        .sgx-kpi-copy > span {
            display:block;
            color:#AFC0CF;
            font-size:10px;
            font-weight:650;
        }

        .sgx-kpi-copy > strong {
            display:block;
            color:#FFFFFF;
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
            color:#8FA2B4;
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
            border-color:#34414D !important;
            border-radius:12px !important;
            background:#17232D !important;
            box-shadow:0 3px 12px rgba(20,30,45,.025);
        }

        .sgx-card-title {
            font-size:12.5px;
            font-weight:820;
            color:#F7F8FA;
        }

        .sgx-card-sub {
            color:#91A3B5;
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
                radial-gradient(circle at center,#17232D 57%,transparent 58%),
                conic-gradient(#8fc267 var(--p),#ffc400 var(--p),#2A3742 0);
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
            color:#FFFFFF;
            font-weight:880;
            line-height:1;
        }

        .sgx-ring span {
            display:block;
            color:#9FB0C0;
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
            color:#AFC0CF;
        }

        .sgx-status-row strong {
            color:#F7F8FA;
            font-size:10px;
        }

        .sgx-healthy-note {
            margin-top:14px;
            padding:9px 10px;
            border-radius:7px;
            background:#183326;
            color:#7EDB91;
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
            color:#AFC0CF;
            font-size:9.8px;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }

        .sgx-wh-track {
            height:13px;
            border-radius:999px;
            background:#24323D;
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
            color:#F7F8FA;
            font-weight:780;
        }

        .sgx-wh-total {
            display:flex;
            justify-content:space-between;
            gap:10px;
            margin-top:15px;
            padding:9px 10px;
            border-radius:7px;
            border:1px solid #2C3A46;
            background:#111C25;
            font-size:9.2px;
            color:#91A3B5;
        }

        .sgx-wh-total strong {
            color:#F7F8FA;
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
            border-bottom:1px solid #2C3A46;
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
            background:#17232D0ed;
            color:#e35348;
        }

        .sgx-alert-icon.yellow {
            background:#17232D7dc;
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
            color:#F7F8FA;
        }

        .sgx-alert-row span {
            display:block;
            margin-top:2px;
            font-size:8.7px;
            color:#8FA2B4;
        }

        .sgx-alert-value {
            font-size:9.5px;
            color:#AFC0CF;
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
            color:#9FB0C0;
            font-size:8.5px;
            text-transform:uppercase;
            letter-spacing:.25px;
            border-bottom:1px solid #34414D;
        }

        .sgx-critical-table td,
        .sgx-product-table td {
            padding:9px;
            color:#EAF0F5;
            border-bottom:1px solid #2C3A46;
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
            background:#17232D0bf;
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
            color:#8FA2B4;
            font-size:8.5px;
            text-transform:uppercase;
            letter-spacing:.35px;
        }

        .sgx-detail-hero strong {
            display:block;
            color:#F7F8FA;
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
            background:#17232D9e8;
            border:1px solid #66571D;
            border-radius:9px;
            font-size:9px;
            color:#E6D88D;
            line-height:1.5;
        }

        .sgx-section-head {
            margin-top:8px;
            margin-bottom:2px;
        }

        .sgx-section-head strong {
            display:block;
            font-size:13px;
            color:#F7F8FA;
        }

        .sgx-section-head span {
            display:block;
            margin-top:2px;
            font-size:9.5px;
            color:#91A3B5;
        }

        .sgx-result {
            display:flex;
            justify-content:space-between;
            gap:12px;
            padding:10px 12px;
            background:#111C25;
            border:1px solid #2C3A46;
            border-radius:9px;
        }

        .sgx-result span {
            display:block;
            font-size:8px;
            color:#8FA2B4;
            text-transform:uppercase;
            letter-spacing:.35px;
        }

        .sgx-result strong {
            display:block;
            margin-top:3px;
            font-size:10.5px;
            color:#F7F8FA;
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

        /* MARITEX · STOCK GENERAL DARK CORPORATIVO */
        .sgx-title, .sgx-card-title, .sgx-section-head strong { color:#F7F8FA !important; }
        .sgx-subtitle, .sgx-card-sub, .sgx-update { color:#9FB0C0 !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] { background:#111C25 !important; border-color:#34414D !important; box-shadow:none !important; }
        div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, .stTextInput input { background:#17232D !important; color:#F7F8FA !important; border-color:#34414D !important; }
        div[data-baseweb="select"] *, .stTextInput input, label, .stMarkdown, .stCaption { color:#F7F8FA; }
        [data-testid="stDataFrame"] { border:1px solid #34414D; border-radius:10px; overflow:hidden; }
        .sgx-ring { background:radial-gradient(circle at center,#17232D 57%,transparent 58%),conic-gradient(#8fc267 var(--p),#ffc400 var(--p),#2A3742 0) !important; }
        .sgx-wh-track { background:#2A3742 !important; }
        .sgx-wh-total, .sgx-result { background:#111C25 !important; border-color:#34414D !important; }
        .sgx-critical-table th,.sgx-product-table th,.sgx-critical-table td,.sgx-product-table td { border-color:#34414D !important; }
        
        /* ============================================================
           STOCK GENERAL · MOCKUP NEGRO MARITEX
           ============================================================ */
        :root{
            --sgx-bg:#000000;
            --sgx-panel:#080808;
            --sgx-panel-2:#0D0D0D;
            --sgx-line:#2A2A2A;
            --sgx-line-2:#383838;
            --sgx-text:#FFFFFF;
            --sgx-muted:#9A9A9A;
            --sgx-yellow:#FFC400;
        }

        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section.main{
            background:#000000 !important;
        }

        [data-testid="stHeader"]{
            background:rgba(0,0,0,.96) !important;
        }

        section[data-testid="stSidebar"]{
            background:#050505 !important;
            border-right:1px solid #202020 !important;
        }

        .sgx-head{
            padding:4px 2px 12px !important;
            border-bottom:1px solid #1E1E1E;
        }

        .sgx-title{
            color:#FFFFFF !important;
            font-size:30px !important;
        }

        .sgx-title::before{
            content:"";
            display:inline-block;
            width:4px;
            height:29px;
            margin-right:10px;
            border-radius:3px;
            background:#FFC400;
            vertical-align:-5px;
        }

        .sgx-subtitle,
        .sgx-update,
        .sgx-card-sub,
        .sgx-section-head span{
            color:#8E8E8E !important;
        }

        .sgx-search-card,
        .sgx-kpi,
        div[data-testid="stVerticalBlockBorderWrapper"],
        .sgx-product-meta > div,
        .sgx-wh-total,
        .sgx-result,
        .sgx-detail-note{
            background:#080808 !important;
            border-color:#2C2C2C !important;
            box-shadow:none !important;
        }

        .sgx-kpi{
            position:relative;
            border-radius:10px !important;
            overflow:hidden;
        }

        .sgx-kpi::before{
            content:"";
            position:absolute;
            left:0;
            top:0;
            bottom:0;
            width:3px;
            background:#FFC400;
        }

        .sgx-kpi-copy > span{
            color:#B8B8B8 !important;
        }

        .sgx-kpi-copy > strong,
        .sgx-card-title,
        .sgx-section-head strong,
        .sgx-product-meta strong,
        .sgx-wh-value,
        .sgx-alert-row strong{
            color:#FFFFFF !important;
        }

        .sgx-kpi-icon.neutral{
            background:#151515 !important;
            color:#D6D6D6 !important;
        }

        .sgx-kpi-icon.green{
            background:#082617 !important;
            color:#26D77A !important;
        }

        .sgx-kpi-icon.yellow{
            background:#312700 !important;
            color:#FFC400 !important;
        }

        .sgx-kpi-icon.red{
            background:#2F1010 !important;
            color:#FF6660 !important;
        }

        .sgx-ring{
            background:
                radial-gradient(circle at center,#080808 57%,transparent 58%),
                conic-gradient(#27D17C var(--p),#FFC400 var(--p),#242424 0) !important;
        }

        .sgx-wh-track{
            background:#202020 !important;
        }

        .sgx-wh-fill{
            background:#FFC400 !important;
        }

        .sgx-healthy-note{
            background:#071A10 !important;
            color:#72DCA2 !important;
            border:1px solid #123D28;
        }

        .sgx-alert-row{
            border-color:#242424 !important;
        }

        .sgx-alert-icon.red{
            background:#2C1010 !important;
            color:#FF716A !important;
        }

        .sgx-alert-icon.yellow{
            background:#302600 !important;
            color:#FFC400 !important;
        }

        .sgx-alert-icon.blue{
            background:#0C2030 !important;
            color:#66B7FF !important;
        }

        .sgx-alert-icon.green{
            background:#082617 !important;
            color:#45DC8E !important;
        }

        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        .stTextInput input,
        input{
            background:#090909 !important;
            color:#FFFFFF !important;
            border-color:#333333 !important;
        }

        div[data-baseweb="popover"],
        div[data-baseweb="menu"]{
            background:#090909 !important;
        }

        div[data-baseweb="menu"] li{
            background:#090909 !important;
            color:#FFFFFF !important;
        }

        div[data-baseweb="menu"] li:hover{
            background:#171717 !important;
        }

        details,
        details > summary{
            background:#070707 !important;
            border-color:#2A2A2A !important;
            color:#FFFFFF !important;
        }

        .stButton > button,
        .stDownloadButton > button{
            background:#0A0A0A !important;
            border:1px solid #333333 !important;
            color:#FFFFFF !important;
        }

        .stButton > button:hover,
        .stDownloadButton > button:hover{
            border-color:#FFC400 !important;
            color:#FFC400 !important;
        }

        .stDownloadButton > button[kind="primary"],
        .stButton > button[kind="primary"]{
            background:#FFC400 !important;
            border-color:#FFC400 !important;
            color:#111111 !important;
        }

        .sgx-badge.green{
            background:#082617 !important;
            color:#55E59A !important;
            border:1px solid #174A30;
        }

        .sgx-badge.yellow{
            background:#302600 !important;
            color:#FFD23F !important;
            border:1px solid #665300;
        }

        .sgx-badge.orange{
            background:#321C0B !important;
            color:#FFAD6A !important;
            border:1px solid #633A18;
        }

        .sgx-badge.red{
            background:#2C1010 !important;
            color:#FF8B86 !important;
            border:1px solid #5A2424;
        }

        .sgx-badge.blue{
            background:#0C2030 !important;
            color:#79C2FF !important;
            border:1px solid #19425E;
        }

        .sgx-badge.neutral{
            background:#151515 !important;
            color:#CFCFCF !important;
            border:1px solid #353535;
        }

        .sgx-table-wrap{
            width:100%;
            overflow:auto;
            margin-top:10px;
            border:1px solid #292929;
            border-radius:10px;
            background:#050505;
            max-height:470px;
        }

        .sgx-data-table{
            width:100%;
            border-collapse:separate;
            border-spacing:0;
            min-width:820px;
            font-size:10px;
        }

        .sgx-data-table thead th{
            position:sticky;
            top:0;
            z-index:2;
            background:#101010;
            color:#A9A9A9;
            text-align:left;
            font-size:8.5px;
            font-weight:800;
            text-transform:uppercase;
            letter-spacing:.04em;
            padding:10px 11px;
            border-bottom:1px solid #333333;
            white-space:nowrap;
        }

        .sgx-data-table tbody td{
            color:#F2F2F2;
            padding:9px 11px;
            border-bottom:1px solid #202020;
            background:#070707;
            white-space:nowrap;
        }

        .sgx-data-table tbody tr:nth-child(even) td{
            background:#0B0B0B;
        }

        .sgx-data-table tbody tr:hover td{
            background:#121212;
        }

        .sgx-data-table tbody tr:last-child td{
            border-bottom:none;
        }

        .sgx-data-table .num{
            text-align:right;
            font-variant-numeric:tabular-nums;
        }

        .sgx-empty-table{
            margin-top:10px;
            padding:20px;
            border:1px dashed #303030;
            border-radius:9px;
            color:#888888;
            background:#060606;
            text-align:center;
            font-size:10px;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"],
        section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]{
            background:#FFC400 !important;
            color:#080808 !important;
            border-color:#FFC400 !important;
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
                    border-top:1px solid #2C3A46;
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

                render_html(
                    _inventory_table_html(
                        product_detail,
                        columns=[
                            "Bodega",
                            "Stock físico",
                            "Disponible",
                            "Por llegar",
                            "Por despachar",
                            "Estado",
                        ],
                    )
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
                                color:#8FA2B4;
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
                        border:1px solid #2C3A46;
                        border-radius:9px;
                        background:#111C25;
                    ">
                        <span style="
                            color:#8FA2B4;
                            font-size:8px;
                            text-transform:uppercase;
                        ">
                            Requieren atención
                        </span>
                        <strong style="
                            display:block;
                            margin-top:4px;
                            color:#FFFFFF;
                            font-size:21px;
                        ">
                            {_fmt_int(
                                attention
                            )}
                        </strong>
                    </div>

                    <div style="
                        padding:12px;
                        border:1px solid #2C3A46;
                        border-radius:9px;
                        background:#111C25;
                    ">
                        <span style="
                            color:#8FA2B4;
                            font-size:8px;
                            text-transform:uppercase;
                        ">
                            Saludables
                        </span>
                        <strong style="
                            display:block;
                            margin-top:4px;
                            color:#FFFFFF;
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
                    color:#91A3B5;
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

        render_html(
            _inventory_table_html(
                display[visible_columns],
                columns=visible_columns,
                max_rows=250,
            )
        )

        if len(display) > 250:
            st.caption(
                f"Vista limitada a 250 registros de {_fmt_int(len(display))}. "
                "El Excel conserva todos los resultados filtrados."
            )
