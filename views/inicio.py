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


def _client_column(df: pd.DataFrame | None) -> str | None:
    return _find_exact(
        df,
        [
            "Cliente",
            "RazonSocial",
            "Razón Social",
            "Nombre Cliente",
            "NombreCliente",
            "Cliente Nombre",
        ],
    ) or _find_contains(df, ["cliente", "razon social", "razón social"])


def _rut_column(df: pd.DataFrame | None) -> str | None:
    return _find_exact(
        df,
        ["Rut", "RUT", "RutCliente", "RUT Cliente", "ClienteRut"],
    ) or _find_contains(df, ["rut"])


def _seller_column(df: pd.DataFrame | None) -> str | None:
    return _find_exact(
        df,
        [
            "Vendedor",
            "Nombre Vendedor",
            "NombreVendedor",
            "Ejecutivo",
            "Ejecutivo Comercial",
        ],
    ) or _find_contains(df, ["vendedor", "ejecutivo"])


def _category_column(df: pd.DataFrame | None) -> str | None:
    return _find_exact(
        df,
        [
            "Categoria",
            "Categoría",
            "Categoria Producto",
            "Categoría Producto",
            "Familia",
            "Linea",
            "Línea",
        ],
    ) or _find_contains(df, ["categoria", "categoría", "familia", "linea", "línea"])


def _prepare_sales_all(sales_df: pd.DataFrame | None) -> pd.DataFrame:
    if sales_df is None or sales_df.empty:
        return pd.DataFrame()

    date_col = _find_exact(
        sales_df,
        ["Fecha_dt", "Fecha", "Fecha Emision", "FechaEmision"],
    )
    if not date_col:
        return pd.DataFrame()

    dates = pd.to_datetime(sales_df[date_col], errors="coerce", dayfirst=True)
    valid = dates.dropna()
    if valid.empty:
        return pd.DataFrame()

    return _prepare_sales(sales_df, valid.min().date(), valid.max().date())


def _sales_documents(sales: pd.DataFrame) -> int:
    if sales is None or sales.empty:
        return 0
    doc_col = _document_column(sales)
    if doc_col and doc_col in sales.columns:
        return int(sales[doc_col].nunique())
    return int(len(sales))


