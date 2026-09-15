from __future__ import annotations

import os
import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


load_dotenv()


# ============================================================
# CONFIGURACIÓN
# ============================================================

WMS_BASE_URL = os.getenv(
    "WMS_BASE_URL",
    "http://104.45.239.215/wms",
).rstrip("/")

WMS_USERNAME = os.getenv("WMS_USERNAME", "").strip()
WMS_PASSWORD = os.getenv("WMS_PASSWORD", "").strip()

WMS_SITE = os.getenv("WMS_SITE", "2").strip()
WMS_RESOURCE = os.getenv("WMS_RESOURCE", "678").strip()
WMS_CLIENT = os.getenv("WMS_CLIENT", "76090530-5").strip()

REQUEST_TIMEOUT = 60

INVENTORY_REPORT_URL = (
    f"{WMS_BASE_URL}/ReporteInventario20SP.aspx"
)


class WMSError(RuntimeError):
    pass


# ============================================================
# UTILIDADES
# ============================================================

def _clean(value: Any) -> str:
    if value is None:
        return ""

    value = str(value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _normalize_order(value: Any) -> str:
    value = _clean(value).replace("%", "")
    if not value:
        return ""

    digits = re.sub(r"[^0-9]", "", value)
    if digits:
        return digits.lstrip("0") or "0"

    return value


def _integer(value: Any) -> int:
    raw = _clean(value)

    if not raw:
        return 0

    # WMS puede devolver 50,000 para representar 50.
    raw = raw.replace(".", "").replace(",", ".")

    try:
        return int(float(raw))
    except Exception:
        return 0


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "html.parser")


# ============================================================
# ASP.NET WEB FORMS
# ============================================================

def _collect_form_payload(html: str) -> dict[str, str]:
    soup = _soup(html)
    form = soup.find("form")

    if form is None:
        return {}

    payload: dict[str, str] = {}

    for field in form.find_all("input"):
        name = field.get("name")

        if not name or field.has_attr("disabled"):
            continue

        field_type = str(field.get("type") or "text").lower()

        if field_type in {
            "button",
            "submit",
            "image",
            "file",
            "reset",
        }:
            continue

        if field_type in {"checkbox", "radio"} and not field.has_attr("checked"):
            continue

        payload[_clean(name)] = str(field.get("value") or "")

    for select in form.find_all("select"):
        name = select.get("name")

        if not name or select.has_attr("disabled"):
            continue

        selected = select.find("option", selected=True) or select.find("option")

        payload[_clean(name)] = (
            str(selected.get("value") or "")
            if selected is not None
            else ""
        )

    for textarea in form.find_all("textarea"):
        name = textarea.get("name")

        if not name or textarea.has_attr("disabled"):
            continue

        payload[_clean(name)] = textarea.get_text() or ""

    return payload


# ============================================================
# LOGIN
# ============================================================

