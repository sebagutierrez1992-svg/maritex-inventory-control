from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET

from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_URL = "https://maritex.azurewebsites.net/api"
LOGIN_URL = "https://maritex.azurewebsites.net/login"

CHANNEL_ENDPOINTS = {
    "B2B": "PendingOrders",
    "B2C": "PendingOrdersB2C",
    "NOLK": "PendingOrdersNolk",
}

DEFAULT_TIMEOUT = 20
TOKEN_EXPIRY_MARGIN = 60


# ============================================================
# CACHE AUTENTICACIÓN
# ============================================================

_ACCESS_TOKEN = ""
_ACCESS_TOKEN_EXPIRES_AT = 0.0
_REFRESH_TOKEN = ""

_AUTH_LOCK = Lock()


# ============================================================
# EXCEPCIONES
# ============================================================

class EcommerceERPError(Exception):
    pass


# ============================================================
# MODELO API
# ============================================================

@dataclass
class APIResult:
    ok: bool
    status_code: int | None
    data: Any = None
    message: str = ""
    url: str = ""


# ============================================================
# CREDENCIALES
# ============================================================

def _get_email() -> str:
    return os.getenv(
        "MARITEX_ERP_EMAIL",
        "",
    ).strip()


def _get_password() -> str:
    return os.getenv(
        "MARITEX_ERP_PASSWORD",
        "",
    ).strip()


def _get_manual_token() -> str:
    return os.getenv(
        "MARITEX_ERP_BEARER_TOKEN",
        "",
    ).strip()


def has_login_credentials() -> bool:
    return bool(
        _get_email()
        and _get_password()
    )


def has_manual_token() -> bool:
    return bool(
        _get_manual_token()
    )


def has_token() -> bool:
    return (
        has_login_credentials()
        or has_manual_token()
    )


# ============================================================
# DECODIFICAR RESPUESTAS
# ============================================================

def _decode_response(raw: bytes) -> Any:

    if not raw:
        return None

    text = raw.decode(
        "utf-8",
        errors="replace",
    ).strip()

    if not text:
        return None

    try:
        return json.loads(text)

    except json.JSONDecodeError:
        return text


# ============================================================
# LOGIN AUTOMÁTICO
# ============================================================

def _cached_token_is_valid() -> bool:

    return bool(
        _ACCESS_TOKEN
        and time.time()
        < (
            _ACCESS_TOKEN_EXPIRES_AT
            - TOKEN_EXPIRY_MARGIN
        )
    )


def _login() -> str:

    global _ACCESS_TOKEN
    global _ACCESS_TOKEN_EXPIRES_AT
    global _REFRESH_TOKEN

    email = _get_email()
    password = _get_password()

    if not email or not password:

        raise EcommerceERPError(
            "No están configuradas "
            "MARITEX_ERP_EMAIL y "
            "MARITEX_ERP_PASSWORD."
        )

    payload = {
        "email": email,
        "password": password,
        "twoFactorCode": "",
        "twoFactorRecoveryCode": "",
    }

    body = json.dumps(
        payload
    ).encode("utf-8")

    request = Request(
        LOGIN_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "User-Agent": "Maritex-Inventory-Control/1.0",
        },
    )

    try:

        with urlopen(
            request,
            timeout=DEFAULT_TIMEOUT,
        ) as response:

            data = _decode_response(
                response.read()
            )

            if not isinstance(
                data,
                dict,
            ):
                raise EcommerceERPError(
                    "Respuesta de login con formato inesperado."
                )

            access_token = str(
                data.get("accessToken")
                or ""
            ).strip()

            refresh_token = str(
                data.get("refreshToken")
                or ""
            ).strip()

            try:
                expires_in = int(
                    data.get(
                        "expiresIn",
                        3600,
                    )
                )
            except Exception:
                expires_in = 3600

            if not access_token:
                raise EcommerceERPError(
                    "Azure no entregó accessToken."
                )

            _ACCESS_TOKEN = access_token
            _REFRESH_TOKEN = refresh_token

            _ACCESS_TOKEN_EXPIRES_AT = (
                time.time()
                + max(
                    expires_in,
                    60,
                )
            )

            return _ACCESS_TOKEN

    except HTTPError as exc:

        if exc.code in (
            400,
            401,
            403,
        ):

            raise EcommerceERPError(
                "Login ERP rechazado. "
                "Verifica email y contraseña."
            ) from exc

        raise EcommerceERPError(
            f"Error HTTP {exc.code} durante el login."
        ) from exc

    except URLError as exc:

        raise EcommerceERPError(
            "No fue posible conectar con el servicio de login."
        ) from exc


