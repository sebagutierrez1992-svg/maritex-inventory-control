import pandas as pd
from services.erp_sales import parse_sales_dates


def test_day_first_dash_format():
    s = pd.Series(["24-08-2026 10:00:00"])
    out = parse_sales_dates(s)
    assert out.iloc[0].day == 24
    assert out.iloc[0].month == 8
