import re


def parse_number(value) -> float:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return 0.0

    text = text.replace("$", "").replace(" ", "")

    if "," in text and "." in text:
        # Chilean format: 1.234.567,89
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".")
    else:
        # Thousands separators only.
        if text.count(".") > 1:
            text = text.replace(".", "")

    text = re.sub(r"[^0-9.\-]", "", text)

    try:
        return float(text)
    except Exception:
        return 0.0


def format_clp(value) -> str:
    try:
        number = int(round(float(value)))
    except Exception:
        number = 0
    return "$" + f"{number:,}".replace(",", ".")
