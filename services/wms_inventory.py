

import html as html_lib
import os
import re
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable

import requests


DEFAULT_WMS_BASE_URL = os.getenv(
    "WMS_BASE_URL",
    "http://104.45.239.215/wms",
).rstrip("/")

INVENTORY_PATH = "/ReporteInventario2020.aspx"

LOGIN_FORM_PATH = "/form_login.aspx"
LOGIN_POST_PATH = "/web_login.aspx"
LOGIN_USER_FIELD = "ctl00$contentLogin$txtUserName"
LOGIN_PASSWORD_FIELD = "ctl00$contentLogin$txtUserPass"
LOGIN_BUTTON_FIELD = "ctl00$contentLogin$valida"

GRID_ID = "ctl00_placeHolderContent_gv_principal"
GRID_EVENT_TARGET = "ctl00$placeHolderContent$gv_principal"

FIELD_DATE = "ctl00$placeHolderContent$cdFecha$dropdown_control"
FIELD_SITE = "ctl00$placeHolderContent$cdSitio$dropdown_control"
FIELD_PRODUCT = "ctl00$placeHolderContent$ctProducto$textbox_control"
FIELD_WAREHOUSE = "ctl00$placeHolderContent$ctBodega$textbox_control"
FIELD_LOCATION = "ctl00$placeHolderContent$ctUbicacion$textbox_control"
FIELD_ZONE = "ctl00$placeHolderContent$ctZona$textbox_control"
FIELD_TREATMENT = "ctl00$placeHolderContent$ctTipoTratamiento$textbox_control"
FIELD_CONTAINER = "ctl00$placeHolderContent$ctContenedor$textbox_control"
FIELD_ORDER = "ctl00$placeHolderContent$ctPedido$textbox_control"

FIELD_AVAILABLE_FOR_SALE = "ctl00$placeHolderContent$chDispVenta"
FIELD_NO_TREATMENT = "ctl00$placeHolderContent$chSinTrata"
FIELD_AVAILABLE = "ctl00$placeHolderContent$chDisponible"
FIELD_GROUPED = "ctl00$placeHolderContent$chGroupBy"
FIELD_FULL_INVENTORY = "ctl00$placeHolderContent$chTodoInv"
FIELD_OUTPUT_LOCATION = "ctl00$placeHolderContent$chUbicacionSalida"

SEARCH_BUTTON = "ctl00$placeHolderContent$ControlCRUD$bBuscar$button"


COLUMN_MAP = {
    "Cod. Producto": "sku",
    "Descripción": "descripcion",
    "Ubicación": "ubicacion",
    "Contenedor": "contenedor",
    "Cantidad": "cantidad",
    "Cant. Reservada": "cantidad_reservada",
    "Bodega": "bodega",
    "Etiqueta": "etiqueta",
    "Cant. X caja": "cantidad_x_caja",
    "N° Cajas": "numero_cajas",
    "Saldo": "saldo",
    "Pedido": "pedido",
    "Tipo Tratam.": "tipo_tratamiento",
    "Sitio": "sitio",
    "Cliente": "cliente",
    "Estado 2": "estado_2",
    "Estado 3": "estado_3",
    "F. Expiración": "fecha_expiracion",
    "F. Fabricación": "fecha_fabricacion",
    "ID": "id",
    "Lote": "lote",
    "Cod. Usuario N°1": "cod_usuario_1",
    "EAN": "ean",
    "Cod. Usuario N°3": "cod_usuario_3",
    "Cod. Usuario N°4": "cod_usuario_4",
    "UDM": "udm",
    "Zona": "zona",
    "Orden de Compra": "orden_compra",
    "OC": "oc",
    "Desc. Componente": "desc_componente",
    "Prod. Componente": "prod_componente",
    "División": "division",
    "ETIQUETADO": "etiquetado",
}

NUMERIC_FIELDS = {
    "cantidad",
    "cantidad_reservada",
    "cantidad_x_caja",
    "numero_cajas",
    "saldo",
}


