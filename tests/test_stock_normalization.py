import pandas as pd
from services.erp_stock import normalize_stock


def test_stock_code_normalization():
    df = pd.DataFrame({
        "Producto": ["ABC 123", "200.0"],
        "StockDisponible": ["10", "5"],
    })
    out = normalize_stock(df)
    assert list(out["Código"]) == ["ABC123", "200"]
    assert out["StockDisponible_num"].sum() == 15
