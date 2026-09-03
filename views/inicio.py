

from datetime import datetime
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from analytics.sales_metrics import calculate_commercial_totals
from services.commercial_dashboard_service import (
    commercial_metrics,
    find_client_column,
    filter_commercial_view,
    prepare_commercial_base,
    signed_amount,
)
from ui.components import render_html
from utils.numbers import format_clp

try:
    from services.crm_service import (
        list_followups,
        list_opportunities,
    )
except Exception:
    list_followups = None
    list_opportunities = None


# ============================================================
# CONFIGURACIÓN
# ============================================================

VAT_RATE = 0.19
VALID_GROUPS = ["Factura", "Boleta", "Nota de crédito"]

SELLER_NAMES = {
    "001": "VENDEDOR 1",
    "01": "JEFE DE VENTAS CM",
    "02": "JEFE DE VENTAS GC",
    "03": "GC1-DANIEL ALVARADO",
    "04": "ROXANA VALENCIA",
    "05": "GRACIELA SANTANDER",
    "06": "CLAUDIA LOPEZ",
    "07": "LORENA OPAZO",
    "08": "MARIO BRITO",
    "09": "XIMENA CROVETTO",
    "10": "REG1",
    "11": "CAROLINA CROCKETT",
    "12": "JOSE GONZALEZ",
    "13": "PERSONAL",
    "14": "REGIONES SUR",
    "15": "VENDEDOR ECOMMERS",
    "16": "MATIAS CHOMALI",
    "17": "ECOMMERS",
    "30": "VENDEDOR ECOMMERS B2C",
    "31": "VENDEDOR ECOMMERS NOLK",
    "32": "VENDEDOR ECOMMERS",
    "33": "MKP FALABELLA",
    "34": "MKP MERCADO LIBRE",
    "35": "MKP - PARIS",
    "42": "JEFE LOCAL",
    "43": "SEBASTIAN ROCCO",
    "44": "MACARENA DE LA ORDEN",
    "45": "MARIELY ROSALES",
    "46": "MELANY VARGAS",
    "47": "MARIA BERNARD",
    "48": "EURO QUIÑONEZ",
    "49": "FRANCISCO PEREZ",
    "50": "GINO MATUS",
    "51": "NELSON SAN MARTIN",
    "54": "JOHANA OBREQUE",
    "60": "JOSE LUIS ROLANO",
    "70": "ANDRES ESPINOZA",
}

EXCLUDED_SELLERS = {"36", "52", "53"}


# ============================================================
# HELPERS GENERALES
# ============================================================

def _go_to(page: str) -> None:
    st.session_state.page = page


def _normalize_seller_code(value) -> str:
    text = str(value or "").strip()

    if text.endswith(".0"):
        text = text[:-2]

    if text == "001":
        return "001"

    if text.isdigit():
        return text.zfill(2)

    return text


def _seller_name(value) -> str:
    code = _normalize_seller_code(value)

    if not code:
        return "Sin vendedor"

    return SELLER_NAMES.get(code, code)


def _seller_display(value) -> str:
    code = _normalize_seller_code(value)

    if not code:
        return "Sin vendedor"

    name = _seller_name(code)

    if name == code:
        return code

    return name


def _money(value) -> str:
    try:
        return format_clp(float(value or 0))
    except Exception:
        return "$0"


