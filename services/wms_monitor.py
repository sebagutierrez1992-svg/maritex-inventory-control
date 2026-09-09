from __future__ import annotations

import base64
import gzip
import json
import os
import random
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


DEFAULT_SIGNALR_BASE = os.getenv(
    "WMS_SIGNALR_BASE",
    "http://104.45.239.215:331/signalr",
).rstrip("/")

DEFAULT_HUB_NAME = os.getenv(
    "WMS_SIGNALR_HUB",
    "scoreshub",
).strip().lower()

CLIENT_PROTOCOL = "1.5"


@dataclass
class WMSMonitorResult:
    ok: bool
    detail: dict[str, Any]
    operational: dict[str, Any]
    messages_seen: int
    source: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "detail": self.detail,
            "operational": self.operational,
            "messages_seen": self.messages_seen,
            "source": self.source,
            "error": self.error,
        }


def decode_compressed_payload(value: str) -> dict[str, Any]:
    """
    Decodifica los argumentos enviados por ScoresHub:
    Base64 -> GZIP -> UTF-8 -> JSON.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Payload vacío o inválido.")

    text = value.strip().strip('"')
    raw = base64.b64decode(text)
    decompressed = gzip.decompress(raw)
    decoded = decompressed.decode("utf-8-sig")
    payload = json.loads(decoded)

    if not isinstance(payload, dict):
        raise ValueError("El payload WMS no devolvió un objeto JSON.")

    return payload


def classify_payload(payload: dict[str, Any]) -> str:
    """
    detail:
        {"PICK": [...]}

    operational:
        {"PICK1": [...], ..., "PICK7": [...]}
    """
    if "PICK" in payload and isinstance(payload.get("PICK"), list):
        return "detail"

    if any(
        key.startswith("PICK") and key != "PICK"
        for key in payload.keys()
    ):
        return "operational"

    return "unknown"


def _coerce_signalr_message(message: Any) -> dict[str, Any]:
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")

    if isinstance(message, str):
        message = message.strip()
        if not message:
            return {}
        try:
            parsed = json.loads(message)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    return message if isinstance(message, dict) else {}


def extract_monitor_payloads(message: Any) -> list[tuple[str, dict[str, Any]]]:
    """
    Extrae argumentos comprimidos de mensajes SignalR como:

    {
        "C": "...",
        "M": [
            {
                "H": "ScoresHub",
                "M": "GetPedidosDespachoInfoDetalladaListCompressed",
                "A": ["H4sIA..."]
            }
        ]
    }
    """
    envelope = _coerce_signalr_message(message)
    calls = envelope.get("M")

    if not isinstance(calls, list):
        return []

    found: list[tuple[str, dict[str, Any]]] = []

    for call in calls:
        if not isinstance(call, dict):
            continue

        method = str(call.get("M") or "")
        args = call.get("A")

        if not isinstance(args, list):
            continue

        for arg in args:
            if not isinstance(arg, str):
                continue

            # Los payloads observados comienzan con H4sI (GZIP en Base64).
            if not arg.strip().startswith("H4sI"):
                continue

            try:
                payload = decode_compressed_payload(arg)
            except Exception:
                continue

            found.append((method, payload))

    return found


def decode_snapshot(value: str) -> dict[str, Any]:
    """
    Permite probar manualmente un H4sIA... capturado desde DevTools.
    """
    return decode_compressed_payload(value)


def _connection_data(hub_name: str) -> str:
    return json.dumps(
        [{"name": hub_name}],
        separators=(",", ":"),
    )


def _negotiate(
    session: requests.Session,
    base_url: str,
    hub_name: str,
    timeout: float,
) -> dict[str, Any]:
    response = session.get(
        f"{base_url}/negotiate",
        params={
            "clientProtocol": CLIENT_PROTOCOL,
            "connectionData": _connection_data(hub_name),
            "_": random.randint(1_000_000_000_000, 9_999_999_999_999),
        },
        timeout=timeout,
    )
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Respuesta negotiate inválida.")

    if not data.get("ConnectionToken"):
        raise RuntimeError("SignalR no entregó ConnectionToken.")

    return data


def _transport_params(
    connection_token: str,
    hub_name: str,
) -> dict[str, str]:
    return {
        "transport": "longPolling",
        "clientProtocol": CLIENT_PROTOCOL,
        "connectionToken": connection_token,
        "connectionData": _connection_data(hub_name),
        "_": str(random.randint(1_000_000_000_000, 9_999_999_999_999)),
    }


def _connect_long_polling(
    session: requests.Session,
    base_url: str,
    connection_token: str,
    hub_name: str,
    timeout: float,
) -> dict[str, Any]:
    response = session.get(
        f"{base_url}/connect",
        params=_transport_params(connection_token, hub_name),
        timeout=timeout,
    )
    response.raise_for_status()
    return _coerce_signalr_message(response.text)


def _start(
    session: requests.Session,
    base_url: str,
    connection_token: str,
    hub_name: str,
    timeout: float,
) -> dict[str, Any]:
    response = session.get(
        f"{base_url}/start",
        params=_transport_params(connection_token, hub_name),
        timeout=timeout,
    )
    response.raise_for_status()

    try:
        data = response.json()
    except Exception:
        data = {}

    if isinstance(data, dict):
        return data

    return {}


def _poll(
    session: requests.Session,
    base_url: str,
    connection_token: str,
    hub_name: str,
    cursor: str | None,
    groups_token: str | None,
    timeout: float,
) -> dict[str, Any]:
    params = _transport_params(
        connection_token,
        hub_name,
    )

    if cursor:
        params["messageId"] = cursor

    if groups_token:
        params["groupsToken"] = groups_token

    response = session.get(
        f"{base_url}/poll",
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    return _coerce_signalr_message(response.text)


def _consume_message(
    message: dict[str, Any],
    detail: dict[str, Any],
    operational: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    decoded_count = 0

    for _method, payload in extract_monitor_payloads(message):
        kind = classify_payload(payload)

        if kind == "detail":
            detail = payload
            decoded_count += 1

        elif kind == "operational":
            operational = payload
            decoded_count += 1

    return detail, operational, decoded_count


def load_wms_monitor(
    *,
    base_url: str = DEFAULT_SIGNALR_BASE,
    hub_name: str = DEFAULT_HUB_NAME,
    timeout: float = 8.0,
    max_polls: int = 5,
) -> dict[str, Any]:
    """
    Intenta leer el monitor WMS mediante ASP.NET SignalR clásico.

    Usa longPolling para evitar agregar una dependencia WebSocket al proyecto.
    La función no reutiliza ni persiste connectionToken: negocia uno nuevo
    en cada ejecución.

    Retorna:
        {
            "ok": bool,
            "detail": {"PICK": [...]},
            "operational": {"PICK1": [...], ...},
            "messages_seen": int,
            "source": "...",
            "error": str | None,
        }
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Maritex-Monitor/1.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
    )

    detail: dict[str, Any] = {}
    operational: dict[str, Any] = {}
    messages_seen = 0

    try:
        negotiate = _negotiate(
            session,
            base_url,
            hub_name,
            timeout,
        )

        token = str(negotiate["ConnectionToken"])

        first = _connect_long_polling(
            session,
            base_url,
            token,
            hub_name,
            timeout,
        )
        messages_seen += 1

        detail, operational, _ = _consume_message(
            first,
            detail,
            operational,
        )

        _start(
            session,
            base_url,
            token,
            hub_name,
            timeout,
        )

        cursor = first.get("C")
        groups_token = first.get("G")

        # El connect inicial puede traer un snapshot que queda inmediatamente
        # superado por el siguiente broadcast del monitor. No cortamos apenas
        # aparecen detail + operational: esperamos al menos un NUEVO payload
        # detail después de tener ambos, y siempre conservamos el último recibido.
        complete_seen = bool(detail and operational)

        for _ in range(max(0, int(max_polls))):
            message = _poll(
                session,
                base_url,
                token,
                hub_name,
                cursor,
                groups_token,
                timeout,
            )
            messages_seen += 1

            if message.get("C"):
                cursor = message.get("C")

            if message.get("G"):
                groups_token = message.get("G")

            payloads = extract_monitor_payloads(message)
            has_new_detail = any(
                classify_payload(payload) == "detail"
                for _method, payload in payloads
            )

            detail, operational, _ = _consume_message(
                message,
                detail,
                operational,
            )

            if detail and operational:
                if complete_seen and has_new_detail:
                    break
                complete_seen = True

        ok = bool(detail or operational)

        return WMSMonitorResult(
            ok=ok,
            detail=detail,
            operational=operational,
            messages_seen=messages_seen,
            source=f"{base_url} · {hub_name}",
            error=None if ok else (
                "SignalR respondió, pero no se recibió todavía un payload "
                "GetPedidosDespachoInfoDetalladaListCompressed."
            ),
        ).as_dict()

    except Exception as exc:
        return WMSMonitorResult(
            ok=False,
            detail={},
            operational={},
            messages_seen=messages_seen,
            source=f"{base_url} · {hub_name}",
            error=f"{type(exc).__name__}: {exc}",
        ).as_dict()

    finally:
        session.close()


