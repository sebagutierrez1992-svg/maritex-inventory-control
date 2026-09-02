import streamlit as st
import altair as alt

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
    integracion_erp,
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
        background: #ffc400;
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
# TEMA ALTAIR · DARK MARITEX
# ============================================================

def _configure_altair_dark():
    """Tema global para evitar fondos blancos en gráficos Altair."""
    def _theme():
        return {
            "config": {
                "background": "#111a22",
                "view": {
                    "fill": "#111a22",
                    "stroke": "#33414d",
                },
                "axis": {
                    "labelColor": "#aeb8c2",
                    "titleColor": "#dbe2e8",
                    "gridColor": "#2b3945",
                    "domainColor": "#4b5c69",
                    "tickColor": "#4b5c69",
                },
                "legend": {
                    "labelColor": "#dce2e8",
                    "titleColor": "#dce2e8",
                },
                "title": {
                    "color": "#f7f9fb",
                },
            }
        }

    try:
        # Altair 5.x
        alt.themes.register("maritex_dark", _theme)
        alt.themes.enable("maritex_dark")
    except Exception:
        try:
            # Compatibilidad con versiones nuevas
            alt.theme.register("maritex_dark", _theme)
            alt.theme.enable("maritex_dark")
        except Exception:
            pass


_configure_altair_dark()


# ============================================================
# PÁGINAS
# ============================================================

