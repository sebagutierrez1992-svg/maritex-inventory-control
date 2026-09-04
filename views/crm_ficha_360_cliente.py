

from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from services.commercial_dashboard_service import (
    prepare_commercial_base,
    signed_amount,
    seller_name,
)

try:
    from services.crm_service import (
        list_followups,
        list_opportunities,
    )
except Exception:
    list_followups = None
    list_opportunities = None


# ============================================================
# HELPERS
# ============================================================

def _money(value: float) -> str:
    try:
        return "$" + f"{int(round(float(value))):,}".replace(",", ".")
    except Exception:
        return "$0"


def _number(value: float | int) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except Exception:
        return "0"


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _display_seller(code: Any) -> str:
    name = _safe_str(seller_name(str(code))) if _safe_str(code) else ""
    corrections = {
        "GINO MATIUS": "GINO MATUS",
    }
    return corrections.get(name.upper(), name)


def _find_first_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    return None


def _find_client_column(df: pd.DataFrame) -> str | None:
    return _find_first_column(
        df,
        (
            "RazonSocial",
            "Razón Social",
            "CLIENTE",
            "Cliente",
            "cliente",
        ),
    )


def _find_rut_column(df: pd.DataFrame) -> str | None:
    return _find_first_column(
        df,
        (
            "CodigoLegal",
            "Código Legal",
            "RUT",
            "Rut",
            "rut",
        ),
    )


def _find_doc_column(df: pd.DataFrame) -> str | None:
    return _find_first_column(
        df,
        (
            "Numero",
            "Número",
            "Documento",
            "NroDocumento",
            "Nro Documento",
        ),
    )


def _find_units_column(df: pd.DataFrame) -> str | None:
    return _find_first_column(
        df,
        (
            "Cantidad_num",
            "Cantidad",
            "Unidades",
            "Unidad",
            "Qty",
            "QTY",
        ),
    )


def _find_description_column(df: pd.DataFrame) -> str | None:
    return _find_first_column(
        df,
        (
            "Producto",
            "Descripcion",
            "Descripción",
            "NombreProducto",
            "Nombre Producto",
            "Detalle",
        ),
    )


def _usable_product_column(df: pd.DataFrame) -> str | None:
    """
    Busca una columna de SKU/código que realmente contenga valores.
    Evita usar una columna existente pero completamente vacía.
    """
    candidates = (
        "SKU",
        "Sku",
        "sku",
        "CodigoProducto",
        "CódigoProducto",
        "Codigo Producto",
        "Código Producto",
        "Codigo",
        "Código",
        "CodProducto",
        "Cod Producto",
        "Articulo",
        "Artículo",
        "Item",
        "Referencia",
    )

    for candidate in candidates:
        if candidate not in df.columns:
            continue

        values = df[candidate].astype(str).str.strip()
        valid = ~values.isin(["", "nan", "None", "<NA>"])

        if int(valid.sum()) > 0:
            return candidate

    # Si no existe código utilizable, usar descripción/producto como último recurso.
    description_col = _find_description_column(df)
    if description_col:
        values = df[description_col].astype(str).str.strip()
        valid = ~values.isin(["", "nan", "None", "<NA>"])
        if int(valid.sum()) > 0:
            return description_col

    return None


def _clean_key(series: pd.Series) -> pd.Series:
    values = series.astype(str).str.strip()
    values = values.replace(
        {
            "": pd.NA,
            "nan": pd.NA,
            "None": pd.NA,
            "<NA>": pd.NA,
        }
    )
    return values


# ============================================================
# PREPARACIÓN DE DATOS
# ============================================================

def _prepare_client_sales(ctx: dict[str, Any]) -> tuple[pd.DataFrame, str | None]:
    sales_df = ctx.get("sales_df")
    base = prepare_commercial_base(sales_df)

    if base is None or base.empty:
        return pd.DataFrame(), None

    client_col = _find_client_column(base)
    if client_col is None:
        return pd.DataFrame(), None

    base = base.copy()
    base["_crm360_amount"] = signed_amount(base, no_vat=False)
    base["_crm360_client"] = _clean_key(base[client_col])
    base = base[base["_crm360_client"].notna()].copy()

    return base, client_col


