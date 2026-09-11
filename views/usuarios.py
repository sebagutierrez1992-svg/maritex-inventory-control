from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from services.auth_service import (
    ALL_PAGES,
    ROLE_DEFAULT_PERMISSIONS,
    VALID_ROLES,
    change_password,
    create_user,
    list_users,
    normalize_permissions,
    update_user,
)
from ui.components import page_header, render_html


ROLE_LABELS = {
    "admin": "Administrador",
    "gerencia": "Gerencia",
    "comercial": "Comercial",
    "operaciones": "Operaciones",
    "consulta": "Consulta",
}

PAGE_LABELS = {
    "Inicio": "Inicio",
    "CRM": "CRM",
    "Stock General": "Stock General",
    "Marketplace": "Marketplace",
    "Monitor Pedidos": "Monitor de Pedidos WMS",
    "Integración ERP": "Integración ERP",
    "Resumen Ejecutivo": "Resumen Ejecutivo",
    "Métricas Stock": "Métricas de Stock",
    "Métricas Vendedores": "Métricas de Vendedores",
    "Plantillas": "Plantillas",
    "Usuarios": "Administración de Usuarios",
}


def _fmt_dt(value) -> str:
    """Formatea fechas de forma segura, incluyendo None, NaN y NaT."""
    if value is None:
        return "—"

    try:
        if pd.isna(value):
            return "—"
    except Exception:
        pass

    if isinstance(value, datetime):
        try:
            return value.strftime("%d-%m-%Y %H:%M")
        except (ValueError, AttributeError):
            return "—"

    try:
        parsed = pd.to_datetime(value, errors="coerce")

        if pd.isna(parsed):
            return "—"

        return parsed.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return "—"


def _require_admin() -> dict:
    user = st.session_state.get("auth_user") or {}
    if str(user.get("role") or "").lower() != "admin":
        st.error("No tienes permisos para acceder a Administración de Usuarios.")
        st.stop()
    return user