# ---------------------------------------------------------------------------
# Detalle de líneas/productos por pedido
# ---------------------------------------------------------------------------

ORDER_LINES_PATH = (
    "/wms/webservices/getAsyncAutocomplete.asmx/"
    "GetMonitorPedidoDetalleComandosPICK"
)


def _extract_asmx_rows(payload):
    """Normaliza la respuesta ASP.NET ASMX {d: '[...]'} a list[dict]."""
    if payload is None:
        return []

    data = payload

    if isinstance(data, dict) and "d" in data:
        data = data.get("d")

    if isinstance(data, str):
        raw = data.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []

    if isinstance(data, dict):
        for key in ("rows", "data", "result", "items"):
            value = data.get(key)
            if isinstance(value, list):
                data = value
                break

    if not isinstance(data, list):
        return []

    return [row for row in data if isinstance(row, dict)]


def get_order_lines(
    ob_oid,
    ob_type,
    sitio,
    cliente,
    dest="ALL",
    timeout=12,
):
    """
    Consulta las líneas reales del pedido en el webservice usado por el WMS.

    Devuelve:
      {
        "ok": bool,
        "rows": list[dict],
        "error": str | None,
        "status_code": int | None,
      }

    No infiere quiebre: solo devuelve datos reales de la línea.
    """
    url = f"http://104.45.239.215{ORDER_LINES_PATH}"

    body = {
        "ob_oid": str(ob_oid or ""),
        "ob_type": str(ob_type or ""),
        "sitio": str(sitio or ""),
        "cliente": str(cliente or ""),
        "strsessid": "1111111999991",
        "dest": str(dest or "ALL"),
    }

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": (
            "http://104.45.239.215/wms/"
            "form_monitor_visor_online_especial_operadores_detalle.aspx"
        ),
    }

    try:
        response = requests.post(
            url,
            json=body,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "rows": [],
                "error": f"HTTP {response.status_code}",
                "status_code": response.status_code,
            }

        try:
            payload = response.json()
        except Exception as exc:
            return {
                "ok": False,
                "rows": [],
                "error": f"Respuesta no JSON: {exc}",
                "status_code": response.status_code,
            }

        rows = _extract_asmx_rows(payload)

        return {
            "ok": True,
            "rows": rows,
            "error": None,
            "status_code": response.status_code,
        }

    except Exception as exc:
        return {
            "ok": False,
            "rows": [],
            "error": str(exc),
            "status_code": None,
        }
