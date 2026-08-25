import streamlit as st


def page_header(title: str, subtitle: str = "", eyebrow: str = ""):
    if eyebrow:
        st.caption(eyebrow)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def source_status(label: str, filename: str | None, extra: str = ""):
    if filename:
        st.success(f"✓ {label}: {filename}")
        if extra:
            st.caption(extra)
    else:
        st.warning(f"{label}: sin fuente cargada")


def section_title(title: str, subtitle: str = ""):
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)
