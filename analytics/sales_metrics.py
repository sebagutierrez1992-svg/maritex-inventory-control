import pandas as pd


def filter_sales(
    df: pd.DataFrame,
    start_date=None,
    end_date=None,
    sellers=None,
    warehouses=None,
    document_types=None,
    client_text="",
) -> pd.DataFrame:
    view = df.copy()

    if start_date is not None and "Fecha_dt" in view.columns:
        view = view[view["Fecha_dt"].dt.date >= start_date]

    if end_date is not None and "Fecha_dt" in view.columns:
        view = view[view["Fecha_dt"].dt.date <= end_date]

    if sellers and "Vendedor" in view.columns:
        view = view[
            view["Vendedor"].fillna("Sin vendedor").astype(str).str.strip().isin(sellers)
        ]

    if warehouses and "Bodega" in view.columns:
        view = view[
            view["Bodega"].fillna("Sin bodega").astype(str).str.strip().isin(warehouses)
        ]

    if document_types and "TipoDocto" in view.columns:
        view = view[view["TipoDocto"].isin(document_types)]

    if client_text and "RazonSocial" in view.columns:
        term = client_text.strip().lower()
        view = view[
            view["RazonSocial"]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.contains(term, regex=False)
        ]

    return view


def commercial_totals(df: pd.DataFrame) -> dict:
    commercial = df[df["Grupo comercial"].isin(["Factura", "Boleta", "Nota de crédito"])]

    return {
        "net_with_vat": float(commercial["VentaFirmadaConIVA"].sum()),
        "net_without_vat": float(commercial["VentaFirmadaSinIVA"].sum()),
        "gross_with_vat": float(
            commercial.loc[
                commercial["Grupo comercial"].isin(["Factura", "Boleta"]),
                "VentaFirmadaConIVA",
            ].sum()
        ),
        "credits_with_vat": float(
            commercial.loc[
                commercial["Grupo comercial"].eq("Nota de crédito"),
                "VentaFirmadaConIVA",
            ].abs().sum()
        ),
    }


def seller_performance(df: pd.DataFrame, include_vat=True) -> pd.DataFrame:
    amount = "VentaFirmadaConIVA" if include_vat else "VentaFirmadaSinIVA"

    if "Vendedor" not in df.columns:
        return pd.DataFrame()

    work = df.copy()
    work["Vendedor"] = work["Vendedor"].fillna("Sin vendedor").astype(str).str.strip()

    number_col = "Numero" if "Numero" in work.columns else "Vendedor"

    result = (
        work.groupby("Vendedor", as_index=False)
        .agg(
            Venta=(amount, "sum"),
            Documentos=(number_col, "nunique"),
        )
    )
    result["Ticket promedio"] = result.apply(
        lambda r: r["Venta"] / r["Documentos"] if r["Documentos"] else 0.0,
        axis=1,
    )
    return result.sort_values("Venta", ascending=False)