@dataclass
class WMSInventoryResult:
    ok: bool
    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    pages_loaded: int
    source: str
    quantity_mode: str
    error: str | None = None
    status_code: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "rows": self.rows,
            "summary": self.summary,
            "pages_loaded": self.pages_loaded,
            "source": self.source,
            "quantity_mode": self.quantity_mode,
            "error": self.error,
            "status_code": self.status_code,
        }


def _clean(value: Any) -> str:
    if value is None:
        return ""
    value = html_lib.unescape(str(value))
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def _attrs_dict(attrs: Iterable[tuple[str, str | None]]) -> dict[str, str]:
    return {_clean(k).lower(): _clean(v) for k, v in attrs}


class _FormStateParser(HTMLParser):
    """Extrae el estado POST de aspnetForm sin dependencias externas."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_form = False
        self.fields: dict[str, str] = {}
        self._select_name: str | None = None
        self._selected_value: str | None = None
        self._first_option_value: str | None = None
        self._textarea_name: str | None = None
        self._textarea_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        a = _attrs_dict(attrs)
        tag = tag.lower()

        if tag == "form":
            form_id = _clean(a.get("id"))
            form_name = _clean(a.get("name"))
            if form_id == "aspnetForm" or form_name == "aspnetForm":
                self.in_form = True
            return

        if not self.in_form:
            return

        if tag == "input":
            name = _clean(a.get("name"))
            if not name:
                return

            input_type = _clean(a.get("type")).lower() or "text"

            # Los submit no deben viajar salvo que explícitamente hagamos click.
            if input_type in {"submit", "button", "image", "reset", "file"}:
                return

            if input_type in {"checkbox", "radio"}:
                if "checked" not in a:
                    return
                self.fields[name] = _clean(a.get("value")) or "on"
                return

            self.fields[name] = _clean(a.get("value"))
            return

        if tag == "select":
            name = _clean(a.get("name"))
            if name:
                self._select_name = name
                self._selected_value = None
                self._first_option_value = None
            return

        if tag == "option" and self._select_name:
            value = _clean(a.get("value"))
            if self._first_option_value is None:
                self._first_option_value = value
            if "selected" in a:
                self._selected_value = value
            return

        if tag == "textarea":
            name = _clean(a.get("name"))
            if name:
                self._textarea_name = name
                self._textarea_parts = []

    def handle_data(self, data: str) -> None:
        if self.in_form and self._textarea_name:
            self._textarea_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag == "select" and self._select_name:
            self.fields[self._select_name] = (
                self._selected_value
                if self._selected_value is not None
                else (self._first_option_value or "")
            )
            self._select_name = None
            self._selected_value = None
            self._first_option_value = None
            return

        if tag == "textarea" and self._textarea_name:
            self.fields[self._textarea_name] = _clean(
                "".join(self._textarea_parts)
            )
            self._textarea_name = None
            self._textarea_parts = []
            return

        if tag == "form" and self.in_form:
            self.in_form = False


class _InventoryGridParser(HTMLParser):
    """Parsea solo gv_principal y detecta sus páginas ASP.NET."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_target = False
        self.table_level = 0

        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.page_numbers: set[int] = set()

        self._in_row = False
        self._current_row: list[str] = []
        self._current_row_class = ""
        self._cell_tag: str | None = None
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        a = _attrs_dict(attrs)
        tag = tag.lower()

        if tag == "table":
            table_id = _clean(a.get("id"))
            if not self.in_target and table_id == GRID_ID:
                self.in_target = True
                self.table_level = 1
                return
            if self.in_target:
                self.table_level += 1
            return

        if not self.in_target:
            return

        if tag == "a":
            href = _clean(a.get("href"))
            m = re.search(r"Page\$(\d+)", href, flags=re.I)
            if m:
                self.page_numbers.add(int(m.group(1)))

        if self.table_level != 1:
            return

        if tag == "tr":
            self._in_row = True
            self._current_row = []
            self._current_row_class = _clean(a.get("class"))
            return

        if self._in_row and tag in {"th", "td"}:
            self._cell_tag = tag
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if (
            self.in_target
            and self.table_level == 1
            and self._in_row
            and self._cell_tag
        ):
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if not self.in_target:
            return

        if self.table_level == 1 and self._in_row and tag in {"th", "td"}:
            if self._cell_tag == tag:
                value = _clean("".join(self._cell_parts))
                self._current_row.append(value)
                self._cell_tag = None
                self._cell_parts = []
            return

        if self.table_level == 1 and tag == "tr" and self._in_row:
            if "gv_pageNumber" not in self._current_row_class:
                if self._current_row:
                    if not self.headers:
                        # La primera fila válida con el mismo número de columnas
                        # será tomada como cabecera solo si venía de <th>.
                        # En la práctica gv_principal siempre trae cabecera <th>.
                        pass
                    self.rows.append(self._current_row)

            self._in_row = False
            self._current_row = []
            self._current_row_class = ""
            return

        if tag == "table":
            if self.table_level > 0:
                self.table_level -= 1
                if self.table_level == 0:
                    self.in_target = False


