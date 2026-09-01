import html
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from analytics.sales_metrics import calculate_commercial_totals, filter_sales
from ui.components import render_html
from utils.dates import available_months, month_bounds, month_label_es
from utils.numbers import format_clp


VAT_RATE = 0.19
VALID_GROUPS = ["Factura", "Boleta", "Nota de crédito"]

# Catálogo comercial aprobado para esta vista.
# 52 y 53 quedan fuera expresamente.
SELLER_CATALOG = {
    "03": ("GC1-DANIEL ALVARADO", "Vendedores"),
    "04": ("ROXANA VALENCIA", "Vendedores"),
    "05": ("GRACIELA SANTANDER", "Vendedores"),
    "06": ("CLAUDIA LOPEZ", "Vendedores"),
    "07": ("LORENA OPAZO", "Vendedores"),
    "08": ("MARIO BRITO", "Vendedores"),
    "09": ("XIMENA CROVETTO", "Vendedores"),
    "11": ("CAROLINA CROCKETT", "Vendedores"),
    "12": ("JOSE GONZALEZ", "Vendedores"),
    "16": ("MATIAS CHOMALI", "Vendedores"),
    "30": ("VENDEDOR ECOMMERS B2C", "Ecommerce / Marketplace"),
    "31": ("VENDEDOR ECOMMERS NOLK", "Ecommerce / Marketplace"),
    "32": ("VENDEDOR ECOMMERS", "Ecommerce / Marketplace"),
    "34": ("MKP MERCADO LIBRE", "Ecommerce / Marketplace"),
    "35": ("MKP - PARIS", "Ecommerce / Marketplace"),
    "43": ("SEBASTIAN ROCCO", "Vendedores"),
    "44": ("MACARENA DE LA ORDEN", "Vendedores"),
    "45": ("MARIELY ROSALES", "Vendedores"),
    "46": ("MELANY VARGAS", "Vendedores"),
    "47": ("MARIA BERNARD", "Vendedores"),
    "48": ("EURO QUIÑONEZ", "Vendedores"),
    "49": ("FRANCISCO PEREZ", "Vendedores"),
    "50": ("GINO MATIUS", "Vendedores"),
    "51": ("NELSON SAN MARTIN", "Vendedores"),
    "54": ("JOHANA OBREQUE", "Vendedores"),
    "60": ("JOSE LUIS ROLLANO", "Vendedores"),
    "70": ("ANDRES ESPINOZA", "Vendedores"),
}


def _norm_text(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("_", " ")
        .replace("-", " ")
    )


def _seller_key(value):
    raw = str(value or "").strip()
    norm = _norm_text(raw)

    # Primero intenta leer código al inicio o valor numérico.
    raw_code = raw.split(".")[0] if raw.replace(".", "", 1).isdigit() else raw
    raw_code = raw_code.zfill(2) if raw_code.isdigit() and len(raw_code) <= 2 else raw_code

    if raw_code in SELLER_CATALOG:
        return raw_code

    for code, (name, _) in SELLER_CATALOG.items():
        if raw == code or raw.startswith(code + " ") or raw.startswith(code + "-"):
            return code
        nname = _norm_text(name)
        if norm == nname or (nname and nname in norm):
            return code

    return None


def _prepare_sellers(df):
    out = df.copy()
    if "Vendedor" not in out.columns:
        out["_VendedorCodigo"] = None
        out["_VendedorNombre"] = "Sin vendedor"
        out["_VendedorGrupo"] = "Otros"
        return out

    out["_VendedorCodigo"] = out["Vendedor"].map(_seller_key)
    out["_VendedorNombre"] = out["_VendedorCodigo"].map(
        lambda c: SELLER_CATALOG[c][0] if c in SELLER_CATALOG else None
    )
    out["_VendedorGrupo"] = out["_VendedorCodigo"].map(
        lambda c: SELLER_CATALOG[c][1] if c in SELLER_CATALOG else None
    )
    return out


def _find_column(columns, candidates):
    normalized = {_norm_text(c): c for c in columns}
    for candidate in candidates:
        key = _norm_text(candidate)
        if key in normalized:
            return normalized[key]
    return None


def _signed_amount(df, no_vat=False):
    if df.empty:
        return pd.Series(dtype="float64")

    amount = pd.to_numeric(df["VentaMonto_num"], errors="coerce").fillna(0).abs()
    if no_vat:
        amount = amount / (1 + VAT_RATE)

    sign = df["Grupo comercial"].map(
        {"Factura": 1, "Boleta": 1, "Nota de crédito": -1}
    ).fillna(0)
    return amount * sign


def _group_amount(df, group, no_vat=False):
    part = df[df["Grupo comercial"].eq(group)]
    if part.empty:
        return 0.0
    amount = pd.to_numeric(part["VentaMonto_num"], errors="coerce").fillna(0).abs()
    if no_vat:
        amount = amount / (1 + VAT_RATE)
    return float(amount.sum())


def _pct_change(current, previous):
    current = float(current or 0)
    previous = float(previous or 0)
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return ((current - previous) / abs(previous)) * 100


def _fmt_pct(value, signed=True):
    if pd.isna(value):
        value = 0
    text = f"{value:+.1f}%" if signed else f"{value:.1f}%"
    return text.replace(".", ",")


def _safe_period(value, fallback_start, fallback_end):
    if isinstance(value, (tuple, list)):
        if len(value) >= 2:
            return value[0], value[1]
        if len(value) == 1:
            return value[0], value[0]
        return fallback_start, fallback_end
    if isinstance(value, (date, pd.Timestamp)):
        return value, value
    return fallback_start, fallback_end


def _previous_period(start_date, end_date):
    start_ts = pd.Timestamp(start_date).normalize()
    end_ts = pd.Timestamp(end_date).normalize()
    days = max((end_ts - start_ts).days + 1, 1)
    prev_end = start_ts - pd.Timedelta(days=1)
    prev_start = prev_end - pd.Timedelta(days=days - 1)
    return prev_start.date(), prev_end.date()


def _date_filter(df, start_date, end_date):
    if df.empty:
        return df.copy()
    dates = df["Fecha_dt"].dt.date
    return df[(dates >= start_date) & (dates <= end_date)].copy()


