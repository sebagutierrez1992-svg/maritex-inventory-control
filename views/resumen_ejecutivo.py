import pandas as pd
import streamlit as st
import altair as alt

from analytics.sales_metrics import calculate_commercial_totals, filter_sales
from ui.components import render_html
from utils.dates import available_months, month_bounds, month_label_es
from utils.numbers import format_clp


VAT_RATE = 0.19
VALID_GROUPS = ["Factura", "Boleta", "Nota de crédito"]


def _norm_text(value):
    return (
        str(value).strip().lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("_", " ")
        .replace("-", " ")
    )


def _find_column(columns, candidates):
    """
    Busca columnas por coincidencia exacta normalizada.
    Evita coincidencias parciales que pueden confundir, por ejemplo,
    Código cliente con Razón social.
    """
    normalized = {_norm_text(c): c for c in columns}

    for candidate in candidates:
        key = _norm_text(candidate)
        if key in normalized:
            return normalized[key]

    return None


def _period_days(a, b):
    return max((pd.Timestamp(b) - pd.Timestamp(a)).days + 1, 0)


def _business_days(a, b):
    return len(pd.bdate_range(a, b)) if b >= a else 0


def _signed_sales_amount(df, no_vat):
    amount = pd.to_numeric(
        df["VentaMonto_num"],
        errors="coerce",
    ).fillna(0).abs()

    if no_vat:
        amount = amount / (1 + VAT_RATE)

    sign = df["Grupo comercial"].map(
        {
            "Factura": 1,
            "Boleta": 1,
            "Nota de crédito": -1,
        }
    ).fillna(0)

    return amount * sign


def _group_amount(df, group, no_vat):
    part = df[df["Grupo comercial"].eq(group)].copy()
    if part.empty:
        return 0.0

    amount = pd.to_numeric(
        part["VentaMonto_num"],
        errors="coerce",
    ).fillna(0).abs()

    if no_vat:
        amount = amount / (1 + VAT_RATE)

    return float(amount.sum())


def _format_pct(value):
    return f"{value:.1f}%".replace(".", ",")


def _prepare_doc_table(df, no_vat, client_col=None, legal_col=None):
    if df.empty:
        return pd.DataFrame()

    cols = []
    for c in ["Fecha_dt", "TipoDocto", "Numero", legal_col, client_col, "Vendedor", "Bodega", "VentaMonto_num"]:
        if c and c in df.columns and c not in cols:
            cols.append(c)

    out = df[cols].copy()

    rename = {}
    if "Fecha_dt" in out.columns:
        out["Fecha"] = out["Fecha_dt"].dt.strftime("%d/%m/%Y")
        out = out.drop(columns=["Fecha_dt"])
    if "TipoDocto" in out.columns:
        rename["TipoDocto"] = "Tipo"
    if "Numero" in out.columns:
        rename["Numero"] = "Número"
    if legal_col and legal_col in out.columns:
        rename[legal_col] = "Código legal"
    if client_col and client_col in out.columns:
        rename[client_col] = "Razón social"

    if "VentaMonto_num" in out.columns:
        out["Total"] = pd.to_numeric(out["VentaMonto_num"], errors="coerce").fillna(0).abs()
        if no_vat:
            out["Total"] = out["Total"] / (1 + VAT_RATE)
        out = out.drop(columns=["VentaMonto_num"])

    out = out.rename(columns=rename)

    preferred = ["Fecha", "Tipo", "Número", "Código legal", "Razón social", "Vendedor", "Bodega", "Total"]
    existing = [c for c in preferred if c in out.columns]
    return out[existing]


