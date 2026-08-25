from datetime import datetime
import pandas as pd


MONTH_NAMES_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre",
}


def month_label_es(period_value) -> str:
    period = pd.Period(period_value, freq="M")
    return f"{MONTH_NAMES_ES[period.month]} {period.year}"


def month_bounds(period_value):
    period = pd.Period(period_value, freq="M")
    return period.start_time.date(), period.end_time.date()


def available_months(df, date_col="Fecha_dt"):
    if date_col not in df.columns:
        return []
    dates = df[date_col].dropna()
    if dates.empty:
        return []
    return (
        dates.dt.to_period("M")
        .drop_duplicates()
        .sort_values(ascending=False)
        .tolist()
    )


def business_days(start_date, end_date) -> int:
    if start_date is None or end_date is None or end_date < start_date:
        return 0
    return len(pd.bdate_range(start=start_date, end=end_date))
