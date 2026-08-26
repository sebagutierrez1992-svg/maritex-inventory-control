import re
from textwrap import dedent

import streamlit as st


# ============================================================
# HEADER SIMPLE
# ============================================================

def page_header(
    title: str,
    subtitle: str = "",
    eyebrow: str = "",
):
    """
    Encabezado simple reutilizable para vistas que todavía
    utilizan componentes nativos de Streamlit.
    """

    if eyebrow:
        st.caption(eyebrow)

    st.title(title)

    if subtitle:
        st.caption(subtitle)


# ============================================================
# ESTADO DE FUENTE
# ============================================================

def source_status(
    label: str,
    filename: str | None,
    extra: str = "",
):
    """
    Muestra el estado de una fuente cargada.
    """

    if filename:
        st.success(
            f"✓ {label}: {filename}"
        )

        if extra:
            st.caption(extra)

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
):
    """
    Título simple de sección.
    """

    st.subheader(title)

    if subtitle:
        st.caption(subtitle)


# ============================================================
# HTML VISUAL
# ============================================================

def render_html(
    content: str,
) -> None:
    """
    Renderiza bloques HTML del dashboard.

    IMPORTANTE:
    Utilizamos st.html() en lugar de
    st.markdown(..., unsafe_allow_html=True).

    Esto evita que Streamlit interprete partes del HTML
    como Markdown o bloques de código, especialmente en
    componentes multilínea como:

    - tarjetas
    - KPI
    - sidebar
    - reglas
    - alertas
    - encabezados
    """

    if content is None:
        return

    clean = dedent(
        str(content)
    ).strip()

    if not clean:
        return

    # --------------------------------------------------------
    # Quitar espacios innecesarios entre tags.
    #
    # Ejemplo:
    #
    # </div>
    # <div>
    #
    # pasa a:
    #
    # </div><div>
    # --------------------------------------------------------

    clean = re.sub(
        r">\s+<",
        "><",
        clean,
    )

    # --------------------------------------------------------
    # Eliminar tabulaciones / saltos excesivos que puedan
    # producir comportamiento inesperado.
    # --------------------------------------------------------

    clean = clean.replace(
        "\t",
        " ",
    )

    # --------------------------------------------------------
    # Render HTML real.
    # --------------------------------------------------------

    st.html(
        clean
    )