def _parse_grid(html: str) -> tuple[list[str], list[list[str]], set[int]]:
    """
    Parseo específico del GridView.

    Como el parser anterior no conserva directamente si la fila usó TH o TD,
    obtenemos headers con un segundo parser liviano y luego filtramos filas de
    datos por longitud.
    """

    class HeaderParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.in_target = False
            self.table_level = 0
            self.in_th = False
            self.parts: list[str] = []
            self.headers: list[str] = []

        def handle_starttag(self, tag, attrs):
            a = _attrs_dict(attrs)
            tag = tag.lower()
            if tag == "table":
                if not self.in_target and _clean(a.get("id")) == GRID_ID:
                    self.in_target = True
                    self.table_level = 1
                    return
                if self.in_target:
                    self.table_level += 1
                return

            if self.in_target and self.table_level == 1 and tag == "th":
                self.in_th = True
                self.parts = []

        def handle_data(self, data):
            if self.in_th:
                self.parts.append(data)

        def handle_endtag(self, tag):
            tag = tag.lower()
            if self.in_target and self.table_level == 1 and tag == "th" and self.in_th:
                self.headers.append(_clean("".join(self.parts)))
                self.in_th = False
                self.parts = []
                return

            if self.in_target and tag == "table":
                self.table_level -= 1
                if self.table_level == 0:
                    self.in_target = False

    hp = HeaderParser()
    hp.feed(html)

    gp = _InventoryGridParser()
    gp.feed(html)

    headers = hp.headers
    rows = gp.rows

    # El parser de filas también toma la fila de cabecera; la quitamos
    # comparándola con los headers normalizados.
    if headers and rows:
        first = [_clean(v) for v in rows[0]]
        if first == [_clean(v) for v in headers]:
            rows = rows[1:]

    if headers:
        rows = [r for r in rows if len(r) == len(headers)]

    return headers, rows, gp.page_numbers


def _parse_form_state(html: str) -> dict[str, str]:
    parser = _FormStateParser()
    parser.feed(html)
    return parser.fields


def _to_number(value: Any) -> int | float:
    text = _clean(value)
    if not text:
        return 0

    # WMS observado usa enteros. Igual soportamos decimal con coma/punto.
    normalized = text.replace(" ", "")
    if "," in normalized and "." not in normalized:
        normalized = normalized.replace(",", ".")
    try:
        number = float(normalized)
    except Exception:
        return 0

    return int(number) if number.is_integer() else number


def parse_inventory_html(
    html: str,
    *,
    available_for_sale: bool = False,
) -> dict[str, Any]:
    """
    Convierte la tabla gv_principal a registros normalizados.

    Cuando WMS tiene activo "Disponible", su propia pantalla indica que
    la columna Cantidad se muestra como:
        cantidad - cantidad_reservada

    Para evitar ambigüedad siempre exponemos:
      - cantidad_reportada_wms
      - cantidad_fisica
      - cantidad_reservada
      - cantidad_disponible
    """
    headers, raw_rows, page_numbers = _parse_grid(html)

    if not headers:
        return {
            "headers": [],
            "rows": [],
            "page_numbers": sorted(page_numbers),
        }

    normalized_headers = [COLUMN_MAP.get(h, h) for h in headers]
    rows: list[dict[str, Any]] = []

    for values in raw_rows:
        row = {
            normalized_headers[i]: _clean(values[i])
            for i in range(min(len(normalized_headers), len(values)))
        }

        for field in NUMERIC_FIELDS:
            if field in row:
                row[field] = _to_number(row.get(field))

        reported = _to_number(row.get("cantidad"))
        reserved = _to_number(row.get("cantidad_reservada"))

        if available_for_sale:
            available = max(reported, 0)
            physical = max(reported + reserved, 0)
        else:
            physical = max(reported, 0)
            available = max(physical - reserved, 0)

        row["cantidad_reportada_wms"] = reported
        row["cantidad_fisica"] = physical
        row["cantidad_disponible"] = available

        rows.append(row)

    return {
        "headers": headers,
        "rows": rows,
        "page_numbers": sorted(page_numbers),
    }


