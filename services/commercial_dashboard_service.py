

import pandas as pd

from analytics.sales_metrics import calculate_commercial_totals


VAT_RATE = 0.19
VALID_GROUPS = ["Factura", "Boleta", "Nota de crédito"]

# Catálogo comercial único.
# Todo Dashboard / Resumen Ejecutivo debe usar este mismo catálogo.
SELLER_CATALOG = {
    "03": ("GC1-DANIEL ALVARADO", "Vendedores"),
    "04": ("ROXANA VALENCIA", "Vendedores"),
    "05": ("GRACIELA SANTANDER", "Vendedores"),
    "06": ("CLAUDIA LOPEZ", "Vendedores"),
    "07": ("LORENA OPAZO", "Vendedores"),
    "08": ("MARIO BRITO", "Vendedores"),
    "09": ("XIMENA CROVETTO", "Vendedores"),
    "11": ("CAROLINA CROCKETT", "Vendedores"),
    "12": ("JOSE GONZALEZ", "Vendedores"),
    "16": ("MATIAS CHOMALI", "Vendedores"),
    "30": ("VENDEDOR ECOMMERS B2C", "Ecommerce / Marketplace"),
    "31": ("VENDEDOR ECOMMERS NOLK", "Ecommerce / Marketplace"),
    "32": ("VENDEDOR ECOMMERS", "Ecommerce / Marketplace"),
    "34": ("MKP MERCADO LIBRE", "Ecommerce / Marketplace"),
    "35": ("MKP - PARIS", "Ecommerce / Marketplace"),
    "43": ("SEBASTIAN ROCCO", "Vendedores"),
    "44": ("MACARENA DE LA ORDEN", "Vendedores"),
    "45": ("MARIELY ROSALES", "Vendedores"),
    "46": ("MELANY VARGAS", "Vendedores"),
    "47": ("MARIA BERNARD", "Vendedores"),
    "48": ("EURO QUIÑONEZ", "Vendedores"),
    "49": ("FRANCISCO PEREZ", "Vendedores"),
    "50": ("GINO MATIUS", "Vendedores"),
    "51": ("NELSON SAN MARTIN", "Vendedores"),
    "54": ("JOHANA OBREQUE", "Vendedores"),
    "60": ("JOSE LUIS ROLANO", "Vendedores"),
    "70": ("ANDRES ESPINOZA", "Vendedores"),
}


def _norm_text(value) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("_", " ")
        .replace("-", " ")
    )


def seller_key(value) -> str | None:
    raw = str(value or "").strip()
    norm = _norm_text(raw)

    raw_code = (
        raw.split(".")[0]
        if raw.replace(".", "", 1).isdigit()
        else raw
    )

    raw_code = (
        raw_code.zfill(2)
        if raw_code.isdigit() and len(raw_code) <= 2
        else raw_code
    )

    if raw_code in SELLER_CATALOG:
        return raw_code

    for code, (name, _) in SELLER_CATALOG.items():
        if (
            raw == code
            or raw.startswith(code + " ")
            or raw.startswith(code + "-")
        ):
            return code

        normalized_name = _norm_text(name)

        if (
            norm == normalized_name
            or (
                normalized_name
                and normalized_name in norm
            )
        ):
            return code

    return None


def seller_name(code) -> str:
    code = str(code or "").strip()
    return (
        SELLER_CATALOG.get(code, (code, "Otros"))[0]
        if code
        else "Sin vendedor"
    )


def find_client_column(df: pd.DataFrame) -> str | None:
    if df is None or df.empty:
        return None

    candidates = [
        "RazonSocial",
        "Razón social",
        "Razon social",
        "Nombre cliente",
        "Nombre Cliente",
        "CLIENTE",
    ]

    normalized = {
        _norm_text(col): col
        for col in df.columns
    }

    for candidate in candidates:
        key = _norm_text(candidate)
        if key in normalized:
            return normalized[key]

    return None


