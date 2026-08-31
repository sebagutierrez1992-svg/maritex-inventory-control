import streamlit as st

from analytics.stock_metrics import (
    stock_view,
    consolidate_inventory,
)

from config.settings import (
    APP_TITLE,
    BASE_DIR,
    ERP_SALES_FILE,
    ERP_SALES_META,
    ERP_STOCK_FILE,
    ERP_STOCK_META,
)

from services.erp_sales import read_sales_source
from services.erp_stock import read_stock_source
from services.remote_stock import load_remote_stock
from services.storage import load_source

from ui.components import render_html
from ui.styles import apply_styles

from views import (
    marketplaces,
    metricas_stock,
    metricas_vendedores,
    plantillas,
    resumen_ejecutivo,
    stock_general,
    inicio,
)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_styles(
    BASE_DIR / "styles.css"
)


# ============================================================
# PÁGINAS
# ============================================================

PAGE_MAP = {
    "Inicio": inicio.render,
    "Stock General": stock_general.render,
    "Marketplace": marketplaces.render,
    "Métricas Stock": metricas_stock.render,
    "Métricas Vendedores": metricas_vendedores.render,
    "Resumen Ejecutivo": resumen_ejecutivo.render,
    "Plantillas": plantillas.render,
}


# ============================================================
# CARGA ERP STOCK
# ============================================================

@st.cache_data(
    show_spinner=False,
)
def prepare_stock_context(
    raw: bytes,
    filename: str,
):
    """
    Lee y prepara ERP Stock UNA SOLA VEZ.

    Devuelve:

    raw_df
        ERP Stock procesado por services.erp_stock.

    normalized
        Vista normalizada SKU + Bodega.

    consolidated
        Vista consolidada por SKU.

    De esta forma Stock General, Métricas Stock
    y Marketplaces reutilizan los mismos datos.
    """

    raw_df = read_stock_source(
        raw,
        filename,
    )

    if (
        raw_df is None
        or raw_df.empty
    ):
        return (
            raw_df,
            None,
            None,
        )

    normalized = stock_view(
        raw_df
    )

    consolidated = consolidate_inventory(
        normalized
    )

    return (
        raw_df,
        normalized,
        consolidated,
    )


# ============================================================
# CARGA ERP VENTAS
# ============================================================

@st.cache_data(
    show_spinner=False,
)
def prepare_sales_context(
    raw: bytes,
    filename: str,
):
    """
    ERP Ventas también queda cacheado.

    Más adelante podemos agregar aquí una capa
    normalizada compartida para:
    - Métricas Vendedores
    - Resumen Ejecutivo
    """

    return read_sales_source(
        raw,
        filename,
    )


# ============================================================
# CONSTRUIR CONTEXTO
# ============================================================

def build_context():

    # --------------------------------------------------------
    # LEER FUENTES GUARDADAS
    # --------------------------------------------------------

    stock_raw, stock_meta = load_source(
        ERP_STOCK_FILE,
        ERP_STOCK_META,
    )

    sales_raw, sales_meta = load_source(
        ERP_SALES_FILE,
        ERP_SALES_META,
    )

    # --------------------------------------------------------
    # DEFAULTS
    # --------------------------------------------------------

    stock_df = None
    stock_normalized = None
    stock_consolidated = None

    sales_df = None

    # --------------------------------------------------------
    # STOCK
    # Prioridad: fuente automática Llegadas_OK.
    # Si falla, se conserva ERP Stock cargado manualmente.
    # --------------------------------------------------------

    remote_error = None

    try:
        remote_df, remote_meta = load_remote_stock()

        if remote_df is not None and not remote_df.empty:
            stock_df = remote_df
            stock_normalized = stock_view(remote_df)
            stock_consolidated = consolidate_inventory(stock_normalized)
            stock_meta = remote_meta

    except Exception as exc:
        remote_error = str(exc)

    if stock_df is None or stock_df.empty:
        if stock_raw:
            stock_filename = (stock_meta or {}).get(
                "filename",
                "erp_stock.xlsx",
            )

            (
                stock_df,
                stock_normalized,
                stock_consolidated,
            ) = prepare_stock_context(
                stock_raw,
                stock_filename,
            )

            stock_meta = dict(stock_meta or {})
            stock_meta["mode"] = "manual_fallback"
            if remote_error:
                stock_meta["remote_error"] = remote_error

    # --------------------------------------------------------
    # VENTAS
    # --------------------------------------------------------

    if sales_raw:

        sales_filename = (
            sales_meta
            or {}
        ).get(
            "filename",
            "erp_ventas.xls",
        )

        sales_df = prepare_sales_context(
            sales_raw,
            sales_filename,
        )

    # --------------------------------------------------------
    # CONTEXTO GLOBAL
    # --------------------------------------------------------

    return {

        # ERP STOCK original
        "stock_df": stock_df,

        # ERP STOCK normalizado por SKU + Bodega
        "stock_normalized": stock_normalized,

        # ERP STOCK consolidado por SKU
        "stock_consolidated": stock_consolidated,

        # Metadata Stock
        "stock_meta": stock_meta,

        # ERP VENTAS
        "sales_df": sales_df,

        # Metadata Ventas
        "sales_meta": sales_meta,
    }