def summarize_inventory(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "registros": 0,
            "sku": 0,
            "cantidad_fisica": 0,
            "cantidad_reservada": 0,
            "cantidad_disponible": 0,
            "sitios": [],
            "bodegas": [],
        }

    def total(field: str) -> float:
        return float(sum(_to_number(r.get(field)) for r in rows))

    def unique(field: str) -> list[str]:
        return sorted(
            {
                _clean(r.get(field))
                for r in rows
                if _clean(r.get(field))
            }
        )

    return {
        "registros": len(rows),
        "sku": len(unique("sku")),
        "cantidad_fisica": total("cantidad_fisica"),
        "cantidad_reservada": total("cantidad_reservada"),
        "cantidad_disponible": total("cantidad_disponible"),
        "sitios": unique("sitio"),
        "bodegas": unique("bodega"),
    }


def inventory_by_sku(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Resumen por SKU + Sitio + Bodega.

    Útil para Stock General y para sugerencias de stock alternativo.
    """
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}

    for row in rows:
        key = (
            _clean(row.get("sku")),
            _clean(row.get("sitio")),
            _clean(row.get("bodega")),
        )

        if key not in grouped:
            grouped[key] = {
                "sku": key[0],
                "descripcion": _clean(row.get("descripcion")),
                "sitio": key[1],
                "bodega": key[2],
                "cantidad_fisica": 0,
                "cantidad_reservada": 0,
                "cantidad_disponible": 0,
                "ubicaciones": set(),
                "contenedores": set(),
                "registros_wms": 0,
            }

        item = grouped[key]
        item["cantidad_fisica"] += _to_number(row.get("cantidad_fisica"))
        item["cantidad_reservada"] += _to_number(row.get("cantidad_reservada"))
        item["cantidad_disponible"] += _to_number(row.get("cantidad_disponible"))
        item["registros_wms"] += 1

        ubicacion = _clean(row.get("ubicacion"))
        contenedor = _clean(row.get("contenedor"))

        if ubicacion:
            item["ubicaciones"].add(ubicacion)
        if contenedor:
            item["contenedores"].add(contenedor)

    result: list[dict[str, Any]] = []

    for item in grouped.values():
        item["ubicaciones"] = sorted(item["ubicaciones"])
        item["contenedores"] = sorted(item["contenedores"])
        result.append(item)

    return sorted(
        result,
        key=lambda x: (
            x.get("sku", ""),
            x.get("sitio", ""),
            x.get("bodega", ""),
        ),
    )



def login_wms(
    session: requests.Session,
    *,
    username: str | None = None,
    password: str | None = None,
    timeout: float = 20.0,
) -> tuple[bool, str | None]:
    """
    Autenticación automática del WMS mediante el formulario ASP.NET.

    Credenciales:
      WMS_USERNAME
      WMS_PASSWORD

    Flujo:
      GET  /form_login.aspx
      POST /web_login.aspx?ReturnUrl=/wms/ReporteInventario2020.aspx
      -> requests.Session conserva automáticamente las cookies.
      -> se valida la sesión abriendo ReporteInventario2020.aspx.

    No imprime ni persiste credenciales/cookies.
    """
    user = (
        username if username is not None else os.getenv("WMS_USERNAME", "")
    ).strip()
    pwd = password if password is not None else os.getenv("WMS_PASSWORD", "")

    if not user or not pwd:
        return False, "Faltan WMS_USERNAME y/o WMS_PASSWORD."

    base_url = DEFAULT_WMS_BASE_URL
    login_form_url = f"{base_url}{LOGIN_FORM_PATH}"
    login_post_url = f"{base_url}{LOGIN_POST_PATH}"

    try:
        # 1. Obtener estado ASP.NET fresco.
        form_response = session.get(
            login_form_url,
            timeout=timeout,
            allow_redirects=True,
        )
        form_response.raise_for_status()

        state = _parse_form_state(form_response.text)
        if "__VIEWSTATE" not in state:
            return False, "El formulario WMS no entregó __VIEWSTATE."

        # 2. Replicar el POST real del navegador.
        payload = dict(state)
        payload["__EVENTTARGET"] = ""
        payload["__EVENTARGUMENT"] = ""
        payload[LOGIN_USER_FIELD] = user
        payload[LOGIN_PASSWORD_FIELD] = pwd
        payload[LOGIN_BUTTON_FIELD] = "Ingresar"

        login_response = session.post(
            login_post_url,
            params={"ReturnUrl": "/wms/ReporteInventario2020.aspx"},
            data=payload,
            timeout=timeout,
            allow_redirects=False,
        )

        # El flujo observado usa 302; algunos deployments pueden responder 200.
        if login_response.status_code not in {200, 301, 302, 303, 307, 308}:
            return (
                False,
                f"Login WMS respondió HTTP {login_response.status_code}.",
            )

        # 3. El navegador observado confirma el login mediante cookies y
        # redirección. No hacemos GET a ReporteInventario2020.aspx aquí:
        # ese método no corresponde al flujo real del reporte y puede causar 500.
        if not session.cookies:
            return (
                False,
                "El login respondió, pero el WMS no entregó cookies de sesión.",
            )

        return True, None

    except requests.RequestException as exc:
        return False, f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def create_wms_session(
    *,
    cookie_header: str | None = None,
) -> requests.Session:
    """
    Crea una sesión HTTP para el WMS.

    No hay credenciales ni cookies hardcodeadas.
    WMS_COOKIE_HEADER queda disponible solo como respaldo manual.
    El flujo preferido es login_wms() usando WMS_USERNAME/WMS_PASSWORD.
    """
    session = requests.Session()
    origin = DEFAULT_WMS_BASE_URL.rsplit("/wms", 1)[0]
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "es-ES,es;q=0.9",
            "Origin": origin,
            "Referer": f"{DEFAULT_WMS_BASE_URL}{INVENTORY_PATH}",
        }
    )

    cookie = (
        cookie_header
        if cookie_header is not None
        else os.getenv("WMS_COOKIE_HEADER", "")
    ).strip()

    if cookie:
        session.headers["Cookie"] = cookie

    return session


def _looks_like_inventory_page(html: str) -> bool:
    return (
        "ReporteInventario2020.aspx" in html
        and "aspnetForm" in html
        and FIELD_SITE.replace("$", "_")[:20]  # harmless stable marker prefix
        in html
    )


def _looks_like_login_page(response: requests.Response) -> bool:
    url = str(response.url or "").lower()
    text = (response.text or "").lower()

    return (
        "login" in url
        or "iniciar sesión" in text
        or "iniciar sesion" in text
        or 'type="password"' in text
        or "type='password'" in text
    )


def _apply_search_filters(
    payload: dict[str, str],
    *,
    date: str | None,
    site: str | None,
    product: str | None,
    warehouse: str | None,
    location: str | None,
    zone: str | None,
    treatment: str | None,
    container: str | None,
    order: str | None,
    available_for_sale: bool,
    grouped: bool,
    full_inventory: bool,
    output_location: bool,
) -> dict[str, str]:
    payload = dict(payload)

    if date is not None:
        payload[FIELD_DATE] = _clean(date)
    if site is not None:
        payload[FIELD_SITE] = _clean(site)
    if product is not None:
        payload[FIELD_PRODUCT] = _clean(product)

    payload[FIELD_WAREHOUSE] = _clean(warehouse)
    payload[FIELD_LOCATION] = _clean(location)
    payload[FIELD_ZONE] = _clean(zone)
    payload[FIELD_TREATMENT] = _clean(treatment)
    payload[FIELD_CONTAINER] = _clean(container)
    payload[FIELD_ORDER] = _clean(order)

    checkbox_fields = {
        FIELD_AVAILABLE_FOR_SALE,
        FIELD_NO_TREATMENT,
        FIELD_AVAILABLE,
        FIELD_GROUPED,
        FIELD_FULL_INVENTORY,
        FIELD_OUTPUT_LOCATION,
    }
    for field in checkbox_fields:
        payload.pop(field, None)

    # La propia página WMS vincula "Disp. para Venta" con:
    #   Sin Tratam. + Disponible.
    if available_for_sale:
        payload[FIELD_AVAILABLE_FOR_SALE] = "on"
        payload[FIELD_NO_TREATMENT] = "on"
        payload[FIELD_AVAILABLE] = "on"

    if grouped:
        payload[FIELD_GROUPED] = "on"

    if full_inventory:
        payload[FIELD_FULL_INVENTORY] = "on"

    if output_location:
        payload[FIELD_OUTPUT_LOCATION] = "on"

    payload["__EVENTTARGET"] = ""
    payload["__EVENTARGUMENT"] = ""
    payload[SEARCH_BUTTON] = ""

    return payload


def _paging_payload(html: str, page_number: int) -> dict[str, str]:
    payload = _parse_form_state(html)

    # Un click de paginación es __doPostBack del GridView, no del botón Buscar.
    payload.pop(SEARCH_BUTTON, None)
    payload["__EVENTTARGET"] = GRID_EVENT_TARGET
    payload["__EVENTARGUMENT"] = f"Page${int(page_number)}"

    return payload


def get_inventory(
    *,
    product: str | None = None,
    site: str | None = "CASA_MATRIZ",
    date: str | None = None,
    warehouse: str | None = "",
    location: str | None = "",
    zone: str | None = "",
    treatment: str | None = "",
    container: str | None = "",
    order: str | None = "",
    available_for_sale: bool = True,
    grouped: bool = False,
    full_inventory: bool = False,
    output_location: bool = False,
    load_all_pages: bool = True,
    max_pages: int = 50,
    timeout: float = 20.0,
    session: requests.Session | None = None,
    cookie_header: str | None = None,
    username: str | None = None,
    password: str | None = None,
    auto_login: bool = True,
) -> dict[str, Any]:
    """
    Consulta ReporteInventario2020.aspx mediante el mismo POST ASP.NET
    observado en el navegador.

    Flujo:
      GET página -> extraer VIEWSTATE/EVENTVALIDATION/campos ->
      POST Buscar -> parsear gv_principal ->
      recorrer Page$2, Page$3, ... si load_all_pages=True.

    IMPORTANTE
    ----------
    - No inventa stock: usa las columnas reales del GridView.
    - Si available_for_sale=True, la pantalla WMS define "Cantidad" como
      (cantidad - cantidad_reservada) y además activa "Sin Tratam.".
    - No contiene credenciales, tokens ni ids de sesión hardcodeados.
    """
    base_url = DEFAULT_WMS_BASE_URL
    url = f"{base_url}{INVENTORY_PATH}"

    own_session = session is None
    http = session or create_wms_session(cookie_header=cookie_header)

    rows: list[dict[str, Any]] = []
    pages_loaded = 0
    last_status: int | None = None

    quantity_mode = (
        "disponible_wms"
        if available_for_sale
        else "fisica_menos_reservada"
    )

    try:
        # Si existen credenciales, autenticamos primero. Así evitamos el GET
        # anónimo al reporte que el servidor WMS puede responder con HTTP 500.
        supplied_user = (
            username if username is not None else os.getenv("WMS_USERNAME", "")
        )
        supplied_password = (
            password if password is not None else os.getenv("WMS_PASSWORD", "")
        )

        if auto_login and str(supplied_user).strip() and str(supplied_password):
            login_ok, login_error = login_wms(
                http,
                username=username,
                password=password,
                timeout=timeout,
            )
            if not login_ok:
                return WMSInventoryResult(
                    ok=False,
                    rows=[],
                    summary=summarize_inventory([]),
                    pages_loaded=0,
                    source=url,
                    quantity_mode=quantity_mode,
                    error=login_error or "No fue posible autenticar en WMS.",
                    status_code=None,
                ).as_dict()

        # El formulario del reporte contiene el VIEWSTATE que necesitamos para
        # reproducir el POST ASP.NET. Si el servidor no admite GET al reporte,
        # devolvemos un diagnóstico específico en vez de ocultar el HTTP 500.
        initial = http.get(
            url,
            timeout=timeout,
            allow_redirects=True,
        )
        last_status = initial.status_code

        if initial.status_code >= 500:
            return WMSInventoryResult(
                ok=False,
                rows=[],
                summary=summarize_inventory([]),
                pages_loaded=0,
                source=url,
                quantity_mode=quantity_mode,
                error=(
                    f"El WMS respondió HTTP {initial.status_code} al GET inicial "
                    "de ReporteInventario2020.aspx. La sesión sí intentó login; "
                    "falta reproducir el estado ASP.NET inicial del reporte por "
                    "la ruta exacta que usa el navegador."
                ),
                status_code=initial.status_code,
            ).as_dict()

        initial.raise_for_status()

        if _looks_like_login_page(initial):
            if auto_login:
                login_ok, login_error = login_wms(
                    http,
                    username=username,
                    password=password,
                    timeout=timeout,
                )
                if not login_ok:
                    return WMSInventoryResult(
                        ok=False,
                        rows=[],
                        summary=summarize_inventory([]),
                        pages_loaded=0,
                        source=url,
                        quantity_mode=quantity_mode,
                        error=login_error or "No fue posible autenticar en WMS.",
                        status_code=initial.status_code,
                    ).as_dict()

                initial = http.get(
                    url,
                    timeout=timeout,
                    allow_redirects=True,
                )
                last_status = initial.status_code

                if initial.status_code >= 500:
                    return WMSInventoryResult(
                        ok=False,
                        rows=[],
                        summary=summarize_inventory([]),
                        pages_loaded=0,
                        source=url,
                        quantity_mode=quantity_mode,
                        error=(
                            f"Login aceptado, pero el GET del reporte respondió "
                            f"HTTP {initial.status_code}. Necesitamos obtener el "
                            "VIEWSTATE inicial sin usar GET directo."
                        ),
                        status_code=initial.status_code,
                    ).as_dict()

                initial.raise_for_status()

            if _looks_like_login_page(initial):
                return WMSInventoryResult(
                    ok=False,
                    rows=[],
                    summary=summarize_inventory([]),
                    pages_loaded=0,
                    source=url,
                    quantity_mode=quantity_mode,
                    error="El WMS continúa solicitando autenticación.",
                    status_code=initial.status_code,
                ).as_dict()

        state = _parse_form_state(initial.text)

        if "__VIEWSTATE" not in state:
            return WMSInventoryResult(
                ok=False,
                rows=[],
                summary=summarize_inventory([]),
                pages_loaded=0,
                source=url,
                quantity_mode=quantity_mode,
                error=(
                    "No se encontró __VIEWSTATE en ReporteInventario2020.aspx. "
                    "La página puede haber cambiado o la sesión no tiene acceso."
                ),
                status_code=initial.status_code,
            ).as_dict()

        payload = _apply_search_filters(
            state,
            date=date,
            site=site,
            product=product,
            warehouse=warehouse,
            location=location,
            zone=zone,
            treatment=treatment,
            container=container,
            order=order,
            available_for_sale=available_for_sale,
            grouped=grouped,
            full_inventory=full_inventory,
            output_location=output_location,
        )

        search = http.post(
            url,
            data=payload,
            timeout=timeout,
            allow_redirects=True,
        )
        last_status = search.status_code
        search.raise_for_status()

        if _looks_like_login_page(search):
            return WMSInventoryResult(
                ok=False,
                rows=[],
                summary=summarize_inventory([]),
                pages_loaded=0,
                source=url,
                quantity_mode=quantity_mode,
                error="La sesión WMS expiró o no está autenticada.",
                status_code=search.status_code,
            ).as_dict()

        parsed = parse_inventory_html(
            search.text,
            available_for_sale=available_for_sale,
        )
        rows.extend(parsed["rows"])
        pages_loaded = 1

        if load_all_pages:
            pending = deque(
                sorted(
                    p
                    for p in parsed["page_numbers"]
                    if p > 1 and p <= max_pages
                )
            )
            queued = set(pending)
            seen = {1}

            current_html = search.text

            while pending and pages_loaded < max_pages:
                page_number = pending.popleft()
                queued.discard(page_number)

                if page_number in seen:
                    continue

                page_payload = _paging_payload(
                    current_html,
                    page_number,
                )

                page_response = http.post(
                    url,
                    data=page_payload,
                    timeout=timeout,
                    allow_redirects=True,
                )
                last_status = page_response.status_code
                page_response.raise_for_status()

                page_parsed = parse_inventory_html(
                    page_response.text,
                    available_for_sale=available_for_sale,
                )

                rows.extend(page_parsed["rows"])
                pages_loaded += 1
                seen.add(page_number)
                current_html = page_response.text

                # Algunos GridView muestran páginas adicionales al avanzar.
                for discovered in page_parsed["page_numbers"]:
                    if (
                        discovered > 0
                        and discovered <= max_pages
                        and discovered not in seen
                        and discovered not in queued
                    ):
                        pending.append(discovered)
                        queued.add(discovered)

        # Desduplicación defensiva: una página repetida no debe duplicar stock.
        # ID parece ser identificador único de inventario; si viene vacío usamos
        # una combinación operacional estable.
        unique_rows: list[dict[str, Any]] = []
        seen_keys: set[tuple[Any, ...]] = set()

        for row in rows:
            row_id = _clean(row.get("id"))

            if row_id:
                key = ("id", row_id)
            else:
                key = (
                    "fallback",
                    _clean(row.get("sku")),
                    _clean(row.get("sitio")),
                    _clean(row.get("bodega")),
                    _clean(row.get("ubicacion")),
                    _clean(row.get("contenedor")),
                    _clean(row.get("etiqueta")),
                    _clean(row.get("pedido")),
                    _to_number(row.get("cantidad_reportada_wms")),
                    _to_number(row.get("cantidad_reservada")),
                )

            if key in seen_keys:
                continue

            seen_keys.add(key)
            unique_rows.append(row)

        summary = summarize_inventory(unique_rows)
        summary["por_sku"] = inventory_by_sku(unique_rows)

        return WMSInventoryResult(
            ok=True,
            rows=unique_rows,
            summary=summary,
            pages_loaded=pages_loaded,
            source=url,
            quantity_mode=quantity_mode,
            error=None,
            status_code=last_status,
        ).as_dict()

    except requests.RequestException as exc:
        return WMSInventoryResult(
            ok=False,
            rows=[],
            summary=summarize_inventory([]),
            pages_loaded=pages_loaded,
            source=url,
            quantity_mode=quantity_mode,
            error=f"{type(exc).__name__}: {exc}",
            status_code=last_status,
        ).as_dict()

    except Exception as exc:
        return WMSInventoryResult(
            ok=False,
            rows=[],
            summary=summarize_inventory([]),
            pages_loaded=pages_loaded,
            source=url,
            quantity_mode=quantity_mode,
            error=f"{type(exc).__name__}: {exc}",
            status_code=last_status,
        ).as_dict()

    finally:
        if own_session:
            http.close()


def get_available_stock(
    sku: str,
    *,
    site: str | None = "CASA_MATRIZ",
    timeout: float = 20.0,
    session: requests.Session | None = None,
    cookie_header: str | None = None,
    username: str | None = None,
    password: str | None = None,
    auto_login: bool = True,
) -> dict[str, Any]:
    """
    Atajo para el uso más común del dashboard:
    stock disponible para venta de un SKU.
    """
    return get_inventory(
        product=sku,
        site=site,
        available_for_sale=True,
        grouped=False,
        full_inventory=False,
        load_all_pages=True,
        timeout=timeout,
        session=session,
        cookie_header=cookie_header,
        username=username,
        password=password,
        auto_login=auto_login,
    )
