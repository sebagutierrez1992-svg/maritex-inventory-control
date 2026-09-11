from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

import bcrypt
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

VALID_ROLES = {
    "admin",
    "gerencia",
    "comercial",
    "operaciones",
    "consulta",
}

ALL_PAGES = (
    "Inicio",
    "CRM",
    "Stock General",
    "Marketplace",
    "Monitor Pedidos",
    "Integración ERP",
    "Resumen Ejecutivo",
    "Métricas Stock",
    "Métricas Vendedores",
    "Plantillas",
    "Usuarios",
)

ROLE_DEFAULT_PERMISSIONS = {
    "admin": list(ALL_PAGES),
    "gerencia": [
        "Inicio",
        "Stock General",
        "Marketplace",
        "CRM",
        "Métricas Stock",
        "Métricas Vendedores",
        "Resumen Ejecutivo",
    ],
    "comercial": [
        "Inicio",
        "CRM",
        "Métricas Vendedores",
        "Resumen Ejecutivo",
    ],
    "operaciones": [
        "Inicio",
        "Stock General",
        "Marketplace",
        "Monitor Pedidos",
        "Integración ERP",
        "Métricas Stock",
        "Plantillas",
    ],
    "consulta": [
        "Inicio",
        "Stock General",
        "Marketplace",
        "Métricas Stock",
        "Métricas Vendedores",
        "Resumen Ejecutivo",
    ],
}


def _get_connection():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada.")
    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        autocommit=False,
    )


def _normalize_role(role: str) -> str:
    value = str(role or "consulta").strip().lower()
    if value not in VALID_ROLES:
        raise ValueError(f"Rol no válido: {value}")
    return value


def normalize_permissions(
    permissions: Iterable[str] | None,
    role: str = "consulta",
) -> list[str]:
    """
    Normaliza permisos y aplica reglas de seguridad.

    - Admin siempre conserva acceso total.
    - Todo usuario conserva Inicio.
    - Usuarios solo puede ser usado por admin.
    - Se descartan nombres de páginas desconocidos.
    """
    role = _normalize_role(role)

    if role == "admin":
        return list(ALL_PAGES)

    if permissions is None:
        permissions = ROLE_DEFAULT_PERMISSIONS.get(
            role,
            ROLE_DEFAULT_PERMISSIONS["consulta"],
        )

    requested = {
        str(page).strip()
        for page in permissions
        if str(page).strip() in ALL_PAGES
    }
    requested.discard("Usuarios")
    requested.add("Inicio")

    return [page for page in ALL_PAGES if page in requested]


def get_effective_permissions(user: dict[str, Any] | None) -> list[str]:
    user = user or {}
    role = str(user.get("role") or "consulta").strip().lower()
    permissions = user.get("permissions")
    return normalize_permissions(permissions, role)


def init_auth_database() -> None:
    """Crea/migra la tabla de usuarios y agrega permisos por pestaña."""
    sql = """
    CREATE TABLE IF NOT EXISTS app_users (
        id BIGSERIAL PRIMARY KEY,
        username VARCHAR(100) UNIQUE NOT NULL,
        full_name VARCHAR(200) NOT NULL,
        password_hash TEXT NOT NULL,
        role VARCHAR(50) NOT NULL DEFAULT 'consulta',
        active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        last_login TIMESTAMPTZ,
        permissions JSONB
    );

    ALTER TABLE app_users
    ADD COLUMN IF NOT EXISTS permissions JSONB;

    CREATE INDEX IF NOT EXISTS idx_app_users_username
    ON app_users(username);

    CREATE INDEX IF NOT EXISTS idx_app_users_active
    ON app_users(active);
    """

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                "SELECT id, role, permissions FROM app_users ORDER BY id"
            )
            rows = cur.fetchall()

            for row in rows:
                if row.get("permissions") is None:
                    role = str(row.get("role") or "consulta").strip().lower()
                    if role not in VALID_ROLES:
                        role = "consulta"
                    perms = normalize_permissions(None, role)
                    cur.execute(
                        "UPDATE app_users SET permissions = %s WHERE id = %s",
                        (Jsonb(perms), int(row["id"])),
                    )
        conn.commit()


