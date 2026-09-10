

import re
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from services.ecommerce_erp import (
    diagnose_erp_response,
    extract_orders,
    extract_vtex_order_id,
    get_pending_orders,
    reinject_order,
)
from services.erp_stock_helper import (
    build_stock_resolution,
)


# ============================================================
# ESTILO VISUAL DE LA VISTA
# ============================================================

def _apply_view_styles():
    st.markdown(
        r"""
        <style>
        :root {
            --erp-bg:#000000; --erp-panel:#080b0e; --erp-card:#0b0f13;
            --erp-card-2:#0e1419; --erp-border:#29343d; --erp-text:#f7f9fb;
            --erp-muted:#9aa8b3; --erp-yellow:#ffc400; --erp-green:#25c784;
            --erp-red:#ff5b57; --erp-blue:#4da3ff;
        }
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], section.main {
            background:#000 !important; color:var(--erp-text) !important;
        }
        [data-testid="stMainBlockContainer"] {max-width:1500px; padding-top:1.2rem;}
        .erp-page-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;padding:4px 2px 18px;margin-bottom:6px;border-bottom:1px solid #1f272e}
        .erp-page-head h1{margin:0;font-size:2rem;line-height:1.05;letter-spacing:-.03em;color:#fff}
        .erp-page-head p{margin:7px 0 0;color:var(--erp-muted);font-size:.9rem}
        .erp-live-pill{display:inline-flex;align-items:center;gap:8px;padding:7px 11px;border:1px solid rgba(255,196,0,.30);border-radius:999px;background:rgba(255,196,0,.07);color:#fff;font-size:.78rem;white-space:nowrap}
        .erp-live-pill i{display:block;width:7px;height:7px;border-radius:999px;background:var(--erp-yellow);box-shadow:0 0 0 4px rgba(255,196,0,.10)}

        /* contenedores */
        div[data-testid="stVerticalBlockBorderWrapper"]{border:1px solid var(--erp-border)!important;border-radius:14px!important;background:#050709!important;box-shadow:none!important}
        div[data-testid="stVerticalBlockBorderWrapper"] > div{background:transparent!important}

        /* métricas */
        div[data-testid="stMetric"]{border:1px solid var(--erp-border);border-left:3px solid var(--erp-yellow);border-radius:12px;background:var(--erp-card);padding:13px 15px;min-height:94px}
        div[data-testid="stMetricLabel"]{color:var(--erp-muted)!important;font-size:.75rem!important;font-weight:750!important;text-transform:uppercase;letter-spacing:.03em}
        div[data-testid="stMetricValue"]{color:#fff!important;font-size:1.55rem!important;line-height:1.15!important;font-weight:800!important}

        /* inputs */
        [data-testid="stTextInput"] input, [data-testid="stSelectbox"] div[data-baseweb="select"] > div{
            background:#080b0e!important;color:#fff!important;border-color:var(--erp-border)!important;border-radius:10px!important;
        }
        [data-testid="stTextInput"] input::placeholder{color:#71808c!important}
        [data-testid="stTextInput"] label, [data-testid="stSelectbox"] label{color:#dce4ea!important;font-weight:700!important}
        [data-baseweb="popover"] > div, [role="listbox"]{background:#080b0e!important;color:#fff!important}

        /* segmented control */
        [data-testid="stSegmentedControl"]{background:#050709!important;border:1px solid var(--erp-border)!important;border-radius:12px!important;padding:4px!important}
        [data-testid="stSegmentedControl"] button{background:transparent!important;color:#c5d0d8!important;border:0!important}
        [data-testid="stSegmentedControl"] button[aria-pressed="true"]{background:var(--erp-yellow)!important;color:#050505!important;font-weight:800!important}

        /* botones */
        .stButton > button{background:#0b0f13!important;color:#fff!important;border:1px solid var(--erp-border)!important;border-radius:10px!important}
        .stButton > button:hover{border-color:var(--erp-yellow)!important;color:var(--erp-yellow)!important}
        .stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"]{background:var(--erp-yellow)!important;color:#050505!important;border-color:var(--erp-yellow)!important;font-weight:850!important}

        /* dataframe: conservar selección de filas, pero neutralizar azul */
        div[data-testid="stDataFrame"]{border:1px solid var(--erp-border)!important;border-radius:13px!important;overflow:hidden!important;background:#070a0d!important;
            --gdg-bg-cell:#0b1116; --gdg-bg-header:#080b0e; --gdg-text-dark:#f5f7f9; --gdg-border-color:#27323b;}
        div[data-testid="stDataFrame"] > div, div[data-testid="stDataFrame"] canvas{background:#0b1116!important}
        div[data-testid="stDataFrame"] [role="columnheader"]{background:#080b0e!important;color:#aebbc5!important}

        /* alertas y expanders */
        [data-testid="stAlert"]{background:#090d10!important;border-radius:10px!important;border-color:#303b43!important;color:#eef3f6!important}
        [data-testid="stExpander"]{background:#050709!important;border:1px solid var(--erp-border)!important;border-radius:12px!important}
        [data-testid="stExpander"] summary{color:#eef3f6!important}
        [data-testid="stCodeBlock"], pre{background:#050709!important;border-color:var(--erp-border)!important}

        hr{border-color:#222b32!important;opacity:1!important}
        .erp-section-kicker{color:var(--erp-yellow);text-transform:uppercase;letter-spacing:.08em;font-size:.68rem;font-weight:850;margin-bottom:3px}
        .erp-section-title{color:#fff;font-size:1.05rem;font-weight:850;margin:0 0 3px}
        .erp-section-sub{color:var(--erp-muted);font-size:.79rem;margin-bottom:10px}
        .erp-table-hint{display:flex;align-items:center;justify-content:space-between;gap:10px;color:#8f9da8;font-size:.76rem;margin:4px 0 9px}
        .erp-table-hint strong{color:#fff}
        .erp-page-indicator{min-height:40px;display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:.78rem}
        .erp-page-indicator strong{color:var(--erp-yellow);margin:0 4px}
        h1,h2,h3,h4,h5{color:#fff!important}
        p, .stCaption{color:#9eabb5}

        /* =====================================================
           MARITEX ERP · V3 · MOCKUP FIEL
           ===================================================== */
        [data-testid="stMainBlockContainer"]{
            max-width:1680px!important;
            padding-top:.8rem!important;
            padding-left:1.35rem!important;
            padding-right:1.35rem!important;
        }

        .erp-page-head{
            display:flex!important;
            align-items:center!important;
            justify-content:space-between!important;
            padding:6px 0 14px!important;
            margin-bottom:8px!important;
        }
        .erp-page-head h1{
            font-size:2.25rem!important;
            font-weight:900!important;
            letter-spacing:-.045em!important;
        }
        .erp-page-head p{
            font-size:.88rem!important;
            color:#9fb1bd!important;
        }

        .erp-top-info{
            display:flex;
            justify-content:flex-end;
            align-items:center;
            gap:18px;
            margin-bottom:4px;
        }
        .erp-last-update{
            color:#8c9aa5;
            font-size:.68rem;
            line-height:1.35;
            text-align:right;
        }
        .erp-last-update strong{
            color:#d9e1e7;
            display:block;
            margin-top:2px;
            font-size:.72rem;
        }

        .erp-kpi-card{
            position:relative;
            min-height:100px;
            padding:14px 14px;
            border:1px solid #28343d;
            border-radius:10px;
            background:linear-gradient(145deg,#131c24,#0a1015);
            overflow:hidden;
        }
        .erp-kpi-card.credit{background:linear-gradient(145deg,#3a1f23,#25161a)}
        .erp-kpi-card.stock{background:linear-gradient(145deg,#3b3515,#24200d)}
        .erp-kpi-card.payment{background:linear-gradient(145deg,#193453,#10243a)}
        .erp-kpi-card.client{background:linear-gradient(145deg,#2e214a,#211835)}
        .erp-kpi-card.integrated{background:linear-gradient(145deg,#153c2c,#0d281d)}
        .erp-kpi-card.unclassified{background:linear-gradient(145deg,#27313a,#1b232a)}

        .erp-kpi-label{
            color:#d6dde3;
            font-size:.72rem;
            font-weight:800;
        }
        .erp-kpi-value{
            margin-top:6px;
            color:#fff;
            font-size:1.7rem;
            font-weight:900;
            line-height:1;
        }
        .erp-kpi-hint{
            color:#92a0ab;
            font-size:.66rem;
            margin-top:7px;
        }

        .erp-toolbar{
            margin-top:10px;
            padding-top:10px;
            border-top:1px solid #222c33;
        }

        .erp-table-shell{
            border:1px solid #26323b;
            border-radius:10px;
            overflow:hidden;
            background:#071016;
        }
        .erp-table-head{
            display:grid;
            grid-template-columns:1.45fr .85fr 1fr .95fr 1.7fr .8fr .65fr;
            gap:0;
            background:#0c141b;
            border-bottom:1px solid #2a353e;
            color:#a9b8c3;
            font-size:.68rem;
            font-weight:850;
            text-transform:uppercase;
            letter-spacing:.025em;
        }
        .erp-table-head > div{
            padding:10px 10px;
            border-right:1px solid #202a31;
        }
        .erp-table-head > div:last-child{border-right:0}

        .erp-row{
            display:grid;
            grid-template-columns:1.45fr .85fr 1fr .95fr 1.7fr .8fr .65fr;
            gap:0;
            min-height:46px;
            align-items:center;
            border-bottom:1px solid #202a31;
            background:#091118;
        }
        .erp-row:last-child{border-bottom:0}
        .erp-row:hover{background:#0d171f}
        .erp-row.selected{
            background:linear-gradient(90deg,rgba(255,196,0,.18),rgba(255,196,0,.04));
            box-shadow:inset 3px 0 0 #ffc400;
        }
        .erp-cell{
            padding:9px 10px;
            color:#e5ebef;
            font-size:.73rem;
            border-right:1px solid #202a31;
            overflow:hidden;
            text-overflow:ellipsis;
            white-space:nowrap;
        }
        .erp-cell:last-child{border-right:0}

        .erp-badge{
            display:inline-flex;
            align-items:center;
            justify-content:center;
            padding:4px 9px;
            border-radius:999px;
            font-size:.65rem;
            font-weight:850;
            color:#071014;
        }
        .erp-badge.credit{background:#ff7b83}
        .erp-badge.stock{background:#ffd52a}
        .erp-badge.payment{background:#67adff}
        .erp-badge.client{background:#c17dff}
        .erp-badge.integrated{background:#45da91}
        .erp-badge.unclassified{background:#9ba9b5}
        .erp-badge.other{background:#d9e1e7}

        .erp-state-dot{
            display:inline-block;
            width:8px;
            height:8px;
            border-radius:50%;
            margin-right:6px;
            vertical-align:middle;
        }
        .erp-state-dot.ok{background:#38d98e}
        .erp-state-dot.err{background:#ff4d5b}

        .erp-detail-panel{
            border:1px solid #26323b;
            border-radius:10px;
            background:#071016;
            padding:16px;
            min-height:620px;
        }
        .erp-detail-title{
            color:#fff;
            font-weight:850;
            font-size:1rem;
            margin-bottom:8px;
        }
        .erp-detail-order{
            color:#fff;
            font-size:1.3rem;
            font-weight:900;
            margin-bottom:3px;
        }
        .erp-detail-meta{
            color:#8b9aa5;
            font-size:.68rem;
            margin-bottom:14px;
        }
        .erp-detail-grid{
            display:grid;
            grid-template-columns:1fr 1fr;
            gap:7px 14px;
            margin-bottom:14px;
        }
        .erp-detail-item{
            display:flex;
            justify-content:space-between;
            gap:10px;
            color:#91a0ac;
            font-size:.7rem;
        }
        .erp-detail-item b{
            color:#f2f5f7;
            font-weight:750;
            text-align:right;
        }
        .erp-error-box{
            margin:12px 0;
            padding:12px 13px;
            border-radius:9px;
            border:1px solid rgba(255,93,100,.22);
            background:linear-gradient(90deg,rgba(255,93,100,.22),rgba(255,93,100,.07));
        }
        .erp-error-box .k{color:#e0bfc2;font-size:.65rem}
        .erp-error-box .v{color:#fff;font-size:.82rem;font-weight:800;margin-top:3px}

        .erp-message-box{
            border:1px solid #26323b;
            border-radius:8px;
            background:#0a1218;
            padding:11px 12px;
            color:#d6e0e6;
            font-size:.7rem;
            line-height:1.45;
            min-height:72px;
        }

        .erp-stock-alt{
            margin-top:12px;
            border:1px solid #26323b;
            border-radius:9px;
            background:#091118;
            overflow:hidden;
        }
        .erp-stock-alt-title{
            padding:10px 12px;
            color:#fff;
            font-size:.78rem;
            font-weight:850;
            border-bottom:1px solid #26323b;
        }
        .erp-stock-alt-row{
            display:grid;
            grid-template-columns:.8fr 1.35fr 1fr 1.3fr;
            gap:8px;
            padding:9px 12px;
            border-bottom:1px solid #202a31;
            color:#d7e0e6;
            font-size:.67rem;
        }
        .erp-stock-alt-row:last-child{border-bottom:0}
        .erp-pill{
            display:inline-block;
            padding:3px 8px;
            border-radius:999px;
            background:#43d98e;
            color:#071014;
            font-weight:850;
            margin-right:5px;
            margin-bottom:3px;
        }
        .erp-pill.zero{background:#7d8a94;color:#fff}

        /* compact native widgets */
        [data-testid="stTextInput"] input,
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div{
            min-height:42px!important;
            background:#0a1218!important;
        }
        .stButton > button{
            min-height:40px!important;
            border-radius:8px!important;
        }
        button[data-testid="stBaseButton-primary"]{
            background:#ffc400!important;
            color:#060606!important;
            border-color:#ffc400!important;
            font-weight:900!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# CONFIGURACIÓN
# ============================================================

CHANNELS = (
    "B2C",
    "B2B",
    "NOLK",
)

CHANNEL_LABELS = {
    "B2C": "B2C",
    "B2B": "B2B",
    "NOLK": "NOLK",
}

REINJECTION_ENABLED_CHANNELS = {
    "B2C",
    "B2B",
    "NOLK",
}


# ============================================================
# CARGA API
# ============================================================

@st.cache_data(
    ttl=30,
    show_spinner=False,
)
def _load_pending_orders(
    channel: str,
):
    """
    Consulta Azure y deja el resultado cacheado durante 30 segundos.
    """
    return get_pending_orders(
        channel
    )


def _clear_pending_cache():
    """
    Limpia solamente el caché de esta consulta.
    """
    try:
        _load_pending_orders.clear()
    except Exception:
        st.cache_data.clear()


AUTO_REFRESH_SECONDS = 30


@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS}s")
def _pending_orders_auto_refresh():
    """
    Autoactualiza la lista de pedidos pendientes.

    El TTL del caché por sí solo no refresca la pantalla. Este fragmento
    despierta cada 30 segundos, limpia el caché y relanza la app completa.
    """
    now = datetime.now()
    last_key = "erp_last_auto_refresh"
    last_refresh = st.session_state.get(last_key)

    if last_refresh is None:
        st.session_state[last_key] = now
        return

    try:
        elapsed = (now - last_refresh).total_seconds()
    except Exception:
        elapsed = AUTO_REFRESH_SECONDS

    if elapsed >= AUTO_REFRESH_SECONDS:
        st.session_state[last_key] = now
        # Volver a la primera página permite ver inmediatamente pedidos nuevos.
        channel = st.session_state.get("erp_channel", "B2C") or "B2C"
        st.session_state[f"erp_page_{channel}"] = 1
        _clear_pending_cache()
        st.rerun(scope="app")


# ============================================================
# HELPERS GENERALES
# ============================================================

def _safe_text(
    value: Any,
    default: str = "-",
) -> str:
    if value is None:
        return default

    text = str(
        value
    ).strip()

    if not text:
        return default

    if text.lower() in {
        "none",
        "nan",
        "nat",
    }:
        return default

    return text


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value is None:
            return default

        number = pd.to_numeric(
            value,
            errors="coerce",
        )

        if pd.isna(
            number
        ):
            return default

        return int(
            round(
                float(
                    number
                )
            )
        )

    except Exception:
        return default


def _format_date(
    value: Any,
) -> str:
    if value is None:
        return "-"

    text = str(
        value
    ).strip()

    if not text:
        return "-"

    parsed = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(
        parsed
    ):
        return text

    try:
        return parsed.strftime(
            "%d-%m-%Y %H:%M"
        )
    except Exception:
        return text


def _get_order_vtex_id(
    order: dict,
) -> str:
    try:
        value = extract_vtex_order_id(
            order
        )
    except Exception:
        value = None

    if value:
        return str(
            value
        ).strip()

    for key in (
        "vtexOrderId",
        "orderId",
        "idOrden",
        "pedido",
        "orden",
    ):
        value = order.get(
            key
        )

        if value:
            return str(
                value
            ).strip()

    return "-"


def _diagnosis_category(
    diagnosis: dict,
) -> str:
    value = (
        diagnosis.get(
            "category"
        )
        or diagnosis.get(
            "categoria"
        )
    )

    if value:
        return str(
            value
        ).strip()

    categories = diagnosis.get(
        "categories"
    )

    if isinstance(
        categories,
        (list, tuple),
    ) and categories:
        return " + ".join(
            [
                str(
                    item
                ).strip()
                for item in categories
                if str(
                    item
                ).strip()
            ]
        )

    return "Sin clasificar"


def _diagnosis_reason(
    diagnosis: dict,
) -> str:
    return _safe_text(
        diagnosis.get(
            "reason"
        )
        or diagnosis.get(
            "motivo"
        )
        or diagnosis.get(
            "message"
        )
        or diagnosis.get(
            "summary"
        ),
        "ERP no entregó mensaje de diagnóstico",
    )


def _get_order_diagnosis(
    order: dict,
) -> dict:
    try:
        diagnosis = diagnose_erp_response(
            order.get(
                "response"
            )
        )
    except Exception as exc:
        diagnosis = {
            "category": "Sin clasificar",
            "reason": (
                "No fue posible interpretar "
                f"la respuesta ERP: {exc}"
            ),
        }

    if not isinstance(
        diagnosis,
        dict,
    ):
        diagnosis = {
            "category": "Sin clasificar",
            "reason": _safe_text(
                diagnosis,
                "ERP no entregó mensaje de diagnóstico",
            ),
        }

    return diagnosis


def _category_matches(
    category: str,
    selected_category: str,
) -> bool:
    if selected_category == "Todas":
        return True

    category_normalized = str(
        category
    ).strip().lower()

    selected_normalized = str(
        selected_category
    ).strip().lower()

    return (
        selected_normalized
        in category_normalized
    )


def _status_badge(
    category: str,
) -> str:
    category_lower = str(
        category
    ).lower()

    if "integrado" in category_lower:
        return "✅ Integrado"

    has_stock = "stock" in category_lower
    has_credit = "crédito" in category_lower or "credito" in category_lower
    has_payment = "pago" in category_lower

    if has_credit and has_stock:
        return "⚠️ Crédito + Stock"

    if has_payment and has_stock:
        return "⚠️ Pago + Stock"

    if has_credit and has_payment:
        return "⚠️ Crédito + Pago"

    if has_stock:
        return "📦 Stock"

    if has_credit:
        return "💳 Crédito"

    if has_payment:
        return "💰 Pago"

    if "cliente" in category_lower:
        return "👤 Cliente"

    if "conex" in category_lower:
        return "🌐 Conexión"

    return "⚠️ " + _safe_text(
        category,
        "Sin clasificar",
    )


def _mask_sensitive_xml(
    xml_text: Any,
) -> str:
    """
    Oculta credenciales dentro del XML técnico antes de mostrarlo.
    """
    text = _safe_text(
        xml_text,
        "",
    )

    if not text:
        return ""

    patterns = [
        (
            r"(<password\b[^>]*>)(.*?)(</password>)",
            r"\1********\3",
        ),
        (
            r"(<Password\b[^>]*>)(.*?)(</Password>)",
            r"\1********\3",
        ),
        (
            r"(<PASSWORD\b[^>]*>)(.*?)(</PASSWORD>)",
            r"\1********\3",
        ),
    ]

    for pattern, replacement in patterns:
        text = re.sub(
            pattern,
            replacement,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

    return text


def _ensure_state():
    if "erp_sent_orders" not in st.session_state:
        st.session_state.erp_sent_orders = set()

    if "erp_verification" not in st.session_state:
        st.session_state.erp_verification = {}

    if "erp_reinject_running" not in st.session_state:
        st.session_state.erp_reinject_running = False

    if "erp_unlock_orders" not in st.session_state:
        st.session_state.erp_unlock_orders = set()

    if "erp_selected_order_by_channel" not in st.session_state:
        st.session_state.erp_selected_order_by_channel = {}


# ============================================================
# TABLA DE PEDIDOS
# ============================================================

def _build_rows(
    orders: list[dict],
) -> pd.DataFrame:
    rows = []

    for index, order in enumerate(
        orders
    ):
        diagnosis = _get_order_diagnosis(
            order
        )

        category = _diagnosis_category(
            diagnosis
        )

        rows.append(
            {
                "_index": index,
                "Pedido VTEX": _get_order_vtex_id(
                    order
                ),
                "Cliente": _safe_text(
                    order.get(
                        "rutCliente"
                    )
                ),
                "Fecha": _format_date(
                    order.get(
                        "sendDate"
                    )
                ),
                "Estado": category,
                "Motivo": _diagnosis_reason(
                    diagnosis
                ),
                "Documento ERP": _safe_text(
                    diagnosis.get(
                        "document_number"
                    )
                    or diagnosis.get(
                        "numero"
                    )
                    or diagnosis.get(
                        "correlative"
                    )
                    or diagnosis.get(
                        "correlativo"
                    )
                ),
            }
        )

    result = pd.DataFrame(rows)

    # V2 · Pedidos más recientes primero.
    # El endpoint B2C puede venir ordenado de más antiguo a más nuevo
    # (igual que el portal, donde los pedidos nuevos terminan en la última página).
    # Para operación diaria mostramos siempre lo recién ingresado en la página 1.
    if not result.empty:
        result["_send_dt"] = pd.to_datetime(
            [
                orders[int(idx)].get("sendDate")
                if 0 <= int(idx) < len(orders)
                else None
                for idx in result["_index"]
            ],
            errors="coerce",
        )

        result = (
            result
            .sort_values(
                by=["_send_dt", "_index"],
                ascending=[False, False],
                na_position="last",
            )
            .reset_index(drop=True)
        )

    return result


# ============================================================
# ENCABEZADO DEL PEDIDO
# ============================================================

def _render_order_header(
    channel: str,
    order: dict,
    diagnosis: dict,
):
    category = _diagnosis_category(
        diagnosis
    )

    document_number = (
        diagnosis.get("document_number")
        or diagnosis.get("numero")
        or diagnosis.get("correlative")
        or diagnosis.get("correlativo")
    )

    with st.container(
        border=True
    ):
        st.markdown(
            '<div class="erp-section-kicker">PEDIDO SELECCIONADO</div>'
            '<div class="erp-section-title">Resumen del documento</div>'
            '<div class="erp-section-sub">Datos principales del pedido y su estado actual en el flujo ERP.</div>',
            unsafe_allow_html=True,
        )

        c0, c1, c2, c3, c4 = st.columns(
            [0.75, 1.45, 1.15, 1.05, 1.25],
            gap="small",
        )

        with c0:
            st.metric(
                "Canal",
                channel,
            )

        with c1:
            st.metric(
                "Pedido",
                _get_order_vtex_id(order),
            )

        with c2:
            st.metric(
                "Cliente",
                _safe_text(order.get("rutCliente")),
            )

        with c3:
            st.metric(
                "Documento ERP",
                _safe_text(document_number),
            )

        with c4:
            st.metric(
                "Estado",
                _status_badge(category),
            )

        st.caption(
            f"Fecha de envío: {_format_date(order.get('sendDate'))}"
        )


# ============================================================
# DIAGNÓSTICOS
# ============================================================

def _render_credit_card(
    diagnosis: dict,
):
    reason = _diagnosis_reason(
        diagnosis
    )

    amount = (
        diagnosis.get("credit_amount")
        or diagnosis.get("monto_credito")
    )

    with st.container(
        border=True
    ):
        st.markdown(
            '<div class="erp-section-kicker">CRÉDITO</div>'
            '<div class="erp-section-title">Validación comercial</div>'
            '<div class="erp-section-sub">El ERP detuvo el documento por una condición asociada al crédito del cliente.</div>',
            unsafe_allow_html=True,
        )

        st.warning(
            reason
        )

        if amount not in (None, ""):
            m1, m2 = st.columns([1, 2], gap="small")
            with m1:
                st.metric(
                    "Monto asociado",
                    _safe_text(amount),
                )
            with m2:
                st.caption(
                    "El monto es informativo y proviene del diagnóstico ERP."
                )


def _render_stock_card(
    order: dict,
    diagnosis: dict,
):
    """
    Tarjeta de quiebre de stock enriquecida con:
    - xmlSend
    - Llegadas_OK
    - CD
    - Patronato
    - sugerencia de traslado
    """
    resolution = build_stock_resolution(
        order,
        diagnosis,
    )

    sku = _safe_text(
        resolution.get("sku")
    )
    product_name = _safe_text(
        resolution.get("product_name"),
        "Producto no identificado",
    )
    requested_qty = _safe_int(
        resolution.get("requested_qty")
    )
    missing_qty = _safe_int(
        resolution.get("missing_qty")
    )
    current_warehouse = _safe_text(
        resolution.get("current_warehouse")
    )
    current_location = _safe_text(
        resolution.get("current_location")
    )
    line_number = _safe_text(
        resolution.get("line")
    )
    cd_stock = _safe_int(
        resolution.get("cd_stock")
    )
    patronato_stock = _safe_int(
        resolution.get("patronato_stock")
    )
    suggestion = resolution.get("suggestion") or {}

    with st.container(
        border=True
    ):
        st.markdown(
            '<div class="erp-section-kicker">QUIEBRE DE STOCK</div>'
            '<div class="erp-section-title">Disponibilidad y resolución sugerida</div>'
            '<div class="erp-section-sub">Se cruza la línea del XML enviado al ERP con el stock vigente de Llegadas_OK.</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f"### {product_name}"
        )

        c1, c2, c3, c4 = st.columns(
            4,
            gap="small",
        )

        with c1:
            st.metric(
                "SKU",
                sku,
            )

        with c2:
            st.metric(
                "Cantidad pedida",
                f"{requested_qty} UN" if requested_qty > 0 else "No informada",
            )

        with c3:
            st.metric(
                "Faltante ERP",
                f"{missing_qty} UN" if missing_qty > 0 else "No informado",
            )

        with c4:
            st.metric(
                "Línea ERP",
                line_number,
            )

        st.markdown("##### Bodega del pedido")

        b1, b2 = st.columns(
            2,
            gap="small",
        )

        with b1:
            st.metric(
                "Bodega origen",
                current_warehouse,
            )

        with b2:
            st.metric(
                "Ubicación",
                current_location,
            )

        st.markdown("##### Disponibilidad alternativa")
        st.caption(
            "Stock vigente desde Llegadas_OK. Para esta decisión se consideran solamente CD y Patronato."
        )

        a1, a2 = st.columns(
            2,
            gap="medium",
        )

        with a1:
            with st.container(border=True):
                st.markdown("**CD**")
                st.metric(
                    "Stock disponible",
                    f"{cd_stock} UN",
                )

                if missing_qty > 0 and cd_stock >= missing_qty:
                    st.markdown("🟢 **Puede cubrir el faltante completo**")
                elif cd_stock > 0:
                    st.markdown("🟡 **Cobertura parcial**")
                else:
                    st.markdown("🔴 **Sin stock disponible**")

        with a2:
            with st.container(border=True):
                st.markdown("**PATRONATO**")
                st.metric(
                    "Stock disponible",
                    f"{patronato_stock} UN",
                )

                if missing_qty > 0 and patronato_stock >= missing_qty:
                    st.markdown("🟢 **Puede cubrir el faltante completo**")
                elif patronato_stock > 0:
                    st.markdown("🟡 **Cobertura parcial**")
                else:
                    st.markdown("🔴 **Sin stock disponible**")

        st.markdown("##### Sugerencia de traslado")

        coverage = _safe_text(
            suggestion.get("coverage"),
            "unknown",
        ).lower()
        message = _safe_text(
            suggestion.get("message"),
            "No existe sugerencia disponible.",
        )

        if coverage == "total":
            st.success(f"✅ {message}")
        elif coverage == "combined":
            st.info(f"🔄 {message}")
        elif coverage == "partial":
            st.warning(f"⚠️ {message}")
        elif coverage == "none":
            st.error(f"🔴 {message}")
        else:
            st.info(message)

        movements = suggestion.get("movements") or []

        if movements:
            movement_rows = []

            for movement in movements:
                movement_rows.append(
                    {
                        "Bodega origen": _safe_text(
                            movement.get("warehouse")
                        ),
                        "Cantidad sugerida": _safe_int(
                            movement.get("quantity")
                        ),
                    }
                )

            movement_df = pd.DataFrame(
                movement_rows
            )

            st.dataframe(
                movement_df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Bodega origen": st.column_config.TextColumn(
                        "Bodega origen",
                    ),
                    "Cantidad sugerida": st.column_config.NumberColumn(
                        "Cantidad sugerida",
                        format="%d UN",
                    ),
                },
            )

        if not resolution.get("stock_lookup_ok"):
            st.warning(
                _safe_text(
                    resolution.get("stock_lookup_message"),
                    "No fue posible consultar el stock alternativo.",
                )
            )

        source = _safe_text(
            resolution.get("stock_source"),
            "",
        )
        loaded_at = _safe_text(
            resolution.get("stock_loaded_at"),
            "",
        )

        if source:
            source_text = f"Fuente: {source}"
            if loaded_at:
                source_text += f" · Actualización: {loaded_at}"
            st.caption(source_text)


def _render_generic_diagnosis(
    diagnosis: dict,
):
    with st.container(
        border=True
    ):
        st.markdown(
            '<div class="erp-section-kicker">DIAGNÓSTICO ERP</div>'
            '<div class="erp-section-title">Resultado del procesamiento</div>'
            '<div class="erp-section-sub">Detalle interpretado a partir de la respuesta del ERP.</div>',
            unsafe_allow_html=True,
        )

        st.info(
            _diagnosis_reason(
                diagnosis
            )
        )


def _render_diagnosis_cards(
    channel: str,
    order: dict,
    diagnosis: dict,
):
    category = _diagnosis_category(
        diagnosis
    )

    normalized = category.lower()

    has_credit = (
        "crédito" in normalized
        or "credito" in normalized
    )

    has_stock = (
        "stock" in normalized
    )

    rendered = False

    if has_credit:
        _render_credit_card(
            diagnosis
        )
        rendered = True

    if has_stock:
        _render_stock_card(
            order,
            diagnosis,
        )
        rendered = True

    if not rendered:
        _render_generic_diagnosis(
            diagnosis
        )


# ============================================================
# VERIFICACIÓN POST REINYECCIÓN
# ============================================================

def _find_order_by_vtex_id(
    orders: list[dict],
    order_id: str,
) -> dict | None:
    wanted = str(
        order_id
    ).strip()

    for order in orders:
        if (
            _get_order_vtex_id(
                order
            )
            == wanted
        ):
            return order

    return None


def _verify_reinjected_order(
    channel: str,
    order_id: str,
    previous_response: Any,
):
    """
    Vuelve a consultar el canal correspondiente sin usar el caché anterior.

    Si desaparece de pendientes:
        se considera retirado de la cola de pendientes.

    Si sigue:
        compara la respuesta ERP con la anterior.
    """
    _clear_pending_cache()

    result = _load_pending_orders(
        channel
    )

    if not getattr(
        result,
        "ok",
        False,
    ):
        return {
            "status": "error",
            "message": _safe_text(
                getattr(
                    result,
                    "message",
                    None,
                ),
                "No fue posible verificar el pedido.",
            ),
        }

    orders = extract_orders(
        getattr(
            result,
            "data",
            None,
        )
    )

    current_order = _find_order_by_vtex_id(
        orders,
        order_id,
    )

    if current_order is None:
        return {
            "status": "removed",
            "message": (
                "El pedido ya no aparece en la lista "
                f"de pendientes {channel}."
            ),
        }

    current_response = current_order.get(
        "response"
    )

    if str(
        current_response
    ) == str(
        previous_response
    ):
        diagnosis = _get_order_diagnosis(
            current_order
        )

        return {
            "status": "same",
            "message": (
                "El pedido continúa en pendientes y "
                "mantiene el mismo diagnóstico ERP."
            ),
            "diagnosis": diagnosis,
        }

    diagnosis = _get_order_diagnosis(
        current_order
    )

    return {
        "status": "changed",
        "message": (
            "El pedido continúa en pendientes, "
            "pero la respuesta ERP cambió."
        ),
        "diagnosis": diagnosis,
    }


def _render_reinjection_status(
    channel: str,
    order_id: str,
):
    verification_key = f"{channel}:{order_id}"

    verification = (
        st.session_state.erp_verification.get(
            verification_key
        )
    )

    if not verification:
        return

    status = verification.get(
        "status"
    )

    message = _safe_text(
        verification.get(
            "message"
        )
    )

    if status == "removed":
        st.success(
            f"✅ {message}"
        )

    elif status == "changed":
        st.warning(
            f"⚠️ {message}"
        )

    elif status == "same":
        st.info(
            f"ℹ️ {message}"
        )

    else:
        st.error(
            message
        )

    diagnosis = verification.get(
        "diagnosis"
    )

    if isinstance(
        diagnosis,
        dict,
    ):
        st.caption(
            "Diagnóstico después de verificar"
        )
        st.write(
            _diagnosis_reason(
                diagnosis
            )
        )


# ============================================================
# REINYECCIÓN
# ============================================================

def _render_reinjection(
    channel: str,
    order: dict,
    diagnosis: dict,
):
    order_id = _get_order_vtex_id(
        order
    )

    category = _diagnosis_category(
        diagnosis
    )

    st.markdown(
        "### Reinyección"
    )

    if channel not in REINJECTION_ENABLED_CHANNELS:
        st.info(
            f"La reinyección de {channel} está deshabilitada "
            "hasta confirmar el endpoint correspondiente."
        )
        return

    if "integrado" in category.lower():
        st.success(
            "El diagnóstico indica que este pedido ya fue integrado. "
            "No se habilita reinyección."
        )
        return

    if order_id == "-":
        st.error(
            "No se pudo identificar el ID VTEX del pedido."
        )
        return

    order_session_key = f"{channel}:{order_id}"

    sent_before = (
        order_session_key
        in st.session_state.erp_sent_orders
    )

    unlocked = (
        order_session_key
        in st.session_state.erp_unlock_orders
    )

    if sent_before and not unlocked:
        st.warning(
            "Este pedido ya fue enviado a reinyección durante "
            "esta sesión. Para evitar duplicados, el envío está bloqueado."
        )

        if st.button(
            "Verificar estado del pedido",
            key=f"erp_verify_{order_id}",
            use_container_width=True,
        ):
            with st.spinner(
                "Verificando pedido..."
            ):
                verification = _verify_reinjected_order(
                    channel,
                    order_id,
                    order.get(
                        "response"
                    ),
                )

            st.session_state.erp_verification[
                order_session_key
            ] = verification

            st.session_state.erp_selected_order_by_channel[
                channel
            ] = order_id

            st.rerun()

        _render_reinjection_status(
            channel,
            order_id,
        )

        with st.expander(
            "Opciones avanzadas",
            expanded=False,
        ):
            st.error(
                "Una segunda reinyección puede provocar un duplicado "
                "si el primer intento continúa procesándose."
            )

            risk_confirmed = st.checkbox(
                "Comprendo el riesgo y necesito habilitar otro intento.",
                key=f"erp_unlock_confirm_{order_id}",
            )

            if st.button(
                "Habilitar otro intento",
                key=f"erp_unlock_btn_{order_id}",
                disabled=not risk_confirmed,
                use_container_width=True,
            ):
                st.session_state.erp_unlock_orders.add(
                    order_session_key
                )
                st.rerun()

        return

    st.caption(
        "La reinyección envía nuevamente el pedido al flujo de aprobación. "
        "Una respuesta HTTP 200 confirma que el backend recibió la solicitud, "
        "no que el ERP haya integrado definitivamente el pedido."
    )

    confirmed = st.checkbox(
        (
            f"Confirmo que deseo reinyectar el pedido "
            f"{order_id}."
        ),
        key=f"erp_confirm_{order_id}",
    )

    send_disabled = (
        not confirmed
        or st.session_state.erp_reinject_running
    )

    if st.button(
        f"Reinyectar pedido {channel}",
        key=f"erp_reinject_{order_id}",
        type="primary",
        disabled=send_disabled,
        use_container_width=True,
    ):
        st.session_state.erp_reinject_running = True

        try:
            with st.spinner(
                "Enviando pedido al flujo de aprobación..."
            ):
                result = reinject_order(
                    channel,
                    order_id,
                )

            if getattr(
                result,
                "ok",
                False,
            ):
                st.session_state.erp_sent_orders.add(
                    order_session_key
                )

                st.session_state.erp_selected_order_by_channel[
                    channel
                ] = order_id

                st.session_state.erp_unlock_orders.discard(
                    order_session_key
                )

                st.success(
                    "Solicitud aceptada por el backend."
                )

                st.info(
                    _safe_text(
                        getattr(
                            result,
                            "message",
                            None,
                        ),
                        "El pedido fue enviado al flujo de aprobación.",
                    )
                )

                st.warning(
                    "Todavía no se confirma que el ERP haya integrado "
                    "el documento. Usa la verificación después del envío."
                )

            else:
                st.error(
                    _safe_text(
                        getattr(
                            result,
                            "message",
                            None,
                        ),
                        "La reinyección no fue aceptada.",
                    )
                )

        finally:
            st.session_state.erp_reinject_running = False

        st.rerun()

    _render_reinjection_status(
        channel,
        order_id,
    )


# ============================================================
# INFORMACIÓN OPERATIVA Y TÉCNICA
# ============================================================

def _render_operational_info(
    order: dict,
):
    with st.container(
        border=True
    ):
        st.markdown(
            "### Información operativa"
        )

        c1, c2, c3, c4 = st.columns(
            4
        )

        with c1:
            st.caption(
                "Seguimiento"
            )
            st.markdown(
                f"**{_safe_text(order.get('numSeguimiento'))}**"
            )

        with c2:
            st.caption(
                "Facturado"
            )

            facturado = order.get(
                "facturado"
            )

            if facturado is True:
                value = "Sí"
            elif facturado is False:
                value = "No"
            else:
                value = "No informado"

            st.markdown(
                f"**{value}**"
            )

        with c3:
            st.caption(
                "Crédito"
            )

            credito = order.get(
                "credito"
            )

            if credito is True:
                value = "Sí"
            elif credito is False:
                value = "No"
            else:
                value = "No informado"

            st.markdown(
                f"**{value}**"
            )

        with c4:
            st.caption(
                "Estado ERP"
            )

            diagnosis = _get_order_diagnosis(
                order
            )

            erp_status = (
                diagnosis.get(
                    "erp_status"
                )
                or diagnosis.get(
                    "status"
                )
                or "-"
            )

            st.markdown(
                f"**{_safe_text(erp_status)}**"
            )


def _render_technical_details(
    order: dict,
):
    with st.expander(
        "Detalles técnicos",
        expanded=False,
    ):
        with st.expander(
            "Respuesta ERP",
            expanded=False,
        ):
            response = order.get(
                "response"
            )

            if isinstance(
                response,
                (dict, list),
            ):
                st.json(
                    response
                )
            else:
                st.code(
                    _safe_text(
                        response,
                        "Sin respuesta ERP.",
                    )
                )

        with st.expander(
            "XML enviado",
            expanded=False,
        ):
            xml_send = _mask_sensitive_xml(
                order.get(
                    "xmlSend"
                )
            )

            if xml_send:
                st.code(
                    xml_send,
                    language="xml",
                )
            else:
                st.caption(
                    "El pedido no contiene XML enviado."
                )

        with st.expander(
            "Registro completo",
            expanded=False,
        ):
            safe_order = dict(
                order
            )

            if "xmlSend" in safe_order:
                safe_order[
                    "xmlSend"
                ] = _mask_sensitive_xml(
                    safe_order.get(
                        "xmlSend"
                    )
                )

            st.json(
                safe_order
            )


# ============================================================
# DETALLE COMPLETO
# ============================================================

def _render_order_detail(
    channel: str,
    order: dict,
):
    diagnosis = _get_order_diagnosis(
        order
    )

    _render_order_header(
        channel,
        order,
        diagnosis,
    )

    st.markdown(
        "### Diagnóstico"
    )

    _render_diagnosis_cards(
        channel,
        order,
        diagnosis,
    )

    _render_operational_info(
        order
    )

    _render_reinjection(
        channel,
        order,
        diagnosis,
    )

    _render_technical_details(
        order
    )


def _render_summary_cards(
    rows: pd.DataFrame,
):
    if rows is None or rows.empty:
        return

    states = rows["Estado"].fillna("").astype(str).str.lower()
    total = len(rows)

    credit_count = int(
        (
            states.str.contains("crédito", regex=False)
            | states.str.contains("credito", regex=False)
        ).sum()
    )
    stock_count = int(states.str.contains("stock", regex=False).sum())
    payment_count = int(states.str.contains("pago", regex=False).sum())
    client_count = int(states.str.contains("cliente", regex=False).sum())
    integrated_count = int(states.str.contains("integrado", regex=False).sum())
    unclassified_count = int(states.str.contains("sin clasificar", regex=False).sum())

    def _pct(value: int) -> str:
        if total <= 0:
            return "0% del total"
        return f"{round((value / total) * 100)}% del total"

    cards = [
        ("Pedidos pendientes", total, "Total en ERP", ""),
        ("Crédito", credit_count, _pct(credit_count), "credit"),
        ("Stock", stock_count, _pct(stock_count), "stock"),
        ("Pago", payment_count, _pct(payment_count), "payment"),
        ("Cliente", client_count, _pct(client_count), "client"),
        ("Integrados", integrated_count, _pct(integrated_count), "integrated"),
        ("Sin clasificar", unclassified_count, _pct(unclassified_count), "unclassified"),
    ]

    cols = st.columns(7, gap="small")

    for col, (label, value, hint, cls) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="erp-kpi-card {cls}">
                    <div class="erp-kpi-label">{label}</div>
                    <div class="erp-kpi-value">{value:,}</div>
                    <div class="erp-kpi-hint">{hint}</div>
                </div>
                """.replace(",", "."),
                unsafe_allow_html=True,
            )


