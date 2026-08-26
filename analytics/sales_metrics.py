import pandas as pd


COMMERCIAL_GROUPS = [
    "Factura",
    "Boleta",
    "Nota de crédito",
]

SALES_GROUPS = [
    "Factura",
    "Boleta",
]


# ============================================================
# HELPERS
# ============================================================

def _safe_numeric(
    series: pd.Series,
) -> pd.Series:
    """
    Convierte una serie a numérica.

    Valores inválidos:
        -> 0
    """

    return pd.to_numeric(
        series,
        errors="coerce",
    ).fillna(0.0)


def _document_count(
    df: pd.DataFrame,
    mask: pd.Series,
) -> int:
    """
    Cuenta documentos únicos.

    Si existe Numero:
        cuenta Numero único.

    Si no existe:
        utiliza cantidad de filas.
    """

    if df is None or df.empty:
        return 0

    if "Numero" in df.columns:
        return int(
            df.loc[
                mask,
                "Numero",
            ]
            .dropna()
            .astype(str)
            .str.strip()
            .replace(
                "",
                pd.NA,
            )
            .dropna()
            .nunique()
        )

    return int(
        mask.sum()
    )


# ============================================================
# FILTROS DE VENTAS
# ============================================================

def filter_sales(
    df: pd.DataFrame,
    start_date=None,
    end_date=None,
    sellers=None,
    warehouses=None,
    document_types=None,
    client_text="",
) -> pd.DataFrame:

    if (
        df is None
        or df.empty
    ):
        return pd.DataFrame()

    view = df.copy()

    # ========================================================
    # FECHAS
    # ========================================================

    if "Fecha_dt" in view.columns:

        if start_date is not None:

            view = view[
                view[
                    "Fecha_dt"
                ].dt.date
                >= start_date
            ]

        if end_date is not None:

            view = view[
                view[
                    "Fecha_dt"
                ].dt.date
                <= end_date
            ]

    # ========================================================
    # VENDEDORES
    # ========================================================

    if (
        sellers
        and "Vendedor" in view.columns
    ):

        selected = {
            str(x).strip()
            for x in sellers
        }

        view = view[
            view[
                "Vendedor"
            ]
            .fillna(
                "Sin vendedor"
            )
            .astype(str)
            .str.strip()
            .isin(
                selected
            )
        ]

    # ========================================================
    # BODEGAS
    # ========================================================

    if (
        warehouses
        and "Bodega" in view.columns
    ):

        selected = {
            str(x).strip()
            for x in warehouses
        }

        view = view[
            view[
                "Bodega"
            ]
            .fillna(
                "Sin bodega"
            )
            .astype(str)
            .str.strip()
            .isin(
                selected
            )
        ]

    # ========================================================
    # TIPO DOCUMENTO
    # ========================================================

    if (
        document_types
        and "TipoDocto" in view.columns
    ):

        selected = {
            str(x).strip()
            for x in document_types
        }

        view = view[
            view[
                "TipoDocto"
            ]
            .fillna("")
            .astype(str)
            .str.strip()
            .isin(
                selected
            )
        ]

    # ========================================================
    # CLIENTE
    # ========================================================

    if (
        client_text
        and "RazonSocial" in view.columns
    ):

        term = (
            client_text
            .strip()
            .lower()
        )

        if term:

            view = view[
                view[
                    "RazonSocial"
                ]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.contains(
                    term,
                    regex=False,
                )
            ]

    return view.copy()


# ============================================================
# TOTALES COMERCIALES
# ============================================================

