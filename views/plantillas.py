
from datetime import datetime
import streamlit as st

from config.settings import ERP_SALES_FILE, ERP_SALES_META, ERP_STOCK_FILE, ERP_STOCK_META, MARKETPLACE_TEMPLATES
from services.erp_sales import read_sales_source
from services.erp_stock import read_stock_source
from services.storage import save_source, load_source
from services.validation import validate_sales_source, validate_stock_source
from ui.components import render_html
from utils.numbers import format_clp


def render(ctx):
    render_html("""
    <div class="gm-page-head">
      <div class="gm-page-title">Plantillas y Fuentes ERP</div>
      <div class="gm-page-subtitle">Centro único para cargar las fuentes de Stock, Ventas y las plantillas de Marketplaces.</div>
    </div>
    <div class="templates-v60-strip"><strong>Flujo de datos:</strong> ERP Stock alimenta Stock General, Métricas de Stock y Marketplaces. ERP Ventas alimenta Métricas Vendedores y Resumen Ejecutivo.</div>
    """)

    render_html('<div class="gm-section-title">Fuentes ERP</div>')
    c1,c2=st.columns(2,gap="medium")
    with c1:
        with st.container(border=True):
            render_html('<div class="templates-v60-card-title">ERP Stock</div><div class="templates-v60-meta">Fuente maestra de inventario para Stock General, Métricas de Stock y Marketplaces.</div>')
            _,meta=load_source(ERP_STOCK_FILE,ERP_STOCK_META)
            if meta:
                st.success(f"✓ Fuente activa: {meta.get('filename','ERP Stock')}")
                render_html(f'<div class="templates-v60-meta">Actualizada: {meta.get("loaded_at","")}</div>')
            else:
                st.warning("Aún no existe una fuente ERP Stock guardada.")
            up=st.file_uploader("Cargar / reemplazar ERP Stock",type=["csv","xls","xlsx"],key="tpl_stock_v617")
            if up is not None:
                try:
                    raw=up.getvalue(); df=read_stock_source(raw,up.name); info=validate_stock_source(df)
                    save_source(raw,up.name,ERP_STOCK_FILE,ERP_STOCK_META,info)
                    st.success(f"✓ ERP Stock actualizado · {info['rows']:,} filas · {info['sku']:,} SKU")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Error cargando ERP Stock: {exc}")

    with c2:
        with st.container(border=True):
            render_html('<div class="templates-v60-card-title">ERP Ventas</div><div class="templates-v60-meta">Fuente comercial para Métricas Vendedores y Resumen Ejecutivo.</div>')
            _,meta=load_source(ERP_SALES_FILE,ERP_SALES_META)
            if meta:
                st.success(f"✓ Fuente activa: {meta.get('filename','ERP Ventas')}")
                render_html(f'<div class="templates-v60-meta">Actualizada: {meta.get("loaded_at","")}</div>')
            else:
                st.warning("Aún no existe una fuente ERP Ventas guardada.")
            up=st.file_uploader("Cargar / reemplazar ERP Ventas",type=["csv","xls","xlsx"],key="tpl_sales_v617")
            if up is not None:
                try:
                    raw=up.getvalue(); df=read_sales_source(raw,up.name); info=validate_sales_source(df)
                    save_source(raw,up.name,ERP_SALES_FILE,ERP_SALES_META,info)
                    st.success(f"✓ ERP Ventas actualizado · {info['commercial_rows']:,} documentos · {info['min_date']} → {info['max_date']} · {format_clp(info['net_sales_with_vat'])}")
                    st.cache_data.clear()
                except Exception as exc:
                    st.error(f"Error cargando ERP Ventas: {exc}")

    render_html('<div class="gm-section-title">Plantillas Marketplaces</div>')
    a,b=st.columns(2,gap="medium")
    for col,(name,path) in zip([a,b],MARKETPLACE_TEMPLATES.items()):
        with col:
            with st.container(border=True):
                render_html(f'<div class="templates-v60-card-title">{name}</div><div class="templates-v60-meta">Plantilla base usada para generar el archivo de actualización.</div>')
                if path.exists():
                    st.success(f"✓ {path.name}")
                    render_html(f'<div class="templates-v60-meta">Actualizada: {datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")}</div>')
                else:
                    st.warning("Plantilla no guardada.")
                up=st.file_uploader(f"Reemplazar plantilla {name}",type=["xlsx"],key=f"tpl_market_v617_{name}")
                if up is not None:
                    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(up.getvalue()); st.success(f"✓ Guardada como {path.name}")
