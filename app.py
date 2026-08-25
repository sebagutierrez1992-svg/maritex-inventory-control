import streamlit as st

from config.settings import (
    APP_TITLE,
    APP_VERSION,
    BASE_DIR,
    ERP_SALES_FILE,
    ERP_SALES_META,
    ERP_STOCK_FILE,
    ERP_STOCK_META,
)
from services.erp_sales import read_sales_source
from services.erp_stock import read_stock_source
from services.storage import load_source
from ui.styles import apply_styles
from views import (
    marketplaces,
    metricas_stock,
    metricas_vendedores,
    plantillas,
    resumen_ejecutivo,
    stock_general,
)

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles(BASE_DIR / "styles.css")

PAGE_MAP = {
    "Stock General": stock_general.render,
    "Marketplaces": marketplaces.render,
    "Métricas de Stock": metricas_stock.render,
    "Métricas Vendedores": metricas_vendedores.render,
    "Resumen Ejecutivo": resumen_ejecutivo.render,
    "Plantillas": plantillas.render,
}


@st.cache_data(show_spinner=False)
def load_stock_context(raw: bytes, filename: str):
    return read_stock_source(raw, filename)


@st.cache_data(show_spinner=False)
def load_sales_context(raw: bytes, filename: str):
    return read_sales_source(raw, filename)


def build_context():
    stock_raw, stock_meta = load_source(ERP_STOCK_FILE, ERP_STOCK_META)
    sales_raw, sales_meta = load_source(ERP_SALES_FILE, ERP_SALES_META)

    stock_df = None
    sales_df = None

    if stock_raw:
        stock_df = load_stock_context(
            stock_raw,
            (stock_meta or {}).get("filename", "erp_stock.xlsx"),
        )

    if sales_raw:
        sales_df = load_sales_context(
            sales_raw,
            (sales_meta or {}).get("filename", "erp_ventas.xls"),
        )

    return {
        "stock_df": stock_df,
        "stock_meta": stock_meta,
        "sales_df": sales_df,
        "sales_meta": sales_meta,
    }


with st.sidebar:
    st.markdown("## Grupo Maritex")
    st.caption(APP_VERSION)

    page = st.radio(
        "Navegación",
        list(PAGE_MAP),
        label_visibility="collapsed",
    )

ctx = build_context()
PAGE_MAP[page](ctx)
