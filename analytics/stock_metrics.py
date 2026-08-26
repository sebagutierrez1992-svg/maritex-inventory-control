import re
import unicodedata

import pandas as pd


# ============================================================
# NORMALIZACIÓN DE COLUMNAS
# ============================================================

def _normalize_name(value: str) -> str:
    """
    Convierte nombres de columnas a una forma comparable.

    Ejemplos:
    "Stock Proyectado" -> "stockproyectado"
    "Descripción "     -> "descripcion"
    "%Max. D/R"        -> "maxdr"
    """
    text = str(value or "").strip().lower()

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )

    text = re.sub(
        r"[^a-z0-9]+",
        "",
        text,
    )

    return text


def _column_map(df: pd.DataFrame) -> dict:
    """
    Mapa:
        nombre normalizado -> nombre real de la columna.
    """
    result = {}

    for col in df.columns:
        key = _normalize_name(col)

        if key and key not in result:
            result[key] = col

    return result


def _find_column(
    df: pd.DataFrame,
    candidates,
):
    """
    Encuentra una columna aunque cambien:
    - mayúsculas
    - minúsculas
    - acentos
    - espacios
    - puntos
    - guiones
    """
    cmap = _column_map(df)

    for candidate in candidates:
        key = _normalize_name(candidate)

        if key in cmap:
            return cmap[key]

    return None


# ============================================================
# HELPERS
# ============================================================

def _empty_series(
    df: pd.DataFrame,
    value=0.0,
):
    return pd.Series(
        value,
        index=df.index,
    )


