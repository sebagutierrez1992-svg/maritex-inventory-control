import pandas as pd
from services.erp_sales import resolve_amount_column


def test_prefers_total_when_it_has_values():
    df = pd.DataFrame({
        "Total": ["1000", "2000"],
        "TotalIngreso": ["900", "1800"],
    })
    col, label = resolve_amount_column(df)
    assert col == "Total"
    assert label == "Total"


def test_uses_total_ingreso_when_total_zero():
    df = pd.DataFrame({
        "Total": ["0", "0"],
        "TotalIngreso": ["900", "1800"],
    })
    col, label = resolve_amount_column(df)
    assert col == "TotalIngreso"
