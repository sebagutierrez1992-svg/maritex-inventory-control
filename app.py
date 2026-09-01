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

STOCK_PAGES = {
    "Inicio",
    "Stock General",
    "Marketplace",
    "Métricas Stock",
    "Resumen Ejecutivo",
}

SALES_PAGES = {
    "Inicio",
    "Métricas Vendedores",
    "Resumen Ejecutivo",
}


# ============================================================
# HELPERS
# ============================================================

def _file_modified_time(path) -> float | None:
    try:
        if path.exists():
            return path.stat().st_mtime
    except Exception:
        pass

    return None


@st.cache_data(show_spinner=False)
def _load_source_cached(
    data_path: str,
    meta_path: str,
    data_mtime: float | None,
    meta_mtime: float | None,
):
    """
    Lee el archivo guardado solo cuando cambia físicamente.
    La clave del caché usa rutas y fechas de modificación.
    """
    return load_source(
        data_path,
        meta_path,
    )


# ============================================================
# STOCK REMOTO
# ============================================================

@st.cache_data(
    ttl=300,
    show_spinner=False,
)
def prepare_remote_stock_context():
    """
    Descarga y transforma Llegadas_OK una vez cada 5 minutos.
    """

    remote_df, remote_meta = load_remote_stock()

    if remote_df is None or remote_df.empty:
        return (
            remote_df,
            None,
            None,
            remote_meta,
        )

    normalized = stock_view(
        remote_df
    )

    consolidated = consolidate_inventory(
        normalized
    )

    return (
        remote_df,
        normalized,
        consolidated,
        remote_meta,
    )


# ============================================================
# STOCK LOCAL - FALLBACK
# ============================================================

@st.cache_data(show_spinner=False)
def _load_and_prepare_local_stock(
    data_path: str,
    meta_path: str,
    data_mtime: float | None,
    meta_mtime: float | None,
):
    """
    Lee y procesa ERP Stock usando únicamente una clave pequeña:
    ruta + mtime. Evita pasar bytes grandes entre cachés.
    """

    raw, meta = load_source(
        data_path,
        meta_path,
    )

    if not raw:
        return (
            None,
            None,
            None,
            meta,
        )

    filename = (
        meta
        or {}
    ).get(
        "filename",
        "erp_stock.xlsx",
    )

    raw_df = read_stock_source(
        raw,
        filename,
    )

    if raw_df is None or raw_df.empty:
        return (
            raw_df,
            None,
            None,
            meta,
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
        meta,
    )


def build_stock_context() -> dict:
    """
    Prioridad:
    1. Llegadas_OK
    2. ERP Stock local como fallback
    """

    remote_error = None

    try:
        (
            stock_df,
            stock_normalized,
            stock_consolidated,
            stock_meta,
        ) = prepare_remote_stock_context()

        if (
            stock_df is not None
            and not stock_df.empty
        ):
            return {
                "stock_df": stock_df,
                "stock_normalized": stock_normalized,
                "stock_consolidated": stock_consolidated,
                "stock_meta": stock_meta,
            }

    except Exception as exc:
        remote_error = str(exc)

    (
        stock_df,
        stock_normalized,
        stock_consolidated,
        stock_meta,
    ) = _load_and_prepare_local_stock(
        str(ERP_STOCK_FILE),
        str(ERP_STOCK_META),
        _file_modified_time(
            ERP_STOCK_FILE
        ),
        _file_modified_time(
            ERP_STOCK_META
        ),
    )

    stock_meta = dict(
        stock_meta
        or {}
    )

    if stock_df is not None and not stock_df.empty:
        stock_meta["mode"] = "manual_fallback"

    if remote_error:
        stock_meta["remote_error"] = remote_error

    return {
        "stock_df": stock_df,
        "stock_normalized": stock_normalized,
        "stock_consolidated": stock_consolidated,
        "stock_meta": stock_meta,
    }


# ============================================================
# VENTAS - CARGA DIFERIDA
# ============================================================

@st.cache_data(show_spinner=False)
def _load_and_prepare_sales(
    data_path: str,
    meta_path: str,
    data_mtime: float | None,
    meta_mtime: float | None,
):
    """
    Lee y procesa ERP Ventas únicamente cuando una página lo necesita.

    Importante:
    los ~MB del ERP no se usan como argumento del caché.
    Streamlit solo hashea strings y mtimes pequeños.
    """

    raw, meta = load_source(
        data_path,
        meta_path,
    )

    if not raw:
        return (
            None,
            meta,
        )

    filename = (
        meta
        or {}
    ).get(
        "filename",
        "erp_ventas.xls",
    )

    sales_df = read_sales_source(
        raw,
        filename,
    )

    return (
        sales_df,
        meta,
    )


def build_sales_context() -> dict:

    sales_df, sales_meta = _load_and_prepare_sales(
        str(ERP_SALES_FILE),
        str(ERP_SALES_META),
        _file_modified_time(
            ERP_SALES_FILE
        ),
        _file_modified_time(
            ERP_SALES_META
        ),
    )

    return {
        "sales_df": sales_df,
        "sales_meta": sales_meta,
    }


# ============================================================
# CONTEXTO POR PÁGINA
# ============================================================

def build_context_for_page(
    page_name: str,
) -> dict:
    """
    Lazy loading.

    Cada página carga solamente las fuentes que realmente necesita.
    """

    ctx = {
        "stock_df": None,
        "stock_normalized": None,
        "stock_consolidated": None,
        "stock_meta": {},
        "sales_df": None,
        "sales_meta": {},
    }

    if page_name in STOCK_PAGES:
        ctx.update(
            build_stock_context()
        )

    if page_name in SALES_PAGES:
        ctx.update(
            build_sales_context()
        )

    return ctx


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
        width="stretch",
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

    sidebar_button(
        "Inicio",
        "Inicio",
        "nav_inicio",
        ":material/home:",
    )

    render_html(
        """
        <div class="sidebar-section-modern">
            <span class="sidebar-section-dot"></span>
            <span>OPERACIÓN</span>
            <i></i>
        </div>
        """
    )

    sidebar_button(
        "Stock General",
        "Stock General",
        "nav_stock_general",
        ":material/inventory_2:",
    )

    sidebar_button(
        "Marketplace",
        "Marketplace",
        "nav_marketplace",
        ":material/storefront:",
    )

    sidebar_button(
        "Resumen Ejecutivo",
        "Resumen Ejecutivo",
        "nav_resumen_ejecutivo",
        ":material/dashboard:",
    )

    render_html(
        """
        <div class="sidebar-section-modern">
            <span class="sidebar-section-dot"></span>
            <span>ANÁLISIS</span>
            <i></i>
        </div>
        """
    )

    sidebar_button(
        "Métricas Stock",
        "Métricas Stock",
        "nav_metricas_stock",
        ":material/monitoring:",
    )

    sidebar_button(
        "Métricas Vendedores",
        "Métricas Vendedores",
        "nav_metricas_vendedores",
        ":material/groups:",
    )

    render_html(
        """
        <div class="sidebar-section-modern">
            <span class="sidebar-section-dot"></span>
            <span>HERRAMIENTAS</span>
            <i></i>
        </div>
        """
    )

    sidebar_button(
        "Plantillas",
        "Plantillas",
        "nav_plantillas",
        ":material/description:",
    )


# ============================================================
# VALIDAR PÁGINA
# ============================================================

page = st.session_state.page

if page not in PAGE_MAP:
    page = "Inicio"
    st.session_state.page = page


# ============================================================
# CARGA DIFERIDA DEL CONTEXTO
# ============================================================

ctx = build_context_for_page(
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
