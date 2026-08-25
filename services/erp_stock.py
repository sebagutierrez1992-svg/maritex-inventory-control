import io
import pandas as pd

from utils.numbers import parse_number
from utils.text import normalize_code


def read_stock_source(raw: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()

    if name.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl")
    elif name.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="xlrd")
    elif name.endswith(".csv"):
        last_error = None
        df = None
        for encoding in ("utf-8-sig", "cp1252", "latin1"):
            try:
                candidate = pd.read_csv(
                    io.BytesIO(raw),
                    sep=None,
                    engine="python",
                    encoding=encoding,
                    dtype=str,
                )
                if len(candidate.columns) > 1:
                    df = candidate
                    break
            except Exception as exc:
                last_error = exc

        if df is None:
            raise ValueError(f"No fue posible leer ERP Stock: {last_error}")
    else:
        raise ValueError("ERP Stock debe ser CSV, XLS o XLSX.")

    return normalize_stock(df)


def normalize_stock(df: pd.DataFrame) -> pd.DataFrame:
    work = df.dropna(axis=1, how="all").copy()

    if "Producto" not in work.columns:
        raise ValueError("ERP Stock debe contener la columna Producto.")

    work["Código"] = work["Producto"].apply(normalize_code)

    for col in ("StockDisponible", "StockFisico", "PorLlegar", "PorDespachar"):
        if col in work.columns:
            work[f"{col}_num"] = work[col].apply(parse_number)

    return work


def consolidate_stock(df: pd.DataFrame) -> pd.DataFrame:
    if "Código" not in df.columns:
        raise ValueError("Stock no normalizado.")

    agg = {}
    for col in ("StockDisponible_num", "StockFisico_num", "PorLlegar_num", "PorDespachar_num"):
        if col in df.columns:
            agg[col] = "sum"

    for col in ("Descripcion", "Familia", "Bodega"):
        if col in df.columns:
            agg[col] = "first"

    if not agg:
        return df[["Código"]].drop_duplicates().copy()

    return df.groupby("Código", as_index=False).agg(agg)