def _client_master(base: pd.DataFrame) -> pd.DataFrame:
    rut_col = _find_rut_column(base)

    agg = (
        base.groupby("_crm360_client", as_index=False)
        .agg(
            Ventas=("_crm360_amount", "sum"),
            UltimaCompra=("Fecha_dt", "max"),
            PrimeraCompra=("Fecha_dt", "min"),
        )
    )

    if rut_col:
        rut_work = base[["_crm360_client", rut_col]].copy()
        rut_work["_rut"] = _clean_key(rut_work[rut_col])
        rut_map = (
            rut_work.dropna(subset=["_rut"])
            .drop_duplicates("_crm360_client", keep="last")
            .set_index("_crm360_client")["_rut"]
            .to_dict()
        )
        agg["RUT"] = agg["_crm360_client"].map(rut_map).fillna("")
    else:
        agg["RUT"] = ""

    if "_VendedorCodigo" in base.columns:
        seller_map = (
            base.sort_values("Fecha_dt")
            .dropna(subset=["_VendedorCodigo"])
            .drop_duplicates("_crm360_client", keep="last")
            .set_index("_crm360_client")["_VendedorCodigo"]
            .to_dict()
        )
        agg["VendedorCodigo"] = agg["_crm360_client"].map(seller_map).fillna("")
        agg["Vendedor"] = agg["VendedorCodigo"].map(_display_seller)
    else:
        agg["VendedorCodigo"] = ""
        agg["Vendedor"] = ""

    return agg.sort_values(["Ventas", "_crm360_client"], ascending=[False, True])


def _client_sales_detail(base: pd.DataFrame, client_name: str) -> pd.DataFrame:
    return base[base["_crm360_client"] == client_name].copy()


# ============================================================
# MÉTRICAS
# ============================================================

def _client_kpis(client_df: pd.DataFrame, reference_date: pd.Timestamp) -> dict[str, Any]:
    sale_docs = client_df[
        client_df["Grupo comercial"].isin(["Factura", "Boleta"])
    ].copy()

    total_sales = float(client_df["_crm360_amount"].sum())
    docs_col = _find_doc_column(client_df)

    docs = int(sale_docs[docs_col].nunique()) if docs_col else 0
    ticket = total_sales / docs if docs else 0.0

    ultima = sale_docs["Fecha_dt"].max() if not sale_docs.empty else client_df["Fecha_dt"].max()
    primera = sale_docs["Fecha_dt"].min() if not sale_docs.empty else client_df["Fecha_dt"].min()

    if pd.notna(ultima) and pd.notna(reference_date):
        days_inactive = max(int((reference_date.normalize() - ultima.normalize()).days), 0)
    else:
        days_inactive = None

    # Frecuencia: días promedio entre documentos de venta.
    frequency_days = None
    if docs_col and not sale_docs.empty:
        purchase_dates = (
            sale_docs[[docs_col, "Fecha_dt"]]
            .dropna()
            .drop_duplicates(subset=[docs_col])
            .sort_values("Fecha_dt")["Fecha_dt"]
        )
        if len(purchase_dates) >= 2:
            diffs = purchase_dates.diff().dropna().dt.days
            if not diffs.empty:
                frequency_days = float(diffs.mean())

    if days_inactive is None:
        state = "Sin dato"
        state_class = "neutral"
    elif days_inactive <= 30:
        state = "Activo"
        state_class = "ok"
    elif days_inactive <= 60:
        state = "Atención"
        state_class = "warn"
    elif days_inactive <= 90:
        state = "Riesgo"
        state_class = "risk"
    else:
        state = "Inactivo"
        state_class = "critical"

    return {
        "ventas": total_sales,
        "documentos": docs,
        "ticket": ticket,
        "ultima_compra": ultima,
        "primera_compra": primera,
        "dias_inactivo": days_inactive,
        "frecuencia_dias": frequency_days,
        "estado": state,
        "estado_class": state_class,
    }


def _monthly_sales(client_df: pd.DataFrame) -> pd.DataFrame:
    work = client_df.copy()
    work = work[work["Fecha_dt"].notna()].copy()

    if work.empty:
        return pd.DataFrame(columns=["Mes", "Ventas"])

    work["Mes"] = work["Fecha_dt"].dt.to_period("M").astype(str)

    return (
        work.groupby("Mes", as_index=False)["_crm360_amount"]
        .sum()
        .rename(columns={"_crm360_amount": "Ventas"})
        .sort_values("Mes")
    )


