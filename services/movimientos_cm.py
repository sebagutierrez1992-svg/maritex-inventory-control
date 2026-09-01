from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOVEMENTS_FILE = (
    PROJECT_ROOT
    / "data"
    / "movimientos_cm"
    / "movimientos_cm_2026.csv"
)


def _normalize_sku(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


@st.cache_data(show_spinner=False)
def load_cm_movements(
    path: str | Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Carga el cache consolidado de movimientos físicos de Casa Matriz.

    El archivo esperado contiene:
    SKU, Producto, Fecha, TipoOperacion, Entrada, Salida, Saldo,
    Documento y Mes.

    No interpreta todas las salidas como ventas: son movimientos físicos.
    """
    file_path = Path(path) if path else DEFAULT_MOVEMENTS_FILE

    meta = {
        "enabled": False,
        "path": str(file_path),
        "reason": "",
        "rows": 0,
        "min_date": None,
        "max_date": None,
    }

    if not file_path.exists():
        meta["reason"] = (
            "No existe data/movimientos_cm/movimientos_cm_2026.csv"
        )
        return pd.DataFrame(), meta

    try:
        df = pd.read_csv(
            file_path,
            sep=";",
            dtype={
                "SKU": "string",
                "Producto": "string",
                "TipoOperacion": "string",
                "Documento": "string",
                "Mes": "string",
            },
        )
    except Exception as exc:
        meta["reason"] = f"No fue posible leer movimientos CM: {exc}"
        return pd.DataFrame(), meta

    required = {
        "SKU",
        "Producto",
        "Fecha",
        "TipoOperacion",
        "Entrada",
        "Salida",
        "Saldo",
        "Mes",
    }

    missing = sorted(required.difference(df.columns))
    if missing:
        meta["reason"] = (
            "Faltan columnas en movimientos CM: "
            + ", ".join(missing)
        )
        return pd.DataFrame(), meta

    df["SKU"] = _normalize_sku(df["SKU"])
    df["Producto"] = df["Producto"].fillna("").astype(str).str.strip()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")

    for col in ["Entrada", "Salida", "Saldo"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    df["TipoOperacion"] = (
        df["TipoOperacion"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    if "Documento" not in df.columns:
        df["Documento"] = ""

    df["Documento"] = (
        df["Documento"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df = df[
        df["SKU"].ne("")
        & df["Fecha"].notna()
    ].copy()

    df = df.sort_values(
        ["Fecha", "SKU"]
    ).reset_index(drop=True)

    if df.empty:
        meta["reason"] = "El cache de movimientos CM está vacío."
        return df, meta

    meta.update(
        {
            "enabled": True,
            "reason": "",
            "rows": int(len(df)),
            "min_date": df["Fecha"].min(),
            "max_date": df["Fecha"].max(),
        }
    )

    return df, meta


def build_cm_rotation_metrics(
    movements: pd.DataFrame,
    reference_date=None,
) -> pd.DataFrame:
    """
    Genera inteligencia de rotación física por SKU.

    Salida 30d / 60d / 90d:
        suma de SALIDAS físicas en la ventana.

    Frecuencia:
        cantidad de fechas distintas con salida > 0.

    Tendencia:
        compara las salidas mensuales más recientes.
    """
    if movements is None or movements.empty:
        return pd.DataFrame()

    work = movements.copy()

    work["Fecha"] = pd.to_datetime(
        work["Fecha"],
        errors="coerce",
    )

    work["Salida"] = pd.to_numeric(
        work["Salida"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0)

    work["Entrada"] = pd.to_numeric(
        work["Entrada"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0)

    work = work[
        work["SKU"].notna()
        & work["Fecha"].notna()
    ].copy()

    if work.empty:
        return pd.DataFrame()

    ref = (
        pd.Timestamp(reference_date)
        if reference_date is not None
        else work["Fecha"].max()
    )

    ref = ref.normalize()

    base = (
        work.sort_values(["SKU", "Fecha"])
        .groupby("SKU", as_index=False)
        .agg(
            Producto=("Producto", "last"),
            Último_saldo_CM=("Saldo", "last"),
        )
    )

    for days in [30, 60, 90]:
        start = ref - pd.Timedelta(days=days - 1)

        part = work[
            work["Fecha"].between(
                start,
                ref,
                inclusive="both",
            )
        ]

        qty = (
            part.groupby("SKU")["Salida"]
            .sum()
            .rename(f"Salidas_{days}d")
        )

        freq = (
            part.loc[part["Salida"] > 0]
            .groupby("SKU")["Fecha"]
            .nunique()
            .rename(f"Frecuencia_{days}d")
        )

        base = base.merge(
            qty,
            on="SKU",
            how="left",
        ).merge(
            freq,
            on="SKU",
            how="left",
        )

    last_exit = (
        work.loc[work["Salida"] > 0]
        .groupby("SKU")["Fecha"]
        .max()
        .rename("Última_salida")
    )

    base = base.merge(
        last_exit,
        on="SKU",
        how="left",
    )

    base["Días_sin_salida"] = (
        ref - pd.to_datetime(
            base["Última_salida"],
            errors="coerce",
        )
    ).dt.days

    base["Días_sin_salida"] = (
        base["Días_sin_salida"]
        .fillna(9999)
        .astype(int)
    )

    for col in [
        "Salidas_30d",
        "Salidas_60d",
        "Salidas_90d",
        "Frecuencia_30d",
        "Frecuencia_60d",
        "Frecuencia_90d",
    ]:
        if col not in base.columns:
            base[col] = 0.0

        base[col] = pd.to_numeric(
            base[col],
            errors="coerce",
        ).fillna(0.0)

    monthly = (
        work.assign(
            Mes_calc=work["Fecha"].dt.to_period("M").astype(str)
        )
        .groupby(
            ["SKU", "Mes_calc"],
            as_index=False,
        )["Salida"]
        .sum()
    )

    month_order = sorted(
        monthly["Mes_calc"].dropna().unique().tolist()
    )

    recent_months = month_order[-3:]

    if recent_months:
        pivot = (
            monthly[
                monthly["Mes_calc"].isin(recent_months)
            ]
            .pivot_table(
                index="SKU",
                columns="Mes_calc",
                values="Salida",
                aggfunc="sum",
                fill_value=0,
            )
            .reset_index()
        )

        rename = {}
        labels = ["Salidas_mes_-2", "Salidas_mes_-1", "Salidas_mes_actual"]

        for idx, month in enumerate(recent_months[-3:]):
            rename[month] = labels[
                idx + (3 - len(recent_months))
            ]

        pivot = pivot.rename(columns=rename)

        base = base.merge(
            pivot,
            on="SKU",
            how="left",
        )

    for col in [
        "Salidas_mes_-2",
        "Salidas_mes_-1",
        "Salidas_mes_actual",
    ]:
        if col not in base.columns:
            base[col] = 0.0

        base[col] = pd.to_numeric(
            base[col],
            errors="coerce",
        ).fillna(0.0)

    def trend(row) -> str:
        prev = float(row.get("Salidas_mes_-1", 0) or 0)
        current = float(row.get("Salidas_mes_actual", 0) or 0)

        if prev <= 0 and current <= 0:
            return "⚪ Sin movimiento"

        if prev <= 0 and current > 0:
            return "🟢 Acelerando"

        ratio = current / prev if prev > 0 else 0

        if ratio >= 1.20:
            return "🟢 Acelerando"

        if ratio <= 0.80:
            return "🟠 Desacelerando"

        return "🔵 Estable"

    base["Tendencia_movimiento"] = base.apply(
        trend,
        axis=1,
    )

    def rotation(row) -> str:
        salida90 = float(row.get("Salidas_90d", 0) or 0)
        days = int(row.get("Días_sin_salida", 9999) or 9999)

        if salida90 <= 0:
            return "⚪ Sin movimiento 90d"

        if days > 60:
            return "🔴 Muy lenta"

        if days > 30:
            return "🟠 Lenta"

        if float(row.get("Salidas_30d", 0) or 0) > 0:
            return "🟢 Activa"

        return "🔵 Moderada"

    base["Estado_rotación"] = base.apply(
        rotation,
        axis=1,
    )

    return base.sort_values(
        ["Salidas_30d", "Salidas_90d"],
        ascending=[False, False],
    ).reset_index(drop=True)
