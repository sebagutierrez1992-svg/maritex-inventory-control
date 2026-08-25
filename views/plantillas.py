import streamlit as st
from config.settings import (
    ERP_SALES_FILE, ERP_SALES_META, ERP_STOCK_FILE, ERP_STOCK_META,
)
from services.erp_sales import read_sales_source
from services.erp_stock import read_stock_source
from services.storage import save_source
from services.validation import validate_sales_source, validate_stock_source
from ui.components import page_header
from utils.numbers import format_clp


def render(ctx):
    page_header(
        "Plantillas",
        "Centro único de fuentes ERP y plantillas de marketplaces.",
        "HERRAMIENTAS",
    )

    st.subheader("ERP Stock")
    stock = st.file_uploader(
        "Cargar ERP Stock",
        type=["csv", "xls", "xlsx"],
        key="new_project_stock_upload",
    )
    if stock is not None:
        raw = stock.getvalue()
        df = read_stock_source(raw, stock.name)
        info = validate_stock_source(df)
        save_source(raw, stock.name, ERP_STOCK_FILE, ERP_STOCK_META, info)
        st.success(
            f"ERP Stock válido · {info['rows']:,} filas · {info['sku']:,} SKU"
        )

    st.subheader("ERP Ventas")
    sales = st.file_uploader(
        "Cargar ERP Ventas",
        type=["csv", "xls", "xlsx"],
        key="new_project_sales_upload",
    )
    if sales is not None:
        raw = sales.getvalue()
        df = read_sales_source(raw, sales.name)
        info = validate_sales_source(df)
        save_source(raw, sales.name, ERP_SALES_FILE, ERP_SALES_META, info)
        st.success(
            "ERP Ventas válido · "
            f"{info['commercial_rows']:,} documentos · "
            f"{info['min_date']} → {info['max_date']} · "
            f"{format_clp(info['net_sales_with_vat'])}"
        )

    st.divider()
    st.subheader("Plantillas Marketplace")
    st.caption("Paris y Mercado Libre se migrarán desde la aplicación legacy.")
