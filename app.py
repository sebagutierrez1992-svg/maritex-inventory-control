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
# SIDEBAR CORPORATIVO — OPCIÓN C V2
# ============================================================

st.markdown(
    """
    <style>
    /* =====================================================
       FONDO REAL DEL SIDEBAR
       ===================================================== */
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] > div,
    [data-testid="stSidebarContent"],
    [data-testid="stSidebarUserContent"] {
        background:
            radial-gradient(circle at 18% 0%, rgba(255, 196, 0, .08) 0%, rgba(255, 196, 0, 0) 30%),
            linear-gradient(180deg, #0a0a0a 0%, #090909 55%, #050505 100%) !important;
    }

    [data-testid="stSidebar"] {
        width: 280px !important;
        min-width: 280px !important;
        border-right: 1px solid rgba(255,196,0,.16) !important;
        box-shadow: 10px 0 28px rgba(0, 0, 0, .16) !important;
    }

    [data-testid="stSidebarContent"] {
        padding: 0 !important;
    }

    [data-testid="stSidebarUserContent"] {
        padding: 14px 16px 18px 16px !important;
        max-width: 280px !important;
    }

    /* Evita espacios gigantes entre widgets */
    [data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] {
        gap: .18rem !important;
    }

    /* =====================================================
       MARCA
       ===================================================== */
    .sidebar-brand-c {
        display: flex;
        align-items: center;
        justify-content: flex-start;
        gap: 12px;
        width: 100%;
        min-height: 68px;
        padding: 7px 8px 16px 8px;
        margin: 0 0 7px 0;
        border-bottom: 1px solid rgba(255,255,255,.10);
        box-sizing: border-box;
    }

    .sidebar-brand-c .brand-mark {
        width: 33px;
        height: 33px;
        position: relative;
        flex: 0 0 33px;
    }

    .sidebar-brand-c .brand-mark:before,
    .sidebar-brand-c .brand-mark:after {
        content: "";
        position: absolute;
        left: 13px;
        top: 1px;
        width: 7px;
        height: 31px;
        border-radius: 2px;
        background: #111111;
        transform-origin: center;
    }

    .sidebar-brand-c .brand-mark:before { transform: rotate(42deg); }
    .sidebar-brand-c .brand-mark:after  { transform: rotate(-42deg); }

    .sidebar-brand-c .brand-copy {
        display: flex;
        flex-direction: column;
        justify-content: center;
        min-width: 0;
    }

    .sidebar-brand-c .brand-name {
        color: #ffffff !important;
        font-size: 19px;
        font-weight: 850;
        letter-spacing: .45px;
        line-height: 1.05;
    }

    .sidebar-brand-c .brand-subtitle {
        color: #91a8bb !important;
        font-size: 8.5px;
        font-weight: 700;
        letter-spacing: 1.25px;
        text-transform: uppercase;
        margin-top: 5px;
        line-height: 1;
    }

    /* =====================================================
       SECCIONES
       ===================================================== */
    .sidebar-section-modern {
        display: flex !important;
        align-items: center !important;
        width: 100% !important;
        gap: 9px !important;
        padding: 15px 7px 6px 7px !important;
        margin: 0 !important;
        box-sizing: border-box !important;
        color: #ffc400 !important;
        font-size: 9px !important;
        font-weight: 850 !important;
        letter-spacing: 1.25px !important;
        text-transform: uppercase !important;
        line-height: 1 !important;
    }

    .sidebar-section-modern .sidebar-section-dot {
        display: none !important;
    }

    .sidebar-section-modern i {
        display: block !important;
        flex: 1 !important;
        height: 1px !important;
        background: linear-gradient(90deg, rgba(255,196,0,.48), rgba(255,196,0,0)) !important;
        margin-left: 4px !important;
    }

    /* =====================================================
       NAVEGACIÓN
       ===================================================== */
    [data-testid="stSidebar"] div.stButton {
        margin: 0 !important;
        width: 100% !important;
    }

    [data-testid="stSidebar"] div.stButton > button {
        position: relative !important;
        width: 100% !important;
        min-height: 42px !important;
        height: 42px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 11px !important;
        padding: 0 12px !important;
        margin: 0 !important;
        border-radius: 8px !important;
        border: 1px solid transparent !important;
        box-shadow: none !important;
        font-size: 13px !important;
        font-weight: 650 !important;
        line-height: 1 !important;
        transition: all .14s ease !important;
    }

    /* Inactivos */
    [data-testid="stSidebar"] div.stButton > button[kind="secondary"] {
        background: transparent !important;
        color: #d7e2eb !important;
    }

    [data-testid="stSidebar"] div.stButton > button[kind="secondary"] p,
    [data-testid="stSidebar"] div.stButton > button[kind="secondary"] span {
        color: #d7e2eb !important;
    }

    [data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover {
        background: rgba(255,196,0,.08) !important;
        border-color: rgba(255,196,0,.16) !important;
        color: #ffffff !important;
        transform: translateX(2px);
    }

    /* Activo */
    [data-testid="stSidebar"] div.stButton > button[kind="primary"] {
        overflow: hidden !important;
        background: linear-gradient(90deg, #ffd21a 0%, #ffc400 100%) !important;
        color: #111111 !important;
        border-color: rgba(255, 196, 0, .42) !important;
        font-weight: 850 !important;
    }

    [data-testid="stSidebar"] div.stButton > button[kind="primary"]:before {
        content: "";
        position: absolute;
        left: 0;
        top: 4px;
        bottom: 4px;
        width: 4px;
        border-radius: 0 4px 4px 0;
        background: #111111;
    }

    [data-testid="stSidebar"] div.stButton > button[kind="primary"] p,
    [data-testid="stSidebar"] div.stButton > button[kind="primary"] span {
        color: #111111 !important;
    }

    [data-testid="stSidebar"] div.stButton > button[kind="primary"] span[data-testid="stIconMaterial"] {
        color: #111111 !important;
    }

    [data-testid="stSidebar"] div.stButton > button[kind="secondary"] span[data-testid="stIconMaterial"] {
        color: #c8d7e2 !important;
    }

    /* Alineación fija del icono y texto */
    [data-testid="stSidebar"] div.stButton > button [data-testid="stIconMaterial"] {
        flex: 0 0 22px !important;
        width: 22px !important;
        min-width: 22px !important;
        text-align: center !important;
        font-size: 20px !important;
        margin: 0 !important;
    }

    [data-testid="stSidebar"] div.stButton > button p {
        margin: 0 !important;
        white-space: nowrap !important;
        text-align: left !important;
    }

    /* =====================================================
       FOOTER
       ===================================================== */
    .sidebar-footer-c {
        margin: 18px 7px 0 7px;
        padding: 13px 0 0 0;
        border-top: 1px solid rgba(255,255,255,.09);
        color: #70869a !important;
        font-size: 8.5px;
        line-height: 1.55;
        letter-spacing: .25px;
    }

    .sidebar-footer-c strong {
        color: #ffc400 !important;
        font-weight: 750;
    }

    /* =====================================================
       SCROLL
       ===================================================== */
    [data-testid="stSidebar"] ::-webkit-scrollbar {
        width: 6px;
    }

    [data-testid="stSidebar"] ::-webkit-scrollbar-track {
        background: transparent;
    }

    [data-testid="stSidebar"] ::-webkit-scrollbar-thumb {
        background: rgba(255,255,255,.14);
        border-radius: 999px;
    }

    /* Botón colapsar */
    [data-testid="stSidebar"] button {
        box-shadow: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
        <div class="sidebar-brand-c">
            <div class="brand-mark" aria-hidden="true"></div>
            <div class="brand-copy">
                <div class="brand-name">MARITEX</div>
                <div class="brand-subtitle">Control Comercial</div>
            </div>
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


    render_html(
        """
        <div class="sidebar-footer-c">
            <strong>MARITEX</strong><br>
            Inventario · Ventas · Marketplace
        </div>
        """
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