def hash_password(password: str) -> str:
    password = str(password or "")
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            str(password).encode("utf-8"),
            str(password_hash).encode("utf-8"),
        )
    except Exception:
        return False


def get_user_by_username(username: str) -> dict[str, Any] | None:
    username = str(username or "").strip().lower()
    if not username:
        return None

    sql = """
    SELECT id, username, full_name, password_hash, role, active,
           permissions, created_at, last_login
    FROM app_users
    WHERE LOWER(username) = %s
    LIMIT 1
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (username,))
            row = cur.fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    sql = """
    SELECT id, username, full_name, role, active, permissions,
           created_at, last_login
    FROM app_users
    WHERE id = %s
    LIMIT 1
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (int(user_id),))
            row = cur.fetchone()
    return dict(row) if row else None


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    user = get_user_by_username(username)
    if not user or not bool(user.get("active")):
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None

    permissions = normalize_permissions(
        user.get("permissions"),
        str(user.get("role") or "consulta"),
    )

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE app_users SET last_login = NOW() WHERE id = %s",
                    (user["id"],),
                )
            conn.commit()
    except Exception:
        pass

    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "active": user["active"],
        "permissions": permissions,
    }


def create_user(
    username: str,
    full_name: str,
    password: str,
    role: str = "consulta",
    permissions: Iterable[str] | None = None,
) -> int:
    username = str(username or "").strip().lower()
    full_name = str(full_name or "").strip()
    role = _normalize_role(role)

    if not username:
        raise ValueError("Debes indicar un nombre de usuario.")
    if not full_name:
        raise ValueError("Debes indicar el nombre del usuario.")

    permissions = normalize_permissions(permissions, role)
    password_hash = hash_password(password)

    sql = """
    INSERT INTO app_users (
        username,
        full_name,
        password_hash,
        role,
        active,
        permissions
    )
    VALUES (%s, %s, %s, %s, TRUE, %s)
    RETURNING id
    """

    try:
        with _get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        username,
                        full_name,
                        password_hash,
                        role,
                        Jsonb(permissions),
                    ),
                )
                result = cur.fetchone()
            conn.commit()
        return int(result["id"])
    except psycopg.errors.UniqueViolation as exc:
        raise ValueError("Ese nombre de usuario ya existe.") from exc


def list_users() -> list[dict[str, Any]]:
    sql = """
    SELECT id, username, full_name, role, active, permissions,
           created_at, last_login
    FROM app_users
    ORDER BY active DESC, full_name ASC
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def update_user(
    user_id: int,
    *,
    full_name: str,
    role: str,
    active: bool,
    permissions: Iterable[str] | None = None,
) -> None:
    full_name = str(full_name or "").strip()
    role = _normalize_role(role)
    if not full_name:
        raise ValueError("El nombre no puede quedar vacío.")

    permissions = normalize_permissions(permissions, role)

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE app_users
                SET full_name = %s,
                    role = %s,
                    active = %s,
                    permissions = %s
                WHERE id = %s
                """,
                (
                    full_name,
                    role,
                    bool(active),
                    Jsonb(permissions),
                    int(user_id),
                ),
            )
        conn.commit()


def update_user_permissions(
    user_id: int,
    permissions: Iterable[str],
) -> None:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("Usuario no encontrado.")

    normalized = normalize_permissions(
        permissions,
        str(user.get("role") or "consulta"),
    )

    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_users SET permissions = %s WHERE id = %s",
                (Jsonb(normalized), int(user_id)),
            )
        conn.commit()


def change_password(user_id: int, new_password: str) -> None:
    password_hash = hash_password(new_password)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_users SET password_hash = %s WHERE id = %s",
                (password_hash, int(user_id)),
            )
        conn.commit()


def set_user_active(user_id: int, active: bool) -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_users SET active = %s WHERE id = %s",
                (bool(active), int(user_id)),
            )
        conn.commit()


def update_user_role(user_id: int, role: str) -> None:
    role = _normalize_role(role)
    permissions = normalize_permissions(None, role)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE app_users SET role = %s, permissions = %s WHERE id = %s",
                (role, Jsonb(permissions), int(user_id)),
            )
        conn.commit()


def delete_user(user_id: int) -> None:
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_users WHERE id = %s", (int(user_id),))
        conn.commit()
