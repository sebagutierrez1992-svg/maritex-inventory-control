import io
import re
from datetime import datetime

import pandas as pd

from config.settings import DEFAULT_VAT_RATE
from utils.numbers import parse_number


# ============================================================
# HELPERS DE COLUMNAS
# ============================================================

def _normalize_column_name(value: str) -> str:
    """
    Normaliza nombres de columnas para poder detectar variantes.

    Ejemplos:
        "Código Artículo" -> "CODIGOARTICULO"
        "cod. articulo"   -> "CODARTICULO"
        "SKU"             -> "SKU"
    """

    value = "" if value is None else str(value)

    replacements = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ñ": "N",
    }

    value = value.upper().strip()

    for old, new in replacements.items():
        value = value.replace(old, new)

    return re.sub(
        r"[^A-Z0-9]",
        "",
        value,
    )


def _column_lookup(df: pd.DataFrame) -> dict:
    """
    Devuelve:
        nombre_normalizado -> nombre_real
    """

    return {
        _normalize_column_name(col): col
        for col in df.columns
    }


def _find_column(
    df: pd.DataFrame,
    candidates,
):
    """
    Busca una columna tolerando:
    - espacios
    - puntos
    - tildes
    - mayúsculas/minúsculas
    """

    lookup = _column_lookup(df)

    for candidate in candidates:

        normalized = _normalize_column_name(
            candidate
        )

        if normalized in lookup:
            return lookup[normalized]

    return None


# ============================================================
# LECTURA EXCEL / HTML
# ============================================================

def read_excel_erp(
    raw: bytes,
    filename: str,
) -> pd.DataFrame:

    name = filename.lower()

    head = (
        raw[:4096]
        .lstrip()
        .lower()
    )

    looks_html = (
        head.startswith(b"<")
        and (
            b"<html" in head
            or b"<table" in head
            or b"<!doctype" in head
        )
    )

    # --------------------------------------------------------
    # XLS exportado realmente como HTML
    # --------------------------------------------------------

    if looks_html:

        try:
            html = raw.decode(
                "utf-8-sig"
            )

        except UnicodeDecodeError:

            html = raw.decode(
                "cp1252",
                errors="replace",
            )

        tables = pd.read_html(
            io.StringIO(html)
        )

        if not tables:
            raise ValueError(
                "El archivo XLS/HTML no contiene tablas."
            )

        return tables[0].astype(str)

    # --------------------------------------------------------
    # XLSX
    # --------------------------------------------------------

    if name.endswith(".xlsx"):

        return pd.read_excel(
            io.BytesIO(raw),
            dtype=str,
            engine="openpyxl",
        )

    # --------------------------------------------------------
    # XLS
    # --------------------------------------------------------

    if name.endswith(".xls"):

        return pd.read_excel(
            io.BytesIO(raw),
            dtype=str,
            engine="xlrd",
        )

    raise ValueError(
        "Formato Excel no soportado."
    )


# ============================================================
# FECHAS
# ============================================================

