from __future__ import annotations

import streamlit as st

from services.auth_service import (
    authenticate_user,
)
from ui.components import render_html


# ============================================================
# ESTILOS
# ============================================================

def _inject_login_styles() -> None:
    st.markdown(
        """
        <style>

        /* =====================================================
           LOGIN MARITEX
           ===================================================== */

        [data-testid="stAppViewContainer"]{
            background:
                radial-gradient(
                    circle at 80% 0%,
                    rgba(255,196,0,.055),
                    transparent 26%
                ),
                #050A0E !important;
        }

        [data-testid="stHeader"]{
            background:transparent !important;
        }

        [data-testid="stMainBlockContainer"]{
            max-width:520px !important;
            padding-top:7vh !important;
        }

        .login-brand{
            text-align:center;
            margin-bottom:24px;
        }

        .login-brand img{
            max-width:210px;
            height:auto;
        }

        .login-card-head{
            padding:28px 30px 18px;

            border:1px solid #30414A;
            border-bottom:0;

            border-radius:14px 14px 0 0;

            background:
                linear-gradient(
                    135deg,
                    #091217 0%,
                    #07100D 100%
                );

            border-left:5px solid #FFC400;
        }

        .login-eyebrow{
            color:#FFC400;

            font-size:9px;
            font-weight:850;

            letter-spacing:.12em;
            text-transform:uppercase;
        }

        .login-title{
            margin-top:10px;

            color:#FFFFFF;

            font-size:30px;
            line-height:1;

            font-weight:900;

            letter-spacing:-.7px;
        }

        .login-subtitle{
            margin-top:12px;

            color:#9FB0BB;

            font-size:11px;
            line-height:1.5;
        }

        .login-system{
            display:flex;
            align-items:center;
            justify-content:center;

            gap:8px;

            margin-top:22px;

            color:#788C98;

            font-size:9px;
        }

        .login-system i{
            width:8px;
            height:8px;

            border-radius:50%;

            background:#23D487;

            box-shadow:
                0 0 0 4px rgba(35,212,135,.10);
        }

        div[data-testid="stForm"]{
            padding:24px 30px 28px !important;

            background:#081118 !important;

            border:1px solid #30414A !important;
            border-top:0 !important;

            border-radius:0 0 14px 14px !important;
        }

        div[data-testid="stTextInput"] label p{
            color:#D8E2E8 !important;

            font-size:10px !important;
            font-weight:800 !important;
        }

        div[data-testid="stTextInput"] input{
            min-height:48px !important;

            background:#0D1A23 !important;

            color:#FFFFFF !important;

            border:1px solid #304957 !important;

            border-radius:9px !important;
        }

        div[data-testid="stTextInput"] input:focus{
            border-color:#FFC400 !important;

            box-shadow:
                0 0 0 1px #FFC400 !important;
        }

        div[data-testid="stTextInput"] input::placeholder{
            color:#657985 !important;
        }

        button[data-testid="stBaseButton-primary"]{
            width:100% !important;

            min-height:48px !important;

            margin-top:10px !important;

            background:#FFC400 !important;

            border:1px solid #FFC400 !important;

            border-radius:9px !important;

            color:#070707 !important;

            font-weight:900 !important;
        }

        button[data-testid="stBaseButton-primary"]:hover{
            background:#FFD332 !important;

            border-color:#FFD332 !important;
        }

        div[data-testid="stAlert"]{
            background:#30171A !important;

            border:1px solid #683038 !important;

            color:#FFD9DC !important;

            border-radius:9px !important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# LOGIN
# ============================================================

def render() -> None:
    """
    Pantalla de inicio de sesión.
    """

    _inject_login_styles()

    render_html(
        """
        <div class="login-brand">
            <img
                src="https://maritexb2c.vtexassets.com/arquivos/logo_maritex_desktop.png"
                alt="Maritex"
            >
        </div>

        <div class="login-card-head">

            <div class="login-eyebrow">
                PLATAFORMA INTERNA
            </div>

            <div class="login-title">
                PANEL DE CONTROL
            </div>

            <div class="login-subtitle">
                Ingresa con tus credenciales para acceder
                al sistema de gestión Maritex.
            </div>

        </div>
        """
    )

    with st.form(
        "login_form",
        clear_on_submit=False,
    ):

        username = st.text_input(
            "Usuario",
            placeholder="Ingresa tu usuario",
            autocomplete="username",
        )

        password = st.text_input(
            "Contraseña",
            type="password",
            placeholder="Ingresa tu contraseña",
            autocomplete="current-password",
        )

        submitted = st.form_submit_button(
            "INICIAR SESIÓN",
            type="primary",
            use_container_width=True,
        )

    if submitted:

        username = str(
            username or ""
        ).strip()

        password = str(
            password or ""
        )

        if not username or not password:
            st.error(
                "Ingresa usuario y contraseña."
            )
            return

        try:
            user = authenticate_user(
                username,
                password,
            )

        except Exception as exc:
            st.error(
                f"No fue posible conectar con el sistema de usuarios: {exc}"
            )
            return

        if not user:
            st.error(
                "Usuario o contraseña incorrectos."
            )
            return

        st.session_state[
            "authenticated"
        ] = True

        st.session_state[
            "auth_user"
        ] = user

        st.session_state[
            "page"
        ] = "Inicio"

        st.rerun()

    render_html(
        """
        <div class="login-system">
            <i></i>
            Sistema interno Maritex
        </div>
        """
    )