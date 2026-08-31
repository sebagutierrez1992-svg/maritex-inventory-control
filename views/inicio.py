

from datetime import date, timedelta
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from ui.components import render_html
from utils.numbers import format_clp


# ============================================================
# HELPERS
# ============================================================

def _num(df: pd.DataFrame | None, column: str) -> pd.Series:
    if df is None:
        return pd.Series(dtype="float64")
    if column not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _money(value: float) -> str:
    return format_clp(float(value))


def _money_compact(value: float) -> str:
    """Formato compacto para tarjetas KPI, evitando desbordes."""
    try:
        value = float(value)
    except Exception:
        return "$0"

    abs_value = abs(value)

    if abs_value >= 1_000_000_000:
        millions = value / 1_000_000
        txt = f"{millions:,.1f}"
        txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"${txt} MM"

    if abs_value >= 1_000_000:
        millions = value / 1_000_000
        txt = f"{millions:,.1f}"
        txt = txt.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"${txt} MM"

    return format_clp(value)


def _fmt_int(value: float | int) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except Exception:
        return "0"


def _find_col(df: pd.DataFrame | None, candidates: list[str]) -> str | None:
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


def _normalize_sku(series: pd.Series) -> pd.Series:
    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def _period_from_sales(sales: pd.DataFrame | None) -> tuple[date, date]:
    if sales is None or sales.empty or "Fecha_dt" not in sales.columns:
        end = date.today()
        return end - timedelta(days=30), end

    valid = pd.to_datetime(
        sales["Fecha_dt"],
        errors="coerce",
    ).dropna()

    if valid.empty:
        end = date.today()
    else:
        end = valid.max().date()

    return end - timedelta(days=30), end


def _prepare_sales(
    sales: pd.DataFrame | None,
    start: date,
    end: date,
) -> pd.DataFrame:
    if sales is None or sales.empty:
        return pd.DataFrame()

    work = sales.copy()

    if "Fecha_dt" not in work.columns:
        return pd.DataFrame()

    work["Fecha_dt"] = pd.to_datetime(
        work["Fecha_dt"],
        errors="coerce",
    )

    work = work[
        work["Fecha_dt"].notna()
        & (work["Fecha_dt"].dt.date >= start)
        & (work["Fecha_dt"].dt.date <= end)
    ].copy()

    if work.empty:
        return work

    if "Grupo comercial" in work.columns:
        allowed = {
            "Factura",
            "Boleta",
            "Nota de crédito",
        }
        work = work[
            work["Grupo comercial"].isin(allowed)
        ].copy()

    if "VentaMonto_num" not in work.columns:
        work["VentaMonto_num"] = 0.0

    work["VentaMonto_num"] = pd.to_numeric(
        work["VentaMonto_num"],
        errors="coerce",
    ).fillna(0.0).abs()

    work["VentaFirmadaConIVA"] = work["VentaMonto_num"]

    if "Grupo comercial" in work.columns:
        credit_mask = work["Grupo comercial"].eq(
            "Nota de crédito"
        )
        work.loc[
            credit_mask,
            "VentaFirmadaConIVA",
        ] *= -1

    if "Cantidad_num" not in work.columns:
        work["Cantidad_num"] = 0.0

    work["Cantidad_num"] = pd.to_numeric(
        work["Cantidad_num"],
        errors="coerce",
    ).fillna(0.0).abs()

    work["CantidadFirmada"] = work["Cantidad_num"]

    if "Grupo comercial" in work.columns:
        credit_mask = work["Grupo comercial"].eq(
            "Nota de crédito"
        )
        work.loc[
            credit_mask,
            "CantidadFirmada",
        ] *= -1

    if "SKU" in work.columns:
        work["SKU"] = _normalize_sku(work["SKU"])

    return work


def _channel_column(sales: pd.DataFrame | None) -> str | None:
    col = _find_col(
        sales,
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
        sales,
        [
            "marketplace",
            "canal",
            "tienda",
            "origen",
        ],
    )


def _apply_channel(
    sales: pd.DataFrame,
    channel_col: str | None,
    channel_value: str,
) -> pd.DataFrame:
    if (
        sales is None
        or sales.empty
        or not channel_col
        or channel_col not in sales.columns
        or channel_value == "Todos"
    ):
        return sales

    values = (
        sales[channel_col]
        .fillna("Sin canal")
        .astype(str)
        .str.strip()
        .replace("", "Sin canal")
    )

    return sales[
        values.eq(channel_value)
    ].copy()


def _delta_text(
    current: float,
    previous: float,
    suffix: str = "",
) -> tuple[str, str]:
    if previous == 0:
        if current == 0:
            return "Sin variación", "neutral"
        return "Sin base comparable", "neutral"

    delta = ((current - previous) / abs(previous)) * 100

    if delta > 0.05:
        return f"▲ {abs(delta):.1f}%{suffix}", "positive"

    if delta < -0.05:
        return f"▼ {abs(delta):.1f}%{suffix}", "negative"

    return f"• {abs(delta):.1f}%{suffix}", "neutral"


def _status_counts(cons: pd.DataFrame) -> dict[str, int]:
    state = cons.get(
        "Estado",
        pd.Series("", index=cons.index),
    ).fillna("").astype(str)

    return {
        "healthy": int(
            state.eq("🟢 Disponible").sum()
        ),
        "low": int(
            state.eq("🟡 Stock bajo").sum()
        ),
        "zero": int(
            state.isin(
                [
                    "🔴 Sin stock",
                    "🔴 Negativo",
                ]
            ).sum()
        ),
        "risk": int(
            state.eq("🟠 Riesgo despacho").sum()
        ),
    }


def _daily_sales(sales: pd.DataFrame) -> pd.DataFrame:
    if sales is None or sales.empty:
        return pd.DataFrame()

    daily = (
        sales.assign(
            Día=sales["Fecha_dt"].dt.floor("D")
        )
        .groupby("Día", as_index=False)
        .agg(
            Venta=("VentaFirmadaConIVA", "sum"),
            Unidades=("CantidadFirmada", "sum"),
        )
        .sort_values("Día")
    )

    return daily


