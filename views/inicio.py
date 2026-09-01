from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st

from ui.components import render_html
from utils.numbers import format_clp


# ============================================================
# HELPERS
# ============================================================

CHILE_TZ = ZoneInfo("America/Santiago")


def _fmt_int(value) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except Exception:
        return "0"


def _money(value) -> str:
    try:
        return format_clp(float(value))
    except Exception:
        return "$0"


def _money_compact(value) -> str:
    try:
        n = float(value)
    except Exception:
        return "$0"

    sign = "-" if n < 0 else ""
    n = abs(n)

    if n >= 1_000_000_000:
        return f"{sign}${n / 1_000_000_000:.2f} mil MM".replace(".", ",")
    if n >= 1_000_000:
        return f"{sign}${n / 1_000_000:.1f} MM".replace(".", ",")
    if n >= 1_000:
        return f"{sign}${n / 1_000:.1f} mil".replace(".", ",")

    return f"{sign}${n:,.0f}".replace(",", ".")


def _normalize_sku(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def _find_exact(df: pd.DataFrame | None, candidates: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    lookup = {
        str(col).strip().lower(): col
        for col in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lookup:
            return lookup[key]

    return None


def _find_contains(df: pd.DataFrame | None, tokens: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    for col in df.columns:
        key = str(col).strip().lower()
        if any(token.lower() in key for token in tokens):
            return col

    return None


def _period_from_sales(sales_df: pd.DataFrame | None) -> tuple[date, date]:
    if sales_df is None or sales_df.empty:
        end = date.today()
        return end - timedelta(days=30), end

    date_col = _find_exact(
        sales_df,
        ["Fecha_dt", "Fecha", "Fecha Emision", "FechaEmision"],
    )

    if not date_col:
        end = date.today()
        return end - timedelta(days=30), end

    valid = pd.to_datetime(
        sales_df[date_col],
        errors="coerce",
        dayfirst=True,
    ).dropna()

    end = valid.max().date() if not valid.empty else date.today()
    return end - timedelta(days=30), end


def _prepare_sales(
    sales_df: pd.DataFrame | None,
    start: date,
    end: date,
) -> pd.DataFrame:
    if sales_df is None or sales_df.empty:
        return pd.DataFrame()

    work = sales_df.copy()

    date_col = _find_exact(
        work,
        ["Fecha_dt", "Fecha", "Fecha Emision", "FechaEmision"],
    )

    if not date_col:
        return pd.DataFrame()

    work["FechaDashboard"] = pd.to_datetime(
        work[date_col],
        errors="coerce",
        dayfirst=True,
    )

    work = work[
        work["FechaDashboard"].notna()
        & (work["FechaDashboard"].dt.date >= start)
        & (work["FechaDashboard"].dt.date <= end)
    ].copy()

    if work.empty:
        return work

    group_col = _find_exact(
        work,
        ["Grupo comercial", "GrupoComercial"],
    )

    if group_col:
        allowed = {
            "Factura",
            "Boleta",
            "Nota de crédito",
        }
        work = work[
            work[group_col].isin(allowed)
        ].copy()

    amount_col = _find_exact(
        work,
        [
            "VentaFirmadaConIVA",
            "VentaMonto_num",
            "Total",
            "Monto",
            "Venta Neta",
        ],
    )

    if amount_col:
        amount = pd.to_numeric(
            work[amount_col],
            errors="coerce",
        ).fillna(0.0)

        if amount_col != "VentaFirmadaConIVA":
            amount = amount.abs()

        if group_col and amount_col != "VentaFirmadaConIVA":
            credit_mask = work[group_col].eq("Nota de crédito")
            amount.loc[credit_mask] *= -1

        work["VentaDashboard"] = amount
    else:
        work["VentaDashboard"] = 0.0

    qty_col = _find_exact(
        work,
        [
            "CantidadFirmada",
            "Cantidad_num",
            "Cantidad",
            "Unidades",
        ],
    )

    if qty_col:
        qty = pd.to_numeric(
            work[qty_col],
            errors="coerce",
        ).fillna(0.0)

        if qty_col != "CantidadFirmada":
            qty = qty.abs()

        if group_col and qty_col != "CantidadFirmada":
            credit_mask = work[group_col].eq("Nota de crédito")
            qty.loc[credit_mask] *= -1

        work["CantidadDashboard"] = qty
    else:
        work["CantidadDashboard"] = 0.0

    sku_col = _find_exact(
        work,
        ["SKU", "Codigo", "Código", "CodigoProducto", "Código Producto"],
    )

    if sku_col:
        work["SKUDashboard"] = _normalize_sku(
            work[sku_col]
        )
    else:
        work["SKUDashboard"] = ""

    return work


def _delta(current: float, previous: float) -> tuple[str, str]:
    if previous == 0:
        if current == 0:
            return "Sin variación", "neutral"
        return "Sin base comparable", "neutral"

    pct = ((current - previous) / abs(previous)) * 100

    if pct > 0.05:
        return f"↑ {abs(pct):.1f}% vs. período anterior", "positive"
    if pct < -0.05:
        return f"↓ {abs(pct):.1f}% vs. período anterior", "negative"

    return f"• {abs(pct):.1f}% vs. período anterior", "neutral"


def _channel_column(sales_df: pd.DataFrame | None) -> str | None:
    col = _find_exact(
        sales_df,
        [
            "Marketplace",
            "MarketPlace",
            "Canal",
            "Tienda",
            "Origen",
        ],
    )

    if col:
        return col

    return _find_contains(
        sales_df,
        ["marketplace", "canal", "tienda", "origen"],
    )


def _document_column(sales_df: pd.DataFrame | None) -> str | None:
    return _find_exact(
        sales_df,
        [
            "Numero",
            "Número",
            "Folio",
            "NroDocumento",
            "NumeroDocumento",
        ],
    )


def _stock_metrics(cons: pd.DataFrame | None) -> dict:
    result = {
        "sku": 0,
        "units": 0,
        "healthy": 0,
        "low": 0,
        "risk": 0,
        "zero": 0,
    }

    if cons is None or cons.empty:
        return result

    code_col = _find_exact(
        cons,
        ["Código", "Codigo", "SKU"],
    )

    available_col = _find_exact(
        cons,
        ["Disponible", "Stock", "Stock Disponible"],
    )

    state_col = _find_exact(
        cons,
        ["Estado", "Estado Stock"],
    )

    if code_col:
        result["sku"] = int(cons[code_col].nunique())
    else:
        result["sku"] = len(cons)

    if available_col:
        available = pd.to_numeric(
            cons[available_col],
            errors="coerce",
        ).fillna(0)
        result["units"] = int(round(available.clip(lower=0).sum()))

    if state_col:
        states = cons[state_col].fillna("").astype(str)

        result["healthy"] = int(
            states.str.contains(
                "Disponible|Saludable",
                case=False,
                regex=True,
            ).sum()
        )
        result["low"] = int(
            states.str.contains(
                "Stock bajo|Bajo",
                case=False,
                regex=True,
            ).sum()
        )
        result["risk"] = int(
            states.str.contains(
                "Riesgo",
                case=False,
                regex=True,
            ).sum()
        )
        result["zero"] = int(
            states.str.contains(
                "Sin stock|Negativo|Agotado",
                case=False,
                regex=True,
            ).sum()
        )
    elif available_col:
        available = pd.to_numeric(
            cons[available_col],
            errors="coerce",
        ).fillna(0)

        result["zero"] = int((available <= 0).sum())
        result["low"] = int(((available > 0) & (available <= 5)).sum())
        result["healthy"] = int((available > 5).sum())

    return result


def _warehouse_summary(raw: pd.DataFrame | None) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Bodega", "Stock"])

    warehouse_col = _find_exact(
        raw,
        ["Bodega", "Warehouse"],
    )

    stock_col = _find_exact(
        raw,
        ["Stock", "Disponible", "Stock Disponible"],
    )

    if not warehouse_col or not stock_col:
        return pd.DataFrame(columns=["Bodega", "Stock"])

    work = raw[[warehouse_col, stock_col]].copy()
    work[stock_col] = pd.to_numeric(
        work[stock_col],
        errors="coerce",
    ).fillna(0)

    return (
        work.groupby(warehouse_col, as_index=False)[stock_col]
        .sum()
        .rename(
            columns={
                warehouse_col: "Bodega",
                stock_col: "Stock",
            }
        )
        .sort_values("Stock", ascending=False)
    )


def _top_products(
    raw_stock: pd.DataFrame | None,
    sales: pd.DataFrame,
    limit: int = 5,
) -> pd.DataFrame:
    if sales is None or sales.empty:
        return pd.DataFrame()

    if "SKUDashboard" not in sales.columns:
        return pd.DataFrame()

    work = (
        sales[sales["SKUDashboard"].ne("")]
        .groupby("SKUDashboard", as_index=False)
        .agg(
            Unidades=("CantidadDashboard", "sum"),
            Venta=("VentaDashboard", "sum"),
        )
    )

    if work.empty:
        return work

    work["Unidades"] = work["Unidades"].clip(lower=0)

    if raw_stock is not None and not raw_stock.empty:
        code_col = _find_exact(
            raw_stock,
            ["Código", "Codigo", "SKU", "Producto"],
        )
        product_col = _find_exact(
            raw_stock,
            ["Producto", "Descripción", "Descripcion"],
        )

        if code_col and product_col:
            names = raw_stock[
                [code_col, product_col]
            ].copy()

            names["SKUDashboard"] = _normalize_sku(
                names[code_col]
            )

            names = (
                names[
                    ["SKUDashboard", product_col]
                ]
                .drop_duplicates("SKUDashboard")
                .rename(columns={product_col: "Producto"})
            )

            work = work.merge(
                names,
                on="SKUDashboard",
                how="left",
            )

    if "Producto" not in work.columns:
        work["Producto"] = work["SKUDashboard"]

    work["Producto"] = (
        work["Producto"]
        .fillna(work["SKUDashboard"])
        .astype(str)
    )

    return (
        work.sort_values(
            ["Venta", "Unidades"],
            ascending=False,
        )
        .head(limit)
        .reset_index(drop=True)
    )


def _critical_products(
    cons: pd.DataFrame | None,
    limit: int = 5,
) -> pd.DataFrame:
    if cons is None or cons.empty:
        return pd.DataFrame()

    code_col = _find_exact(cons, ["Código", "Codigo", "SKU"])
    product_col = _find_exact(cons, ["Producto", "Descripción", "Descripcion"])
    available_col = _find_exact(cons, ["Disponible", "Stock", "Stock Disponible"])
    state_col = _find_exact(cons, ["Estado", "Estado Stock"])

    if not code_col or not available_col:
        return pd.DataFrame()

    cols = [code_col, available_col]
    if product_col:
        cols.append(product_col)
    if state_col:
        cols.append(state_col)

    work = cons[cols].copy()
    work[available_col] = pd.to_numeric(
        work[available_col],
        errors="coerce",
    ).fillna(0)

    if state_col:
        priority_mask = work[state_col].fillna("").astype(str).str.contains(
            "Sin stock|Negativo|Stock bajo|Riesgo|Agotado|Bajo",
            case=False,
            regex=True,
        )
        work = work[priority_mask].copy()
    else:
        work = work[work[available_col] <= 5].copy()

    if work.empty:
        return work

    work = work.sort_values(
        available_col,
        ascending=True,
    ).head(limit)

    out = pd.DataFrame()
    out["SKU"] = _normalize_sku(work[code_col])
    out["Producto"] = (
        work[product_col].astype(str)
        if product_col
        else out["SKU"]
    )
    out["Stock Actual"] = work[available_col].round().astype(int)

    if state_col:
        out["Estado"] = work[state_col].astype(str)
    else:
        out["Estado"] = out["Stock Actual"].apply(
            lambda x: "SIN STOCK" if x <= 0 else "BAJO"
        )

    return out.reset_index(drop=True)


def _margin_data(sales: pd.DataFrame) -> tuple[float | None, float | None]:
    """
    Solo calcula margen si existen columnas explícitas de costo.
    Nunca usa CentroCosto ni columnas parecidas.
    """
    if sales is None or sales.empty:
        return None, None

    cost_col = _find_exact(
        sales,
        [
            "Costo",
            "Costo_num",
            "Costo Total",
            "CostoTotal",
            "Costo Venta",
            "CostoVenta",
        ],
    )

    if not cost_col:
        return None, None

    cost = pd.to_numeric(
        sales[cost_col],
        errors="coerce",
    ).fillna(0).abs().sum()

    revenue = float(
        sales.get(
            "VentaDashboard",
            pd.Series(dtype="float64"),
        ).sum()
    )

    margin = revenue - cost

    margin_pct = (
        margin / revenue * 100
        if revenue != 0
        else None
    )

    return margin, margin_pct


def _kpi_html(
    label: str,
    value: str,
    helper: str,
    icon: str,
    tone: str = "yellow",
) -> str:
    return f"""
    <div class="homepro-kpi">
        <div class="homepro-kpi-top">
            <span class="homepro-kpi-label">{escape(label)}</span>
            <span class="homepro-kpi-icon {escape(tone)}">{escape(icon)}</span>
        </div>
        <div class="homepro-kpi-value">{escape(value)}</div>
        <div class="homepro-kpi-helper {escape(tone)}">{escape(helper)}</div>
    </div>
    """


def _nav_button(label: str, target: str, key: str):
    if st.button(label, key=key, width="stretch"):
        st.session_state.page = target
        st.rerun()


# ============================================================
# CSS
# ============================================================

def _inject_css():
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1600px;
            padding-top: 1.05rem;
            padding-bottom: 2.2rem;
        }

        div[data-testid="stVerticalBlock"] {
            gap: .72rem;
        }

        .homepro-head {
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:24px;
            margin-bottom:8px;
        }

        .homepro-greeting {
            font-size:29px;
            font-weight:800;
            color:#121820;
            letter-spacing:-.8px;
            line-height:1.1;
        }

        .homepro-sub {
            margin-top:7px;
            font-size:13px;
            color:#7d8792;
        }

        .homepro-update {
            display:flex;
            gap:9px;
            align-items:center;
            color:#747d87;
            font-size:12px;
            white-space:nowrap;
            padding-top:5px;
        }

        .homepro-update-dot {
            width:8px;
            height:8px;
            border-radius:999px;
            background:#22c55e;
            box-shadow:0 0 0 4px rgba(34,197,94,.10);
        }

        .homepro-kpis {
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:12px;
            margin:6px 0 4px 0;
        }

        .homepro-kpi {
            background:#fff;
            border:1px solid #e9edf1;
            border-radius:12px;
            padding:17px 17px 14px 17px;
            min-height:112px;
            box-shadow:0 3px 12px rgba(20,30,45,.035);
        }

        .homepro-kpi-top {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:8px;
        }

        .homepro-kpi-label {
            font-size:12px;
            color:#303943;
            font-weight:650;
        }

        .homepro-kpi-icon {
            width:29px;
            height:29px;
            display:flex;
            align-items:center;
            justify-content:center;
            border-radius:999px;
            font-size:14px;
            font-weight:800;
        }

        .homepro-kpi-icon.yellow {
            background:#fff6d6;
            color:#e3a600;
        }

        .homepro-kpi-icon.green {
            background:#eaf8ec;
            color:#22a447;
        }

        .homepro-kpi-icon.red {
            background:#fff0ee;
            color:#dd584c;
        }

        .homepro-kpi-icon.blue {
            background:#eef5ff;
            color:#3f7fd6;
        }

        .homepro-kpi-value {
            margin-top:12px;
            color:#10161d;
            font-size:22px;
            font-weight:800;
            line-height:1;
            letter-spacing:-.45px;
        }

        .homepro-kpi-helper {
            margin-top:12px;
            font-size:10.5px;
            font-weight:600;
            color:#89929c;
        }

        .homepro-kpi-helper.green,
        .homepro-kpi-helper.positive {
            color:#15a34a;
        }

        .homepro-kpi-helper.red,
        .homepro-kpi-helper.negative {
            color:#dc5148;
        }

        .homepro-card-title {
            font-size:13px;
            font-weight:800;
            color:#1a2027;
            margin-bottom:2px;
        }

        .homepro-card-sub {
            color:#8b949e;
            font-size:10.5px;
            margin-bottom:4px;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color:#e9edf1 !important;
            border-radius:12px !important;
            background:white !important;
            box-shadow:0 3px 12px rgba(20,30,45,.025);
        }

        .homepro-alerts {
            display:flex;
            flex-direction:column;
            gap:0;
            margin-top:1px;
        }

        .homepro-alert {
            display:grid;
            grid-template-columns:30px 1fr auto;
            align-items:center;
            gap:10px;
            padding:13px 0;
            border-bottom:1px solid #edf0f2;
        }

        .homepro-alert:last-child {
            border-bottom:0;
        }

        .homepro-alert-icon {
            width:28px;
            height:28px;
            border-radius:8px;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:13px;
            font-weight:900;
        }

        .homepro-alert-icon.red {
            background:#fff0ed;
            color:#ec5447;
        }

        .homepro-alert-icon.yellow {
            background:#fff7dd;
            color:#e7a900;
        }

        .homepro-alert-icon.blue {
            background:#eef5ff;
            color:#4283d4;
        }

        .homepro-alert-icon.green {
            background:#edf9ef;
            color:#35a756;
        }

        .homepro-alert strong {
            display:block;
            font-size:12px;
            color:#20272e;
            margin-bottom:2px;
        }

        .homepro-alert small {
            font-size:9.5px;
            color:#9099a3;
        }

        .homepro-alert-value {
            font-size:11px;
            color:#4b5560;
            font-weight:700;
        }

        .homepro-status-summary {
            display:grid;
            grid-template-columns:repeat(3,1fr);
            gap:8px;
            margin-top:3px;
        }

        .homepro-status-summary > div {
            border:1px solid #edf0f2;
            border-radius:9px;
            padding:8px;
        }

        .homepro-status-summary span {
            display:block;
            color:#8c949e;
            font-size:9px;
        }

        .homepro-status-summary strong {
            display:block;
            color:#161c22;
            font-size:13px;
            margin-top:2px;
        }

        .homepro-product-list {
            margin-top:4px;
        }

        .homepro-product-row {
            display:grid;
            grid-template-columns:28px minmax(0,1fr) 85px 110px;
            gap:10px;
            align-items:center;
            min-height:42px;
            border-bottom:1px solid #edf0f2;
            font-size:10.5px;
        }

        .homepro-product-row:last-child {
            border-bottom:0;
        }

        .homepro-rank {
            color:#9ba3ac;
            font-weight:700;
        }

        .homepro-product-main strong {
            display:block;
            color:#252d35;
            font-size:10.5px;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }

        .homepro-product-main span {
            color:#9aa2ab;
            font-size:9px;
        }

        .homepro-num {
            text-align:right;
            font-weight:700;
            color:#303840;
        }

        .homepro-money {
            text-align:right;
            font-weight:700;
            color:#121820;
        }

        .homepro-attention {
            background:linear-gradient(90deg,#fff8df 0%,#fffdf6 70%,#fff 100%);
            border:1px solid #f4e8ba;
            border-radius:11px;
            padding:13px 15px;
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:15px;
        }

        .homepro-attention strong {
            display:block;
            font-size:12px;
            color:#242b32;
        }

        .homepro-attention span {
            display:block;
            margin-top:2px;
            font-size:9.5px;
            color:#8e876d;
        }

        .homepro-table {
            width:100%;
            border-collapse:collapse;
            font-size:10px;
        }

        .homepro-table th {
            text-align:left;
            color:#68727d;
            padding:9px 10px;
            border-bottom:1px solid #e8ecef;
            font-size:9px;
            text-transform:uppercase;
            letter-spacing:.25px;
        }

        .homepro-table td {
            padding:10px;
            border-bottom:1px solid #edf0f2;
            color:#2b333b;
        }

        .homepro-table tr:last-child td {
            border-bottom:0;
        }

        .homepro-badge {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            min-width:54px;
            border-radius:999px;
            padding:4px 8px;
            font-size:8px;
            font-weight:800;
        }

        .homepro-badge.red {
            background:#ffe3dd;
            color:#c94d42;
        }

        .homepro-badge.yellow {
            background:#fff0bf;
            color:#a66c00;
        }

        .homepro-badge.orange {
            background:#ffead8;
            color:#b75f16;
        }

        .homepro-quick-title {
            font-size:12px;
            font-weight:800;
            color:#222a31;
            margin-bottom:8px;
        }

        .homepro-foot {
            text-align:center;
            color:#a0a8b0;
            font-size:9px;
            padding:14px 0 0 0;
        }

        .stButton > button {
            border-radius:9px !important;
            min-height:40px !important;
            font-size:11px !important;
            font-weight:700 !important;
        }


        .homepro-inventory-hero {
            display:flex;
            align-items:center;
            gap:16px;
            margin-top:10px;
            margin-bottom:14px;
        }

        .homepro-health-ring {
            --p: 0%;
            width:96px;
            height:96px;
            flex:0 0 96px;
            border-radius:50%;
            background:
                radial-gradient(circle at center, #fff 58%, transparent 59%),
                conic-gradient(#8fc267 var(--p), #eef1f3 0);
            display:flex;
            align-items:center;
            justify-content:center;
            position:relative;
        }

        .homepro-health-ring > div {
            text-align:center;
            line-height:1;
        }

        .homepro-health-ring strong {
            display:block;
            font-size:24px;
            font-weight:850;
            color:#141a20;
            letter-spacing:-.5px;
        }

        .homepro-health-ring span {
            display:block;
            margin-top:5px;
            font-size:9px;
            color:#8b949d;
        }

        .homepro-health-copy {
            min-width:0;
            flex:1;
        }

        .homepro-health-copy strong {
            display:block;
            color:#1e252c;
            font-size:12px;
            margin-bottom:5px;
        }

        .homepro-health-copy p {
            margin:0;
            color:#8a939c;
            font-size:9.5px;
            line-height:1.45;
        }

        .homepro-status-list {
            display:flex;
            flex-direction:column;
            gap:9px;
        }

        .homepro-status-row {
            display:grid;
            grid-template-columns:10px minmax(0,1fr) auto;
            align-items:center;
            gap:9px;
            font-size:10px;
        }

        .homepro-status-row i {
            width:8px;
            height:8px;
            border-radius:999px;
        }

        .homepro-status-row i.green { background:#8fc267; }
        .homepro-status-row i.yellow { background:#ffc400; }
        .homepro-status-row i.orange { background:#f4a44b; }
        .homepro-status-row i.red { background:#ef6656; }

        .homepro-status-row span {
            color:#69737d;
        }

        .homepro-status-row strong {
            color:#20272e;
            font-size:10.5px;
        }

        .homepro-wh-list {
            display:flex;
            flex-direction:column;
            gap:13px;
            margin-top:13px;
        }

        .homepro-wh-row {
            display:grid;
            grid-template-columns:88px minmax(0,1fr) 62px;
            align-items:center;
            gap:10px;
        }

        .homepro-wh-name {
            color:#59636d;
            font-size:10px;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }

        .homepro-wh-track {
            position:relative;
            height:12px;
            border-radius:999px;
            background:#f1f3f5;
            overflow:hidden;
        }

        .homepro-wh-bar {
            height:100%;
            min-width:3px;
            border-radius:999px;
            background:linear-gradient(90deg,#ffc400,#ffd553);
        }

        .homepro-wh-value {
            text-align:right;
            color:#303840;
            font-size:10px;
            font-weight:750;
        }

        .homepro-wh-total {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:12px;
            margin-top:15px;
            padding-top:11px;
            border-top:1px solid #edf0f2;
            color:#9099a3;
            font-size:9.5px;
        }

        .homepro-wh-total strong {
            color:#20272e;
            font-size:11px;
        }

        @media (max-width: 1100px) {
            .homepro-kpis {
                grid-template-columns:repeat(2,minmax(0,1fr));
            }
        }

        @media (max-width: 700px) {
            .homepro-head {
                flex-direction:column;
            }
            .homepro-kpis {
                grid-template-columns:1fr;
            }
            .homepro-product-row {
                grid-template-columns:24px minmax(0,1fr) 62px;
            }
            .homepro-product-row .homepro-money {
                display:none;
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

    raw = ctx.get("stock_normalized")
    cons = ctx.get("stock_consolidated")
    sales_df = ctx.get("sales_df")
    stock_meta = ctx.get("stock_meta") or {}

    default_start, default_end = _period_from_sales(sales_df)

    if "homepro_period" not in st.session_state:
        st.session_state.homepro_period = (
            default_start,
            default_end,
        )

    now_cl = datetime.now(CHILE_TZ)
    greeting = (
        "Buenos días"
        if now_cl.hour < 12
        else "Buenas tardes"
        if now_cl.hour < 20
        else "Buenas noches"
    )

    updated = (
        stock_meta.get("generatedAt")
        or stock_meta.get("loaded_at")
        or now_cl.strftime("%d/%m/%Y %H:%M")
    )

    render_html(
        f"""
        <div class="homepro-head">
            <div>
                <div class="homepro-greeting">{greeting}, Sebastián 👋</div>
                <div class="homepro-sub">
                    Aquí tienes un resumen general del negocio.
                </div>
            </div>
            <div class="homepro-update">
                <span class="homepro-update-dot"></span>
                <span>Última actualización: {escape(str(updated))}</span>
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # FILTRO DE FECHA
    # --------------------------------------------------------

    filter_left, filter_right = st.columns([1.25, 4.75])

    with filter_left:
        period = st.date_input(
            "Período",
            value=st.session_state.homepro_period,
            key="homepro_period_picker",
            format="DD/MM/YYYY",
        )

    # st.date_input con rango puede devolver:
    # - una fecha única,
    # - una tupla de 1 elemento mientras el usuario elige el segundo día,
    # - una tupla de 2 fechas cuando el rango está completo.
    if isinstance(period, (tuple, list)):
        if len(period) >= 2:
            start, end = period[0], period[1]
        elif len(period) == 1:
            start = end = period[0]
        else:
            start, end = default_start, default_end
    else:
        start = end = period

    st.session_state.homepro_period = (start, end)

    # --------------------------------------------------------
    # DATOS VENTAS
    # --------------------------------------------------------

    current_sales = _prepare_sales(
        sales_df,
        start,
        end,
    )

    days = max((end - start).days + 1, 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    previous_sales = _prepare_sales(
        sales_df,
        prev_start,
        prev_end,
    )

    current_revenue = float(
        current_sales.get(
            "VentaDashboard",
            pd.Series(dtype="float64"),
        ).sum()
    )

    previous_revenue = float(
        previous_sales.get(
            "VentaDashboard",
            pd.Series(dtype="float64"),
        ).sum()
    )

    current_units = max(
        float(
            current_sales.get(
                "CantidadDashboard",
                pd.Series(dtype="float64"),
            ).sum()
        ),
        0,
    )

    previous_units = max(
        float(
            previous_sales.get(
                "CantidadDashboard",
                pd.Series(dtype="float64"),
            ).sum()
        ),
        0,
    )

    revenue_delta, revenue_tone = _delta(
        current_revenue,
        previous_revenue,
    )

    units_delta, units_tone = _delta(
        current_units,
        previous_units,
    )

    margin, margin_pct = _margin_data(current_sales)

    stock = _stock_metrics(cons)

    total_states = max(
        stock["healthy"]
        + stock["low"]
        + stock["risk"]
        + stock["zero"],
        1,
    )

    healthy_pct = (
        stock["healthy"] / total_states * 100
    )

    if margin is None:
        margin_value = "—"
        margin_helper = "Costo no disponible en ERP"
        margin_tone = "yellow"
    else:
        margin_value = _money_compact(margin)
        margin_helper = (
            f"{margin_pct:.1f}% sobre venta neta"
            if margin_pct is not None
            else "Margen calculado"
        )
        margin_tone = "green" if margin >= 0 else "red"

    # --------------------------------------------------------
    # KPIs
    # --------------------------------------------------------

    kpis = "".join(
        [
            _kpi_html(
                "Ventas Netas",
                _money_compact(current_revenue),
                revenue_delta,
                "↗",
                "green" if revenue_tone == "positive" else (
                    "red" if revenue_tone == "negative" else "yellow"
                ),
            ),
            _kpi_html(
                "Margen Bruto",
                margin_value,
                margin_helper,
                "◫",
                margin_tone,
            ),
            _kpi_html(
                "Unidades Vendidas",
                _fmt_int(current_units),
                units_delta,
                "▣",
                "green" if units_tone == "positive" else (
                    "red" if units_tone == "negative" else "yellow"
                ),
            ),
            _kpi_html(
                "Stock Total (UND)",
                _fmt_int(stock["units"]),
                f"{healthy_pct:.0f}% del inventario saludable",
                "⬡",
                "yellow",
            ),
            _kpi_html(
                "SKU Activos",
                _fmt_int(stock["sku"]),
                f"{_fmt_int(stock['low'] + stock['zero'])} requieren atención",
                "⌘",
                "yellow",
            ),
        ]
    )

    render_html(
        f"""
        <div class="homepro-kpis">
            {kpis}
        </div>
        """
    )

    # --------------------------------------------------------
    # FILA PRINCIPAL
    # --------------------------------------------------------

    left, middle, right = st.columns(
        [1.55, 1.08, 1.12],
        gap="medium",
    )

    with left:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Ventas Netas</div>
                <div class="homepro-card-sub">
                    Evolución diaria del período seleccionado
                </div>
                """
            )

            if current_sales.empty:
                st.info("No hay ventas disponibles para el período seleccionado.")
            else:
                daily = (
                    current_sales.assign(
                        Día=current_sales["FechaDashboard"].dt.floor("D")
                    )
                    .groupby("Día", as_index=False)["VentaDashboard"]
                    .sum()
                    .rename(columns={"VentaDashboard": "Venta"})
                    .sort_values("Día")
                )

                line = (
                    alt.Chart(daily)
                    .mark_area(
                        line={
                            "color": "#f3b400",
                            "strokeWidth": 2.3,
                        },
                        color="#ffd94f",
                        opacity=0.19,
                    )
                    .encode(
                        x=alt.X(
                            "Día:T",
                            title=None,
                            axis=alt.Axis(
                                format="%d %b",
                                labelColor="#7c8792",
                                domain=False,
                                tickColor="#e8ecef",
                            ),
                        ),
                        y=alt.Y(
                            "Venta:Q",
                            title=None,
                            axis=alt.Axis(
                                format="~s",
                                labelColor="#7c8792",
                                domain=False,
                                gridColor="#edf0f2",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("Día:T", title="Fecha", format="%d/%m/%Y"),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                    .properties(height=270)
                )

                st.altair_chart(
                    line,
                    width="stretch",
                )

    with middle:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Ventas por Canal</div>
                <div class="homepro-card-sub">
                    Participación sobre la venta neta
                </div>
                """
            )

            channel_col = _channel_column(sales_df)

            if (
                current_sales.empty
                or not channel_col
                or channel_col not in current_sales.columns
            ):
                st.info("No se encontró una columna de canal o marketplace.")
            else:
                channel = current_sales.copy()

                channel["CanalDashboard"] = (
                    channel[channel_col]
                    .fillna("Sin canal")
                    .astype(str)
                    .str.strip()
                    .replace("", "Sin canal")
                )

                channel = (
                    channel.groupby(
                        "CanalDashboard",
                        as_index=False,
                    )["VentaDashboard"]
                    .sum()
                    .rename(
                        columns={
                            "CanalDashboard": "Canal",
                            "VentaDashboard": "Venta",
                        }
                    )
                    .sort_values("Venta", ascending=False)
                    .head(7)
                )

                donut = (
                    alt.Chart(channel)
                    .mark_arc(
                        innerRadius=68,
                        outerRadius=100,
                        cornerRadius=4,
                    )
                    .encode(
                        theta=alt.Theta("Venta:Q"),
                        color=alt.Color(
                            "Canal:N",
                            scale=alt.Scale(
                                range=[
                                    "#ffc400",
                                    "#1d232a",
                                    "#7fbf4d",
                                    "#ef624f",
                                    "#9aa3ac",
                                    "#4d82bc",
                                    "#d7a847",
                                ]
                            ),
                            legend=alt.Legend(
                                orient="bottom",
                                columns=2,
                                labelColor="#6d7781",
                                title=None,
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("Canal:N", title="Canal"),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                    .properties(height=270)
                )

                st.altair_chart(
                    donut,
                    width="stretch",
                )

    with right:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Alertas y Oportunidades</div>
                <div class="homepro-card-sub">
                    Prioridades operacionales actuales
                </div>
                """
            )

            alerts_html = f"""
            <div class="homepro-alerts">
                <div class="homepro-alert">
                    <div class="homepro-alert-icon red">!</div>
                    <div>
                        <strong>{_fmt_int(stock['zero'])} productos sin stock</strong>
                        <small>Revisar disponibilidad y demanda.</small>
                    </div>
                    <div class="homepro-alert-value">Crítico</div>
                </div>

                <div class="homepro-alert">
                    <div class="homepro-alert-icon yellow">△</div>
                    <div>
                        <strong>{_fmt_int(stock['low'])} productos con stock bajo</strong>
                        <small>Productos con necesidad de reposición.</small>
                    </div>
                    <div class="homepro-alert-value">Atención</div>
                </div>

                <div class="homepro-alert">
                    <div class="homepro-alert-icon blue">↻</div>
                    <div>
                        <strong>{_fmt_int(stock['risk'])} productos en riesgo</strong>
                        <small>Revisar cobertura y disponibilidad.</small>
                    </div>
                    <div class="homepro-alert-value">Revisar</div>
                </div>

                <div class="homepro-alert">
                    <div class="homepro-alert-icon green">✓</div>
                    <div>
                        <strong>{healthy_pct:.0f}% del inventario saludable</strong>
                        <small>{_fmt_int(stock['healthy'])} SKU disponibles.</small>
                    </div>
                    <div class="homepro-alert-value">OK</div>
                </div>
            </div>
            """

            render_html(alerts_html)

    # --------------------------------------------------------
    # SEGUNDA FILA
    # --------------------------------------------------------

    left2, middle2, right2 = st.columns(
        [1.55, 1.08, 1.12],
        gap="medium",
    )

    with left2:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Top 5 Productos por Ventas</div>
                <div class="homepro-card-sub">
                    Productos con mayor venta neta del período
                </div>
                """
            )

            top = _top_products(
                raw,
                current_sales,
                limit=5,
            )

            if top.empty:
                st.info("No hay ventas por SKU disponibles.")
            else:
                rows = ""

                for i, row in top.iterrows():
                    rows += f"""
                    <div class="homepro-product-row">
                        <div class="homepro-rank">{i + 1}</div>
                        <div class="homepro-product-main">
                            <strong>{escape(str(row['Producto'])[:42])}</strong>
                            <span>SKU {escape(str(row['SKUDashboard']))}</span>
                        </div>
                        <div class="homepro-num">{_fmt_int(row['Unidades'])}</div>
                        <div class="homepro-money">{_money_compact(row['Venta'])}</div>
                    </div>
                    """

                render_html(
                    f"""
                    <div class="homepro-product-list">
                        {rows}
                    </div>
                    """
                )

    with middle2:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Estado del Inventario</div>
                <div class="homepro-card-sub">
                    Salud y disponibilidad actual de los SKU
                </div>
                """
            )

            healthy_units = stock["healthy"]
            low_units = stock["low"]
            risk_units = stock["risk"]
            zero_units = stock["zero"]

            render_html(
                f"""
                <div class="homepro-inventory-hero">
                    <div
                        class="homepro-health-ring"
                        style="--p:{healthy_pct:.1f}%"
                    >
                        <div>
                            <strong>{healthy_pct:.0f}%</strong>
                            <span>Saludable</span>
                        </div>
                    </div>

                    <div class="homepro-health-copy">
                        <strong>
                            {_fmt_int(healthy_units)} SKU con disponibilidad normal
                        </strong>
                        <p>
                            El indicador resume la condición actual del inventario.
                            Los productos con stock bajo, riesgo o quiebre quedan
                            destacados para revisión.
                        </p>
                    </div>
                </div>

                <div class="homepro-status-list">
                    <div class="homepro-status-row">
                        <i class="green"></i>
                        <span>Saludable</span>
                        <strong>{_fmt_int(healthy_units)} SKU</strong>
                    </div>

                    <div class="homepro-status-row">
                        <i class="yellow"></i>
                        <span>Stock bajo</span>
                        <strong>{_fmt_int(low_units)} SKU</strong>
                    </div>

                    <div class="homepro-status-row">
                        <i class="orange"></i>
                        <span>Riesgo operacional</span>
                        <strong>{_fmt_int(risk_units)} SKU</strong>
                    </div>

                    <div class="homepro-status-row">
                        <i class="red"></i>
                        <span>Sin stock</span>
                        <strong>{_fmt_int(zero_units)} SKU</strong>
                    </div>
                </div>
                """
            )

    with right2:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Distribución por Bodega</div>
                <div class="homepro-card-sub">
                    Unidades disponibles por ubicación
                </div>
                """
            )

            warehouses = _warehouse_summary(raw)

            if warehouses.empty:
                st.info("No hay distribución por bodega disponible.")
            else:
                warehouses = warehouses.head(8).copy()
                total_wh = float(warehouses["Stock"].clip(lower=0).sum())
                max_wh = max(float(warehouses["Stock"].max()), 1.0)

                wh_rows = ""

                for _, row in warehouses.iterrows():
                    units = max(float(row["Stock"]), 0.0)
                    width = min((units / max_wh) * 100, 100)
                    share = (units / total_wh * 100) if total_wh > 0 else 0

                    wh_rows += f"""
                    <div class="homepro-wh-row">
                        <div class="homepro-wh-name">
                            {escape(str(row['Bodega']))}
                        </div>

                        <div class="homepro-wh-track">
                            <div
                                class="homepro-wh-bar"
                                style="width:{width:.1f}%"
                            ></div>
                        </div>

                        <div class="homepro-wh-value">
                            {_fmt_int(units)}
                        </div>
                    </div>
                    """

                top_wh = str(warehouses.iloc[0]["Bodega"])
                top_share = (
                    float(warehouses.iloc[0]["Stock"]) / total_wh * 100
                    if total_wh > 0
                    else 0
                )

                render_html(
                    f"""
                    <div class="homepro-wh-list">
                        {wh_rows}
                    </div>

                    <div class="homepro-wh-total">
                        <span>
                            Mayor concentración:
                            <strong>{escape(top_wh)}</strong>
                            · {top_share:.0f}%
                        </span>
                        <strong>{_fmt_int(total_wh)} UND</strong>
                    </div>
                    """
                )

    # --------------------------------------------------------
    # ALERTA + TABLA + ACCESOS
    # --------------------------------------------------------

    attention_count = stock["low"] + stock["zero"] + stock["risk"]

    render_html(
        f"""
        <div class="homepro-attention">
            <div>
                <strong>⚠ {_fmt_int(attention_count)} productos requieren atención</strong>
                <span>
                    Revisa el detalle de productos con stock bajo,
                    sin stock o riesgo operacional.
                </span>
            </div>
        </div>
        """
    )

    table_col, quick_col = st.columns(
        [2.55, 1.0],
        gap="medium",
    )

    with table_col:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-card-title">Productos que requieren atención</div>
                <div class="homepro-card-sub">
                    Prioridad según disponibilidad actual
                </div>
                """
            )

            critical = _critical_products(
                cons,
                limit=7,
            )

            if critical.empty:
                st.success("No hay productos críticos para mostrar.")
            else:
                rows = ""

                for _, row in critical.iterrows():
                    state = str(row["Estado"])
                    state_low = state.lower()

                    if (
                        "sin stock" in state_low
                        or "negativo" in state_low
                        or "agotado" in state_low
                    ):
                        badge_class = "red"
                        badge_text = "SIN STOCK"
                    elif "riesgo" in state_low:
                        badge_class = "orange"
                        badge_text = "RIESGO"
                    else:
                        badge_class = "yellow"
                        badge_text = "BAJO"

                    rows += f"""
                    <tr>
                        <td>{escape(str(row['SKU']))}</td>
                        <td>{escape(str(row['Producto'])[:55])}</td>
                        <td style="text-align:right">{_fmt_int(row['Stock Actual'])}</td>
                        <td>
                            <span class="homepro-badge {badge_class}">
                                {badge_text}
                            </span>
                        </td>
                    </tr>
                    """

                render_html(
                    f"""
                    <table class="homepro-table">
                        <thead>
                            <tr>
                                <th>SKU</th>
                                <th>Producto</th>
                                <th style="text-align:right">Stock actual</th>
                                <th>Estado</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows}
                        </tbody>
                    </table>
                    """
                )

    with quick_col:
        with st.container(border=True):
            render_html(
                """
                <div class="homepro-quick-title">Accesos Rápidos</div>
                """
            )

            q1, q2 = st.columns(2, gap="small")

            with q1:
                _nav_button(
                    "📦 Stock General",
                    "Stock General",
                    "homepro_stock",
                )

            with q2:
                _nav_button(
                    "🛒 Marketplace",
                    "Marketplace",
                    "homepro_market",
                )

            q3, q4 = st.columns(2, gap="small")

            with q3:
                _nav_button(
                    "📊 Resumen",
                    "Resumen Ejecutivo",
                    "homepro_resumen",
                )

            with q4:
                _nav_button(
                    "📄 Plantillas",
                    "Plantillas",
                    "homepro_templates",
                )

            render_html(
                f"""
                <div style="
                    margin-top:10px;
                    padding:12px;
                    border-radius:9px;
                    background:#f8fafb;
                    border:1px solid #edf0f2;
                ">
                    <div style="
                        font-size:9px;
                        color:#919aa3;
                        text-transform:uppercase;
                        letter-spacing:.4px;
                    ">
                        Resumen de inventario
                    </div>
                    <div style="
                        font-size:19px;
                        font-weight:800;
                        color:#151b21;
                        margin-top:4px;
                    ">
                        {_fmt_int(stock['units'])} UND
                    </div>
                    <div style="
                        font-size:9.5px;
                        color:#7e8791;
                        margin-top:4px;
                    ">
                        {_fmt_int(stock['sku'])} SKU activos
                    </div>
                </div>
                """
            )

    render_html(
        """
        <div class="homepro-foot">
            MARITEX · Control de Inventario
        </div>
        """
    )