def _active_clients(sales: pd.DataFrame) -> int:
    if sales is None or sales.empty:
        return 0

    rut_col = _rut_column(sales)
    if rut_col and rut_col in sales.columns:
        return int(
            sales[rut_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )

    client_col = _client_column(sales)
    if client_col and client_col in sales.columns:
        return int(
            sales[client_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )

    return 0


def _seller_summary(sales: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    seller_col = _seller_column(sales)
    if sales is None or sales.empty or not seller_col or seller_col not in sales.columns:
        return pd.DataFrame(columns=["Vendedor", "Venta"])

    work = sales[[seller_col, "VentaDashboard"]].copy()
    work[seller_col] = (
        work[seller_col].fillna("Sin vendedor").astype(str).str.strip().replace("", "Sin vendedor")
    )
    return (
        work.groupby(seller_col, as_index=False)["VentaDashboard"]
        .sum()
        .rename(columns={seller_col: "Vendedor", "VentaDashboard": "Venta"})
        .sort_values("Venta", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )


def _mix_summary(sales: pd.DataFrame, limit: int = 6) -> tuple[pd.DataFrame, str]:
    col = _category_column(sales)
    label = "Categoría"

    if not col:
        col = _channel_column(sales)
        label = "Canal"

    if sales is None or sales.empty or not col or col not in sales.columns:
        return pd.DataFrame(columns=[label, "Venta"]), label

    work = sales[[col, "VentaDashboard"]].copy()
    work[col] = (
        work[col].fillna(f"Sin {label.lower()}").astype(str).str.strip().replace("", f"Sin {label.lower()}")
    )
    out = (
        work.groupby(col, as_index=False)["VentaDashboard"]
        .sum()
        .rename(columns={col: label, "VentaDashboard": "Venta"})
        .sort_values("Venta", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )
    return out, label


def _latest_orders(sales: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    if sales is None or sales.empty or "FechaDashboard" not in sales.columns:
        return pd.DataFrame()

    doc_col = _document_column(sales)
    client_col = _client_column(sales)
    seller_col = _seller_column(sales)

    cols = ["FechaDashboard", "VentaDashboard"]
    for c in [doc_col, client_col, seller_col]:
        if c and c in sales.columns and c not in cols:
            cols.append(c)

    work = sales[cols].copy()
    work = work.dropna(subset=["FechaDashboard"])

    if doc_col and doc_col in work.columns:
        agg = {
            "FechaDashboard": "max",
            "VentaDashboard": "sum",
        }
        if client_col and client_col in work.columns:
            agg[client_col] = "first"
        if seller_col and seller_col in work.columns:
            agg[seller_col] = "first"

        work = work.groupby(doc_col, as_index=False).agg(agg)
    else:
        work = work.sort_values("FechaDashboard", ascending=False).head(limit)

    work = work.sort_values("FechaDashboard", ascending=False).head(limit).reset_index(drop=True)

    out = pd.DataFrame()
    out["Documento"] = (
        work[doc_col].astype(str)
        if doc_col and doc_col in work.columns
        else [f"Venta {i+1}" for i in range(len(work))]
    )
    out["Fecha"] = work["FechaDashboard"].dt.strftime("%d-%m-%Y")
    out["Cliente"] = (
        work[client_col].fillna("Sin cliente").astype(str)
        if client_col and client_col in work.columns
        else "Sin cliente"
    )
    out["Vendedor"] = (
        work[seller_col].fillna("Sin vendedor").astype(str)
        if seller_col and seller_col in work.columns
        else "Sin vendedor"
    )
    out["Total"] = pd.to_numeric(work["VentaDashboard"], errors="coerce").fillna(0.0)
    return out


def _inject_css():
    st.markdown(
        """
<style>
/* ============================================================
   MARITEX DASHBOARD · DARK CRM
   ============================================================ */

.block-container{
    max-width:1680px;
    padding-top:.85rem;
    padding-bottom:2rem;
}

div[data-testid="stVerticalBlock"]{gap:.65rem}

.home-head{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:20px;
    margin-bottom:2px;
}
.home-title{
    color:#F7F9FB;
    font-size:29px;
    line-height:1;
    font-weight:850;
    letter-spacing:-.7px;
}
.home-sub{
    color:#9EACB8;
    font-size:12px;
    margin-top:7px;
}
.home-live{
    display:flex;
    align-items:center;
    gap:8px;
    color:#D8E0E6;
    background:#121C25;
    border:1px solid #33434F;
    border-radius:10px;
    padding:9px 13px;
    font-size:10.5px;
}
.home-live i{
    display:block;
    width:8px;height:8px;border-radius:999px;
    background:#24CC6A;
    box-shadow:0 0 0 4px rgba(36,204,106,.10);
}

/* KPI */
.home-kpis{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:11px;
    margin:5px 0 2px;
}
.home-kpi{
    background:linear-gradient(145deg,#18242E,#111A22);
    border:1px solid #33434F;
    border-radius:11px;
    padding:14px 15px 13px;
    min-height:111px;
    position:relative;
    overflow:hidden;
}
.home-kpi::after{
    content:"";
    position:absolute;
    left:14px;right:14px;bottom:8px;height:2px;
    border-radius:999px;
    opacity:.45;
}
.home-kpi.yellow::after{background:linear-gradient(90deg,#FFC400,transparent)}
.home-kpi.green::after{background:linear-gradient(90deg,#34C867,transparent)}
.home-kpi.purple::after{background:linear-gradient(90deg,#8B5CF6,transparent)}
.home-kpi.orange::after{background:linear-gradient(90deg,#F97316,transparent)}
.home-kpi.blue::after{background:linear-gradient(90deg,#3B82F6,transparent)}

.home-kpi-top{display:flex;align-items:center;gap:11px}
.home-kpi-icon{
    width:38px;height:38px;border-radius:999px;
    display:flex;align-items:center;justify-content:center;
    font-size:17px;font-weight:850;flex:0 0 38px;
}
.home-kpi-icon.yellow{color:#FFC400;background:rgba(255,196,0,.11);border:1px solid rgba(255,196,0,.28)}
.home-kpi-icon.green{color:#44D478;background:rgba(34,197,94,.11);border:1px solid rgba(34,197,94,.26)}
.home-kpi-icon.purple{color:#9E7BFF;background:rgba(139,92,246,.12);border:1px solid rgba(139,92,246,.25)}
.home-kpi-icon.orange{color:#FB7C2C;background:rgba(249,115,22,.12);border:1px solid rgba(249,115,22,.26)}
.home-kpi-icon.blue{color:#62A2FF;background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.25)}

.home-kpi-label{color:#BBC6CF;font-size:9.5px;text-transform:uppercase;font-weight:750}
.home-kpi-value{color:#FFF;font-size:21px;font-weight:850;line-height:1;margin-top:6px;letter-spacing:-.35px}
.home-kpi-help{color:#8D9AA5;font-size:8.9px;margin-top:8px;font-weight:650}
.home-kpi-help.positive{color:#49D17B}
.home-kpi-help.negative{color:#FF776E}
.home-kpi-help.yellow{color:#F3CB36}

/* card wrappers */
div[data-testid="stVerticalBlockBorderWrapper"]{
    border:1px solid #33434F !important;
    background:linear-gradient(145deg,#18242E,#111A22) !important;
    border-radius:11px !important;
    box-shadow:none !important;
}
.home-card-title{color:#F4F7F9;font-size:11.5px;font-weight:850;margin-bottom:1px}
.home-card-sub{color:#8997A3;font-size:8.8px;margin-bottom:5px}
.home-card-foot{color:#70808D;font-size:8.3px;margin-top:6px}

/* operational strip */
.ops-grid{
    display:grid;
    grid-template-columns:repeat(5,1fr);
    gap:0;
    margin-top:8px;
}
.ops-item{
    min-width:0;
    padding:4px 12px 8px;
    border-right:1px solid #2E3D49;
}
.ops-item:first-child{padding-left:0}
.ops-item:last-child{border-right:0}
.ops-icon{
    width:28px;height:28px;border-radius:999px;
    display:flex;align-items:center;justify-content:center;
    margin-bottom:7px;font-weight:900
}
.ops-icon.blue{background:#17375E;color:#6BA9FF}
.ops-icon.teal{background:#123E3C;color:#56D7C6}
.ops-icon.pink{background:#54203D;color:#FF7AB6}
.ops-icon.yellow{background:#4A3A08;color:#FFC400}
.ops-icon.purple{background:#2F2058;color:#A581FF}
.ops-label{color:#8C99A4;font-size:7.7px;text-transform:uppercase}
.ops-value{color:#F7F9FB;font-size:16px;font-weight:850;margin-top:5px}
.ops-help{color:#82909C;font-size:7.8px;margin-top:4px}

/* alerts */
.alert-list{display:flex;flex-direction:column}
.alert-row{
    display:grid;
    grid-template-columns:29px minmax(0,1fr) auto;
    gap:9px;align-items:center;
    padding:9px 0;border-bottom:1px solid #2E3D49;
}
.alert-row:last-child{border-bottom:0}
.alert-icon{
    width:28px;height:28px;border-radius:999px;
    display:flex;align-items:center;justify-content:center;
    font-size:11px;font-weight:900
}
.alert-icon.red{background:#572323;color:#FF7872}
.alert-icon.orange{background:#4B2B12;color:#FF9D4A}
.alert-icon.yellow{background:#4A3A08;color:#FFC400}
.alert-icon.blue{background:#17375E;color:#68A7FF}
.alert-icon.green{background:#123E26;color:#64DC8E}
.alert-row strong{display:block;color:#EDF2F5;font-size:9.7px}
.alert-row small{display:block;color:#84929E;font-size:8px;margin-top:2px}
.alert-value{
    min-width:36px;text-align:center;
    padding:3px 7px;border-radius:5px;
    color:#F7F9FB;font-size:8.5px;font-weight:850;background:#24323D
}

/* product rows */
.prod-list{display:flex;flex-direction:column;margin-top:2px}
.prod-row{
    display:grid;
    grid-template-columns:20px minmax(0,1fr) 92px 65px;
    align-items:center;gap:8px;
    padding:8px 0;border-bottom:1px solid #2D3C47;
}
.prod-row:last-child{border-bottom:0}
.prod-rank{color:#75838E;font-size:8.8px;font-weight:750}
.prod-main strong{display:block;color:#EAF0F4;font-size:9.3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.prod-main span{display:block;color:#74838F;font-size:7.8px;margin-top:1px}
.prod-money{text-align:right;color:#F1F5F8;font-size:9px;font-weight:780}
.prod-bar{height:7px;background:#24323D;border-radius:999px;overflow:hidden}
.prod-bar i{display:block;height:100%;background:linear-gradient(90deg,#FFC400,#FFD95D);border-radius:999px}

/* tables */
.dash-table{width:100%;border-collapse:collapse;font-size:8.4px}
.dash-table th{
    color:#8D9AA5;font-size:7.7px;font-weight:700;text-align:left;
    border-bottom:1px solid #33434F;padding:6px 5px
}
.dash-table td{
    color:#D9E1E7;border-bottom:1px solid #2B3944;padding:7px 5px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:165px
}
.dash-table tr:last-child td{border-bottom:0}
.dash-table .money{color:#F5F7F9;font-weight:780;text-align:right}

/* inventory */
.inv-donut{
    --p:0%;
    width:96px;height:96px;border-radius:50%;
    background:
      radial-gradient(circle at center,#151F28 56%,transparent 57%),
      conic-gradient(#FFC400 var(--p),#2A3945 0);
    display:flex;align-items:center;justify-content:center;
}
.inv-donut div{text-align:center}
.inv-donut strong{display:block;color:#FFF;font-size:18px}
.inv-donut span{display:block;color:#81909C;font-size:7.8px;margin-top:4px}
.inv-layout{display:flex;align-items:center;gap:14px;margin-top:8px}
.inv-list{flex:1;display:flex;flex-direction:column;gap:8px}
.inv-line{display:grid;grid-template-columns:8px minmax(0,1fr) auto;align-items:center;gap:7px;font-size:8.7px}
.inv-line i{width:7px;height:7px;border-radius:999px}
.inv-line i.green{background:#71CC72}
.inv-line i.yellow{background:#FFC400}
.inv-line i.orange{background:#F49A43}
.inv-line i.red{background:#EF6656}
.inv-line span{color:#9AA7B2}
.inv-line strong{color:#EDF2F5;font-size:8.8px}

/* buttons/date input */
.stButton>button{
    border-radius:8px !important;
    min-height:35px !important;
    font-size:9.5px !important;
    font-weight:750 !important;
}
[data-testid="stDateInput"] label{color:#A8B4BE !important;font-size:9px !important}
[data-testid="stDateInput"] input{
    background:#141F28 !important;color:#F4F7F9 !important;border-color:#3A4955 !important;
}

/* charts */
[data-testid="stVegaLiteChart"]{background:transparent !important}

/* footer */
.home-foot{
    color:#6F7E89;font-size:8.2px;padding:7px 0 0;
    display:flex;align-items:center;gap:6px
}

/* responsive */
@media(max-width:1200px){
    .home-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
    .ops-grid{grid-template-columns:repeat(2,1fr)}
    .ops-item{border-right:0;border-bottom:1px solid #2E3D49}
}
@media(max-width:700px){
    .home-head{flex-direction:column}
    .home-kpis{grid-template-columns:1fr}
    .ops-grid{grid-template-columns:1fr}
}
</style>
        """,
        unsafe_allow_html=True,
    )


def render(ctx):
    _inject_css()

    raw = ctx.get("stock_normalized")
    cons = ctx.get("stock_consolidated")
    sales_df = ctx.get("sales_df")
    stock_meta = ctx.get("stock_meta") or {}

    default_start, default_end = _period_from_sales(sales_df)

    if "dash_period" not in st.session_state:
        # Mostrar por defecto aproximadamente 12 meses si hay información suficiente.
        candidate_start = default_end - timedelta(days=364)
        st.session_state.dash_period = (candidate_start, default_end)

    now_cl = datetime.now(CHILE_TZ)
    updated = (
        stock_meta.get("generatedAt")
        or stock_meta.get("loaded_at")
        or now_cl.strftime("%d/%m/%Y %H:%M")
    )

    # --------------------------------------------------------
    # HEADER + FILTRO
    # --------------------------------------------------------
    head_left, head_mid, head_date = st.columns([2.6, 1.15, 1.55], gap="small")

    with head_left:
        render_html(
            """
<div class="home-head">
    <div>
        <div class="home-title">Dashboard</div>
        <div class="home-sub">Resumen general del negocio actualizado en tiempo real.</div>
    </div>
</div>
            """
        )

    with head_mid:
        render_html(
            f"""
<div class="home-live">
    <i></i>
    <span>Datos ERP activos · {escape(str(updated))}</span>
</div>
            """
        )

    with head_date:
        period = st.date_input(
            "Período",
            value=st.session_state.dash_period,
            key="dash_period_picker",
            format="DD/MM/YYYY",
            label_visibility="collapsed",
        )

    if isinstance(period, (tuple, list)):
        if len(period) >= 2:
            start, end = period[0], period[1]
        elif len(period) == 1:
            start = end = period[0]
        else:
            start, end = st.session_state.dash_period
    else:
        start = end = period

    st.session_state.dash_period = (start, end)

    current_sales = _prepare_sales(sales_df, start, end)
    days = max((end - start).days + 1, 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    previous_sales = _prepare_sales(sales_df, prev_start, prev_end)

    current_revenue = float(
        current_sales.get("VentaDashboard", pd.Series(dtype="float64")).sum()
    )
    previous_revenue = float(
        previous_sales.get("VentaDashboard", pd.Series(dtype="float64")).sum()
    )

    revenue_delta, revenue_tone = _delta(current_revenue, previous_revenue)

    current_docs = _sales_documents(current_sales)
    previous_docs = _sales_documents(previous_sales)
    docs_delta, docs_tone = _delta(float(current_docs), float(previous_docs))

    clients = _active_clients(current_sales)
    previous_clients = _active_clients(previous_sales)
    client_delta, client_tone = _delta(float(clients), float(previous_clients))

    margin, margin_pct = _margin_data(current_sales)
    stock = _stock_metrics(cons)

    total_states = max(stock["healthy"] + stock["low"] + stock["risk"] + stock["zero"], 1)
    healthy_pct = stock["healthy"] / total_states * 100

    if margin is None:
        margin_value = "—"
        margin_helper = "Costo no disponible en ERP"
    else:
        margin_value = _money_compact(margin)
        margin_helper = (
            f"{margin_pct:.1f}% sobre ventas" if margin_pct is not None else "Margen calculado"
        )

    # --------------------------------------------------------
    # KPI SUPERIORES
    # --------------------------------------------------------
    kpis = f"""
<div class="home-kpis">
    <div class="home-kpi yellow">
        <div class="home-kpi-top">
            <div class="home-kpi-icon yellow">↗</div>
            <div>
                <div class="home-kpi-label">Ventas período</div>
                <div class="home-kpi-value">{escape(_money_compact(current_revenue))}</div>
                <div class="home-kpi-help {'positive' if revenue_tone == 'positive' else 'negative' if revenue_tone == 'negative' else 'yellow'}">{escape(revenue_delta)}</div>
            </div>
        </div>
    </div>

    <div class="home-kpi green">
        <div class="home-kpi-top">
            <div class="home-kpi-icon green">$</div>
            <div>
                <div class="home-kpi-label">Margen bruto</div>
                <div class="home-kpi-value">{escape(margin_value)}</div>
                <div class="home-kpi-help positive">{escape(margin_helper)}</div>
            </div>
        </div>
    </div>

    <div class="home-kpi purple">
        <div class="home-kpi-top">
            <div class="home-kpi-icon purple">▥</div>
            <div>
                <div class="home-kpi-label">Pedidos / documentos</div>
                <div class="home-kpi-value">{_fmt_int(current_docs)}</div>
                <div class="home-kpi-help {'positive' if docs_tone == 'positive' else 'negative' if docs_tone == 'negative' else 'yellow'}">{escape(docs_delta)}</div>
            </div>
        </div>
    </div>

    <div class="home-kpi orange">
        <div class="home-kpi-top">
            <div class="home-kpi-icon orange">●</div>
            <div>
                <div class="home-kpi-label">Clientes activos</div>
                <div class="home-kpi-value">{_fmt_int(clients)}</div>
                <div class="home-kpi-help {'positive' if client_tone == 'positive' else 'negative' if client_tone == 'negative' else 'yellow'}">{escape(client_delta)}</div>
            </div>
        </div>
    </div>

    <div class="home-kpi blue">
        <div class="home-kpi-top">
            <div class="home-kpi-icon blue">◇</div>
            <div>
                <div class="home-kpi-label">Stock total</div>
                <div class="home-kpi-value">{_fmt_int(stock['units'])}</div>
                <div class="home-kpi-help positive">{healthy_pct:.0f}% del inventario saludable</div>
            </div>
        </div>
    </div>
</div>
"""
    render_html(kpis)

    # --------------------------------------------------------
    # FILA 1: VENTAS / MIX / TOP PRODUCTOS
    # --------------------------------------------------------
    c1, c2, c3 = st.columns([1.55, 1.05, 1.15], gap="medium")

    with c1:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Ventas por período</div>
<div class="home-card-sub">Evolución de ventas dentro del rango seleccionado</div>
                """
            )

            if current_sales.empty:
                st.info("No hay ventas para el período seleccionado.")
            else:
                monthly = (
                    current_sales.assign(
                        Mes=current_sales["FechaDashboard"].dt.to_period("M").dt.to_timestamp()
                    )
                    .groupby("Mes", as_index=False)["VentaDashboard"]
                    .sum()
                    .rename(columns={"VentaDashboard": "Venta"})
                    .sort_values("Mes")
                )
                monthly["Acumulado"] = monthly["Venta"].cumsum()

                bars = (
                    alt.Chart(monthly)
                    .mark_bar(color="#FFC400", cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
                    .encode(
                        x=alt.X("Mes:T", title=None, axis=alt.Axis(format="%b %Y", labelColor="#9EACB8", labelAngle=0, domain=False, tickColor="#33434F")),
                        y=alt.Y("Venta:Q", title=None, axis=alt.Axis(format="~s", labelColor="#9EACB8", domain=False, gridColor="#2D3C47")),
                        tooltip=[
                            alt.Tooltip("Mes:T", title="Mes", format="%m/%Y"),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                )
                line = (
                    alt.Chart(monthly)
                    .mark_line(color="#E9EEF2", point=alt.OverlayMarkDef(color="#E9EEF2", size=28), strokeWidth=1.7)
                    .encode(
                        x="Mes:T",
                        y=alt.Y("Acumulado:Q", axis=alt.Axis(orient="right", format="~s", labelColor="#9EACB8", domain=False, grid=False)),
                        tooltip=[alt.Tooltip("Acumulado:Q", title="Acumulado", format=",.0f")],
                    )
                )

                st.altair_chart(
                    alt.layer(bars, line).resolve_scale(y="independent").properties(height=255, background="#111A22"),
                    width="stretch",
                )

    with c2:
        with st.container(border=True):
            mix, mix_label = _mix_summary(current_sales)
            render_html(
                f"""
<div class="home-card-title">Ventas por {escape(mix_label.lower())}</div>
<div class="home-card-sub">Participación sobre las ventas del período</div>
                """
            )

            if mix.empty:
                st.info("No se encontró categoría o canal en ERP Ventas.")
            else:
                donut = (
                    alt.Chart(mix)
                    .mark_arc(innerRadius=58, outerRadius=88, cornerRadius=3)
                    .encode(
                        theta=alt.Theta("Venta:Q"),
                        color=alt.Color(
                            f"{mix_label}:N",
                            scale=alt.Scale(range=["#FFC400","#4A83D8","#76BF59","#EF694F","#8B5CF6","#F29542"]),
                            legend=alt.Legend(orient="bottom", columns=2, labelColor="#A8B4BE", title=None, labelLimit=120),
                        ),
                        tooltip=[
                            alt.Tooltip(f"{mix_label}:N", title=mix_label),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                    .properties(height=255, background="#111A22")
                )
                st.altair_chart(donut, width="stretch")

    with c3:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Top 5 productos</div>
<div class="home-card-sub">Productos con mayor venta del período</div>
                """
            )
            top = _top_products(raw, current_sales, limit=5)
            if top.empty:
                st.info("No hay ventas por SKU disponibles.")
            else:
                max_sale = max(float(top["Venta"].max()), 1.0)
                rows = ""
                for i, row in top.iterrows():
                    width = max(3.0, min(float(row["Venta"]) / max_sale * 100, 100))
                    rows += f"""
<div class="prod-row">
    <div class="prod-rank">{i + 1}</div>
    <div class="prod-main">
        <strong>{escape(str(row['Producto'])[:34])}</strong>
        <span>SKU {escape(str(row['SKUDashboard']))}</span>
    </div>
    <div class="prod-money">{escape(_money_compact(row['Venta']))}</div>
    <div class="prod-bar"><i style="width:{width:.1f}%"></i></div>
</div>
"""
                render_html(f'<div class="prod-list">{rows}</div>')

    # --------------------------------------------------------
    # FILA 2: OPERACIONALES / VENDEDORES / ALERTAS
    # --------------------------------------------------------
    r2a, r2b, r2c = st.columns([1.55, 1.05, 1.15], gap="medium")

    with r2a:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Indicadores operacionales</div>
<div class="home-card-sub">Lectura rápida del desempeño comercial y de inventario</div>
                """
            )
            ticket = current_revenue / current_docs if current_docs else 0
            sales_per_client = current_revenue / clients if clients else 0
            units = float(current_sales.get("CantidadDashboard", pd.Series(dtype="float64")).sum()) if not current_sales.empty else 0.0
            units_per_doc = units / current_docs if current_docs else 0
            attention = stock["low"] + stock["risk"] + stock["zero"]

            render_html(
                f"""
<div class="ops-grid">
    <div class="ops-item">
        <div class="ops-icon blue">$</div>
        <div class="ops-label">Ticket promedio</div>
        <div class="ops-value">{escape(_money_compact(ticket))}</div>
        <div class="ops-help">Venta / documento</div>
    </div>
    <div class="ops-item">
        <div class="ops-icon teal">◎</div>
        <div class="ops-label">Venta por cliente</div>
        <div class="ops-value">{escape(_money_compact(sales_per_client))}</div>
        <div class="ops-help">Promedio período</div>
    </div>
    <div class="ops-item">
        <div class="ops-icon pink">▣</div>
        <div class="ops-label">Unidades</div>
        <div class="ops-value">{_fmt_int(units)}</div>
        <div class="ops-help">{units_per_doc:.1f} por documento</div>
    </div>
    <div class="ops-item">
        <div class="ops-icon yellow">✓</div>
        <div class="ops-label">Stock saludable</div>
        <div class="ops-value">{healthy_pct:.1f}%</div>
        <div class="ops-help">{_fmt_int(stock['healthy'])} SKU</div>
    </div>
    <div class="ops-item">
        <div class="ops-icon purple">!</div>
        <div class="ops-label">Requieren atención</div>
        <div class="ops-value">{_fmt_int(attention)}</div>
        <div class="ops-help">Bajo + riesgo + sin stock</div>
    </div>
</div>
                """
            )

    with r2b:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Ventas por vendedor</div>
<div class="home-card-sub">Top 10 del período seleccionado</div>
                """
            )
            sellers = _seller_summary(current_sales, 10)
            if sellers.empty:
                st.info("No se encontró vendedor en ERP Ventas.")
            else:
                chart = (
                    alt.Chart(sellers)
                    .mark_bar(color="#58B96A", cornerRadiusEnd=2)
                    .encode(
                        x=alt.X("Venta:Q", title=None, axis=alt.Axis(format="~s", labelColor="#9EACB8", gridColor="#2D3C47", domain=False)),
                        y=alt.Y("Vendedor:N", sort="-x", title=None, axis=alt.Axis(labelColor="#C4CDD4", domain=False, labelLimit=110)),
                        tooltip=[
                            alt.Tooltip("Vendedor:N", title="Vendedor"),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                    .properties(height=235, background="#111A22")
                )
                st.altair_chart(chart, width="stretch")

    with r2c:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Alertas y pendientes</div>
<div class="home-card-sub">Prioridades actuales de inventario</div>
                """
            )
            render_html(
                f"""
<div class="alert-list">
    <div class="alert-row">
        <div class="alert-icon red">!</div>
        <div><strong>Productos sin stock</strong><small>Requieren revisión inmediata</small></div>
        <div class="alert-value">{_fmt_int(stock['zero'])}</div>
    </div>
    <div class="alert-row">
        <div class="alert-icon orange">↓</div>
        <div><strong>Stock bajo</strong><small>Revisar reposición y cobertura</small></div>
        <div class="alert-value">{_fmt_int(stock['low'])}</div>
    </div>
    <div class="alert-row">
        <div class="alert-icon yellow">△</div>
        <div><strong>Riesgo operacional</strong><small>Productos que requieren seguimiento</small></div>
        <div class="alert-value">{_fmt_int(stock['risk'])}</div>
    </div>
    <div class="alert-row">
        <div class="alert-icon green">✓</div>
        <div><strong>Inventario saludable</strong><small>SKU con disponibilidad normal</small></div>
        <div class="alert-value">{_fmt_int(stock['healthy'])}</div>
    </div>
</div>
                """
            )

    # --------------------------------------------------------
    # FILA 3: ÚLTIMOS PEDIDOS / INVENTARIO
    # --------------------------------------------------------
    r3a, r3b = st.columns([1.75, 1.0], gap="medium")

    with r3a:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Últimos pedidos / documentos</div>
<div class="home-card-sub">Movimientos comerciales más recientes dentro del período</div>
                """
            )
            orders = _latest_orders(current_sales, 5)
            if orders.empty:
                st.info("No hay documentos recientes para mostrar.")
            else:
                rows = ""
                for _, row in orders.iterrows():
                    rows += f"""
<tr>
    <td>{escape(str(row['Documento'])[:22])}</td>
    <td>{escape(str(row['Fecha']))}</td>
    <td>{escape(str(row['Cliente'])[:34])}</td>
    <td>{escape(str(row['Vendedor'])[:24])}</td>
    <td class="money">{escape(_money_compact(row['Total']))}</td>
</tr>
"""
                render_html(
                    f"""
<table class="dash-table">
    <thead><tr><th>Documento</th><th>Fecha</th><th>Cliente</th><th>Vendedor</th><th style="text-align:right">Total</th></tr></thead>
    <tbody>{rows}</tbody>
</table>
                    """
                )

    with r3b:
        with st.container(border=True):
            render_html(
                """
<div class="home-card-title">Estado del inventario</div>
<div class="home-card-sub">Distribución actual de los SKU por condición</div>
                """
            )
            render_html(
                f"""
<div class="inv-layout">
    <div class="inv-donut" style="--p:{healthy_pct:.1f}%">
        <div><strong>{healthy_pct:.0f}%</strong><span>Saludable</span></div>
    </div>
    <div class="inv-list">
        <div class="inv-line"><i class="green"></i><span>Saludable</span><strong>{_fmt_int(stock['healthy'])}</strong></div>
        <div class="inv-line"><i class="yellow"></i><span>Stock bajo</span><strong>{_fmt_int(stock['low'])}</strong></div>
        <div class="inv-line"><i class="orange"></i><span>Riesgo</span><strong>{_fmt_int(stock['risk'])}</strong></div>
        <div class="inv-line"><i class="red"></i><span>Sin stock</span><strong>{_fmt_int(stock['zero'])}</strong></div>
    </div>
</div>
<div class="home-card-foot">{_fmt_int(stock['units'])} unidades disponibles · {_fmt_int(stock['sku'])} SKU activos</div>
                """
            )

    # --------------------------------------------------------
    # ACCESOS RÁPIDOS
    # --------------------------------------------------------
    with st.container(border=True):
        render_html(
            """
<div class="home-card-title">Accesos rápidos</div>
<div class="home-card-sub">Navegación directa a los módulos operacionales</div>
            """
        )
        q1, q2, q3, q4, q5 = st.columns(5, gap="small")
        with q1:
            _nav_button("📦 Stock General", "Stock General", "dash_stock")
        with q2:
            _nav_button("🛒 Marketplace", "Marketplace", "dash_market")
        with q3:
            _nav_button("🔗 Integración ERP", "Integración ERP", "dash_erp")
        with q4:
            _nav_button("👤 CRM", "CRM", "dash_crm")
        with q5:
            _nav_button("📊 Resumen", "Resumen Ejecutivo", "dash_summary")

    render_html(
        """
<div class="home-foot">
    <span>ⓘ</span>
    <span>Los indicadores se construyen con ERP Ventas y ERP Stock disponibles en la sesión actual.</span>
</div>
        """
    )