# ============================================================
# RENDER PRINCIPAL
# ============================================================

def render():
    _ensure_state()
    _apply_view_styles()
    _pending_orders_auto_refresh()

    st.markdown(
        """
        <div class="erp-page-head">
            <div>
                <h1>Integración ERP</h1>
                <p>Pedidos B2C, B2B y NOLK: diagnóstico operativo, stock alternativo y reinyección controlada.</p>
            </div>
            <div class="erp-live-pill"><i></i>ERP activo · autoactualiza cada 30 s</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top1, top2 = st.columns([3.2, 1], gap="large")

    with top1:
        channel = st.segmented_control(
            "Canal",
            options=list(CHANNELS),
            default="B2C",
            format_func=lambda value: CHANNEL_LABELS.get(value, value),
            key="erp_channel",
        )
        if not channel:
            channel = "B2C"

    with top2:
        st.markdown(
            f"""
            <div class="erp-top-info">
                <div class="erp-last-update">
                    Última actualización
                    <strong>{datetime.now().strftime("%d-%m-%Y %H:%M")}</strong>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            "Actualizar",
            key="erp_refresh",
            use_container_width=True,
            type="primary",
            icon=":material/refresh:",
        ):
            st.session_state["erp_last_auto_refresh"] = datetime.now()
            st.session_state[f"erp_page_{channel}"] = 1
            _clear_pending_cache()
            st.rerun()

    with st.spinner(f"Consultando pedidos {channel}..."):
        result = _load_pending_orders(channel)

    if not getattr(result, "ok", False):
        st.error(
            _safe_text(
                getattr(result, "message", None),
                "No fue posible consultar los pedidos pendientes.",
            )
        )
        return

    orders = extract_orders(
        getattr(result, "data", None)
    )

    if not orders:
        st.success(f"No existen pedidos pendientes para {channel}.")
        return

    rows = _build_rows(orders)
    _render_summary_cards(rows)

    st.markdown("<div class='erp-toolbar'></div>", unsafe_allow_html=True)

    f1, f2, f3 = st.columns([2.0, 1.0, .8], gap="small")

    with f1:
        search = st.text_input(
            "Buscar pedido",
            placeholder="Pedido VTEX, cliente, documento ERP o motivo...",
            key="erp_search",
        )

    categories = [
        "Todas",
        "Crédito",
        "Stock",
        "Pago",
        "Cliente",
        "Integrado",
        "Sin clasificar",
    ]

    with f2:
        category_filter = st.selectbox(
            "Categoría",
            categories,
            key="erp_category_filter",
        )

    with f3:
        only_errors = st.selectbox(
            "Estado",
            ["Todos", "Con error", "Integrados"],
            key="erp_status_filter_v3",
        )

    filtered = rows.copy()

    if search:
        query = str(search).strip().lower()
        mask = pd.Series(False, index=filtered.index)

        for column in (
            "Pedido VTEX",
            "Cliente",
            "Documento ERP",
            "Estado",
            "Motivo",
        ):
            mask = (
                mask
                | filtered[column]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.contains(query, regex=False)
            )
        filtered = filtered[mask]

    if category_filter != "Todas":
        filtered = filtered[
            filtered["Estado"].apply(
                lambda value: _category_matches(
                    value,
                    category_filter,
                )
            )
        ]

    if only_errors == "Con error":
        filtered = filtered[
            ~filtered["Estado"].fillna("").astype(str).str.lower().str.contains(
                "integrado",
                regex=False,
            )
        ]
    elif only_errors == "Integrados":
        filtered = filtered[
            filtered["Estado"].fillna("").astype(str).str.lower().str.contains(
                "integrado",
                regex=False,
            )
        ]

    if filtered.empty:
        st.info("No hay pedidos que coincidan con los filtros.")
        return

    page_size = 10
    total_filtered = len(filtered)
    total_pages = max((total_filtered + page_size - 1) // page_size, 1)
    page_key = f"erp_page_{channel}"

    if page_key not in st.session_state:
        st.session_state[page_key] = 1

    current_page = max(
        1,
        min(
            int(st.session_state.get(page_key, 1) or 1),
            total_pages,
        ),
    )
    st.session_state[page_key] = current_page

    start_row = (current_page - 1) * page_size
    end_row = min(start_row + page_size, total_filtered)
    page_filtered = filtered.iloc[start_row:end_row].copy()

    persisted_order_id = _safe_text(
        st.session_state.erp_selected_order_by_channel.get(channel),
        "",
    )

    if not persisted_order_id:
        persisted_order_id = _safe_text(
            page_filtered.iloc[0]["Pedido VTEX"],
            "",
        )
        st.session_state.erp_selected_order_by_channel[channel] = persisted_order_id

    left, right = st.columns([1.62, 1.0], gap="small")

    # =========================================================
    # LEFT · TABLE
    # =========================================================
    with left:
        st.markdown(
            f"""
            <div class="erp-table-hint">
                <span><strong>{start_row + 1}–{end_row}</strong> de {total_filtered:,} pedidos</span>
                <span>Más recientes primero</span>
            </div>
            """.replace(",", "."),
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div class="erp-table-shell">
                <div class="erp-table-head">
                    <div>VTEX ORDER</div>
                    <div>FECHA</div>
                    <div>RUT CLIENTE</div>
                    <div>CATEGORÍA</div>
                    <div>MOTIVO PRINCIPAL</div>
                    <div>ESTADO</div>
                    <div>ACCIÓN</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # native rows + buttons to preserve stable interaction
        for pos, (_, row) in enumerate(page_filtered.iterrows()):
            order_id = _safe_text(row["Pedido VTEX"])
            category = _safe_text(row["Estado"], "Sin clasificar")
            reason = _safe_text(row["Motivo"])
            client = _safe_text(row["Cliente"])
            date_text = _safe_text(row["Fecha"])
            is_integrated = "integrado" in category.lower()

            cat_norm = category.lower()
            if "crédito" in cat_norm or "credito" in cat_norm:
                badge_cls = "credit"
            elif "stock" in cat_norm:
                badge_cls = "stock"
            elif "pago" in cat_norm:
                badge_cls = "payment"
            elif "cliente" in cat_norm:
                badge_cls = "client"
            elif "integrado" in cat_norm:
                badge_cls = "integrated"
            elif "sin clasificar" in cat_norm:
                badge_cls = "unclassified"
            else:
                badge_cls = "other"

            selected_cls = "selected" if order_id == persisted_order_id else ""

            rc = st.columns([1.45, .85, 1.0, .95, 1.7, .8, .65], gap="small")

            with rc[0]:
                st.markdown(
                    f"<div class='erp-cell {selected_cls}'><b>{order_id}</b></div>",
                    unsafe_allow_html=True,
                )
            with rc[1]:
                st.markdown(
                    f"<div class='erp-cell'>{date_text}</div>",
                    unsafe_allow_html=True,
                )
            with rc[2]:
                st.markdown(
                    f"<div class='erp-cell'>{client}</div>",
                    unsafe_allow_html=True,
                )
            with rc[3]:
                st.markdown(
                    f"<div class='erp-cell'><span class='erp-badge {badge_cls}'>{category}</span></div>",
                    unsafe_allow_html=True,
                )
            with rc[4]:
                short_reason = reason if len(reason) <= 46 else reason[:43].rstrip() + "…"
                st.markdown(
                    f"<div class='erp-cell'>{short_reason}</div>",
                    unsafe_allow_html=True,
                )
            with rc[5]:
                state_cls = "ok" if is_integrated else "err"
                state_text = "OK" if is_integrated else "Error"
                st.markdown(
                    f"<div class='erp-cell'><span class='erp-state-dot {state_cls}'></span>{state_text}</div>",
                    unsafe_allow_html=True,
                )
            with rc[6]:
                if st.button(
                    "Ver",
                    key=f"erp_row_open_{channel}_{current_page}_{pos}_{order_id}",
                    use_container_width=True,
                    type="primary" if order_id == persisted_order_id else "secondary",
                ):
                    st.session_state.erp_selected_order_by_channel[channel] = order_id
                    st.rerun()

        n1, n2, n3 = st.columns([1, 2, 1], gap="small")
        with n1:
            if st.button(
                "‹",
                key=f"erp_prev_{channel}",
                disabled=current_page <= 1,
                use_container_width=True,
            ):
                st.session_state[page_key] = current_page - 1
                st.rerun()

        with n2:
            st.markdown(
                f'<div class="erp-page-indicator">Página <strong>{current_page}</strong> de {total_pages}</div>',
                unsafe_allow_html=True,
            )

        with n3:
            if st.button(
                "›",
                key=f"erp_next_{channel}",
                disabled=current_page >= total_pages,
                use_container_width=True,
            ):
                st.session_state[page_key] = current_page + 1
                st.rerun()

    # =========================================================
    # RIGHT · DETAIL
    # =========================================================
    selected_matches = rows[
        rows["Pedido VTEX"].astype(str) == str(persisted_order_id)
    ]

    if selected_matches.empty:
        st.session_state.erp_selected_order_by_channel[channel] = _safe_text(
            filtered.iloc[0]["Pedido VTEX"],
            "",
        )
        st.rerun()

    selected_index = int(
        selected_matches.iloc[0]["_index"]
    )

    if selected_index < 0 or selected_index >= len(orders):
        st.error("No fue posible resolver el pedido seleccionado.")
        return

    selected_order = orders[selected_index]
    diagnosis = _get_order_diagnosis(selected_order)
    category = _diagnosis_category(diagnosis)
    reason = _diagnosis_reason(diagnosis)
    order_id = _get_order_vtex_id(selected_order)
    rut = _safe_text(selected_order.get("rutCliente"))
    send_date = _format_date(selected_order.get("sendDate"))
    erp_status = _safe_text(
        diagnosis.get("erp_status")
        or diagnosis.get("status")
    )
    document_type = _safe_text(
        diagnosis.get("document_type")
    )
    document_number = _safe_text(
        diagnosis.get("document_number")
        or diagnosis.get("numero")
        or diagnosis.get("correlative")
    )
    message = _safe_text(
        diagnosis.get("message")
        or diagnosis.get("summary")
        or reason
    )

    with right:
        detail_html = (
            f'<div class="erp-detail-panel">'
            f'<div class="erp-detail-title">Detalle del pedido</div>'
            f'<div class="erp-detail-order">{order_id}</div>'
            f'<div class="erp-detail-meta">{channel} &nbsp; | &nbsp; {send_date}</div>'
            f'<div class="erp-detail-grid">'
            f'<div class="erp-detail-item"><span>RUT Cliente</span><b>{rut}</b></div>'
            f'<div class="erp-detail-item"><span>Estado ERP</span><b>{erp_status}</b></div>'
            f'<div class="erp-detail-item"><span>Categoría</span><b>{category}</b></div>'
            f'<div class="erp-detail-item"><span>Documento ERP</span><b>{document_type}</b></div>'
            f'<div class="erp-detail-item"><span>N° Documento</span><b>{document_number}</b></div>'
            f'</div>'
            f'<div class="erp-error-box">'
            f'<div class="k">Motivo del error</div>'
            f'<div class="v">{reason}</div>'
            f'</div>'
            f'<div class="erp-message-box">{message}</div>'
            f'</div>'
        )
        st.markdown(
            detail_html,
            unsafe_allow_html=True,
        )

        # Existing functionality preserved below the compact summary
        st.markdown("")
        _render_diagnosis_cards(
            channel,
            selected_order,
            diagnosis,
        )

        _render_reinjection(
            channel,
            selected_order,
            diagnosis,
        )

        with st.expander("Ver diagnóstico completo", expanded=False):
            _render_operational_info(selected_order)
            _render_technical_details(selected_order)

