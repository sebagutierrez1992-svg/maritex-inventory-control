import pandas as pd


def stock_summary(df: pd.DataFrame) -> dict:
    available_col = (
        "StockDisponible_num"
        if "StockDisponible_num" in df.columns
        else None
    )

    units = float(df[available_col].sum()) if available_col else 0.0

    return {
        "sku_total": int(df["Código"].nunique()) if "Código" in df.columns else len(df),
        "units_available": int(round(units)),
        "warehouses": int(df["Bodega"].nunique()) if "Bodega" in df.columns else 0,
    }


def top_stock(df: pd.DataFrame, n=20) -> pd.DataFrame:
    col = "StockDisponible_num"
    if col not in df.columns:
        return pd.DataFrame()
    return df.sort_values(col, ascending=False).head(n).copy()
