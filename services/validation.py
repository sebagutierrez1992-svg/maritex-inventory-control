import pandas as pd


def validate_sales_source(df: pd.DataFrame) -> dict:
    required = ["TipoDocto", "Fecha_dt", "VentaFirmadaConIVA"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"ERP Ventas incompleto. Faltan: {', '.join(missing)}")

    commercial = df[df["Grupo comercial"].isin(["Factura", "Boleta", "Nota de crédito"])]

    dates = commercial["Fecha_dt"].dropna()
    return {
        "rows": int(len(df)),
        "commercial_rows": int(len(commercial)),
        "min_date": dates.min().strftime("%d/%m/%Y") if not dates.empty else None,
        "max_date": dates.max().strftime("%d/%m/%Y") if not dates.empty else None,
        "sellers": int(commercial["Vendedor"].nunique()) if "Vendedor" in commercial.columns else 0,
        "net_sales_with_vat": float(commercial["VentaFirmadaConIVA"].sum()),
        "amount_column": (
            commercial["VentaMontoCampo"].dropna().iloc[0]
            if "VentaMontoCampo" in commercial.columns and not commercial.empty
            else None
        ),
    }


def validate_stock_source(df: pd.DataFrame) -> dict:
    if "Código" not in df.columns:
        raise ValueError("ERP Stock sin Código normalizado.")

    return {
        "rows": int(len(df)),
        "sku": int(df["Código"].nunique()),
        "warehouses": int(df["Bodega"].nunique()) if "Bodega" in df.columns else 0,
    }