def parse_sales_dates(
    series: pd.Series,
) -> pd.Series:

    raw = (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )

    result = pd.Series(
        pd.NaT,
        index=raw.index,
        dtype="datetime64[ns]",
    )

    # --------------------------------------------------------
    # FECHA EXCEL NUMÉRICA
    # --------------------------------------------------------

    numeric = pd.to_numeric(
        raw.str.replace(
            ",",
            ".",
            regex=False,
        ),
        errors="coerce",
    )

    excel_mask = numeric.between(
        20000,
        80000,
        inclusive="both",
    )

    if excel_mask.any():

        result.loc[
            excel_mask
        ] = pd.to_datetime(
            numeric.loc[
                excel_mask
            ],
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )

    # --------------------------------------------------------
    # YYYY-MM-DD
    # --------------------------------------------------------

    remaining = (
        result.isna()
        & raw.ne("")
    )

    iso = (
        remaining
        & raw.str.match(
            r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}"
        )
    )

    if iso.any():

        result.loc[
            iso
        ] = pd.to_datetime(
            raw.loc[iso],
            errors="coerce",
            yearfirst=True,
        )

    # --------------------------------------------------------
    # DD-MM-YYYY
    # --------------------------------------------------------

    remaining = (
        result.isna()
        & raw.ne("")
    )

    dash = (
        remaining
        & raw.str.match(
            r"^\d{1,2}-\d{1,2}-\d{4}"
        )
    )

    if dash.any():

        result.loc[
            dash
        ] = pd.to_datetime(
            raw.loc[dash],
            errors="coerce",
            dayfirst=True,
        )

    # --------------------------------------------------------
    # DD/MM/YYYY o MM/DD/YYYY
    # --------------------------------------------------------

    remaining = (
        result.isna()
        & raw.ne("")
    )

    slash = (
        remaining
        & raw.str.match(
            r"^\d{1,2}/\d{1,2}/\d{4}"
        )
    )

    if slash.any():

        values = raw.loc[
            slash
        ]

        parts = values.str.extract(
            r"^(?P<a>\d{1,2})/"
            r"(?P<b>\d{1,2})/"
            r"(?P<y>\d{4})"
        )

        a = pd.to_numeric(
            parts["a"],
            errors="coerce",
        )

        b = pd.to_numeric(
            parts["b"],
            errors="coerce",
        )

        d_first = pd.to_datetime(
            values,
            errors="coerce",
            dayfirst=True,
        )

        m_first = pd.to_datetime(
            values,
            errors="coerce",
            dayfirst=False,
        )

        evidence_day = int(
            (a > 12).sum()
        )

        evidence_month = int(
            (b > 12).sum()
        )

        future_limit = (
            pd.Timestamp(
                datetime.now().date()
            )
            + pd.Timedelta(
                days=1
            )
        )

        future_day = int(
            (
                d_first
                .dropna()
                .dt.normalize()
                > future_limit
            ).sum()
        )

        future_month = int(
            (
                m_first
                .dropna()
                .dt.normalize()
                > future_limit
            ).sum()
        )

        if (
            evidence_day
            > evidence_month
        ):
            chosen = d_first

        elif (
            evidence_month
            > evidence_day
        ):
            chosen = m_first

        elif (
            future_day
            < future_month
        ):
            chosen = d_first

        elif (
            future_month
            < future_day
        ):
            chosen = m_first

        else:
            chosen = d_first

        result.loc[
            slash
        ] = chosen

    # --------------------------------------------------------
    # FALLBACK
    # --------------------------------------------------------

    remaining = (
        result.isna()
        & raw.ne("")
    )

    if remaining.any():

        result.loc[
            remaining
        ] = pd.to_datetime(
            raw.loc[
                remaining
            ],
            errors="coerce",
        )

    return result


# ============================================================
# DOCUMENTOS COMERCIALES
# ============================================================

def classify_document(
    value: str,
) -> str:

    value = (
        ""
        if value is None
        else str(value)
        .strip()
        .upper()
    )

    if not value:
        return "Otro"

    # --------------------------------------------------------
    # NOTAS DE CRÉDITO
    # --------------------------------------------------------

    if (
        value.startswith("NC ")
        or value.startswith("NC(")
        or "NOTA CREDITO" in value
        or "NOTA DE CREDITO" in value
        or "NC DEVOL" in value
        or "NC REFACT" in value
    ):
        return "Nota de crédito"

    # --------------------------------------------------------
    # DOCUMENTOS NO COMERCIALES
    # --------------------------------------------------------

    excluded = (
        "CIERRE",
        "NOTA VENTA",
        "NOTA VTA",
        "NV ",
        "PICKING",
        "COTIZACION",
        "COMPROMISO",
        "GUIA",
        "DEVOL.",
        "DEVOLUCION",
        "ND ",
        "ND(",
    )

    if any(
        token in value
        for token in excluded
    ):
        return "Otro"

    # --------------------------------------------------------
    # FACTURAS
    # --------------------------------------------------------

    if (
        "FACTURA" in value
        or value.startswith(
            "F.VTA"
        )
        or value.startswith(
            "FV "
        )
    ):
        return "Factura"

    # --------------------------------------------------------
    # BOLETAS
    # --------------------------------------------------------

    if (
        "BOLETA" in value
        or value.startswith(
            "BV "
        )
    ):
        return "Boleta"

    return "Otro"


# ============================================================
# MONTO
# ============================================================

def resolve_amount_column(
    df: pd.DataFrame,
):

    candidates = [
        "Total",
        "TotalIngreso",
        "Monto",
        "Importe",
        "Valor",
        "Venta",
        "Venta Neta",
        "VentaNeta",
    ]

    column = _find_column(
        df,
        candidates,
    )

    if column is None:
        return None, None

    numeric = df[
        column
    ].apply(
        parse_number
    )

    if (
        numeric.abs()
        > 0.000001
    ).any():

        return (
            column,
            column,
        )

    return None, None