# ============================================================
# ESTADO DE NAVEGACIÓN
# ============================================================

if "page" not in st.session_state:
    st.session_state.page = "Inicio"


# ============================================================
# CAMBIAR PÁGINA
# ============================================================

def change_page(
    page_name: str,
):

    if page_name in PAGE_MAP:
        st.session_state.page = page_name


# ============================================================
# BOTÓN SIDEBAR
# ============================================================

def sidebar_button(
    label: str,
    page_name: str,
    key: str,
    icon: str,
):
    """Botón de navegación del sidebar con icono Material."""

    active = (
        st.session_state.page
        == page_name
    )

    button_type = (
        "primary"
        if active
        else "secondary"
    )

    st.button(
        label,
        key=key,
        use_container_width=True,
        type=button_type,
        icon=icon,
        on_click=change_page,
        args=(
            page_name,
        ),
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    render_html(
        """
        <div class="sidebar-brand-modern">
            <div class="sidebar-logo-mark" aria-hidden="true">
                <span></span><span></span>
            </div>
            <div class="sidebar-brand-name">MARITEX</div>
        </div>
        """
    )

    sidebar_button("Inicio", "Inicio", "nav_inicio", ":material/home:")

    render_html(
        """
        <div class="sidebar-section-modern">
            <span class="sidebar-section-dot"></span>
            <span>OPERACIÓN</span>
            <i></i>
        </div>
        """
    )
    sidebar_button("Stock General", "Stock General", "nav_stock_general", ":material/inventory_2:")
    sidebar_button("Marketplace", "Marketplace", "nav_marketplace", ":material/storefront:")
    sidebar_button("Resumen Ejecutivo", "Resumen Ejecutivo", "nav_resumen_ejecutivo", ":material/dashboard:")

    render_html(
        """
        <div class="sidebar-section-modern">
            <span class="sidebar-section-dot"></span>
            <span>ANÁLISIS</span>
            <i></i>
        </div>
        """
    )
    sidebar_button("Métricas Stock", "Métricas Stock", "nav_metricas_stock", ":material/monitoring:")
    sidebar_button("Métricas Vendedores", "Métricas Vendedores", "nav_metricas_vendedores", ":material/groups:")

    render_html(
        """
        <div class="sidebar-section-modern">
            <span class="sidebar-section-dot"></span>
            <span>HERRAMIENTAS</span>
            <i></i>
        </div>
        """
    )
    sidebar_button("Plantillas", "Plantillas", "nav_plantillas", ":material/description:")


# ============================================================
# CONSTRUIR DATOS
# ============================================================

ctx = build_context()


# ============================================================
# VALIDAR PÁGINA
# ============================================================

page = (
    st.session_state.page
)

if page not in PAGE_MAP:

    page = "Inicio"

    st.session_state.page = (
        page
    )


# ============================================================
# RENDER
# ============================================================

PAGE_MAP[
    page
](
    ctx
)