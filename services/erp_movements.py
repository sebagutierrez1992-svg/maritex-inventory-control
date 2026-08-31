from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime
from typing import Any

import pandas as pd

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# CONFIGURACIÓN
# ============================================================

DEFAULT_LOCATION = "Casa Matriz"

# Clasificación inicial de operaciones.
# Se puede ampliar después cuando identifiquemos más códigos.
DEFAULT_OPERATION_CLASSIFICATION = {
    "99": "SALIDA_DEMANDA_CANDIDATA",
    "21": "ENTRADA",
    "11": "TRASLADO_CANDIDATO",
}


# ============================================================
# REGEX BASE
# ============================================================

NUMBER = (
    r"-?"
    r"(?:\d{1,3}(?:\.\d{3})*|\d+)"
    r"(?:,\d+)?"
)

DATE = r"\d{2}-\d{2}-\d{4}"


# ============================================================
# FORMATO REAL EXTRAÍDO DESDE FLEXLINE
# ============================================================

# Saldo/base inicial:
#
# 26-08-2026    20,00  0,00  20,00 16
#
# Significa:
# Fecha | Entrada | Salida | Saldo | TipoDocumento

OPENING_RE = re.compile(
    rf"""
    ^\s*
    (?P<fecha>{DATE})
    \s+
    (?P<entrada>{NUMBER})
    \s+
    (?P<salida>{NUMBER})
    \s+
    (?P<saldo>{NUMBER})
    \s+
    (?P<tipo_documento>\d+)
    \s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


# Movimiento real:
#
# 27-08-2026 00 0000003555  0,00  1,00  19,00 99
#
# Significa:
# Fecha
# TipoDocumento
# Documento
# Entrada
# Salida
# Saldo
# TipoOperacion

MOVEMENT_RE = re.compile(
    rf"""
    ^\s*
    (?P<fecha>{DATE})
    \s+
    (?P<tipo_documento>\d+)
    \s+
    (?P<documento>\d+)
    \s+
    (?P<entrada>{NUMBER})
    \s+
    (?P<salida>{NUMBER})
    \s+
    (?P<saldo>{NUMBER})
    \s+
    (?P<tipo_operacion>\d+)
    \s*$
    """,
    re.VERBOSE | re.MULTILINE,
)


# ============================================================
# HELPERS
# ============================================================


def _parse_number(value: Any) -> float:
    """
    Convierte números provenientes de Flexline.

    Ejemplos:
        1.637,00 -> 1637.0
        35,00    -> 35.0
        -2,00    -> -2.0
    """

    if value is None:
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    text = (
        text
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(text)

    except Exception:
        return 0.0


def _parse_date(value: Any):
    """
    Convierte DD-MM-YYYY a Timestamp.
    """

    if value is None:
        return pd.NaT

    return pd.to_datetime(
        str(value).strip(),
        format="%d-%m-%Y",
        errors="coerce",
    )


def _clean_text(value: Any) -> str:
    """
    Limpia espacios repetidos.
    """

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def _normalize_sku(value: Any) -> str:
    """
    Normaliza SKU conservando guiones y letras.

    Ejemplo:
        NP-551121 -> NP-551121
        10012003  -> 10012003
    """

    text = _clean_text(
        value
    ).upper()

    text = re.sub(
        r"\.0$",
        "",
        text,
    )

    return text


def _file_hash(raw: bytes) -> str:
    """
    Hash del archivo para identificar
    exactamente qué PDF fue procesado.
    """

    return hashlib.sha256(
        raw
    ).hexdigest()


# ============================================================
# CLASIFICACIÓN DE MOVIMIENTOS
# ============================================================


def classify_movement(
    *,
    tipo_operacion: str,
    entrada: float,
    salida: float,
    es_saldo_inicial: bool,
    operation_map: dict[str, str] | None = None,
) -> str:
    """
    Clasificación inicial de cada movimiento.

    La operación 99 se mantiene como
    SALIDA_DEMANDA_CANDIDATA hasta terminar
    la validación completa del Libro Mayor.
    """

    if es_saldo_inicial:
        return "SALDO_INICIAL"

    operation_map = (
        operation_map
        or DEFAULT_OPERATION_CLASSIFICATION
    )

    op = str(
        tipo_operacion
        or ""
    ).strip()

    if op in operation_map:
        return operation_map[op]

    if salida > 0 and entrada <= 0:
        return "SALIDA_OTRA"

    if entrada > 0 and salida <= 0:
        return "ENTRADA_OTRA"

    if entrada > 0 and salida > 0:
        return "MOVIMIENTO_MIXTO"

    return "SIN_MOVIMIENTO"


# ============================================================
# DETECCIÓN DE BLOQUES DE PRODUCTO
# ============================================================


def _product_sections(
    text: str,
) -> list[dict]:
    """
    Divide una página del PDF en bloques de producto.

    El PDF extraído por pypdf entrega algo así:

        CODIGO DE LA UNIDAD DE MEDIDA (TABLA 6):
        10012003

        PARKA TAURUS ...
        SALIDAS SALDO FINAL
        26-08-2026 ...
        27-08-2026 ...
        TOTALES:
    """

    if not text:
        return []

    marker_pattern = re.compile(
        r"CODIGO\s+DE\s+LA\s+UNIDAD\s+DE\s+MEDIDA"
        r"\s*\(TABLA\s+6\)\s*:",
        flags=re.IGNORECASE,
    )

    matches = list(
        marker_pattern.finditer(
            text
        )
    )

    if not matches:
        return []

    sections = []

    for index, match in enumerate(
        matches
    ):

        start = match.end()

        end = (
            matches[
                index + 1
            ].start()
            if index + 1 < len(matches)
            else len(text)
        )

        section = text[
            start:end
        ]

        # ----------------------------------------------------
        # Separar cabecera de producto / movimientos
        # ----------------------------------------------------

        split = re.split(
            r"SALIDAS\s+SALDO\s+FINAL",
            section,
            flags=re.IGNORECASE,
            maxsplit=1,
        )

        if len(split) != 2:
            continue

        header = split[0]
        movement_part = split[1]

        # ----------------------------------------------------
        # SKU y descripción
        # ----------------------------------------------------

        header_lines = [
            _clean_text(
                line
            )
            for line in header.splitlines()
        ]

        header_lines = [
            line
            for line in header_lines
            if line
        ]

        if not header_lines:
            continue

        sku = _normalize_sku(
            header_lines[0]
        )

        producto = (
            " ".join(
                header_lines[1:]
            )
            if len(header_lines) > 1
            else ""
        )

        producto = _clean_text(
            producto
        )

        if not sku:
            continue

        sections.append(
            {
                "sku":
                    sku,

                "producto":
                    producto,

                "text":
                    movement_part,
            }
        )

    return sections


# ============================================================
# PARSER DE UN BLOQUE DE PRODUCTO
# ============================================================


def _parse_section(
    section: dict,
    *,
    page_number: int,
    local: str,
    operation_map: dict[str, str] | None,
) -> list[dict]:

    sku = section[
        "sku"
    ]

    producto = section[
        "producto"
    ]

    text = section[
        "text"
    ]

    # --------------------------------------------------------
    # Evitar contaminación con siguiente bloque/pie.
    # --------------------------------------------------------

    text = re.split(
        r"TOTALES\s*:",
        text,
        flags=re.IGNORECASE,
        maxsplit=1,
    )[0]

    rows: list[dict] = []

    # ========================================================
    # SALDO INICIAL
    # ========================================================

    opening_match = (
        OPENING_RE.search(
            text
        )
    )

    if opening_match:

        entrada = _parse_number(
            opening_match.group(
                "entrada"
            )
        )

        salida = _parse_number(
            opening_match.group(
                "salida"
            )
        )

        saldo = _parse_number(
            opening_match.group(
                "saldo"
            )
        )

        tipo_documento = str(
            opening_match.group(
                "tipo_documento"
            )
        ).strip()

        rows.append(
            {
                "Fecha":
                    _parse_date(
                        opening_match.group(
                            "fecha"
                        )
                    ),

                "SKU":
                    sku,

                "Producto":
                    producto,

                "Local":
                    local,

                "TipoDocumento":
                    tipo_documento,

                "Documento":
                    "",

                "TipoOperacion":
                    "",

                "Entrada":
                    entrada,

                "Salida":
                    salida,

                "Saldo":
                    saldo,

                "Clasificacion":
                    "SALDO_INICIAL",

                "EsSaldoInicial":
                    True,

                "Pagina":
                    page_number,
            }
        )

    # ========================================================
    # MOVIMIENTOS REALES
    # ========================================================

    for match in MOVEMENT_RE.finditer(
        text
    ):

        fecha = _parse_date(
            match.group(
                "fecha"
            )
        )

        tipo_documento = str(
            match.group(
                "tipo_documento"
            )
        ).strip()

        documento = str(
            match.group(
                "documento"
            )
        ).strip()

        entrada = _parse_number(
            match.group(
                "entrada"
            )
        )

        salida = _parse_number(
            match.group(
                "salida"
            )
        )

        saldo = _parse_number(
            match.group(
                "saldo"
            )
        )

        tipo_operacion = str(
            match.group(
                "tipo_operacion"
            )
        ).strip()

        classification = (
            classify_movement(
                tipo_operacion=(
                    tipo_operacion
                ),

                entrada=entrada,

                salida=salida,

                es_saldo_inicial=False,

                operation_map=(
                    operation_map
                ),
            )
        )

        rows.append(
            {
                "Fecha":
                    fecha,

                "SKU":
                    sku,

                "Producto":
                    producto,

                "Local":
                    local,

                "TipoDocumento":
                    tipo_documento,

                "Documento":
                    documento,

                "TipoOperacion":
                    tipo_operacion,

                "Entrada":
                    entrada,

                "Salida":
                    salida,

                "Saldo":
                    saldo,

                "Clasificacion":
                    classification,

                "EsSaldoInicial":
                    False,

                "Pagina":
                    page_number,
            }
        )

    return rows


# ============================================================
# LECTOR PRINCIPAL PDF
# ============================================================


def read_inventory_movements_pdf(
    raw: bytes,
    *,
    filename: str = (
        "detalle de inventario unidades.pdf"
    ),
    local: str = DEFAULT_LOCATION,
    operation_map: dict[str, str] | None = None,
    max_pages: int | None = None,
) -> tuple[
    pd.DataFrame,
    dict,
]:
    """
    Lee:

        Libro Mayor Auxiliar
        -> Detalle de inventario Unidades

    El PDF actual corresponde a Casa Matriz.

    Devuelve un DataFrame con:

        Fecha
        SKU
        Producto
        Local
        TipoDocumento
        Documento
        TipoOperacion
        Entrada
        Salida
        Saldo
        Clasificacion
        EsSaldoInicial
        Pagina
    """

    if PdfReader is None:

        raise ImportError(
            "Falta instalar pypdf. "
            "Ejecuta: pip install pypdf"
        )

    if not raw:

        raise ValueError(
            "El PDF está vacío."
        )

    reader = PdfReader(
        io.BytesIO(
            raw
        )
    )

    total_pages = len(
        reader.pages
    )

    if (
        max_pages is not None
        and max_pages > 0
    ):

        pages_to_read = min(
            total_pages,
            int(
                max_pages
            ),
        )

    else:

        pages_to_read = (
            total_pages
        )

    rows: list[
        dict
    ] = []

    pages_with_data = 0

    # ========================================================
    # RECORRER PÁGINAS
    # ========================================================

    for page_index in range(
        pages_to_read
    ):

        page_number = (
            page_index + 1
        )

        page = reader.pages[
            page_index
        ]

        try:

            text = (
                page.extract_text()
                or ""
            )

        except Exception:

            text = ""

        if not text.strip():
            continue

        sections = (
            _product_sections(
                text
            )
        )

        if not sections:
            continue

        page_rows: list[
            dict
        ] = []

        for section in sections:

            parsed = (
                _parse_section(
                    section,

                    page_number=(
                        page_number
                    ),

                    local=(
                        local
                    ),

                    operation_map=(
                        operation_map
                    ),
                )
            )

            page_rows.extend(
                parsed
            )

        if page_rows:

            pages_with_data += 1

            rows.extend(
                page_rows
            )

    # ========================================================
    # VALIDACIÓN
    # ========================================================

    if not rows:

        raise ValueError(
            "No fue posible detectar movimientos "
            "en el PDF. Verifica que corresponda "
            "a 'Detalle de inventario Unidades'."
        )

    # ========================================================
    # DATAFRAME
    # ========================================================

    df = pd.DataFrame(
        rows
    )

    # ========================================================
    # NORMALIZACIÓN
    # ========================================================

    df["Fecha"] = pd.to_datetime(
        df["Fecha"],
        errors="coerce",
    )

    for col in [
        "Entrada",
        "Salida",
        "Saldo",
    ]:

        df[col] = (
            pd.to_numeric(
                df[col],
                errors="coerce",
            )
            .fillna(0.0)
        )

    for col in [
        "SKU",
        "Producto",
        "Local",
        "TipoDocumento",
        "Documento",
        "TipoOperacion",
        "Clasificacion",
    ]:

        df[col] = (
            df[col]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    df["SKU"] = (
        df["SKU"]
        .map(
            _normalize_sku
        )
    )

    df["EsSaldoInicial"] = (
        df[
            "EsSaldoInicial"
        ]
        .fillna(False)
        .astype(bool)
    )

    df["Pagina"] = (
        pd.to_numeric(
            df["Pagina"],
            errors="coerce",
        )
        .fillna(0)
        .astype(int)
    )

    # ========================================================
    # ORDEN
    # ========================================================

    df = (
        df.sort_values(
            [
                "SKU",
                "Fecha",
                "Pagina",
                "EsSaldoInicial",
            ],

            ascending=[
                True,
                True,
                True,
                False,
            ],

            na_position="last",
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # METADATA
    # ========================================================

    movements = df[
        ~df[
            "EsSaldoInicial"
        ]
    ].copy()

    meta = {
        "filename":
            filename,

        "local":
            local,

        "pdf_pages":
            total_pages,

        "pages_read":
            pages_to_read,

        "pages_with_data":
            pages_with_data,

        "rows":
            len(
                df
            ),

        "movements":
            len(
                movements
            ),

        "sku":
            int(
                df[
                    "SKU"
                ].nunique()
            ),

        "total_entradas":
            float(
                movements[
                    "Entrada"
                ].sum()
            ),

        "total_salidas":
            float(
                movements[
                    "Salida"
                ].sum()
            ),

        "generated_at":
            datetime.now()
            .isoformat(),

        "sha256":
            _file_hash(
                raw
            ),
    }

    return (
        df,
        meta,
    )


# ============================================================
# RESUMEN POR TIPO DE OPERACIÓN
# ============================================================


def movement_operation_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Permite identificar todos los códigos
    de operación presentes en el Libro Mayor.
    """

    if (
        df is None
        or df.empty
    ):

        return pd.DataFrame()

    work = df[
        ~df[
            "EsSaldoInicial"
        ]
    ].copy()

    if work.empty:

        return pd.DataFrame(
            columns=[
                "TipoOperacion",
                "Clasificacion",
                "Registros",
                "SKU",
                "Documentos",
                "Entradas",
                "Salidas",
            ]
        )

    summary = (
        work
        .groupby(
            [
                "TipoOperacion",
                "Clasificacion",
            ],

            dropna=False,

            as_index=False,
        )
        .agg(
            Registros=(
                "SKU",
                "size",
            ),

            SKU=(
                "SKU",
                "nunique",
            ),

            Documentos=(
                "Documento",
                "nunique",
            ),

            Entradas=(
                "Entrada",
                "sum",
            ),

            Salidas=(
                "Salida",
                "sum",
            ),
        )
    )

    return (
        summary
        .sort_values(
            [
                "Salidas",
                "Entradas",
                "Registros",
            ],

            ascending=[
                False,
                False,
                False,
            ],
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# MOVIMIENTOS DE DEMANDA CANDIDATA
# ============================================================


def demand_candidate_movements(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devuelve exclusivamente movimientos
    clasificados inicialmente como demanda.

    Todavía NO los llamamos "ventas definitivas",
    porque estamos validando los códigos de operación.
    """

    if (
        df is None
        or df.empty
    ):

        return pd.DataFrame()

    return (
        df[
            (
                df[
                    "Clasificacion"
                ]
                ==
                "SALIDA_DEMANDA_CANDIDATA"
            )
            &
            (
                df[
                    "Salida"
                ] > 0
            )
        ]
        .copy()
    )


# ============================================================
# DEMANDA CONSOLIDADA POR SKU
# ============================================================


def demand_by_sku(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Consolida la demanda candidata
    a nivel SKU para Casa Matriz.
    """

    movements = (
        demand_candidate_movements(
            df
        )
    )

    if movements.empty:

        return pd.DataFrame(
            columns=[
                "SKU",
                "Producto",
                "Local",
                "Unidades salida",
                "Movimientos",
                "Documentos",
                "Primera salida",
                "Última salida",
            ]
        )

    result = (
        movements
        .groupby(
            [
                "SKU",
                "Producto",
                "Local",
            ],

            as_index=False,
        )
        .agg(
            **{
                "Unidades salida":
                    (
                        "Salida",
                        "sum",
                    ),

                "Movimientos":
                    (
                        "SKU",
                        "size",
                    ),

                "Documentos":
                    (
                        "Documento",
                        "nunique",
                    ),

                "Primera salida":
                    (
                        "Fecha",
                        "min",
                    ),

                "Última salida":
                    (
                        "Fecha",
                        "max",
                    ),
            }
        )
    )

    return (
        result
        .sort_values(
            "Unidades salida",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )


# ============================================================
# MOVIMIENTOS REALES SIN SALDO INICIAL
# ============================================================


def real_movements(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Elimina las filas utilizadas solamente
    como saldo inicial del reporte.
    """

    if (
        df is None
        or df.empty
    ):

        return pd.DataFrame()

    return (
        df[
            ~df[
                "EsSaldoInicial"
            ]
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )


# ============================================================
# RESUMEN POR SKU
# ============================================================


def movement_summary_by_sku(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resume todos los movimientos de inventario,
    no solamente demanda.
    """

    work = real_movements(
        df
    )

    if work.empty:

        return pd.DataFrame(
            columns=[
                "SKU",
                "Producto",
                "Local",
                "Entradas",
                "Salidas",
                "Movimientos",
                "Primera fecha",
                "Última fecha",
            ]
        )

    result = (
        work
        .groupby(
            [
                "SKU",
                "Producto",
                "Local",
            ],
            as_index=False,
        )
        .agg(
            Entradas=(
                "Entrada",
                "sum",
            ),

            Salidas=(
                "Salida",
                "sum",
            ),

            Movimientos=(
                "SKU",
                "size",
            ),

            **{
                "Primera fecha":
                    (
                        "Fecha",
                        "min",
                    ),

                "Última fecha":
                    (
                        "Fecha",
                        "max",
                    ),
            }
        )
    )

    return (
        result
        .sort_values(
            [
                "Salidas",
                "Entradas",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .reset_index(
            drop=True
        )
    )