PAGE_MAP = {
    "Inicio": inicio.render,
    "Stock General": stock_general.render,
    "Marketplace": marketplaces.render,
    "Integración ERP": lambda ctx: integracion_erp.render(),
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
        "Integración ERP",
        "Integración ERP",
        "nav_integracion_erp",
        ":material/sync_alt:",
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
# DARK RUNTIME OVERRIDE · DEBE EJECUTARSE DESPUÉS DE CADA VISTA
# ============================================================

def apply_dark_runtime_override():
    st.markdown(
        """
        <style>
        /* -----------------------------------------------------
           Fondo y texto general
           ----------------------------------------------------- */
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > .main,
        .main {
            background:
                radial-gradient(circle at 85% 0%, rgba(39,66,86,.22), rgba(39,66,86,0) 28%),
                linear-gradient(135deg,#14202a 0%,#0f1821 66%,#0b141c 100%) !important;
            color:#f5f7f9 !important;
        }

        [data-testid="stHeader"]{
            background:rgba(15,24,33,.90) !important;
            border-bottom:1px solid #263642 !important;
        }

        /* -----------------------------------------------------
           Títulos
           ----------------------------------------------------- */
        .re-title,.re-card-title,.re-rank-name,.re-client-name,
        .homepro-greeting,.homepro-card-title,.homepro-product-main strong,
        .sgx-title,.sgx-card-title,.sgx-search-head strong,.sgx-product-meta strong,
        .ms-title,.ms-section-head,.ms-card-head,
        .mk2-title,.mk2-platform-title,
        .seller-title,.seller-card-title,.seller-section-title,
        .tpl3-title,.tpl3-name,.tpl3-source strong {
            color:#f7f9fb !important;
        }

        .re-sub,.re-card-sub,
        .homepro-sub,.homepro-card-sub,.homepro-update,
        .sgx-subtitle,.sgx-update,.sgx-search-head span,.sgx-card-sub,
        .ms-subtitle,.ms-head-badge,
        .mk2-subtitle,.mk2-live,
        .seller-subtitle,.sales-detail-subtitle,
        .tpl3-subtitle,.tpl3-file,.tpl3-date,.tpl3-source span {
            color:#9eabb6 !important;
        }

        /* -----------------------------------------------------
           Controles Streamlit
           ----------------------------------------------------- */
        [data-testid="stSelectbox"] label,
        [data-testid="stDateInput"] label,
        [data-testid="stNumberInput"] label,
        [data-testid="stTextInput"] label,
        [data-testid="stMultiSelect"] label,
        [data-testid="stFileUploader"] label {
            color:#b8c2cb !important;
        }

        div[data-baseweb="select"] > div,
        [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input,
        [data-testid="stMultiSelect"] > div > div {
            background:#141e27 !important;
            border:1px solid #3b4a56 !important;
            color:#f4f7f9 !important;
            box-shadow:none !important;
        }

        div[data-baseweb="select"] span,
        div[data-baseweb="select"] svg,
        [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input,
        [data-testid="stTextInput"] input {
            color:#e9eef2 !important;
            fill:#dfe6eb !important;
        }

        /* Toggle */
        [data-testid="stToggle"] label p{
            color:#f0f3f6 !important;
        }

        /* -----------------------------------------------------
           Contenedores Streamlit
           ----------------------------------------------------- */
        div[data-testid="stVerticalBlockBorderWrapper"]{
            background:linear-gradient(145deg,#18232d,#121b23) !important;
            border:1px solid #34434f !important;
            box-shadow:0 10px 28px rgba(0,0,0,.12) !important;
        }

        /* -----------------------------------------------------
           RESUMEN EJECUTIVO
           ----------------------------------------------------- */
        .re-info{
            background:#111a22 !important;
            border:1px solid #3b4b57 !important;
            color:#cbd3da !important;
            box-shadow:none !important;
        }
        .re-info strong{color:#ffc400 !important;}

        .re-kpi{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border:1px solid #34434f !important;
            box-shadow:0 10px 25px rgba(0,0,0,.11) !important;
        }
        .re-kpi-label{color:#b3bec8 !important;}
        .re-kpi-value{color:#ffffff !important;}
        .re-kpi-foot{color:#9da9b4 !important;}
        .re-kpi-foot span{color:#9da9b4 !important;}

        .re-icon.green{background:#123f28 !important;color:#6be394 !important;}
        .re-icon.blue{background:#17375e !important;color:#69a9ff !important;}
        .re-icon.purple{background:#382265 !important;color:#c08cff !important;}
        .re-icon.yellow{background:#4b3b08 !important;color:#ffc400 !important;}
        .re-icon.red{background:#572323 !important;color:#ff6d6d !important;}

        .st-key-re_open_docs button{
            background:rgba(37,99,235,.10) !important;
            border-color:#2862ad !important;
            color:#70a7ff !important;
        }
        .st-key-re_open_clients button{
            background:rgba(124,58,237,.11) !important;
            border-color:#6740a6 !important;
            color:#c08cff !important;
        }
        .st-key-re_open_nc button{
            background:rgba(220,38,38,.12) !important;
            border-color:#a53232 !important;
            color:#ff7474 !important;
        }

        .re-client-head,.re-rank-head{
            color:#9eabb6 !important;
            border-color:#34434f !important;
        }
        .re-client-row,.re-rank-row{
            color:#e8edf1 !important;
            border-color:#2d3c47 !important;
        }
        .re-client-rank{color:#8e9aa5 !important;}
        .re-client-value,.re-rank-value{color:#f5f7f9 !important;}
        .re-rank-row.current{
            background:#332b0c !important;
        }

        .re-detail-pill{
            background:#17232d !important;
            border-color:#3a4955 !important;
            color:#dce3e8 !important;
        }

        .re-goal{
            background:linear-gradient(145deg,#202b35,#141d25) !important;
            border-color:#3b4955 !important;
        }
        .re-goal-title,.re-projection{color:#aeb8c2 !important;}
        .re-goal-title strong{color:#fff !important;}
        .re-goal-track{background:#2d3944 !important;}

        /* -----------------------------------------------------
           INICIO
           ----------------------------------------------------- */
        .homepro-kpi,
        .homepro-attention,
        .homepro-status-summary > div{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#f5f7f9 !important;
        }
        .homepro-kpi-label,.homepro-kpi-helper,
        .homepro-alert small,.homepro-status-summary span,
        .homepro-product-main span{
            color:#9da9b4 !important;
        }
        .homepro-kpi-value,.homepro-alert strong,
        .homepro-status-summary strong,.homepro-product-main strong,
        .homepro-num,.homepro-money{
            color:#f7f9fb !important;
        }
        .homepro-alert,.homepro-product-row,.homepro-table th,.homepro-table td{
            border-color:#2d3c47 !important;
        }
        .homepro-table th{color:#9eabb6 !important;}
        .homepro-table td{color:#dfe5ea !important;}
        .homepro-attention span{color:#b5aa86 !important;}
        .homepro-attention strong{color:#fff !important;}

        /* -----------------------------------------------------
           STOCK GENERAL
           ----------------------------------------------------- */
        .sgx-search-card,.sgx-kpi,.sgx-product-meta > div,
        .sgx-wh-total,.sgx-detail-hero,.sgx-card{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#f5f7f9 !important;
        }
        .sgx-kpi-copy > span,.sgx-kpi-copy > small,
        .sgx-product-meta span,.sgx-status-row span,.sgx-wh-name{
            color:#9da9b4 !important;
        }
        .sgx-kpi-copy > strong,.sgx-product-meta strong,.sgx-status-row strong,
        .sgx-wh-value,.sgx-ring strong{
            color:#f7f9fb !important;
        }
        .sgx-ring{
            background:
                radial-gradient(circle at center,#16212a 57%,transparent 58%),
                conic-gradient(#79c35a var(--p),#ffc400 var(--p),#26343f 0) !important;
        }
        .sgx-ring span{color:#9da9b4 !important;}
        .sgx-wh-track{background:#273640 !important;}
        .sgx-healthy-note{
            background:#163323 !important;
            color:#72d48b !important;
        }

        /* -----------------------------------------------------
           MARKETPLACE
           ----------------------------------------------------- */
        .mk2-source,.mk2-platform-head,.mk2-summary-grid > div,
        .mk3-compact-summary{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#dfe5ea !important;
        }
        .mk3-compact-summary{color:#9da9b4 !important;}
        .mk3-compact-summary b{color:#f5f7f9 !important;}

        /* -----------------------------------------------------
           MÉTRICAS STOCK
           ----------------------------------------------------- */
        .ms-source,.ms-kpi,.ms-risk-strip,.ms-info-box,
        .ms-movement-summary > div{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#e6ebef !important;
        }
        .ms-kpi-label,.ms-kpi-helper,.ms-source-update,.ms-source-item span{
            color:#9da9b4 !important;
        }
        .ms-kpi-value,.ms-source-item strong{color:#f7f9fb !important;}

        /* -----------------------------------------------------
           MÉTRICAS VENDEDORES
           ----------------------------------------------------- */
        .seller-rule,.sales-rule-strip,.sales-data-status,
        .seller-card,.client-search-summary,.sales-detail-box,
        .seller-goal-wrap{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#dfe5ea !important;
        }
        .sales-kpi-button-wrap .stButton > button{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#f4f7f9 !important;
        }

        /* -----------------------------------------------------
           PLANTILLAS
           ----------------------------------------------------- */
        .tpl3-card,.tpl3-source{
            background:linear-gradient(145deg,#1a2530,#141e27) !important;
            border-color:#34434f !important;
            color:#e6ebef !important;
        }

        /* -----------------------------------------------------
           Botones, descargas, expanders y alertas
           ----------------------------------------------------- */
        .main .stButton > button:not([kind="primary"]),
        .main .stDownloadButton > button{
            background:#17232d !important;
            border-color:#3b4a56 !important;
            color:#eef2f5 !important;
        }
        .main .stButton > button:not([kind="primary"]):hover,
        .main .stDownloadButton > button:hover{
            background:#202d38 !important;
            border-color:#556675 !important;
            color:#fff !important;
        }

        [data-testid="stExpander"]{
            background:#141f28 !important;
            border-color:#34434f !important;
        }
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] summary *{
            color:#e9eef2 !important;
        }

        [data-testid="stAlert"]{
            background:#17232d !important;
            border-color:#3b4a56 !important;
            color:#e8edf1 !important;
        }
        [data-testid="stAlert"] *{color:inherit !important;}

        /* -----------------------------------------------------
           DATAFRAME
           ----------------------------------------------------- */
        [data-testid="stDataFrame"]{
            background:#111a22 !important;
            border-color:#34434f !important;
        }

        /* -----------------------------------------------------
           VEGA / ALTAIR
           ----------------------------------------------------- */
        [data-testid="stVegaLiteChart"],
        [data-testid="stVegaLiteChart"] > div{
            background:#111a22 !important;
            border-radius:9px !important;
        }

        /* -----------------------------------------------------
           Menús flotantes
           ----------------------------------------------------- */
        div[data-baseweb="popover"],
        div[data-baseweb="menu"],
        ul[role="listbox"],
        li[role="option"]{
            background:#17232d !important;
            color:#eef2f5 !important;
        }
        li[role="option"]:hover{
            background:#24323d !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# RENDER
# ============================================================

PAGE_MAP[
    page
](
    ctx
)

# Se inyecta al final para ganar a los estilos internos de cada vista.
apply_dark_runtime_override()