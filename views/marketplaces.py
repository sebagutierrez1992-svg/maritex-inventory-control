import streamlit as st
from ui.components import page_header


def render(ctx):
    page_header(
        "Marketplaces",
        "Actualización de stock de marketplaces usando ERP Stock.",
        "OPERACIÓN",
    )
    st.info("La lógica completa de Paris y Mercado Libre se migrará desde legacy durante V61.")
