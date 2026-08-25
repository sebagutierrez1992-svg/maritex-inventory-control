from utils.text import normalize_name


def find_casa_matriz(warehouse_values) -> list[str]:
    values = [str(v).strip() for v in warehouse_values if str(v).strip()]
    return [v for v in values if "casamatriz" in normalize_name(v)]


def apply_publishable_stock(stock: float, reserve: int = 0, max_stock: int | None = None) -> int:
    publish = max(0, float(stock) - float(reserve))
    if max_stock is not None:
        publish = min(publish, float(max_stock))
    return int(round(publish))
