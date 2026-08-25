import pandas as pd


def calendar_days(start_date, end_date) -> int:
    if start_date is None or end_date is None or end_date < start_date:
        return 0
    return (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1


def business_days(start_date, end_date) -> int:
    if start_date is None or end_date is None or end_date < start_date:
        return 0
    return len(pd.bdate_range(start=start_date, end=end_date))


def project_sales(actual_sales, start_date, actual_end, target_end, mode="calendar"):
    day_fn = business_days if mode == "business" else calendar_days
    elapsed = day_fn(start_date, actual_end)
    target = day_fn(start_date, target_end)

    if elapsed <= 0:
        return {
            "daily_run_rate": 0.0,
            "projected_sales": 0.0,
            "elapsed_units": 0,
            "target_units": target,
        }

    run_rate = float(actual_sales) / elapsed
    projected = float(actual_sales) if target_end <= actual_end else run_rate * target

    return {
        "daily_run_rate": run_rate,
        "projected_sales": projected,
        "elapsed_units": elapsed,
        "target_units": target,
    }