def calculate_commercial_totals(
    df: pd.DataFrame,
    vat_rate: float = 0.19,
) -> dict:
    """
    Regla comercial:

    Facturas:
        suman.

    Boletas:
        suman.

    Notas de crédito:
        restan.

    Otros:
        no participan.

    ERP Total:
        se interpreta como monto con IVA.
    """

    empty = {
        "ventas_brutas_con_iva": 0.0,
        "notas_credito_con_iva": 0.0,
        "venta_neta_con_iva": 0.0,

        "ventas_brutas_sin_iva": 0.0,
        "notas_credito_sin_iva": 0.0,
        "venta_neta_sin_iva": 0.0,

        "iva_neto": 0.0,
    }

    if (
        df is None
        or df.empty
    ):
        return empty

    work = df.copy()

    # ========================================================
    # VALIDACIONES
    # ========================================================

    if (
        "VentaMonto_num"
        not in work.columns
    ):
        work[
            "VentaMonto_num"
        ] = 0.0

    if (
        "Grupo comercial"
        not in work.columns
    ):
        work[
            "Grupo comercial"
        ] = "Otro"

    work[
        "VentaMonto_num"
    ] = _safe_numeric(
        work[
            "VentaMonto_num"
        ]
    )

    # ========================================================
    # MÁSCARAS
    # ========================================================

    sales_mask = (
        work[
            "Grupo comercial"
        ]
        .isin(
            SALES_GROUPS
        )
    )

    credit_mask = (
        work[
            "Grupo comercial"
        ]
        .eq(
            "Nota de crédito"
        )
    )

    # ========================================================
    # VENTAS BRUTAS
    #
    # Usamos absoluto para que cualquier signo extraño
    # proveniente del ERP no invierta la lógica comercial.
    # ========================================================

    sales = float(
        work.loc[
            sales_mask,
            "VentaMonto_num",
        ]
        .abs()
        .sum()
    )

    # ========================================================
    # NOTAS DE CRÉDITO
    # ========================================================

    credits = float(
        work.loc[
            credit_mask,
            "VentaMonto_num",
        ]
        .abs()
        .sum()
    )

    # ========================================================
    # VENTA NETA
    # ========================================================

    net_with_vat = (
        sales
        - credits
    )

    divisor = (
        1
        + float(
            vat_rate
        )
    )

    if divisor:

        sales_without_vat = (
            sales
            / divisor
        )

        credits_without_vat = (
            credits
            / divisor
        )

        net_without_vat = (
            net_with_vat
            / divisor
        )

    else:

        sales_without_vat = 0.0
        credits_without_vat = 0.0
        net_without_vat = 0.0

    net_vat = (
        net_with_vat
        - net_without_vat
    )

    return {
        "ventas_brutas_con_iva": sales,
        "notas_credito_con_iva": credits,
        "venta_neta_con_iva": net_with_vat,

        "ventas_brutas_sin_iva": sales_without_vat,
        "notas_credito_sin_iva": credits_without_vat,
        "venta_neta_sin_iva": net_without_vat,

        "iva_neto": net_vat,
    }


# ============================================================
# RESUMEN POR VENDEDOR
# ============================================================

