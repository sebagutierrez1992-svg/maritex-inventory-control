from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st


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


# ============================================================
# ESTILOS
# ============================================================

def _apply_styles() -> None:
    st.markdown(
        """
<style>
.block-container{
    max-width:1680px;
    padding-top:.9rem;
    padding-bottom:2rem;
}
div[data-testid="stVerticalBlock"]{gap:.65rem}

.crm-page-head{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:20px;
    margin-bottom:6px;
}
.crm-page-head h1{
    margin:0;
    color:#F7F9FB;
    font-size:30px;
    line-height:1;
    letter-spacing:-.7px;
    font-weight:850;
}
.crm-page-head p{
    margin:7px 0 0;
    color:#9EACB8;
    font-size:12px;
}
.crm-live-pill{
    display:inline-flex;
    align-items:center;
    gap:8px;
    padding:9px 13px;
    border:1px solid #33434F;
    border-radius:10px;
    background:#121C25;
    color:#D8E0E6;
    font-size:10.5px;
    white-space:nowrap;
}
.crm-live-pill i{
    display:block;
    width:8px;height:8px;border-radius:999px;
    background:#24CC6A;
    box-shadow:0 0 0 4px rgba(36,204,106,.10);
}

.crm-kpis{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:11px;
    margin:6px 0 3px;
}
.crm-kpi{
    position:relative;
    overflow:hidden;
    min-height:118px;
    border:1px solid #33434F;
    border-radius:11px;
    padding:15px;
    background:linear-gradient(145deg,#18242E,#111A22);
}
.crm-kpi::after{
    content:"";
    position:absolute;
    left:14px;right:14px;bottom:8px;height:2px;
    border-radius:999px;
    opacity:.42;
}
.crm-kpi.yellow::after{background:linear-gradient(90deg,#FFC400,transparent)}
.crm-kpi.green::after{background:linear-gradient(90deg,#34C867,transparent)}
.crm-kpi.purple::after{background:linear-gradient(90deg,#8B5CF6,transparent)}
.crm-kpi.orange::after{background:linear-gradient(90deg,#F97316,transparent)}

.crm-kpi-top{display:flex;align-items:center;gap:11px}
.crm-kpi-icon{
    width:40px;height:40px;flex:0 0 40px;
    display:flex;align-items:center;justify-content:center;
    border-radius:999px;font-size:18px;font-weight:900;
}
.crm-kpi-icon.yellow{color:#FFC400;background:rgba(255,196,0,.11);border:1px solid rgba(255,196,0,.28)}
.crm-kpi-icon.green{color:#44D478;background:rgba(34,197,94,.11);border:1px solid rgba(34,197,94,.26)}
.crm-kpi-icon.purple{color:#9E7BFF;background:rgba(139,92,246,.12);border:1px solid rgba(139,92,246,.25)}
.crm-kpi-icon.orange{color:#FB7C2C;background:rgba(249,115,22,.12);border:1px solid rgba(249,115,22,.26)}
.crm-kpi-label{color:#BBC6CF;font-size:9.5px;text-transform:uppercase;font-weight:760}
.crm-kpi-value{color:#FFF;font-size:22px;font-weight:850;line-height:1;margin-top:6px;letter-spacing:-.35px}
.crm-kpi-help{color:#8D9AA5;font-size:8.9px;margin-top:8px;font-weight:650}
.crm-kpi-help.green{color:#49D17B}
.crm-kpi-help.orange{color:#F6A35E}

div[data-testid="stVerticalBlockBorderWrapper"]{
    border:1px solid #33434F !important;
    background:linear-gradient(145deg,#18242E,#111A22) !important;
    border-radius:11px !important;
    box-shadow:none !important;
}
div[data-testid="stDataFrame"]{
    border:1px solid #33434F;
    border-radius:10px;
    overflow:hidden;
    background:#111A22;
}

.crm-section-kicker{
    color:#FFC400;
    text-transform:uppercase;
    letter-spacing:.08em;
    font-size:8px;
    font-weight:850;
    margin-bottom:2px;
}
.crm-section-title{
    color:#F4F7F9;
    font-size:12px;
    font-weight:850;
    margin:0 0 2px;
}
.crm-section-sub{
    color:#8997A3;
    font-size:8.8px;
    margin-bottom:6px;
}
.crm-client-title{
    color:#F7F9FB;
    font-size:18px;
    font-weight:850;
    margin-bottom:2px;
}
.crm-client-sub{
    color:#8F9DA8;
    font-size:10px;
    margin-bottom:8px;
}

.crm-top-row{
    display:grid;
    grid-template-columns:28px minmax(0,1.6fr) 110px 92px 65px 90px;
    gap:8px;
    align-items:center;
    min-height:38px;
    border-bottom:1px solid #2D3C47;
    font-size:8.8px;
}
.crm-top-row.header{
    color:#83919D;
    font-size:7.7px;
    text-transform:uppercase;
    font-weight:720;
}
.crm-top-row:last-child{border-bottom:0}
.crm-rank{color:#73818D;font-weight:800}
.crm-client-name{
    color:#EDF2F5;font-weight:760;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.crm-client-rut{color:#9EABB6}
.crm-money{color:#FFC400;font-weight:820;text-align:right}
.crm-orders{color:#DCE3E8;text-align:right}
.crm-date{color:#B3BEC7;text-align:right}

.crm-activity-list{display:flex;flex-direction:column}
.crm-activity{
    display:grid;
    grid-template-columns:28px minmax(0,1fr) auto;
    gap:9px;align-items:center;
    padding:9px 0;border-bottom:1px solid #2E3D49;
}
.crm-activity:last-child{border-bottom:0}
.crm-activity-icon{
    width:28px;height:28px;border-radius:999px;
    display:flex;align-items:center;justify-content:center;
    font-size:11px;font-weight:900;
}
.crm-activity-icon.green{background:#123E26;color:#64DC8E}
.crm-activity-icon.blue{background:#17375E;color:#68A7FF}
.crm-activity-icon.purple{background:#2F2058;color:#A581FF}
.crm-activity strong{display:block;color:#EDF2F5;font-size:9.5px}
.crm-activity small{display:block;color:#84929E;font-size:7.9px;margin-top:2px}
.crm-activity-time{color:#AEB9C2;font-size:8px;text-align:right}

.crm-empty{
    min-height:180px;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;
    text-align:center;
    border:1px dashed #3A4955;
    border-radius:10px;
    color:#82909C;
    padding:20px;
}
.crm-empty strong{color:#EAF0F4;font-size:12px;margin-bottom:5px}
.crm-empty span{font-size:9px;max-width:360px}

.stButton>button{
    border-radius:8px !important;
    min-height:35px !important;
    font-size:9.5px !important;
    font-weight:750 !important;
}
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] div[data-baseweb="select"]>div{
    background:#141F28 !important;
    border-color:#3A4955 !important;
    color:#F4F7F9 !important;
}
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label{
    color:#A8B4BE !important;
    font-size:9px !important;
}
div[data-testid="stMetric"]{
    border:1px solid #33434F;
    border-radius:10px;
    background:#141F28;
    padding:10px 12px;
}
div[data-testid="stMetricLabel"]{
    color:#91A0AB !important;
    font-size:9px !important;
    font-weight:700 !important;
}
div[data-testid="stMetricValue"]{
    color:#F7F9FB !important;
    font-size:19px !important;
}
hr{border-color:#2B3A45 !important}

@media(max-width:1100px){
    .crm-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:700px){
    .crm-page-head{flex-direction:column}
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

            st.markdown(
                """
<div class="crm-empty">
    <strong>Sin actividades registradas</strong>
    <span>Cuando conectemos la base persistente del CRM, aquí aparecerán llamadas, correos, reuniones y tareas próximas.</span>
</div>
                """,
                unsafe_allow_html=True,
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
            st.markdown(
                """
<div class="crm-empty">
    <strong>Sin oportunidades registradas</strong>
    <span>Esta tarjeta quedará activa cuando agreguemos el almacenamiento persistente para oportunidades y pipeline.</span>
</div>
                """,
                unsafe_allow_html=True,
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

def _render_opportunities() -> None:
    with st.container(border=True):
        st.markdown(
            """
<div class="crm-section-kicker">OPORTUNIDADES</div>
<div class="crm-section-title">Gestión comercial</div>
<div class="crm-section-sub">Cotizaciones y negocios comerciales abiertos.</div>
<div class="crm-empty">
    <strong>Módulo listo para persistencia</strong>
    <span>La visual ya está preparada. El siguiente paso es conectar PostgreSQL para crear, editar y conservar oportunidades en Render.</span>
</div>
            """,
            unsafe_allow_html=True,
        )

# ============================================================
# SEGUIMIENTOS
# ============================================================

def _render_followups() -> None:
    with st.container(border=True):
        st.markdown(
            """
<div class="crm-section-kicker">SEGUIMIENTOS</div>
<div class="crm-section-title">Próximas acciones</div>
<div class="crm-section-sub">Llamadas, correos, reuniones y tareas comerciales.</div>
<div class="crm-empty">
    <strong>Sin seguimientos registrados</strong>
    <span>Cuando conectemos la base persistente, aquí aparecerán las acciones pendientes por cliente, vendedor y fecha.</span>
</div>
            """,
            unsafe_allow_html=True,
        )

# ============================================================
# PIPELINE
# ============================================================

def _render_pipeline() -> None:
    with st.container(border=True):
        st.markdown(
            """
<div class="crm-section-kicker">PIPELINE</div>
<div class="crm-section-title">Embudo comercial</div>
<div class="crm-section-sub">Prospecto → Contactado → Cotizado → Negociación → Ganado / Perdido</div>
<div class="crm-empty">
    <strong>Pipeline preparado</strong>
    <span>Las columnas y tarjetas del embudo se activarán cuando exista una tabla persistente de oportunidades.</span>
</div>
            """,
            unsafe_allow_html=True,
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
        '<h1>CRM</h1>'
        '<p>Clientes, actividad comercial, oportunidades y seguimiento.</p>'
        '</div>'
        '<div class="crm-live-pill">'
        '<i></i>ERP Ventas conectado'
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
        _render_opportunities()

    elif section == "Seguimientos":
        _render_followups()

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