def create_wms_session(
    username: str | None = None,
    password: str | None = None,
) -> requests.Session:

    user = (username or WMS_USERNAME).strip()
    pwd = password or WMS_PASSWORD

    if not user:
        raise WMSError("WMS_USERNAME no está configurado.")

    if not pwd:
        raise WMSError("WMS_PASSWORD no está configurado.")

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/153.0.0.0 "
                "Safari/537.36"
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml,"
                "application/xml;q=0.9,"
                "image/avif,"
                "image/webp,"
                "*/*;q=0.8"
            ),
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
    )

    # --------------------------------------------------------
    # LOGIN PRINCIPAL
    # --------------------------------------------------------

    login_url = (
        f"{WMS_BASE_URL}/web_login.aspx"
        "?ReturnUrl=%2Fwms%2Flogin.aspx"
    )

    response = session.get(
        login_url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    payload = _collect_form_payload(response.text)

    payload.update(
        {
            "ctl00$contentLogin$txtUserName": user,
            "ctl00$contentLogin$txtUserPass": pwd,
            "ctl00$contentLogin$valida": "Ingresar",
        }
    )

    response = session.post(
        login_url,
        data=payload,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    # --------------------------------------------------------
    # SELECCIÓN DE CONTEXTO WMS
    # --------------------------------------------------------

    form_login_url = f"{WMS_BASE_URL}/form_login.aspx"

    response = session.get(
        form_login_url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    context_payload = _collect_form_payload(response.text)

    context_payload.update(
        {
            "ctl00$placeHolderContent$sitio": WMS_SITE,
            "ctl00$placeHolderContent$recurso": WMS_RESOURCE,
            "ctl00$placeHolderContent$cliente": WMS_CLIENT,
            "ctl00$placeHolderContent$inicia_sesion": "Inicia Sesion",
        }
    )

    response = session.post(
        form_login_url,
        data=context_payload,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    final_url = str(response.url).lower()

    if "web_login.aspx" in final_url:
        raise WMSError("El WMS volvió al login principal.")

    return session


# ============================================================
# PARSER GENÉRICO DE GRIDVIEW
# ============================================================

def _find_table_by_id_contains(
    html: str,
    id_fragment: str,
):
    soup = _soup(html)

    fragment = id_fragment.lower()

    for table in soup.find_all("table"):
        table_id = _clean(table.get("id") or "").lower()

        if fragment in table_id:
            return table

    return None


def _parse_grid_table(
    table,
) -> list[dict[str, str]]:
    if table is None:
        return []

    tbody = table.find("tbody")

    if tbody:
        rows = tbody.find_all("tr", recursive=False)
    else:
        rows = table.find_all("tr", recursive=False)

    if not rows:
        return []

    header_row = None
    headers: list[str] = []

    for row in rows:
        ths = row.find_all("th", recursive=False)

        if not ths:
            continue

        current_headers = [
            _clean(th.get_text(" ", strip=True))
            for th in ths
        ]

        if current_headers:
            header_row = row
            headers = current_headers
            break

    if header_row is None:
        return []

    results: list[dict[str, str]] = []

    start_index = rows.index(header_row) + 1

    for row in rows[start_index:]:
        cells = row.find_all("td", recursive=False)

        if not cells:
            continue

        values = [
            _clean(cell.get_text(" ", strip=True))
            for cell in cells
        ]

        if not any(values):
            continue

        item: dict[str, str] = {}

        for index, value in enumerate(values):
            header = headers[index] if index < len(headers) else ""
            key = header or f"col_{index}"
            item[key] = value

        results.append(item)

    return results


# ============================================================
# TABLA PRINCIPAL DE PEDIDOS
# ============================================================

def _extract_grid(
    html: str,
) -> list[dict[str, str]]:

    table = _find_table_by_id_contains(
        html,
        "gv_principal",
    )

    rows = _parse_grid_table(table)

    # Mantener solo filas con pedido.
    return [
        row
        for row in rows
        if _clean(row.get("Pedido"))
    ]


def normalize_wms_row(
    row: dict[str, str],
) -> dict[str, Any]:

    requested = _integer(
        row.get("sol")
        or row.get("Solicitado")
        or row.get("Solic.")
    )

    completed = _integer(
        row.get("ok")
        or row.get("OK")
    )

    pending = max(requested - completed, 0)

    progress = (
        round(completed / requested * 100, 1)
        if requested > 0
        else 0.0
    )

    return {
        "pedido": _clean(row.get("Pedido")),
        "estado_wms": _clean(
            row.get("Orden Estado.")
            or row.get("Orden Estado")
        ),
        "estado_monitor": _clean(
            row.get("Estado Monitor")
        ),
        "fecha_creacion": _clean(
            row.get("Fecha Creación")
        ),
        "tipo_despacho": _clean(
            row.get("Tipo Despacho")
        ),
        "cliente": _clean(
            row.get("Cliente")
            or row.get("Cliente (DE)")
        ),
        "nombre_cliente": _clean(
            row.get("Nombre Cliente")
            or row.get("Nombre (DE)")
        ),
        "factura": _clean(
            row.get("Factura")
            or row.get("Factura.")
        ),
        "fecha_despacho": _clean(
            row.get("Fecha Despacho (2)")
        ),
        "estado_orden_simple": _clean(
            row.get("Estado Orden Simple")
        ),
        "estado_registro": _clean(
            row.get("Estado Registro")
        ),
        "estado_lp": _clean(
            row.get("Estado LP")
        ),
        "ola": _clean(row.get("Ola")),
        "direccion": _clean(
            row.get("Direccion")
            or row.get("Dirección")
        ),
        "ciudad": _clean(row.get("Ciudad")),
        "solicitado": requested,
        "ok": completed,
        "pendiente": pending,
        "avance": progress,
        "raw": row,
    }


# ============================================================
# BÚSQUEDA PEDIDOS
# ============================================================

def _search_order_page(
    session: requests.Session,
    order: str | None = None,
    days_back: int = 90,
    debug: bool = False,
) -> tuple[str, list[dict[str, str]]]:

    url = f"{WMS_BASE_URL}/form_out_pedido2020.aspx"

    response = session.get(
        url,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    payload = _collect_form_payload(response.text)

    today = datetime.now()
    start = today - timedelta(days=max(days_back, 1))

    payload[
        "ctl00$placeHolderContent$cdtFecha_crea$textbox_control1"
    ] = start.strftime("%d-%m-%Y")

    payload[
        "ctl00$placeHolderContent$cdtFecha_crea$textbox_control2"
    ] = today.strftime("%d-%m-%Y")

    if order:
        normalized = _normalize_order(order)

        payload[
            "ctl00$placeHolderContent$ctPedido$textbox_control"
        ] = f"%{normalized}"

    payload[
        "ctl00$placeHolderContent$ControlCRUD$bBuscar$button"
    ] = ""

    payload["__EVENTTARGET"] = ""
    payload["__EVENTARGUMENT"] = ""

    response = session.post(
        url,
        data=payload,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()

    rows = _extract_grid(response.text)

    if debug:
        print("SEARCH URL:", response.url)
        print("SEARCH ROWS:", len(rows))
        print("ORDER FOUND:", order and _normalize_order(order) in response.text)

    return response.text, rows


def search_orders(
    order: str | None = None,
    days_back: int = 90,
    debug: bool = False,
) -> list[dict[str, Any]]:

    session = create_wms_session()

    try:
        _html, rows = _search_order_page(
            session=session,
            order=order,
            days_back=days_back,
            debug=debug,
        )

        return [
            normalize_wms_row(row)
            for row in rows
        ]
    finally:
        session.close()


def search_order(
    order: str,
    debug: bool = False,
) -> dict[str, Any] | None:

    wanted = _normalize_order(order)

    rows = search_orders(
        order=wanted,
        days_back=90,
        debug=debug,
    )

    for row in rows:
        candidate = _normalize_order(
            row.get("pedido")
        )

        if candidate == wanted:
            return row

    if len(rows) == 1:
        return rows[0]

    return None


# ============================================================
# COMANDOS DEL PEDIDO
# ============================================================

def _find_order_row_and_commands_target(
    html: str,
    order: str,
) -> tuple[dict[str, str] | None, str | None]:

    wanted = _normalize_order(order)

    table = _find_table_by_id_contains(
        html,
        "gv_principal",
    )

    if table is None:
        return None, None

    tbody = table.find("tbody")

    if tbody:
        tr_rows = tbody.find_all("tr", recursive=False)
    else:
        tr_rows = table.find_all("tr", recursive=False)

    for tr in tr_rows:
        text = _clean(
            tr.get_text(" ", strip=True)
        )

        if wanted not in _normalize_order(text) and wanted not in text:
            # La fila puede contener muchos dígitos juntos.
            # Seguimos validando específicamente el contenido del pedido.
            pass

        cells = tr.find_all("td", recursive=False)

        if not cells:
            continue

        # Buscamos el link "Ver comandos del pedido".
        link = tr.find(
            "a",
            id=lambda value: (
                value
                and "LinkButton_ver_comandos"
                in _clean(value)
            ),
        )

        if link is None:
            continue

        href = _clean(link.get("href") or "")

        match = re.search(
            r"__doPostBack\('([^']+)'",
            href,
        )

        if not match:
            continue

        event_target = match.group(1)

        # Verificar que la fila corresponde al pedido buscado.
        row_text = _clean(
            tr.get_text(" ", strip=True)
        )

        # En el HTML del WMS el pedido conserva ceros iniciales.
        # Aceptamos comparación normalizada.
        digit_candidates = re.findall(
            r"\d{5,}",
            row_text,
        )

        if not any(
            _normalize_order(candidate) == wanted
            for candidate in digit_candidates
        ):
            continue

        return {
            "row_text": row_text,
            "link_id": _clean(link.get("id") or ""),
            "href": href,
        }, event_target

    return None, None


def _extract_commands_grid(
    html: str,
    debug: bool = False,
) -> list[dict[str, str]]:

    table = _find_table_by_id_contains(
        html,
        "gv_comandos",
    )

    if table is None:
        if debug:
            print("COMANDOS: no se encontró tabla gv_comandos")
        return []

    # En esta grilla el WMS no siempre usa TH para la cabecera.
    # Por eso inspeccionamos todos los TR y aceptamos TH o TD.
    rows = table.find_all("tr")

    if debug:
        print("COMANDOS TABLE ID:", table.get("id"))
        print("COMANDOS TR COUNT:", len(rows))

    if not rows:
        return []

    expected_headers = {
        "pedido",
        "tipo pedido",
        "linea",
        "producto (desc.)",
        "producto",
        "descripción producto",
        "descripcion producto",
        "cantidad",
        "estado",
        "operador",
        "contenedor",
        "ubicación act.",
        "ubicacion act.",
        "bodega",
    }

    header_index = None
    headers: list[str] = []

    for idx, row in enumerate(rows):
        cells = row.find_all(["th", "td"], recursive=False)

        if not cells:
            continue

        values = [
            _clean(cell.get_text(" ", strip=True))
            for cell in cells
        ]

        normalized = {
            _clean(v).lower()
            for v in values
            if _clean(v)
        }

        # Una cabecera válida debe compartir al menos 3 nombres conocidos.
        score = len(normalized & expected_headers)

        if debug and idx < 8:
            print(
                f"COMANDOS ROW {idx}:",
                values[:20],
                "HEADER SCORE:",
                score,
            )

        if score >= 3:
            header_index = idx
            headers = values
            break

    if header_index is None:
        if debug:
            print("COMANDOS: no se detectó fila de encabezados.")
        return []

    results: list[dict[str, str]] = []

    for row in rows[header_index + 1:]:
        cells = row.find_all(["td", "th"], recursive=False)

        if not cells:
            continue

        values = [
            _clean(cell.get_text(" ", strip=True))
            for cell in cells
        ]

        if not any(values):
            continue

        # Ignorar filas de pie/botones que no tengan suficientes columnas.
        if len(values) < max(5, len(headers) // 2):
            continue

        item: dict[str, str] = {}

        for index, value in enumerate(values):
            header = (
                headers[index]
                if index < len(headers)
                else ""
            )

            key = header or f"col_{index}"
            item[key] = value

        # Solo conservar filas que parezcan comandos reales.
        row_text = " ".join(values).strip()

        if not row_text:
            continue

        results.append(item)

    if debug:
        print("COMANDOS HEADERS:", headers)
        print("COMANDOS PARSED ROWS:", len(results))

        if results:
            print("COMANDOS FIRST PARSED RAW:")
            print(results[0])

    return results


def _normalize_command_status(value: Any) -> str:
    raw = _clean(value)

    if not raw:
        return ""

    upper = raw.upper()

    if "PACKING" in upper or "PACK" in upper:
        return "Packing"

    if "PICKING" in upper or "PICK" in upper:
        return "Picking"

    if "REPOS" in upper:
        return "Reposición"

    if "QUIEBRE" in upper:
        return "Quiebre"

    if "CHECK" in upper or "CONTROL" in upper:
        return "Check"

    if "FACTUR" in upper:
        return "Facturar"

    if "FINAL" in upper or "COMPLET" in upper or upper == "OK":
        return "Completado"

    return raw


def normalize_command_row(
    row: dict[str, str],
) -> dict[str, Any]:

    sku = _clean(
        row.get("Producto (Desc.)")
        or row.get("Producto")
        or row.get("producto")
    )

    description = _clean(
        row.get("Descripción Producto")
        or row.get("Descripcion Producto")
        or row.get("Descrip.")
        or row.get("Descripción")
    )

    qty = _integer(
        row.get("Cantidad")
        or row.get("qty")
    )

    raw_status = _clean(
        row.get("Estado")
        or row.get("estado")
    )

    return {
        "pedido": _clean(
            row.get("Pedido")
            or row.get("pedido")
        ),
        "linea": _clean(
            row.get("linea")
            or row.get("Línea")
            or row.get("Linea")
        ),
        "sku": sku,
        "producto": description,
        "cantidad": qty,
        "estado_raw": raw_status,
        "proceso": _normalize_command_status(
            raw_status
        ),
        "operador": _clean(
            row.get("Operador")
        ),
        "equipamiento": _clean(
            row.get("Equipamiento")
        ),
        "contenedor": _clean(
            row.get("Contenedor")
        ),
        "ubicacion": _clean(
            row.get("Ubicación Act.")
            or row.get("Ubicacion Act.")
            or row.get("Ubicación")
        ),
        "bodega": _clean(
            row.get("Bodega")
        ),
        "destino": _clean(
            row.get("Destino")
        ),
        "fecha_liberacion": _clean(
            row.get("Fecha Liberación")
            or row.get("Fecha Liberacion")
        ),
        "fecha_nv": _clean(
            row.get("Fecha NV.")
            or row.get("Fecha NV")
        ),
        "raw": row,
    }


def get_order_commands(
    order: str,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Abre el modal COMANDOS del pedido mediante el mismo postback
    ASP.NET que usa el botón "Ver comandos del pedido".

    Retorna:
        {
            "ok": bool,
            "order": "...",
            "rows": [...],
            "raw_rows": [...],
            "error": None | str,
        }
    """

    session = create_wms_session()

    try:
        search_html, _rows = _search_order_page(
            session=session,
            order=order,
            days_back=90,
            debug=debug,
        )

        row_info, event_target = (
            _find_order_row_and_commands_target(
                search_html,
                order,
            )
        )

        if not event_target:
            return {
                "ok": False,
                "order": str(order),
                "rows": [],
                "raw_rows": [],
                "error": (
                    "No se encontró el botón "
                    "'Ver comandos del pedido' "
                    "para la orden."
                ),
            }

        payload = _collect_form_payload(
            search_html
        )

        # El postback del modal se realiza sobre la misma página.
        payload["__EVENTTARGET"] = event_target
        payload["__EVENTARGUMENT"] = ""

        # No reenviar el botón Buscar.
        payload.pop(
            "ctl00$placeHolderContent$ControlCRUD$bBuscar$button",
            None,
        )

        url = f"{WMS_BASE_URL}/form_out_pedido2020.aspx"

        response = session.post(
            url,
            data=payload,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        raw_rows = _extract_commands_grid(
            response.text,
            debug=debug,
        )

        rows = [
            normalize_command_row(row)
            for row in raw_rows
        ]

        if debug:
            print()
            print("=== COMANDOS WMS ===")
            print("PEDIDO:", order)
            print("EVENTTARGET:", event_target)
            print("ROW INFO:", row_info)
            print("STATUS:", response.status_code)
            print("HTML LEN:", len(response.text))
            print("GV COMANDOS:", "gv_comandos" in response.text)
            print("FILAS COMANDOS:", len(rows))

            if raw_rows:
                print("PRIMERA FILA RAW:")
                print(raw_rows[0])

            if rows:
                print("PRIMERA FILA NORMALIZADA:")
                print(rows[0])

            with open(
                "wms_debug_commands.html",
                "w",
                encoding="utf-8",
            ) as f:
                f.write(response.text)

            print(
                "HTML comandos guardado en "
                "wms_debug_commands.html"
            )

        return {
            "ok": bool(rows),
            "order": str(order),
            "rows": rows,
            "raw_rows": raw_rows,
            "error": (
                None
                if rows
                else "El modal COMANDOS no devolvió filas."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "order": str(order),
            "rows": [],
            "raw_rows": [],
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }

    finally:
        session.close()


# ============================================================
# RESUMEN DE COMANDOS POR SKU
# ============================================================

def summarize_order_commands(
    order: str,
    debug: bool = False,
) -> dict[str, Any]:

    result = get_order_commands(
        order=order,
        debug=debug,
    )

    if not result.get("ok"):
        return result

    grouped: dict[str, dict[str, Any]] = {}

    for row in result["rows"]:
        sku = _clean(row.get("sku"))

        if not sku:
            continue

        item = grouped.setdefault(
            sku,
            {
                "sku": sku,
                "producto": _clean(
                    row.get("producto")
                ),
                "cantidad_comandos": 0,
                "procesos": [],
                "estados_raw": [],
                "operadores": [],
                "contenedores": [],
                "ubicaciones": [],
                "comandos": 0,
            },
        )

        item["cantidad_comandos"] += int(
            row.get("cantidad") or 0
        )
        item["comandos"] += 1

        for target, value in (
            ("procesos", row.get("proceso")),
            ("estados_raw", row.get("estado_raw")),
            ("operadores", row.get("operador")),
            ("contenedores", row.get("contenedor")),
            ("ubicaciones", row.get("ubicacion")),
        ):
            cleaned = _clean(value)

            if cleaned and cleaned not in item[target]:
                item[target].append(cleaned)

    summary_rows = list(grouped.values())

    return {
        "ok": True,
        "order": str(order),
        "rows": summary_rows,
        "command_rows": result["rows"],
        "error": None,
    }


# ============================================================
# ENDPOINT DIRECTO DE DETALLE / COMANDOS
# ============================================================

def _extract_js_variable(
    html: str,
    variable_name: str,
) -> str:
    """
    Extrae variables JavaScript simples del HTML, por ejemplo:
        var var_sitio = "CASA_MATRIZ";
        var var_sessid = 'abc123';
    """
    pattern = (
        rf"\bvar\s+{re.escape(variable_name)}\s*=\s*"
        rf"['\"]([^'\"]*)['\"]"
    )

    match = re.search(
        pattern,
        html or "",
        flags=re.IGNORECASE,
    )

    return _clean(match.group(1)) if match else ""


def _decode_asmx_response(
    response: requests.Response,
) -> Any:
    """
    Los servicios ASMX suelen responder:
        {"d": "[{...}, {...}]"}
    o bien:
        {"d": [...]}
    """

    try:
        data = response.json()
    except Exception as exc:
        raise WMSError(
            "El WebService no devolvió JSON válido. "
            f"Content-Type={response.headers.get('Content-Type')!r}. "
            f"Inicio respuesta={response.text[:500]!r}"
        ) from exc

    if not isinstance(data, dict):
        return data

    raw = data.get("d")

    if raw is None:
        return data

    if not isinstance(raw, str):
        return raw

    raw = raw.strip()

    if not raw:
        return []

    # Primera opción: JSON estándar.
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Algunos ASMX antiguos devuelven JSON con pequeñas irregularidades.
    # No usamos eval por seguridad: devolvemos el texto crudo si no es JSON.
    return raw


def _ob_type_candidates(
    requested_type: str | None,
    search_rows: list[dict[str, str]] | None = None,
) -> list[str]:
    """
    El JavaScript del WMS llama al endpoint usando data[i].TipoPedido.
    Como el grid principal puede mostrar una descripción distinta al código
    interno, probamos una lista pequeña de candidatos de solo lectura.
    """

    values: list[str] = []

    def add(value: Any) -> None:
        cleaned = _clean(value)

        if cleaned and cleaned not in values:
            values.append(cleaned)

    add(requested_type)

    for row in search_rows or []:
        for key in (
            "TipoPedido",
            "Tipo Pedido",
            "ObType",
            "Ob Type",
            "Tipo Documento",
            "Tipo Doc.",
            "Documento",
        ):
            add(row.get(key))

    # Códigos observados/esperables en el WMS para notas de venta.
    add("NVV")
    add("NVI")

    # Descripciones visibles que a veces son aceptadas por integraciones ASMX.
    add("NOTA VENTA WMS")
    add("NOTA VENTA")

    return values


def get_order_commands_direct(
    order: str,
    tipo_pedido: str | None = None,
    sitio: str | None = None,
    cliente: str | None = None,
    dest: str | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Consulta directamente el WebService que usa el JavaScript del WMS:

    /webservices/getAsyncAutocomplete.asmx/
    GetMonitorPedidoDetalleComandosPICK

    No modifica datos; es una consulta de detalle.

    Retorna:
        {
            "ok": bool,
            "order": str,
            "rows": list,
            "ob_type_used": str | None,
            "site_used": str,
            "client_used": str,
            "sessid": str,
            "error": str | None,
        }
    """

    wanted = str(order).strip()
    session = create_wms_session()

    try:
        # ----------------------------------------------------
        # 1) Buscar el pedido.
        # Esto además deja la sesión en el mismo contexto
        # que usa el navegador antes de abrir el detalle.
        # ----------------------------------------------------
        search_html, search_rows = _search_order_page(
            session=session,
            order=wanted,
            days_back=90,
            debug=debug,
        )

        # ----------------------------------------------------
        # 2) Obtener variables reales que incrusta el WMS.
        # ----------------------------------------------------
        js_site = _extract_js_variable(
            search_html,
            "var_sitio",
        )

        js_client = _extract_js_variable(
            search_html,
            "var_cliente",
        )

        sessid = _extract_js_variable(
            search_html,
            "var_sessid",
        )

        site_used = (
            _clean(sitio)
            or js_site
            or "CASA_MATRIZ"
        )

        client_used = (
            _clean(cliente)
            or js_client
            or WMS_CLIENT
        )

        dest_used = _clean(dest)

        if not dest_used:
            dest_used = (
                "MESON-TIENDA"
                if site_used.upper() == "ACOMATTA"
                else "ALL"
            )

        if not sessid:
            return {
                "ok": False,
                "order": wanted,
                "rows": [],
                "ob_type_used": None,
                "site_used": site_used,
                "client_used": client_used,
                "sessid": "",
                "error": (
                    "No se encontró var_sessid en el HTML del WMS."
                ),
            }

        endpoint = (
            f"{WMS_BASE_URL}"
            "/webservices/getAsyncAutocomplete.asmx/"
            "GetMonitorPedidoDetalleComandosPICK"
        )

        candidates = _ob_type_candidates(
            requested_type=tipo_pedido,
            search_rows=search_rows,
        )

        attempts: list[dict[str, Any]] = []

        # ----------------------------------------------------
        # 3) Probar candidatos de ob_type.
        # ----------------------------------------------------
        for ob_type in candidates:
            payload = {
                "ob_oid": wanted,
                "ob_type": ob_type,
                "sitio": site_used,
                "cliente": client_used,
                "strsessid": sessid,
                "dest": dest_used,
            }

            if debug:
                print()
                print("-----------------------------------")
                print("PROBANDO WEB SERVICE")
                print("-----------------------------------")
                print("ENDPOINT:", endpoint)
                print("PEDIDO:", wanted)
                print("OB_TYPE:", ob_type)
                print("SITIO:", site_used)
                print("CLIENTE:", client_used)
                print("DEST:", dest_used)
                print("SESSID:", sessid)

            response = session.post(
                endpoint,
                json=payload,
                headers={
                    "Content-Type": (
                        "application/json; charset=utf-8"
                    ),
                    "Accept": (
                        "application/json, "
                        "text/javascript, */*; q=0.01"
                    ),
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": (
                        f"{WMS_BASE_URL}/"
                        "form_out_pedido2020.aspx"
                    ),
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            attempt = {
                "ob_type": ob_type,
                "status_code": response.status_code,
                "content_type": response.headers.get(
                    "Content-Type"
                ),
                "response_len": len(response.text),
            }

            if debug:
                print("STATUS:", response.status_code)
                print(
                    "CONTENT-TYPE:",
                    response.headers.get("Content-Type"),
                )
                print(
                    "RESPONSE LEN:",
                    len(response.text),
                )

            if not response.ok:
                attempt["error"] = response.text[:500]
                attempts.append(attempt)
                continue

            try:
                parsed = _decode_asmx_response(
                    response
                )
            except Exception as exc:
                attempt["error"] = (
                    f"{type(exc).__name__}: {exc}"
                )
                attempts.append(attempt)
                continue

            # Algunos servicios podrían envolver el listado.
            rows: list[Any] = []

            if isinstance(parsed, list):
                rows = parsed

            elif isinstance(parsed, dict):
                for key in (
                    "rows",
                    "data",
                    "result",
                    "items",
                ):
                    candidate = parsed.get(key)

                    if isinstance(candidate, list):
                        rows = candidate
                        break

            elif isinstance(parsed, str):
                attempt["raw_response"] = parsed[:1000]

            attempt["row_count"] = len(rows)
            attempts.append(attempt)

            if debug:
                print(
                    "TIPO PARSEADO:",
                    type(parsed).__name__,
                )
                print(
                    "CANTIDAD FILAS:",
                    len(rows),
                )

                if rows:
                    first = rows[0]

                    if isinstance(first, dict):
                        print()
                        print("CLAVES PRIMERA FILA:")
                        print(list(first.keys()))

                    print()
                    print("PRIMERA FILA:")
                    print(first)

                    print()
                    print("PRIMERAS 5 FILAS:")

                    for item in rows[:5]:
                        print(item)

            if rows:
                # Filtramos por pedido si el endpoint devuelve
                # más registros de los esperados.
                normalized_wanted = _normalize_order(
                    wanted
                )

                filtered: list[Any] = []

                for item in rows:
                    if not isinstance(item, dict):
                        filtered.append(item)
                        continue

                    item_order = (
                        item.get("ObOid")
                        or item.get("ob_oid")
                        or item.get("Pedido")
                        or item.get("pedido")
                    )

                    if not item_order:
                        filtered.append(item)
                        continue

                    if (
                        _normalize_order(item_order)
                        == normalized_wanted
                    ):
                        filtered.append(item)

                if filtered:
                    rows = filtered

                return {
                    "ok": True,
                    "order": wanted,
                    "rows": rows,
                    "ob_type_used": ob_type,
                    "site_used": site_used,
                    "client_used": client_used,
                    "dest_used": dest_used,
                    "sessid": sessid,
                    "attempts": attempts,
                    "error": None,
                }

        return {
            "ok": False,
            "order": wanted,
            "rows": [],
            "ob_type_used": None,
            "site_used": site_used,
            "client_used": client_used,
            "dest_used": dest_used,
            "sessid": sessid,
            "attempts": attempts,
            "error": (
                "El WebService respondió, pero ninguno de los "
                "candidatos de TipoPedido devolvió filas."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "order": wanted,
            "rows": [],
            "ob_type_used": None,
            "site_used": _clean(sitio),
            "client_used": _clean(cliente),
            "sessid": "",
            "attempts": [],
            "error": (
                f"{type(exc).__name__}: {exc}"
            ),
        }

    finally:
        session.close()


def inspect_order_commands(
    order: str,
    tipo_pedido: str | None = None,
) -> dict[str, Any]:
    """
    Función de diagnóstico pensada para ejecutar manualmente.
    Imprime todas las claves que entrega el WebService.
    """

    print()
    print("===================================")
    print("PRUEBA ENDPOINT COMANDOS DIRECTO")
    print("===================================")
    print("Pedido:", order)

    result = get_order_commands_direct(
        order=order,
        tipo_pedido=tipo_pedido,
        debug=True,
    )

    print()
    print("===================================")
    print("RESULTADO FINAL")
    print("===================================")
    print("OK:", result.get("ok"))
    print(
        "OB_TYPE UTILIZADO:",
        result.get("ob_type_used"),
    )
    print(
        "SITIO:",
        result.get("site_used"),
    )
    print(
        "CLIENTE:",
        result.get("client_used"),
    )

    if not result.get("ok"):
        print(
            "ERROR:",
            result.get("error"),
        )

        print()
        print("INTENTOS:")

        for attempt in result.get("attempts") or []:
            print(attempt)

        return result

    rows = result.get("rows") or []

    print("FILAS:", len(rows))

    if rows and isinstance(rows[0], dict):
        all_keys: list[str] = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            for key in row.keys():
                if key not in all_keys:
                    all_keys.append(key)

        print()
        print("TODAS LAS CLAVES ENCONTRADAS:")
        print(all_keys)

        print()
        print("DETALLE PRIMERAS 10 FILAS:")

        for row in rows[:10]:
            print(row)

    return result


# ============================================================
# ENDPOINT ADICIONAL: GetComandosPICKObType
# ============================================================

def get_commands_pick_obtype(
    order: str,
    tipo_pedido: str | None = None,
    sitio: str | None = None,
    cliente: str | None = None,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Consulta el endpoint declarado por el propio WMS:
        /webservices/getAsyncAutocomplete.asmx/GetComandosPICKObType

    Como aún no conocemos con certeza su contrato exacto de parámetros,
    esta función prueba variantes conservadoras basadas en los nombres
    ya observados en el JavaScript del WMS.

    No modifica datos; solo consulta.
    """

    wanted = str(order).strip()
    session = create_wms_session()

    try:
        search_html, search_rows = _search_order_page(
            session=session,
            order=wanted,
            days_back=90,
            debug=debug,
        )

        js_site = _extract_js_variable(
            search_html,
            "var_sitio",
        ) or "CASA_MATRIZ"

        js_client = _extract_js_variable(
            search_html,
            "var_cliente",
        ) or WMS_CLIENT

        sessid = _extract_js_variable(
            search_html,
            "var_sessid",
        )

        site_used = _clean(sitio) or js_site
        client_used = _clean(cliente) or js_client

        if not sessid:
            return {
                "ok": False,
                "order": wanted,
                "rows": [],
                "error": "No se encontró var_sessid.",
                "attempts": [],
            }

        endpoint = (
            f"{WMS_BASE_URL}"
            "/webservices/getAsyncAutocomplete.asmx/"
            "GetComandosPICKObType"
        )

        ob_types = _ob_type_candidates(
            requested_type=tipo_pedido,
            search_rows=search_rows,
        )

        # Variantes de payload a probar de forma segura.
        # Se priorizan nombres de parámetros observados en otros métodos ASMX.
        payload_templates = []

        for ob_type in ob_types:
            payload_templates.extend(
                [
                    {
                        "ob_oid": wanted,
                        "ob_type": ob_type,
                        "sitio": site_used,
                        "cliente": client_used,
                        "strsessid": sessid,
                    },
                    {
                        "pedido": wanted,
                        "tipo_pedido": ob_type,
                        "sitio": site_used,
                        "cliente": client_used,
                        "strsessid": sessid,
                    },
                    {
                        "ob_oid": wanted,
                        "ob_type": ob_type,
                        "sitio": site_used,
                        "cliente": client_used,
                    },
                ]
            )

        attempts = []

        for payload in payload_templates:
            if debug:
                print()
                print("-----------------------------------")
                print("PROBANDO GetComandosPICKObType")
                print("-----------------------------------")
                print("ENDPOINT:", endpoint)
                print("PAYLOAD:", payload)

            response = session.post(
                endpoint,
                json=payload,
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{WMS_BASE_URL}/form_out_pedido2020.aspx",
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )

            attempt = {
                "payload": payload,
                "status_code": response.status_code,
                "content_type": response.headers.get("Content-Type"),
                "response_len": len(response.text),
            }

            if debug:
                print("STATUS:", response.status_code)
                print("CONTENT-TYPE:", response.headers.get("Content-Type"))
                print("RESPONSE LEN:", len(response.text))

            if not response.ok:
                attempt["error"] = response.text[:500]
                attempts.append(attempt)
                continue

            try:
                parsed = _decode_asmx_response(response)
            except Exception as exc:
                attempt["error"] = f"{type(exc).__name__}: {exc}"
                attempts.append(attempt)
                continue

            rows = []
            if isinstance(parsed, list):
                rows = parsed
            elif isinstance(parsed, dict):
                for key in ("rows", "data", "result", "items"):
                    candidate = parsed.get(key)
                    if isinstance(candidate, list):
                        rows = candidate
                        break

            attempt["row_count"] = len(rows)
            attempts.append(attempt)

            if debug:
                print("TIPO PARSEADO:", type(parsed).__name__)
                print("CANTIDAD FILAS:", len(rows))
                if rows:
                    first = rows[0]
                    if isinstance(first, dict):
                        print("CLAVES PRIMERA FILA:")
                        print(list(first.keys()))
                    print("PRIMERA FILA:")
                    print(first)

            if rows:
                return {
                    "ok": True,
                    "order": wanted,
                    "rows": rows,
                    "payload_used": payload,
                    "attempts": attempts,
                    "error": None,
                }

        return {
            "ok": False,
            "order": wanted,
            "rows": [],
            "payload_used": None,
            "attempts": attempts,
            "error": (
                "GetComandosPICKObType respondió, pero ninguna variante "
                "de payload devolvió filas."
            ),
        }

    except Exception as exc:
        return {
            "ok": False,
            "order": wanted,
            "rows": [],
            "payload_used": None,
            "attempts": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        session.close()


def inspect_both_wms_endpoints(
    order: str,
) -> dict[str, Any]:
    """
    Ejecuta ambas fuentes:
    1) GetMonitorPedidoDetalleComandosPICK
    2) GetComandosPICKObType

    Imprime las claves y primeras filas para poder comparar/correlacionar.
    """

    print()
    print("===================================")
    print("1) DETALLE PEDIDO / COMANDOS")
    print("===================================")

    detail = get_order_commands_direct(
        order=order,
        tipo_pedido=None,
        debug=True,
    )

    print()
    print("===================================")
    print("2) ESTADO OPERACIONAL COMANDOS")
    print("===================================")

    commands = get_commands_pick_obtype(
        order=order,
        tipo_pedido=None,
        debug=True,
    )

    print()
    print("===================================")
    print("RESUMEN COMPARATIVO")
    print("===================================")

    print("DETALLE OK:", detail.get("ok"))
    print("DETALLE FILAS:", len(detail.get("rows") or []))
    print("COMANDOS OK:", commands.get("ok"))
    print("COMANDOS FILAS:", len(commands.get("rows") or []))

    if detail.get("rows"):
        print()
        print("CLAVES DETALLE:")
        keys = []
        for row in detail["rows"]:
            if isinstance(row, dict):
                for key in row:
                    if key not in keys:
                        keys.append(key)
        print(keys)

    if commands.get("rows"):
        print()
        print("CLAVES COMANDOS:")
        keys = []
        for row in commands["rows"]:
            if isinstance(row, dict):
                for key in row:
                    if key not in keys:
                        keys.append(key)
        print(keys)

        print()
        print("PRIMERAS 10 FILAS COMANDOS:")
        for row in commands["rows"][:10]:
            print(row)

    return {
        "detail": detail,
        "commands": commands,
    }


# ============================================================
# REPORTE COMANDOS PICKING
# ============================================================

REPORT_COMMANDS_URL = (
    f"{WMS_BASE_URL}/ReporteComandosShipunit2020.aspx"
)

REPORT_ORDER_FIELD = (
    "ctl00$placeHolderContent$ctPedido$textbox_control"
)

REPORT_SEARCH_BUTTON = (
    "ctl00$placeHolderContent$ControlCRUD$bBuscar$button"
)

REPORT_GRID_EVENTTARGET = (
    "ctl00$placeHolderContent$gv_principal"
)


def _extract_report_commands_grid(
    html: str,
) -> list[dict[str, str]]:
    """
    Extrae la grilla principal del reporte:
        ctl00_placeHolderContent_gv_principal
    """
    table = _find_table_by_id_contains(
        html,
        "gv_principal",
    )

    if table is None:
        return []

    rows = _parse_grid_table(table)

    # El GridView inserta una fila de paginación que nuestro parser puede
    # interpretar como {'col_0': '1 2'}. Solo conservamos filas de datos.
    clean_rows: list[dict[str, str]] = []

    for row in rows:
        pedido = _clean(row.get("Pedido"))
        producto = _clean(row.get("Producto"))

        if pedido or producto:
            clean_rows.append(row)

    return clean_rows


def _extract_report_page_numbers(
    html: str,
) -> list[int]:
    """
    Detecta páginas disponibles del GridView ASP.NET a partir de enlaces:
        __doPostBack('ctl00$placeHolderContent$gv_principal','Page$2')
    """
    soup = _soup(html)
    table = _find_table_by_id_contains(
        html,
        "gv_principal",
    )

    if table is None:
        return [1]

    pages = {1}

    for a in table.find_all("a"):
        href = str(a.get("href") or "")
        match = re.search(
            r"__doPostBack\('ctl00\$placeHolderContent\$gv_principal','Page\$(\d+)'\)",
            href,
            flags=re.IGNORECASE,
        )
        if match:
            pages.add(int(match.group(1)))

    return sorted(pages)


def _filter_report_rows_for_order(
    rows: list[dict[str, str]],
    order: str,
) -> list[dict[str, str]]:
    wanted = _clean(order)
    filtered: list[dict[str, str]] = []

    for row in rows:
        row_order = _clean(
            row.get("Pedido")
            or row.get("pedido")
        )

        # Si existe columna Pedido, exigimos coincidencia.
        if row_order and row_order != wanted:
            continue

        # Excluir cualquier fila residual que no sea de producto.
        producto = _clean(row.get("Producto"))
        if not producto:
            continue

        filtered.append(row)

    return filtered


def _aggregate_report_by_product(
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    Agrupa las filas del reporte por SKU sumando la columna Cantidad.
    Un SKU puede estar dividido entre varios contenedores/ubicaciones.
    """
    grouped: dict[str, dict[str, Any]] = {}

    for row in rows:
        sku = _clean(row.get("Producto"))
        if not sku:
            continue

        try:
            qty = float(
                str(row.get("Cantidad") or "0")
                .replace(".", "")
                .replace(",", ".")
            )
        except Exception:
            qty = 0.0

        if sku not in grouped:
            grouped[sku] = {
                "Producto": sku,
                "Descrip.": _clean(
                    row.get("Descrip.")
                    or row.get("Descripción")
                ),
                "Cantidad": 0.0,
                "Contenedores": set(),
                "Ubicaciones": set(),
            }

        grouped[sku]["Cantidad"] += qty

        cont = _clean(row.get("Cont."))
        if cont:
            grouped[sku]["Contenedores"].add(cont)

        ubic = _clean(
            row.get("Ubicación")
            or row.get("Ubicacion")
        )
        if ubic:
            grouped[sku]["Ubicaciones"].add(ubic)

    result: list[dict[str, Any]] = []

    for sku, item in grouped.items():
        qty = item["Cantidad"]

        if float(qty).is_integer():
            qty = int(qty)

        result.append(
            {
                "Producto": sku,
                "Descrip.": item["Descrip."],
                "Cantidad": qty,
                "Contenedores": sorted(item["Contenedores"]),
                "Ubicaciones": sorted(item["Ubicaciones"]),
            }
        )

    result.sort(key=lambda x: str(x["Producto"]))
    return result


def search_report_commands(
    order: str,
    *,
    save_html: bool = True,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Busca un pedido en ReporteComandosShipunit2020.aspx y recorre
    automáticamente todas las páginas del GridView.

    Devuelve:
      - rows: todas las filas físicas del reporte
      - grouped: filas agrupadas por SKU, sumando Cantidad
      - total_quantity: suma total de Cantidad de todas las páginas
      - pages_read: páginas efectivamente consultadas
    """
    wanted = _clean(order)

    if not wanted:
        return {
            "ok": False,
            "order": wanted,
            "rows": [],
            "grouped": [],
            "total_quantity": 0,
            "pages_read": [],
            "error": "El número de pedido está vacío.",
        }

    session = create_wms_session()

    try:
        # ----------------------------------------------------
        # 1. ABRIR REPORTE
        # ----------------------------------------------------
        response = session.get(
            REPORT_COMMANDS_URL,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        initial_html = response.text
        payload = _collect_form_payload(initial_html)

        if debug:
            print("===================================")
            print("REPORTE COMANDOS PICKING")
            print("===================================")
            print("GET STATUS:", response.status_code)
            print("GET URL:", response.url)
            print("GET HTML LEN:", len(initial_html))
            print("PAYLOAD BASE CAMPOS:", len(payload))

        # ----------------------------------------------------
        # 2. BUSCAR PEDIDO - PÁGINA 1
        # ----------------------------------------------------
        payload[REPORT_ORDER_FIELD] = wanted
        payload[REPORT_SEARCH_BUTTON] = ""
        payload["__EVENTTARGET"] = ""
        payload["__EVENTARGUMENT"] = ""

        response = session.post(
            REPORT_COMMANDS_URL,
            data=payload,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        current_html = response.text
        all_rows: list[dict[str, str]] = []
        pages_read: list[int] = []

        page1_rows = _filter_report_rows_for_order(
            _extract_report_commands_grid(current_html),
            wanted,
        )
        all_rows.extend(page1_rows)
        pages_read.append(1)

        if save_html:
            Path(
                f"wms_reporte_comandos_{wanted}_p1.html"
            ).write_text(
                current_html,
                encoding="utf-8",
            )

        pages = _extract_report_page_numbers(
            current_html,
        )

        if debug:
            print()
            print("POST STATUS:", response.status_code)
            print("POST URL:", response.url)
            print("POST HTML LEN:", len(current_html))
            print("PÁGINAS DETECTADAS:", pages)
            print("FILAS PÁGINA 1:", len(page1_rows))

        # ----------------------------------------------------
        # 3. RECORRER PÁGINAS 2..N MEDIANTE POSTBACK
        # ----------------------------------------------------
        for page_no in pages:
            if page_no == 1:
                continue

            page_payload = _collect_form_payload(
                current_html,
            )

            # Mantener filtro del pedido.
            page_payload[REPORT_ORDER_FIELD] = wanted

            # ASP.NET GridView paging.
            page_payload["__EVENTTARGET"] = (
                REPORT_GRID_EVENTTARGET
            )
            page_payload["__EVENTARGUMENT"] = (
                f"Page${page_no}"
            )

            # No reenviar botón Buscar durante el postback de página.
            page_payload.pop(
                REPORT_SEARCH_BUTTON,
                None,
            )

            page_response = session.post(
                REPORT_COMMANDS_URL,
                data=page_payload,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            page_response.raise_for_status()

            current_html = page_response.text

            page_rows = _filter_report_rows_for_order(
                _extract_report_commands_grid(
                    current_html,
                ),
                wanted,
            )

            all_rows.extend(page_rows)
            pages_read.append(page_no)

            if save_html:
                Path(
                    f"wms_reporte_comandos_{wanted}_p{page_no}.html"
                ).write_text(
                    current_html,
                    encoding="utf-8",
                )

            if debug:
                print(
                    f"FILAS PÁGINA {page_no}:",
                    len(page_rows),
                )

        # ----------------------------------------------------
        # 4. AGRUPAR POR SKU
        # ----------------------------------------------------
        grouped = _aggregate_report_by_product(
            all_rows,
        )

        total_quantity = 0.0

        for row in all_rows:
            try:
                qty = float(
                    str(row.get("Cantidad") or "0")
                    .replace(".", "")
                    .replace(",", ".")
                )
            except Exception:
                qty = 0.0

            total_quantity += qty

        if float(total_quantity).is_integer():
            total_quantity = int(total_quantity)

        headers: list[str] = []
        for row in all_rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)

        # ----------------------------------------------------
        # 5. DIAGNÓSTICO
        # ----------------------------------------------------
        if debug:
            print()
            print("===================================")
            print("RESULTADO TODAS LAS PÁGINAS")
            print("===================================")
            print("PÁGINAS LEÍDAS:", pages_read)
            print("FILAS TOTALES:", len(all_rows))
            print("CANTIDAD TOTAL REPORTE:", total_quantity)

            print()
            print("AGRUPADO POR SKU:")
            for item in grouped:
                print(item)

            print()
            print("PRIMERAS 30 FILAS FÍSICAS:")
            for row in all_rows[:30]:
                print(row)

        return {
            "ok": True,
            "order": wanted,
            "status_code": response.status_code,
            "url": response.url,
            "rows": all_rows,
            "grouped": grouped,
            "headers": headers,
            "total_quantity": total_quantity,
            "pages_read": pages_read,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "order": wanted,
            "status_code": None,
            "url": REPORT_COMMANDS_URL,
            "rows": [],
            "grouped": [],
            "headers": [],
            "total_quantity": 0,
            "pages_read": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    finally:
        session.close()


def inspect_report_commands(
    order: str = "0000120100",
) -> dict[str, Any]:
    print("===================================")
    print("PRUEBA REPORTE COMANDOS PICKING")
    print("===================================")
    print("PEDIDO:", order)

    result = search_report_commands(
        order=order,
        save_html=True,
        debug=True,
    )

    print()
    print("===================================")
    print("RESULTADO FINAL")
    print("===================================")
    print("OK:", result.get("ok"))
    print("PEDIDO:", result.get("order"))
    print("STATUS:", result.get("status_code"))
    print("PÁGINAS:", result.get("pages_read"))
    print("FILAS:", len(result.get("rows") or []))
    print(
        "CANTIDAD TOTAL:",
        result.get("total_quantity"),
    )
    print("ERROR:", result.get("error"))

    return result


# ============================================================
# REPORTE INVENTARIO - DISPONIBLE PARA VENTA
# ============================================================

INVENTORY_PRODUCT_FIELD = (
    "ctl00$placeHolderContent$ctProducto$textbox_control"
)

INVENTORY_PRODUCT_MODAL_F2 = (
    "ctl00$placeHolderContent$modal_producto$f2"
)

INVENTORY_SITE_FIELD = (
    "ctl00$placeHolderContent$ctSitio$textbox_control"
)

INVENTORY_SEARCH_BUTTON = (
    "ctl00$placeHolderContent$ControlCRUD$bBuscar$button"
)

INVENTORY_GRID_EVENTTARGET = (
    "ctl00$placeHolderContent$gv_principal"
)

INVENTORY_PAGE_SIZE_FIELD = (
    "ctl00$placeHolderContent$GridVIewControlTools$ddl_page_num"
)

INVENTORY_CHECKBOXES = (
    "ctl00$placeHolderContent$chDispVenta",
    "ctl00$placeHolderContent$chSinTrata",
    "ctl00$placeHolderContent$chDisponible",
    "ctl00$placeHolderContent$chTodoInv",
)


def _float_quantity(value: Any) -> float:
    raw = _clean(value)
    if not raw:
        return 0.0

    raw = raw.replace(".", "").replace(",", ".")

    try:
        return float(raw)
    except Exception:
        return 0.0


def _extract_inventory_grid(
    html: str,
) -> list[dict[str, str]]:
    """
    Extrae la grilla principal de ReporteInventario20SP.aspx.
    Excluye filas de paginación o filas sin producto.
    """
    table = _find_table_by_id_contains(
        html,
        "gv_principal",
    )

    if table is None:
        return []

    rows = _parse_grid_table(table)
    clean_rows: list[dict[str, str]] = []

    for row in rows:
        sku = _clean(
            row.get("Cod. Producto")
            or row.get("Producto")
        )

        if not sku:
            continue

        clean_rows.append(row)

    return clean_rows


def _extract_inventory_page_numbers(
    html: str,
) -> list[int]:
    """
    Detecta las páginas disponibles del GridView ASP.NET del reporte
    de inventario.
    """
    table = _find_table_by_id_contains(
        html,
        "gv_principal",
    )

    if table is None:
        return [1]

    pages = {1}

    for a in table.find_all("a"):
        href = str(a.get("href") or "")
        match = re.search(
            r"__doPostBack\('ctl00\$placeHolderContent\$gv_principal','Page\$(\d+)'\)",
            href,
            flags=re.IGNORECASE,
        )

        if match:
            pages.add(int(match.group(1)))

    return sorted(pages)


def _filter_inventory_rows_for_sku(
    rows: list[dict[str, str]],
    sku: str,
) -> list[dict[str, str]]:
    wanted = _clean(sku)
    filtered: list[dict[str, str]] = []

    for row in rows:
        row_sku = _clean(
            row.get("Cod. Producto")
            or row.get("Producto")
        )

        if row_sku != wanted:
            continue

        filtered.append(row)

    return filtered


def _normalize_inventory_row(
    row: dict[str, str],
) -> dict[str, Any]:
    qty = _float_quantity(row.get("Cantidad"))

    if float(qty).is_integer():
        qty = int(qty)

    return {
        "sku": _clean(
            row.get("Cod. Producto")
            or row.get("Producto")
        ),
        "descripcion": _clean(
            row.get("Descripción")
            or row.get("Descrip.")
        ),
        "ubicacion": _clean(
            row.get("Ubicación")
            or row.get("Ubicacion")
        ),
        "contenedor": _clean(row.get("Contenedor")),
        "cantidad": qty,
        "sitio": _clean(row.get("Sitio")),
        "ean": _clean(row.get("EAN")),
        "lote": _clean(row.get("Lote")),
        "fecha_expiracion": _clean(row.get("F. Expiración")),
        "tipo_tratamiento": _clean(row.get("Tipo Tratam.")),
        "bodega": _clean(row.get("Bodega")),
        "etiqueta": _clean(row.get("Etiqueta")),
        "zona": _clean(row.get("Zona")),
        "udm_1": _clean(row.get("UDM (1)")),
        "udm_2": _clean(row.get("UDM (2)")),
        "estado_1": _clean(row.get("Estado 1")),
        "estado_2": _clean(row.get("Estado 2")),
        "estado_3": _clean(row.get("Estado 3")),
        "raw": row,
    }


def _inventory_operational_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Devuelve solo inventario operativo.

    Bodega 25 se excluye expresamente porque es contable y no debe
    participar en Picking, Reposición, Abastecimiento ni Quiebre.
    """
    result: list[dict[str, Any]] = []

    for row in rows:
        bodega = _clean(row.get("bodega")).upper()

        if bodega == "25":
            continue

        result.append(row)

    return result


def search_inventory_available(
    sku: str,
    *,
    site: str = "CASA_MATRIZ",
    page_size: int = 1000,
    save_html: bool = False,
    debug: bool = False,
) -> dict[str, Any]:
    """
    Consulta ReporteInventario20SP.aspx usando los mismos filtros que el
    navegador para obtener el stock realmente Disponible para Venta.

    Filtros activados:
      - Disp. para Venta
      - Sin Tratam.
      - Disponible
      - Inv. Completo

    Retorna, entre otros:
      - rows: filas normalizadas del reporte
      - operational_rows: mismas filas excluyendo Bodega 25
      - total_available: total Disponible para Venta
      - total_operational: total operativo excluyendo Bodega 25
      - pages_read: páginas consultadas

    Importante:
      Esta función consulta disponibilidad. No clasifica por sí sola un SKU
      como Picking / Reposición / Abastecimiento / Quiebre.
    """
    wanted = _clean(sku)
    wanted_site = _clean(site) or "CASA_MATRIZ"

    if not wanted:
        return {
            "ok": False,
            "sku": wanted,
            "site": wanted_site,
            "rows": [],
            "operational_rows": [],
            "total_available": 0,
            "total_operational": 0,
            "pages_read": [],
            "error": "El SKU está vacío.",
        }

    session = create_wms_session()

    try:
        # ----------------------------------------------------
        # 1. ABRIR REPORTE INVENTARIO
        # ----------------------------------------------------
        response = session.get(
            INVENTORY_REPORT_URL,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        payload = _collect_form_payload(response.text)

        # ----------------------------------------------------
        # 2. REPRODUCIR EL POST VALIDADO EN NAVEGADOR
        # ----------------------------------------------------
        payload[INVENTORY_SITE_FIELD] = wanted_site
        payload[INVENTORY_PRODUCT_FIELD] = wanted
        payload[INVENTORY_PRODUCT_MODAL_F2] = wanted

        for checkbox_name in INVENTORY_CHECKBOXES:
            payload[checkbox_name] = "on"

        payload[INVENTORY_SEARCH_BUTTON] = ""
        payload["__EVENTTARGET"] = ""
        payload["__EVENTARGUMENT"] = ""

        # El navegador usa 10 por defecto, pero para integración conviene
        # reducir postbacks. El WMS ofrece 1000/5000 en este selector.
        if page_size not in {10, 20, 100, 1000, 5000}:
            page_size = 1000
        payload[INVENTORY_PAGE_SIZE_FIELD] = str(page_size)

        headers = {
            "Origin": WMS_BASE_URL.rsplit("/wms", 1)[0],
            "Referer": INVENTORY_REPORT_URL,
        }

        response = session.post(
            INVENTORY_REPORT_URL,
            data=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()

        current_html = response.text
        all_raw_rows: list[dict[str, str]] = []
        pages_read: list[int] = []

        page1_rows = _filter_inventory_rows_for_sku(
            _extract_inventory_grid(current_html),
            wanted,
        )
        all_raw_rows.extend(page1_rows)
        pages_read.append(1)

        if save_html:
            Path(
                f"wms_inventario_{wanted}_p1.html"
            ).write_text(
                current_html,
                encoding="utf-8",
            )

        pages = _extract_inventory_page_numbers(current_html)

        # ----------------------------------------------------
        # 3. RECORRER PAGINACIÓN SI EXISTE
        # ----------------------------------------------------
        for page_no in pages:
            if page_no == 1:
                continue

            page_payload = _collect_form_payload(current_html)

            page_payload[INVENTORY_SITE_FIELD] = wanted_site
            page_payload[INVENTORY_PRODUCT_FIELD] = wanted
            page_payload[INVENTORY_PRODUCT_MODAL_F2] = wanted
            page_payload[INVENTORY_PAGE_SIZE_FIELD] = str(page_size)

            for checkbox_name in INVENTORY_CHECKBOXES:
                page_payload[checkbox_name] = "on"

            page_payload["__EVENTTARGET"] = INVENTORY_GRID_EVENTTARGET
            page_payload["__EVENTARGUMENT"] = f"Page${page_no}"
            page_payload.pop(INVENTORY_SEARCH_BUTTON, None)

            page_response = session.post(
                INVENTORY_REPORT_URL,
                data=page_payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            page_response.raise_for_status()

            current_html = page_response.text

            page_rows = _filter_inventory_rows_for_sku(
                _extract_inventory_grid(current_html),
                wanted,
            )

            all_raw_rows.extend(page_rows)
            pages_read.append(page_no)

            if save_html:
                Path(
                    f"wms_inventario_{wanted}_p{page_no}.html"
                ).write_text(
                    current_html,
                    encoding="utf-8",
                )

        # ----------------------------------------------------
        # 4. NORMALIZAR Y TOTALIZAR
        # ----------------------------------------------------
        rows = [
            _normalize_inventory_row(row)
            for row in all_raw_rows
        ]

        operational_rows = _inventory_operational_rows(rows)

        total_available = sum(
            _float_quantity(row.get("cantidad"))
            for row in rows
        )

        total_operational = sum(
            _float_quantity(row.get("cantidad"))
            for row in operational_rows
        )

        if float(total_available).is_integer():
            total_available = int(total_available)

        if float(total_operational).is_integer():
            total_operational = int(total_operational)

        # Resumen por bodega.
        by_warehouse: dict[str, float] = {}
        for row in operational_rows:
            warehouse = _clean(row.get("bodega")) or "SIN_BODEGA"
            by_warehouse[warehouse] = (
                by_warehouse.get(warehouse, 0.0)
                + _float_quantity(row.get("cantidad"))
            )

        by_warehouse_clean: dict[str, int | float] = {}
        for warehouse, qty in by_warehouse.items():
            by_warehouse_clean[warehouse] = (
                int(qty) if float(qty).is_integer() else qty
            )

        if debug:
            print("===================================")
            print("REPORTE INVENTARIO DISPONIBLE")
            print("===================================")
            print("SKU:", wanted)
            print("SITIO:", wanted_site)
            print("STATUS:", response.status_code)
            print("PÁGINAS:", pages_read)
            print("FILAS:", len(rows))
            print("TOTAL DISPONIBLE:", total_available)
            print("TOTAL OPERATIVO:", total_operational)
            print("POR BODEGA:", by_warehouse_clean)
            print()
            for row in rows:
                print(row)

        return {
            "ok": True,
            "sku": wanted,
            "site": wanted_site,
            "status_code": response.status_code,
            "url": response.url,
            "rows": rows,
            "raw_rows": all_raw_rows,
            "operational_rows": operational_rows,
            "total_available": total_available,
            "total_operational": total_operational,
            "by_warehouse": by_warehouse_clean,
            "pages_read": pages_read,
            "error": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "sku": wanted,
            "site": wanted_site,
            "status_code": None,
            "url": INVENTORY_REPORT_URL,
            "rows": [],
            "raw_rows": [],
            "operational_rows": [],
            "total_available": 0,
            "total_operational": 0,
            "by_warehouse": {},
            "pages_read": [],
            "error": f"{type(exc).__name__}: {exc}",
        }

    finally:
        session.close()


def inspect_inventory_available(
    sku: str = "610444",
) -> dict[str, Any]:
    result = search_inventory_available(
        sku=sku,
        site="CASA_MATRIZ",
        page_size=1000,
        save_html=True,
        debug=True,
    )

    print()
    print("===================================")
    print("RESULTADO INVENTARIO")
    print("===================================")
    print("OK:", result.get("ok"))
    print("SKU:", result.get("sku"))
    print("TOTAL DISPONIBLE:", result.get("total_available"))
    print("TOTAL OPERATIVO:", result.get("total_operational"))
    print("ERROR:", result.get("error"))

    return result


# ============================================================
# PRUEBA DIRECTA
# ============================================================

if __name__ == "__main__":
    inspect_report_commands(
        order="0000120100",
    )