def build_seller_summary(
    df: pd.DataFrame,
    vat_rate: float = 0.19,
) -> pd.DataFrame:

    if (
        df is None
        or df.empty
        or "Vendedor" not in df.columns
    ):
        return pd.DataFrame()

    work = df.copy()

    # ========================================================
    # VENDEDOR
    # ========================================================

    work[
        "Vendedor"
    ] = (
        work[
            "Vendedor"
        ]
        .fillna(
            "Sin vendedor"
        )
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # MONTO
    # ========================================================

    if (
        "VentaMonto_num"
        not in work.columns
    ):
        work[
            "VentaMonto_num"
        ] = 0.0

    work[
        "VentaMonto_num"
    ] = _safe_numeric(
        work[
            "VentaMonto_num"
        ]
    )

    if (
        "Grupo comercial"
        not in work.columns
    ):
        work[
            "Grupo comercial"
        ] = "Otro"

    # ========================================================
    # IMPACTO COMERCIAL
    #
    # Factura / Boleta:
    #   positivo
    #
    # Nota crédito:
    #   negativo
    #
    # Otro:
    #   cero
    # ========================================================

    sales_mask = (
        work[
            "Grupo comercial"
        ]
        .isin(
            SALES_GROUPS
        )
    )

    credit_mask = (
        work[
            "Grupo comercial"
        ]
        .eq(
            "Nota de crédito"
        )
    )

    work[
        "Impacto con IVA"
    ] = 0.0

    work.loc[
        sales_mask,
        "Impacto con IVA",
    ] = (
        work.loc[
            sales_mask,
            "VentaMonto_num",
        ]
        .abs()
    )

    work.loc[
        credit_mask,
        "Impacto con IVA",
    ] = -(
        work.loc[
            credit_mask,
            "VentaMonto_num",
        ]
        .abs()
    )

    # ========================================================
    # SIN IVA
    # ========================================================

    divisor = (
        1
        + float(
            vat_rate
        )
    )

    if divisor:

        work[
            "Impacto sin IVA"
        ] = (
            work[
                "Impacto con IVA"
            ]
            / divisor
        )

    else:

        work[
            "Impacto sin IVA"
        ] = 0.0

    # ========================================================
    # COLUMNAS DE DOCUMENTOS / CLIENTES
    # ========================================================

    number_col = (
        "Numero"
        if "Numero" in work.columns
        else "Vendedor"
    )

    client_col = (
        "RazonSocial"
        if "RazonSocial" in work.columns
        else "Vendedor"
    )

    # ========================================================
    # SOLO DOCUMENTOS COMERCIALES
    # ========================================================

    commercial = work[
        work[
            "Grupo comercial"
        ]
        .isin(
            COMMERCIAL_GROUPS
        )
    ].copy()

    if commercial.empty:
        return pd.DataFrame()

    # ========================================================
    # AGRUPACIÓN
    # ========================================================

    result = (
        commercial
        .groupby(
            "Vendedor",
            as_index=False,
        )
        .agg(
            Venta_con_IVA=(
                "Impacto con IVA",
                "sum",
            ),
            Venta_sin_IVA=(
                "Impacto sin IVA",
                "sum",
            ),
            Documentos=(
                number_col,
                "nunique",
            ),
            Clientes=(
                client_col,
                "nunique",
            ),
        )
        .sort_values(
            "Venta_con_IVA",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )

    # ========================================================
    # PARTICIPACIÓN
    # ========================================================

    total_net = float(
        result[
            "Venta_con_IVA"
        ].sum()
    )

    if total_net:

        result[
            "Participación %"
        ] = (
            result[
                "Venta_con_IVA"
            ]
            / total_net
            * 100
        )

    else:

        result[
            "Participación %"
        ] = 0.0

    # ========================================================
    # TICKET PROMEDIO
    # ========================================================

    result[
        "Ticket promedio"
    ] = result.apply(
        lambda row: (
            row[
                "Venta_con_IVA"
            ]
            / row[
                "Documentos"
            ]
            if row[
                "Documentos"
            ]
            else 0.0
        ),
        axis=1,
    )

    return result


# ============================================================
# PERÍODO ANTERIOR
# ============================================================

def previous_period_bounds(
    start_date,
    end_date,
):
    """
    Devuelve un período inmediatamente anterior
    con la misma cantidad de días.
    """

    if (
        start_date is None
        or end_date is None
    ):
        return (
            None,
            None,
        )

    start = pd.Timestamp(
        start_date
    )

    end = pd.Timestamp(
        end_date
    )

    period_days = max(
        (
            end
            - start
        ).days
        + 1,
        1,
    )

    # Día inmediatamente anterior
    prev_end = (
        start
        - pd.Timedelta(
            days=1
        )
    )

    prev_start = (
        prev_end
        - pd.Timedelta(
            days=period_days - 1
        )
    )

    return (
        prev_start,
        prev_end,
    )


# ============================================================
# COMPATIBILIDAD CON VISTAS ANTIGUAS
# ============================================================

def commercial_totals(
    df: pd.DataFrame,
    vat_rate: float = 0.19,
) -> dict:
    """
    Compatibilidad para:
    - Resumen Ejecutivo
    - otras vistas antiguas

    Utiliza exactamente la misma regla comercial
    de calculate_commercial_totals().
    """

    totals = calculate_commercial_totals(
        df,
        vat_rate=vat_rate,
    )

    # ========================================================
    # SIN DATOS
    # ========================================================

    if (
        df is None
        or df.empty
    ):

        return {
            "gross_with_vat": 0.0,
            "credits_with_vat": 0.0,
            "net_with_vat": 0.0,

            "gross_without_vat": 0.0,
            "credits_without_vat": 0.0,
            "net_without_vat": 0.0,

            "sales_documents": 0,
            "credit_documents": 0,
            "commercial_documents": 0,

            "ticket_with_vat": 0.0,
            "ticket_without_vat": 0.0,
        }

    work = df.copy()

    if (
        "Grupo comercial"
        not in work.columns
    ):
        work[
            "Grupo comercial"
        ] = "Otro"

    # ========================================================
    # MÁSCARAS
    # ========================================================

    sales_mask = (
        work[
            "Grupo comercial"
        ]
        .isin(
            SALES_GROUPS
        )
    )

    credit_mask = (
        work[
            "Grupo comercial"
        ]
        .eq(
            "Nota de crédito"
        )
    )

    commercial_mask = (
        sales_mask
        | credit_mask
    )

    # ========================================================
    # DOCUMENTOS
    # ========================================================

    sales_documents = _document_count(
        work,
        sales_mask,
    )

    credit_documents = _document_count(
        work,
        credit_mask,
    )

    commercial_documents = _document_count(
        work,
        commercial_mask,
    )

    # ========================================================
    # TICKET PROMEDIO
    #
    # Se calcula sobre documentos de venta
    # Facturas + Boletas.
    # ========================================================

    ticket_with_vat = (
        totals[
            "ventas_brutas_con_iva"
        ]
        / sales_documents
        if sales_documents
        else 0.0
    )

    ticket_without_vat = (
        totals[
            "ventas_brutas_sin_iva"
        ]
        / sales_documents
        if sales_documents
        else 0.0
    )

    # ========================================================
    # RESULTADO
    # ========================================================

    return {
        "gross_with_vat": totals[
            "ventas_brutas_con_iva"
        ],

        "credits_with_vat": totals[
            "notas_credito_con_iva"
        ],

        "net_with_vat": totals[
            "venta_neta_con_iva"
        ],

        "gross_without_vat": totals[
            "ventas_brutas_sin_iva"
        ],

        "credits_without_vat": totals[
            "notas_credito_sin_iva"
        ],

        "net_without_vat": totals[
            "venta_neta_sin_iva"
        ],

        "sales_documents": (
            sales_documents
        ),

        "credit_documents": (
            credit_documents
        ),

        "commercial_documents": (
            commercial_documents
        ),

        "ticket_with_vat": (
            ticket_with_vat
        ),

        "ticket_without_vat": (
            ticket_without_vat
        ),
    }


# ============================================================
# COMPATIBILIDAD SELLER PERFORMANCE
# ============================================================

def seller_performance(
    df: pd.DataFrame,
    include_vat: bool = True,
) -> pd.DataFrame:
    """
    Mantiene compatibilidad con vistas antiguas que
    todavía utilizan seller_performance().

    Internamente reutiliza build_seller_summary().
    """

    result = build_seller_summary(
        df,
        vat_rate=0.19,
    )

    if (
        result is None
        or result.empty
    ):
        return pd.DataFrame()

    if include_vat:

        output = result[
            [
                "Vendedor",
                "Venta_con_IVA",
                "Documentos",
                "Ticket promedio",
            ]
        ].copy()

        output = output.rename(
            columns={
                "Venta_con_IVA": "Venta",
            }
        )

    else:

        output = result[
            [
                "Vendedor",
                "Venta_sin_IVA",
                "Documentos",
            ]
        ].copy()

        output = output.rename(
            columns={
                "Venta_sin_IVA": "Venta",
            }
        )

        output[
            "Ticket promedio"
        ] = output.apply(
            lambda row: (
                row[
                    "Venta"
                ]
                / row[
                    "Documentos"
                ]
                if row[
                    "Documentos"
                ]
                else 0.0
            ),
            axis=1,
        )

    return (
        output
        .sort_values(
            "Venta",
            ascending=False,
        )
        .reset_index(
            drop=True
        )
    )