# ============================================================
# SKU
# ============================================================

def resolve_sku_column(
    df: pd.DataFrame,
):

    candidates = [
        "SKU",
        "Sku",
        "Código",
        "Codigo",
        "Código Producto",
        "Codigo Producto",
        "CodProducto",
        "Cod Producto",
        "CodArticulo",
        "Cod Articulo",
        "Cod. Articulo",
        "Cod. Artículo",
        "Código Artículo",
        "Codigo Articulo",
        "CodItem",
        "Cod Item",
        "Item",
        "Artículo",
        "Articulo",
        "Referencia",
        "CodReferencia",
        "Código Referencia",
    ]

    return _find_column(
        df,
        candidates,
    )


# ============================================================
# CANTIDAD
# ============================================================

def resolve_quantity_column(
    df: pd.DataFrame,
):

    candidates = [
        "Cantidad",
        "Cant",
        "Cantidad Vendida",
        "CantidadVendida",
        "Unidades",
        "Unidad",
        "Qty",
        "Quantity",
        "Cantidad Facturada",
        "CantidadFacturada",
        "CantVendida",
    ]

    column = _find_column(
        df,
        candidates,
    )

    if column is None:
        return None

    numeric = df[
        column
    ].apply(
        parse_number
    )

    if (
        numeric.abs()
        > 0.000001
    ).any():

        return column

    return None


# ============================================================
# FECHA
# ============================================================

def resolve_date_column(
    df: pd.DataFrame,
):

    candidates = [
        "Fecha",
        "Fecha Emision",
        "Fecha Emisión",
        "FechaEmision",
        "Fecha Documento",
        "FechaDocumento",
        "Fecha Docto",
        "FechaDocto",
    ]

    return _find_column(
        df,
        candidates,
    )


# ============================================================
# TIPO DOCUMENTO
# ============================================================

def resolve_document_type_column(
    df: pd.DataFrame,
):

    candidates = [
        "TipoDocto",
        "Tipo Docto",
        "Tipo Documento",
        "TipoDocumento",
        "Documento",
        "Tipo",
    ]

    return _find_column(
        df,
        candidates,
    )


# ============================================================
# NORMALIZAR SKU
# ============================================================

def normalize_sku(
    series: pd.Series,
) -> pd.Series:

    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
    )


# ============================================================
# LECTOR PRINCIPAL ERP VENTAS
# ============================================================

