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
    "Stock General": stock_general.render,
    "Marketplaces": marketplaces.render,
    "Métricas de Stock": metricas_stock.render,
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
    # --------------------------------------------------------

    if stock_raw:

        stock_filename = (
            stock_meta
            or {}
        ).get(
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
    st.session_state.page = "Stock General"


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
    arrow: bool = False,
):
    """
    Navegación mediante botones.

    PRIMARY
        Página activa.

    SECONDARY
        Resto de páginas.
    """

    active = (
        st.session_state.page
        == page_name
    )

    button_type = (
        "primary"
        if active
        else "secondary"
    )

    display_label = (
        f"{label} ›"
        if arrow
        else label
    )

    st.button(
        display_label,
        key=key,
        use_container_width=True,
        type=button_type,
        on_click=change_page,
        args=(
            page_name,
        ),
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    # --------------------------------------------------------
    # MARCA
    # --------------------------------------------------------

    render_html(
        """
        <div class="sidebar-brand-final">

            <div class="sidebar-x">
                X
            </div>

            <div class="sidebar-brand-text">
                Grupo Maritex
            </div>

        </div>
        """
    )

    # --------------------------------------------------------
    # OPERACIÓN
    # --------------------------------------------------------

    render_html(
        """
        <div class="sidebar-section-final">

            <span>
                OPERACIÓN
            </span>

            <div class="sidebar-section-line"></div>

        </div>
        """
    )

    sidebar_button(
        label="Stock General",
        page_name="Stock General",
        key="nav_stock_general",
    )

    sidebar_button(
        label="Marketplaces",
        page_name="Marketplaces",
        key="nav_marketplaces",
    )

    # --------------------------------------------------------
    # ANÁLISIS
    # --------------------------------------------------------

    render_html(
        """
        <div class="sidebar-section-final sidebar-section-space">

            <span>
                ANÁLISIS
            </span>

            <div class="sidebar-section-line"></div>

        </div>
        """
    )

    sidebar_button(
        label="Métricas de Stock",
        page_name="Métricas de Stock",
        key="nav_metricas_stock",
    )

    sidebar_button(
        label="Métricas Vendedores",
        page_name="Métricas Vendedores",
        key="nav_metricas_vendedores",
    )

    sidebar_button(
        label="Resumen Ejecutivo",
        page_name="Resumen Ejecutivo",
        key="nav_resumen_ejecutivo",
    )

    # --------------------------------------------------------
    # HERRAMIENTAS
    # --------------------------------------------------------

    render_html(
        """
        <div class="sidebar-section-final sidebar-section-space">

            <span>
                HERRAMIENTAS
            </span>

            <div class="sidebar-section-line"></div>

        </div>
        """
    )

    sidebar_button(
        label="Plantillas",
        page_name="Plantillas",
        key="nav_plantillas",
        arrow=True,
    )


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

    page = "Stock General"

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