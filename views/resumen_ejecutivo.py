import streamlit as st
from analytics.sales_metrics import commercial_totals
from ui.components import page_header
from utils.numbers import format_clp


def render(ctx):
    page_header(
        "Resumen Ejecutivo",
        "Performance comercial, cumplimiento y proyección.",
        "ANÁLISIS",
    )
    df = ctx.get("sales_df")
    if df is None:
        st.info("Carga ERP Ventas desde Plantillas.")
        return

    base = st.selectbox(
        "Base de análisis",
        ["Venta final con IVA", "Venta final sin IVA"],
    )

    totals = commercial_totals(df)
    amount = (
        totals["net_without_vat"]
        if base == "Venta final sin IVA"
        else totals["net_with_vat"]
    )

    goal = st.number_input("Meta", min_value=0, value=100_000_000, step=100_000)
    compliance = amount / goal * 100 if goal else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Venta actual", format_clp(amount))
    c2.metric("Meta", format_clp(goal))
    c3.metric("Cumplimiento", f"{compliance:.1f}%")
