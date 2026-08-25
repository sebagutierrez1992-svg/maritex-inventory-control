import streamlit as st
from analytics.stock_metrics import stock_summary
from ui.components import page_header


def render(ctx):
    page_header(
        "Métricas de Stock",
        "Estado, riesgos y distribución del inventario.",
        "ANÁLISIS",
    )
    df = ctx.get("stock_df")
    if df is None:
        st.info("Carga ERP Stock desde Plantillas.")
        return

    summary = stock_summary(df)
    c1, c2, c3 = st.columns(3)
    c1.metric("SKU", f"{summary['sku_total']:,}")
    c2.metric("Unidades disponibles", f"{summary['units_available']:,}")
    c3.metric("Bodegas", f"{summary['warehouses']:,}")
