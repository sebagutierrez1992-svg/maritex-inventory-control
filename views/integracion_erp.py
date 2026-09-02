

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
        """
        <style>
        /* Cabecera */
        .erp-page-head {
            display:flex;
            align-items:flex-end;
            justify-content:space-between;
            gap:18px;
            padding:4px 2px 14px 2px;
            margin-bottom:4px;
        }
        .erp-page-head h1 {
            margin:0;
            font-size:2rem;
            line-height:1.05;
            letter-spacing:-.03em;
            color:#f7f9fb;
        }
        .erp-page-head p {
            margin:7px 0 0 0;
            color:#94a3af;
            font-size:.9rem;
        }
        .erp-live-pill {
            display:inline-flex;
            align-items:center;
            gap:8px;
            padding:7px 11px;
            border:1px solid rgba(255,196,0,.22);
            border-radius:999px;
            background:rgba(255,196,0,.07);
            color:#e8edf2;
            font-size:.78rem;
            white-space:nowrap;
        }
        .erp-live-pill i {
            display:block;
            width:7px;
            height:7px;
            border-radius:999px;
            background:#ffc400;
            box-shadow:0 0 0 4px rgba(255,196,0,.10);
        }

        /* Tarjetas nativas */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color:#2d3d49 !important;
            border-radius:14px !important;
            background:linear-gradient(180deg, rgba(18,30,40,.96), rgba(15,26,35,.96)) !important;
            box-shadow:0 8px 24px rgba(0,0,0,.10);
        }

        /* Métricas */
        div[data-testid="stMetric"] {
            border:1px solid #2d3d49;
            border-radius:12px;
            background:#111d27;
            padding:12px 14px;
            min-height:92px;
        }
        div[data-testid="stMetricLabel"] {
            color:#93a2ae !important;
            font-size:.78rem !important;
            font-weight:650 !important;
        }
        div[data-testid="stMetricValue"] {
            color:#f6f8fa !important;
            font-size:1.65rem !important;
            line-height:1.15 !important;
        }

        /* Dataframe */
        div[data-testid="stDataFrame"] {
            border:1px solid #2d3d49;
            border-radius:13px;
            overflow:hidden;
            background:#101b24;
        }

        /* Separadores */
        hr {
            border-color:#2b3a45 !important;
            opacity:.85;
        }

        /* Textos secundarios */
        .erp-section-kicker {
            color:#ffc400;
            text-transform:uppercase;
            letter-spacing:.08em;
            font-size:.68rem;
            font-weight:800;
            margin-bottom:2px;
        }
        .erp-section-title {
            color:#f7f9fb;
            font-size:1.02rem;
            font-weight:800;
            margin:0 0 3px 0;
        }
        .erp-section-sub {
            color:#8f9da8;
            font-size:.79rem;
            margin-bottom:10px;
        }

        /* Tabla: instrucción clic */
        .erp-table-hint {
            display:flex;
            align-items:center;
            justify-content:space-between;
            gap:10px;
            color:#90a0ac;
            font-size:.76rem;
            margin:2px 0 8px 0;
        }
        .erp-table-hint strong {
            color:#dce3e8;
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

    return pd.DataFrame(
        rows
    )


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
    stock_count = int(states.str.contains("stock", regex=False).sum())
    credit_count = int(
        (
            states.str.contains("crédito", regex=False)
            | states.str.contains("credito", regex=False)
        ).sum()
    )
    other_count = max(total - stock_count - credit_count, 0)

    c1, c2, c3, c4 = st.columns(4, gap="small")

    with c1:
        st.metric("Pendientes", total)
    with c2:
        st.metric("Con problema de stock", stock_count)
    with c3:
        st.metric("Con problema de crédito", credit_count)
    with c4:
        st.metric("Otros diagnósticos", other_count)


# ============================================================
# RENDER PRINCIPAL
# ============================================================

def render():
    _ensure_state()
    _apply_view_styles()

    st.markdown(
        """
        <div class="erp-page-head">
            <div>
                <h1>Integración ERP</h1>
                <p>Pedidos B2C, B2B y NOLK: diagnóstico operativo, stock alternativo y reinyección controlada.</p>
            </div>
            <div class="erp-live-pill"><i></i>Conexión ERP activa</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top1, top2 = st.columns(
        [3, 1]
    )

    with top1:
        channel = st.segmented_control(
            "Canal",
            options=list(CHANNELS),
            default="B2C",
            format_func=lambda value: CHANNEL_LABELS.get(
                value,
                value,
            ),
            key="erp_channel",
        )

        if not channel:
            channel = "B2C"

    with top2:
        st.write("")
        st.write("")

        if st.button(
            "Actualizar",
            key="erp_refresh",
            use_container_width=True,
            icon=":material/refresh:",
        ):
            _clear_pending_cache()
            st.rerun()

    with st.spinner(
        f"Consultando pedidos {channel}..."
    ):
        result = _load_pending_orders(
            channel
        )

    if not getattr(
        result,
        "ok",
        False,
    ):
        st.error(
            _safe_text(
                getattr(
                    result,
                    "message",
                    None,
                ),
                "No fue posible consultar los pedidos pendientes.",
            )
        )
        return

    orders = extract_orders(
        getattr(
            result,
            "data",
            None,
        )
    )

    if not orders:
        st.success(
            f"No existen pedidos pendientes para {channel}."
        )
        return

    rows = _build_rows(
        orders
    )

    _render_summary_cards(
        rows
    )

    st.markdown("")

    categories = [
        "Todas",
        "Crédito",
        "Stock",
        "Pago",
        "Cliente",
        "Integrado",
        "Sin clasificar",
    ]

    f1, f2 = st.columns(
        [2, 1]
    )

    with f1:
        search = st.text_input(
            "Buscar pedido",
            placeholder=(
                "Pedido VTEX, cliente, documento ERP o motivo..."
            ),
            key="erp_search",
        )

    with f2:
        category_filter = st.selectbox(
            "Tipo de diagnóstico",
            categories,
            key="erp_category_filter",
        )

    filtered = rows.copy()

    if search:
        query = str(search).strip().lower()

        mask = pd.Series(
            False,
            index=filtered.index,
        )

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
                .str.contains(
                    query,
                    regex=False,
                )
            )

        filtered = filtered[
            mask
        ]

    if category_filter != "Todas":
        filtered = filtered[
            filtered["Estado"].apply(
                lambda value: _category_matches(
                    value,
                    category_filter,
                )
            )
        ]

    if filtered.empty:
        st.info(
            "No hay pedidos que coincidan con los filtros."
        )
        return

    st.markdown(
        f"""
        <div class="erp-table-hint">
            <span><strong>{len(filtered):,}</strong> de {len(rows):,} pedidos visibles</span>
            <span>Haz clic en una fila para revisar el pedido</span>
        </div>
        """.replace(",", "."),
        unsafe_allow_html=True,
    )

    display = filtered[
        [
            "Pedido VTEX",
            "Cliente",
            "Fecha",
            "Estado",
            "Documento ERP",
            "Motivo",
        ]
    ].copy()

    table_event = st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=min(
            430,
            38 + len(display) * 35,
        ),
        key=f"erp_orders_table_{channel}",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Pedido VTEX": st.column_config.TextColumn(
                "Pedido",
                width="medium",
            ),
            "Cliente": st.column_config.TextColumn(
                "Cliente",
                width="small",
            ),
            "Fecha": st.column_config.TextColumn(
                "Fecha",
                width="medium",
            ),
            "Estado": st.column_config.TextColumn(
                "Estado",
                width="medium",
            ),
            "Documento ERP": st.column_config.TextColumn(
                "Documento ERP",
                width="small",
            ),
            "Motivo": st.column_config.TextColumn(
                "Motivo",
                width="large",
            ),
        },
    )

    selected_position = None
    selected_order_id = None

    try:
        selected_rows = list(
            table_event.selection.rows
        )
        if selected_rows:
            selected_position = int(
                selected_rows[0]
            )
    except Exception:
        selected_position = None

    # Si el usuario hizo clic en una fila, esa selección pasa a ser
    # la selección persistente del canal.
    if selected_position is not None:
        if (
            selected_position < 0
            or selected_position >= len(filtered)
        ):
            st.error(
                "No fue posible resolver el pedido seleccionado."
            )
            return

        selected_order_id = _safe_text(
            filtered.iloc[
                selected_position
            ]["Pedido VTEX"],
            "",
        )

        if selected_order_id:
            st.session_state.erp_selected_order_by_channel[
                channel
            ] = selected_order_id

    # Si no hay clic activo en la tabla (por ejemplo después de un rerun),
    # recuperamos el pedido persistido para este canal.
    if not selected_order_id:
        persisted_order_id = _safe_text(
            st.session_state.erp_selected_order_by_channel.get(
                channel
            ),
            "",
        )

        if persisted_order_id:
            matches = filtered[
                filtered["Pedido VTEX"].astype(str)
                == persisted_order_id
            ]

            if not matches.empty:
                selected_order_id = persisted_order_id

    # Solo usamos la primera fila cuando el usuario aún no ha seleccionado
    # ningún pedido en este canal.
    if not selected_order_id:
        selected_order_id = _safe_text(
            filtered.iloc[0]["Pedido VTEX"],
            "",
        )

        if selected_order_id:
            st.session_state.erp_selected_order_by_channel[
                channel
            ] = selected_order_id

    # Resolver el índice real del pedido desde el dataframe completo.
    selected_matches = rows[
        rows["Pedido VTEX"].astype(str)
        == str(selected_order_id)
    ]

    if selected_matches.empty:
        # El pedido pudo desaparecer de pendientes después de verificar.
        # En ese caso mostramos el resultado de verificación y no saltamos
        # silenciosamente a otro pedido.
        verification_key = (
            f"{channel}:{selected_order_id}"
        )

        verification = st.session_state.erp_verification.get(
            verification_key
        )

        if verification:
            st.divider()
            st.markdown(
                f"### Resultado de verificación · {channel} · {selected_order_id}"
            )
            _render_reinjection_status(
                channel,
                selected_order_id,
            )
            return

        st.error(
            "El pedido seleccionado ya no está disponible en la lista actual."
        )
        return

    selected_index = int(
        selected_matches.iloc[0]["_index"]
    )

    if (
        selected_index < 0
        or selected_index >= len(orders)
    ):
        st.error(
            "No fue posible resolver el pedido seleccionado."
        )
        return

    selected_order = orders[
        selected_index
    ]

    st.divider()

    _render_order_detail(
        channel,
        selected_order,
    )