def _metrics(df, no_vat, client_col):
    totals = calculate_commercial_totals(df, VAT_RATE)
    net = float(totals["venta_neta_sin_iva"] if no_vat else totals["venta_neta_con_iva"])
    gross = float(totals["ventas_brutas_sin_iva"] if no_vat else totals["ventas_brutas_con_iva"])
    credits = float(totals["notas_credito_sin_iva"] if no_vat else totals["notas_credito_con_iva"])

    sale_docs = df[df["Grupo comercial"].isin(["Factura", "Boleta"])]
    docs = int(sale_docs["Numero"].nunique()) if "Numero" in sale_docs.columns else int(len(sale_docs))

    if client_col and client_col in sale_docs.columns:
        clients = int(
            sale_docs[client_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )
    else:
        clients = 0

    ticket = gross / docs if docs else 0.0

    return {
        "net": net,
        "gross": gross,
        "credits": credits,
        "docs": docs,
        "clients": clients,
        "ticket": ticket,
    }


def _kpi_card(icon, label, value, variation, icon_class="green", invert=False):
    good = variation <= 0 if invert else variation >= 0
    trend_class = "trend-up" if good else "trend-down"
    arrow = "▲" if variation >= 0 else "▼"
    return f"""
    <div class="re-kpi">
      <div class="re-kpi-top">
        <div class="re-icon {icon_class}">{icon}</div>
        <div class="re-kpi-copy">
          <div class="re-kpi-label">{html.escape(label)}</div>
          <div class="re-kpi-value">{html.escape(str(value))}</div>
        </div>
      </div>
      <div class="re-kpi-foot">
        <span>vs período anterior</span>
        <strong class="{trend_class}">{arrow} {_fmt_pct(abs(variation), signed=False)}</strong>
      </div>
    </div>
    """


def _client_table(df, no_vat, client_col, legal_col):
    if df.empty or not client_col:
        return pd.DataFrame(columns=["Cliente", "Venta neta"])

    work = df.copy()
    work["_VentaNeta"] = _signed_amount(work, no_vat)

    group_cols = [c for c in [legal_col, client_col] if c and c in work.columns]
    if not group_cols:
        return pd.DataFrame(columns=["Cliente", "Venta neta"])

    out = (
        work.groupby(group_cols, dropna=False)["_VentaNeta"]
        .sum()
        .reset_index()
        .sort_values("_VentaNeta", ascending=False)
    )

    if client_col in out.columns:
        out["Cliente"] = out[client_col].fillna("Sin razón social").astype(str)
    elif legal_col in out.columns:
        out["Cliente"] = out[legal_col].fillna("Sin cliente").astype(str)

    out["Venta neta"] = out["_VentaNeta"]
    return out[["Cliente", "Venta neta"]]



def _document_detail(df, no_vat, client_col, legal_col):
    """Una fila por documento de venta, lista para consulta/búsqueda."""
    if df.empty:
        return pd.DataFrame(columns=["Fecha", "Documento", "Tipo", "Código cliente", "Cliente", "Venta neta"])

    work = df[df["Grupo comercial"].isin(["Factura", "Boleta"])].copy()
    if work.empty:
        return pd.DataFrame(columns=["Fecha", "Documento", "Tipo", "Código cliente", "Cliente", "Venta neta"])

    work["_VentaNeta"] = _signed_amount(work, no_vat)

    group_cols = [c for c in ["Fecha_dt", "Numero", "TipoDocto", "Grupo comercial"] if c in work.columns]
    agg = {"_VentaNeta": "sum"}
    if legal_col and legal_col in work.columns:
        agg[legal_col] = "first"
    if client_col and client_col in work.columns:
        agg[client_col] = "first"

    out = work.groupby(group_cols, dropna=False).agg(agg).reset_index()
    out = out.sort_values("Fecha_dt", ascending=False)

    result = pd.DataFrame()
    result["Fecha"] = pd.to_datetime(out["Fecha_dt"], errors="coerce").dt.strftime("%d-%m-%Y")
    result["Documento"] = out["Numero"].fillna("").astype(str) if "Numero" in out.columns else ""
    result["Tipo"] = (
        out["TipoDocto"].fillna("").astype(str)
        if "TipoDocto" in out.columns
        else out["Grupo comercial"].fillna("").astype(str)
    )
    result["Código cliente"] = (
        out[legal_col].fillna("").astype(str)
        if legal_col and legal_col in out.columns
        else ""
    )
    result["Cliente"] = (
        out[client_col].fillna("").astype(str)
        if client_col and client_col in out.columns
        else ""
    )
    result["Venta neta"] = out["_VentaNeta"].round(0).astype(float)
    return result


def _client_detail(df, no_vat, client_col, legal_col):
    """Resumen por cliente con cantidad de documentos y venta neta."""
    if df.empty:
        return pd.DataFrame(columns=["Código cliente", "Cliente", "Documentos", "Venta neta"])

    work = df[df["Grupo comercial"].isin(["Factura", "Boleta", "Nota de crédito"])].copy()
    if work.empty:
        return pd.DataFrame(columns=["Código cliente", "Cliente", "Documentos", "Venta neta"])

    work["_VentaNeta"] = _signed_amount(work, no_vat)

    group_cols = [c for c in [legal_col, client_col] if c and c in work.columns]
    if not group_cols:
        return pd.DataFrame(columns=["Código cliente", "Cliente", "Documentos", "Venta neta"])

    agg = {"_VentaNeta": "sum"}
    if "Numero" in work.columns:
        agg["Numero"] = pd.Series.nunique

    out = work.groupby(group_cols, dropna=False).agg(agg).reset_index()
    out = out.sort_values("_VentaNeta", ascending=False)

    result = pd.DataFrame()
    result["Código cliente"] = (
        out[legal_col].fillna("").astype(str)
        if legal_col and legal_col in out.columns
        else ""
    )
    result["Cliente"] = (
        out[client_col].fillna("Sin razón social").astype(str)
        if client_col and client_col in out.columns
        else "Sin cliente"
    )
    result["Documentos"] = out["Numero"].fillna(0).astype(int) if "Numero" in out.columns else 0
    result["Venta neta"] = out["_VentaNeta"].round(0).astype(float)
    return result


def _credit_detail(df, no_vat, client_col, legal_col):
    """Una fila por nota de crédito para consulta/búsqueda."""
    if df.empty:
        return pd.DataFrame(columns=["Fecha", "Documento", "Código cliente", "Cliente", "Monto NC"])

    work = df[df["Grupo comercial"].eq("Nota de crédito")].copy()
    if work.empty:
        return pd.DataFrame(columns=["Fecha", "Documento", "Código cliente", "Cliente", "Monto NC"])

    work["_MontoNC"] = pd.to_numeric(work["VentaMonto_num"], errors="coerce").fillna(0).abs()
    if no_vat:
        work["_MontoNC"] = work["_MontoNC"] / (1 + VAT_RATE)

    group_cols = [c for c in ["Fecha_dt", "Numero", "TipoDocto"] if c in work.columns]
    agg = {"_MontoNC": "sum"}
    if legal_col and legal_col in work.columns:
        agg[legal_col] = "first"
    if client_col and client_col in work.columns:
        agg[client_col] = "first"

    out = work.groupby(group_cols, dropna=False).agg(agg).reset_index()
    out = out.sort_values("Fecha_dt", ascending=False)

    result = pd.DataFrame()
    result["Fecha"] = pd.to_datetime(out["Fecha_dt"], errors="coerce").dt.strftime("%d-%m-%Y")
    result["Documento"] = out["Numero"].fillna("").astype(str) if "Numero" in out.columns else ""
    result["Código cliente"] = (
        out[legal_col].fillna("").astype(str)
        if legal_col and legal_col in out.columns
        else ""
    )
    result["Cliente"] = (
        out[client_col].fillna("").astype(str)
        if client_col and client_col in out.columns
        else ""
    )
    result["Monto NC"] = out["_MontoNC"].round(0).astype(float)
    return result


def _search_table(df, query):
    """Búsqueda libre en todas las columnas visibles."""
    if df.empty or not str(query or "").strip():
        return df

    q = str(query).strip().lower()
    mask = pd.Series(False, index=df.index)
    for col in df.columns:
        mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(q, regex=False)
    return df[mask].copy()


def _latest_sales(df, no_vat, client_col):
    if df.empty:
        return pd.DataFrame(columns=["Fecha", "Documento", "Tipo", "Cliente", "Monto Bruto", "Notas de Crédito", "Venta Neta"])

    work = df.copy()
    work["_MontoAbs"] = pd.to_numeric(work["VentaMonto_num"], errors="coerce").fillna(0).abs()
    if no_vat:
        work["_MontoAbs"] = work["_MontoAbs"] / (1 + VAT_RATE)

    work["_VentaNeta"] = _signed_amount(work, no_vat)
    work["_Bruto"] = work["_MontoAbs"].where(work["Grupo comercial"].isin(["Factura", "Boleta"]), 0)
    work["_NC"] = work["_MontoAbs"].where(work["Grupo comercial"].eq("Nota de crédito"), 0)

    # Una fila por documento para evitar duplicación visual por líneas de detalle.
    group_cols = [c for c in ["Fecha_dt", "Numero", "TipoDocto", "Grupo comercial"] if c in work.columns]
    agg = {"_Bruto": "sum", "_NC": "sum", "_VentaNeta": "sum"}
    if client_col and client_col in work.columns:
        agg[client_col] = "first"

    out = work.groupby(group_cols, dropna=False).agg(agg).reset_index()
    out = out.sort_values("Fecha_dt", ascending=False).head(8)

    result = pd.DataFrame()
    result["Fecha"] = out["Fecha_dt"].dt.strftime("%d/%m/%Y")
    result["Documento"] = out["Numero"].astype(str) if "Numero" in out.columns else ""
    result["Tipo"] = out["Grupo comercial"].astype(str)
    result["Cliente"] = out[client_col].fillna("").astype(str) if client_col and client_col in out.columns else ""
    result["Monto Bruto"] = out["_Bruto"]
    result["Notas de Crédito"] = out["_NC"]
    result["Venta Neta"] = out["_VentaNeta"]
    return result


def render(ctx):
    st.markdown(
        """
        <style>
        .block-container{
            max-width:1600px;
            padding-top:1.25rem;
            padding-bottom:2rem;
        }

        /* Cabecera */
        .re-head{
            display:flex;
            justify-content:space-between;
            align-items:flex-start;
            gap:18px;
            margin-bottom:8px;
        }
        .re-title{
            font-size:31px;
            font-weight:900;
            letter-spacing:-.035em;
            color:#101218;
            line-height:1.05;
        }
        .re-sub{
            margin-top:7px;
            color:#374151;
            font-size:13px;
            font-weight:600;
        }

        /* Barra informativa */
        .re-info{
            background:#fff;
            border:1px solid #e6e9ef;
            border-radius:10px;
            padding:10px 14px;
            color:#4b5563;
            font-size:11px;
            margin:10px 0 12px;
            box-shadow:0 2px 10px rgba(17,24,39,.025);
        }

        /* Ajustes de controles */
        div[data-testid="stSelectbox"] label,
        div[data-testid="stDateInput"] label,
        div[data-testid="stNumberInput"] label,
        div[data-testid="stMultiSelect"] label{
            color:#262b34 !important;
            font-size:11px !important;
            font-weight:700 !important;
        }
        div[data-baseweb="select"] > div,
        div[data-testid="stDateInput"] input,
        div[data-testid="stNumberInput"] input{
            min-height:45px;
            border-radius:9px !important;
        }
        div[data-testid="stDownloadButton"] button,
        div[data-testid="stButton"] button{
            min-height:45px;
            border-radius:9px;
            border:1px solid #d7dce4;
            background:#fff;
            color:#111827;
            font-weight:700;
        }

        /* KPI */
        .re-kpi-grid{
            display:grid;
            grid-template-columns:repeat(5,minmax(0,1fr));
            gap:12px;
            margin:12px 0;
        }
        .re-kpi{
            background:#fff;
            border:1px solid #e3e7ed;
            border-radius:12px;
            padding:17px 17px 13px;
            min-height:120px;
            box-shadow:0 3px 14px rgba(17,24,39,.035);
        }
        .re-kpi-top{
            display:flex;
            gap:13px;
            align-items:center;
        }
        .re-icon{
            width:44px;
            height:44px;
            min-width:44px;
            border-radius:50%;
            display:flex;
            align-items:center;
            justify-content:center;
            font-size:21px;
            font-weight:900;
        }
        .re-icon.green{background:#edf8ef;color:#14912c;}
        .re-icon.blue{background:#eef4ff;color:#2266dc;}
        .re-icon.purple{background:#f3efff;color:#7440d8;}
        .re-icon.yellow{background:#fff8e6;color:#efad00;}
        .re-icon.red{background:#fff0f0;color:#de2f2f;}
        .re-kpi-copy{min-width:0;}
        .re-kpi-label{
            color:#344054;
            font-size:10px;
            font-weight:800;
            text-transform:uppercase;
            letter-spacing:.02em;
        }
        .re-kpi-value{
            color:#101218;
            font-size:23px;
            line-height:1.15;
            font-weight:900;
            margin-top:7px;
            white-space:nowrap;
        }
        .re-kpi-foot{
            display:flex;
            justify-content:flex-end;
            gap:8px;
            align-items:center;
            margin-top:12px;
            font-size:9.5px;
            color:#667085;
        }
        .trend-up{color:#159447;}
        .trend-down{color:#d92d20;}

        /* Botones de consulta bajo KPIs */
        .st-key-re_open_docs button,
        .st-key-re_open_clients button,
        .st-key-re_open_nc button{
            min-height:34px !important;
            height:34px !important;
            border-radius:8px !important;
            font-size:11px !important;
            font-weight:750 !important;
            box-shadow:none !important;
            margin-top:-5px !important;
        }
        .st-key-re_open_docs button{
            background:#f4f7ff !important;
            border-color:#dbe5ff !important;
            color:#225fc8 !important;
        }
        .st-key-re_open_clients button{
            background:#f7f4ff !important;
            border-color:#e5dcff !important;
            color:#6840bd !important;
        }
        .st-key-re_open_nc button{
            background:#fff5f5 !important;
            border-color:#ffdada !important;
            color:#c92a2a !important;
        }
        .re-detail-summary{
            display:flex;
            gap:10px;
            flex-wrap:wrap;
            margin:4px 0 10px;
        }
        .re-detail-pill{
            background:#f7f8fa;
            border:1px solid #e5e8ee;
            border-radius:999px;
            padding:5px 10px;
            color:#475467;
            font-size:10px;
            font-weight:700;
        }

        /* Tarjetas de sección */
        .re-card-title{
            color:#151820;
            font-size:13px;
            font-weight:850;
            margin-bottom:6px;
        }
        .re-card-sub{
            color:#667085;
            font-size:10px;
            margin-bottom:8px;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]{
            border-color:#e3e7ed !important;
            border-radius:12px !important;
            box-shadow:0 3px 14px rgba(17,24,39,.025);
            background:#fff;
        }

        /* Tabla top clientes en HTML */
        .re-client-head, .re-client-row{
            display:grid;
            grid-template-columns:34px 1fr auto;
            gap:8px;
            align-items:center;
        }
        .re-client-head{
            color:#667085;
            font-size:9.5px;
            padding:7px 4px;
            border-bottom:1px solid #e9edf2;
        }
        .re-client-row{
            padding:10px 4px;
            border-bottom:1px solid #edf0f4;
            font-size:10.5px;
            color:#20242c;
        }
        .re-client-row:last-child{border-bottom:none;}
        .re-client-rank{color:#475467;}
        .re-client-name{
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
        }
        .re-client-value{font-weight:800;}

        /* Ranking */
        .re-rank-head, .re-rank-row{
            display:grid;
            grid-template-columns:32px 1.5fr .8fr .65fr;
            gap:8px;
            align-items:center;
        }
        .re-rank-head{
            padding:7px 8px;
            color:#667085;
            font-size:9.5px;
            border-bottom:1px solid #e9edf2;
        }
        .re-rank-row{
            padding:10px 8px;
            border-bottom:1px solid #edf0f4;
            font-size:10.5px;
        }
        .re-rank-row.current{
            background:#fff8dc;
            border-radius:6px;
        }
        .re-rank-name{font-weight:700;}
        .re-rank-value{text-align:right;}
        .re-rank-var{text-align:right;font-weight:800;}
        .re-rank-var.up{color:#159447;}
        .re-rank-var.down{color:#d92d20;}

        /* Meta */
        .re-goal{
            display:grid;
            grid-template-columns:1.15fr 1fr .8fr;
            gap:24px;
            align-items:center;
            background:#fff;
            border:1px solid #e3e7ed;
            border-radius:12px;
            padding:15px 18px;
            margin-top:12px;
            box-shadow:0 3px 14px rgba(17,24,39,.025);
        }
        .re-goal-title{
            font-size:11px;
            color:#3b4250;
        }
        .re-goal-title strong{
            color:#111827;
            font-weight:850;
        }
        .re-goal-track{
            height:9px;
            background:#edf0f4;
            border-radius:999px;
            overflow:hidden;
        }
        .re-goal-fill{
            height:100%;
            background:#f7b500;
            border-radius:999px;
        }
        .re-goal-pct{
            font-size:11px;
            font-weight:850;
            margin-top:6px;
        }
        .re-projection{
            text-align:right;
            color:#475467;
            font-size:11px;
        }
        .re-projection strong{color:#14823b;}

        div[data-testid="stDataFrame"]{
            border:1px solid #e7eaf0;
            border-radius:9px;
            overflow:hidden;
        }

        @media(max-width:1200px){
            .re-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
            .re-goal{grid-template-columns:1fr;}
            .re-projection{text-align:left;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    df = ctx.get("sales_df")

    render_html(
        """
        <div class="re-head">
          <div>
            <div class="re-title">RESUMEN EJECUTIVO</div>
            <div class="re-sub">Desempeño de ventas</div>
          </div>
        </div>
        """
    )

    if df is None or df.empty:
        st.info("Carga ERP Ventas desde Plantillas para visualizar el desempeño comercial.")
        return

    required = {"Grupo comercial", "Fecha_dt", "VentaMonto_num"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        st.error(f"Faltan columnas requeridas en ERP Ventas: {', '.join(missing)}")
        return

    base = df[df["Grupo comercial"].isin(VALID_GROUPS)].copy()
    base = _prepare_sellers(base)
    base = base[base["_VendedorCodigo"].notna()].copy()

    if base.empty:
        st.warning("No hay ventas asociadas a los vendedores/canales configurados.")
        return

    legal_col = _find_column(
        base.columns,
        ["CodigoLegal", "Código legal", "Codigo legal", "RUT cliente", "Rut cliente", "RUT", "Rut"],
    )
    client_col = _find_column(
        base.columns,
        ["RazonSocial", "Razón social", "Razon social", "Nombre cliente", "Nombre Cliente"],
    )
    if legal_col and client_col and legal_col == client_col:
        legal_col = None

    # Mes por defecto: el más reciente disponible.
    months = available_months(base, "Fecha_dt")
    if not months:
        st.warning("No hay fechas válidas en ERP Ventas.")
        return

    month_labels = [month_label_es(m) for m in months]
    month_map = dict(zip(month_labels, months))

    present_codes = set(base["_VendedorCodigo"].dropna().astype(str))
    seller_options = [
        (group, code, name)
        for code, (name, group) in SELLER_CATALOG.items()
        if code in present_codes
    ]

    # ------------------------- filtros superiores -------------------------
    f1, f2, f3, f4 = st.columns([1.35, 1.35, 1.0, .72], gap="small")

    with f1:
        seller_group = st.selectbox(
            "Tipo",
            ["Todos", "Vendedores", "Ecommerce / Marketplace"],
            key="re_group_v900",
        )
        scoped = [
            (g, c, n) for g, c, n in seller_options
            if seller_group == "Todos" or g == seller_group
        ]
        seller_labels = [f"{c} · {n}" for _, c, n in scoped]
        selected_label = st.selectbox(
            "Vendedor",
            ["Todos"] + seller_labels,
            key="re_seller_v900",
        )

    with f2:
        month_label = st.selectbox(
            "Mes base",
            month_labels,
            index=0,
            key="re_month_v900",
        )
        selected_month = month_map[month_label]
        month_start, month_end = month_bounds(selected_month)

        month_rows = base[
            (base["Fecha_dt"].dt.date >= month_start)
            & (base["Fecha_dt"].dt.date <= month_end)
        ]
        max_real = month_rows["Fecha_dt"].max().date() if not month_rows.empty else month_end
        default_end = min(month_end, max_real)

        # El período debe representar el mes calendario completo seleccionado,
        # aunque el ERP no tenga movimientos en los primeros o últimos días.
        # Ej.: agosto siempre debe permitir 01/08 al 31/08 aunque la primera
        # venta disponible sea del 03/08.
        period_value = st.date_input(
            "Período",
            value=(month_start, month_end),
            min_value=month_start,
            max_value=month_end,
            key="re_period_v960",
        )

    with f3:
        compare_previous = st.toggle(
            "Comparar período anterior",
            value=True,
            key="re_compare_v900",
        )
        no_vat = st.selectbox(
            "Base",
            ["Con IVA", "Sin IVA"],
            key="re_base_v900",
        ) == "Sin IVA"

    start_date, end_date = _safe_period(period_value, month_start, default_end)

    selected_code = None
    if selected_label != "Todos":
        selected_code = selected_label.split(" · ", 1)[0]

    work = base.copy()
    if seller_group != "Todos":
        work = work[work["_VendedorGrupo"].eq(seller_group)].copy()
    if selected_code:
        work = work[work["_VendedorCodigo"].eq(selected_code)].copy()

    current = _date_filter(work, start_date, end_date)
    prev_start, prev_end = _previous_period(start_date, end_date)
    previous = _date_filter(work, prev_start, prev_end)

    # Exportación respeta todos los filtros.
    with f4:
        st.markdown("<div style='height:17px'></div>", unsafe_allow_html=True)
        export_df = current.copy()
        csv = export_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "⇩ Exportar",
            data=csv,
            file_name=f"resumen_ventas_{start_date}_{end_date}.csv",
            mime="text/csv",
            width="stretch",
        )

    render_html(
        "<div class='re-info'>ⓘ Los valores de venta neta consideran: "
        "<strong>Facturas + Boletas − Notas de crédito.</strong></div>"
    )

    cur = _metrics(current, no_vat, client_col)
    prv = _metrics(previous, no_vat, client_col)

    var_net = _pct_change(cur["net"], prv["net"]) if compare_previous else 0
    var_docs = _pct_change(cur["docs"], prv["docs"]) if compare_previous else 0
    var_clients = _pct_change(cur["clients"], prv["clients"]) if compare_previous else 0
    var_ticket = _pct_change(cur["ticket"], prv["ticket"]) if compare_previous else 0
    var_nc = _pct_change(cur["credits"], prv["credits"]) if compare_previous else 0

    kpis = "".join(
        [
            _kpi_card("$", "Venta neta", format_clp(cur["net"]), var_net, "green"),
            _kpi_card("▤", "Documentos", f'{cur["docs"]:,}'.replace(",", "."), var_docs, "blue"),
            _kpi_card("♙", "Clientes atendidos", f'{cur["clients"]:,}'.replace(",", "."), var_clients, "purple"),
            _kpi_card("▱", "Ticket promedio", format_clp(cur["ticket"]), var_ticket, "yellow"),
            _kpi_card("↶", "Notas de crédito", format_clp(cur["credits"]), var_nc, "red", invert=True),
        ]
    )
    render_html(f"<div class='re-kpi-grid'>{kpis}</div>")

    # Acciones consultables de los KPI.
    if "re_detail_panel" not in st.session_state:
        st.session_state["re_detail_panel"] = None

    a1, a2, a3, a4, a5 = st.columns(5, gap="small")
    with a2:
        if st.button("⌕ Consultar documentos", width="stretch", key="re_open_docs"):
            st.session_state["re_detail_panel"] = (
                None if st.session_state["re_detail_panel"] == "docs" else "docs"
            )
    with a3:
        if st.button("⌕ Consultar clientes", width="stretch", key="re_open_clients"):
            st.session_state["re_detail_panel"] = (
                None if st.session_state["re_detail_panel"] == "clients" else "clients"
            )
    with a5:
        if st.button("⌕ Consultar NC", width="stretch", key="re_open_nc"):
            st.session_state["re_detail_panel"] = (
                None if st.session_state["re_detail_panel"] == "nc" else "nc"
            )

    detail_panel = st.session_state.get("re_detail_panel")

    if detail_panel:
        with st.container(border=True):
            head_left, head_right = st.columns([5.3, .7])
            with head_right:
                if st.button("✕", help="Cerrar detalle", width="stretch", key="re_close_detail"):
                    st.session_state["re_detail_panel"] = None
                    st.rerun()

            if detail_panel == "docs":
                all_detail = _document_detail(current, no_vat, client_col, legal_col)

                with head_left:
                    render_html(
                        "<div class='re-card-title'>Detalle de documentos</div>"
                        "<div class='re-card-sub'>Facturas y boletas del período y vendedor seleccionados</div>"
                    )

                s1, s2 = st.columns([3.7, 1.3], gap="small")
                with s1:
                    q = st.text_input(
                        "Buscar",
                        placeholder="Número, cliente, código o tipo de documento...",
                        key="re_search_docs",
                        label_visibility="collapsed",
                    )
                with s2:
                    doc_type = st.selectbox(
                        "Tipo",
                        ["Todos", "Factura", "Boleta"],
                        key="re_doc_type_detail",
                        label_visibility="collapsed",
                    )

                detail = all_detail
                if doc_type != "Todos" and not detail.empty:
                    detail = detail[
                        detail["Tipo"].astype(str).str.contains(doc_type, case=False, na=False)
                    ]
                detail = _search_table(detail, q)

                total_detail = float(pd.to_numeric(detail.get("Venta neta", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
                render_html(
                    "<div class='re-detail-summary'>"
                    f"<span class='re-detail-pill'>{len(detail):,} documentos</span>"
                    f"<span class='re-detail-pill'>Venta listada: {html.escape(format_clp(total_detail))}</span>"
                    "</div>".replace(",", ".")
                )

                st.dataframe(
                    detail,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Venta neta": st.column_config.NumberColumn("Venta neta", format="$ %.0f"),
                    },
                )
                st.download_button(
                    "⬇ Exportar documentos",
                    data=detail.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"documentos_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    key="re_export_docs",
                )

            elif detail_panel == "clients":
                all_detail = _client_detail(current, no_vat, client_col, legal_col)

                with head_left:
                    render_html(
                        "<div class='re-card-title'>Clientes atendidos</div>"
                        "<div class='re-card-sub'>Consulta comercial de clientes con movimientos en el período</div>"
                    )

                q = st.text_input(
                    "Buscar",
                    placeholder="Razón social o CódigoLegal...",
                    key="re_search_clients",
                    label_visibility="collapsed",
                )
                detail = _search_table(all_detail, q)

                total_detail = float(pd.to_numeric(detail.get("Venta neta", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
                render_html(
                    "<div class='re-detail-summary'>"
                    f"<span class='re-detail-pill'>{len(detail):,} clientes</span>"
                    f"<span class='re-detail-pill'>Venta neta: {html.escape(format_clp(total_detail))}</span>"
                    "</div>".replace(",", ".")
                )

                st.dataframe(
                    detail,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Documentos": st.column_config.NumberColumn("Documentos", format="%d"),
                        "Venta neta": st.column_config.NumberColumn("Venta neta", format="$ %.0f"),
                    },
                )
                st.download_button(
                    "⬇ Exportar clientes",
                    data=detail.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"clientes_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    key="re_export_clients",
                )

            elif detail_panel == "nc":
                all_detail = _credit_detail(current, no_vat, client_col, legal_col)

                with head_left:
                    render_html(
                        "<div class='re-card-title'>Notas de crédito</div>"
                        "<div class='re-card-sub'>Detalle de devoluciones y ajustes del período seleccionado</div>"
                    )

                q = st.text_input(
                    "Buscar",
                    placeholder="Número de NC, razón social o CódigoLegal...",
                    key="re_search_nc",
                    label_visibility="collapsed",
                )
                detail = _search_table(all_detail, q)

                total_detail = float(pd.to_numeric(detail.get("Monto NC", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
                render_html(
                    "<div class='re-detail-summary'>"
                    f"<span class='re-detail-pill'>{len(detail):,} notas de crédito</span>"
                    f"<span class='re-detail-pill'>Monto listado: {html.escape(format_clp(total_detail))}</span>"
                    "</div>".replace(",", ".")
                )

                st.dataframe(
                    detail,
                    hide_index=True,
                    width="stretch",
                    column_config={
                        "Monto NC": st.column_config.NumberColumn("Monto NC", format="$ %.0f"),
                    },
                )
                st.download_button(
                    "⬇ Exportar notas de crédito",
                    data=detail.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"notas_credito_{start_date}_{end_date}.csv",
                    mime="text/csv",
                    key="re_export_nc",
                )

    # ------------------------- bloque central -------------------------
    left, middle, right = st.columns([1.45, .92, 1.0], gap="small")

    # Evolución
    with left:
        with st.container(border=True):
            render_html(
                "<div class='re-card-title'>Evolución de Ventas Netas (CLP)</div>"
                "<div class='re-card-sub'>Este período vs período anterior</div>"
            )

            current_daily = current.copy()
            current_daily["_VentaNeta"] = _signed_amount(current_daily, no_vat)
            current_daily["Día"] = current_daily["Fecha_dt"].dt.normalize()
            current_daily = (
                current_daily.groupby("Día", as_index=False)["_VentaNeta"]
                .sum()
                .rename(columns={"_VentaNeta": "Venta"})
            )
            current_daily["Serie"] = "Este período"
            current_daily["Índice"] = range(1, len(current_daily) + 1)

            prev_daily = previous.copy()
            prev_daily["_VentaNeta"] = _signed_amount(prev_daily, no_vat)
            prev_daily["Día"] = prev_daily["Fecha_dt"].dt.normalize()
            prev_daily = (
                prev_daily.groupby("Día", as_index=False)["_VentaNeta"]
                .sum()
                .rename(columns={"_VentaNeta": "Venta"})
            )
            prev_daily["Serie"] = "Período anterior"
            prev_daily["Índice"] = range(1, len(prev_daily) + 1)

            if current_daily.empty and prev_daily.empty:
                st.info("Sin movimientos para graficar.")
            else:
                chart_data = current_daily
                if compare_previous and not prev_daily.empty:
                    chart_data = pd.concat([current_daily, prev_daily], ignore_index=True)

                base_chart = (
                    alt.Chart(chart_data)
                    .encode(
                        x=alt.X("Índice:Q", title=None, axis=alt.Axis(labels=False, ticks=False)),
                        y=alt.Y(
                            "Venta:Q",
                            title=None,
                            axis=alt.Axis(format="~s", grid=True, gridColor="#edf0f4"),
                        ),
                        color=alt.Color(
                            "Serie:N",
                            title=None,
                            scale=alt.Scale(
                                domain=["Este período", "Período anterior"],
                                range=["#f5b400", "#b8c0cc"],
                            ),
                            legend=alt.Legend(orient="top"),
                        ),
                        tooltip=[
                            alt.Tooltip("Día:T", title="Fecha"),
                            alt.Tooltip("Venta:Q", title="Venta neta", format=",.0f"),
                            alt.Tooltip("Serie:N", title="Serie"),
                        ],
                    )
                )

                line = base_chart.mark_line(strokeWidth=2.3)
                points = (
                    alt.Chart(current_daily)
                    .mark_circle(size=48, color="#f5b400")
                    .encode(
                        x=alt.X("Índice:Q", title=None, axis=alt.Axis(labels=False, ticks=False)),
                        y=alt.Y("Venta:Q", title=None),
                        tooltip=[
                            alt.Tooltip("Día:T", title="Fecha"),
                            alt.Tooltip("Venta:Q", title="Venta neta", format=",.0f"),
                        ],
                    )
                )
                st.altair_chart((line + points).properties(height=245), width="stretch")

    # Composición
    with middle:
        with st.container(border=True):
            render_html("<div class='re-card-title'>Ventas Netas por Tipo de Documento</div>")

            inv = _group_amount(current, "Factura", no_vat)
            bol = _group_amount(current, "Boleta", no_vat)
            nc = _group_amount(current, "Nota de crédito", no_vat)

            donut_df = pd.DataFrame(
                {
                    "Tipo": ["Facturas", "Boletas", "Notas de Crédito"],
                    "Monto": [inv, bol, nc],
                }
            )
            donut_df = donut_df[donut_df["Monto"] > 0]

            if donut_df.empty:
                st.info("Sin documentos en el período.")
            else:
                donut = (
                    alt.Chart(donut_df)
                    .mark_arc(innerRadius=58, outerRadius=90)
                    .encode(
                        theta=alt.Theta("Monto:Q"),
                        color=alt.Color(
                            "Tipo:N",
                            scale=alt.Scale(
                                domain=["Facturas", "Boletas", "Notas de Crédito"],
                                range=["#f5b400", "#2e6bdc", "#df3026"],
                            ),
                            legend=None,
                        ),
                        tooltip=[
                            alt.Tooltip("Tipo:N", title="Tipo"),
                            alt.Tooltip("Monto:Q", title="Monto", format=",.0f"),
                        ],
                    )
                    .properties(height=190)
                )
                st.altair_chart(donut, width="stretch")

            total_positive = inv + bol
            inv_pct = inv / total_positive * 100 if total_positive else 0
            bol_pct = bol / total_positive * 100 if total_positive else 0
            nc_pct = nc / total_positive * 100 if total_positive else 0

            render_html(
                f"""
                <div style="font-size:10px;line-height:1.9;color:#303744">
                  <div>🟡 <strong>Facturas</strong> &nbsp; {format_clp(inv)}
                    <span style="float:right">{_fmt_pct(inv_pct, False)}</span></div>
                  <div>🔵 <strong>Boletas</strong> &nbsp; {format_clp(bol)}
                    <span style="float:right">{_fmt_pct(bol_pct, False)}</span></div>
                  <div>🔴 <strong>Notas de Crédito</strong> &nbsp; -{format_clp(nc)}
                    <span style="float:right">-{_fmt_pct(nc_pct, False)}</span></div>
                  <div style="margin-top:10px;padding:8px 9px;background:#fff9e9;border-radius:7px;">
                    Venta neta = Facturas + Boletas - Notas de crédito
                  </div>
                </div>
                """
            )

    # Top clientes
    with right:
        with st.container(border=True):
            render_html("<div class='re-card-title'>Top 5 Clientes por Venta Neta</div>")
            clients = _client_table(current, no_vat, client_col, legal_col).head(5)

            if clients.empty:
                st.info("Sin clientes identificados.")
            else:
                rows = []
                for idx, row in enumerate(clients.itertuples(index=False), start=1):
                    rows.append(
                        f"""
                        <div class="re-client-row">
                          <div class="re-client-rank">{idx}</div>
                          <div class="re-client-name">{html.escape(str(row[0]))}</div>
                          <div class="re-client-value">{format_clp(float(row[1]))}</div>
                        </div>
                        """
                    )
                render_html(
                    """
                    <div class="re-client-head">
                      <div></div><div>Cliente</div><div>Venta Neta (CLP)</div>
                    </div>
                    """
                    + "".join(rows)
                )

    # ------------------------- bloque inferior -------------------------
    lower_left, lower_right = st.columns([1.55, 1.0], gap="small")

    with lower_left:
        with st.container(border=True):
            render_html("<div class='re-card-title'>Últimas Ventas</div>")
            latest = _latest_sales(current, no_vat, client_col)
            if latest.empty:
                st.info("Sin ventas para mostrar.")
            else:
                st.dataframe(
                    latest,
                    hide_index=True,
                    width="stretch",
                    height=270,
                    column_config={
                        "Monto Bruto": st.column_config.NumberColumn("Monto Bruto", format="$%d"),
                        "Notas de Crédito": st.column_config.NumberColumn("Notas de Crédito", format="$%d"),
                        "Venta Neta": st.column_config.NumberColumn("Venta Neta", format="$%d"),
                    },
                )

    with lower_right:
        with st.container(border=True):
            render_html(
                f"<div class='re-card-title'>Ranking de Vendedores por Venta Neta</div>"
                f"<div class='re-card-sub'>Período: {pd.Timestamp(start_date).strftime('%d/%m/%Y')} - {pd.Timestamp(end_date).strftime('%d/%m/%Y')}</div>"
            )

            # Ranking usa todos los vendedores/canales del grupo seleccionado,
            # aunque arriba haya un vendedor específico elegido.
            rank_scope = base.copy()
            if seller_group != "Todos":
                rank_scope = rank_scope[rank_scope["_VendedorGrupo"].eq(seller_group)].copy()

            rank_cur = _date_filter(rank_scope, start_date, end_date)
            rank_prev = _date_filter(rank_scope, prev_start, prev_end)

            def build_rank(frame):
                if frame.empty:
                    return pd.DataFrame(columns=["_VendedorCodigo", "_VendedorNombre", "Venta"])
                tmp = frame.copy()
                tmp["_Venta"] = _signed_amount(tmp, no_vat)
                return (
                    tmp.groupby(["_VendedorCodigo", "_VendedorNombre"], dropna=False)["_Venta"]
                    .sum()
                    .reset_index()
                    .rename(columns={"_Venta": "Venta"})
                )

            rc = build_rank(rank_cur)
            rp = build_rank(rank_prev).rename(columns={"Venta": "VentaPrev"})
            ranking = rc.merge(rp[["_VendedorCodigo", "VentaPrev"]], on="_VendedorCodigo", how="left")
            ranking["VentaPrev"] = ranking["VentaPrev"].fillna(0)
            ranking["Variacion"] = ranking.apply(
                lambda r: _pct_change(r["Venta"], r["VentaPrev"]), axis=1
            )
            ranking = ranking.sort_values("Venta", ascending=False).head(7).reset_index(drop=True)

            if ranking.empty:
                st.info("Sin vendedores para rankear.")
            else:
                render_html(
                    """
                    <div class="re-rank-head">
                      <div></div><div>Vendedor</div><div style="text-align:right">Venta Neta</div><div style="text-align:right">vs anterior</div>
                    </div>
                    """
                )
                rank_rows = []
                for i, row in ranking.iterrows():
                    is_current = selected_code and row["_VendedorCodigo"] == selected_code
                    cls = "re-rank-row current" if is_current else "re-rank-row"
                    var_cls = "up" if row["Variacion"] >= 0 else "down"
                    arrow = "▲" if row["Variacion"] >= 0 else "▼"
                    rank_rows.append(
                        f"""
                        <div class="{cls}">
                          <div>{i + 1}</div>
                          <div class="re-rank-name">{html.escape(str(row['_VendedorNombre']))}</div>
                          <div class="re-rank-value">{format_clp(float(row['Venta']))}</div>
                          <div class="re-rank-var {var_cls}">{arrow} {_fmt_pct(abs(row['Variacion']), False)}</div>
                        </div>
                        """
                    )
                render_html("".join(rank_rows))

    # ------------------------- seguimiento de meta comercial -------------------------
    st.markdown("### Seguimiento de meta comercial")

    # La meta se ingresa manualmente. No se inventan metas oficiales.
    seller_label_for_goal = selected_label if selected_label != "Todos" else "Equipo seleccionado"
    goal_key = f"re_goal_v960_{str(selected_code or seller_group).replace(' ', '_').replace('/', '_')}"

    goal_col, status_col = st.columns([1.05, 2.95], gap="large")

    with goal_col:
        monthly_goal = st.number_input(
            "Meta mensual (CLP)",
            min_value=0,
            value=int(st.session_state.get(goal_key, 0) or 0),
            step=500000,
            key=goal_key,
            help="Ingresa la meta oficial del vendedor o canal. Se mantiene durante la sesión.",
        )

        st.caption(
            f"Meta aplicada a: **{seller_label_for_goal}**. "
            "Si no existe una meta oficial cargada, déjala en $0."
        )

    # Cálculo de avance y proyección
    net_sales_now = float(cur.get("net", 0) or 0)

    # Para proyectar usamos días calendario transcurridos dentro del mes seleccionado,
    # hasta la última fecha con movimiento disponible dentro del período.
    if not current.empty and "Fecha_dt" in current.columns:
        valid_dates = pd.to_datetime(current["Fecha_dt"], errors="coerce").dropna()
        last_sales_date = valid_dates.max().date() if not valid_dates.empty else start_date
    else:
        last_sales_date = start_date

    effective_date = min(max(last_sales_date, start_date), end_date)
    elapsed_days = max((effective_date - month_start).days + 1, 1)
    total_month_days = max((month_end - month_start).days + 1, 1)

    projected_close = (net_sales_now / elapsed_days) * total_month_days if elapsed_days else 0
    remaining = max(float(monthly_goal) - net_sales_now, 0) if monthly_goal > 0 else 0
    achievement = (net_sales_now / float(monthly_goal) * 100) if monthly_goal > 0 else 0
    projected_achievement = (
        projected_close / float(monthly_goal) * 100
        if monthly_goal > 0 else 0
    )

    days_left = max((month_end - effective_date).days, 0)
    daily_needed = (remaining / days_left) if monthly_goal > 0 and days_left > 0 else 0

    with status_col:
        if monthly_goal > 0:
            progress_value = min(max(achievement / 100, 0), 1)
            st.progress(
                progress_value,
                text=f"{achievement:.1f}% de cumplimiento · {format_clp(net_sales_now)} de {format_clp(monthly_goal)}",
            )

            m1, m2, m3, m4 = st.columns(4, gap="small")
            m1.metric(
                "Falta para la meta",
                format_clp(remaining),
                help="Monto pendiente para alcanzar la meta mensual.",
            )
            m2.metric(
                "Días restantes",
                f"{days_left}",
                help="Días calendario restantes desde la última fecha con movimiento del período.",
            )
            m3.metric(
                "Venta diaria necesaria",
                format_clp(daily_needed) if days_left > 0 else format_clp(remaining),
                help="Promedio diario requerido para alcanzar la meta al cierre de mes.",
            )
            m4.metric(
                "Proyección de cierre",
                format_clp(projected_close),
                delta=f"{projected_achievement:.1f}% de la meta",
                help="Proyección lineal según el ritmo de venta acumulado.",
            )

            if achievement >= 100:
                st.success(
                    f"Meta alcanzada. El avance actual es {achievement:.1f}% "
                    f"y supera la meta en {format_clp(net_sales_now - monthly_goal)}."
                )
            elif projected_close >= monthly_goal:
                st.info(
                    f"Al ritmo actual, la proyección de cierre es {format_clp(projected_close)} "
                    f"({projected_achievement:.1f}% de la meta)."
                )
            else:
                projected_gap = max(monthly_goal - projected_close, 0)
                st.warning(
                    f"Al ritmo actual, la proyección quedaría {format_clp(projected_gap)} "
                    f"bajo la meta. Se requieren aproximadamente {format_clp(daily_needed)} "
                    f"por día durante los {days_left} días restantes."
                )
        else:
            st.info(
                "Ingresa una **meta mensual oficial** para activar el % de cumplimiento, "
                "monto faltante, venta diaria necesaria y proyección de cierre."
            )