def _marketplace_data(
    sales: pd.DataFrame,
    channel_col: str | None,
) -> pd.DataFrame:
    if (
        sales is None
        or sales.empty
        or not channel_col
        or channel_col not in sales.columns
    ):
        return pd.DataFrame()

    work = sales.copy()

    work["CanalDashboard"] = (
        work[channel_col]
        .fillna("Sin canal")
        .astype(str)
        .str.strip()
        .replace("", "Sin canal")
    )

    result = (
        work.groupby(
            "CanalDashboard",
            as_index=False,
        )["VentaFirmadaConIVA"]
        .sum()
        .rename(
            columns={
                "CanalDashboard": "Canal",
                "VentaFirmadaConIVA": "Venta",
            }
        )
        .sort_values(
            "Venta",
            ascending=False,
        )
    )

    return result


def _top_products(
    stock: pd.DataFrame | None,
    sales: pd.DataFrame,
    limit: int = 6,
) -> pd.DataFrame:
    if (
        sales is None
        or sales.empty
        or "SKU" not in sales.columns
    ):
        return pd.DataFrame()

    work = (
        sales.groupby(
            "SKU",
            as_index=False,
        )
        .agg(
            Unidades=("CantidadFirmada", "sum"),
            Venta=("VentaFirmadaConIVA", "sum"),
        )
    )

    work["Unidades"] = work["Unidades"].clip(lower=0)

    work = work.sort_values(
        ["Unidades", "Venta"],
        ascending=False,
    ).head(limit)

    if (
        stock is not None
        and not stock.empty
        and "Código" in stock.columns
    ):
        stock_names = stock.copy()
        stock_names["SKU"] = _normalize_sku(
            stock_names["Código"]
        )

        if "Producto" not in stock_names.columns:
            stock_names["Producto"] = stock_names["SKU"]

        names = (
            stock_names[
                [
                    "SKU",
                    "Producto",
                ]
            ]
            .drop_duplicates("SKU")
        )

        work = work.merge(
            names,
            on="SKU",
            how="left",
        )

    if "Producto" not in work.columns:
        work["Producto"] = work["SKU"]

    work["Producto"] = (
        work["Producto"]
        .fillna(work["SKU"])
        .astype(str)
    )

    return work


