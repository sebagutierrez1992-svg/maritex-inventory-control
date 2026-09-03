

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from services.crm_service import (
    create_followup,
    create_opportunity,
    get_crm_summary,
    get_pipeline_summary,
    list_followups,
    list_opportunities,
    update_followup,
    update_opportunity,
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

CRM_TABS = (
    "Resumen",
    "Clientes",
    "Oportunidades",
    "Seguimientos",
    "Pipeline",
)


CRM_STAGES = (
    "Prospección",
    "Contacto",
    "Cotización",
    "Negociación",
    "Cierre",
)

CRM_STATUSES = (
    "Abierta",
    "Ganada",
    "Perdida",
)

CRM_STAGE_PROBABILITY = {
    "Prospección": 10,
    "Contacto": 25,
    "Cotización": 50,
    "Negociación": 75,
    "Cierre": 90,
}


CRM_FOLLOWUP_TYPES = (
    "Llamada",
    "Correo",
    "Reunión",
    "WhatsApp",
    "Tarea",
    "Nota",
)


# ============================================================
# ESTILOS
# ============================================================

def _apply_styles() -> None:
    st.markdown(
        """
<style>
/* =========================================================
   CRM MONDAY-INSPIRED · MARITEX
   ========================================================= */

.block-container{
    max-width:1700px;
    padding-top:1rem;
    padding-bottom:2.5rem;
}

[data-testid="stAppViewContainer"]{
    background:#F6F7FB;
}

[data-testid="stHeader"]{
    background:rgba(246,247,251,.92);
}

div[data-testid="stVerticalBlock"]{
    gap:.72rem;
}

/* ---------------------------------------------------------
   HEADER
   --------------------------------------------------------- */

.crm-page-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:18px;
    padding:18px 20px;
    border:1px solid #E3E6EC;
    border-radius:16px;
    background:#FFFFFF;
    box-shadow:0 4px 18px rgba(20,32,50,.05);
    margin-bottom:10px;
}

.crm-page-head h1{
    margin:0;
    color:#171B24;
    font-size:31px;
    line-height:1;
    letter-spacing:-.8px;
    font-weight:850;
}

.crm-page-head p{
    margin:8px 0 0;
    color:#737C8B;
    font-size:12px;
}

.crm-live-pill{
    display:inline-flex;
    align-items:center;
    gap:8px;
    padding:9px 13px;
    border:1px solid #DDE2E8;
    border-radius:999px;
    background:#FAFBFC;
    color:#384252;
    font-size:10px;
    font-weight:750;
    white-space:nowrap;
}

.crm-live-pill i{
    display:block;
    width:8px;
    height:8px;
    border-radius:999px;
    background:#22C55E;
    box-shadow:0 0 0 4px rgba(34,197,94,.10);
}

/* ---------------------------------------------------------
   NAV / SEGMENTED
   --------------------------------------------------------- */

div[data-testid="stSegmentedControl"]{
    background:#FFFFFF;
    border:1px solid #E2E6EC;
    border-radius:13px;
    padding:4px;
    box-shadow:0 2px 10px rgba(20,32,50,.04);
}

div[data-testid="stSegmentedControl"] button{
    color:#586273 !important;
    border-radius:9px !important;
    font-size:10px !important;
    font-weight:750 !important;
}

div[data-testid="stSegmentedControl"] button[aria-pressed="true"]{
    background:#FFF6CC !important;
    color:#5E4A00 !important;
    box-shadow:inset 0 0 0 1px #F2C200 !important;
}

/* ---------------------------------------------------------
   KPI CARDS
   --------------------------------------------------------- */

.crm-kpis{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:12px;
    margin:8px 0 12px;
}

.crm-kpi{
    position:relative;
    overflow:hidden;
    min-height:118px;
    border:1px solid #E4E8EE;
    border-radius:14px;
    padding:16px;
    background:#FFFFFF;
    box-shadow:0 3px 14px rgba(20,32,50,.045);
}

.crm-kpi::before{
    content:"";
    position:absolute;
    left:0;
    top:0;
    bottom:0;
    width:4px;
    border-radius:14px 0 0 14px;
}

.crm-kpi.yellow::before{background:#F6C500}
.crm-kpi.green::before{background:#22C55E}
.crm-kpi.purple::before{background:#8B5CF6}
.crm-kpi.orange::before{background:#F97316}

.crm-kpi-label{
    color:#7A8492;
    font-size:9px;
    text-transform:uppercase;
    letter-spacing:.06em;
    font-weight:800;
}

.crm-kpi-value{
    color:#1D2430;
    font-size:24px;
    font-weight:850;
    line-height:1;
    margin-top:8px;
    letter-spacing:-.45px;
}

.crm-kpi-help{
    color:#8A94A3;
    font-size:8.8px;
    margin-top:10px;
    font-weight:650;
}

.crm-kpi-help.green{color:#16A34A}
.crm-kpi-help.orange{color:#EA580C}

/* ---------------------------------------------------------
   CONTAINERS / TABLES
   --------------------------------------------------------- */

div[data-testid="stVerticalBlockBorderWrapper"]{
    border:1px solid #E2E6EC !important;
    background:#FFFFFF !important;
    border-radius:14px !important;
    box-shadow:0 3px 14px rgba(20,32,50,.04) !important;
}

div[data-testid="stDataFrame"]{
    border:1px solid #E2E6EC;
    border-radius:12px;
    overflow:hidden;
    background:#FFFFFF;
}

div[data-testid="stDataFrame"] *{
    color:#26303D;
}

div[data-testid="stMetric"]{
    border:1px solid #E2E6EC;
    border-radius:12px;
    background:#FFFFFF;
    padding:10px 12px;
}

div[data-testid="stMetricLabel"]{
    color:#7B8592 !important;
    font-size:9px !important;
    font-weight:750 !important;
}

div[data-testid="stMetricValue"]{
    color:#1D2430 !important;
    font-size:19px !important;
}

/* ---------------------------------------------------------
   SECTION TITLES
   --------------------------------------------------------- */

.crm-section-kicker{
    color:#B58D00;
    text-transform:uppercase;
    letter-spacing:.10em;
    font-size:8px;
    font-weight:850;
    margin-bottom:3px;
}

.crm-section-title{
    color:#202733;
    font-size:14px;
    font-weight:850;
    margin:0 0 3px;
}

.crm-section-sub{
    color:#8A94A3;
    font-size:9px;
    margin-bottom:8px;
}

.crm-client-title{
    color:#202733;
    font-size:19px;
    font-weight:850;
    margin-bottom:2px;
}

.crm-client-sub{
    color:#8A94A3;
    font-size:10px;
    margin-bottom:8px;
}

/* ---------------------------------------------------------
   TOP CLIENTS
   --------------------------------------------------------- */

.crm-top-row{
    display:grid;
    grid-template-columns:28px minmax(0,1.6fr) 110px 92px 65px 90px;
    gap:8px;
    align-items:center;
    min-height:39px;
    border-bottom:1px solid #EEF1F4;
    font-size:8.8px;
}

.crm-top-row.header{
    color:#9099A6;
    font-size:7.7px;
    text-transform:uppercase;
    font-weight:750;
}

.crm-top-row:last-child{border-bottom:0}
.crm-rank{color:#9099A6;font-weight:800}
.crm-client-name{
    color:#28313E;
    font-weight:780;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.crm-client-rut{color:#7E8794}
.crm-money{color:#9B7B00;font-weight:850;text-align:right}
.crm-orders{color:#495261;text-align:right}
.crm-date{color:#65707F;text-align:right}

/* ---------------------------------------------------------
   EMPTY STATES
   --------------------------------------------------------- */

.crm-empty{
    min-height:170px;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    text-align:center;
    border:1px dashed #D8DEE6;
    border-radius:12px;
    color:#8A94A3;
    padding:20px;
    background:#FBFCFD;
}

.crm-empty strong{
    color:#303846;
    font-size:12px;
    margin-bottom:5px;
}

.crm-empty span{
    font-size:9px;
    max-width:360px;
}

/* ---------------------------------------------------------
   INPUTS / BUTTONS
   --------------------------------------------------------- */

.stButton>button{
    border-radius:9px !important;
    min-height:36px !important;
    font-size:9.5px !important;
    font-weight:780 !important;
}

.stButton>button[kind="primary"]{
    background:#F5C400 !important;
    border-color:#F5C400 !important;
    color:#302600 !important;
}

[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] div[data-baseweb="select"]>div,
[data-testid="stNumberInput"] input,
[data-testid="stDateInput"] input{
    background:#FFFFFF !important;
    border-color:#DDE2E8 !important;
    color:#202733 !important;
    border-radius:9px !important;
}

[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stDateInput"] label,
[data-testid="stRadio"] label{
    color:#66717F !important;
    font-size:9px !important;
    font-weight:750 !important;
}

/* ---------------------------------------------------------
   EXPANDERS
   --------------------------------------------------------- */

details{
    background:#FFFFFF !important;
    border:1px solid #E2E6EC !important;
    border-radius:12px !important;
}

details summary{
    color:#384252 !important;
    font-size:10px !important;
    font-weight:780 !important;
}

/* ---------------------------------------------------------
   MONDAY BOARD
   --------------------------------------------------------- */

.crm-board-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
    margin:8px 0 10px;
}

.crm-board-title{
    font-size:15px;
    font-weight:850;
    color:#202733;
}

.crm-board-meta{
    font-size:9px;
    color:#8A94A3;
}

.crm-stage-head{
    border-radius:12px 12px 8px 8px;
    padding:12px 12px 10px;
    margin-bottom:8px;
    background:#FFFFFF;
    border:1px solid #E1E6EC;
    box-shadow:0 2px 10px rgba(20,32,50,.035);
    position:relative;
    overflow:hidden;
}

.crm-stage-head::before{
    content:"";
    position:absolute;
    left:0;
    top:0;
    right:0;
    height:4px;
    background:#F5C400;
}

.crm-stage-name{
    color:#303846;
    font-size:11px;
    font-weight:850;
    margin-top:2px;
}

.crm-stage-count{
    color:#1D2430;
    font-size:21px;
    font-weight:850;
    margin-top:5px;
}

.crm-stage-total{
    color:#8B95A2;
    font-size:8.5px;
    margin-top:2px;
}

.crm-kanban-card{
    border:1px solid #E2E6EC;
    border-radius:12px;
    padding:12px;
    margin-bottom:8px;
    background:#FFFFFF;
    box-shadow:0 3px 12px rgba(20,32,50,.045);
}

.crm-kanban-id{
    color:#9AA3AE;
    font-size:7.8px;
    margin-bottom:5px;
}

.crm-kanban-client{
    color:#27303C;
    font-size:10.5px;
    font-weight:850;
    line-height:1.25;
}

.crm-kanban-title{
    color:#717B88;
    font-size:8.8px;
    margin-top:4px;
}

.crm-kanban-money{
    color:#8A6D00;
    font-size:13px;
    font-weight:850;
    margin-top:10px;
}

.crm-kanban-chip{
    display:inline-flex;
    align-items:center;
    padding:3px 7px;
    border-radius:999px;
    background:#FFF4C2;
    color:#725900;
    font-size:7.5px;
    font-weight:800;
    margin-top:6px;
}

.crm-kanban-label{
    color:#9AA3AE;
    font-size:7.5px;
    margin-top:9px;
}

.crm-kanban-action{
    color:#47515E;
    font-size:8.5px;
    margin-top:2px;
    line-height:1.3;
}

.crm-kanban-date{
    color:#7D8794;
    font-size:7.7px;
    margin-top:3px;
}

.crm-stage-empty{
    border:1px dashed #D9DEE5;
    border-radius:10px;
    padding:22px 10px;
    color:#A0A8B3;
    text-align:center;
    font-size:8.5px;
    background:#FAFBFC;
}

hr{
    border-color:#E9EDF1 !important;
}

/* ---------------------------------------------------------
   RESPONSIVE
   --------------------------------------------------------- */

@media(max-width:1100px){
    .crm-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
}

@media(max-width:700px){
    .crm-page-head{
        flex-direction:column;
        align-items:flex-start;
    }
    .crm-kpis{grid-template-columns:1fr}
}
</style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# HELPERS
# ============================================================

def _safe_text(
    value: Any,
    default: str = "-",
) -> str:
    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    if text.lower() in {
        "nan",
        "none",
        "nat",
    }:
        return default

    return text


def _money(
    value: Any,
) -> str:
    try:
        number = float(value or 0)
    except Exception:
        number = 0

    return (
        f"${number:,.0f}"
        .replace(",", ".")
    )


def _number(
    value: Any,
) -> float:
    number = pd.to_numeric(
        value,
        errors="coerce",
    )

    if pd.isna(number):
        return 0.0

    return float(number)


def _normalize_name(
    value: Any,
) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
        .replace(".", "")
    )


def _find_column(
    df: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    if df is None or df.empty:
        return None

    normalized = {
        _normalize_name(column): column
        for column in df.columns
    }

    # Coincidencia exacta
    for candidate in candidates:
        key = _normalize_name(candidate)

        if key in normalized:
            return normalized[key]

    # Coincidencia parcial
    for candidate in candidates:
        key = _normalize_name(candidate)

        for normalized_column, original_column in normalized.items():
            if (
                key in normalized_column
                or normalized_column in key
            ):
                return original_column

    return None


def _db_rows_to_frame(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)

    for column in (
        "estimated_amount",
        "probability",
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="coerce",
            ).fillna(0)

    return frame


def _opportunity_display_frame(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    frame = _db_rows_to_frame(rows)

    if frame.empty:
        return pd.DataFrame(
            columns=[
                "ID",
                "Cliente",
                "RUT",
                "Oportunidad",
                "Monto",
                "Etapa",
                "Probabilidad",
                "Estado",
                "Vendedor",
                "Cierre estimado",
                "Próxima acción",
                "Fecha próxima acción",
            ]
        )

    display = pd.DataFrame(
        {
            "ID": frame["id"],
            "Cliente": frame["client_name"],
            "RUT": frame["client_rut"].fillna("-"),
            "Oportunidad": frame["title"],
            "Monto": frame["estimated_amount"],
            "Etapa": frame["stage"],
            "Probabilidad": frame["probability"],
            "Estado": frame["status"],
            "Vendedor": frame["seller"].fillna("-"),
            "Cierre estimado": frame["expected_close_date"],
            "Próxima acción": frame["next_action"].fillna("-"),
            "Fecha próxima acción": frame["next_action_date"],
        }
    )

    for column in (
        "Cierre estimado",
        "Fecha próxima acción",
    ):
        display[column] = pd.to_datetime(
            display[column],
            errors="coerce",
        ).dt.strftime("%d-%m-%Y")

    return display




def _followup_display_frame(
    rows: list[dict[str, Any]],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=[
                "ID",
                "Fecha",
                "Cliente",
                "RUT",
                "Oportunidad",
                "Tipo",
                "Asunto",
                "Responsable",
                "Detalle",
                "Próximo seguimiento",
                "Estado",
            ]
        )

    frame = pd.DataFrame(rows)

    display = pd.DataFrame(
        {
            "ID": frame["id"],
            "Fecha": frame["followup_date"],
            "Cliente": frame["client_name"].fillna("-"),
            "RUT": frame["client_rut"].fillna("-"),
            "Oportunidad": frame["opportunity_id"].fillna("-"),
            "Tipo": frame["followup_type"].fillna("-"),
            "Asunto": frame["subject"].fillna("-"),
            "Responsable": frame["seller"].fillna("-"),
            "Detalle": frame["notes"].fillna("-"),
            "Próximo seguimiento": frame["next_followup_date"],
            "Estado": frame["completed"].map(
                {
                    True: "Completado",
                    False: "Pendiente",
                }
            ),
        }
    )

    display["Fecha"] = pd.to_datetime(
        display["Fecha"],
        errors="coerce",
    ).dt.strftime("%d-%m-%Y %H:%M")

    display["Próximo seguimiento"] = pd.to_datetime(
        display["Próximo seguimiento"],
        errors="coerce",
    ).dt.strftime("%d-%m-%Y")

    return display


def _followup_opportunity_label(
    opportunity: dict[str, Any],
) -> str:
    return (
        f"#{opportunity.get('id')} · "
        f"{_safe_text(opportunity.get('client_name'))} · "
        f"{_safe_text(opportunity.get('title'))}"
    )


# ============================================================
# DETECCIÓN DE COLUMNAS ERP VENTAS
# ============================================================

def _detect_sales_columns(
    sales_df: pd.DataFrame,
) -> dict:
    return {
        "rut": _find_column(
            sales_df,
            [
                "CodigoLegal",
                "CódigoLegal",
                "Codigo Legal",
                "Código Legal",
                "CodLegal",
                "rut cliente",
                "rutcliente",
                "rut",
                "cliente rut",
                "cod cliente",
                "codigo cliente",
            ],
        ),

        "client": _find_column(
            sales_df,
            [
                "RazonSocial",
                "RazónSocial",
                "razon social",
                "razón social",
                "cliente",
                "nombre cliente",
                "nombre",
                "glosa cliente",
            ],
        ),

        "seller": _find_column(
            sales_df,
            [
                "vendedor",
                "nombre vendedor",
                "ejecutivo",
                "seller",
            ],
        ),

        "date": _find_column(
            sales_df,
            [
                "fecha",
                "fecha documento",
                "fecha emision",
                "fecha emisión",
                "fec emision",
            ],
        ),

        "amount": _find_column(
            sales_df,
            [
                "TotalIngreso",
                "total ingreso",
                "total",
                "venta",
                "monto",
                "monto neto",
                "neto",
                "total documento",
                "valor venta",
            ],
        ),

        "document": _find_column(
            sales_df,
            [
                "numero documento",
                "nro documento",
                "documento",
                "folio",
                "numero",
            ],
        ),

        "product": _find_column(
            sales_df,
            [
                "producto",
                "descripcion producto",
                "descripción producto",
                "descripcion",
                "sku",
            ],
        ),
    }


# ============================================================
# PREPARAR CLIENTES
# ============================================================

def _prepare_clients(
    sales_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    if (
        sales_df is None
        or sales_df.empty
    ):
        return pd.DataFrame(), {}

    columns = _detect_sales_columns(
        sales_df
    )

    client_col = columns.get("client")
    rut_col = columns.get("rut")
    seller_col = columns.get("seller")
    date_col = columns.get("date")
    amount_col = columns.get("amount")
    document_col = columns.get("document")

    if not client_col and not rut_col:
        return pd.DataFrame(), columns

    work = sales_df.copy()

    # --------------------------------------------------------
    # Identificador cliente
    # --------------------------------------------------------

    if rut_col:
        work["_crm_rut"] = (
            work[rut_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        work["_crm_rut"] = ""

    if client_col:
        work["_crm_cliente"] = (
            work[client_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        work["_crm_cliente"] = ""

    work["_crm_key"] = work["_crm_rut"]

    empty_rut = (
        work["_crm_key"]
        .eq("")
    )

    work.loc[
        empty_rut,
        "_crm_key",
    ] = work.loc[
        empty_rut,
        "_crm_cliente",
    ]

    work = work[
        work["_crm_key"].astype(str).str.strip() != ""
    ].copy()

    if work.empty:
        return pd.DataFrame(), columns

    # --------------------------------------------------------
    # Fecha
    # --------------------------------------------------------

    if date_col:
        work["_crm_fecha"] = pd.to_datetime(
            work[date_col],
            errors="coerce",
            dayfirst=True,
        )
    else:
        work["_crm_fecha"] = pd.NaT

    # --------------------------------------------------------
    # Venta
    # --------------------------------------------------------

    if amount_col:
        work["_crm_venta"] = pd.to_numeric(
            work[amount_col],
            errors="coerce",
        ).fillna(0)
    else:
        work["_crm_venta"] = 0.0

    # --------------------------------------------------------
    # Vendedor
    # --------------------------------------------------------

    if seller_col:
        work["_crm_vendedor"] = (
            work[seller_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        work["_crm_vendedor"] = ""

    # --------------------------------------------------------
    # Nº pedidos/documentos
    # --------------------------------------------------------

    if document_col:
        work["_crm_documento"] = (
            work[document_col]
            .fillna("")
            .astype(str)
            .str.strip()
        )
    else:
        work["_crm_documento"] = ""

    # --------------------------------------------------------
    # Ventas 12 meses
    # --------------------------------------------------------

    valid_dates = work["_crm_fecha"].dropna()

    if not valid_dates.empty:
        max_date = valid_dates.max()
        cutoff = max_date - pd.DateOffset(months=12)

        work["_crm_venta_12m"] = work["_crm_venta"].where(
            work["_crm_fecha"] >= cutoff,
            0,
        )
    else:
        work["_crm_venta_12m"] = work["_crm_venta"]

    # --------------------------------------------------------
    # Agrupar
    # --------------------------------------------------------

    aggregation = {
        "Cliente": (
            "_crm_cliente",
            lambda values: next(
                (
                    str(v).strip()
                    for v in values
                    if str(v).strip()
                ),
                "-",
            ),
        ),

        "RUT": (
            "_crm_rut",
            lambda values: next(
                (
                    str(v).strip()
                    for v in values
                    if str(v).strip()
                ),
                "-",
            ),
        ),

        "Vendedor": (
            "_crm_vendedor",
            lambda values: next(
                (
                    str(v).strip()
                    for v in values
                    if str(v).strip()
                ),
                "-",
            ),
        ),

        "Última compra": (
            "_crm_fecha",
            "max",
        ),

        "Ventas acumuladas": (
            "_crm_venta",
            "sum",
        ),

        "Ventas 12 meses": (
            "_crm_venta_12m",
            "sum",
        ),
    }

    if document_col:
        aggregation["Pedidos"] = (
            "_crm_documento",
            "nunique",
        )
    else:
        aggregation["Pedidos"] = (
            "_crm_key",
            "size",
        )

    clients = (
        work
        .groupby(
            "_crm_key",
            dropna=False,
        )
        .agg(
            **aggregation
        )
        .reset_index()
        .rename(
            columns={
                "_crm_key": "_client_key",
            }
        )
    )

    clients["Ventas acumuladas"] = (
        pd.to_numeric(
            clients["Ventas acumuladas"],
            errors="coerce",
        )
        .fillna(0)
    )

    clients["Ventas 12 meses"] = (
        pd.to_numeric(
            clients["Ventas 12 meses"],
            errors="coerce",
        )
        .fillna(0)
    )

    clients["Pedidos"] = (
        pd.to_numeric(
            clients["Pedidos"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    clients = clients.sort_values(
        "Ventas 12 meses",
        ascending=False,
    ).reset_index(drop=True)

    return clients, columns


# ============================================================
# RESUMEN
# ============================================================

def _render_summary(
    clients: pd.DataFrame,
) -> None:
    if clients.empty:
        st.info("No existen datos de clientes disponibles.")
        return

    total_clients = len(clients)
    total_sales = clients["Ventas 12 meses"].sum()
    average_sales = clients["Ventas 12 meses"].mean() if total_clients else 0

    dates = pd.to_datetime(clients["Última compra"], errors="coerce")
    valid_dates = dates.dropna()

    inactive_clients = 0
    reference_date = None
    if not valid_dates.empty:
        reference_date = valid_dates.max()
        limit = reference_date - timedelta(days=90)
        inactive_clients = int((dates.notna() & (dates < limit)).sum())

    inactive_pct = (
        inactive_clients / total_clients * 100
        if total_clients
        else 0
    )

    try:
        crm_summary = get_crm_summary()
        upcoming_followups = list_followups(
            pending_only=True,
            limit=6,
        )
        open_opportunities = list_opportunities(
            status="Abierta",
            limit=6,
        )
    except Exception:
        crm_summary = {}
        upcoming_followups = []
        open_opportunities = []

    # KPIs
    # Importante: no dejamos líneas en blanco entre tarjetas HTML.
    # Streamlit/Markdown puede interpretar los bloques posteriores como código.
    kpi_html = (
        f'<div class="crm-kpis">'
        f'<div class="crm-kpi yellow">'
        f'<div class="crm-kpi-top">'
        f'<div class="crm-kpi-icon yellow">●</div>'
        f'<div>'
        f'<div class="crm-kpi-label">Clientes</div>'
        f'<div class="crm-kpi-value">{total_clients:,}</div>'
        f'<div class="crm-kpi-help">Total cartera</div>'
        f'</div></div></div>'
        f'<div class="crm-kpi green">'
        f'<div class="crm-kpi-top">'
        f'<div class="crm-kpi-icon green">$</div>'
        f'<div>'
        f'<div class="crm-kpi-label">Ventas 12 meses</div>'
        f'<div class="crm-kpi-value">{_money(total_sales)}</div>'
        f'<div class="crm-kpi-help green">Facturación reciente ERP</div>'
        f'</div></div></div>'
        f'<div class="crm-kpi purple">'
        f'<div class="crm-kpi-top">'
        f'<div class="crm-kpi-icon purple">▥</div>'
        f'<div>'
        f'<div class="crm-kpi-label">Venta promedio</div>'
        f'<div class="crm-kpi-value">{_money(average_sales)}</div>'
        f'<div class="crm-kpi-help">Promedio por cliente</div>'
        f'</div></div></div>'
        f'<div class="crm-kpi orange">'
        f'<div class="crm-kpi-top">'
        f'<div class="crm-kpi-icon orange">◷</div>'
        f'<div>'
        f'<div class="crm-kpi-label">Sin compra +90 días</div>'
        f'<div class="crm-kpi-value">{inactive_clients:,}</div>'
        f'<div class="crm-kpi-help orange">{inactive_pct:.1f}% de la cartera · al corte ERP</div>'
        f'</div></div></div>'
        f'</div>'
    ).replace(",", ".")

    st.markdown(kpi_html, unsafe_allow_html=True)

    s1, s2, s3 = st.columns(3, gap="small")

    with s1:
        st.metric(
            "Seguimientos pendientes",
            int(crm_summary.get("pending_followups") or 0),
        )

    with s2:
        st.metric(
            "Vencidos",
            int(crm_summary.get("overdue_followups") or 0),
        )

    with s3:
        st.metric(
            "Para hoy",
            int(crm_summary.get("today_followups") or 0),
        )

    # Primera fila: ranking / concentración / actividad
    left, middle, right = st.columns([1.48, 1.0, .92], gap="medium")

    with left:
        with st.container(border=True):
            st.markdown(
                """
<div class="crm-section-kicker">CLIENTES</div>
<div class="crm-section-title">Principales clientes</div>
<div class="crm-section-sub">Top por ventas de los últimos 12 meses.</div>
                """,
                unsafe_allow_html=True,
            )

            top = clients.head(7).copy()
            rows = """
<div class="crm-top-row header">
    <div>#</div><div>Cliente</div><div>RUT</div>
    <div style="text-align:right">Ventas 12m</div>
    <div style="text-align:right">Pedidos</div>
    <div style="text-align:right">Última compra</div>
</div>
"""
            for i, (_, row) in enumerate(top.iterrows(), start=1):
                dt = pd.to_datetime(row.get("Última compra"), errors="coerce")
                last = dt.strftime("%d-%m-%Y") if not pd.isna(dt) else "-"
                rows += f"""
<div class="crm-top-row">
    <div class="crm-rank">{i}</div>
    <div class="crm-client-name">{_safe_text(row.get("Cliente"))}</div>
    <div class="crm-client-rut">{_safe_text(row.get("RUT"))}</div>
    <div class="crm-money">{_money(row.get("Ventas 12 meses"))}</div>
    <div class="crm-orders">{int(_number(row.get("Pedidos")))}</div>
    <div class="crm-date">{last}</div>
</div>
"""
            st.markdown(rows, unsafe_allow_html=True)

    with middle:
        with st.container(border=True):
            st.markdown(
                """
<div class="crm-section-kicker">CONCENTRACIÓN</div>
<div class="crm-section-title">Ventas por cliente</div>
<div class="crm-section-sub">Participación de los principales clientes.</div>
                """,
                unsafe_allow_html=True,
            )

            chart = clients[["Cliente", "Ventas 12 meses"]].head(10).copy()
            chart = chart[chart["Ventas 12 meses"] > 0]
            if chart.empty:
                st.info("No existen montos de venta disponibles.")
            else:
                st.bar_chart(
                    chart.set_index("Cliente")["Ventas 12 meses"],
                    use_container_width=True,
                    height=285,
                )

    with right:
        with st.container(border=True):
            st.markdown(
                """
<div class="crm-section-kicker">ACTIVIDAD</div>
<div class="crm-section-title">Actividad próxima</div>
<div class="crm-section-sub">Seguimientos comerciales pendientes.</div>
                """,
                unsafe_allow_html=True,
            )

            if not upcoming_followups:
                st.markdown(
                    """
<div class="crm-empty">
    <strong>Sin actividades pendientes</strong>
    <span>No existen seguimientos comerciales pendientes registrados.</span>
</div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                activity_rows = []

                for item in upcoming_followups:
                    next_date = pd.to_datetime(
                        item.get("next_followup_date"),
                        errors="coerce",
                    )

                    next_label = (
                        next_date.strftime("%d-%m")
                        if not pd.isna(next_date)
                        else "-"
                    )

                    activity_rows.append(
                        {
                            "Fecha": next_label,
                            "Cliente": _safe_text(
                                item.get("client_name")
                            ),
                            "Tipo": _safe_text(
                                item.get("followup_type")
                            ),
                            "Acción": _safe_text(
                                item.get("subject")
                                or item.get("notes")
                            ),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(activity_rows),
                    hide_index=True,
                    use_container_width=True,
                    height=285,
                )

    # Segunda fila: clientes recientes / vendedor / oportunidades
    left2, middle2, right2 = st.columns([1.48, 1.0, .92], gap="medium")

    with left2:
        with st.container(border=True):
            st.markdown(
                """
<div class="crm-section-kicker">CARTERA</div>
<div class="crm-section-title">Clientes recientes</div>
<div class="crm-section-sub">Clientes ordenados por última compra.</div>
                """,
                unsafe_allow_html=True,
            )

            recent = clients.copy()
            recent["_fecha"] = pd.to_datetime(recent["Última compra"], errors="coerce")
            recent = recent.sort_values("_fecha", ascending=False).head(8)

            display = recent[
                ["Cliente", "RUT", "Vendedor", "Última compra", "Ventas 12 meses", "Pedidos"]
            ].copy()
            display["Última compra"] = pd.to_datetime(
                display["Última compra"], errors="coerce"
            ).dt.strftime("%d-%m-%Y")

            st.dataframe(
                display,
                hide_index=True,
                use_container_width=True,
                height=315,
                column_config={
                    "Ventas 12 meses": st.column_config.NumberColumn(
                        "Ventas 12 meses",
                        format="$ %.0f",
                    ),
                    "Pedidos": st.column_config.NumberColumn(
                        "Pedidos",
                        format="%d",
                    ),
                },
            )

    with middle2:
        with st.container(border=True):
            st.markdown(
                """
<div class="crm-section-kicker">VENDEDORES</div>
<div class="crm-section-title">Distribución por vendedor</div>
<div class="crm-section-sub">Ventas 12 meses de la cartera asociada.</div>
                """,
                unsafe_allow_html=True,
            )

            sellers = (
                clients.groupby("Vendedor", as_index=False)["Ventas 12 meses"]
                .sum()
                .sort_values("Ventas 12 meses", ascending=False)
                .head(10)
            )
            sellers = sellers[
                sellers["Vendedor"].fillna("").astype(str).str.strip().ne("")
                & sellers["Vendedor"].astype(str).ne("-")
            ]

            if sellers.empty:
                st.info("No se encontró vendedor asociado.")
            else:
                st.bar_chart(
                    sellers.set_index("Vendedor")["Ventas 12 meses"],
                    use_container_width=True,
                    height=285,
                )

    with right2:
        with st.container(border=True):
            st.markdown(
                """
<div class="crm-section-kicker">OPORTUNIDADES</div>
<div class="crm-section-title">Oportunidades abiertas</div>
<div class="crm-section-sub">Negocios y cotizaciones activas.</div>
                """,
                unsafe_allow_html=True,
            )
            if not open_opportunities:
                st.markdown(
                    """
<div class="crm-empty">
    <strong>Sin oportunidades abiertas</strong>
    <span>No existen negocios abiertos registrados actualmente.</span>
</div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                opp_rows = []

                for item in open_opportunities:
                    opp_rows.append(
                        {
                            "Cliente": _safe_text(
                                item.get("client_name")
                            ),
                            "Etapa": _safe_text(
                                item.get("stage")
                            ),
                            "Monto": float(
                                item.get("estimated_amount")
                                or 0
                            ),
                        }
                    )

                st.dataframe(
                    pd.DataFrame(opp_rows),
                    hide_index=True,
                    use_container_width=True,
                    height=285,
                    column_config={
                        "Monto": st.column_config.NumberColumn(
                            "Monto",
                            format="$ %.0f",
                        )
                    },
                )


# ============================================================
# CLIENTES
# ============================================================

def _render_clients(
    clients: pd.DataFrame,
) -> None:
    if clients.empty:
        st.info(
            "No fue posible construir la cartera de clientes "
            "desde ERP Ventas."
        )
        return

    # --------------------------------------------------------
    # Filtros
    # --------------------------------------------------------

    f1, f2 = st.columns(
        [2, 1],
        gap="small",
    )

    with f1:
        search = st.text_input(
            "Buscar cliente",
            placeholder="Nombre, RUT o vendedor...",
            key="crm_client_search",
        )

    with f2:
        sellers = sorted(
            [
                value
                for value in clients["Vendedor"]
                .dropna()
                .astype(str)
                .unique()
                if value
                and value != "-"
            ]
        )

        seller = st.selectbox(
            "Vendedor",
            ["Todos"] + sellers,
            key="crm_seller_filter",
        )

    filtered = clients.copy()

    if search:
        query = (
            str(search)
            .strip()
            .lower()
        )

        mask = pd.Series(
            False,
            index=filtered.index,
        )

        for column in (
            "Cliente",
            "RUT",
            "Vendedor",
        ):
            mask = (
                mask
                | filtered[column]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.contains(
                    query,
                    regex=False,
                )
            )

        filtered = filtered[
            mask
        ]

    if seller != "Todos":
        filtered = filtered[
            filtered["Vendedor"]
            .astype(str)
            == seller
        ]

    if filtered.empty:
        st.info(
            "No existen clientes que coincidan con los filtros."
        )
        return

    # --------------------------------------------------------
    # Tabla
    # --------------------------------------------------------

    display = filtered[
        [
            "Cliente",
            "RUT",
            "Vendedor",
            "Última compra",
            "Ventas 12 meses",
            "Ventas acumuladas",
            "Pedidos",
        ]
    ].copy()

    display["Última compra"] = pd.to_datetime(
        display["Última compra"],
        errors="coerce",
    ).dt.strftime(
        "%d-%m-%Y"
    )

    table_event = st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=min(
            500,
            38 + len(display) * 35,
        ),
        key="crm_clients_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Cliente": st.column_config.TextColumn(
                "Cliente",
                width="large",
            ),

            "RUT": st.column_config.TextColumn(
                "RUT",
                width="medium",
            ),

            "Vendedor": st.column_config.TextColumn(
                "Vendedor",
                width="medium",
            ),

            "Última compra": st.column_config.TextColumn(
                "Última compra",
                width="medium",
            ),

            "Ventas 12 meses": st.column_config.NumberColumn(
                "Ventas 12 meses",
                format="$ %.0f",
            ),

            "Ventas acumuladas": st.column_config.NumberColumn(
                "Venta acumulada",
                format="$ %.0f",
            ),

            "Pedidos": st.column_config.NumberColumn(
                "Pedidos",
                format="%d",
            ),
        },
    )

    # --------------------------------------------------------
    # Cliente seleccionado
    # --------------------------------------------------------

    selected_position = None

    try:
        selected_rows = list(
            table_event.selection.rows
        )

        if selected_rows:
            selected_position = int(
                selected_rows[0]
            )

    except Exception:
        selected_position = None

    if selected_position is None:
        selected_position = 0

    if (
        selected_position < 0
        or selected_position >= len(filtered)
    ):
        return

    client = filtered.iloc[
        selected_position
    ]

    st.divider()

    with st.container(
        border=True
    ):
        st.markdown(
            f"""
            <div class="crm-section-kicker">
                CLIENTE SELECCIONADO
            </div>

            <div class="crm-client-title">
                {_safe_text(client.get("Cliente"))}
            </div>

            <div class="crm-client-sub">
                {_safe_text(client.get("RUT"))}
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2, c3, c4 = st.columns(
            4,
            gap="small",
        )

        with c1:
            st.metric(
                "Ventas 12 meses",
                _money(
                    client.get(
                        "Ventas 12 meses"
                    )
                ),
            )

        with c2:
            st.metric(
                "Ventas acumuladas",
                _money(
                    client.get(
                        "Ventas acumuladas"
                    )
                ),
            )

        with c3:
            st.metric(
                "Pedidos",
                int(
                    _number(
                        client.get(
                            "Pedidos"
                        )
                    )
                ),
            )

        with c4:
            date_value = pd.to_datetime(
                client.get(
                    "Última compra"
                ),
                errors="coerce",
            )

            last_purchase = (
                date_value.strftime(
                    "%d-%m-%Y"
                )
                if not pd.isna(date_value)
                else "-"
            )

            st.metric(
                "Última compra",
                last_purchase,
            )

        st.caption(
            f"Vendedor: {_safe_text(client.get('Vendedor'))}"
        )


# ============================================================
# OPORTUNIDADES
# ============================================================

def _render_opportunities(
    clients: pd.DataFrame,
) -> None:
    st.markdown(
        """
<div class="crm-section-kicker">OPORTUNIDADES</div>
<div class="crm-section-title">Gestión comercial</div>
<div class="crm-section-sub">Crea, administra y actualiza negocios comerciales guardados en PostgreSQL.</div>
        """,
        unsafe_allow_html=True,
    )

    try:
        rows = list_opportunities(limit=1000)
    except Exception as exc:
        st.error(f"No fue posible cargar las oportunidades: {exc}")
        return

    # --------------------------------------------------------
    # KPIs
    # --------------------------------------------------------
    try:
        summary = get_crm_summary()
    except Exception:
        summary = {}

    k1, k2, k3, k4 = st.columns(4, gap="small")

    with k1:
        st.metric(
            "Oportunidades abiertas",
            int(summary.get("open_opportunities") or 0),
        )

    with k2:
        st.metric(
            "Monto abierto",
            _money(summary.get("open_amount") or 0),
        )

    with k3:
        st.metric(
            "Monto ponderado",
            _money(summary.get("weighted_amount") or 0),
        )

    with k4:
        st.metric(
            "Ganadas",
            int(summary.get("won_opportunities") or 0),
        )

    # --------------------------------------------------------
    # CREAR OPORTUNIDAD
    # --------------------------------------------------------
    with st.expander(
        "Nueva oportunidad",
        expanded=not bool(rows),
    ):
        if clients.empty:
            st.warning(
                "No hay clientes ERP disponibles para crear oportunidades."
            )
        else:
            client_records = clients[
                ["Cliente", "RUT", "Vendedor"]
            ].copy()

            client_records["Cliente"] = (
                client_records["Cliente"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            client_records["RUT"] = (
                client_records["RUT"]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            client_records = client_records[
                client_records["Cliente"].ne("")
            ].reset_index(drop=True)

            labels: list[str] = []
            client_map: dict[str, dict[str, Any]] = {}

            for _, row in client_records.iterrows():
                client_name = _safe_text(
                    row.get("Cliente"),
                    "",
                )
                client_rut = _safe_text(
                    row.get("RUT"),
                    "",
                )

                label = (
                    f"{client_name} · {client_rut}"
                    if client_rut
                    else client_name
                )

                if label in client_map:
                    continue

                labels.append(label)
                client_map[label] = {
                    "Cliente": client_name,
                    "RUT": client_rut,
                    "Vendedor": _safe_text(
                        row.get("Vendedor"),
                        "",
                    ),
                }

            with st.form(
                "crm_new_opportunity_form",
                clear_on_submit=True,
            ):
                selected_client_label = st.selectbox(
                    "Cliente",
                    labels,
                    key="crm_new_opportunity_client",
                )

                selected_client = client_map.get(
                    selected_client_label,
                    {},
                )

                f1, f2 = st.columns(
                    [1.35, 1],
                    gap="small",
                )

                with f1:
                    title = st.text_input(
                        "Nombre de oportunidad",
                        placeholder="Ej: Renovación uniformes temporada 2027",
                    )

                with f2:
                    seller = st.text_input(
                        "Vendedor",
                        value=selected_client.get(
                            "Vendedor",
                            "",
                        ),
                    )

                f3, f4, f5 = st.columns(
                    [1, 1, 1],
                    gap="small",
                )

                with f3:
                    estimated_amount = st.number_input(
                        "Monto estimado",
                        min_value=0.0,
                        step=10000.0,
                        format="%.0f",
                    )

                with f4:
                    stage = st.selectbox(
                        "Etapa",
                        CRM_STAGES,
                        index=0,
                    )

                with f5:
                    probability = st.number_input(
                        "Probabilidad (%)",
                        min_value=0,
                        max_value=100,
                        value=CRM_STAGE_PROBABILITY.get(
                            stage,
                            10,
                        ),
                        step=5,
                    )

                f6, f7 = st.columns(
                    2,
                    gap="small",
                )

                with f6:
                    expected_close_date = st.date_input(
                        "Fecha estimada de cierre",
                    )

                with f7:
                    next_action_date = st.date_input(
                        "Fecha próxima acción",
                    )

                next_action = st.text_input(
                    "Próxima acción",
                    placeholder="Ej: Enviar cotización actualizada",
                )

                description = st.text_area(
                    "Observaciones",
                    placeholder="Antecedentes, requerimientos y notas comerciales...",
                    height=100,
                )

                submitted = st.form_submit_button(
                    "Guardar oportunidad",
                    type="primary",
                    use_container_width=True,
                )

                if submitted:
                    if not title.strip():
                        st.error(
                            "Debes ingresar un nombre para la oportunidad."
                        )
                    else:
                        try:
                            create_opportunity(
                                client_name=selected_client.get(
                                    "Cliente",
                                    "",
                                ),
                                client_rut=selected_client.get(
                                    "RUT",
                                    "",
                                ),
                                seller=seller,
                                title=title,
                                description=description,
                                estimated_amount=estimated_amount,
                                stage=stage,
                                probability=int(probability),
                                expected_close_date=expected_close_date,
                                next_action_date=next_action_date,
                                next_action=next_action,
                                status="Abierta",
                            )

                            st.success(
                                "Oportunidad guardada correctamente."
                            )
                            st.rerun()

                        except Exception as exc:
                            st.error(
                                f"No fue posible guardar la oportunidad: {exc}"
                            )

    st.markdown("")

    # --------------------------------------------------------
    # LISTADO
    # --------------------------------------------------------
    if not rows:
        st.info(
            "Todavía no existen oportunidades registradas."
        )
        return

    display = _opportunity_display_frame(rows)

    with st.container(border=True):
        st.markdown(
            """
<div class="crm-section-kicker">CARTERA COMERCIAL</div>
<div class="crm-section-title">Oportunidades registradas</div>
<div class="crm-section-sub">Negocios almacenados de forma persistente en PostgreSQL.</div>
            """,
            unsafe_allow_html=True,
        )

        filter1, filter2, filter3 = st.columns(
            [1.3, 1, 1],
            gap="small",
        )

        with filter1:
            search = st.text_input(
                "Buscar",
                placeholder="Cliente, RUT u oportunidad...",
                key="crm_opp_search",
            )

        with filter2:
            stage_filter = st.selectbox(
                "Etapa",
                ["Todas"] + list(CRM_STAGES),
                key="crm_opp_stage_filter",
            )

        with filter3:
            status_filter = st.selectbox(
                "Estado",
                ["Todos"] + list(CRM_STATUSES),
                key="crm_opp_status_filter",
            )

        filtered = display.copy()

        if search:
            query = search.strip().lower()
            mask = pd.Series(
                False,
                index=filtered.index,
            )

            for column in (
                "Cliente",
                "RUT",
                "Oportunidad",
                "Vendedor",
            ):
                mask = (
                    mask
                    | filtered[column]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    .str.contains(
                        query,
                        regex=False,
                    )
                )

            filtered = filtered[mask]

        if stage_filter != "Todas":
            filtered = filtered[
                filtered["Etapa"] == stage_filter
            ]

        if status_filter != "Todos":
            filtered = filtered[
                filtered["Estado"] == status_filter
            ]

        st.dataframe(
            filtered,
            hide_index=True,
            use_container_width=True,
            height=min(
                500,
                70 + max(len(filtered), 1) * 35,
            ),
            column_config={
                "Monto": st.column_config.NumberColumn(
                    "Monto",
                    format="$ %.0f",
                ),
                "Probabilidad": st.column_config.NumberColumn(
                    "Probabilidad",
                    format="%d %%",
                ),
            },
        )

    # --------------------------------------------------------
    # EDITAR
    # --------------------------------------------------------
    opportunity_map: dict[str, dict[str, Any]] = {}

    for row in rows:
        label = (
            f"#{row.get('id')} · "
            f"{_safe_text(row.get('client_name'))} · "
            f"{_safe_text(row.get('title'))}"
        )
        opportunity_map[label] = row

    with st.expander(
        "Editar oportunidad",
        expanded=False,
    ):
        selected_label = st.selectbox(
            "Seleccionar oportunidad",
            list(opportunity_map.keys()),
            key="crm_edit_opportunity_select",
        )

        selected = opportunity_map[selected_label]

        stage_value = _safe_text(
            selected.get("stage"),
            "Prospección",
        )
        status_value = _safe_text(
            selected.get("status"),
            "Abierta",
        )

        stage_index = (
            CRM_STAGES.index(stage_value)
            if stage_value in CRM_STAGES
            else 0
        )

        status_index = (
            CRM_STATUSES.index(status_value)
            if status_value in CRM_STATUSES
            else 0
        )

        expected_date = pd.to_datetime(
            selected.get("expected_close_date"),
            errors="coerce",
        )
        next_date = pd.to_datetime(
            selected.get("next_action_date"),
            errors="coerce",
        )

        with st.form(
            f"crm_edit_opportunity_form_{selected.get('id')}",
        ):
            e1, e2 = st.columns(
                [1.4, 1],
                gap="small",
            )

            with e1:
                edit_title = st.text_input(
                    "Oportunidad",
                    value=_safe_text(
                        selected.get("title"),
                        "",
                    ),
                )

            with e2:
                edit_seller = st.text_input(
                    "Vendedor",
                    value=_safe_text(
                        selected.get("seller"),
                        "",
                    ),
                )

            e3, e4, e5, e6 = st.columns(
                4,
                gap="small",
            )

            with e3:
                edit_amount = st.number_input(
                    "Monto estimado",
                    min_value=0.0,
                    value=float(
                        selected.get("estimated_amount")
                        or 0
                    ),
                    step=10000.0,
                    format="%.0f",
                )

            with e4:
                edit_stage = st.selectbox(
                    "Etapa",
                    CRM_STAGES,
                    index=stage_index,
                )

            with e5:
                edit_probability = st.number_input(
                    "Probabilidad (%)",
                    min_value=0,
                    max_value=100,
                    value=int(
                        selected.get("probability")
                        or 0
                    ),
                    step=5,
                )

            with e6:
                edit_status = st.selectbox(
                    "Estado",
                    CRM_STATUSES,
                    index=status_index,
                )

            e7, e8 = st.columns(
                2,
                gap="small",
            )

            with e7:
                edit_expected_date = st.date_input(
                    "Fecha estimada de cierre",
                    value=(
                        expected_date.date()
                        if not pd.isna(expected_date)
                        else datetime.now().date()
                    ),
                )

            with e8:
                edit_next_date = st.date_input(
                    "Fecha próxima acción",
                    value=(
                        next_date.date()
                        if not pd.isna(next_date)
                        else datetime.now().date()
                    ),
                )

            edit_next_action = st.text_input(
                "Próxima acción",
                value=_safe_text(
                    selected.get("next_action"),
                    "",
                ),
            )

            edit_description = st.text_area(
                "Observaciones",
                value=_safe_text(
                    selected.get("description"),
                    "",
                ),
                height=100,
            )

            update_submitted = st.form_submit_button(
                "Guardar cambios",
                type="primary",
                use_container_width=True,
            )

            if update_submitted:
                if not edit_title.strip():
                    st.error(
                        "El nombre de la oportunidad no puede quedar vacío."
                    )
                else:
                    try:
                        update_opportunity(
                            int(selected["id"]),
                            title=edit_title,
                            seller=edit_seller,
                            description=edit_description,
                            estimated_amount=edit_amount,
                            stage=edit_stage,
                            probability=int(edit_probability),
                            expected_close_date=edit_expected_date,
                            next_action_date=edit_next_date,
                            next_action=edit_next_action,
                            status=edit_status,
                        )

                        st.success(
                            "Oportunidad actualizada correctamente."
                        )
                        st.rerun()

                    except Exception as exc:
                        st.error(
                            f"No fue posible actualizar la oportunidad: {exc}"
                        )


# ============================================================
# SEGUIMIENTOS
# ============================================================

def _render_followups(
    clients: pd.DataFrame,
) -> None:
    st.markdown(
        """
<div class="crm-section-kicker">SEGUIMIENTOS</div>
<div class="crm-section-title">Próximas acciones</div>
<div class="crm-section-sub">Llamadas, correos, reuniones, WhatsApp, tareas y notas comerciales persistentes.</div>
        """,
        unsafe_allow_html=True,
    )

    try:
        followups = list_followups(
            limit=1000,
        )
        opportunities = list_opportunities(
            limit=1000,
        )
        summary = get_crm_summary()
    except Exception as exc:
        st.error(
            f"No fue posible cargar los seguimientos: {exc}"
        )
        return

    # --------------------------------------------------------
    # KPIs
    # --------------------------------------------------------
    pending_count = int(
        summary.get("pending_followups") or 0
    )
    overdue_count = int(
        summary.get("overdue_followups") or 0
    )
    today_count = int(
        summary.get("today_followups") or 0
    )

    followup_kpis_html = (
        '<div class="crm-kpis" style="grid-template-columns:repeat(3,minmax(0,1fr));">'
        '<div class="crm-kpi yellow">'
        '<div class="crm-kpi-label">Pendientes</div>'
        f'<div class="crm-kpi-value">{pending_count}</div>'
        '<div class="crm-kpi-help">Seguimientos por realizar</div>'
        '</div>'
        '<div class="crm-kpi orange">'
        '<div class="crm-kpi-label">Vencidos</div>'
        f'<div class="crm-kpi-value">{overdue_count}</div>'
        '<div class="crm-kpi-help orange">Requieren atención</div>'
        '</div>'
        '<div class="crm-kpi green">'
        '<div class="crm-kpi-label">Para hoy</div>'
        f'<div class="crm-kpi-value">{today_count}</div>'
        '<div class="crm-kpi-help green">Agenda del día</div>'
        '</div>'
        '</div>'
    )

    st.markdown(
        followup_kpis_html,
        unsafe_allow_html=True,
    )

    # --------------------------------------------------------
    # NUEVO SEGUIMIENTO
    # --------------------------------------------------------
    with st.expander(
        "Nuevo seguimiento",
        expanded=not bool(followups),
    ):
        mode = st.radio(
            "Asociar seguimiento a",
            options=[
                "Oportunidad",
                "Cliente",
            ],
            horizontal=True,
            key="crm_followup_mode",
        )

        opportunity_map: dict[str, dict[str, Any]] = {}
        client_map: dict[str, dict[str, Any]] = {}

        for opportunity in opportunities:
            label = _followup_opportunity_label(
                opportunity
            )
            opportunity_map[label] = opportunity

        if not clients.empty:
            for _, row in clients.iterrows():
                client_name = _safe_text(
                    row.get("Cliente"),
                    "",
                )
                client_rut = _safe_text(
                    row.get("RUT"),
                    "",
                )

                if not client_name:
                    continue

                label = (
                    f"{client_name} · {client_rut}"
                    if client_rut
                    else client_name
                )

                if label in client_map:
                    continue

                client_map[label] = {
                    "Cliente": client_name,
                    "RUT": client_rut,
                    "Vendedor": _safe_text(
                        row.get("Vendedor"),
                        "",
                    ),
                }

        selected_opportunity = None
        selected_client = None

        if mode == "Oportunidad":
            if not opportunity_map:
                st.info(
                    "No existen oportunidades disponibles. "
                    "Puedes registrar el seguimiento directamente por cliente."
                )
            else:
                opportunity_label = st.selectbox(
                    "Oportunidad",
                    list(opportunity_map.keys()),
                    key="crm_followup_opportunity",
                )
                selected_opportunity = opportunity_map.get(
                    opportunity_label
                )

        if mode == "Cliente" or (
            mode == "Oportunidad"
            and not opportunity_map
        ):
            if not client_map:
                st.warning(
                    "No existen clientes ERP disponibles."
                )
            else:
                client_label = st.selectbox(
                    "Cliente",
                    list(client_map.keys()),
                    key="crm_followup_client",
                )
                selected_client = client_map.get(
                    client_label
                )

        if selected_opportunity:
            default_client_name = _safe_text(
                selected_opportunity.get("client_name"),
                "",
            )
            default_client_rut = _safe_text(
                selected_opportunity.get("client_rut"),
                "",
            )
            default_seller = _safe_text(
                selected_opportunity.get("seller"),
                "",
            )
            default_opportunity_id = int(
                selected_opportunity["id"]
            )
        elif selected_client:
            default_client_name = selected_client.get(
                "Cliente",
                "",
            )
            default_client_rut = selected_client.get(
                "RUT",
                "",
            )
            default_seller = selected_client.get(
                "Vendedor",
                "",
            )
            default_opportunity_id = None
        else:
            default_client_name = ""
            default_client_rut = ""
            default_seller = ""
            default_opportunity_id = None

        if default_client_name:
            with st.form(
                "crm_new_followup_form",
                clear_on_submit=True,
            ):
                f1, f2, f3 = st.columns(
                    [1, 1.15, 1],
                    gap="small",
                )

                with f1:
                    followup_type = st.selectbox(
                        "Tipo",
                        CRM_FOLLOWUP_TYPES,
                    )

                with f2:
                    subject = st.text_input(
                        "Asunto",
                        placeholder="Ej: Confirmar recepción de cotización",
                    )

                with f3:
                    seller = st.text_input(
                        "Responsable",
                        value=default_seller,
                    )

                st.caption(
                    f"Cliente: {default_client_name} · "
                    f"RUT: {default_client_rut or '-'}"
                )

                notes = st.text_area(
                    "Detalle",
                    placeholder="Resumen de llamada, correo, reunión o tarea...",
                    height=110,
                )

                next_followup_date = st.date_input(
                    "Próximo seguimiento",
                    key="crm_new_followup_date",
                )

                submitted = st.form_submit_button(
                    "Guardar seguimiento",
                    type="primary",
                    use_container_width=True,
                )

                if submitted:
                    if not subject.strip() and not notes.strip():
                        st.error(
                            "Ingresa un asunto o detalle para el seguimiento."
                        )
                    else:
                        try:
                            create_followup(
                                opportunity_id=default_opportunity_id,
                                client_rut=default_client_rut,
                                client_name=default_client_name,
                                seller=seller,
                                followup_type=followup_type,
                                subject=subject,
                                notes=notes,
                                next_followup_date=next_followup_date,
                                completed=False,
                            )

                            st.success(
                                "Seguimiento guardado correctamente."
                            )
                            st.rerun()

                        except Exception as exc:
                            st.error(
                                f"No fue posible guardar el seguimiento: {exc}"
                            )

    st.markdown("")

    # --------------------------------------------------------
    # LISTADO
    # --------------------------------------------------------
    if not followups:
        st.info(
            "Todavía no existen seguimientos registrados."
        )
        return

    display = _followup_display_frame(
        followups
    )

    with st.container(border=True):
        st.markdown(
            """
<div class="crm-section-kicker">AGENDA COMERCIAL</div>
<div class="crm-section-title">Seguimientos registrados</div>
<div class="crm-section-sub">Historial y próximas acciones guardadas en PostgreSQL.</div>
            """,
            unsafe_allow_html=True,
        )

        f1, f2, f3 = st.columns(
            [1.4, 1, 1],
            gap="small",
        )

        with f1:
            search = st.text_input(
                "Buscar",
                placeholder="Cliente, RUT, asunto o responsable...",
                key="crm_followup_search",
            )

        with f2:
            type_filter = st.selectbox(
                "Tipo",
                ["Todos"] + list(CRM_FOLLOWUP_TYPES),
                key="crm_followup_type_filter",
            )

        with f3:
            state_filter = st.selectbox(
                "Estado",
                [
                    "Todos",
                    "Pendiente",
                    "Completado",
                ],
                key="crm_followup_state_filter",
            )

        filtered = display.copy()

        if search:
            query = search.strip().lower()

            mask = pd.Series(
                False,
                index=filtered.index,
            )

            for column in (
                "Cliente",
                "RUT",
                "Asunto",
                "Responsable",
                "Detalle",
            ):
                mask = (
                    mask
                    | filtered[column]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    .str.contains(
                        query,
                        regex=False,
                    )
                )

            filtered = filtered[
                mask
            ]

        if type_filter != "Todos":
            filtered = filtered[
                filtered["Tipo"] == type_filter
            ]

        if state_filter != "Todos":
            filtered = filtered[
                filtered["Estado"] == state_filter
            ]

        st.dataframe(
            filtered,
            hide_index=True,
            use_container_width=True,
            height=min(
                520,
                70 + max(len(filtered), 1) * 35,
            ),
        )

    # --------------------------------------------------------
    # CAMBIAR ESTADO / EDITAR
    # --------------------------------------------------------
    followup_map: dict[str, dict[str, Any]] = {}

    for row in followups:
        label = (
            f"#{row.get('id')} · "
            f"{_safe_text(row.get('client_name'))} · "
            f"{_safe_text(row.get('subject') or row.get('followup_type'))}"
        )
        followup_map[label] = row

    with st.expander(
        "Editar seguimiento",
        expanded=False,
    ):
        selected_label = st.selectbox(
            "Seleccionar seguimiento",
            list(followup_map.keys()),
            key="crm_edit_followup_select",
        )

        selected = followup_map[
            selected_label
        ]

        selected_type = _safe_text(
            selected.get("followup_type"),
            "Nota",
        )

        type_index = (
            CRM_FOLLOWUP_TYPES.index(selected_type)
            if selected_type in CRM_FOLLOWUP_TYPES
            else len(CRM_FOLLOWUP_TYPES) - 1
        )

        next_date = pd.to_datetime(
            selected.get("next_followup_date"),
            errors="coerce",
        )

        with st.form(
            f"crm_edit_followup_{selected.get('id')}"
        ):
            e1, e2, e3 = st.columns(
                [1, 1.2, 1],
                gap="small",
            )

            with e1:
                edit_type = st.selectbox(
                    "Tipo",
                    CRM_FOLLOWUP_TYPES,
                    index=type_index,
                )

            with e2:
                edit_subject = st.text_input(
                    "Asunto",
                    value=_safe_text(
                        selected.get("subject"),
                        "",
                    ),
                )

            with e3:
                edit_seller = st.text_input(
                    "Responsable",
                    value=_safe_text(
                        selected.get("seller"),
                        "",
                    ),
                )

            edit_notes = st.text_area(
                "Detalle",
                value=_safe_text(
                    selected.get("notes"),
                    "",
                ),
                height=110,
            )

            e4, e5 = st.columns(
                2,
                gap="small",
            )

            with e4:
                edit_next_date = st.date_input(
                    "Próximo seguimiento",
                    value=(
                        next_date.date()
                        if not pd.isna(next_date)
                        else datetime.now().date()
                    ),
                )

            with e5:
                edit_completed = st.checkbox(
                    "Marcar como completado",
                    value=bool(
                        selected.get("completed")
                    ),
                )

            update_submitted = st.form_submit_button(
                "Guardar cambios",
                type="primary",
                use_container_width=True,
            )

            if update_submitted:
                try:
                    update_followup(
                        int(selected["id"]),
                        followup_type=edit_type,
                        subject=edit_subject,
                        seller=edit_seller,
                        notes=edit_notes,
                        next_followup_date=edit_next_date,
                        completed=edit_completed,
                    )

                    st.success(
                        "Seguimiento actualizado correctamente."
                    )
                    st.rerun()

                except Exception as exc:
                    st.error(
                        f"No fue posible actualizar el seguimiento: {exc}"
                    )


# ============================================================
# PIPELINE
# ============================================================

def _render_pipeline() -> None:
    st.markdown(
        """
<div class="crm-section-kicker">TUBERÍA</div>
<div class="crm-section-title">Tablero comercial</div>
<div class="crm-section-sub">Vista inspirada en Monday para gestionar oportunidades por etapa.</div>
        """,
        unsafe_allow_html=True,
    )

    try:
        open_rows = list_opportunities(
            status="Abierta",
            limit=1000,
        )
        summary = get_crm_summary()
    except Exception as exc:
        st.error(
            f"No fue posible cargar la tubería comercial: {exc}"
        )
        return

    open_amount = float(
        summary.get("open_amount") or 0
    )
    weighted_amount = float(
        summary.get("weighted_amount") or 0
    )
    open_count = int(
        summary.get("open_opportunities") or 0
    )
    won_count = int(
        summary.get("won_opportunities") or 0
    )

    board_kpis = (
        '<div class="crm-kpis">'
        '<div class="crm-kpi yellow">'
        '<div class="crm-kpi-label">Embudo total</div>'
        f'<div class="crm-kpi-value">{_money(open_amount)}</div>'
        '<div class="crm-kpi-help">Valor de oportunidades abiertas</div>'
        '</div>'
        '<div class="crm-kpi purple">'
        '<div class="crm-kpi-label">Embudo ponderado</div>'
        f'<div class="crm-kpi-value">{_money(weighted_amount)}</div>'
        '<div class="crm-kpi-help">Monto ajustado por probabilidad</div>'
        '</div>'
        '<div class="crm-kpi green">'
        '<div class="crm-kpi-label">Oportunidades abiertas</div>'
        f'<div class="crm-kpi-value">{open_count}</div>'
        '<div class="crm-kpi-help green">Negocios activos</div>'
        '</div>'
        '<div class="crm-kpi orange">'
        '<div class="crm-kpi-label">Ganadas</div>'
        f'<div class="crm-kpi-value">{won_count}</div>'
        '<div class="crm-kpi-help">Cierres exitosos</div>'
        '</div>'
        '</div>'
    )

    st.markdown(
        board_kpis,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
<div class="crm-board-head">
    <div>
        <div class="crm-board-title">Board de oportunidades</div>
        <div class="crm-board-meta">Mueve negocios entre etapas con los controles rápidos de cada tarjeta.</div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    if not open_rows:
        st.info(
            "No existen oportunidades abiertas en la tubería."
        )
        return

    stage_columns = st.columns(
        len(CRM_STAGES),
        gap="small",
    )

    for stage_index, (column, stage) in enumerate(
        zip(stage_columns, CRM_STAGES)
    ):
        stage_rows = [
            row
            for row in open_rows
            if _safe_text(
                row.get("stage"),
                "",
            ) == stage
        ]

        stage_total = sum(
            float(
                row.get("estimated_amount")
                or 0
            )
            for row in stage_rows
        )

        with column:
            st.markdown(
                (
                    '<div class="crm-stage-head">'
                    f'<div class="crm-stage-name">{stage}</div>'
                    f'<div class="crm-stage-count">{len(stage_rows)}</div>'
                    f'<div class="crm-stage-total">{_money(stage_total)}</div>'
                    '</div>'
                ),
                unsafe_allow_html=True,
            )

            if not stage_rows:
                st.markdown(
                    '<div class="crm-stage-empty">Sin oportunidades</div>',
                    unsafe_allow_html=True,
                )
                continue

            for item in stage_rows:
                opportunity_id = int(
                    item.get("id")
                )

                amount = float(
                    item.get("estimated_amount")
                    or 0
                )
                probability = int(
                    item.get("probability")
                    or 0
                )

                next_date = pd.to_datetime(
                    item.get("next_action_date"),
                    errors="coerce",
                )
                next_date_label = (
                    next_date.strftime("%d-%m-%Y")
                    if not pd.isna(next_date)
                    else "-"
                )

                close_date = pd.to_datetime(
                    item.get("expected_close_date"),
                    errors="coerce",
                )
                close_date_label = (
                    close_date.strftime("%d-%m-%Y")
                    if not pd.isna(close_date)
                    else "-"
                )

                client_name = _safe_text(
                    item.get("client_name")
                )
                title = _safe_text(
                    item.get("title")
                )
                seller = _safe_text(
                    item.get("seller")
                )
                next_action = _safe_text(
                    item.get("next_action"),
                    "Sin próxima acción",
                )

                st.markdown(
                    (
                        '<div class="crm-kanban-card">'
                        f'<div class="crm-kanban-id">#{opportunity_id} · {seller}</div>'
                        f'<div class="crm-kanban-client">{client_name}</div>'
                        f'<div class="crm-kanban-title">{title}</div>'
                        f'<div class="crm-kanban-money">{_money(amount)}</div>'
                        f'<div class="crm-kanban-chip">{probability}% probabilidad</div>'
                        '<div class="crm-kanban-label">Próxima acción</div>'
                        f'<div class="crm-kanban-action">{next_action}</div>'
                        f'<div class="crm-kanban-date">{next_date_label}</div>'
                        f'<div class="crm-kanban-date">Cierre: {close_date_label}</div>'
                        '</div>'
                    ),
                    unsafe_allow_html=True,
                )

                # ------------------------------------------------
                # Acciones rápidas tipo board
                # ------------------------------------------------
                left_col, right_col = st.columns(
                    2,
                    gap="small",
                )

                if stage_index > 0:
                    previous_stage = CRM_STAGES[
                        stage_index - 1
                    ]

                    with left_col:
                        if st.button(
                            "←",
                            key=f"crm_prev_{opportunity_id}",
                            help=f"Mover a {previous_stage}",
                            use_container_width=True,
                        ):
                            try:
                                update_opportunity(
                                    opportunity_id,
                                    stage=previous_stage,
                                    probability=CRM_STAGE_PROBABILITY.get(
                                        previous_stage,
                                        probability,
                                    ),
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(
                                    f"No fue posible mover la oportunidad: {exc}"
                                )
                else:
                    with left_col:
                        st.caption("")

                if stage_index < len(CRM_STAGES) - 1:
                    next_stage = CRM_STAGES[
                        stage_index + 1
                    ]

                    with right_col:
                        if st.button(
                            "→",
                            key=f"crm_next_{opportunity_id}",
                            help=f"Mover a {next_stage}",
                            use_container_width=True,
                        ):
                            try:
                                update_opportunity(
                                    opportunity_id,
                                    stage=next_stage,
                                    probability=CRM_STAGE_PROBABILITY.get(
                                        next_stage,
                                        probability,
                                    ),
                                )
                                st.rerun()
                            except Exception as exc:
                                st.error(
                                    f"No fue posible mover la oportunidad: {exc}"
                                )
                else:
                    with right_col:
                        st.caption("")

                action1, action2 = st.columns(
                    2,
                    gap="small",
                )

                with action1:
                    if st.button(
                        "✓ Ganada",
                        key=f"crm_win_{opportunity_id}",
                        use_container_width=True,
                    ):
                        try:
                            update_opportunity(
                                opportunity_id,
                                status="Ganada",
                                probability=100,
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(
                                f"No fue posible cerrar como ganada: {exc}"
                            )

                with action2:
                    if st.button(
                        "✕ Perdida",
                        key=f"crm_lost_{opportunity_id}",
                        use_container_width=True,
                    ):
                        try:
                            update_opportunity(
                                opportunity_id,
                                status="Perdida",
                                probability=0,
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(
                                f"No fue posible cerrar como perdida: {exc}"
                            )

                st.markdown("")

    st.markdown("")

    with st.expander(
        "Vista de tabla",
        expanded=False,
    ):
        display = _opportunity_display_frame(
            open_rows
        )

        st.dataframe(
            display[
                [
                    "ID",
                    "Cliente",
                    "RUT",
                    "Oportunidad",
                    "Monto",
                    "Etapa",
                    "Probabilidad",
                    "Vendedor",
                    "Cierre estimado",
                    "Próxima acción",
                    "Fecha próxima acción",
                ]
            ],
            hide_index=True,
            use_container_width=True,
            column_config={
                "Monto": st.column_config.NumberColumn(
                    "Monto",
                    format="$ %.0f",
                ),
                "Probabilidad": st.column_config.NumberColumn(
                    "Probabilidad",
                    format="%d %%",
                ),
            },
        )


# ============================================================
# INFORMACIÓN FUENTE
# ============================================================

def _render_source_info(
    sales_df: pd.DataFrame,
    detected_columns: dict,
) -> None:
    with st.expander(
        "Información de la fuente",
        expanded=False,
    ):
        st.markdown(
            "**Fuente actual:** ERP Ventas"
        )

        st.write(
            f"Registros disponibles: "
            f"{len(sales_df):,}".replace(",", ".")
        )

        st.markdown(
            "**Columnas detectadas para CRM:**"
        )

        source_rows = []

        for key, value in detected_columns.items():
            source_rows.append(
                {
                    "Dato CRM": key,
                    "Columna ERP": (
                        value
                        if value
                        else "No detectada"
                    ),
                }
            )

        st.dataframe(
            pd.DataFrame(
                source_rows
            ),
            hide_index=True,
            use_container_width=True,
        )



# ============================================================
# RENDER PRINCIPAL
# ============================================================

def render(
    ctx: dict | None = None,
) -> None:
    _apply_styles()

    ctx = ctx or {}

    sales_df = ctx.get(
        "sales_df"
    )

    if sales_df is None:
        sales_df = pd.DataFrame()

    header_html = (
        '<div class="crm-page-head">'
        '<div>'
        '<h1>CRM Comercial</h1>'
        '<p>Gestión de clientes, oportunidades, seguimiento y tubería comercial.</p>'
        '</div>'
        '<div class="crm-live-pill">'
        '<i></i>ERP + PostgreSQL conectados'
        '</div>'
        '</div>'
    )
    st.markdown(header_html, unsafe_allow_html=True)

    if sales_df.empty:
        st.warning(
            "No existen datos de ERP Ventas disponibles "
            "para construir el CRM."
        )
        return

    clients, detected_columns = (
        _prepare_clients(
            sales_df
        )
    )

    if clients.empty:
        st.error(
            "No fue posible identificar clientes en ERP Ventas. "
            "Revisa las columnas de nombre/RUT del archivo de ventas."
        )

        _render_source_info(
            sales_df,
            detected_columns,
        )

        return

    # --------------------------------------------------------
    # Navegación CRM
    # --------------------------------------------------------

    section = st.segmented_control(
        "Sección CRM",
        options=list(
            CRM_TABS
        ),
        default="Resumen",
        key="crm_section",
    )

    if not section:
        section = "Resumen"

    st.markdown("")

    # --------------------------------------------------------
    # Contenido
    # --------------------------------------------------------

    if section == "Resumen":
        _render_summary(
            clients
        )

    elif section == "Clientes":
        _render_clients(
            clients
        )

    elif section == "Oportunidades":
        _render_opportunities(
            clients
        )

    elif section == "Seguimientos":
        _render_followups(
            clients
        )

    elif section == "Pipeline":
        _render_pipeline()

    # --------------------------------------------------------
    # Información técnica
    # --------------------------------------------------------

    st.markdown("")

    _render_source_info(
        sales_df,
        detected_columns,
    )