def read_sales_source(
    raw: bytes,
    filename: str,
) -> pd.DataFrame:

    name = filename.lower()

    # --------------------------------------------------------
    # LEER ARCHIVO
    # --------------------------------------------------------

    if name.endswith(
        (
            ".xls",
            ".xlsx",
        )
    ):

        df = read_excel_erp(
            raw,
            filename,
        )

    elif name.endswith(
        ".csv"
    ):

        last_error = None
        df = None

        for encoding in (
            "utf-8-sig",
            "cp1252",
            "latin1",
        ):

            try:

                candidate = pd.read_csv(
                    io.BytesIO(raw),
                    sep=None,
                    engine="python",
                    encoding=encoding,
                    dtype=str,
                )

                if (
                    len(
                        candidate.columns
                    )
                    > 1
                ):
                    df = candidate
                    break

            except Exception as exc:
                last_error = exc

        if df is None:

            raise ValueError(
                f"No fue posible leer ERP Ventas: "
                f"{last_error}"
            )

    else:

        raise ValueError(
            "ERP Ventas debe ser CSV, XLS o XLSX."
        )

    # --------------------------------------------------------
    # LIMPIEZA INICIAL
    # --------------------------------------------------------

    df = (
        df
        .dropna(
            axis=1,
            how="all",
        )
        .copy()
    )

    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    # --------------------------------------------------------
    # DIAGNÓSTICO
    #
    # Lo dejamos temporalmente para identificar las
    # columnas reales del ERP.
    # --------------------------------------------------------

    print(
        "ERP VENTAS COLUMNAS:",
        df.columns.tolist(),
    )

    # ========================================================
    # FECHA
    # ========================================================

    date_col = resolve_date_column(
        df
    )

    if date_col:

        df["Fecha_dt"] = parse_sales_dates(
            df[
                date_col
            ]
        )

        df["FechaCampo"] = (
            date_col
        )

    else:

        df["Fecha_dt"] = pd.NaT

        df["FechaCampo"] = (
            "No detectado"
        )

    # ========================================================
    # SKU
    # ========================================================

    sku_col = resolve_sku_column(
        df
    )

    if sku_col:

        df["SKU"] = normalize_sku(
            df[
                sku_col
            ]
        )

        df["SKUCampo"] = (
            sku_col
        )

    else:

        df["SKU"] = ""

        df["SKUCampo"] = (
            "No detectado"
        )

    # ========================================================
    # CANTIDAD
    # ========================================================

    qty_col = resolve_quantity_column(
        df
    )

    if qty_col:

        df["Cantidad_num"] = (
            df[
                qty_col
            ]
            .apply(
                parse_number
            )
        )

        df["CantidadCampo"] = (
            qty_col
        )

    else:

        df["Cantidad_num"] = 0.0

        df["CantidadCampo"] = (
            "No detectado"
        )

    # ========================================================
    # MONTO
    # ========================================================

    amount_col, amount_label = (
        resolve_amount_column(
            df
        )
    )

    if amount_col:

        df[
            "VentaMonto_num"
        ] = (
            df[
                amount_col
            ]
            .apply(
                parse_number
            )
        )

        df[
            "VentaMontoCampo"
        ] = amount_label

    else:

        df[
            "VentaMonto_num"
        ] = 0.0

        df[
            "VentaMontoCampo"
        ] = "No detectado"

    # ========================================================
    # TIPO DOCUMENTO
    # ========================================================

    document_col = (
        resolve_document_type_column(
            df
        )
    )

    if document_col:

        df[
            "Grupo comercial"
        ] = (
            df[
                document_col
            ]
            .apply(
                classify_document
            )
        )

        df[
            "TipoDoctoCampo"
        ] = document_col

    else:

        df[
            "Grupo comercial"
        ] = "Otro"

        df[
            "TipoDoctoCampo"
        ] = "No detectado"

    # ========================================================
    # MONTO FIRMADO
    #
    # FACTURA / BOLETA = positivo
    # NOTA CRÉDITO     = negativo
    # OTRO             = cero
    # ========================================================

    amount = pd.to_numeric(
        df[
            "VentaMonto_num"
        ],
        errors="coerce",
    ).fillna(0.0)

    df[
        "VentaFirmadaConIVA"
    ] = 0.0

    commercial_positive = (
        df[
            "Grupo comercial"
        ].isin(
            [
                "Factura",
                "Boleta",
            ]
        )
    )

    credit = (
        df[
            "Grupo comercial"
        ].eq(
            "Nota de crédito"
        )
    )

    df.loc[
        commercial_positive,
        "VentaFirmadaConIVA",
    ] = amount.loc[
        commercial_positive
    ].abs()

    df.loc[
        credit,
        "VentaFirmadaConIVA",
    ] = -amount.loc[
        credit
    ].abs()

    # ========================================================
    # VENTA SIN IVA
    # ========================================================

    df[
        "VentaFirmadaSinIVA"
    ] = (
        df[
            "VentaFirmadaConIVA"
        ]
        / (
            1
            + DEFAULT_VAT_RATE
        )
    )

    # ========================================================
    # CANTIDAD FIRMADA
    #
    # Se usa para:
    # - cobertura
    # - rotación
    # - venta unidades 30d / 90d
    # ========================================================

    quantity = pd.to_numeric(
        df[
            "Cantidad_num"
        ],
        errors="coerce",
    ).fillna(0.0)

    df[
        "CantidadFirmada"
    ] = 0.0

    df.loc[
        commercial_positive,
        "CantidadFirmada",
    ] = quantity.loc[
        commercial_positive
    ].abs()

    df.loc[
        credit,
        "CantidadFirmada",
    ] = -quantity.loc[
        credit
    ].abs()

    # ========================================================
    # DIAGNÓSTICO FINAL
    # ========================================================

    print(
        "ERP VENTAS DETECCIÓN:",
        {
            "fecha": date_col,
            "sku": sku_col,
            "cantidad": qty_col,
            "monto": amount_col,
            "documento": document_col,
        },
    )

    return df