def _operational_table(
    cons: pd.DataFrame,
    sales_30: pd.DataFrame,
) -> pd.DataFrame:
    if cons is None or cons.empty:
        return pd.DataFrame()

    stock = cons.copy()

    if "Código" not in stock.columns:
        return pd.DataFrame()

    stock["SKU"] = _normalize_sku(
        stock["Código"]
    )

    if "Producto" not in stock.columns:
        stock["Producto"] = stock["SKU"]

    if "Disponible" not in stock.columns:
        stock["Disponible"] = 0

    stock["Disponible"] = pd.to_numeric(
        stock["Disponible"],
        errors="coerce",
    ).fillna(0)

    stock_columns = [
        "SKU",
        "Producto",
        "Disponible",
    ]

    if "Estado" in stock.columns:
        stock_columns.append("Estado")

    stock = (
        stock[stock_columns]
        .drop_duplicates("SKU")
    )

    if (
        sales_30 is not None
        and not sales_30.empty
        and "SKU" in sales_30.columns
    ):
        demand = (
            sales_30.groupby(
                "SKU",
                as_index=False,
            )
            .agg(
                Venta30=("VentaFirmadaConIVA", "sum"),
                Unidades30=("CantidadFirmada", "sum"),
            )
        )

        demand["Unidades30"] = demand[
            "Unidades30"
        ].clip(lower=0)

        stock = stock.merge(
            demand,
            on="SKU",
            how="left",
        )

    if "Venta30" not in stock.columns:
        stock["Venta30"] = 0.0

    if "Unidades30" not in stock.columns:
        stock["Unidades30"] = 0.0

    stock["Venta30"] = pd.to_numeric(
        stock["Venta30"],
        errors="coerce",
    ).fillna(0.0)

    stock["Unidades30"] = pd.to_numeric(
        stock["Unidades30"],
        errors="coerce",
    ).fillna(0.0)

    daily_demand = stock["Unidades30"] / 30.0

    stock["Cobertura"] = (
        stock["Disponible"]
        / daily_demand.where(
            daily_demand > 0
        )
    )

    def priority(row: pd.Series) -> tuple[int, str]:
        available = float(row["Disponible"])
        demand30 = float(row["Unidades30"])
        coverage = row["Cobertura"]

        if demand30 > 0 and available <= 0:
            return 1, "🔴 Crítico"

        if (
            demand30 > 0
            and pd.notna(coverage)
            and coverage <= 7
        ):
            return 2, "🔴 Crítico"

        if demand30 > 0 and available <= 5:
            return 3, "🟠 Reponer"

        if (
            demand30 > 0
            and pd.notna(coverage)
            and coverage <= 15
        ):
            return 4, "🟡 Atención"

        if demand30 == 0 and available > 0:
            return 6, "⚪ Sin venta 30d"

        return 5, "🟢 Saludable"

    priorities = stock.apply(
        priority,
        axis=1,
        result_type="expand",
    )

    stock["PrioridadOrden"] = priorities[0]
    stock["Prioridad"] = priorities[1]

    stock["Cobertura días"] = stock["Cobertura"].apply(
        lambda value: (
            "—"
            if pd.isna(value)
            else f"{value:.1f}"
        )
    )

    stock["Stock"] = (
        stock["Disponible"]
        .round()
        .astype(int)
    )

    stock["Unidades 30d"] = (
        stock["Unidades30"]
        .round()
        .astype(int)
    )

    stock["Ventas 30d"] = stock["Venta30"].apply(
        _money
    )

    result = (
        stock.sort_values(
            [
                "PrioridadOrden",
                "Unidades30",
                "Disponible",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .head(15)
        [
            [
                "Prioridad",
                "SKU",
                "Producto",
                "Stock",
                "Unidades 30d",
                "Ventas 30d",
                "Cobertura días",
            ]
        ]
    )

    return result


def _kpi_card(
    label: str,
    value: str,
    helper: str,
    icon: str,
    tone: str = "lime",
    delta: str | None = None,
    delta_tone: str = "neutral",
) -> str:
    delta_html = ""

    if delta:
        delta_html = (
            f"<span class='mx-kpi-delta {delta_tone}'>"
            f"{escape(delta)}"
            f"</span>"
        )

    return f"""
    <div class="mx-kpi">
        <div class="mx-kpi-top">
            <div class="mx-kpi-icon {tone}">
                {escape(icon)}
            </div>
            {delta_html}
        </div>
        <div class="mx-kpi-label">{escape(label)}</div>
        <div class="mx-kpi-value">{escape(value)}</div>
        <div class="mx-kpi-helper">{escape(helper)}</div>
    </div>
    """


# ============================================================
# VISUAL HELPERS — HOME V2
# ============================================================

def _home_css():
    st.markdown(
        """
        <style>
        /* =====================================================
           MARITEX HOME — VISUAL EJECUTIVO CLARO
           ===================================================== */
        .block-container {
            padding-top: .75rem !important;
            padding-bottom: 2rem !important;
            max-width: 1600px !important;
        }

        .mx2-head {
            display:flex;
            align-items:flex-start;
            justify-content:space-between;
            gap:22px;
            margin: 2px 0 14px 0;
        }
        .mx2-greeting {
            font-size: 28px;
            line-height: 1.05;
            font-weight: 800;
            color:#111827;
            letter-spacing:-0.6px;
            margin:0;
        }
        .mx2-subtitle {
            margin-top:7px;
            color:#7b8490;
            font-size:13px;
        }
        .mx2-pill {
            display:inline-flex;
            align-items:center;
            gap:8px;
            padding:9px 12px;
            border:1px solid #e7ebef;
            border-radius:10px;
            background:#fff;
            color:#5f6875;
            font-size:12px;
            box-shadow:0 2px 10px rgba(17,24,39,.03);
            white-space:nowrap;
        }
        .mx2-pill-dot {
            width:8px;height:8px;border-radius:50%;
            background:#7fc600;
            box-shadow:0 0 0 4px rgba(127,198,0,.11);
        }

        .mx2-kpi-grid {
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:12px;
            margin:10px 0 16px 0;
        }
        .mx2-kpi {
            min-height:108px;
            min-width:0;
            overflow:hidden;
            border:1px solid #e7ebef;
            border-radius:14px;
            background:#fff;
            padding:15px 15px 13px 15px;
            box-shadow:0 4px 18px rgba(17,24,39,.035);
        }
        .mx2-kpi-row {
            display:flex;
            align-items:center;
            gap:13px;
        }
        .mx2-kpi-icon {
            width:44px;height:44px;
            min-width:44px;
            border-radius:50%;
            display:flex;
            align-items:center;
            justify-content:center;
            background:#fff2c9;
            color:#111827;
            font-size:20px;
            font-weight:800;
        }
        .mx2-kpi-label {
            font-size:11px;
            font-weight:800;
            color:#202630;
            letter-spacing:.15px;
            text-transform:uppercase;
        }
        .mx2-kpi-value {
            margin-top:4px;
            color:#111827;
            font-size:clamp(17px, 1.20vw, 21px);
            line-height:1.08;
            font-weight:800;
            letter-spacing:-.25px;
            white-space:nowrap;
            overflow:visible;
            max-width:100%;
        }
        .mx2-kpi-delta {
            margin-top:7px;
            font-size:9.5px;
            line-height:1.25;
            color:#7b8490;
            padding-left:57px;
            min-height:22px;
        }
        .mx2-kpi-delta .positive { color:#14a44d;font-weight:700; }
        .mx2-kpi-delta .negative { color:#e43d3d;font-weight:700; }
        .mx2-kpi-delta .neutral { color:#7b8490;font-weight:700; }

        .mx2-card-head {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:16px;
            padding:2px 1px 10px 1px;
        }
        .mx2-card-title {
            color:#18202a;
            font-size:13px;
            font-weight:800;
            text-transform:uppercase;
            letter-spacing:.12px;
        }
        .mx2-card-sub {
            display:block;
            margin-top:3px;
            color:#8a929d;
            font-size:11px;
            font-weight:400;
            text-transform:none;
            letter-spacing:0;
        }
        .mx2-link {
            color:#e9a900;
            font-size:11px;
            font-weight:800;
            white-space:nowrap;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color:#e7ebef !important;
            border-radius:14px !important;
            background:#fff !important;
            box-shadow:0 4px 18px rgba(17,24,39,.035) !important;
        }

        .mx2-inventory-shell {
            display:grid;
            grid-template-columns:.76fr 1.35fr 1.25fr;
            border:1px solid #edf0f3;
            border-radius:11px;
            overflow:hidden;
            margin-top:2px;
            min-height:255px;
        }
        .mx2-inv-side {
            padding:19px 18px;
            border-right:1px solid #edf0f3;
        }
        .mx2-inv-metric + .mx2-inv-metric {
            margin-top:28px;
            padding-top:22px;
            border-top:1px solid #edf0f3;
        }
        .mx2-inv-label {
            color:#5f6874;font-size:11px;font-weight:600;
        }
        .mx2-inv-number {
            color:#111827;font-size:26px;font-weight:800;margin-top:6px;
        }
        .mx2-inv-helper {
            color:#8b949f;font-size:10px;margin-top:3px;
        }
        .mx2-warehouse {
            padding:17px 17px;
            border-right:1px solid #edf0f3;
        }
        .mx2-small-title {
            color:#232a34;font-size:11px;font-weight:800;margin-bottom:16px;
        }
        .mx2-wh-row {
            display:grid;
            grid-template-columns:88px minmax(70px,1fr) 62px;
            align-items:center;
            gap:9px;
            margin:14px 0;
            font-size:10px;
            color:#424b56;
        }
        .mx2-bar {
            height:10px;
            border-radius:2px;
            background:#f1f3f5;
            overflow:hidden;
        }
        .mx2-bar > i {
            display:block;
            height:100%;
            background:#f7b900;
            border-radius:2px;
        }
        .mx2-donut-side { padding:17px 17px; }

        .mx2-status-legend {
            display:grid;
            grid-template-columns:1fr;
            gap:8px;
            margin-top:2px;
        }
        .mx2-status-item {
            display:grid;
            grid-template-columns:10px 1fr auto;
            align-items:center;
            gap:8px;
            font-size:10px;
            color:#535d69;
        }
        .mx2-status-item i { width:8px;height:8px;border-radius:50%;display:block; }
        .mx2-status-item strong { color:#111827;font-size:11px; }

        .mx2-sales-foot {
            display:grid;
            grid-template-columns:repeat(4,1fr);
            gap:8px;
            margin-top:6px;
        }
        .mx2-sales-mini {
            border:1px solid #edf0f3;
            border-radius:9px;
            padding:10px 11px;
            background:#fff;
        }
        .mx2-sales-mini span {
            color:#7e8792;font-size:9px;display:block;margin-bottom:5px;
        }
        .mx2-sales-mini strong {
            color:#111827;
            font-size:12.5px;
            white-space:nowrap;
        }

        .mx2-product-table {
            width:100%;
            border-collapse:collapse;
            font-size:10px;
        }
        .mx2-product-table th {
            text-align:left;
            color:#737d89;
            font-weight:600;
            background:#fafbfc;
            padding:8px 7px;
            border-bottom:1px solid #edf0f3;
        }
        .mx2-product-table td {
            padding:9px 7px;
            border-bottom:1px solid #f0f2f4;
            color:#303944;
            vertical-align:middle;
        }
        .mx2-product-table td.num { text-align:right; }
        .mx2-product-table tr:last-child td { border-bottom:0; }

        .mx2-alert-list { margin-top:1px; }
        .mx2-alert-row {
            display:grid;
            grid-template-columns:38px 46px 1fr 18px;
            align-items:center;
            gap:8px;
            padding:12px 2px;
            border-bottom:1px solid #edf0f3;
        }
        .mx2-alert-row:last-child { border-bottom:0; }
        .mx2-alert-ico {
            width:30px;height:30px;border-radius:50%;
            display:flex;align-items:center;justify-content:center;
            font-weight:800;font-size:13px;
        }
        .mx2-alert-ico.red { background:#ffe2e2;color:#e73535; }
        .mx2-alert-ico.yellow { background:#fff0c7;color:#e8a900; }
        .mx2-alert-ico.blue { background:#e5f0ff;color:#3274c8; }
        .mx2-alert-n {
            color:#111827;
            font-size:20px;
            font-weight:800;
        }
        .mx2-alert-text strong {
            display:block;color:#202833;font-size:10px;margin-bottom:2px;
        }
        .mx2-alert-text span { color:#8a929c;font-size:9px; }
        .mx2-arrow { color:#7a838e;font-size:17px; }

        .mx2-repo-table {
            width:100%;
            border-collapse:collapse;
            font-size:9.5px;
        }
        .mx2-repo-table th {
            color:#717b86;
            background:#fafbfc;
            font-weight:600;
            padding:8px 6px;
            text-align:left;
            border-bottom:1px solid #edf0f3;
        }
        .mx2-repo-table td {
            padding:9px 6px;
            color:#333d48;
            border-bottom:1px solid #f0f2f4;
        }
        .mx2-repo-table td.num { text-align:right; }
        .mx2-repo-table td.miss { color:#e03636;font-weight:800; }
        .mx2-repo-table tr:last-child td { border-bottom:0; }

        .mx2-bottom-grid {
            display:grid;
            grid-template-columns:1.28fr .90fr 1.28fr;
            gap:16px;
            margin-top:16px;
            align-items:stretch;
        }
        .mx2-bottom-card {
            min-width:0;
            min-height:315px;
            height:100%;
            border:1px solid #e7ebef;
            border-radius:14px;
            background:#fff;
            padding:16px 18px;
            box-shadow:0 4px 18px rgba(17,24,39,.035);
            overflow:hidden;
        }
        .mx2-bottom-card .mx2-empty {
            min-height:225px;
        }
        .mx2-bottom-card .mx2-alert-row {
            padding:10px 1px;
        }
        .mx2-bottom-card .mx2-alert-text span {
            line-height:1.25;
        }

        .mx2-empty {
            min-height:160px;
            display:flex;align-items:center;justify-content:center;
            text-align:center;color:#8b949f;font-size:12px;
        }
        .mx2-foot {
            text-align:center;
            color:#98a0aa;
            font-size:10px;
            margin-top:16px;
        }

        [data-testid="stHorizontalBlock"] {
            gap: 1rem !important;
        }

        [data-testid="stDateInput"],
        [data-testid="stSelectbox"] {
            margin-bottom: 2px !important;
        }

        [data-testid="stDateInput"] label,
        [data-testid="stSelectbox"] label {
            color:#7c8590 !important;
            font-size:11px !important;
            font-weight:600 !important;
        }
        div[data-baseweb="select"] > div,
        [data-testid="stDateInput"] input {
            border-color:#e5e9ed !important;
            border-radius:10px !important;
            background:#fff !important;
        }

        @media (max-width: 1250px) {
            .mx2-kpi-grid { grid-template-columns:repeat(3,1fr); }
            .mx2-bottom-grid { grid-template-columns:1fr 1fr; }
        }
        @media (max-width: 900px) {
            .mx2-kpi-grid { grid-template-columns:repeat(2,1fr); }
            .mx2-inventory-shell { grid-template-columns:1fr; }
            .mx2-inv-side,.mx2-warehouse { border-right:0;border-bottom:1px solid #edf0f3; }
            .mx2-sales-foot { grid-template-columns:repeat(2,1fr); }
            .mx2-bottom-grid { grid-template-columns:1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _warehouse_summary(raw: pd.DataFrame | None) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Bodega", "Stock"])

    warehouse_col = _find_col(raw, ["Bodega", "Sucursal", "Warehouse"])
    if not warehouse_col:
        warehouse_col = _find_contains(raw, ["bodega", "sucursal", "warehouse"])

    value_col = _find_col(raw, ["Stock", "Disponible", "Stock Proyectado"])
    if not value_col:
        value_col = _find_contains(raw, ["stock", "disponible"])

    if not warehouse_col or not value_col:
        return pd.DataFrame(columns=["Bodega", "Stock"])

    work = raw[[warehouse_col, value_col]].copy()
    work[warehouse_col] = (
        work[warehouse_col].fillna("Sin bodega").astype(str).str.strip()
    )
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce").fillna(0.0)
    work[value_col] = work[value_col].clip(lower=0)

    return (
        work.groupby(warehouse_col, as_index=False)[value_col]
        .sum()
        .rename(columns={warehouse_col: "Bodega", value_col: "Stock"})
        .sort_values("Stock", ascending=False)
    )


def _gross_margin(sales: pd.DataFrame) -> tuple[float | None, str]:
    if sales is None or sales.empty:
        return None, "Sin ventas"

    cost_col = _find_col(
        sales,
        [
            "CostoTotal",
            "Costo Total",
            "Costo",
            "CostoVenta",
            "Costo Venta",
            "Costo_num",
        ],
    )
    # No usar búsqueda parcial por "costo": podría confundir "CentroCosto"
    # con una columna monetaria de costo.
    if not cost_col:
        return None, "Costo no disponible"

    cost = pd.to_numeric(sales[cost_col], errors="coerce").fillna(0.0).abs()
    revenue = pd.to_numeric(
        sales.get("VentaFirmadaConIVA", 0),
        errors="coerce",
    ).fillna(0.0)
    margin = float(revenue.sum() - cost.sum())
    return margin, "Venta neta menos costo"


def _kpi_v2(label, value, icon, delta_text="", delta_tone="neutral"):
    delta_html = ""
    if delta_text:
        comparative = (
            f"{escape(delta_text)} vs período anterior"
            if delta_text.startswith(("▲", "▼", "•"))
            else escape(delta_text)
        )
        delta_html = (
            f"<div class='mx2-kpi-delta'>"
            f"<span class='{escape(delta_tone)}'>{comparative}</span>"
            f"</div>"
        )

    return f"""
    <div class="mx2-kpi">
        <div class="mx2-kpi-row">
            <div class="mx2-kpi-icon">{escape(icon)}</div>
            <div style="min-width:0;">
                <div class="mx2-kpi-label">{escape(label)}</div>
                <div class="mx2-kpi-value">{escape(value)}</div>
            </div>
        </div>
        {delta_html}
    </div>
    """


def _safe_doc_count(sales: pd.DataFrame) -> int:
    if sales is None or sales.empty:
        return 0
    doc_col = _find_col(sales, ["Numero", "NroComprobante", "N° Documento", "Documento"])
    if doc_col and doc_col in sales.columns:
        return int(sales[doc_col].dropna().astype(str).nunique())
    return len(sales)


def _best_day(daily: pd.DataFrame):
    if daily is None or daily.empty:
        return 0.0, "—"
    row = daily.loc[daily["Venta"].idxmax()]
    day = pd.to_datetime(row["Día"], errors="coerce")
    label = day.strftime("%d/%m") if pd.notna(day) else "—"
    return float(row["Venta"]), label


def _inventory_html(warehouse: pd.DataFrame, stock_units: int, sku_active: int):
    if warehouse.empty:
        wh_html = "<div class='mx2-empty'>Sin detalle por bodega.</div>"
    else:
        max_stock = max(float(warehouse["Stock"].max()), 1.0)
        rows = []
        for row in warehouse.head(5).itertuples(index=False):
            value = max(float(row.Stock), 0.0)
            width = min(value / max_stock * 100, 100)
            rows.append(
                f"""
                <div class="mx2-wh-row">
                    <span>{escape(str(row.Bodega)[:22])}</span>
                    <div class="mx2-bar"><i style="width:{width:.1f}%"></i></div>
                    <strong>{_fmt_int(value)}</strong>
                </div>
                """
            )
        wh_html = "".join(rows)

    return f"""
    <div class="mx2-inventory-shell">
        <div class="mx2-inv-side">
            <div class="mx2-inv-metric">
                <div class="mx2-inv-label">Stock total</div>
                <div class="mx2-inv-number">{_fmt_int(stock_units)}</div>
                <div class="mx2-inv-helper">unidades disponibles</div>
            </div>
            <div class="mx2-inv-metric">
                <div class="mx2-inv-label">SKUs activos</div>
                <div class="mx2-inv-number">{_fmt_int(sku_active)}</div>
                <div class="mx2-inv-helper">con disponibilidad</div>
            </div>
        </div>
        <div class="mx2-warehouse">
            <div class="mx2-small-title">Stock por bodega</div>
            {wh_html}
        </div>
        <div class="mx2-donut-side">
            <div class="mx2-small-title">Estado del inventario (SKUs)</div>
            <div id="mx2-donut-target"></div>
        </div>
    </div>
    """


def _top_products_html(top: pd.DataFrame, total_revenue: float) -> str:
    if top is None or top.empty:
        return "<div class='mx2-empty'>No hay ventas por SKU disponibles.</div>"

    rows = []
    for row in top.head(5).itertuples(index=False):
        sale = max(float(getattr(row, "Venta", 0.0)), 0.0)
        units = max(float(getattr(row, "Unidades", 0.0)), 0.0)
        share = sale / total_revenue * 100 if total_revenue > 0 else 0
        rows.append(
            f"""
            <tr>
                <td>{escape(str(getattr(row, "Producto", ""))[:42])}</td>
                <td>{escape(str(getattr(row, "SKU", "")))}</td>
                <td class="num">{_fmt_int(units)}</td>
                <td class="num">{_money(sale)}</td>
                <td class="num">{share:.1f}%</td>
            </tr>
            """
        )

    return f"""
    <table class="mx2-product-table">
        <thead>
            <tr>
                <th>Producto</th>
                <th>SKU</th>
                <th style="text-align:right">Unidades</th>
                <th style="text-align:right">Venta neta</th>
                <th style="text-align:right">% total</th>
            </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
    </table>
    """


def _repo_html(operational: pd.DataFrame) -> str:
    if operational is None or operational.empty:
        return "<div class='mx2-empty'>Sin reposiciones críticas.</div>"

    work = operational.copy()
    work = work[
        work["Prioridad"].astype(str).str.contains(
            "Crítico|Reponer|Atención",
            regex=True,
            na=False,
        )
    ].head(5)

    if work.empty:
        return "<div class='mx2-empty'>No hay reposiciones prioritarias.</div>"

    rows = []
    for _, row in work.iterrows():
        stock = int(pd.to_numeric(row.get("Stock", 0), errors="coerce") or 0)
        units_30 = int(pd.to_numeric(row.get("Unidades 30d", 0), errors="coerce") or 0)

        # Objetivo simple: 15 días de demanda, con mínimo operativo de 6 unidades.
        objective = max(6, int(round(units_30 / 30.0 * 15)))
        missing = max(objective - stock, 0)

        product = str(row.get("Producto", ""))
        sku = str(row.get("SKU", ""))

        rows.append(
            f"""
            <tr>
                <td>{escape(product[:34])}</td>
                <td>{escape(sku)}</td>
                <td class="num">{stock}</td>
                <td class="num">{objective}</td>
                <td class="num miss">{missing}</td>
            </tr>
            """
        )

    return f"""
    <table class="mx2-repo-table">
        <thead>
            <tr>
                <th>Producto</th>
                <th>SKU</th>
                <th style="text-align:right">Stock actual</th>
                <th style="text-align:right">Stock objetivo</th>
                <th style="text-align:right">Faltante</th>
            </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
    </table>
    """


# ============================================================
# RENDER
# ============================================================

def render(ctx):
    _home_css()

    raw = ctx.get("stock_normalized")
    cons = ctx.get("stock_consolidated")
    sales_df = ctx.get("sales_df")
    stock_meta = ctx.get("stock_meta") or {}
    sales_meta = ctx.get("sales_meta") or {}

    default_start, default_end = _period_from_sales(sales_df)

    if "home_period_v2" not in st.session_state:
        st.session_state.home_period_v2 = (default_start, default_end)

    # HEADER + FILTERS — misma fila, como el mockup
    h_left, h_period, h_wh = st.columns([1.75, .74, .64], gap="medium")

    with h_left:
        render_html(
            f"""
            <div style="padding-top:8px;">
                <div class="mx2-greeting">¡Buenos días! 👋</div>
                <div class="mx2-subtitle">
                    Resumen general de la operación al {default_end.strftime("%d/%m/%Y")}
                </div>
            </div>
            """
        )

    with h_period:
        period = st.date_input(
            "Período",
            value=st.session_state.home_period_v2,
            key="home_period_v2_picker",
            format="DD/MM/YYYY",
        )
        if isinstance(period, (tuple, list)) and len(period) == 2:
            start, end = period
        else:
            start = end = period
        st.session_state.home_period_v2 = (start, end)

    warehouse = _warehouse_summary(raw)
    wh_options = ["Todas las bodegas"] + warehouse["Bodega"].astype(str).tolist()

    with h_wh:
        selected_wh = st.selectbox(
            "Bodega",
            wh_options,
            index=0,
            key="home_warehouse_v2",
        )

    # SALES
    current_sales = _prepare_sales(sales_df, start, end)
    days = max((end - start).days + 1, 1)

    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    previous_sales = _prepare_sales(sales_df, prev_start, prev_end)

    current_revenue = float(
        current_sales.get("VentaFirmadaConIVA", pd.Series(dtype="float64")).sum()
    )
    previous_revenue = float(
        previous_sales.get("VentaFirmadaConIVA", pd.Series(dtype="float64")).sum()
    )
    current_units = max(
        float(current_sales.get("CantidadFirmada", pd.Series(dtype="float64")).sum()),
        0.0,
    )
    previous_units = max(
        float(previous_sales.get("CantidadFirmada", pd.Series(dtype="float64")).sum()),
        0.0,
    )

    sales_delta, sales_tone = _delta_text(current_revenue, previous_revenue)
    units_delta, units_tone = _delta_text(current_units, previous_units)

    if cons is None or cons.empty:
        render_html(
            "<div class='mx2-empty'>No hay inventario consolidado disponible.</div>"
        )
        return

    counts = _status_counts(cons)
    stock_series = _num(cons, "Disponible").clip(lower=0)
    stock_units = int(round(stock_series.sum()))
    sku_total = int(cons["Código"].nunique()) if "Código" in cons.columns else len(cons)
    sku_active = int((stock_series > 0).sum())

    rotation = current_units / stock_units if stock_units > 0 else 0.0
    prev_rotation = previous_units / stock_units if stock_units > 0 else 0.0
    rotation_delta, rotation_tone = _delta_text(rotation, prev_rotation)

    margin_value, margin_helper = _gross_margin(current_sales)
    if margin_value is None:
        margin_display = "—"
        margin_delta = margin_helper
        margin_tone = "neutral"
    else:
        prev_margin, _ = _gross_margin(previous_sales)
        margin_display = _money_compact(margin_value)
        if prev_margin is None:
            margin_delta, margin_tone = "Sin base comparable", "neutral"
        else:
            margin_delta, margin_tone = _delta_text(margin_value, prev_margin)

    # KPI ROW
    kpis = "".join(
        [
            _kpi_v2("VENTA NETA", _money_compact(current_revenue), "↗", sales_delta, sales_tone),
            _kpi_v2("UNIDADES VENDIDAS", _fmt_int(current_units), "▣", units_delta, units_tone),
            _kpi_v2("MARGEN BRUTO", margin_display, "$", margin_delta, margin_tone),
            _kpi_v2("SKUs ACTIVOS", _fmt_int(sku_active), "◇", f"{_fmt_int(sku_total)} SKU totales", "neutral"),
            _kpi_v2("ROTACIÓN PROMEDIO", f"{rotation:.2f}", "↻", rotation_delta, rotation_tone),
        ]
    )
    render_html(f"<div class='mx2-kpi-grid'>{kpis}</div>")

    # MAIN ROW
    left, right = st.columns([1.58, 1.0], gap="medium")

    with left:
        with st.container(border=True):
            render_html(
                """
                <div class="mx2-card-head">
                    <div class="mx2-card-title">▣ &nbsp; Resumen de inventario</div>
                    <div class="mx2-link">Ver detalle →</div>
                </div>
                """
            )

            inv_left, inv_right = st.columns([1.62, .98], gap="small")

            with inv_left:
                # Inventory side + warehouse bars (without donut placeholder)
                if warehouse.empty:
                    wh_html = "<div class='mx2-empty'>Sin detalle por bodega.</div>"
                else:
                    max_stock = max(float(warehouse["Stock"].max()), 1.0)
                    rows = []
                    wh_view = warehouse.copy()
                    if selected_wh != "Todas las bodegas":
                        wh_view = wh_view[wh_view["Bodega"].astype(str).eq(selected_wh)]
                    for row in wh_view.head(5).itertuples(index=False):
                        val = max(float(row.Stock), 0.0)
                        width = min(val / max_stock * 100, 100)
                        rows.append(
                            f"""
                            <div class="mx2-wh-row">
                                <span>{escape(str(row.Bodega)[:22])}</span>
                                <div class="mx2-bar"><i style="width:{width:.1f}%"></i></div>
                                <strong>{_fmt_int(val)}</strong>
                            </div>
                            """
                        )
                    wh_html = "".join(rows)

                render_html(
                    f"""
                    <div style="display:grid;grid-template-columns:.7fr 1.3fr;border:1px solid #edf0f3;border-radius:11px;overflow:hidden;min-height:255px;">
                        <div class="mx2-inv-side">
                            <div class="mx2-inv-metric">
                                <div class="mx2-inv-label">Stock total</div>
                                <div class="mx2-inv-number">{_fmt_int(stock_units)}</div>
                                <div class="mx2-inv-helper">unidades</div>
                            </div>
                            <div class="mx2-inv-metric">
                                <div class="mx2-inv-label">SKUs activos</div>
                                <div class="mx2-inv-number">{_fmt_int(sku_active)}</div>
                                <div class="mx2-inv-helper">con stock</div>
                            </div>
                        </div>
                        <div class="mx2-warehouse" style="border-right:0;">
                            <div class="mx2-small-title">Stock por bodega</div>
                            {wh_html}
                        </div>
                    </div>
                    """
                )

            with inv_right:
                render_html("<div class='mx2-small-title'>Estado del inventario (SKUs)</div>")
                status_df = pd.DataFrame(
                    {
                        "Estado": ["Saludable", "Bajo", "Riesgo", "Crítico"],
                        "SKU": [
                            counts["healthy"],
                            counts["low"],
                            counts["risk"],
                            counts["zero"],
                        ],
                    }
                )
                status_df = status_df[status_df["SKU"] > 0].copy()

                if status_df.empty:
                    render_html("<div class='mx2-empty'>Sin estados disponibles.</div>")
                else:
                    donut = (
                        alt.Chart(status_df)
                        .mark_arc(innerRadius=57, outerRadius=84, cornerRadius=2)
                        .encode(
                            theta=alt.Theta("SKU:Q"),
                            color=alt.Color(
                                "Estado:N",
                                scale=alt.Scale(
                                    domain=["Saludable", "Bajo", "Riesgo", "Crítico"],
                                    range=["#79bd45", "#f4b900", "#f28c28", "#e83c3c"],
                                ),
                                legend=None,
                            ),
                            tooltip=[
                                alt.Tooltip("Estado:N", title="Estado"),
                                alt.Tooltip("SKU:Q", title="SKU", format=",.0f"),
                            ],
                        )
                        .properties(height=132)
                    )
                    st.altair_chart(donut, use_container_width=True)

                    total_status = max(int(status_df["SKU"].sum()), 1)
                    legend = ""
                    colors = {
                        "Saludable": "#79bd45",
                        "Bajo": "#f4b900",
                        "Riesgo": "#f28c28",
                        "Crítico": "#e83c3c",
                    }
                    for row in status_df.itertuples(index=False):
                        pct = row.SKU / total_status * 100
                        legend += (
                            f"<div class='mx2-status-item'>"
                            f"<i style='background:{colors[row.Estado]}'></i>"
                            f"<span>{escape(row.Estado)}</span>"
                            f"<strong>{pct:.0f}%</strong>"
                            f"</div>"
                        )
                    render_html(f"<div class='mx2-status-legend'>{legend}</div>")

    with right:
        with st.container(border=True):
            render_html(
                """
                <div class="mx2-card-head">
                    <div class="mx2-card-title">
                        Ventas netas
                        <span class="mx2-card-sub">Evolución del período seleccionado</span>
                    </div>
                    <div class="mx2-link">Ver detalle →</div>
                </div>
                """
            )

            daily = _daily_sales(current_sales)
            if daily.empty:
                render_html("<div class='mx2-empty'>No hay ventas para el período.</div>")
            else:
                chart = (
                    alt.Chart(daily)
                    .mark_area(
                        line={"color": "#f2b300", "strokeWidth": 2.2},
                        color={
                            "x1": 1,
                            "y1": 1,
                            "x2": 1,
                            "y2": 0,
                            "gradient": "linear",
                            "stops": [
                                {"offset": 0, "color": "#ffffff"},
                                {"offset": 1, "color": "#fff4c9"},
                            ],
                        },
                        opacity=0.62,
                    )
                    .encode(
                        x=alt.X(
                            "Día:T",
                            title=None,
                            axis=alt.Axis(
                                format="%d %b",
                                labelColor="#7b8490",
                                domain=False,
                                tickColor="#edf0f3",
                                labelAngle=0,
                            ),
                        ),
                        y=alt.Y(
                            "Venta:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7b8490",
                                domain=False,
                                gridColor="#edf0f3",
                                format="~s",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("Día:T", title="Fecha", format="%d/%m/%Y"),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                    .properties(height=190)
                )
                st.altair_chart(chart, use_container_width=True)

            avg_daily = current_revenue / days
            best_value, best_label = _best_day(daily)
            days_with_sales = int((daily["Venta"] != 0).sum()) if not daily.empty else 0
            docs = _safe_doc_count(current_sales)
            ticket = current_revenue / docs if docs > 0 else 0.0

            render_html(
                f"""
                <div class="mx2-sales-foot">
                    <div class="mx2-sales-mini">
                        <span>Promedio diario</span>
                        <strong>{_money(avg_daily)}</strong>
                    </div>
                    <div class="mx2-sales-mini">
                        <span>Mejor día</span>
                        <strong>{_money(best_value)}</strong>
                        <span style="margin:3px 0 0">{escape(best_label)}</span>
                    </div>
                    <div class="mx2-sales-mini">
                        <span>Días con ventas</span>
                        <strong>{days_with_sales} / {days}</strong>
                    </div>
                    <div class="mx2-sales-mini">
                        <span>Ticket promedio</span>
                        <strong>{_money(ticket)}</strong>
                    </div>
                </div>
                """
            )

    # 30-DAY OPERATIONAL DATA
    sales_30 = _prepare_sales(sales_df, end - timedelta(days=29), end)
    operational = _operational_table(cons, sales_30)
    critical_count = (
        int(
            operational["Prioridad"]
            .astype(str)
            .str.contains("Crítico", regex=False)
            .sum()
        )
        if not operational.empty
        else 0
    )

    no_sales_count = (
        int(
            operational["Prioridad"]
            .astype(str)
            .str.contains("Sin venta", regex=False)
            .sum()
        )
        if not operational.empty
        else 0
    )

    # BOTTOM ROW — una sola grilla HTML para que las 3 tarjetas
    # queden perfectamente alineadas y con la misma altura.
    top = _top_products(raw, current_sales, limit=5)
    top_html = _top_products_html(top, current_revenue)
    repo_html = _repo_html(operational)

    alerts_html = f"""
    <div class="mx2-alert-list">
        <div class="mx2-alert-row">
            <div class="mx2-alert-ico red">×</div>
            <div class="mx2-alert-n">{_fmt_int(counts["zero"])}</div>
            <div class="mx2-alert-text">
                <strong>SKUs sin stock</strong>
                <span>Requieren reposición urgente</span>
            </div>
            <div class="mx2-arrow">→</div>
        </div>
        <div class="mx2-alert-row">
            <div class="mx2-alert-ico yellow">!</div>
            <div class="mx2-alert-n">{_fmt_int(counts["low"])}</div>
            <div class="mx2-alert-text">
                <strong>SKUs con stock bajo</strong>
                <span>Disponibilidad ≤ 5 unidades</span>
            </div>
            <div class="mx2-arrow">→</div>
        </div>
        <div class="mx2-alert-row">
            <div class="mx2-alert-ico yellow">↻</div>
            <div class="mx2-alert-n">{_fmt_int(critical_count)}</div>
            <div class="mx2-alert-text">
                <strong>SKUs con cobertura crítica</strong>
                <span>Demanda de últimos 30 días</span>
            </div>
            <div class="mx2-arrow">→</div>
        </div>
        <div class="mx2-alert-row">
            <div class="mx2-alert-ico blue">▣</div>
            <div class="mx2-alert-n">{_fmt_int(no_sales_count)}</div>
            <div class="mx2-alert-text">
                <strong>Sin venta reciente</strong>
                <span>Revisar rotación del inventario</span>
            </div>
            <div class="mx2-arrow">→</div>
        </div>
    </div>
    """

    render_html(
        f"""
        <div class="mx2-bottom-grid">
            <div class="mx2-bottom-card">
                <div class="mx2-card-head">
                    <div class="mx2-card-title">Top 5 productos por ventas</div>
                </div>
                {top_html}
            </div>

            <div class="mx2-bottom-card">
                <div class="mx2-card-head">
                    <div class="mx2-card-title">Alertas de inventario</div>
                    <div class="mx2-link">Ver todas →</div>
                </div>
                {alerts_html}
            </div>

            <div class="mx2-bottom-card">
                <div class="mx2-card-head">
                    <div class="mx2-card-title">Reposiciones pendientes</div>
                    <div class="mx2-link">Ver todas →</div>
                </div>
                {repo_html}
            </div>
        </div>
        """
    )

    stock_source = (
        stock_meta.get("loaded_at")
        or stock_meta.get("generated_at")
        or stock_meta.get("filename")
        or "Fuente activa"
    )
    sales_source = (
        sales_meta.get("loaded_at")
        or sales_meta.get("filename")
        or "Fuente activa"
    )
    render_html(
        f"""
        <div class="mx2-foot">
            Stock: {escape(str(stock_source))} &nbsp; · &nbsp;
            Ventas: {escape(str(sales_source))}
            <br>© 2026 Maritex. Todos los derechos reservados.
        </div>
        """
    )
