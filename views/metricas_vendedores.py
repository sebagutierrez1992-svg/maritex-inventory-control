import streamlit as st
from analytics.sales_metrics import commercial_totals, seller_performance
from ui.components import page_header
from utils.numbers import format_clp


def render(ctx):
    page_header(
        "Métricas Vendedores",
        "Desempeño comercial basado exclusivamente en ERP Ventas.",
        "ANÁLISIS",
    )
    df = ctx.get("sales_df")
    if df is None:
        st.info("Carga ERP Ventas desde Plantillas.")
        return

    totals = commercial_totals(df)
    c1, c2 = st.columns(2)
    c1.metric("Venta neta con IVA", format_clp(totals["net_with_vat"]))
    c2.metric("Venta neta sin IVA", format_clp(totals["net_without_vat"]))

    perf = seller_performance(df, include_vat=True)
    st.dataframe(perf, use_container_width=True, hide_index=True)
