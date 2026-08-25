from pathlib import Path
import streamlit as st


def apply_styles(css_path: Path) -> None:
    if not css_path.exists():
        return
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
