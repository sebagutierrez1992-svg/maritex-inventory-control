import re
from html import escape
from textwrap import dedent

import streamlit as st


# ============================================================
# HEADER GLOBAL MARITEX
# ============================================================

def page_header(
    title: str,
    subtitle: str = "",
    eyebrow: str = "",
    status: str = "Sistema conectado",
    updated: str = "",
) -> None:
    """
    Encabezado visual global estilo Maritex.

    Parámetros:
    - title: título principal de la vista.
    - subtitle: descripción secundaria.
    - eyebrow: texto pequeño opcional sobre el título.
    - status: badge de estado ubicado a la derecha.
    - updated: fecha/hora de última actualización opcional.

    Ejemplo:
        page_header(
            title="CRM",
            subtitle=(
                "Resumen ejecutivo, clientes, oportunidades, "
                "seguimientos y tubería comercial."
            ),
            status="ERP + PostgreSQL conectados",
        )
    """

    safe_title = escape(
        str(title or "").strip()
    )

    safe_subtitle = escape(
        str(subtitle or "").strip()
    )

    safe_eyebrow = escape(
        str(eyebrow or "").strip()
    )

    safe_status = escape(
        str(
            status
            or "Sistema conectado"
        ).strip()
    )

    safe_updated = escape(
        str(updated or "").strip()
    )

    eyebrow_html = (
        f"""
        <div class="mx-page-eyebrow">
            {safe_eyebrow}
        </div>
        """
        if safe_eyebrow
        else ""
    )

    subtitle_html = (
        f"""
        <div class="mx-page-subtitle">
            {safe_subtitle}
        </div>
        """
        if safe_subtitle
        else ""
    )

    updated_html = (
        f"""
        <div class="mx-page-updated">
            Última actualización:
            {safe_updated}
        </div>
        """
        if safe_updated
        else ""
    )

    render_html(
        f"""
        <div class="mx-page-header">

            <div class="mx-page-header-copy">

                {eyebrow_html}

                <div class="mx-page-title">
                    {safe_title}
                </div>

                {subtitle_html}

            </div>

            <div class="mx-page-status-wrap">

                <div class="mx-page-status">
                    <span class="mx-page-status-dot"></span>
                    {safe_status}
                </div>

                {updated_html}

            </div>

        </div>
        """
    )


# ============================================================
# HEADER SIMPLE LEGACY
# ============================================================

def simple_page_header(
    title: str,
    subtitle: str = "",
    eyebrow: str = "",
) -> None:
    """
    Encabezado simple basado en componentes nativos Streamlit.

    Se mantiene por compatibilidad con vistas antiguas que todavía
    no utilizan el header global Maritex.
    """

    if eyebrow:
        st.caption(
            eyebrow
        )

    st.title(
        title
    )

    if subtitle:
        st.caption(
            subtitle
        )


# ============================================================
# ESTADO DE FUENTE
# ============================================================

def source_status(
    label: str,
    filename: str | None,
    extra: str = "",
) -> None:
    """
    Muestra el estado de una fuente cargada.
    """

    if filename:
        st.success(
            f"✓ {label}: {filename}"
        )

        if extra:
            st.caption(
                extra
            )

    else:
        st.warning(
            f"{label}: sin fuente cargada"
        )


# ============================================================
# TÍTULO DE SECCIÓN
# ============================================================

def section_title(
    title: str,
    subtitle: str = "",
) -> None:
    """
    Título simple de sección.
    """

    st.subheader(
        title
    )

    if subtitle:
        st.caption(
            subtitle
        )


# ============================================================
# TÍTULO DE SECCIÓN VISUAL MARITEX
# ============================================================

def visual_section_title(
    title: str,
    subtitle: str = "",
) -> None:
    """
    Título visual reutilizable para bloques internos.
    """

    safe_title = escape(
        str(title or "").strip()
    )

    safe_subtitle = escape(
        str(subtitle or "").strip()
    )

    subtitle_html = (
        f"""
        <div class="mx-section-subtitle">
            {safe_subtitle}
        </div>
        """
        if safe_subtitle
        else ""
    )

    render_html(
        f"""
        <div class="mx-section-header">

            <div class="mx-section-title">
                {safe_title}
            </div>

            {subtitle_html}

        </div>
        """
    )


# ============================================================
# BADGE DE ESTADO
# ============================================================

def status_badge(
    text: str,
    tone: str = "green",
) -> None:
    """
    Badge visual de estado.

    tone:
    - green
    - yellow
    - red
    - blue
    - gray
    """

    safe_text = escape(
        str(text or "").strip()
    )

    valid_tones = {
        "green",
        "yellow",
        "red",
        "blue",
        "gray",
    }

    if tone not in valid_tones:
        tone = "gray"

    render_html(
        f"""
        <div class="mx-status-badge {tone}">
            <span></span>
            {safe_text}
        </div>
        """
    )


# ============================================================
# KPI SIMPLE
# ============================================================

def metric_card(
    label: str,
    value: str,
    subtitle: str = "",
    tone: str = "yellow",
) -> None:
    """
    KPI reutilizable tipo Maritex.
    """

    safe_label = escape(
        str(label or "").strip()
    )

    safe_value = escape(
        str(value or "").strip()
    )

    safe_subtitle = escape(
        str(subtitle or "").strip()
    )

    valid_tones = {
        "green",
        "blue",
        "purple",
        "yellow",
        "red",
        "gray",
    }

    if tone not in valid_tones:
        tone = "gray"

    subtitle_html = (
        f"""
        <div class="mx-metric-sub">
            {safe_subtitle}
        </div>
        """
        if safe_subtitle
        else ""
    )

    render_html(
        f"""
        <div class="mx-metric-card {tone}">

            <div class="mx-metric-label">
                {safe_label}
            </div>

            <div class="mx-metric-value">
                {safe_value}
            </div>

            {subtitle_html}

        </div>
        """
    )


# ============================================================
# EMPTY STATE
# ============================================================

def empty_state(
    title: str,
    message: str = "",
) -> None:
    """
    Estado vacío reutilizable.
    """

    safe_title = escape(
        str(title or "").strip()
    )

    safe_message = escape(
        str(message or "").strip()
    )

    message_html = (
        f"""
        <div class="mx-empty-message">
            {safe_message}
        </div>
        """
        if safe_message
        else ""
    )

    render_html(
        f"""
        <div class="mx-empty-state">

            <div class="mx-empty-icon">
                —
            </div>

            <div class="mx-empty-title">
                {safe_title}
            </div>

            {message_html}

        </div>
        """
    )


# ============================================================
# HTML VISUAL
# ============================================================

def render_html(
    content: str,
) -> None:
    """
    Renderiza bloques HTML reales del dashboard.

    Utilizamos st.html() en lugar de:

        st.markdown(
            ...,
            unsafe_allow_html=True,
        )

    Esto evita que Streamlit interprete partes del HTML
    como Markdown o bloques de código, especialmente en:

    - tarjetas
    - KPI
    - sidebar
    - alertas
    - encabezados
    - tablas
    - badges
    """

    if content is None:
        return

    clean = dedent(
        str(content)
    ).strip()

    if not clean:
        return

    # --------------------------------------------------------
    # Compactar espacios entre tags
    # --------------------------------------------------------

    clean = re.sub(
        r">\s+<",
        "><",
        clean,
    )

    # --------------------------------------------------------
    # Eliminar tabulaciones
    # --------------------------------------------------------

    clean = clean.replace(
        "\t",
        " ",
    )

    # --------------------------------------------------------
    # Render HTML real
    # --------------------------------------------------------

    st.html(
        clean
    )