def _number(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _safe_text(value, default="-") -> str:
    text = str(value or "").strip()
    return text if text else default


def _help(text: str) -> str:
    safe = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    return (
        '<span class="dash-help">?'
        f'<span class="dash-help-tip">{safe}</span>'
        '</span>'
    )


# ============================================================
# STOCK
# ============================================================

def _stock_metrics(ctx) -> dict:
    consolidated = ctx.get("stock_consolidated")
    inventory = ctx.get("stock_normalized")

    result = {
        "sku": 0,
        "units": 0,
        "healthy": 0,
        "low": 0,
        "zero": 0,
        "risk": 0,
        "warehouses": 0,
        "value": 0.0,
    }

    if consolidated is None or consolidated.empty:
        return result

    states = consolidated.get(
        "Estado",
        pd.Series("", index=consolidated.index),
    ).astype(str)

    available = pd.to_numeric(
        consolidated.get("Disponible", 0),
        errors="coerce",
    ).fillna(0)

    price = pd.to_numeric(
        consolidated.get("Precio", 0),
        errors="coerce",
    ).fillna(0)

    result.update(
        {
            "sku": (
                int(consolidated["Código"].nunique())
                if "Código" in consolidated.columns
                else int(len(consolidated))
            ),
            "units": int(round(available.sum())),
            "healthy": int(states.eq("🟢 Disponible").sum()),
            "low": int(states.eq("🟡 Stock bajo").sum()),
            "zero": int(
                states.isin(
                    ["🔴 Sin stock", "🔴 Negativo"]
                ).sum()
            ),
            "risk": int(
                states.eq("🟠 Riesgo despacho").sum()
            ),
            "value": float(
                (
                    available.clip(lower=0)
                    * price
                ).sum()
            ),
        }
    )

    if (
        inventory is not None
        and not inventory.empty
        and "Bodega" in inventory.columns
    ):
        result["warehouses"] = int(
            inventory["Bodega"]
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )

    return result


# ============================================================
# VENTAS
# ============================================================

def _prepare_sales(sales_df: pd.DataFrame) -> pd.DataFrame:
    """Usa la base comercial oficial compartida."""
    work = prepare_commercial_base(
        sales_df
    )

    if work.empty:
        return work

    work["VentaDashboard"] = signed_amount(
        work,
        no_vat=False,
    )

    return work


def _sales_period(work: pd.DataFrame):
    if work is None or work.empty:
        return None, None

    return (
        work["Fecha_dt"].min().date(),
        work["Fecha_dt"].max().date(),
    )


def _seller_options(work: pd.DataFrame) -> list[str]:
    if (
        work is None
        or work.empty
        or "Vendedor" not in work.columns
    ):
        return []

    values = set()

    for value in work["Vendedor"].dropna():
        code = _normalize_seller_code(value)

        if (
            code
            and code not in EXCLUDED_SELLERS
        ):
            values.add(code)

    return sorted(
        values,
        key=lambda code: (
            _seller_name(code),
            code,
        ),
    )


def _filter_sales(
    work: pd.DataFrame,
    seller: str,
    start_date,
    end_date,
) -> pd.DataFrame:
    if work is None or work.empty:
        return pd.DataFrame()

    out = work[
        (
            work["Fecha_dt"].dt.date
            >= start_date
        )
        & (
            work["Fecha_dt"].dt.date
            <= end_date
        )
    ].copy()

    if (
        seller != "Todos"
        and "Vendedor" in out.columns
    ):
        code = _normalize_seller_code(
            seller
        )

        seller_codes = (
            out["Vendedor"]
            .map(
                _normalize_seller_code
            )
        )

        out = out[
            seller_codes == code
        ].copy()

    return out


def _sales_summary(work: pd.DataFrame) -> dict:
    client_col = find_client_column(
        work
    )

    metrics = commercial_metrics(
        work,
        no_vat=False,
        client_col=client_col,
    )

    return {
        "net": metrics["net"],
        "gross": metrics["gross"],
        "credits": metrics["credits"],
        "documents": metrics["docs"],
        "clients": metrics["clients"],
        "ticket": metrics["ticket"],
    }


def _daily_sales(work: pd.DataFrame) -> pd.DataFrame:
    if work is None or work.empty:
        return pd.DataFrame(
            columns=["Día", "Venta"]
        )

    return (
        work.assign(
            Día=work[
                "Fecha_dt"
            ].dt.normalize()
        )
        .groupby(
            "Día",
            as_index=False,
        )["VentaDashboard"]
        .sum()
        .rename(
            columns={
                "VentaDashboard":
                "Venta"
            }
        )
        .sort_values("Día")
    )


def _seller_ranking(
    work: pd.DataFrame,
    limit: int = 5,
) -> pd.DataFrame:
    if (
        work is None
        or work.empty
        or "Vendedor" not in work.columns
    ):
        return pd.DataFrame(
            columns=[
                "Ranking",
                "Vendedor",
                "Ventas del período",
                "% Participación",
            ]
        )

    temp = work.copy()

    temp["_seller_code"] = (
        temp["Vendedor"]
        .map(
            _normalize_seller_code
        )
    )

    temp = temp[
        ~temp[
            "_seller_code"
        ].isin(
            EXCLUDED_SELLERS
        )
    ].copy()

    grouped = (
        temp.groupby(
            "_seller_code",
            as_index=False,
        )["VentaDashboard"]
        .sum()
        .sort_values(
            "VentaDashboard",
            ascending=False,
        )
        .head(limit)
        .reset_index(drop=True)
    )

    total = float(
        grouped["VentaDashboard"].sum()
    )

    grouped["Ranking"] = (
        grouped.index + 1
    )

    grouped["Vendedor"] = (
        grouped[
            "_seller_code"
        ].map(
            _seller_name
        )
    )

    grouped[
        "Ventas del período"
    ] = grouped[
        "VentaDashboard"
    ]

    grouped[
        "% Participación"
    ] = (
        grouped[
            "VentaDashboard"
        ]
        / total
        * 100
        if total
        else 0
    )

    return grouped[
        [
            "Ranking",
            "Vendedor",
            "Ventas del período",
            "% Participación",
        ]
    ]


def _top_clients(
    work: pd.DataFrame,
    limit: int = 5,
) -> pd.DataFrame:
    if work is None or work.empty:
        return pd.DataFrame()

    client_col = (
        "RazonSocial"
        if "RazonSocial" in work.columns
        else "CLIENTE"
        if "CLIENTE" in work.columns
        else None
    )

    if not client_col:
        return pd.DataFrame()

    agg = {
        "VentaDashboard": "sum",
        "Fecha_dt": "max",
    }

    if "Numero" in work.columns:
        grouped = (
            work.groupby(
                client_col,
                as_index=False,
            )
            .agg(
                Venta=(
                    "VentaDashboard",
                    "sum",
                ),
                Pedidos=(
                    "Numero",
                    "nunique",
                ),
                Ultima=(
                    "Fecha_dt",
                    "max",
                ),
            )
        )
    else:
        grouped = (
            work.groupby(
                client_col,
                as_index=False,
            )
            .agg(
                Venta=(
                    "VentaDashboard",
                    "sum",
                ),
                Pedidos=(
                    "VentaDashboard",
                    "size",
                ),
                Ultima=(
                    "Fecha_dt",
                    "max",
                ),
            )
        )

    grouped = (
        grouped.sort_values(
            "Venta",
            ascending=False,
        )
        .head(limit)
        .reset_index(drop=True)
    )

    grouped["Última compra"] = (
        grouped["Ultima"]
        .dt.strftime(
            "%d-%m-%Y"
        )
    )

    return grouped[
        [
            client_col,
            "Venta",
            "Pedidos",
            "Última compra",
        ]
    ].rename(
        columns={
            client_col: "Cliente",
            "Venta":
            "Ventas del período",
        }
    )


def _sales_by_branch(work: pd.DataFrame) -> pd.DataFrame:
    """
    Ventas por sucursal comercial.

    Sólo considera:
    - Casa Matriz
    - Patronato
    - Concepción

    No mezcla CD ni bodegas de reserva con sucursales.
    """
    branches = ["Casa Matriz", "Patronato", "Concepción"]

    if work is None or work.empty:
        return pd.DataFrame({"Sucursal": branches, "Venta": [0.0, 0.0, 0.0]})

    source_col = None

    # Si ERP trae una columna explícita de sucursal, tiene prioridad.
    for candidate in ("Sucursal", "SUCURSAL", "Local", "LOCAL", "Bodega"):
        if candidate in work.columns:
            source_col = candidate
            break

    if not source_col:
        return pd.DataFrame({"Sucursal": branches, "Venta": [0.0, 0.0, 0.0]})

    temp = work.copy()

    def classify(value):
        raw = str(value or "").strip().upper()
        normalized = (
            raw.replace("Á", "A")
               .replace("É", "E")
               .replace("Í", "I")
               .replace("Ó", "O")
               .replace("Ú", "U")
        )

        # Bodegas de reserva no representan ventas de una sucursal.
        if "RESERVA" in normalized:
            return None

        if "PATRONATO" in normalized:
            return "Patronato"

        if "CONCEPCION" in normalized:
            return "Concepción"

        if "CASA MATRIZ" in normalized:
            return "Casa Matriz"

        # Aceptar CM sólo cuando el valor identifica directamente la sucursal.
        compact = normalized.replace("-", " ").replace("_", " ").strip()
        tokens = compact.split()
        if normalized == "CM" or compact == "CM" or (
            len(tokens) <= 3 and "CM" in tokens
        ):
            return "Casa Matriz"

        return None

    temp["SucursalDashboard"] = temp[source_col].map(classify)
    temp = temp[temp["SucursalDashboard"].notna()].copy()

    grouped = (
        temp.groupby("SucursalDashboard", as_index=False)["VentaDashboard"]
        .sum()
        .rename(columns={"SucursalDashboard": "Sucursal", "VentaDashboard": "Venta"})
    )

    base = pd.DataFrame({"Sucursal": branches})
    result = base.merge(grouped, on="Sucursal", how="left")
    result["Venta"] = pd.to_numeric(result["Venta"], errors="coerce").fillna(0.0)

    return result


# ============================================================
# CRM ALERTAS
# ============================================================

def _crm_alerts() -> dict:
    result = {
        "open_opportunities": 0,
        "pending_followups": 0,
        "overdue_followups": 0,
    }

    try:
        if list_opportunities:
            rows = list_opportunities(
                status="Abierta",
                limit=500,
            )
            result[
                "open_opportunities"
            ] = len(rows or [])

        if list_followups:
            rows = list_followups(
                pending_only=True,
                limit=500,
            )

            rows = rows or []

            result[
                "pending_followups"
            ] = len(rows)

            today = (
                pd.Timestamp.today()
                .normalize()
            )

            overdue = 0

            for row in rows:
                dt = pd.to_datetime(
                    row.get(
                        "next_followup_date"
                    ),
                    errors="coerce",
                )

                if (
                    not pd.isna(dt)
                    and dt.normalize()
                    < today
                ):
                    overdue += 1

            result[
                "overdue_followups"
            ] = overdue

    except Exception:
        pass

    return result


# ============================================================
# CSS
# ============================================================

def _inject_css() -> None:
    st.markdown(
        """
<style>
:root{
    --bg:#071017;
    --panel:#0D171E;
    --panel2:#101B23;
    --line:#263640;
    --line2:#31434F;
    --text:#F6F8FA;
    --muted:#93A4B0;
    --yellow:#FFC400;
    --green:#27D17C;
    --red:#FF544D;
    --blue:#4093FF;
}

/* ============================================================
   BASE GENERAL
   ============================================================ */
.block-container{
    max-width:1580px !important;
    padding-top:1.15rem !important;
    padding-bottom:2rem !important;
}

div[data-testid="stAppViewContainer"]{
    background:
        radial-gradient(circle at 70% 0%, rgba(27,55,74,.18), transparent 34%),
        #071017 !important;
}

div[data-testid="stVerticalBlock"]{
    gap:.72rem !important;
}

/* ============================================================
   SIDEBAR - ESTILO SEGUNDA IMAGEN
   ============================================================ */
section[data-testid="stSidebar"]{
    background:
        linear-gradient(180deg,#071019 0%,#050A0F 100%) !important;
    border-right:1px solid #1E2B34 !important;
}

section[data-testid="stSidebar"] > div{
    padding-top:1rem !important;
}

section[data-testid="stSidebar"] [data-testid="stButton"] button{
    min-height:42px !important;
    border-radius:8px !important;
    justify-content:flex-start !important;
    padding-left:14px !important;
    background:transparent !important;
    border-color:transparent !important;
    color:#E7EDF1 !important;
    font-size:12px !important;
}

section[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"]{
    background:#111B22 !important;
    color:#FFC400 !important;
    border-left:3px solid #FFC400 !important;
}

section[data-testid="stSidebar"] [data-testid="stButton"] button:hover{
    background:#0F1920 !important;
    color:#FFC400 !important;
}

/* ============================================================
   HEADER
   ============================================================ */
.dash-head{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:24px;
    padding:0 2px 10px;
    margin-bottom:2px;
    border-bottom:1px solid #1E2A33;
}

.dash-title-line{
    display:flex;
    align-items:center;
    gap:12px;
}

.dash-title-mark{
    width:4px;
    height:35px;
    border-radius:3px;
    background:var(--yellow);
}

.dash-title{
    color:#fff;
    font-size:32px;
    font-weight:850;
    letter-spacing:-.7px;
    line-height:1;
}

.dash-sub{
    color:#A1AFB8;
    font-size:12px;
    margin-top:7px;
}

.dash-live{
    display:flex;
    align-items:center;
    gap:8px;
    color:#E4EAEE;
    background:#0D171E;
    border:1px solid #2C3C47;
    border-radius:8px;
    padding:9px 13px;
    font-size:10px;
}

.dash-live i{
    width:8px;
    height:8px;
    border-radius:50%;
    background:#27D17C;
    box-shadow:0 0 0 4px rgba(39,209,124,.10);
}

/* ============================================================
   FILTROS
   ============================================================ */
div[data-testid="stVerticalBlockBorderWrapper"]{
    background:linear-gradient(180deg,#0F1920,#0B141B) !important;
    border:1px solid #2A3944 !important;
    border-radius:10px !important;
    box-shadow:none !important;
}

div[data-testid="stVerticalBlockBorderWrapper"] > div{
    padding:.8rem .85rem !important;
}

div[data-testid="stSelectbox"] label,
div[data-testid="stDateInput"] label{
    color:#BEC8CF !important;
    font-size:10px !important;
    font-weight:750 !important;
}

div[data-testid="stSelectbox"] > div > div,
div[data-testid="stDateInput"] > div > div{
    min-height:44px !important;
    background:#0A141B !important;
    border:1px solid #31424E !important;
    border-radius:8px !important;
}

/* ============================================================
   KPI GRANDES COMO SEGUNDA IMAGEN
   ============================================================ */
.dash-kpis{
    display:grid;
    grid-template-columns:repeat(5,minmax(0,1fr));
    gap:10px;
    margin:5px 0 1px;
}

.dash-kpi{
    position:relative;
    min-height:145px;
    padding:16px 15px 13px 17px;
    background:linear-gradient(145deg,#15232C,#0F1920);
    border:1px solid #2E3F4A;
    border-radius:10px;
    overflow:visible;
}

.dash-kpi:before{
    content:"";
    position:absolute;
    left:-1px;
    top:-1px;
    bottom:-1px;
    width:3px;
    border-radius:10px 0 0 10px;
    background:#FFC400;
}

.dash-kpi-top{
    display:flex;
    align-items:center;
    gap:10px;
}

.dash-kpi-icon{
    width:44px;
    height:44px;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
    font-size:19px;
    font-weight:900;
    flex:0 0 auto;
}

.dash-kpi-icon.green{color:#31E78A;background:#07391F;}
.dash-kpi-icon.blue{color:#67A9FF;background:#10335B;}
.dash-kpi-icon.purple{color:#C072FF;background:#3A1D56;}
.dash-kpi-icon.yellow{color:#FFD33E;background:#493A00;}
.dash-kpi-icon.red{color:#FF746D;background:#54211F;}

.dash-kpi-label{
    display:flex;
    align-items:center;
    gap:6px;
    color:#E0E6EA;
    font-size:9px;
    font-weight:850;
    letter-spacing:.05em;
    text-transform:uppercase;
}

.dash-kpi-value{
    margin:11px 0 8px 54px;
    color:#fff;
    font-size:27px;
    line-height:1;
    font-weight:850;
}

.dash-kpi-sub{
    margin-left:54px;
    color:#AFBAC2;
    font-size:9px;
}

.dash-kpi-foot{
    margin:11px 0 0 54px;
    color:#71858F;
    font-size:8px;
}

/* ============================================================
   HELPERS
   ============================================================ */
.dash-help{
    position:relative;
    display:inline-flex;
    width:16px;
    height:16px;
    align-items:center;
    justify-content:center;
    border:1px solid #6B7B86;
    border-radius:50%;
    color:#FFC400;
    background:#101A21;
    font-size:9px;
    font-weight:900;
    cursor:help;
    z-index:30;
}

.dash-help-tip{
    visibility:hidden;
    opacity:0;
    position:absolute;
    z-index:10000;
    top:22px;
    left:0;
    width:230px;
    max-width:calc(100vw - 50px);
    padding:10px 11px;
    border:1px solid #3B4A55;
    border-radius:8px;
    background:#080D11;
    color:#E9EEF1;
    font-size:9px;
    line-height:1.45;
    font-weight:500;
    letter-spacing:0;
    text-transform:none;
    white-space:normal;
    box-shadow:0 10px 25px rgba(0,0,0,.40);
}

.dash-help:hover .dash-help-tip{
    visibility:visible;
    opacity:1;
}

/* ============================================================
   TÍTULOS DE CARDS
   ============================================================ */
.card-title{
    display:flex;
    align-items:center;
    gap:6px;
    color:#FFC400;
    font-size:12px;
    font-weight:850;
    text-transform:uppercase;
    letter-spacing:.025em;
}

.card-sub{
    color:#7F929E;
    font-size:9px;
    margin-top:3px;
    margin-bottom:9px;
}

/* ============================================================
   RESUMEN COMERCIAL
   ============================================================ */
.summary-table{
    width:100%;
    border-collapse:collapse;
    font-size:10px;
}

.summary-table td{
    padding:8px 3px;
    border-bottom:1px solid #263640;
    color:#DCE4E8;
}

.summary-table td:nth-child(2){
    text-align:right;
    font-weight:750;
    color:#fff;
}

.summary-table tr:last-child td{
    border-bottom:none;
}

/* ============================================================
   INVENTARIO
   ============================================================ */
.inventory-grid{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:10px;
    margin-top:9px;
}

.inv-card{
    display:flex;
    align-items:center;
    justify-content:space-between;
    min-height:76px;
    border:1px solid #2B3B46;
    border-radius:8px;
    padding:11px 12px;
    background:#0B141A;
}

.inv-card strong{
    color:#fff;
    font-size:22px;
}

.inv-card span{
    display:block;
    color:#9EADB7;
    font-size:9px;
}

/* ============================================================
   ALERTAS
   ============================================================ */
.alert-list{
    display:flex;
    flex-direction:column;
    gap:4px;
}

.alert-row{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    padding:8px 2px;
    border-bottom:1px solid #23333D;
}

.alert-row:last-child{
    border-bottom:none;
}

.alert-copy{
    display:flex;
    align-items:center;
    gap:9px;
}

.alert-icon{
    width:30px;
    height:30px;
    border-radius:50%;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#FFC400;
    background:#332B08;
    border:1px solid #4B3D0A;
    font-weight:900;
    font-size:12px;
}

.alert-row strong{
    display:block;
    color:#F3F6F8;
    font-size:9px;
}

.alert-row small{
    color:#7E909C;
    font-size:8px;
}

.alert-value{
    color:#FFC400;
    font-weight:850;
    font-size:12px;
}

/* ============================================================
   BOTONES ACCESO RÁPIDO
   ============================================================ */
div[data-testid="stButton"] > button{
    min-height:58px;
    border-radius:8px !important;
    background:#0E181F !important;
    border:1px solid #30414C !important;
    color:#E8EEF1 !important;
    box-shadow:none !important;
    font-weight:700 !important;
    font-size:10px !important;
}

div[data-testid="stButton"] > button:hover{
    border-color:#FFC400 !important;
    color:#FFC400 !important;
}

/* ============================================================
   DATAFRAMES
   ============================================================ */
div[data-testid="stDataFrame"]{
    border:1px solid #273741;
    border-radius:8px;
    overflow:hidden;
}

/* ============================================================
   CHARTS
   ============================================================ */
.vega-embed,
.vega-embed > div{
    background:transparent !important;
}

/* ============================================================
   RESPONSIVE
   ============================================================ */
@media(max-width:1100px){
    .dash-kpis{
        grid-template-columns:repeat(2,minmax(0,1fr));
    }
}

@media(max-width:700px){
    .dash-head{
        flex-direction:column;
    }

    .dash-kpis{
        grid-template-columns:1fr;
    }
}


/* ============================================================
   ACCESOS RÁPIDOS · TARJETAS LIMPIAS
   ============================================================ */
.quick-card-icon{
    height:58px;
    display:flex;
    align-items:flex-end;
    justify-content:center;
    color:#FFC400;
    font-size:30px;
    font-weight:850;
    margin-top:4px;
    margin-bottom:5px;
    pointer-events:none;
}

.quick-card-label{
    min-height:34px;
    display:flex;
    align-items:flex-start;
    justify-content:center;
    text-align:center;
    color:#F4F7F9;
    font-size:10px;
    font-weight:650;
    line-height:1.2;
    padding:0 4px;
    pointer-events:none;
}

/* El botón "Abrir" ocupa la tarjeta completa visualmente,
   pero ocultamos su texto para no superponer icono y nombre */
div[data-testid="stButton"] > button[kind="secondary"]{
    position:relative;
}

/* Sólo afecta botones de quick access por estructura dentro de columnas */
div[data-testid="stHorizontalBlock"] div[data-testid="column"] .quick-card-label + div[data-testid="stButton"] > button{
    min-height:30px !important;
    margin-top:4px !important;
    padding:0 !important;
    background:#0D171E !important;
    border:1px solid #30414C !important;
    border-radius:7px !important;
    color:#8FA0AB !important;
    font-size:8px !important;
    font-weight:600 !important;
}

div[data-testid="stHorizontalBlock"] div[data-testid="column"] .quick-card-label + div[data-testid="stButton"] > button:hover{
    border-color:#FFC400 !important;
    color:#FFC400 !important;
}

/* Marco exterior visual de cada acceso */
div[data-testid="stHorizontalBlock"] div[data-testid="column"]:has(.quick-card-icon){
    background:linear-gradient(180deg,#101B23,#0C151B);
    border:1px solid #30414C;
    border-radius:8px;
    padding:10px 8px 8px;
    min-height:132px;
}

div[data-testid="stHorizontalBlock"] div[data-testid="column"]:has(.quick-card-icon):hover{
    border-color:#FFC400;
    background:#111D25;
}


/* ============================================================
   SIDEBAR · ESTADO ACTIVO
   El botón activo debe ser amarillo Maritex con texto negro.
   ============================================================ */
section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"],
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"]{
    background:#FFC400 !important;
    border:1px solid #FFC400 !important;
    border-left:4px solid #FFE16A !important;
    color:#080D11 !important;
    font-weight:800 !important;
    opacity:1 !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"] *,
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"] *{
    color:#080D11 !important;
    fill:#080D11 !important;
    opacity:1 !important;
}

section[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="stBaseButton-primary"]:hover,
section[data-testid="stSidebar"] div[data-testid="stButton"] button[kind="primary"]:hover{
    background:#FFD02A !important;
    border-color:#FFD02A !important;
    color:#080D11 !important;
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

    stock = _stock_metrics(ctx)
    sales_all = _prepare_sales(
        ctx.get("sales_df")
    )

    period_start, period_end = (
        _sales_period(sales_all)
    )

    now = datetime.now()

    stock_meta = (
        ctx.get("stock_meta")
        or {}
    )

    sales_meta = (
        ctx.get("sales_meta")
        or {}
    )

    updated = escape(
        str(
            sales_meta.get("loaded_at")
            or stock_meta.get("loaded_at")
            or now.strftime(
                "%d-%m-%Y %H:%M"
            )
        )
    )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------
    render_html(
        f"""
<div class="dash-head">
    <div>
        <div class="dash-title-line">
            <span class="dash-title-mark"></span>
            <div class="dash-title">Dashboard</div>
        </div>
        <div class="dash-sub">
            Resumen general del negocio · ventas, inventario y gestión comercial.
        </div>
    </div>

    <div>
        <div class="dash-live">
            <i></i>
            ERP + CRM conectados
        </div>
        <div class="dash-sub" style="text-align:right;margin-top:6px;">
            Última actualización: {updated}
        </div>
    </div>
</div>
        """
    )

    if (
        sales_all is None
        or sales_all.empty
        or period_start is None
        or period_end is None
    ):
        st.warning(
            "No hay datos de ERP Ventas disponibles para construir el dashboard comercial."
        )
        return

    # --------------------------------------------------------
    # FILTROS
    # --------------------------------------------------------
    with st.container(border=True):
        selected_period = st.date_input(
            "Período",
            value=(period_start, period_end),
            min_value=period_start,
            max_value=period_end,
            key="home_dash_period_v2",
        )

    # Inicio siempre consolidado: sin filtro por vendedor.
    selected_seller = "Todos"

    if (
        isinstance(
            selected_period,
            (tuple, list),
        )
        and len(selected_period) == 2
    ):
        start_date, end_date = (
            selected_period
        )
    else:
        start_date = selected_period
        end_date = selected_period

    # ========================================================
    # VISTA COMERCIAL ÚNICA COMPARTIDA
    # ========================================================
    sales = filter_commercial_view(
        sales_all,
        start_date,
        end_date,
    )

    metrics = _sales_summary(
        sales
    )

    crm = _crm_alerts()

    source_name = _safe_text(
        (ctx.get("sales_meta") or {}).get("filename"),
        "ERP Ventas",
    )
    actual_max_date = (
        sales_all["Fecha_dt"].max().strftime("%d-%m-%Y")
        if not sales_all.empty
        else "-"
    )

    st.caption(
        "Servicio comercial único · catálogo autorizado + "
        "Factura + Boleta - Nota de crédito · Con IVA · "
        f"Fuente: {source_name} · Última fecha ERP: {actual_max_date}"
    )

    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------
    render_html(
        f"""
<div class="dash-kpis">

    <article class="dash-kpi">
        <div class="dash-kpi-top">
            <div class="dash-kpi-icon green">$</div>
            <div class="dash-kpi-label">
                Ventas del período
                {_help("Misma venta neta del Resumen Ejecutivo: Facturas + Boletas - Notas de crédito, con IVA.")}
            </div>
        </div>
        <div class="dash-kpi-value">{_money(metrics["net"])}</div>
        <div class="dash-kpi-sub">
            {pd.Timestamp(start_date).strftime("%d-%m-%Y")} al {pd.Timestamp(end_date).strftime("%d-%m-%Y")}
        </div>
        <div class="dash-kpi-foot">Fuente: ERP Ventas</div>
    </article>

    <article class="dash-kpi">
        <div class="dash-kpi-top">
            <div class="dash-kpi-icon blue">◫</div>
            <div class="dash-kpi-label">
                Stock total
                {_help("Cantidad total de unidades disponibles en el inventario consolidado.")}
            </div>
        </div>
        <div class="dash-kpi-value">{stock["units"]:,}</div>
        <div class="dash-kpi-sub">Unidades disponibles</div>
        <div class="dash-kpi-foot">{stock["warehouses"]} bodegas detectadas</div>
    </article>

    <article class="dash-kpi">
        <div class="dash-kpi-top">
            <div class="dash-kpi-icon purple">◇</div>
            <div class="dash-kpi-label">
                SKU activos
                {_help("Cantidad de SKU distintos contenidos en el inventario consolidado.")}
            </div>
        </div>
        <div class="dash-kpi-value">{stock["sku"]:,}</div>
        <div class="dash-kpi-sub">Códigos de inventario</div>
        <div class="dash-kpi-foot">{stock["low"] + stock["zero"]:,} requieren atención</div>
    </article>

    <article class="dash-kpi">
        <div class="dash-kpi-top">
            <div class="dash-kpi-icon yellow">▥</div>
            <div class="dash-kpi-label">
                Valor inventario
                {_help("Valor estimado del inventario disponible: unidades disponibles por precio ERP.")}
            </div>
        </div>
        <div class="dash-kpi-value">{_money(stock["value"])}</div>
        <div class="dash-kpi-sub">Disponible × precio ERP</div>
        <div class="dash-kpi-foot">Fuente: ERP Stock</div>
    </article>

    <article class="dash-kpi">
        <div class="dash-kpi-top">
            <div class="dash-kpi-icon red">▤</div>
            <div class="dash-kpi-label">
                Documentos de venta
                {_help("Cantidad de facturas y boletas únicas del período seleccionado.")}
            </div>
        </div>
        <div class="dash-kpi-value">{metrics["documents"]:,}</div>
        <div class="dash-kpi-sub">Facturas + Boletas</div>
        <div class="dash-kpi-foot">{metrics["clients"]:,} clientes atendidos</div>
    </article>

</div>
        """
    )

    # --------------------------------------------------------
    # FILA 1
    # --------------------------------------------------------
    left, center, right = st.columns(
        [1.08, 1.35, 1.20],
        gap="medium",
    )

    with left:
        with st.container(border=True):
            render_html(
                f"""
<div class="card-title">
    Resumen comercial
    {_help("Indicadores principales del período comercial seleccionado.")}
</div>
<div class="card-sub">ERP Ventas · misma base comercial del Resumen Ejecutivo</div>

<table class="summary-table">
    <tr><td>Venta neta</td><td>{_money(metrics["net"])}</td></tr>
    <tr><td>Ventas brutas</td><td>{_money(metrics["gross"])}</td></tr>
    <tr><td>Notas de crédito</td><td>{_money(metrics["credits"])}</td></tr>
    <tr><td>Documentos</td><td>{metrics["documents"]:,}</td></tr>
    <tr><td>Clientes atendidos</td><td>{metrics["clients"]:,}</td></tr>
    <tr><td>Ticket promedio</td><td>{_money(metrics["ticket"])}</td></tr>
</table>
                """
            )

    with center:
        with st.container(border=True):
            render_html(
                f"""
<div class="card-title">
    Ventas por día
    {_help("Evolución diaria de la venta neta comercial dentro del período seleccionado.")}
</div>
<div class="card-sub">Facturas + Boletas - Notas de crédito</div>
                """
            )

            daily = _daily_sales(
                sales
            )

            if daily.empty:
                st.info(
                    "No hay ventas para el período seleccionado."
                )
            else:
                chart = (
                    alt.Chart(daily)
                    .mark_area(
                        line={
                            "color":
                            "#FFC400",
                            "strokeWidth":
                            2.4,
                        },
                        color="#FFC400",
                        opacity=.14,
                    )
                    .encode(
                        x=alt.X(
                            "Día:T",
                            title=None,
                            axis=alt.Axis(
                                format="%d-%m",
                                labelColor="#9CAEB9",
                                grid=False,
                            ),
                        ),
                        y=alt.Y(
                            "Venta:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#9CAEB9",
                                gridColor="#25343E",
                                format="~s",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Día:T",
                                title="Fecha",
                                format="%d-%m-%Y",
                            ),
                            alt.Tooltip(
                                "Venta:Q",
                                title="Venta",
                                format=",.0f",
                            ),
                        ],
                    )
                    .properties(
                        height=285
                    )
                    .configure_view(
                        stroke=None
                    )
                    .configure(
                        background="#0D161D"
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

    with right:
        with st.container(border=True):
            branch_sales = _sales_by_branch(sales)

            render_html(
                f"""
<div class="card-title">
    Ventas por sucursal
    {_help("Distribución de la venta comercial entre Casa Matriz, Patronato y Concepción. No incluye CD ni bodegas de reserva.")}
</div>
<div class="card-sub">Casa Matriz · Patronato · Concepción</div>
                """
            )

            branch_positive = branch_sales[branch_sales["Venta"] > 0].copy()

            if branch_positive.empty:
                st.info(
                    "No hay ventas asociadas a Casa Matriz, Patronato o Concepción en el período seleccionado."
                )
            else:
                donut = (
                    alt.Chart(branch_positive)
                    .mark_arc(
                        innerRadius=58,
                        outerRadius=92,
                    )
                    .encode(
                        theta=alt.Theta("Venta:Q"),
                        color=alt.Color(
                            "Sucursal:N",
                            sort=["Casa Matriz", "Patronato", "Concepción"],
                            legend=alt.Legend(
                                labelColor="#DCE4E8",
                                title=None,
                            ),
                            scale=alt.Scale(
                                domain=["Casa Matriz", "Patronato", "Concepción"],
                                range=["#FFC400", "#2B8CEB", "#29C38F"],
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip("Sucursal:N", title="Sucursal"),
                            alt.Tooltip("Venta:Q", title="Venta", format=",.0f"),
                        ],
                    )
                    .properties(height=285)
                    .configure_view(stroke=None)
                    .configure(background="#0D161D")
                )

                st.altair_chart(
                    donut,
                    use_container_width=True,
                )

    # --------------------------------------------------------
    # FILA 2
    # --------------------------------------------------------
    left2, center2, right2 = st.columns(
        [1.05, 1.30, 1.10],
        gap="medium",
    )

    with left2:
        with st.container(border=True):
            render_html(
                f"""
<div class="card-title">
    Top vendedores
    {_help("Ranking de vendedores por venta neta en el período seleccionado.")}
</div>
<div class="card-sub">Excluye códigos 36, 52 y 53</div>
                """
            )

            ranking = _seller_ranking(
                sales,
                limit=6,
            )

            if ranking.empty:
                st.caption(
                    "Sin datos de vendedores."
                )
            else:
                st.dataframe(
                    ranking,
                    hide_index=True,
                    use_container_width=True,
                    height=255,
                    column_config={
                        "Ventas del período":
                        st.column_config.NumberColumn(
                            "Ventas del período",
                            format="$ %.0f",
                        ),
                        "% Participación":
                        st.column_config.NumberColumn(
                            "% Participación",
                            format="%.1f %%",
                        ),
                    },
                )

    with center2:
        with st.container(border=True):
            render_html(
                f"""
<div class="card-title">
    Clientes top por ventas
    {_help("Clientes con mayor venta neta dentro del período seleccionado.")}
</div>
<div class="card-sub">ERP Ventas</div>
                """
            )

            clients = _top_clients(
                sales,
                limit=6,
            )

            if clients.empty:
                st.caption(
                    "Sin datos de clientes."
                )
            else:
                st.dataframe(
                    clients,
                    hide_index=True,
                    use_container_width=True,
                    height=255,
                    column_config={
                        "Ventas del período":
                        st.column_config.NumberColumn(
                            "Ventas del período",
                            format="$ %.0f",
                        ),
                        "Pedidos":
                        st.column_config.NumberColumn(
                            "Pedidos",
                            format="%d",
                        ),
                    },
                )

    with right2:
        with st.container(border=True):
            total_states = max(
                stock["healthy"]
                + stock["low"]
                + stock["zero"]
                + stock["risk"],
                1,
            )

            def pct(value):
                return (
                    value / total_states * 100
                )

            render_html(
                f"""
<div class="card-title">
    Estado del inventario
    {_help("Distribución de SKU según el estado consolidado del inventario.")}
</div>
<div class="card-sub">Visión rápida de disponibilidad y riesgo</div>

<div class="inventory-grid">

    <div class="inv-card">
        <div>
            <span>Con stock</span>
            <strong>{stock["healthy"]:,}</strong>
        </div>
        <span style="color:#28CC74;font-weight:800;">{pct(stock["healthy"]):.1f}%</span>
    </div>

    <div class="inv-card">
        <div>
            <span>Stock bajo</span>
            <strong>{stock["low"]:,}</strong>
        </div>
        <span style="color:#FFC400;font-weight:800;">{pct(stock["low"]):.1f}%</span>
    </div>

    <div class="inv-card">
        <div>
            <span>Sin stock</span>
            <strong>{stock["zero"]:,}</strong>
        </div>
        <span style="color:#FF4F4F;font-weight:800;">{pct(stock["zero"]):.1f}%</span>
    </div>

    <div class="inv-card">
        <div>
            <span>Riesgo despacho</span>
            <strong>{stock["risk"]:,}</strong>
        </div>
        <span style="color:#64A8FF;font-weight:800;">{pct(stock["risk"]):.1f}%</span>
    </div>

</div>
                """
            )

    # --------------------------------------------------------
    # FILA 3
    # --------------------------------------------------------
    alerts_col, quick_col = st.columns(
        [1.05, 1.55],
        gap="medium",
    )

    with alerts_col:
        with st.container(border=True):
            render_html(
                f"""
<div class="card-title">
    Alertas y pendientes
    {_help("Resumen de alertas operativas provenientes de inventario y CRM.")}
</div>
<div class="card-sub">Elementos que requieren revisión</div>

<div class="alert-list">

    <div class="alert-row">
        <div class="alert-copy">
            <div class="alert-icon">!</div>
            <div>
                <strong>Seguimientos vencidos</strong>
                <small>CRM · requiere gestión comercial</small>
            </div>
        </div>
        <div class="alert-value">{crm["overdue_followups"]:,}</div>
    </div>

    <div class="alert-row">
        <div class="alert-copy">
            <div class="alert-icon">◷</div>
            <div>
                <strong>Seguimientos pendientes</strong>
                <small>CRM · actividades por realizar</small>
            </div>
        </div>
        <div class="alert-value">{crm["pending_followups"]:,}</div>
    </div>

    <div class="alert-row">
        <div class="alert-copy">
            <div class="alert-icon">▣</div>
            <div>
                <strong>SKU con stock bajo</strong>
                <small>Inventario · revisar reposición</small>
            </div>
        </div>
        <div class="alert-value">{stock["low"]:,}</div>
    </div>

    <div class="alert-row">
        <div class="alert-copy">
            <div class="alert-icon">×</div>
            <div>
                <strong>SKU sin stock</strong>
                <small>Inventario · sin disponibilidad</small>
            </div>
        </div>
        <div class="alert-value">{stock["zero"]:,}</div>
    </div>

</div>
                """
            )

    with quick_col:
        with st.container(border=True):
            render_html(
                """
<div class="card-title">Accesos rápidos</div>
<div class="card-sub">Navegación directa a los módulos principales</div>
                """
            )

            q1, q2, q3, q4, q5, q6 = st.columns(6, gap="small")

            quick_items = [
                (q1, "▥", "Resumen Ejecutivo", "dash_quick_exec", "Resumen Ejecutivo"),
                (q2, "♙", "Clientes", "dash_quick_clients", "CRM"),
                (q3, "□", "Oportunidades", "dash_quick_opps", "CRM"),
                (q4, "○", "CRM", "dash_quick_crm", "CRM"),
                (q5, "⌁", "Métricas Vendedores", "dash_quick_sellers", "Métricas Vendedores"),
                (q6, "▤", "Plantillas", "dash_quick_templates", "Plantillas"),
            ]

            for col, icon, label, key, page in quick_items:
                with col:
                    st.markdown(
                        f"""
<div class="quick-card-icon">{icon}</div>
<div class="quick-card-label">{label}</div>
                        """,
                        unsafe_allow_html=True,
                    )

                    st.button(
                        "Abrir",
                        key=key,
                        use_container_width=True,
                        on_click=_go_to,
                        args=(page,),
                    )

    # Fin del dashboard
    return None