def _get_token(
    force_login: bool = False,
) -> str:

    if has_login_credentials():

        with _AUTH_LOCK:

            if (
                not force_login
                and _cached_token_is_valid()
            ):
                return _ACCESS_TOKEN

            return _login()

    return _get_manual_token()


def invalidate_access_token() -> None:

    global _ACCESS_TOKEN
    global _ACCESS_TOKEN_EXPIRES_AT
    global _REFRESH_TOKEN

    with _AUTH_LOCK:

        _ACCESS_TOKEN = ""
        _ACCESS_TOKEN_EXPIRES_AT = 0.0
        _REFRESH_TOKEN = ""


def get_auth_status() -> dict:

    mode = "none"

    if has_login_credentials():
        mode = "automatic_login"

    elif has_manual_token():
        mode = "manual_bearer"

    return {
        "configured": has_token(),
        "mode": mode,
        "email_configured": bool(
            _get_email()
        ),
        "password_configured": bool(
            _get_password()
        ),
        "manual_token_configured": (
            has_manual_token()
        ),
        "cached_token_valid": (
            _cached_token_is_valid()
        ),
    }


# ============================================================
# HTTP
# ============================================================

def _build_url(
    endpoint: str,
) -> str:

    endpoint = str(
        endpoint or ""
    ).strip().lstrip("/")

    return f"{BASE_URL}/{endpoint}"


def _build_headers() -> dict[str, str]:

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": "Maritex-Inventory-Control/1.0",
    }

    token = _get_token()

    if token:
        headers[
            "Authorization"
        ] = f"Bearer {token}"

    return headers


def _request(
    method: str,
    url: str,
    timeout: int = DEFAULT_TIMEOUT,
    _retry_auth: bool = True,
) -> APIResult:

    try:
        headers = _build_headers()

    except EcommerceERPError as exc:

        return APIResult(
            ok=False,
            status_code=None,
            data=None,
            message=str(exc),
            url=url,
        )

    request = Request(
        url,
        method=method.upper(),
        headers=headers,
    )

    try:

        with urlopen(
            request,
            timeout=timeout,
        ) as response:

            data = _decode_response(
                response.read()
            )

            message = "OK"

            if (
                isinstance(data, str)
                and data
            ):
                message = data

            return APIResult(
                ok=(
                    200
                    <= response.status
                    < 300
                ),
                status_code=response.status,
                data=data,
                message=message,
                url=url,
            )

    except HTTPError as exc:

        if (
            exc.code == 401
            and _retry_auth
            and has_login_credentials()
        ):

            try:

                invalidate_access_token()

                _get_token(
                    force_login=True
                )

            except Exception as auth_exc:

                return APIResult(
                    ok=False,
                    status_code=401,
                    data=None,
                    message=(
                        "La sesión ERP expiró "
                        "y no fue posible renovarla: "
                        f"{auth_exc}"
                    ),
                    url=url,
                )

            return _request(
                method=method,
                url=url,
                timeout=timeout,
                _retry_auth=False,
            )

        try:
            detail = _decode_response(
                exc.read()
            )

        except Exception:
            detail = None

        if exc.code == 401:
            message = "HTTP 401: No autorizado."

        elif exc.code == 403:
            message = (
                "HTTP 403: Sin permisos para esta operación."
            )

        else:
            message = (
                str(detail)
                if detail
                else (
                    f"HTTP {exc.code}: "
                    f"{exc.reason}"
                )
            )

        return APIResult(
            ok=False,
            status_code=exc.code,
            data=detail,
            message=message,
            url=url,
        )

    except URLError as exc:

        return APIResult(
            ok=False,
            status_code=None,
            data=None,
            message=(
                "No fue posible conectar "
                f"con Azure: {exc.reason}"
            ),
            url=url,
        )

    except TimeoutError:

        return APIResult(
            ok=False,
            status_code=None,
            data=None,
            message=(
                "La conexión con Azure "
                "superó el tiempo de espera."
            ),
            url=url,
        )

    except Exception as exc:

        return APIResult(
            ok=False,
            status_code=None,
            data=None,
            message=f"Error inesperado: {exc}",
            url=url,
        )


# ============================================================
# CANALES
# ============================================================

