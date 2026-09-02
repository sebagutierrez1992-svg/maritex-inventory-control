

from typing import Any
import re
import xml.etree.ElementTree as ET

import pandas as pd

from services.remote_stock import load_remote_stock


ALTERNATIVE_WAREHOUSES = ("CD", "PATRONATO")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_sku(value: Any) -> str:
    text = _clean_text(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _safe_int(value: Any) -> int:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return 0
    return int(round(float(parsed)))


def _flatten_text(value: Any) -> list[str]:
    """
    Convierte estructuras anidadas en una lista de textos.
    Se usa como respaldo cuando el ERP entrega el faltante
    dentro de MENSAJE / VALIDACION / raw y no en missing_stock.
    """
    result: list[str] = []

    if value is None:
        return result

    if isinstance(value, str):
        text = value.strip()
        if text:
            result.append(text)
        return result

    if isinstance(value, dict):
        for item in value.values():
            result.extend(_flatten_text(item))
        return result

    if isinstance(value, (list, tuple)):
        for item in value:
            result.extend(_flatten_text(item))
        return result

    result.append(str(value))
    return result


def _extract_missing_qty(*values: Any) -> int:
    """
    Busca cantidades faltantes en mensajes ERP, por ejemplo:

        Faltan 4 UN
        Faltan 78 UN Stock Real...
        faltan 2 unidades

    Devuelve 0 cuando no existe evidencia suficiente.
    """
    texts: list[str] = []

    for value in values:
        texts.extend(_flatten_text(value))

    combined = " ".join(texts)

    patterns = (
        r"\bfaltan?\s+([0-9]+(?:[.,][0-9]+)?)\s*(?:un|und|uds|unidades?)\b",
        r"\bstock\s+faltante\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)\b",
        r"\bfaltante\s*[:=]?\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:un|und|uds|unidades?)?\b",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            combined,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        raw = match.group(1).replace(",", ".")

        try:
            return max(
                int(round(float(raw))),
                0,
            )
        except (TypeError, ValueError):
            continue

    return 0


def _local_name(tag: str) -> str:
    return str(tag).split("}")[-1]


def _child_text(element: ET.Element, tag_name: str) -> str:
    wanted = tag_name.lower()
    for child in list(element):
        if _local_name(child.tag).lower() == wanted:
            return _clean_text(child.text)
    return ""


def _split_warehouse_location(warehouse: Any, location: Any = "") -> tuple[str, str]:
    """
    Normaliza respuestas ERP que mezclan ambos datos, por ejemplo:
    'Bodega 01-CASA MATRIZ,Ubicación= PRINCIPAL'.
    """
    clean_warehouse = _clean_text(warehouse)
    clean_location = _clean_text(location)

    if clean_warehouse:
        match = re.search(
            r"^(?:Bodega\s*)?(.+?)(?:,\s*Ubicaci[oó]n\s*=\s*(.+))$",
            clean_warehouse,
            flags=re.IGNORECASE,
        )
        if match:
            clean_warehouse = _clean_text(match.group(1))
            if not clean_location:
                clean_location = _clean_text(match.group(2))

    clean_warehouse = re.sub(
        r"^Bodega\s+",
        "",
        clean_warehouse,
        flags=re.IGNORECASE,
    ).strip()

    return clean_warehouse, clean_location


def extract_order_line_from_xml_send(xml_send: Any, sku: Any) -> dict:
    clean_sku = _clean_sku(sku)
    result = {
        "sku": clean_sku,
        "product_name": "",
        "requested_qty": 0,
        "warehouse": "",
        "location": "",
        "line": "",
        "sequence": "",
    }

    if not clean_sku:
        return result

    xml_text = _clean_text(xml_send)
    if not xml_text:
        return result

    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, ValueError, TypeError):
        return result

    for element in root.iter():
        if _local_name(element.tag).upper() != "DETALLE":
            continue

        product_code = _clean_sku(_child_text(element, "Producto"))
        if product_code != clean_sku:
            continue

        product_name = (
            _child_text(element, "Comentario")
            or _child_text(element, "Glosa")
            or _child_text(element, "Descripcion")
            or _child_text(element, "Descripción")
            or _child_text(element, "Analisis1")
        )

        result.update(
            {
                "product_name": product_name,
                "requested_qty": _safe_int(_child_text(element, "Cantidad")),
                "warehouse": _child_text(element, "Bodega"),
                "location": _child_text(element, "Ubicacion"),
                "line": _child_text(element, "Linea"),
                "sequence": _child_text(element, "Secuencia"),
            }
        )
        return result

    return result


def get_alternative_stock(sku: Any) -> dict:
    clean_sku = _clean_sku(sku)
    result = {
        "sku": clean_sku,
        "product_name": "",
        "warehouses": {"CD": 0, "PATRONATO": 0},
        "source": "Llegadas_OK / stock.json",
        "loaded_at": "",
        "ok": False,
        "message": "",
    }

    if not clean_sku:
        result["message"] = "No existe SKU para consultar stock."
        return result

    try:
        stock_df, meta = load_remote_stock()
    except Exception as exc:
        result["message"] = f"No fue posible consultar Llegadas_OK: {exc}"
        return result

    if stock_df is None or stock_df.empty:
        result["message"] = "Llegadas_OK no entregó stock."
        return result

    required_columns = {"Producto", "Bodega", "Stock"}
    if not required_columns.issubset(set(stock_df.columns)):
        result["message"] = "La estructura de stock no contiene Producto, Bodega y Stock."
        return result

    work = stock_df.copy()
    work["_sku_match"] = (
        work["Producto"]
        .astype(str)
        .str.strip()
        .str.replace(".0", "", regex=False)
    )
    work["_warehouse_match"] = (
        work["Bodega"]
        .astype(str)
        .str.strip()
        .str.upper()
    )
    work["_stock_num"] = pd.to_numeric(work["Stock"], errors="coerce").fillna(0)

    sku_rows = work[work["_sku_match"] == clean_sku].copy()
    if sku_rows.empty:
        result["message"] = f"El SKU {clean_sku} no existe en Llegadas_OK."
        return result

    if "Descripción" in sku_rows.columns:
        descriptions = sku_rows["Descripción"].dropna().astype(str).str.strip()
        descriptions = descriptions[descriptions != ""]
        if not descriptions.empty:
            result["product_name"] = descriptions.iloc[0]

    for warehouse in ALTERNATIVE_WAREHOUSES:
        rows = sku_rows[sku_rows["_warehouse_match"] == warehouse]
        result["warehouses"][warehouse] = _safe_int(
            rows["_stock_num"].sum() if not rows.empty else 0
        )

    meta = meta or {}
    result["loaded_at"] = _clean_text(
        meta.get("loaded_at") or meta.get("generated_at")
    )
    result["source"] = _clean_text(
        meta.get("source") or "Llegadas_OK / stock.json"
    )
    result["ok"] = True
    return result


def build_transfer_suggestion(warehouse_stock: dict, missing_qty: Any) -> dict:
    missing = max(_safe_int(missing_qty), 0)
    cd = max(_safe_int(warehouse_stock.get("CD", 0)), 0)
    patronato = max(_safe_int(warehouse_stock.get("PATRONATO", 0)), 0)

    result = {
        "missing_qty": missing,
        "coverage": "unknown",
        "covered_qty": 0,
        "remaining_qty": missing,
        "movements": [],
        "message": "",
    }

    if missing <= 0:
        result.update(
            {
                "coverage": "not_required",
                "remaining_qty": 0,
                "message": "No hay una cantidad faltante válida para sugerir traslado.",
            }
        )
        return result

    if cd >= missing:
        result.update(
            {
                "coverage": "total",
                "covered_qty": missing,
                "remaining_qty": 0,
                "movements": [{"warehouse": "CD", "quantity": missing}],
                "message": f"Solicitar {missing} UN desde CD.",
            }
        )
        return result

    if patronato >= missing:
        result.update(
            {
                "coverage": "total",
                "covered_qty": missing,
                "remaining_qty": 0,
                "movements": [{"warehouse": "PATRONATO", "quantity": missing}],
                "message": f"Solicitar {missing} UN desde Patronato.",
            }
        )
        return result

    if cd > 0 and cd + patronato >= missing:
        from_cd = min(cd, missing)
        remaining = missing - from_cd
        from_patronato = min(patronato, remaining)
        movements = []
        if from_cd > 0:
            movements.append({"warehouse": "CD", "quantity": from_cd})
        if from_patronato > 0:
            movements.append({"warehouse": "PATRONATO", "quantity": from_patronato})

        result.update(
            {
                "coverage": "combined",
                "covered_qty": from_cd + from_patronato,
                "remaining_qty": 0,
                "movements": movements,
                "message": (
                    f"Combinar traslado: {from_cd} UN desde CD"
                    + (
                        f" + {from_patronato} UN desde Patronato."
                        if from_patronato > 0
                        else "."
                    )
                ),
            }
        )
        return result

    movements = []
    covered = 0

    if cd > 0:
        qty = min(cd, missing)
        movements.append({"warehouse": "CD", "quantity": qty})
        covered += qty

    remaining = max(missing - covered, 0)

    if remaining > 0 and patronato > 0:
        qty = min(patronato, remaining)
        movements.append({"warehouse": "PATRONATO", "quantity": qty})
        covered += qty

    remaining = max(missing - covered, 0)

    if covered > 0:
        result.update(
            {
                "coverage": "partial",
                "covered_qty": covered,
                "remaining_qty": remaining,
                "movements": movements,
                "message": (
                    f"Se pueden cubrir {covered} de {missing} UN. "
                    f"Continúan faltando {remaining} UN."
                ),
            }
        )
    else:
        result.update(
            {
                "coverage": "none",
                "covered_qty": 0,
                "remaining_qty": missing,
                "movements": [],
                "message": "Sin stock disponible en CD ni Patronato.",
            }
        )

    return result


def build_stock_resolution(order: dict, diagnosis: dict) -> dict:
    diagnosis = diagnosis or {}
    order = order or {}

    stocks = diagnosis.get("stocks") or []
    first_stock = (
        stocks[0]
        if isinstance(stocks, list) and stocks and isinstance(stocks[0], dict)
        else {}
    )

    sku = _clean_sku(
        first_stock.get("product")
        or diagnosis.get("product")
    )

    missing_qty = (
        first_stock.get("missing_stock")
        or first_stock.get("missing_qty")
        or first_stock.get("faltante")
        or diagnosis.get("missing_stock")
        or diagnosis.get("missing_qty")
        or diagnosis.get("faltante")
        or 0
    )

    # Algunas respuestas ERP no dejan el faltante en un campo
    # estructurado y solo lo informan dentro de MENSAJE / VALIDACION.
    # Ejemplo: "Faltan 4 UN del producto 1150524..."
    if _safe_int(missing_qty) <= 0:
        missing_qty = _extract_missing_qty(
            first_stock,
            diagnosis.get("reason"),
            diagnosis.get("motivo"),
            diagnosis.get("message"),
            diagnosis.get("summary"),
            diagnosis.get("raw"),
            order.get("response"),
        )

    xml_line = extract_order_line_from_xml_send(
        order.get("xmlSend"),
        sku,
    )
    alternative_stock = get_alternative_stock(sku)

    product_name = (
        xml_line.get("product_name")
        or alternative_stock.get("product_name")
        or first_stock.get("description")
        or diagnosis.get("description")
        or ""
    )

    # La cantidad pedida debe venir del DETALLE del xmlSend.
    # Como respaldo, usamos campos estructurados solo si existen;
    # nunca inferimos que "faltante ERP" sea igual a "cantidad pedida".
    requested_qty = (
        xml_line.get("requested_qty")
        or first_stock.get("requested_qty")
        or first_stock.get("quantity")
        or first_stock.get("cantidad")
        or diagnosis.get("requested_qty")
        or diagnosis.get("quantity")
        or diagnosis.get("cantidad")
        or 0
    )

    raw_warehouse = (
        xml_line.get("warehouse")
        or first_stock.get("warehouse")
        or diagnosis.get("warehouse")
        or ""
    )
    raw_location = (
        xml_line.get("location")
        or first_stock.get("location")
        or diagnosis.get("location")
        or ""
    )
    current_warehouse, current_location = _split_warehouse_location(
        raw_warehouse,
        raw_location,
    )

    suggestion = build_transfer_suggestion(
        alternative_stock.get("warehouses") or {},
        missing_qty,
    )

    return {
        "sku": sku,
        "product_name": product_name,
        "requested_qty": _safe_int(requested_qty),
        "missing_qty": _safe_int(missing_qty),
        "current_warehouse": current_warehouse,
        "current_location": current_location,
        "line": (
            xml_line.get("line")
            or first_stock.get("line")
            or ""
        ),
        "cd_stock": _safe_int(
            (alternative_stock.get("warehouses") or {}).get("CD", 0)
        ),
        "patronato_stock": _safe_int(
            (alternative_stock.get("warehouses") or {}).get("PATRONATO", 0)
        ),
        "stock_source": alternative_stock.get("source") or "Llegadas_OK / stock.json",
        "stock_loaded_at": alternative_stock.get("loaded_at") or "",
        "stock_lookup_ok": bool(alternative_stock.get("ok")),
        "stock_lookup_message": alternative_stock.get("message") or "",
        "suggestion": suggestion,
    }