def _top_products(client_df: pd.DataFrame) -> pd.DataFrame:
    product_col = _usable_product_column(client_df)
    if not product_col:
        return pd.DataFrame()

    doc_col = _find_doc_column(client_df)
    units_col = _find_units_column(client_df)
    desc_col = _find_description_column(client_df)

    work = client_df.copy()
    work["_product_key"] = _clean_key(work[product_col])
    work = work[work["_product_key"].notna()].copy()

    if work.empty:
        return pd.DataFrame()

    # Descripción asociada al SKU/código, si existe y es otra columna.
    if desc_col and desc_col != product_col:
        desc_map = (
            work[["_product_key", desc_col]]
            .assign(_desc=lambda x: _clean_key(x[desc_col]))
            .dropna(subset=["_desc"])
            .drop_duplicates("_product_key", keep="last")
            .set_index("_product_key")["_desc"]
            .to_dict()
        )
    else:
        desc_map = {}

    grouped = work.groupby("_product_key", as_index=False).agg(
        Ventas=("_crm360_amount", "sum")
    )

    if units_col:
        units_num = pd.to_numeric(work[units_col], errors="coerce").fillna(0)
        work["_units_num"] = units_num.abs()
        units = (
            work.groupby("_product_key", as_index=False)["_units_num"]
            .sum()
            .rename(columns={"_units_num": "Unidades"})
        )
        grouped = grouped.merge(units, on="_product_key", how="left")

    if doc_col:
        docs = (
            work[work["Grupo comercial"].isin(["Factura", "Boleta"])]
            .groupby("_product_key", as_index=False)[doc_col]
            .nunique()
            .rename(columns={doc_col: "Documentos"})
        )
        grouped = grouped.merge(docs, on="_product_key", how="left")

    total = float(grouped["Ventas"].sum())
    grouped["Participación"] = (
        grouped["Ventas"] / total * 100 if total else 0.0
    )

    grouped["Producto"] = grouped["_product_key"].map(desc_map).fillna("")

    grouped = grouped.sort_values("Ventas", ascending=False).head(12)

    rename_key = "SKU" if product_col != desc_col else "Producto"
    grouped = grouped.rename(columns={"_product_key": rename_key})

    ordered = []
    for col in ("SKU", "Producto", "Unidades", "Ventas", "Documentos", "Participación"):
        if col in grouped.columns and col not in ordered:
            ordered.append(col)

    return grouped[ordered]


# ============================================================
# CRM
# ============================================================

