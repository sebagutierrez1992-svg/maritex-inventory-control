import streamlit as st
from ui.components import page_header


def render(ctx):
    page_header(
        "Stock General",
        "Consulta y operación sobre la fuente ERP Stock normalizada.",
        "OPERACIÓN",
    )
    stock_df = ctx.get("stock_df")
    if stock_df is None:
        st.info("Carga ERP Stock desde Plantillas.")
        return
    st.dataframe(stock_df, use_container_width=True, hide_index=True)