def render(ctx):
    st.markdown("""
    <style>
    .block-container{
        max-width:1500px;
        padding-top:1.35rem;
        padding-bottom:2.5rem;
    }

    .exec-head{
        display:flex;
        justify-content:space-between;
        align-items:flex-start;
        gap:24px;
        margin-bottom:16px;
    }
    .exec-title{
        font-size:33px;
        line-height:1.05;
        font-weight:850;
        color:#0f172a;
        letter-spacing:-.035em;
    }
    .exec-subtitle{
        color:#4f6078;
        font-size:14px;
        margin-top:8px;
    }
    .exec-pill{
        background:#fff;
        border:1px solid #dbe4ee;
        border-radius:12px;
        padding:11px 14px;
        color:#546277;
        font-size:12px;
        box-shadow:0 3px 12px rgba(15,23,42,.035);
    }

    .section-card{
        background:#fff;
        border:1px solid #dce4ed;
        border-radius:15px;
        padding:16px;
        box-shadow:0 3px 15px rgba(15,23,42,.035);
        margin-bottom:16px;
    }

    .kpi-grid{
        display:grid;
        grid-template-columns:repeat(5,minmax(0,1fr));
        gap:12px;
        margin:14px 0;
    }
    .kpi-card{
        background:#fff;
        border:1px solid #dce4ed;
        border-radius:15px;
        padding:18px;
        min-height:145px;
        box-shadow:0 3px 14px rgba(15,23,42,.04);
    }
    .kpi-label{
        color:#4f6078;
        font-size:11px;
        font-weight:800;
        text-transform:uppercase;
        letter-spacing:.03em;
    }
    .kpi-sub{
        color:#6d7b90;
        font-size:10px;
        margin-top:3px;
    }
    .kpi-value{
        color:#101828;
        font-size:25px;
        font-weight:850;
        letter-spacing:-.02em;
        margin-top:16px;
    }
    .kpi-note{
        color:#6f7c90;
        font-size:11px;
        margin-top:10px;
    }
    .kpi-red .kpi-value{color:#dc3545;}
    .kpi-blue .kpi-value{color:#155eef;}

    .daily-strip{
        display:grid;
        grid-template-columns:repeat(3,minmax(0,1fr));
        gap:0;
        border:1px solid #dce4ed;
        background:#fff;
        border-radius:15px;
        margin:14px 0 16px;
        overflow:hidden;
    }
    .daily-item{
        padding:18px 22px;
        min-height:108px;
        border-right:1px solid #e4eaf0;
    }
    .daily-item:last-child{border-right:none;}
    .daily-item .label{
        font-size:11px;
        color:#4e5f77;
        font-weight:800;
        text-transform:uppercase;
    }
    .daily-item strong{
        display:block;
        font-size:22px;
        color:#101828;
        margin-top:11px;
    }
    .daily-item small{
        display:block;
        color:#728097;
        font-size:11px;
        margin-top:5px;
    }

    .composition-wrap{
        background:#fff;
        border:1px solid #dce4ed;
        border-radius:15px;
        padding:16px;
        margin:16px 0;
        box-shadow:0 3px 15px rgba(15,23,42,.035);
    }
    .section-title{
        color:#101828;
        font-size:13px;
        font-weight:850;
        text-transform:uppercase;
        letter-spacing:.02em;
        margin-bottom:13px;
    }
    .comp-row{
        display:grid;
        grid-template-columns:1fr auto 1fr auto 1fr auto 1fr;
        gap:12px;
        align-items:center;
    }
    .comp-card{
        background:#fbfcfe;
        border:1px solid #dfe6ee;
        border-radius:11px;
        padding:17px;
        text-align:center;
        min-height:94px;
    }
    .comp-card.blue{border-color:#9bb8ff;}
    .comp-card span{
        display:block;
        font-size:11px;
        font-weight:850;
        text-transform:uppercase;
        color:#334155;
    }
    .comp-card strong{
        display:block;
        font-size:20px;
        color:#111827;
        margin-top:8px;
    }
    .comp-card.red strong{color:#dc3545;}
    .comp-card.blue strong{color:#155eef;}
    .comp-card small{
        display:block;
        margin-top:6px;
        color:#718096;
        font-size:11px;
    }
    .comp-op{
        font-weight:900;
        font-size:25px;
        color:#23395d;
    }

    div[data-testid="stDataFrame"]{
        border:1px solid #dce4ed;
        border-radius:12px;
        overflow:hidden;
        background:#fff;
    }
    div[data-testid="stExpander"]{
        border:1px solid #dce4ed;
        border-radius:12px;
        background:#fff;
        box-shadow:none;
    }

    @media(max-width:1100px){
        .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
        .daily-strip{grid-template-columns:1fr;}
        .daily-item{border-right:none;border-bottom:1px solid #e4eaf0;}
        .comp-row{grid-template-columns:1fr;}
        .comp-op{text-align:center;}
    }
    </style>
    """, unsafe_allow_html=True)

    df = ctx.get("sales_df")

    render_html("""
    <div class="exec-head">
      <div>
        <div class="exec-title">Resumen Ejecutivo</div>
        <div class="exec-subtitle">Análisis de ventas · Facturas + Boletas − Notas de crédito</div>
      </div>
      <div class="exec-pill">Datos cargados desde ERP Ventas</div>
    </div>
    """)

    if df is None or df.empty:
        st.info("Carga ERP Ventas desde Plantillas.")
        return

    base = df[df["Grupo comercial"].isin(VALID_GROUPS)].copy()
    if base.empty:
        st.warning("No hay Facturas, Boletas o Notas de crédito reconocidas en el archivo ERP.")
        return

    # Columnas de cliente del ERP.
    # Prioridad estricta: Razón social = nombre del cliente.
    legal_col = _find_column(
        base.columns,
        [
            "CodigoLegal",
            "Código legal",
            "Codigo legal",
            "Cod legal",
            "Código Legal",
            "RUT cliente",
            "Rut cliente",
            "RUT",
            "Rut",
        ],
    )

    client_col = _find_column(
        base.columns,
        [
            "RazonSocial",
            "Razón social",
            "Razon social",
            "Razón Social",
            "Razon Social",
            "Cliente razón social",
            "Cliente razon social",
            "Nombre cliente",
            "Nombre Cliente",
        ],
    )

    # Nunca permitir que Código legal y Razón social apunten
    # accidentalmente a la misma columna.
    if legal_col is not None and client_col is not None and legal_col == client_col:
        legal_col = None

    months = available_months(base, "Fecha_dt")
    labels = [month_label_es(m) for m in months]
    mm = dict(zip(labels, months))

    sellers = sorted(base["Vendedor"].fillna("Sin vendedor").astype(str).str.strip().unique().tolist())
    whs = sorted(base["Bodega"].fillna("Sin bodega").astype(str).str.strip().unique().tolist()) if "Bodega" in base.columns else []
    types = sorted(base["TipoDocto"].dropna().astype(str).unique().tolist()) if "TipoDocto" in base.columns else []

    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns([1.0, 1.3, 1.0, .9, 1.15], gap="small")

        with c1:
            lab = st.selectbox("Mes", labels, index=0, key="exec_month_v700")
            month = mm[lab]
            mstart, mend = month_bounds(month)

        mr = base[(base["Fecha_dt"].dt.date >= mstart) & (base["Fecha_dt"].dt.date <= mend)]
        realmax = mr["Fecha_dt"].max().date() if not mr.empty else mstart
        dend = min(mend, realmax)

        with c2:
            days = st.date_input(
                "Rango de fechas",
                value=(mstart, dend),
                min_value=mstart,
                max_value=mend,
                key=f"exec_days_v700_{month}",
            )

        with c3:
            fs = st.multiselect("Vendedor", sellers, placeholder="Todos", key="exec_seller_v700")

        with c4:
            fw = st.multiselect("Bodega", whs, placeholder="Todas", key="exec_wh_v700")

        with c5:
            ft = st.multiselect(
                "Tipo de documento",
                types,
                placeholder="Facturas + Boletas + NC",
                key="exec_type_v700",
            )

        c6, c7 = st.columns([1.0, 1.0], gap="small")
        with c6:
            base_mode = st.selectbox(
                "Base de análisis",
                ["Venta final con IVA", "Venta final sin IVA"],
                key="exec_base_v700",
            )
        with c7:
            goal = st.number_input(
                "Meta de venta",
                min_value=0,
                value=100_000_000,
                step=100_000,
                key="exec_goal_v700",
            )

    sdate, edate = mstart, dend
    if isinstance(days, (tuple, list)) and len(days) == 2:
        sdate, edate = days

    filtered = filter_sales(base, sellers=fs, warehouses=fw, document_types=ft)
    actual_view = filtered[
        (filtered["Fecha_dt"].dt.date >= sdate)
        & (filtered["Fecha_dt"].dt.date <= edate)
    ].copy()

    actual_end = actual_view["Fecha_dt"].max().date() if not actual_view.empty else sdate
    no_vat = base_mode == "Venta final sin IVA"
    short = "Sin IVA" if no_vat else "Con IVA"

    totals = calculate_commercial_totals(actual_view, VAT_RATE)
    actual = float(totals["venta_neta_sin_iva"] if no_vat else totals["venta_neta_con_iva"])
    gross = float(totals["ventas_brutas_sin_iva"] if no_vat else totals["ventas_brutas_con_iva"])
    credits = float(totals["notas_credito_sin_iva"] if no_vat else totals["notas_credito_con_iva"])

    invoice_sales = _group_amount(actual_view, "Factura", no_vat)
    receipt_sales = _group_amount(actual_view, "Boleta", no_vat)
    credit_sales = _group_amount(actual_view, "Nota de crédito", no_vat)

    sales_only = actual_view[actual_view["Grupo comercial"].isin(["Factura", "Boleta"])]
    docs = sales_only["Numero"].nunique() if "Numero" in sales_only.columns else len(sales_only)
    ticket = gross / docs if docs else 0

    daily = actual_view.copy()
    daily["_VentaFirmada"] = _signed_sales_amount(daily, no_vat)
    daily["Fecha"] = daily["Fecha_dt"].dt.normalize()
    daily_sales = (
        daily.groupby("Fecha", as_index=False)
        .agg(Venta=("_VentaFirmada", "sum"))
        .sort_values("Fecha")
    )

    active_days = int((daily_sales["Venta"] != 0).sum()) if not daily_sales.empty else 0
    avg_day = float(daily_sales["Venta"].sum()) / active_days if active_days else 0
    best_day_value = float(daily_sales["Venta"].max()) if not daily_sales.empty else 0
    best_day_date = daily_sales.loc[daily_sales["Venta"].idxmax(), "Fecha"] if not daily_sales.empty else None
    last_day_value = float(daily_sales.iloc[-1]["Venta"]) if not daily_sales.empty else 0
    last_day_date = daily_sales.iloc[-1]["Fecha"] if not daily_sales.empty else None

    remaining_days = max((pd.Timestamp(mend) - pd.Timestamp(actual_end)).days, 0)

    prev_end = pd.Timestamp(sdate) - pd.Timedelta(days=1)
    plen = _period_days(sdate, actual_end)
    prev_start = prev_end - pd.Timedelta(days=max(plen - 1, 0))
    prev = filtered[
        (filtered["Fecha_dt"] >= prev_start.normalize())
        & (filtered["Fecha_dt"] <= prev_end.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1))
    ]
    prev_tot = calculate_commercial_totals(prev, VAT_RATE)
    previous = float(prev_tot["venta_neta_sin_iva"] if no_vat else prev_tot["venta_neta_con_iva"])
    variation = ((actual - previous) / previous * 100) if previous else (100 if actual > 0 else 0)

    nc_ratio = credit_sales / (invoice_sales + receipt_sales) * 100 if (invoice_sales + receipt_sales) > 0 else 0

    render_html(f"""
    <div class="kpi-grid">
      <div class="kpi-card kpi-blue">
        <div class="kpi-label">Venta neta</div>
        <div class="kpi-sub">{short}</div>
        <div class="kpi-value">{format_clp(actual)}</div>
        <div class="kpi-note">Facturas + Boletas − NC · {variation:+.1f}% vs período anterior</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Venta bruta</div>
        <div class="kpi-sub">{short}</div>
        <div class="kpi-value">{format_clp(gross)}</div>
        <div class="kpi-note">Antes de notas de crédito</div>
      </div>
      <div class="kpi-card kpi-red">
        <div class="kpi-label">Notas de crédito</div>
        <div class="kpi-sub">{short}</div>
        <div class="kpi-value">-{format_clp(credit_sales)}</div>
        <div class="kpi-note">{_format_pct(nc_ratio)} sobre Facturas + Boletas</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Ticket promedio</div>
        <div class="kpi-sub">{short}</div>
        <div class="kpi-value">{format_clp(ticket)}</div>
        <div class="kpi-note">{docs:,} documentos de venta</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Días restantes</div>
        <div class="kpi-sub">del mes</div>
        <div class="kpi-value">{remaining_days}</div>
        <div class="kpi-note">calendario</div>
      </div>
    </div>
    """)

    render_html(f"""
    <div class="daily-strip">
      <div class="daily-item">
        <div class="label">Venta promedio por día</div>
        <strong>{format_clp(avg_day)}</strong>
        <small>{active_days} días con movimiento</small>
      </div>
      <div class="daily-item">
        <div class="label">Mejor día</div>
        <strong>{format_clp(best_day_value)}</strong>
        <small>{pd.Timestamp(best_day_date).strftime("%d/%m/%Y") if best_day_date is not None else "Sin datos"}</small>
      </div>
      <div class="daily-item">
        <div class="label">Último día con venta</div>
        <strong>{format_clp(last_day_value)}</strong>
        <small>{pd.Timestamp(last_day_date).strftime("%d/%m/%Y") if last_day_date is not None else "Sin datos"}</small>
      </div>
    </div>
    """)

    invoice_pct = invoice_sales / gross * 100 if gross else 0
    receipt_pct = receipt_sales / gross * 100 if gross else 0
    credit_pct = credit_sales / gross * 100 if gross else 0

    render_html(f"""
    <div class="composition-wrap">
      <div class="section-title">Composición de la venta · {short}</div>
      <div class="comp-row">
        <div class="comp-card">
          <span>Facturas</span>
          <strong>{format_clp(invoice_sales)}</strong>
          <small>{_format_pct(invoice_pct)}</small>
        </div>
        <div class="comp-op">+</div>
        <div class="comp-card">
          <span>Boletas</span>
          <strong>{format_clp(receipt_sales)}</strong>
          <small>{_format_pct(receipt_pct)}</small>
        </div>
        <div class="comp-op">−</div>
        <div class="comp-card red">
          <span>Notas de crédito</span>
          <strong>-{format_clp(credit_sales)}</strong>
          <small>-{_format_pct(credit_pct)}</small>
        </div>
        <div class="comp-op">=</div>
        <div class="comp-card blue">
          <span>Venta neta</span>
          <strong>{format_clp(actual)}</strong>
          <small>100,0%</small>
        </div>
      </div>
    </div>
    """)

    # Expandibles: facturas, boletas, notas de crédito
    exp1, exp2, exp3 = st.columns(3, gap="small")

    with exp1:
        inv_df = actual_view[actual_view["Grupo comercial"].eq("Factura")].copy()
        with st.expander(f"FACTURAS · {len(inv_df):,} registros"):
            st.dataframe(
                _prepare_doc_table(inv_df, no_vat, client_col, legal_col),
                hide_index=True,
                use_container_width=True,
                height=300,
                column_config={"Total": st.column_config.NumberColumn("Total", format="$%d")},
            )

    with exp2:
        bol_df = actual_view[actual_view["Grupo comercial"].eq("Boleta")].copy()
        with st.expander(f"BOLETAS · {len(bol_df):,} registros"):
            st.dataframe(
                _prepare_doc_table(bol_df, no_vat, client_col, legal_col),
                hide_index=True,
                use_container_width=True,
                height=300,
                column_config={"Total": st.column_config.NumberColumn("Total", format="$%d")},
            )

    with exp3:
        nc_df = actual_view[actual_view["Grupo comercial"].eq("Nota de crédito")].copy()
        with st.expander(f"NOTAS DE CRÉDITO · {len(nc_df):,} registros"):
            st.dataframe(
                _prepare_doc_table(nc_df, no_vat, client_col, legal_col),
                hide_index=True,
                use_container_width=True,
                height=300,
                column_config={"Total": st.column_config.NumberColumn("Total", format="$%d")},
            )

    left, right = st.columns([1.0, 1.05], gap="small")

    with left:
        render_html('<div class="section-title" style="margin-top:18px">Clientes · Top por venta neta</div>')

        if legal_col or client_col:
            clients = actual_view.copy()
            clients["_VentaFirmada"] = _signed_sales_amount(clients, no_vat)

            group_cols = [c for c in [legal_col, client_col] if c is not None]

            agg_map = {"Venta neta": ("_VentaFirmada", "sum")}
            if "Numero" in clients.columns:
                agg_map["Docs."] = ("Numero", "nunique")

            client_group = (
                clients.groupby(group_cols, dropna=False)
                .agg(**agg_map)
                .reset_index()
                .sort_values("Venta neta", ascending=False)
            )

            rename = {}
            if legal_col:
                rename[legal_col] = "Código legal"
            if client_col:
                rename[client_col] = "Razón social"
            client_group = client_group.rename(columns=rename)

            total_clients = float(client_group["Venta neta"].sum()) if not client_group.empty else 0
            client_group["% Part."] = (
                client_group["Venta neta"] / total_clients * 100
                if total_clients
                else 0
            )

            search = st.text_input(
                "Buscar cliente",
                placeholder="Código legal o razón social...",
                key="exec_client_search_v700",
                label_visibility="collapsed",
            )

            view = client_group.copy()
            if search:
                term = search.strip().lower()
                mask = pd.Series(False, index=view.index)
                for col in ["Código legal", "Razón social"]:
                    if col in view.columns:
                        mask |= view[col].fillna("").astype(str).str.lower().str.contains(term, regex=False)
                view = view[mask]

            st.dataframe(
                view.head(10),
                hide_index=True,
                use_container_width=True,
                height=385,
                column_config={
                    "Venta neta": st.column_config.NumberColumn("Venta neta", format="$%d"),
                    "% Part.": st.column_config.NumberColumn("% Part.", format="%.1f%%"),
                },
            )
        else:
            st.warning(
                "No se detectó la columna Razón social del ERP. "
                f"Columnas disponibles: {', '.join(map(str, actual_view.columns.tolist()))}"
            )

    with right:
        render_html(f'<div class="section-title" style="margin-top:18px">Performance de venta por día · {short}</div>')

        if daily_sales.empty:
            st.info("No hay ventas diarias para el período.")
        else:
            avg_daily_value = float(daily_sales["Venta"].mean())
            running_avg = daily_sales["Venta"].expanding().mean()
            chart_df = daily_sales.copy()
            chart_df["Promedio diario"] = avg_daily_value
            chart_df["Promedio acumulado"] = running_avg

            bars = alt.Chart(chart_df).mark_bar(
                cornerRadiusTopLeft=3,
                cornerRadiusTopRight=3,
                color="#2563eb",
            ).encode(
                x=alt.X("Fecha:T", title="Fecha", axis=alt.Axis(format="%d/%m", labelAngle=0)),
                y=alt.Y("Venta:Q", title="Venta neta (CLP)"),
                tooltip=[
                    alt.Tooltip("Fecha:T", title="Fecha", format="%d/%m/%Y"),
                    alt.Tooltip("Venta:Q", title="Venta neta", format=","),
                ],
            )

            avg_line = alt.Chart(chart_df).mark_rule(
                color="#16a34a",
                strokeDash=[6, 4],
            ).encode(
                y="Promedio diario:Q"
            )

            run_line = alt.Chart(chart_df).mark_line(
                color="#ef4444",
                strokeDash=[5, 4],
                strokeWidth=1.5,
            ).encode(
                x="Fecha:T",
                y="Promedio acumulado:Q",
            )

            st.altair_chart(
                (bars + avg_line + run_line).properties(height=385),
                use_container_width=True,
            )

    # Documentos de venta / NC al final, como referencia
    col_a, col_b = st.columns(2, gap="small")

    with col_a:
        render_html('<div class="section-title" style="margin-top:18px">Documentos de venta · Facturas + Boletas</div>')
        docs_df = actual_view[actual_view["Grupo comercial"].isin(["Factura", "Boleta"])].copy()
        st.dataframe(
            _prepare_doc_table(docs_df, no_vat, client_col, legal_col).head(10),
            hide_index=True,
            use_container_width=True,
            height=300,
            column_config={"Total": st.column_config.NumberColumn("Total", format="$%d")},
        )

    with col_b:
        render_html('<div class="section-title" style="margin-top:18px">Notas de crédito</div>')
        nc_df = actual_view[actual_view["Grupo comercial"].eq("Nota de crédito")].copy()
        st.dataframe(
            _prepare_doc_table(nc_df, no_vat, client_col, legal_col).head(10),
            hide_index=True,
            use_container_width=True,
            height=300,
            column_config={"Total": st.column_config.NumberColumn("Total", format="$%d")},
        )

    render_html("""
    <div style="
        margin-top:16px;
        border:1px solid #d6e3ff;
        background:#f7faff;
        border-radius:12px;
        padding:13px 15px;
        color:#52617a;
        font-size:12px;">
      Las ventas se calculan como <strong>Facturas + Boletas − Notas de crédito</strong>.
      Los montos consideran la base de análisis seleccionada.
    </div>
    """)