def _client_crm_rows(
    client_name: str,
    rut: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    opportunities: list[dict[str, Any]] = []
    followups: list[dict[str, Any]] = []

    try:
        if list_opportunities:
            rows = list_opportunities(client_rut=rut, limit=500) if rut else list_opportunities(limit=500)
            for row in rows or []:
                same_name = _safe_str(row.get("client_name")).lower() == client_name.lower()
                same_rut = bool(rut) and _safe_str(row.get("client_rut")).lower() == rut.lower()
                if same_name or same_rut:
                    opportunities.append(row)
    except Exception:
        pass

    try:
        if list_followups:
            rows = list_followups(client_rut=rut, limit=500) if rut else list_followups(limit=500)
            for row in rows or []:
                same_name = _safe_str(row.get("client_name")).lower() == client_name.lower()
                same_rut = bool(rut) and _safe_str(row.get("client_rut")).lower() == rut.lower()
                if same_name or same_rut:
                    followups.append(row)
    except Exception:
        pass

    return opportunities, followups


# ============================================================
# VISUAL
# ============================================================

def _styles() -> None:
    st.markdown(
        """
<style>
.crm360-page-head{
    display:flex;
    justify-content:space-between;
    align-items:center;
    gap:18px;
    padding:20px 22px;
    border:1px solid #26333d;
    border-left:4px solid #ffc400;
    border-radius:14px;
    background:linear-gradient(135deg,#101a22 0%,#0d151c 100%);
    margin:4px 0 16px;
}
.crm360-page-title{
    color:#ffffff;
    font-size:27px;
    line-height:1.05;
    font-weight:850;
    letter-spacing:-.4px;
}
.crm360-page-sub{
    color:#91a1ad;
    font-size:11px;
    margin-top:7px;
}
.crm360-pill{
    display:inline-flex;
    align-items:center;
    gap:7px;
    white-space:nowrap;
    padding:8px 11px;
    border:1px solid #33434e;
    border-radius:999px;
    background:#0b1319;
    color:#dfe7ec;
    font-size:10px;
    font-weight:700;
}
.crm360-dot{
    width:7px;
    height:7px;
    border-radius:50%;
    background:#ffc400;
    box-shadow:0 0 0 3px rgba(255,196,0,.12);
}
.crm360-client-card{
    padding:18px 20px;
    border:1px solid #2b3944;
    border-left:5px solid #ffc400;
    border-radius:13px;
    background:#101a22;
    margin:12px 0 13px;
}
.crm360-client-name{
    color:#fff;
    font-size:24px;
    font-weight:850;
    margin:0;
}
.crm360-client-meta{
    color:#9cadb9;
    font-size:10px;
    margin-top:7px;
}
.crm360-kpis{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:12px;
    margin:0 0 15px;
}
.crm360-kpi{
    min-height:92px;
    padding:15px 16px;
    border:1px solid #2b3944;
    border-radius:12px;
    background:#101a22;
}
.crm360-kpi-label{
    color:#9dadb9;
    font-size:10px;
    font-weight:700;
    margin-bottom:8px;
}
.crm360-kpi-value{
    color:#fff;
    font-size:21px;
    line-height:1.1;
    font-weight:850;
}
.crm360-kpi-note{
    color:#71828e;
    font-size:9px;
    margin-top:7px;
}
.crm360-status{
    display:inline-flex;
    align-items:center;
    padding:5px 9px;
    border-radius:999px;
    font-size:10px;
    font-weight:800;
    margin-top:8px;
}
.crm360-status.ok{background:rgba(54,211,153,.10);color:#7ee7be;border:1px solid rgba(54,211,153,.25);}
.crm360-status.warn{background:rgba(255,196,0,.10);color:#ffd759;border:1px solid rgba(255,196,0,.25);}
.crm360-status.risk{background:rgba(255,143,64,.10);color:#ffad72;border:1px solid rgba(255,143,64,.25);}
.crm360-status.critical{background:rgba(255,88,88,.10);color:#ff9696;border:1px solid rgba(255,88,88,.25);}
.crm360-status.neutral{background:rgba(148,163,184,.10);color:#c2ccd4;border:1px solid rgba(148,163,184,.25);}
.crm360-section{
    color:#fff;
    font-size:18px;
    font-weight:800;
    margin:8px 0 2px;
}
.crm360-section-sub{
    color:#7f919e;
    font-size:9px;
    margin-bottom:9px;
}
.crm360-activity{
    display:grid;
    grid-template-columns:repeat(4,minmax(0,1fr));
    gap:10px;
    margin:4px 0 15px;
}
.crm360-activity-item{
    padding:12px 13px;
    border:1px solid #263540;
    border-radius:10px;
    background:#0f1820;
}
.crm360-activity-label{
    color:#82939f;
    font-size:9px;
}
.crm360-activity-value{
    color:#edf2f5;
    font-size:14px;
    font-weight:800;
    margin-top:5px;
}
@media(max-width:1100px){
    .crm360-kpis,.crm360-activity{grid-template-columns:repeat(2,minmax(0,1fr));}
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _kpi_html(label: str, value: str, note: str = "", status: tuple[str, str] | None = None) -> str:
    status_html = ""
    if status:
        text, css_class = status
        status_html = f'<div class="crm360-status {escape(css_class)}">{escape(text)}</div>'

    note_html = f'<div class="crm360-kpi-note">{escape(note)}</div>' if note else ""

    # Se devuelve en una sola línea para evitar que Streamlit interprete
    # los fragmentos HTML indentados como bloques de código Markdown.
    return (
        f'<div class="crm360-kpi">'
        f'<div class="crm360-kpi-label">{escape(label)}</div>'
        f'<div class="crm360-kpi-value">{escape(value)}</div>'
        f'{status_html}'
        f'{note_html}'
        f'</div>'
    )


def render_client_360(ctx: dict[str, Any]) -> None:
    _styles()

    st.markdown(
        """
<div class="crm360-page-head">
    <div>
        <div class="crm360-page-title">Ficha 360° de Cliente</div>
        <div class="crm360-page-sub">
            Perfil comercial unificado · ventas ERP · comportamiento de compra · oportunidades · seguimientos
        </div>
    </div>
    <div class="crm360-pill"><span class="crm360-dot"></span> ERP + CRM</div>
</div>
        """,
        unsafe_allow_html=True,
    )

    base, client_col = _prepare_client_sales(ctx)

    if base.empty or not client_col:
        st.warning("No hay ventas comerciales disponibles para construir la ficha 360°.")
        return

    master = _client_master(base)

    search_col, selector_col = st.columns([0.9, 1.7])

    with search_col:
        search = st.text_input(
            "Buscar cliente",
            placeholder="Razón social o RUT...",
            key="crm360_search",
        ).strip()

    filtered = master.copy()
    if search:
        needle = search.lower()
        filtered = filtered[
            filtered["_crm360_client"].str.lower().str.contains(needle, na=False)
            | filtered["RUT"].astype(str).str.lower().str.contains(needle, na=False)
        ]

    if filtered.empty:
        st.info("No se encontraron clientes con ese criterio.")
        return

    with selector_col:
        selected = st.selectbox(
            "Cliente",
            filtered["_crm360_client"].tolist(),
            key="crm360_client_selector",
        )

    client_row = filtered[filtered["_crm360_client"] == selected].iloc[0]
    client_df = _client_sales_detail(base, selected)

    reference_date = base["Fecha_dt"].max()
    kpis = _client_kpis(client_df, reference_date)

    rut = _safe_str(client_row.get("RUT"))
    vendedor = _safe_str(client_row.get("Vendedor"))

    st.markdown(
        f"""
<div class="crm360-client-card">
    <div class="crm360-client-name">{escape(selected)}</div>
    <div class="crm360-client-meta">
        RUT: {escape(rut or "Sin dato")} &nbsp;·&nbsp;
        Vendedor: {escape(vendedor or "Sin dato")}
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    last_purchase = (
        kpis["ultima_compra"].strftime("%d-%m-%Y")
        if pd.notna(kpis["ultima_compra"])
        else "Sin dato"
    )
    days_txt = (
        f'{_number(kpis["dias_inactivo"])} días'
        if kpis["dias_inactivo"] is not None
        else "Sin dato"
    )

    kpi_grid_html = (
        '<div class="crm360-kpis">'
        + _kpi_html(
            "Venta acumulada",
            _money(kpis["ventas"]),
            "Factura + Boleta − Nota de crédito",
        )
        + _kpi_html(
            "Documentos de venta",
            _number(kpis["documentos"]),
            "Documentos únicos · Factura + Boleta",
        )
        + _kpi_html(
            "Ticket promedio",
            _money(kpis["ticket"]),
            "Venta neta / documentos de venta",
        )
        + _kpi_html(
            "Última compra",
            last_purchase,
            days_txt,
            (kpis["estado"], kpis["estado_class"]),
        )
        + '</div>'
    )
    st.markdown(kpi_grid_html, unsafe_allow_html=True)

    # --------------------------------------------------------
    # ACTIVIDAD
    # --------------------------------------------------------
    frequency_txt = (
        f'{kpis["frecuencia_dias"]:.0f} días'
        if kpis["frecuencia_dias"] is not None
        else "Sin histórico suficiente"
    )
    first_purchase = (
        kpis["primera_compra"].strftime("%d-%m-%Y")
        if pd.notna(kpis["primera_compra"])
        else "Sin dato"
    )
    source_date = (
        reference_date.strftime("%d-%m-%Y")
        if pd.notna(reference_date)
        else "Sin dato"
    )

    st.markdown(
        """
<div class="crm360-section">Actividad del cliente</div>
<div class="crm360-section-sub">
    Señales calculadas sobre el último día disponible en la fuente ERP.
</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div class="crm360-activity">
    <div class="crm360-activity-item">
        <div class="crm360-activity-label">Estado comercial</div>
        <div class="crm360-activity-value">{escape(kpis["estado"])}</div>
    </div>
    <div class="crm360-activity-item">
        <div class="crm360-activity-label">Días desde última compra</div>
        <div class="crm360-activity-value">{escape(days_txt)}</div>
    </div>
    <div class="crm360-activity-item">
        <div class="crm360-activity-label">Frecuencia promedio</div>
        <div class="crm360-activity-value">{escape(frequency_txt)}</div>
    </div>
    <div class="crm360-activity-item">
        <div class="crm360-activity-label">Primera compra visible</div>
        <div class="crm360-activity-value">{escape(first_purchase)}</div>
    </div>
</div>
        """,
        unsafe_allow_html=True,
    )

    left, right = st.columns([1.08, 1])

    with left:
        st.markdown(
            """
<div class="crm360-section">Evolución de ventas</div>
<div class="crm360-section-sub">Venta neta mensual del cliente en el histórico actualmente cargado.</div>
            """,
            unsafe_allow_html=True,
        )

        monthly = _monthly_sales(client_df)
        if not monthly.empty:
            st.bar_chart(
                monthly.set_index("Mes")["Ventas"],
                use_container_width=True,
            )
        else:
            st.info("Sin evolución mensual disponible.")

    with right:
        st.markdown(
            """
<div class="crm360-section">Productos más comprados</div>
<div class="crm360-section-sub">Ranking por venta neta. Los documentos son únicos por producto.</div>
            """,
            unsafe_allow_html=True,
        )

        products = _top_products(client_df)

        if products.empty:
            st.info(
                "La fuente ERP no contiene un SKU/código de producto utilizable para este cliente."
            )
        else:
            show = products.copy()

            if "Ventas" in show.columns:
                show["Ventas"] = show["Ventas"].map(_money)

            if "Unidades" in show.columns:
                show["Unidades"] = show["Unidades"].map(_number)

            if "Documentos" in show.columns:
                show["Documentos"] = show["Documentos"].fillna(0).map(_number)

            if "Participación" in show.columns:
                show["Participación"] = show["Participación"].map(
                    lambda x: f"{float(x):.1f}%"
                )

            st.dataframe(
                show,
                use_container_width=True,
                hide_index=True,
                height=310,
            )

    # --------------------------------------------------------
    # HISTORIAL + CRM
    # --------------------------------------------------------
    opportunities, followups = _client_crm_rows(selected, rut)

    tab1, tab2, tab3 = st.tabs(
        ["Historial ERP", "Oportunidades", "Seguimientos"]
    )

    with tab1:
        doc_col = _find_doc_column(client_df)
        product_col = _usable_product_column(client_df)

        cols: list[str] = []
        for c in (
            "Fecha_dt",
            "Grupo comercial",
            doc_col,
            product_col,
            "_crm360_amount",
        ):
            if c and c in client_df.columns and c not in cols:
                cols.append(c)

        hist = client_df[cols].sort_values("Fecha_dt", ascending=False).copy()

        rename = {
            "Fecha_dt": "Fecha",
            "Grupo comercial": "Tipo",
            "_crm360_amount": "Venta",
        }
        if doc_col:
            rename[doc_col] = "Documento"
        if product_col:
            rename[product_col] = "SKU / Producto"

        hist = hist.rename(columns=rename)

        if "Venta" in hist.columns:
            hist["Venta"] = hist["Venta"].map(_money)

        if "Fecha" in hist.columns:
            hist["Fecha"] = pd.to_datetime(hist["Fecha"], errors="coerce").dt.strftime("%d-%m-%Y")

        st.dataframe(
            hist,
            use_container_width=True,
            hide_index=True,
            height=360,
        )

    with tab2:
        if not opportunities:
            st.info(
                "No hay oportunidades disponibles para este cliente "
                "o la base CRM no está conectada en este entorno."
            )
        else:
            opp_df = pd.DataFrame(opportunities)
            keep = [
                c
                for c in (
                    "id",
                    "title",
                    "stage",
                    "status",
                    "estimated_amount",
                    "probability",
                    "next_action",
                    "next_action_date",
                    "seller",
                )
                if c in opp_df.columns
            ]

            if "estimated_amount" in opp_df.columns:
                opp_df["estimated_amount"] = pd.to_numeric(
                    opp_df["estimated_amount"], errors="coerce"
                ).fillna(0).map(_money)

            st.dataframe(
                opp_df[keep],
                use_container_width=True,
                hide_index=True,
                height=330,
            )

    with tab3:
        if not followups:
            st.info(
                "No hay seguimientos disponibles para este cliente "
                "o la base CRM no está conectada en este entorno."
            )
        else:
            fol_df = pd.DataFrame(followups)
            keep = [
                c
                for c in (
                    "id",
                    "followup_type",
                    "subject",
                    "status",
                    "next_followup_date",
                    "seller",
                )
                if c in fol_df.columns
            ]

            st.dataframe(
                fol_df[keep],
                use_container_width=True,
                hide_index=True,
                height=330,
            )

    st.caption(
        f"Fuente comercial única · Con IVA · Última fecha ERP disponible: {source_date}"
    )