def _numeric(
    df: pd.DataFrame,
    candidates,
) -> pd.Series:

    column = _find_column(
        df,
        candidates,
    )

    if column is None:
        return _empty_series(
            df,
            0.0,
        )

    source = df[column]

    # Ya numérico
    if pd.api.types.is_numeric_dtype(source):
        return (
            pd.to_numeric(
                source,
                errors="coerce",
            )
            .fillna(0.0)
            .astype(float)
        )

    # Texto Flexline / Excel
    text = (
        source
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Algunos Excel llegan como 10,00000000
    # o 1.234,56.
    def parse_number(value):
        value = str(value).strip()

        if not value:
            return 0.0

        value = (
            value
            .replace("$", "")
            .replace(" ", "")
        )

        # Caso latino:
        # 1.234,56
        if (
            "." in value
            and "," in value
            and value.rfind(",")
            > value.rfind(".")
        ):
            value = (
                value
                .replace(".", "")
                .replace(",", ".")
            )

        # Caso:
        # 10,00000000
        elif (
            "," in value
            and "." not in value
        ):
            value = value.replace(
                ",",
                ".",
            )

        try:
            return float(value)

        except Exception:
            return 0.0

    return text.map(
        parse_number
    ).astype(float)


def _text(
    df: pd.DataFrame,
    candidates,
    default="",
) -> pd.Series:

    column = _find_column(
        df,
        candidates,
    )

    if column is None:
        return _empty_series(
            df,
            default,
        ).astype(str)

    return (
        df[column]
        .fillna(default)
        .astype(str)
        .str.strip()
    )


def _clean_code(
    series: pd.Series,
) -> pd.Series:
    """
    Evita códigos como:

    1000802.0

    y los transforma en:

    1000802
    """
    values = (
        series
        .fillna("")
        .astype(str)
        .str.strip()
    )

    values = values.str.replace(
        r"\.0$",
        "",
        regex=True,
    )

    return values


# ============================================================
# ESTADO DEL INVENTARIO
# ============================================================

def add_inventory_status(
    df: pd.DataFrame,
) -> pd.DataFrame:

    out = df.copy()

    if "Disponible" not in out.columns:
        out["Disponible"] = 0.0

    if "Por llegar" not in out.columns:
        out["Por llegar"] = 0.0

    if "Por despachar" not in out.columns:
        out["Por despachar"] = 0.0

    available = (
        pd.to_numeric(
            out["Disponible"],
            errors="coerce",
        )
        .fillna(0.0)
    )

    incoming = (
        pd.to_numeric(
            out["Por llegar"],
            errors="coerce",
        )
        .fillna(0.0)
    )

    outgoing = (
        pd.to_numeric(
            out["Por despachar"],
            errors="coerce",
        )
        .fillna(0.0)
    )

    def classify(
        available_value,
        incoming_value,
        outgoing_value,
    ):

        if available_value < 0:
            return "🔴 Negativo"

        if (
            available_value == 0
            and incoming_value > 0
        ):
            return "🔵 Por llegar"

        if available_value == 0:
            return "🔴 Sin stock"

        if (
            outgoing_value > available_value
            and outgoing_value > 0
        ):
            return "🟠 Riesgo despacho"

        if (
            available_value > 0
            and available_value <= 5
        ):
            return "🟡 Stock bajo"

        return "🟢 Disponible"

    out["Estado"] = [
        classify(
            available_value,
            incoming_value,
            outgoing_value,
        )
        for (
            available_value,
            incoming_value,
            outgoing_value,
        )
        in zip(
            available,
            incoming,
            outgoing,
        )
    ]

    return out


# ============================================================
# VISTA NORMALIZADA ERP STOCK
# ============================================================

def stock_view(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Convierte el ERP Stock de Flexline a una estructura estable.

    Formato Flexline esperado, entre otros:

    Empresa
    Producto
    Descripción
    Unidad
    Stock
    Stock Proyectado
    Precio Venta
    %Max. D/R
    Bodega

    Esta salida es compartida por:

    - Stock General
    - Métricas de Stock
    - Marketplaces
    """

    columns = [
        "Empresa",
        "Código",
        "Producto",
        "Unidad",
        "Bodega",
        "Familia",
        "Subfamilia",
        "Stock físico",
        "Disponible",
        "Por llegar",
        "Por despachar",
        "Precio",
        "Estado",
    ]

    if df is None:
        return pd.DataFrame(
            columns=columns,
        )

    if df.empty:
        return pd.DataFrame(
            columns=columns,
        )

    work = df.copy()

    out = pd.DataFrame(
        index=work.index,
    )

    # --------------------------------------------------------
    # Empresa
    # --------------------------------------------------------

    out["Empresa"] = _text(
        work,
        [
            "Empresa",
            "CodEmpresa",
            "Código Empresa",
            "Codigo Empresa",
        ],
    )

    # --------------------------------------------------------
    # SKU / código
    #
    # En el ERP real que estamos usando,
    # la columna Producto contiene el código SKU.
    # --------------------------------------------------------

    code = _text(
        work,
        [
            "Producto",
            "Código",
            "Codigo",
            "SKU",
            "Sku",
            "CodProducto",
            "CodigoProducto",
            "CodArticulo",
            "CodigoArticulo",
        ],
    )

    out["Código"] = _clean_code(
        code
    )

    # --------------------------------------------------------
    # Descripción
    # --------------------------------------------------------

    out["Producto"] = _text(
        work,
        [
            "Descripción",
            "Descripcion",
            "Descripción Producto",
            "Descripcion Producto",
            "DescProducto",
            "Nombre Producto",
            "Nombre",
            "Articulo",
            "Artículo",
        ],
    )

    # Si falta descripción:
    out.loc[
        out["Producto"].eq(""),
        "Producto",
    ] = out.loc[
        out["Producto"].eq(""),
        "Código",
    ]

    # --------------------------------------------------------
    # Unidad
    # --------------------------------------------------------

    out["Unidad"] = _text(
        work,
        [
            "Unidad",
            "UM",
            "Unidad Medida",
            "UnidadMedida",
        ],
    )

    # --------------------------------------------------------
    # Bodega
    # --------------------------------------------------------

    out["Bodega"] = _text(
        work,
        [
            "Bodega",
            "DescBodega",
            "Descripción Bodega",
            "Descripcion Bodega",
            "Almacen",
            "Almacén",
        ],
    )

    # --------------------------------------------------------
    # Familia / Subfamilia
    # --------------------------------------------------------

    out["Familia"] = _text(
        work,
        [
            "DescFamilia",
            "Familia",
            "Descripción Familia",
            "Descripcion Familia",
        ],
    )

    out["Subfamilia"] = _text(
        work,
        [
            "DescSubFamilia",
            "DescSubfamilia",
            "SubFamilia",
            "Subfamilia",
            "Descripción Subfamilia",
            "Descripcion Subfamilia",
        ],
    )

    # --------------------------------------------------------
    # STOCK FÍSICO
    #
    # Flexline:
    # Stock
    # --------------------------------------------------------

    out["Stock físico"] = _numeric(
        work,
        [
            "StockFisico_num",
            "Stock Físico",
            "Stock Fisico",
            "StockFisico",
            "Stock_num",
            "Stock",
        ],
    )

    # --------------------------------------------------------
    # DISPONIBLE
    #
    # Flexline:
    # Stock Proyectado
    #
    # Esta es la columna principal que debe utilizar
    # Stock General.
    # --------------------------------------------------------

    projected_column = _find_column(
        work,
        [
            "Stock Proyectado",
            "StockProyectado",
            "Stock Disponible",
            "StockDisponible",
            "StockDisponible_num",
            "Disponible",
        ],
    )

    if projected_column is not None:
        out["Disponible"] = _numeric(
            work,
            [projected_column],
        )

    else:
        # fallback a Stock físico
        out["Disponible"] = (
            out["Stock físico"]
            .copy()
        )

    # --------------------------------------------------------
    # POR LLEGAR
    # --------------------------------------------------------

    out["Por llegar"] = _numeric(
        work,
        [
            "PorLlegar_num",
            "StockPorLlegar_num",
            "Stock Por Llegar",
            "StockPorLlegar",
            "Por Llegar",
            "PorLlegar",
        ],
    )

    # --------------------------------------------------------
    # POR DESPACHAR
    # --------------------------------------------------------

    out["Por despachar"] = _numeric(
        work,
        [
            "PorDespachar_num",
            "StockPorDespachar_num",
            "Stock Por Despachar",
            "StockPorDespachar",
            "Por Despachar",
            "PorDespachar",
        ],
    )

    # --------------------------------------------------------
    # Precio Venta
    # --------------------------------------------------------

    out["Precio"] = _numeric(
        work,
        [
            "Precio Venta_num",
            "Precio Venta",
            "PrecioVenta",
            "Precio",
        ],
    )

    # --------------------------------------------------------
    # Eliminar filas realmente vacías
    # --------------------------------------------------------

    valid_code = (
        out["Código"]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    )

    out = out[
        valid_code
    ].copy()

    out.reset_index(
        drop=True,
        inplace=True,
    )

    return add_inventory_status(
        out
    )


# ============================================================
# CONSOLIDACIÓN SKU
# ============================================================

def consolidate_inventory(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Consolida todas las bodegas por SKU.

    IMPORTANTE:

    Esto sirve para Stock General y Métricas.

    Marketplaces debe filtrar Casa Matriz
    ANTES de consolidar.
    """

    if df is None or df.empty:
        return stock_view(
            df
        )

    normalized_columns = {
        "Código",
        "Producto",
        "Bodega",
        "Familia",
        "Subfamilia",
        "Stock físico",
        "Disponible",
        "Por llegar",
        "Por despachar",
        "Precio",
    }

    if normalized_columns.issubset(
        set(df.columns)
    ):
        work = df.copy()

    else:
        work = stock_view(
            df
        )

    if work.empty:
        return work

    def first_text(
        series,
    ):
        values = (
            series
            .fillna("")
            .astype(str)
            .str.strip()
        )

        values = values[
            values.ne("")
        ]

        if values.empty:
            return ""

        return values.iloc[0]

    grouped = (
        work.groupby(
            "Código",
            as_index=False,
            dropna=False,
        )
        .agg(
            Producto=(
                "Producto",
                first_text,
            ),
            Familia=(
                "Familia",
                first_text,
            ),
            Subfamilia=(
                "Subfamilia",
                first_text,
            ),
            Bodegas=(
                "Bodega",
                lambda series: (
                    series
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace(
                        "",
                        pd.NA,
                    )
                    .dropna()
                    .nunique()
                ),
            ),
            **{
                "Stock físico": (
                    "Stock físico",
                    "sum",
                ),
                "Disponible": (
                    "Disponible",
                    "sum",
                ),
                "Por llegar": (
                    "Por llegar",
                    "sum",
                ),
                "Por despachar": (
                    "Por despachar",
                    "sum",
                ),
                "Precio": (
                    "Precio",
                    "max",
                ),
            },
        )
    )

    grouped.reset_index(
        drop=True,
        inplace=True,
    )

    return add_inventory_status(
        grouped
    )


# ============================================================
# RESUMEN STOCK
# ============================================================

def stock_summary(
    df: pd.DataFrame,
) -> dict:

    raw = stock_view(
        df
    )

    consolidated = consolidate_inventory(
        raw
    )

    if consolidated.empty:
        return {
            "sku_total": 0,
            "units_available": 0,
            "units_incoming": 0,
            "warehouses": 0,
            "available": 0,
            "low": 0,
            "zero": 0,
            "negative": 0,
            "risk": 0,
            "incoming_sku": 0,
        }

    states = (
        consolidated["Estado"]
        .fillna("")
        .astype(str)
    )

    return {
        "sku_total": int(
            consolidated[
                "Código"
            ].nunique()
        ),

        "units_available": int(
            round(
                pd.to_numeric(
                    consolidated["Disponible"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )
        ),

        "units_incoming": int(
            round(
                pd.to_numeric(
                    consolidated["Por llegar"],
                    errors="coerce",
                )
                .fillna(0)
                .sum()
            )
        ),

        "warehouses": int(
            raw["Bodega"]
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        ),

        "available": int(
            states.eq(
                "🟢 Disponible"
            ).sum()
        ),

        "low": int(
            states.eq(
                "🟡 Stock bajo"
            ).sum()
        ),

        "zero": int(
            states.eq(
                "🔴 Sin stock"
            ).sum()
        ),

        "negative": int(
            states.eq(
                "🔴 Negativo"
            ).sum()
        ),

        "risk": int(
            states.eq(
                "🟠 Riesgo despacho"
            ).sum()
        ),

        "incoming_sku": int(
            states.eq(
                "🔵 Por llegar"
            ).sum()
        ),
    }


# ============================================================
# PRODUCTOS CRÍTICOS
# ============================================================

def priority_stock(
    df: pd.DataFrame,
    limit=10,
) -> pd.DataFrame:

    view = consolidate_inventory(
        df
    )

    if view.empty:
        result = view.copy()

        result["Prioridad_score"] = (
            pd.Series(
                dtype=float
            )
        )

        result["Prioridad"] = (
            pd.Series(
                dtype=str
            )
        )

        return result

    def priority(
        row,
    ):

        state = str(
            row.get(
                "Estado",
                "",
            )
        )

        available = float(
            row.get(
                "Disponible",
                0,
            )
            or 0
        )

        incoming = float(
            row.get(
                "Por llegar",
                0,
            )
            or 0
        )

        outgoing = float(
            row.get(
                "Por despachar",
                0,
            )
            or 0
        )

        # Negativo
        if "Negativo" in state:
            return 100, "Alta"

        # Sin stock sin reposición
        if (
            "Sin stock" in state
            and incoming <= 0
        ):
            return 98, "Alta"

        # Sin stock pero viene mercadería
        if "Sin stock" in state:
            return 94, "Alta"

        # Riesgo despacho
        if (
            "Riesgo" in state
            or (
                outgoing > available
                and outgoing > 0
            )
        ):
            return 90, "Alta"

        # Stock bajo
        if "Stock bajo" in state:
            return 75, "Media"

        # Reposición
        if "Por llegar" in state:
            return 50, "Media"

        return 0, "Baja"

    scoring = view.apply(
        lambda row: pd.Series(
            priority(row),
            index=[
                "Prioridad_score",
                "Prioridad",
            ],
        ),
        axis=1,
    )

    result = pd.concat(
        [
            view.reset_index(
                drop=True
            ),
            scoring.reset_index(
                drop=True
            ),
        ],
        axis=1,
    )

    result = result[
        result[
            "Prioridad_score"
        ] > 0
    ]

    result = result.sort_values(
        [
            "Prioridad_score",
            "Disponible",
        ],
        ascending=[
            False,
            True,
        ],
    )

    return (
        result
        .head(
            int(limit)
        )
        .reset_index(
            drop=True
        )
    )