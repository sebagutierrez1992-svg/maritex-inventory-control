from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def is_database_configured() -> bool:
    return bool(DATABASE_URL)


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL no está configurada. "
            "Agrega la variable de entorno DATABASE_URL antes de usar el CRM."
        )

    conn = psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
        connect_timeout=10,
    )

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_connection() -> dict[str, Any]:
    if not DATABASE_URL:
        return {
            "ok": False,
            "message": "DATABASE_URL no está configurada.",
        }

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        current_database() AS database_name,
                        current_user AS database_user,
                        version() AS postgres_version
                    """
                )
                row = cur.fetchone()

        return {
            "ok": True,
            "message": "Conexión PostgreSQL correcta.",
            "database_name": row["database_name"],
            "database_user": row["database_user"],
            "postgres_version": row["postgres_version"],
        }

    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
        }


def init_crm_database() -> None:
    """
    Crea las tablas necesarias para el CRM.
    Puede ejecutarse varias veces sin borrar información existente.
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS crm_opportunities (
                    id BIGSERIAL PRIMARY KEY,

                    client_rut VARCHAR(50),
                    client_name VARCHAR(255) NOT NULL,
                    seller VARCHAR(255),

                    title VARCHAR(255) NOT NULL,
                    description TEXT,

                    estimated_amount NUMERIC(18, 2) NOT NULL DEFAULT 0,
                    stage VARCHAR(50) NOT NULL DEFAULT 'Prospección',
                    probability INTEGER NOT NULL DEFAULT 10,

                    expected_close_date DATE,
                    next_action_date DATE,
                    next_action TEXT,

                    status VARCHAR(30) NOT NULL DEFAULT 'Abierta',

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                    CONSTRAINT crm_opportunities_probability_check
                    CHECK (probability >= 0 AND probability <= 100)
                )
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_opportunities_client_rut
                ON crm_opportunities (client_rut)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_opportunities_seller
                ON crm_opportunities (seller)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_opportunities_stage
                ON crm_opportunities (stage)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_opportunities_status
                ON crm_opportunities (status)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_opportunities_close_date
                ON crm_opportunities (expected_close_date)
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS crm_followups (
                    id BIGSERIAL PRIMARY KEY,

                    opportunity_id BIGINT
                        REFERENCES crm_opportunities(id)
                        ON DELETE CASCADE,

                    client_rut VARCHAR(50),
                    client_name VARCHAR(255),

                    seller VARCHAR(255),

                    followup_type VARCHAR(50) NOT NULL DEFAULT 'Nota',
                    subject VARCHAR(255),
                    notes TEXT,

                    followup_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    next_followup_date DATE,

                    completed BOOLEAN NOT NULL DEFAULT FALSE,

                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_followups_opportunity
                ON crm_followups (opportunity_id)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_followups_client_rut
                ON crm_followups (client_rut)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_followups_seller
                ON crm_followups (seller)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_crm_followups_next_date
                ON crm_followups (next_followup_date)
                """
            )


def create_opportunity(
    *,
    client_name: str,
    title: str,
    client_rut: str | None = None,
    seller: str | None = None,
    description: str | None = None,
    estimated_amount: float | int | Decimal = 0,
    stage: str = "Prospección",
    probability: int = 10,
    expected_close_date: date | None = None,
    next_action_date: date | None = None,
    next_action: str | None = None,
    status: str = "Abierta",
) -> dict[str, Any]:
    client_name = (client_name or "").strip()
    title = (title or "").strip()

    if not client_name:
        raise ValueError("client_name es obligatorio.")

    if not title:
        raise ValueError("title es obligatorio.")

    probability = int(probability)

    if probability < 0 or probability > 100:
        raise ValueError("probability debe estar entre 0 y 100.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crm_opportunities (
                    client_rut,
                    client_name,
                    seller,
                    title,
                    description,
                    estimated_amount,
                    stage,
                    probability,
                    expected_close_date,
                    next_action_date,
                    next_action,
                    status
                )
                VALUES (
                    %(client_rut)s,
                    %(client_name)s,
                    %(seller)s,
                    %(title)s,
                    %(description)s,
                    %(estimated_amount)s,
                    %(stage)s,
                    %(probability)s,
                    %(expected_close_date)s,
                    %(next_action_date)s,
                    %(next_action)s,
                    %(status)s
                )
                RETURNING *
                """,
                {
                    "client_rut": _clean_optional_text(client_rut),
                    "client_name": client_name,
                    "seller": _clean_optional_text(seller),
                    "title": title,
                    "description": _clean_optional_text(description),
                    "estimated_amount": Decimal(str(estimated_amount or 0)),
                    "stage": stage.strip() or "Prospección",
                    "probability": probability,
                    "expected_close_date": expected_close_date,
                    "next_action_date": next_action_date,
                    "next_action": _clean_optional_text(next_action),
                    "status": status.strip() or "Abierta",
                },
            )

            return dict(cur.fetchone())