def _styles() -> None:
    st.markdown(
        """
        <style>
        .usr-info{
            padding:12px 14px;
            border:1px solid #34434f;
            border-radius:10px;
            background:linear-gradient(145deg,#18232d,#121b23);
            color:#dbe4ea;
            font-size:12px;
            margin-bottom:14px;
        }
        .usr-info b{color:#ffc400;}
        .usr-perm-help{
            padding:11px 13px;
            border:1px solid #34434f;
            border-left:4px solid #ffc400;
            border-radius:9px;
            background:#111a22;
            color:#aebbc5;
            font-size:11px;
            margin:8px 0 14px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _permission_options(role: str) -> list[str]:
    if role == "admin":
        return list(ALL_PAGES)
    return [page for page in ALL_PAGES if page != "Usuarios"]


def _permission_summary(permissions) -> str:
    values = list(permissions or [])
    return f"{len(values)} pestañas" if values else "Sin permisos personalizados"


def render(ctx=None) -> None:
    current_user = _require_admin()
    _styles()

    page_header(
        title="ADMINISTRACIÓN DE USUARIOS",
        subtitle=(
            "Crea cuentas, asigna roles y define exactamente "
            "a qué pestañas puede ingresar cada usuario."
        ),
        status="Acceso exclusivo administrador",
    )

    render_html(
        f"""
        <div class="usr-info">
            Sesión administrativa: <b>{current_user.get('full_name', 'Administrador')}</b>
            · usuario {current_user.get('username', '')}
        </div>
        """
    )

    tab_users, tab_create = st.tabs(["Usuarios", "Crear usuario"])

    with tab_create:
        st.subheader("Nuevo usuario")

        c1, c2 = st.columns(2)
        with c1:
            username = st.text_input(
                "Usuario",
                placeholder="ej: j.perez",
                key="usr_create_username",
            )
            full_name = st.text_input(
                "Nombre completo",
                placeholder="Juan Pérez",
                key="usr_create_full_name",
            )
        with c2:
            role_options = sorted(VALID_ROLES)
            role = st.selectbox(
                "Rol",
                options=role_options,
                format_func=lambda x: ROLE_LABELS.get(x, x.title()),
                key="usr_create_role",
            )
            password = st.text_input(
                "Contraseña inicial",
                type="password",
                placeholder="Mínimo 8 caracteres",
                key="usr_create_password",
            )

        confirm = st.text_input(
            "Confirmar contraseña",
            type="password",
            key="usr_create_confirm",
        )

        default_permissions = ROLE_DEFAULT_PERMISSIONS.get(
            role,
            ROLE_DEFAULT_PERMISSIONS["consulta"],
        )
        if role == "admin":
            selected_permissions = list(ALL_PAGES)
            st.multiselect(
                "Pestañas permitidas",
                options=list(ALL_PAGES),
                default=list(ALL_PAGES),
                format_func=lambda x: PAGE_LABELS.get(x, x),
                disabled=True,
                key="usr_create_admin_permissions",
            )
            st.caption("El rol Administrador siempre tiene acceso total.")
        else:
            selected_permissions = st.multiselect(
                "Pestañas permitidas",
                options=_permission_options(role),
                default=[
                    p for p in default_permissions
                    if p != "Usuarios"
                ],
                format_func=lambda x: PAGE_LABELS.get(x, x),
                key=f"usr_create_permissions_{role}",
            )

        render_html(
            """
            <div class="usr-perm-help">
                <b>Inicio</b> se mantiene siempre habilitado. La pestaña
                <b>Usuarios</b> está reservada exclusivamente a administradores.
            </div>
            """
        )

        if st.button(
            "Crear usuario",
            type="primary",
            use_container_width=True,
            key="usr_create_submit",
        ):
            if password != confirm:
                st.error("Las contraseñas no coinciden.")
            else:
                try:
                    user_id = create_user(
                        username=username,
                        full_name=full_name,
                        password=password,
                        role=role,
                        permissions=selected_permissions,
                    )
                    st.success(f"Usuario creado correctamente. ID: {user_id}")
                    for key in (
                        "usr_create_username",
                        "usr_create_full_name",
                        "usr_create_password",
                        "usr_create_confirm",
                    ):
                        st.session_state.pop(key, None)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with tab_users:
        try:
            users = list_users()
        except Exception as exc:
            st.error(f"No fue posible cargar los usuarios: {exc}")
            return

        if not users:
            st.info("Aún no hay usuarios registrados.")
            return

        df = pd.DataFrame(users)
        df["Rol"] = df["role"].map(lambda x: ROLE_LABELS.get(str(x), str(x)))
        df["Estado"] = df["active"].map(lambda x: "Activo" if bool(x) else "Inactivo")
        df["Accesos"] = df["permissions"].map(_permission_summary)
        df["Creado"] = df["created_at"].map(_fmt_dt)
        df["Último acceso"] = df["last_login"].map(_fmt_dt)

        table = df[
            [
                "id",
                "username",
                "full_name",
                "Rol",
                "Estado",
                "Accesos",
                "Creado",
                "Último acceso",
            ]
        ].copy()
        table.columns = [
            "ID",
            "Usuario",
            "Nombre",
            "Rol",
            "Estado",
            "Accesos",
            "Creado",
            "Último acceso",
        ]

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("### Editar usuario")
        selectable = {
            f"{u['full_name']} · {u['username']}": u
            for u in users
        }
        selected_label = st.selectbox(
            "Selecciona un usuario",
            options=list(selectable.keys()),
            key="usr_selected_user",
        )
        selected = selectable[selected_label]
        selected_id = int(selected["id"])

        c1, c2 = st.columns([1.35, 1])

        with c1:
            full_name_edit = st.text_input(
                "Nombre completo",
                value=str(selected.get("full_name") or ""),
                key=f"usr_edit_name_{selected_id}",
            )

            role_options = sorted(VALID_ROLES)
            current_role = str(selected.get("role") or "consulta")
            role_index = (
                role_options.index(current_role)
                if current_role in role_options
                else 0
            )
            role_edit = st.selectbox(
                "Rol",
                options=role_options,
                index=role_index,
                format_func=lambda x: ROLE_LABELS.get(x, x.title()),
                key=f"usr_edit_role_{selected_id}",
            )

            active_edit = st.toggle(
                "Usuario activo",
                value=bool(selected.get("active")),
                key=f"usr_edit_active_{selected_id}",
            )

            stored_permissions = normalize_permissions(
                selected.get("permissions"),
                current_role,
            )

            if role_edit == "admin":
                permissions_edit = list(ALL_PAGES)
                st.multiselect(
                    "Pestañas permitidas",
                    options=list(ALL_PAGES),
                    default=list(ALL_PAGES),
                    format_func=lambda x: PAGE_LABELS.get(x, x),
                    disabled=True,
                    key=f"usr_edit_permissions_admin_{selected_id}",
                )
                st.caption("El rol Administrador siempre tiene acceso total.")
            else:
                allowed_options = _permission_options(role_edit)
                default_edit = [
                    p for p in stored_permissions
                    if p in allowed_options
                ]
                permissions_edit = st.multiselect(
                    "Pestañas permitidas",
                    options=allowed_options,
                    default=default_edit,
                    format_func=lambda x: PAGE_LABELS.get(x, x),
                    key=f"usr_edit_permissions_{selected_id}_{role_edit}",
                )

            render_html(
                """
                <div class="usr-perm-help">
                    Marca solamente las pestañas que este usuario debe ver.
                    Los cambios de acceso se aplicarán en su próximo inicio de sesión.
                </div>
                """
            )

            save = st.button(
                "Guardar usuario y permisos",
                type="primary",
                use_container_width=True,
                key=f"usr_edit_save_{selected_id}",
            )

            if save:
                if selected_id == int(current_user.get("id") or -1) and not active_edit:
                    st.error("No puedes desactivar tu propia cuenta mientras estás conectado.")
                elif selected_id == int(current_user.get("id") or -1) and role_edit != "admin":
                    st.error("No puedes quitarte el rol administrador desde tu propia sesión.")
                else:
                    try:
                        update_user(
                            selected_id,
                            full_name=full_name_edit,
                            role=role_edit,
                            active=active_edit,
                            permissions=permissions_edit,
                        )
                        st.success("Usuario y permisos actualizados correctamente.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        with c2:
            st.markdown("**Restablecer contraseña**")
            new_password = st.text_input(
                "Nueva contraseña",
                type="password",
                key=f"usr_new_password_{selected_id}",
            )
            new_password_confirm = st.text_input(
                "Confirmar nueva contraseña",
                type="password",
                key=f"usr_new_password_confirm_{selected_id}",
            )

            if st.button(
                "Cambiar contraseña",
                use_container_width=True,
                key=f"usr_password_save_{selected_id}",
            ):
                if new_password != new_password_confirm:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        change_password(selected_id, new_password)
                        st.success("Contraseña actualizada correctamente.")
                    except Exception as exc:
                        st.error(str(exc))