def normalize_channel(
    channel: str,
) -> str:

    value = str(
        channel or ""
    ).strip().upper()

    if value not in CHANNEL_ENDPOINTS:

        raise EcommerceERPError(
            f"Canal inválido: {channel}"
        )

    return value


def endpoint_for_channel(
    channel: str,
) -> str:

    return CHANNEL_ENDPOINTS[
        normalize_channel(channel)
    ]


# ============================================================
# PENDIENTES
# ============================================================

def get_pending_orders(
    channel: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> APIResult:

    channel = normalize_channel(
        channel
    )

    endpoint = (
        CHANNEL_ENDPOINTS[
            channel
        ]
    )

    url = _build_url(
        endpoint
    )

    # Evitar respuestas cacheadas en proxy/browser
    url = (
        f"{url}?t={int(time.time())}"
    )

    return _request(
        method="GET",
        url=url,
        timeout=timeout,
    )


def get_pending_b2b(
    timeout: int = DEFAULT_TIMEOUT,
) -> APIResult:

    return get_pending_orders(
        "B2B",
        timeout,
    )


def get_pending_b2c(
    timeout: int = DEFAULT_TIMEOUT,
) -> APIResult:

    return get_pending_orders(
        "B2C",
        timeout,
    )


def get_pending_nolk(
    timeout: int = DEFAULT_TIMEOUT,
) -> APIResult:

    return get_pending_orders(
        "NOLK",
        timeout,
    )


# ============================================================
# REINYECCIÓN
# ============================================================

def reinject_order(
    channel: str,
    order_id: str,
    timeout: int = 30,
) -> APIResult:

    channel = normalize_channel(
        channel
    )

    clean_order_id = str(
        order_id or ""
    ).strip()

    if not clean_order_id:

        return APIResult(
            ok=False,
            status_code=None,
            message="Debe indicar un orderId VTEX.",
        )

    safe_order_id = quote(
        clean_order_id,
        safe="-",
    )

    endpoint = CHANNEL_ENDPOINTS[
        channel
    ]

    url = _build_url(
        (
            f"{endpoint}/"
            f"{safe_order_id}"
        )
    )

    return _request(
        method="POST",
        url=url,
        timeout=timeout,
    )


def reinject_b2c_order(
    order_id: str,
    timeout: int = 30,
) -> APIResult:

    return reinject_order(
        "B2C",
        order_id,
        timeout,
    )


def reinject_b2b_order(
    order_id: str,
    timeout: int = 30,
) -> APIResult:

    return reinject_order(
        "B2B",
        order_id,
        timeout,
    )


def reinject_nolk_order(
    order_id: str,
    timeout: int = 30,
) -> APIResult:

    return reinject_order(
        "NOLK",
        order_id,
        timeout,
    )


# ============================================================
# EXTRAER PEDIDOS
# ============================================================

def extract_orders(
    payload: Any,
) -> list[dict]:

    if payload is None:
        return []

    if isinstance(
        payload,
        list,
    ):

        return [
            item
            for item in payload
            if isinstance(item, dict)
        ]

    if not isinstance(
        payload,
        dict,
    ):
        return []

    for key in (
        "items",
        "data",
        "orders",
        "pendingOrders",
        "PendingOrders",
        "result",
        "results",
        "value",
    ):

        value = payload.get(
            key
        )

        if isinstance(
            value,
            list,
        ):

            return [
                item
                for item in value
                if isinstance(item, dict)
            ]

    lower_keys = {
        str(key).lower()
        for key in payload
    }

    markers = {
        "id",
        "idorden",
        "orderid",
        "vtexorder",
        "pedido",
    }

    if lower_keys & markers:
        return [payload]

    return []


# ============================================================
# JSON / VTEX
# ============================================================

def _try_json_loads(
    value: Any,
) -> Any:

    if not isinstance(
        value,
        str,
    ):
        return value

    try:
        return json.loads(
            value.strip()
        )

    except Exception:
        return value


def extract_vtex_order_id(
    value: Any,
) -> str:

    if value is None:
        return ""

    if isinstance(
        value,
        dict,
    ):

        for key in (
            "orderId",
            "orderID",
            "OrderId",
            "OrderID",
            "order_id",
            "id",
        ):

            result = value.get(
                key
            )

            if result:
                return str(
                    result
                ).strip()

        return ""

    text = str(
        value
    ).strip()

    if not text:
        return ""

    parsed = _try_json_loads(
        text
    )

    if isinstance(
        parsed,
        dict,
    ):

        found = extract_vtex_order_id(
            parsed
        )

        if found:
            return found

    patterns = (
        r'"orderId"\s*:\s*"([^"]+)"',
        r"'orderId'\s*:\s*'([^']+)'",
        r'orderId\s*[:=]\s*["\']?([A-Za-z0-9\-]+)',
    )

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(
                1
            ).strip()

    return ""


# ============================================================
# TEXTO
# ============================================================

def normalize_erp_text(
    value: Any,
) -> str:

    if value is None:
        return ""

    if isinstance(
        value,
        str,
    ):
        return value.strip()

    if isinstance(
        value,
        dict,
    ):

        return " ".join(
            normalize_erp_text(v)
            for v in value.values()
        ).strip()

    if isinstance(
        value,
        (list, tuple),
    ):

        return " ".join(
            normalize_erp_text(v)
            for v in value
        ).strip()

    return str(
        value
    ).strip()


def _clean_spaces(
    value: Any,
) -> str:

    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def _search_first(
    text: str,
    patterns: tuple[str, ...],
) -> str | None:

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return _clean_spaces(
                match.group(1)
            )

    return None


# ============================================================
# XML
# ============================================================

def _parse_xml(
    value: Any,
) -> ET.Element | None:

    if not isinstance(
        value,
        str,
    ):
        return None

    text = value.strip()

    if not text.startswith("<"):
        return None

    try:
        return ET.fromstring(
            text
        )

    except ET.ParseError:

        try:
            return ET.fromstring(
                f"<ROOT>{text}</ROOT>"
            )

        except ET.ParseError:
            return None


def _xml_text(
    element: ET.Element | None,
) -> str:

    if element is None:
        return ""

    return _clean_spaces(
        " ".join(
            element.itertext()
        )
    )


def _find_xml_text(
    element: ET.Element,
    tag: str,
) -> str | None:

    found = element.find(
        f".//{tag}"
    )

    if found is None:
        return None

    text = _xml_text(
        found
    )

    return text or None


# ============================================================
# PARSER DE CRÉDITO
# ============================================================

def _extract_credit_amount(
    text: str,
) -> str | None:

    value = _search_first(
        text,
        (
            (
                r"l[ií]mite\s+de\s+cr[eé]dito"
                r"\s+excedido\s+en\s+\$?\s*([\d\.,]+)"
            ),
            (
                r"cr[eé]dito\s+excedido"
                r"\s+en\s+\$?\s*([\d\.,]+)"
            ),
        ),
    )

    return value


# ============================================================
# PARSER DE STOCK
# ============================================================

def _extract_missing_stock(
    text: str,
) -> str | None:

    text = _clean_spaces(
        text
    )

    patterns = (
        # Faltan 78 UN Stock Real...
        r"faltan\s+([\d\.,]+\s*(?:un|unidad(?:es)?)?)",

        # faltante: 12
        r"faltante\s*[:=]?\s*([\d\.,]+\s*(?:un|unidad(?:es)?)?)",

        # faltan 5 unidades
        r"faltan\s+([\d\.,]+\s+unidades?)",

        # stock insuficiente: 10
        r"stock\s+insuficiente[^\d]*([\d\.,]+)",
    )

    return _search_first(
        text,
        patterns,
    )


def _extract_product(
    text: str,
) -> str | None:

    text = _clean_spaces(
        text
    )

    return _search_first(
        text,
        (
            (
                r"(?:producto|sku)"
                r"\s*[:=]?\s*"
                r"([A-Za-z0-9._\-]+)"
            ),
        ),
    )


def _extract_line(
    text: str,
) -> str | None:

    return _search_first(
        text,
        (
            r"l[ií]nea\s*[:=]?\s*([A-Za-z0-9._\- ]+)",
        ),
    )


def _extract_warehouse(
    text: str,
) -> str | None:

    text = _clean_spaces(
        text
    )

    patterns = (
        (
            r"(Bodega\s+"
            r"[0-9A-Za-zÁÉÍÓÚáéíóúÑñ._\- ]+"
            r"(?:,\s*Ubicaci[oó]n\s*=\s*"
            r"[A-Za-zÁÉÍÓÚáéíóúÑñ0-9._\- ]+)?)"
        ),
        (
            r"Bodega\s*[:=]\s*"
            r"([^()]+)"
        ),
    )

    result = _search_first(
        text,
        patterns,
    )

    if result:
        return result.strip(
            " ,.-"
        )[:200]

    return None


# ============================================================
# NORMALIZAR UN STOCK
# ============================================================

def _normalize_stock_record(
    line: Any = None,
    product: Any = None,
    description: Any = None,
    warehouse: Any = None,
    validation: Any = None,
) -> dict:

    line_text = _clean_spaces(
        line
    ) or None

    product_text = _clean_spaces(
        product
    ) or None

    description_text = _clean_spaces(
        description
    ) or None

    warehouse_text = _clean_spaces(
        warehouse
    ) or None

    validation_text = _clean_spaces(
        validation
    ) or None

    combined = _clean_spaces(
        " ".join(
            [
                str(line or ""),
                str(product or ""),
                str(description or ""),
                str(warehouse or ""),
                str(validation or ""),
            ]
        )
    )

    if not product_text:
        product_text = _extract_product(
            combined
        )

    if not warehouse_text:
        warehouse_text = _extract_warehouse(
            combined
        )

    if not line_text:
        line_text = _extract_line(
            combined
        )

    missing_stock = _extract_missing_stock(
        validation_text
        or combined
    )

    return {
        "line": line_text,
        "product": product_text,
        "description": description_text,
        "warehouse": warehouse_text,
        "validation": validation_text,
        "missing_stock": missing_stock,
    }


# ============================================================
# STOCK DESDE XML
# ============================================================

def _extract_xml_stocks(
    root: ET.Element,
) -> list[dict]:

    stocks: list[dict] = []

    stock_elements = root.findall(
        ".//STOCK"
    )

    for stock_element in stock_elements:

        stock = _normalize_stock_record(
            line=_find_xml_text(
                stock_element,
                "LINEA",
            ),
            product=_find_xml_text(
                stock_element,
                "PRODUCTO",
            ),
            description=_find_xml_text(
                stock_element,
                "GLOSA",
            ),
            warehouse=_find_xml_text(
                stock_element,
                "BODEGA",
            ),
            validation=_find_xml_text(
                stock_element,
                "VALIDACION",
            ),
        )

        if any(
            stock.get(key)
            for key in (
                "line",
                "product",
                "description",
                "warehouse",
                "validation",
                "missing_stock",
            )
        ):
            stocks.append(
                stock
            )

    return stocks


# ============================================================
# STOCK DESDE JSON
# ============================================================

def _find_document_dict(
    payload: Any,
) -> dict:

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    root = payload.get(
        "root",
        payload,
    )

    if not isinstance(
        root,
        dict,
    ):
        return {}

    document_list = root.get(
        "DOCUMENTOLIST",
        root,
    )

    if not isinstance(
        document_list,
        dict,
    ):
        return {}

    document = document_list.get(
        "DOCUMENTO",
        document_list,
    )

    if isinstance(
        document,
        list,
    ):

        if document and isinstance(
            document[0],
            dict,
        ):
            return document[0]

        return {}

    if isinstance(
        document,
        dict,
    ):
        return document

    return {}


def _extract_json_message(
    document: dict,
) -> str | None:

    message = document.get(
        "MENSAJE"
    )

    if isinstance(
        message,
        str,
    ):
        return _clean_spaces(
            message
        ) or None

    if isinstance(
        message,
        dict,
    ):

        for key in (
            "_",
            "value",
            "#text",
            "text",
        ):

            if message.get(
                key
            ):

                return _clean_spaces(
                    message.get(key)
                )

        text = normalize_erp_text(
            message
        )

        return text or None

    return None


def _extract_json_stocks(
    document: dict,
) -> list[dict]:

    stocks: list[dict] = []

    stocks_container = document.get(
        "STOCKS"
    )

    if not stocks_container:
        return stocks

    raw_stock = None

    if isinstance(
        stocks_container,
        dict,
    ):
        raw_stock = stocks_container.get(
            "STOCK",
            stocks_container,
        )

    elif isinstance(
        stocks_container,
        list,
    ):
        raw_stock = stocks_container

    if raw_stock is None:
        return stocks

    if isinstance(
        raw_stock,
        dict,
    ):
        raw_stock = [
            raw_stock
        ]

    if not isinstance(
        raw_stock,
        list,
    ):
        return stocks

    for item in raw_stock:

        if not isinstance(
            item,
            dict,
        ):
            continue

        stock = _normalize_stock_record(
            line=(
                item.get("LINEA")
                or item.get("linea")
                or item.get("line")
            ),
            product=(
                item.get("PRODUCTO")
                or item.get("producto")
                or item.get("SKU")
                or item.get("sku")
            ),
            description=(
                item.get("GLOSA")
                or item.get("glosa")
                or item.get("DESCRIPCION")
                or item.get("descripcion")
                or item.get("description")
            ),
            warehouse=(
                item.get("BODEGA")
                or item.get("bodega")
                or item.get("warehouse")
            ),
            validation=(
                item.get("VALIDACION")
                or item.get("validacion")
                or item.get("validation")
            ),
        )

        stocks.append(
            stock
        )

    return stocks


# ============================================================
# STOCK DESDE TEXTO LIBRE
# ============================================================

def _extract_text_stock(
    text: str,
) -> list[dict]:

    text = _clean_spaces(
        text
    )

    if not text:
        return []

    missing_stock = _extract_missing_stock(
        text
    )

    product = _extract_product(
        text
    )

    warehouse = _extract_warehouse(
        text
    )

    line = _extract_line(
        text
    )

    if not any(
        (
            missing_stock,
            product,
            warehouse,
            line,
        )
    ):
        return []

    return [
        {
            "line": line,
            "product": product,
            "description": None,
            "warehouse": warehouse,
            "validation": text,
            "missing_stock": missing_stock,
        }
    ]


# ============================================================
# DETALLE ERP
# ============================================================

def extract_erp_details(
    response: Any,
) -> dict:

    details = {
        "document_type": None,
        "correlative": None,
        "document_number": None,
        "erp_status": None,
        "message": None,
        "credit_exceeded": None,
        "stocks": [],
        "format": "text",
    }

    if response is None:
        return details

    # ========================================================
    # XML
    # ========================================================

    xml_root = _parse_xml(
        response
    )

    if xml_root is not None:

        details["format"] = "xml"

        details[
            "document_type"
        ] = _find_xml_text(
            xml_root,
            "TIPODOCTO",
        )

        details[
            "correlative"
        ] = _find_xml_text(
            xml_root,
            "CORRELATIVO",
        )

        details[
            "document_number"
        ] = _find_xml_text(
            xml_root,
            "NUMERO",
        )

        details[
            "erp_status"
        ] = _find_xml_text(
            xml_root,
            "ESTADO",
        )

        message_element = xml_root.find(
            ".//MENSAJE"
        )

        if message_element is not None:

            message = _xml_text(
                message_element
            )

            details[
                "message"
            ] = message or None

        details[
            "stocks"
        ] = _extract_xml_stocks(
            xml_root
        )

        diagnostic_text = _clean_spaces(
            details.get(
                "message"
            )
            or normalize_erp_text(
                response
            )
        )

        details[
            "credit_exceeded"
        ] = _extract_credit_amount(
            diagnostic_text
        )

        # Si STOCKS viene vacío pero el mensaje contiene
        # información de stock, intentamos recuperarla.
        if not details[
            "stocks"
        ]:

            details[
                "stocks"
            ] = _extract_text_stock(
                diagnostic_text
            )

        return details

    # ========================================================
    # JSON
    # ========================================================

    parsed = _try_json_loads(
        response
    )

    if isinstance(
        parsed,
        dict,
    ):

        details["format"] = "json"

        document = _find_document_dict(
            parsed
        )

        if document:

            details[
                "document_type"
            ] = (
                document.get("TIPODOCTO")
                or document.get("tipoDocto")
            )

            details[
                "correlative"
            ] = (
                document.get("CORRELATIVO")
                or document.get("correlativo")
            )

            details[
                "document_number"
            ] = (
                document.get("NUMERO")
                or document.get("numero")
            )

            details[
                "erp_status"
            ] = (
                document.get("ESTADO")
                or document.get("estado")
            )

            details[
                "message"
            ] = _extract_json_message(
                document
            )

            details[
                "stocks"
            ] = _extract_json_stocks(
                document
            )

        diagnostic_text = _clean_spaces(
            details.get(
                "message"
            )
            or normalize_erp_text(
                parsed
            )
        )

        details[
            "credit_exceeded"
        ] = _extract_credit_amount(
            diagnostic_text
        )

        if not details[
            "stocks"
        ]:

            details[
                "stocks"
            ] = _extract_text_stock(
                diagnostic_text
            )

        return details

    # ========================================================
    # TEXTO
    # ========================================================

    text = normalize_erp_text(
        response
    )

    details[
        "message"
    ] = text or None

    details[
        "credit_exceeded"
    ] = _extract_credit_amount(
        text
    )

    details[
        "stocks"
    ] = _extract_text_stock(
        text
    )

    return details


# ============================================================
# CLASIFICACIÓN
# ============================================================

def classify_erp_response(
    response: Any,
) -> dict:

    details = extract_erp_details(
        response
    )

    text = _clean_spaces(
        details.get("message")
        or normalize_erp_text(
            response
        )
    )

    normalized = text.lower()

    categories: list[str] = []

    # --------------------------------------------------------
    # INTEGRADO
    # --------------------------------------------------------

    if any(
        item in normalized
        for item in (
            "documento integrado exitosamente",
            "inyeccion correcta",
            "inyección correcta",
            "integrado exitosamente",
        )
    ):

        categories.append(
            "Integrado"
        )

    # --------------------------------------------------------
    # CRÉDITO
    # --------------------------------------------------------

    if any(
        item in normalized
        for item in (
            "límite de crédito",
            "limite de credito",
            "crédito excedido",
            "credito excedido",
            "crédito no vigente",
            "credito no vigente",
            "sin crédito asignado",
            "sin credito asignado",
            "crédito vencido",
            "credito vencido",
            "crédito bloqueado",
            "credito bloqueado",
        )
    ):

        categories.append(
            "Crédito"
        )

    # --------------------------------------------------------
    # STOCK
    # --------------------------------------------------------

    has_structured_stock = bool(
        details.get(
            "stocks"
        )
    )

    if (
        has_structured_stock
        or (
            "faltan"
            in normalized
            and "stock"
            in normalized
        )
        or "stock insuficiente" in normalized
        or "sin stock" in normalized
    ):

        categories.append(
            "Stock"
        )

    # --------------------------------------------------------
    # PAGO
    # --------------------------------------------------------

    if any(
        item in normalized
        for item in (
            "condiciones de pago no cuadran",
            "condicion de pago no cuadra",
            "condición de pago no cuadra",
            "forma de pago",
        )
    ):

        categories.append(
            "Pago"
        )

    # --------------------------------------------------------
    # CLIENTE
    # --------------------------------------------------------

    if any(
        item in normalized
        for item in (
            "cliente no existe",
            "cliente inexistente",
            "rut no existe",
            "rut inválido",
            "rut invalido",
            "cliente bloqueado",
        )
    ):

        categories.append(
            "Cliente"
        )

    # --------------------------------------------------------
    # PRODUCTO
    # --------------------------------------------------------

    if any(
        item in normalized
        for item in (
            "producto no existe",
            "sku no existe",
            "sku inválido",
            "sku invalido",
        )
    ):

        categories.append(
            "Producto / SKU"
        )

    # --------------------------------------------------------
    # PRECIO
    # --------------------------------------------------------

    if any(
        item in normalized
        for item in (
            "precio inválido",
            "precio invalido",
            "precio incorrecto",
        )
    ):

        categories.append(
            "Precio"
        )

    if not categories:
        categories.append(
            "Sin clasificar"
        )

    return {
        "categories": list(
            dict.fromkeys(
                categories
            )
        ),
        "summary": text,
        "raw": response,
    }


# ============================================================
# ESTADO ERP LEGIBLE
# ============================================================

def get_erp_status_label(
    status: Any,
) -> str:

    value = _safe_status_value(
        status
    )

    if value == "":
        return "No informado"

    # Por ahora evitamos afirmar una semántica
    # no confirmada por la API.
    if value == "0":
        return "0"

    return value


def _safe_status_value(
    value: Any,
) -> str:

    if value is None:
        return ""

    return str(
        value
    ).strip()


# ============================================================
# DIAGNÓSTICO
# ============================================================

def diagnose_erp_response(
    response: Any,
) -> dict:

    details = extract_erp_details(
        response
    )

    classification = classify_erp_response(
        response
    )

    categories = classification.get(
        "categories",
        [],
    )

    message = _clean_spaces(
        details.get("message")
        or ""
    )

    lower_message = message.lower()

    # ========================================================
    # CATEGORÍA PRINCIPAL
    # ========================================================

    if "Integrado" in categories:

        category = "Integrado"
        reason = (
            "Documento integrado exitosamente"
        )

    elif (
        "Crédito" in categories
        and "Stock" in categories
    ):

        category = "Crédito + Stock"
        reason = (
            "Problema de crédito y stock insuficiente"
        )

    elif "Crédito" in categories:

        category = "Crédito"

        if (
            "sin crédito asignado"
            in lower_message
            or "sin credito asignado"
            in lower_message
        ):

            reason = (
                "Cliente sin crédito asignado"
            )

        elif (
            "crédito no vigente"
            in lower_message
            or "credito no vigente"
            in lower_message
        ):

            reason = (
                "Crédito no vigente"
            )

        elif (
            "crédito vencido"
            in lower_message
            or "credito vencido"
            in lower_message
        ):

            reason = (
                "Crédito vencido"
            )

        elif (
            "crédito bloqueado"
            in lower_message
            or "credito bloqueado"
            in lower_message
        ):

            reason = (
                "Crédito bloqueado"
            )

        elif details.get(
            "credit_exceeded"
        ):

            reason = (
                "Límite de crédito excedido"
            )

        else:

            reason = (
                "Problema de crédito"
            )

    elif "Stock" in categories:

        category = "Stock"
        reason = "Stock insuficiente"

    elif "Pago" in categories:

        category = "Pago"
        reason = (
            "Condiciones de pago no cuadran con el total"
        )

    elif "Cliente" in categories:

        category = "Cliente"
        reason = (
            "Problema con datos del cliente"
        )

    elif "Producto / SKU" in categories:

        category = "Producto"
        reason = (
            "Producto o SKU no reconocido"
        )

    elif "Precio" in categories:

        category = "Precio"
        reason = "Problema de precio"

    else:

        category = "Sin clasificar"

        reason = (
            message[-180:]
            if message
            else (
                "ERP no entregó mensaje de diagnóstico"
            )
        )

    # ========================================================
    # STOCK PRINCIPAL
    # ========================================================

    stocks = (
        details.get("stocks")
        or []
    )

    stock_info = (
        stocks[0]
        if stocks
        else {}
    )

    return {
        "category": category,
        "reason": reason,
        "categories": categories,

        # Crédito
        "credit_exceeded": (
            details.get(
                "credit_exceeded"
            )
        ),

        # Stock principal
        "missing_stock": (
            stock_info.get(
                "missing_stock"
            )
        ),
        "product": (
            stock_info.get(
                "product"
            )
        ),
        "description": (
            stock_info.get(
                "description"
            )
        ),
        "warehouse": (
            stock_info.get(
                "warehouse"
            )
        ),
        "line": (
            stock_info.get(
                "line"
            )
        ),

        # Documento
        "document_type": (
            details.get(
                "document_type"
            )
        ),
        "document_number": (
            details.get(
                "document_number"
            )
        ),
        "correlative": (
            details.get(
                "correlative"
            )
        ),

        # Estado
        "erp_status": (
            details.get(
                "erp_status"
            )
        ),
        "erp_status_label": (
            get_erp_status_label(
                details.get(
                    "erp_status"
                )
            )
        ),

        # Mensaje
        "message": (
            details.get(
                "message"
            )
        ),
        "response_format": (
            details.get(
                "format"
            )
        ),

        # Todos los stocks
        "stocks": stocks,

        "raw": response,
    }


# ============================================================
# NORMALIZACIÓN DE PEDIDOS
# ============================================================

def normalize_order(
    order: dict[str, Any],
) -> dict[str, Any]:

    if not isinstance(
        order,
        dict,
    ):
        return {}

    result = dict(
        order
    )

    result[
        "vtexOrderId"
    ] = extract_vtex_order_id(
        order.get(
            "vtexOrder"
        )
    )

    result[
        "erpDiagnosis"
    ] = diagnose_erp_response(
        order.get(
            "response"
        )
    )

    return result


def normalize_orders(
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    return [
        normalize_order(
            order
        )
        for order in orders
        if isinstance(
            order,
            dict,
        )
    ]


# ============================================================
# TEST DE CONEXIÓN
# ============================================================

def check_api_connection(
    channel: str = "B2C",
    timeout: int = 10,
) -> dict:

    result = get_pending_orders(
        channel,
        timeout,
    )

    return {
        "ok": result.ok,
        "status_code": (
            result.status_code
        ),
        "message": (
            result.message
        ),
        "url": (
            result.url
        ),
        "authenticated": (
            result.status_code
            != 401
        ),
    }