def list_opportunities(
    *,
    seller: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    client_rut: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if seller:
        conditions.append("seller = %(seller)s")
        params["seller"] = seller

    if stage:
        conditions.append("stage = %(stage)s")
        params["stage"] = stage

    if status:
        conditions.append("status = %(status)s")
        params["status"] = status

    if client_rut:
        conditions.append("client_rut = %(client_rut)s")
        params["client_rut"] = client_rut

    where_sql = ""

    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    limit = max(1, min(int(limit), 5000))

    query = f"""
        SELECT *
        FROM crm_opportunities
        {where_sql}
        ORDER BY
            CASE
                WHEN status = 'Abierta' THEN 0
                ELSE 1
            END,
            next_action_date NULLS LAST,
            expected_close_date NULLS LAST,
            created_at DESC
        LIMIT {limit}
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def get_opportunity(opportunity_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM crm_opportunities
                WHERE id = %(id)s
                """,
                {"id": int(opportunity_id)},
            )

            row = cur.fetchone()

            if not row:
                return None

            return dict(row)


def update_opportunity(
    opportunity_id: int,
    **fields: Any,
) -> dict[str, Any] | None:
    allowed_fields = {
        "client_rut",
        "client_name",
        "seller",
        "title",
        "description",
        "estimated_amount",
        "stage",
        "probability",
        "expected_close_date",
        "next_action_date",
        "next_action",
        "status",
    }

    updates: list[str] = []
    params: dict[str, Any] = {
        "id": int(opportunity_id),
    }

    for key, value in fields.items():
        if key not in allowed_fields:
            continue

        if key == "probability":
            value = int(value)

            if value < 0 or value > 100:
                raise ValueError("probability debe estar entre 0 y 100.")

        if key == "estimated_amount":
            value = Decimal(str(value or 0))

        if key in {
            "client_rut",
            "seller",
            "description",
            "next_action",
        }:
            value = _clean_optional_text(value)

        updates.append(f"{key} = %({key})s")
        params[key] = value

    if not updates:
        return get_opportunity(opportunity_id)

    updates.append("updated_at = NOW()")

    query = f"""
        UPDATE crm_opportunities
        SET {", ".join(updates)}
        WHERE id = %(id)s
        RETURNING *
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()

            if not row:
                return None

            return dict(row)


def delete_opportunity(opportunity_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM crm_opportunities
                WHERE id = %(id)s
                """,
                {"id": int(opportunity_id)},
            )

            return cur.rowcount > 0


def create_followup(
    *,
    followup_type: str = "Nota",
    opportunity_id: int | None = None,
    client_rut: str | None = None,
    client_name: str | None = None,
    seller: str | None = None,
    subject: str | None = None,
    notes: str | None = None,
    followup_date: datetime | None = None,
    next_followup_date: date | None = None,
    completed: bool = False,
) -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crm_followups (
                    opportunity_id,
                    client_rut,
                    client_name,
                    seller,
                    followup_type,
                    subject,
                    notes,
                    followup_date,
                    next_followup_date,
                    completed
                )
                VALUES (
                    %(opportunity_id)s,
                    %(client_rut)s,
                    %(client_name)s,
                    %(seller)s,
                    %(followup_type)s,
                    %(subject)s,
                    %(notes)s,
                    COALESCE(%(followup_date)s, NOW()),
                    %(next_followup_date)s,
                    %(completed)s
                )
                RETURNING *
                """,
                {
                    "opportunity_id": opportunity_id,
                    "client_rut": _clean_optional_text(client_rut),
                    "client_name": _clean_optional_text(client_name),
                    "seller": _clean_optional_text(seller),
                    "followup_type": followup_type.strip() or "Nota",
                    "subject": _clean_optional_text(subject),
                    "notes": _clean_optional_text(notes),
                    "followup_date": followup_date,
                    "next_followup_date": next_followup_date,
                    "completed": bool(completed),
                },
            )

            return dict(cur.fetchone())


def list_followups(
    *,
    opportunity_id: int | None = None,
    client_rut: str | None = None,
    seller: str | None = None,
    pending_only: bool = False,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}

    if opportunity_id is not None:
        conditions.append("opportunity_id = %(opportunity_id)s")
        params["opportunity_id"] = int(opportunity_id)

    if client_rut:
        conditions.append("client_rut = %(client_rut)s")
        params["client_rut"] = client_rut

    if seller:
        conditions.append("seller = %(seller)s")
        params["seller"] = seller

    if pending_only:
        conditions.append("completed = FALSE")

    where_sql = ""

    if conditions:
        where_sql = "WHERE " + " AND ".join(conditions)

    limit = max(1, min(int(limit), 5000))

    query = f"""
        SELECT *
        FROM crm_followups
        {where_sql}
        ORDER BY
            completed ASC,
            next_followup_date NULLS LAST,
            followup_date DESC,
            created_at DESC
        LIMIT {limit}
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]