def prepare_commercial_base(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construye LA base comercial oficial usada tanto por Inicio como
    por Resumen Ejecutivo.

    Reglas:
    1. Sólo Factura, Boleta y Nota de crédito.
    2. Fecha_dt válida.
    3. Sólo vendedores/canales contenidos en SELLER_CATALOG.
       Esto replica el comportamiento del Resumen Ejecutivo aprobado.
    4. VentaMonto_num se conserva sin modificación.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    required = {
        "Grupo comercial",
        "Fecha_dt",
        "VentaMonto_num",
    }

    if not required.issubset(df.columns):
        return pd.DataFrame()

    out = df[
        df["Grupo comercial"].isin(
            VALID_GROUPS
        )
    ].copy()

    if out.empty:
        return out

    out["Fecha_dt"] = pd.to_datetime(
        out["Fecha_dt"],
        errors="coerce",
    )

    out = out.dropna(
        subset=["Fecha_dt"]
    ).copy()

    if "Vendedor" not in out.columns:
        out["_VendedorCodigo"] = None
        out["_VendedorNombre"] = None
        out["_VendedorGrupo"] = None
        return out.iloc[0:0].copy()

    out["_VendedorCodigo"] = (
        out["Vendedor"].map(
            seller_key
        )
    )

    out["_VendedorNombre"] = (
        out["_VendedorCodigo"].map(
            lambda code: (
                SELLER_CATALOG[code][0]
                if code in SELLER_CATALOG
                else None
            )
        )
    )

    out["_VendedorGrupo"] = (
        out["_VendedorCodigo"].map(
            lambda code: (
                SELLER_CATALOG[code][1]
                if code in SELLER_CATALOG
                else None
            )
        )
    )

    # Esta era la diferencia que quedaba entre Dashboard y Resumen:
    # Resumen Ejecutivo excluía filas cuyo vendedor no pertenecía al
    # catálogo comercial y Dashboard aún las estaba incluyendo.
    out = out[
        out["_VendedorCodigo"].notna()
    ].copy()

    return out


def filter_commercial_view(
    base: pd.DataFrame,
    start_date,
    end_date,
    seller_group: str | None = None,
    seller_code: str | None = None,
) -> pd.DataFrame:
    if base is None or base.empty:
        return pd.DataFrame()

    out = base.copy()

    if (
        seller_group
        and seller_group != "Todos"
    ):
        out = out[
            out["_VendedorGrupo"].eq(
                seller_group
            )
        ].copy()

    if seller_code:
        out = out[
            out["_VendedorCodigo"].eq(
                str(seller_code)
            )
        ].copy()

    dates = out["Fecha_dt"].dt.date

    return out[
        (dates >= start_date)
        & (dates <= end_date)
    ].copy()


def signed_amount(
    df: pd.DataFrame,
    no_vat: bool = False,
) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    amount = pd.to_numeric(
        df["VentaMonto_num"],
        errors="coerce",
    ).fillna(0).abs()

    if no_vat:
        amount = amount / (1 + VAT_RATE)

    sign = (
        df["Grupo comercial"]
        .map(
            {
                "Factura": 1,
                "Boleta": 1,
                "Nota de crédito": -1,
            }
        )
        .fillna(0)
    )

    return amount * sign


def commercial_metrics(
    df: pd.DataFrame,
    no_vat: bool = False,
    client_col: str | None = None,
) -> dict:
    """
    KPI oficial compartido.

    Si Inicio y Resumen Ejecutivo entregan la misma vista `df`,
    esta función garantiza exactamente los mismos resultados.
    """
    result = {
        "net": 0.0,
        "gross": 0.0,
        "credits": 0.0,
        "docs": 0,
        "clients": 0,
        "ticket": 0.0,
    }

    if df is None or df.empty:
        return result

    totals = calculate_commercial_totals(
        df,
        VAT_RATE,
    )

    result["net"] = float(
        totals[
            "venta_neta_sin_iva"
            if no_vat
            else "venta_neta_con_iva"
        ]
    )

    result["gross"] = float(
        totals[
            "ventas_brutas_sin_iva"
            if no_vat
            else "ventas_brutas_con_iva"
        ]
    )

    result["credits"] = float(
        totals[
            "notas_credito_sin_iva"
            if no_vat
            else "notas_credito_con_iva"
        ]
    )

    sale_docs = df[
        df["Grupo comercial"].isin(
            ["Factura", "Boleta"]
        )
    ].copy()

    result["docs"] = (
        int(
            sale_docs["Numero"].nunique()
        )
        if "Numero" in sale_docs.columns
        else int(len(sale_docs))
    )

    client_col = (
        client_col
        if client_col
        and client_col in sale_docs.columns
        else find_client_column(sale_docs)
    )

    if client_col:
        result["clients"] = int(
            sale_docs[client_col]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .nunique()
        )

    result["ticket"] = (
        result["gross"]
        / result["docs"]
        if result["docs"]
        else 0.0
    )

    return result