import io
from datetime import datetime

import pandas as pd

from config.settings import DEFAULT_VAT_RATE
from utils.numbers import parse_number


def read_excel_erp(raw: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()
    head = raw[:4096].lstrip().lower()

    looks_html = head.startswith(b"<") and (
        b"<html" in head or b"<table" in head or b"<!doctype" in head
    )

    if looks_html:
        try:
            html = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            html = raw.decode("cp1252", errors="replace")
        tables = pd.read_html(io.StringIO(html))
        if not tables:
            raise ValueError("El archivo XLS/HTML no contiene tablas.")
        return tables[0].astype(str)

    if name.endswith(".xlsx"):
        return pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl")

    if name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(raw), dtype=str, engine="xlrd")

    raise ValueError("Formato Excel no soportado.")


def parse_sales_dates(series: pd.Series) -> pd.Series:
    raw = series.fillna("").astype(str).str.strip()
    result = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")

    numeric = pd.to_numeric(raw.str.replace(",", ".", regex=False), errors="coerce")
    excel_mask = numeric.between(20000, 80000, inclusive="both")
    if excel_mask.any():
        result.loc[excel_mask] = pd.to_datetime(
            numeric.loc[excel_mask], unit="D", origin="1899-12-30", errors="coerce"
        )

    remaining = result.isna() & raw.ne("")

    iso = remaining & raw.str.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")
    if iso.any():
        result.loc[iso] = pd.to_datetime(raw.loc[iso], errors="coerce", yearfirst=True)

    remaining = result.isna() & raw.ne("")
    dash = remaining & raw.str.match(r"^\d{1,2}-\d{1,2}-\d{4}")
    if dash.any():
        result.loc[dash] = pd.to_datetime(raw.loc[dash], errors="coerce", dayfirst=True)

    remaining = result.isna() & raw.ne("")
    slash = remaining & raw.str.match(r"^\d{1,2}/\d{1,2}/\d{4}")

    if slash.any():
        values = raw.loc[slash]
        parts = values.str.extract(r"^(?P<a>\d{1,2})/(?P<b>\d{1,2})/(?P<y>\d{4})")
        a = pd.to_numeric(parts["a"], errors="coerce")
        b = pd.to_numeric(parts["b"], errors="coerce")

        d_first = pd.to_datetime(values, errors="coerce", dayfirst=True)
        m_first = pd.to_datetime(values, errors="coerce", dayfirst=False)

        evidence_day = int((a > 12).sum())
        evidence_month = int((b > 12).sum())

        future_limit = pd.Timestamp(datetime.now().date()) + pd.Timedelta(days=1)
        future_day = int((d_first.dropna().dt.normalize() > future_limit).sum())
        future_month = int((m_first.dropna().dt.normalize() > future_limit).sum())

        if evidence_day > evidence_month:
            chosen = d_first
        elif evidence_month > evidence_day:
            chosen = m_first
        elif future_day < future_month:
            chosen = d_first
        elif future_month < future_day:
            chosen = m_first
        else:
            chosen = d_first

        result.loc[slash] = chosen

    remaining = result.isna() & raw.ne("")
    if remaining.any():
        result.loc[remaining] = pd.to_datetime(raw.loc[remaining], errors="coerce")

    return result


def classify_document(value: str) -> str:
    value = "" if value is None else str(value).strip().upper()

    if not value:
        return "Otro"

    if (
        value.startswith("NC ")
        or value.startswith("NC(")
        or "NOTA CREDITO" in value
        or "NOTA DE CREDITO" in value
        or "NC DEVOL" in value
        or "NC REFACT" in value
    ):
        return "Nota de crédito"

    excluded = (
        "CIERRE", "NOTA VENTA", "NOTA VTA", "NV ", "PICKING",
        "COTIZACION", "COMPROMISO", "GUIA", "DEVOL.", "DEVOLUCION",
        "ND ", "ND(",
    )
    if any(token in value for token in excluded):
        return "Otro"

    if "FACTURA" in value or value.startswith("F.VTA") or value.startswith("FV "):
        return "Factura"

    if "BOLETA" in value or value.startswith("BV "):
        return "Boleta"

    return "Otro"


def resolve_amount_column(df: pd.DataFrame):
    candidates = [
        ("Total", "Total"),
        ("TotalIngreso", "TotalIngreso"),
        ("Monto", "Monto"),
        ("Importe", "Importe"),
        ("Valor", "Valor"),
    ]

    for source, label in candidates:
        if source not in df.columns:
            continue
        numeric = df[source].apply(parse_number)
        if (numeric.abs() > 0.000001).any():
            return source, label

    return None, None


def read_sales_source(raw: bytes, filename: str) -> pd.DataFrame:
    name = filename.lower()

    if name.endswith((".xls", ".xlsx")):
        df = read_excel_erp(raw, filename)
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
            raise ValueError(f"No fue posible leer ERP Ventas: {last_error}")
    else:
        raise ValueError("ERP Ventas debe ser CSV, XLS o XLSX.")

    df = df.dropna(axis=1, how="all").copy()

    if "Fecha" in df.columns:
        df["Fecha_dt"] = parse_sales_dates(df["Fecha"])

    amount_col, amount_label = resolve_amount_column(df)
    if amount_col:
        df["VentaMonto_num"] = df[amount_col].apply(parse_number)
        df["VentaMontoCampo"] = amount_label
    else:
        df["VentaMonto_num"] = 0.0
        df["VentaMontoCampo"] = "No detectado"

    if "TipoDocto" in df.columns:
        df["Grupo comercial"] = df["TipoDocto"].apply(classify_document)
    else:
        df["Grupo comercial"] = "Otro"

    # Fuente de verdad: monto firmado.
    df["VentaFirmadaConIVA"] = df.apply(
        lambda r: (
            -abs(float(r["VentaMonto_num"]))
            if r["Grupo comercial"] == "Nota de crédito"
            else float(r["VentaMonto_num"])
            if r["Grupo comercial"] in ("Factura", "Boleta")
            else 0.0
        ),
        axis=1,
    )
    df["VentaFirmadaSinIVA"] = df["VentaFirmadaConIVA"] / (1 + DEFAULT_VAT_RATE)

    return df