def update_followup(
    followup_id: int,
    **fields: Any,
) -> dict[str, Any] | None:
    allowed_fields = {
        "opportunity_id",
        "client_rut",
        "client_name",
        "seller",
        "followup_type",
        "subject",
        "notes",
        "followup_date",
        "next_followup_date",
        "completed",
    }

    updates: list[str] = []
    params: dict[str, Any] = {
        "id": int(followup_id),
    }

    for key, value in fields.items():
        if key not in allowed_fields:
            continue

        if key in {
            "client_rut",
            "client_name",
            "seller",
            "subject",
            "notes",
        }:
            value = _clean_optional_text(value)

        if key == "completed":
            value = bool(value)

        updates.append(f"{key} = %({key})s")
        params[key] = value

    if not updates:
        return get_followup(followup_id)

    updates.append("updated_at = NOW()")

    query = f"""
        UPDATE crm_followups
        SET {", ".join(updates)}
        WHERE id = %(id)s
        RETURNING *
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()

            if not row:
                return None

            return dict(row)


def get_followup(followup_id: int) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM crm_followups
                WHERE id = %(id)s
                """,
                {"id": int(followup_id)},
            )

            row = cur.fetchone()

            if not row:
                return None

            return dict(row)


def delete_followup(followup_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM crm_followups
                WHERE id = %(id)s
                """,
                {"id": int(followup_id)},
            )

            return cur.rowcount > 0


def get_pipeline_summary() -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    stage,
                    COUNT(*) AS opportunities,
                    COALESCE(SUM(estimated_amount), 0) AS total_amount,
                    COALESCE(
                        SUM(
                            estimated_amount *
                            (probability::NUMERIC / 100)
                        ),
                        0
                    ) AS weighted_amount
                FROM crm_opportunities
                WHERE status = 'Abierta'
                GROUP BY stage
                ORDER BY
                    CASE stage
                        WHEN 'Prospección' THEN 1
                        WHEN 'Contacto' THEN 2
                        WHEN 'Cotización' THEN 3
                        WHEN 'Negociación' THEN 4
                        WHEN 'Cierre' THEN 5
                        ELSE 99
                    END,
                    stage
                """
            )

            return [dict(row) for row in cur.fetchall()]


def get_crm_summary() -> dict[str, Any]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'Abierta'
                    ) AS open_opportunities,

                    COALESCE(
                        SUM(estimated_amount) FILTER (
                            WHERE status = 'Abierta'
                        ),
                        0
                    ) AS open_amount,

                    COALESCE(
                        SUM(
                            estimated_amount *
                            (probability::NUMERIC / 100)
                        ) FILTER (
                            WHERE status = 'Abierta'
                        ),
                        0
                    ) AS weighted_amount,

                    COUNT(*) FILTER (
                        WHERE status = 'Ganada'
                    ) AS won_opportunities,

                    COALESCE(
                        SUM(estimated_amount) FILTER (
                            WHERE status = 'Ganada'
                        ),
                        0
                    ) AS won_amount
                FROM crm_opportunities
                """
            )

            opportunity_summary = dict(cur.fetchone())

            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE completed = FALSE
                    ) AS pending_followups,

                    COUNT(*) FILTER (
                        WHERE completed = FALSE
                          AND next_followup_date < CURRENT_DATE
                    ) AS overdue_followups,

                    COUNT(*) FILTER (
                        WHERE completed = FALSE
                          AND next_followup_date = CURRENT_DATE
                    ) AS today_followups
                FROM crm_followups
                """
            )

            followup_summary = dict(cur.fetchone())

    return {
        **opportunity_summary,
        **followup_summary,
    }


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()

    return text or None