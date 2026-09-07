

from datetime import datetime
from io import BytesIO
from pathlib import Path

import streamlit as st
from openpyxl import load_workbook

from config.settings import (
    ERP_SALES_FILE,
    ERP_SALES_META,
    MARKETPLACE_TEMPLATES,
)
from services.erp_sales import read_sales_source
from services.storage import save_source, load_source
from services.validation import validate_sales_source
from ui.components import render_html
from utils.numbers import format_clp


def _norm(value) -> str:
    if value is None:
        return ""

    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("_", "")
        .replace("-", "")
    )


def _headers(ws, row: int = 1) -> set[str]:
    return {
        _norm(cell.value)
        for cell in ws[row]
        if cell.value is not None
    }


def _validate_template(
    name: str,
    raw: bytes,
) -> tuple[bool, str]:

    try:
        wb = load_workbook(
            BytesIO(raw),
            read_only=True,
            data_only=False,
        )

    except Exception as exc:
        return False, f"No se pudo abrir el archivo: {exc}"

    if name == "Paris Marketplace":

        if "stock" not in wb.sheetnames:
            return (
                False,
                "La plantilla Paris debe contener la hoja 'stock'.",
            )

        headers = _headers(
            wb["stock"],
            1,
        )

        missing = {
            "skuseller",
            "nuevostock",
        } - headers

        if missing:
            return (
                False,
                "Faltan columnas: "
                + ", ".join(
                    sorted(missing)
                ),
            )

        return True, "Plantilla Paris válida."

    if name == "Mercado Libre":

        if "Publicaciones" not in wb.sheetnames:
            return (
                False,
                "La plantilla Mercado Libre debe contener "
                "la hoja 'Publicaciones'.",
            )

        # Algunas planillas MELI contienen metadata
        # antes de la fila real de encabezados.
        ws = wb["Publicaciones"]

        found = False

        for row in range(
            1,
            min(ws.max_row, 10) + 1,
        ):
            headers = _headers(
                ws,
                row,
            )

            required = {
                "familyid",
                "itemid",
                "productnumber",
                "variationid",
                "sku",
                "title",
                "variations",
                "quantity",
                "price",
                "currencyid",
                "condition",
                "shippingmethod",
                "listingtype",
                "feepersale",
                "status",
            }

            if required.issubset(headers):
                found = True
                break

        if not found:
            return (
                False,
                "La plantilla Mercado Libre no corresponde al archivo "
                "Publicaciones oficial o le faltan columnas obligatorias.",
            )

        return True, "Plantilla Mercado Libre válida."

    return False, "Marketplace no reconocido."


def _short_name(
    name: str,
) -> str:
    return (
        "Paris"
        if name == "Paris Marketplace"
        else "Mercado Libre"
    )


def _template_uploader_key(
    name: str,
    mode: str,
) -> str:
    """
    Genera una key versionada para cada uploader de plantilla.

    Esto evita que React/Streamlit intente reutilizar un nodo
    file_uploader que ya fue desmontado después de st.rerun().
    """
    state_key = (
        f"tpl3_upload_version_"
        f"{mode}_"
        f"{_norm(name)}"
    )

    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    return (
        f"tpl3_upload_"
        f"{mode}_"
        f"{name}_"
        f"{st.session_state[state_key]}"
    )


def _advance_template_uploader(
    name: str,
    mode: str,
) -> None:

    state_key = (
        f"tpl3_upload_version_"
        f"{mode}_"
        f"{_norm(name)}"
    )

    st.session_state[state_key] = (
        int(
            st.session_state.get(
                state_key,
                0,
            )
        )
        + 1
    )


def _template_meta_path(path: Path) -> Path:
    path = Path(path)
    return path.with_suffix(path.suffix + ".meta.json")


def _save_marketplace_template(
    *,
    name: str,
    path: Path,
    raw: bytes,
    original_filename: str,
) -> dict:
    """Guarda la plantilla de forma atómica y verifica la escritura."""
    meta_path = _template_meta_path(path)

    meta = save_source(
        raw,
        original_filename,
        path,
        meta_path,
        {
            "source": "marketplace_template",
            "marketplace": name,
        },
    )

    saved_raw, saved_meta = load_source(
        path,
        meta_path,
    )

    if saved_raw is None or saved_raw != raw:
        raise IOError(
            "La plantilla fue procesada, pero la verificación posterior "
            "no coincide con el archivo cargado."
        )

    return saved_meta or meta


def _render_template_card(
    name: str,
    path: Path,
):
    short = _short_name(
        name
    )

    exists = path.exists()

    status = (
        "ACTIVA"
        if exists
        else "NO CARGADA"
    )

    status_class = (
        "ok"
        if exists
        else "missing"
    )

    if exists:
        _, template_meta = load_source(
            path,
            _template_meta_path(path),
        )

        if template_meta:
            filename = template_meta.get(
                "filename",
                path.name,
            )
            loaded_at = template_meta.get(
                "loaded_at",
                "",
            )
            try:
                updated = datetime.fromisoformat(
                    loaded_at
                ).strftime(
                    "%d/%m/%Y %H:%M"
                )
            except Exception:
                updated = datetime.fromtimestamp(
                    path.stat().st_mtime
                ).strftime(
                    "%d/%m/%Y %H:%M"
                )
        else:
            updated = datetime.fromtimestamp(
                path.stat().st_mtime
            ).strftime(
                "%d/%m/%Y %H:%M"
            )
            filename = path.name

    else:
        updated = "—"
        filename = "Sin archivo"

    render_html(
        f"""
        <div class="tpl3-card">
            <div class="tpl3-top">
                <div>
                    <div class="tpl3-name">
                        {short}
                    </div>
                    <div class="tpl3-file">
                        {filename}
                    </div>
                </div>

                <div class="tpl3-status {status_class}">
                    {status}
                </div>
            </div>

            <div class="tpl3-date">
                Actualizada: {updated}
            </div>
        </div>
        """
    )

    if exists:

        c1, c2 = st.columns(
            2,
            gap="small",
        )

        with c1:
            with st.popover(
                "Reemplazar",
                use_container_width=True,
                icon=":material/upload_file:",
            ):
                uploaded = st.file_uploader(
                    f"Nueva plantilla {short}",
                    type=["xlsx"],
                    key=_template_uploader_key(
                        name,
                        "replace",
                    ),
                    label_visibility="collapsed",
                )

                if uploaded is not None:
                    raw = uploaded.getvalue()
                    valid, message = _validate_template(
                        name,
                        raw,
                    )

                    if not valid:
                        st.error(message)
                    else:
                        st.success(
                            f"✓ {uploaded.name} validada."
                        )

                        if st.button(
                            "Guardar plantilla",
                            type="primary",
                            use_container_width=True,
                            key=f"tpl3_save_{_norm(name)}",
                        ):
                            try:
                                meta = _save_marketplace_template(
                                    name=name,
                                    path=path,
                                    raw=raw,
                                    original_filename=uploaded.name,
                                )

                                st.cache_data.clear()
                                _advance_template_uploader(
                                    name,
                                    "replace",
                                )
                                st.session_state[
                                    "tpl3_flash_success"
                                ] = (
                                    f"✓ {short} actualizada con "
                                    f"{meta.get('filename', uploaded.name)}."
                                )
                                st.rerun()

                            except Exception as exc:
                                st.error(
                                    "No fue posible guardar la plantilla: "
                                    f"{exc}"
                                )

        with c2:
            try:
                st.download_button(
                    "Descargar",
                    data=path.read_bytes(),
                    file_name=filename,
                    mime=(
                        "application/vnd.openxmlformats-"
                        "officedocument.spreadsheetml.sheet"
                    ),
                    use_container_width=True,
                    icon=":material/download:",
                    key=f"tpl3_download_{name}",
                )
            except Exception as exc:
                st.warning(
                    "No fue posible leer "
                    f"la plantilla: {exc}"
                )

    else:
        uploaded = st.file_uploader(
            f"Cargar plantilla {short}",
            type=["xlsx"],
            key=_template_uploader_key(
                name,
                "missing",
            ),
        )

        if uploaded is not None:
            raw = uploaded.getvalue()
            valid, message = _validate_template(
                name,
                raw,
            )

            if not valid:
                st.error(message)
            else:
                st.success(
                    f"✓ {uploaded.name} validada."
                )

                if st.button(
                    "Guardar plantilla",
                    type="primary",
                    use_container_width=True,
                    key=f"tpl3_save_missing_{_norm(name)}",
                ):
                    try:
                        meta = _save_marketplace_template(
                            name=name,
                            path=path,
                            raw=raw,
                            original_filename=uploaded.name,
                        )
                        st.cache_data.clear()
                        _advance_template_uploader(
                            name,
                            "missing",
                        )
                        st.session_state[
                            "tpl3_flash_success"
                        ] = (
                            f"✓ {short} asociada con "
                            f"{meta.get('filename', uploaded.name)}."
                        )
                        st.rerun()

                    except Exception as exc:
                        st.error(
                            "No fue posible guardar la plantilla: "
                            f"{exc}"
                        )



def _sales_uploader_key() -> str:
    """
    File uploader versionado para ERP Ventas.

    Evita errores React del tipo:
    removeChild: el nodo no es un hijo de este nodo
    después de guardar + st.rerun().
    """

    if "tpl3_sales_version" not in st.session_state:
        st.session_state[
            "tpl3_sales_version"
        ] = 0

    return (
        "tpl3_sales_"
        f"{st.session_state['tpl3_sales_version']}"
    )


def _advance_sales_uploader() -> None:
    st.session_state[
        "tpl3_sales_version"
    ] = (
        int(
            st.session_state.get(
                "tpl3_sales_version",
                0,
            )
        )
        + 1
    )


def _render_sales_source():

    _, meta = load_source(
        ERP_SALES_FILE,
        ERP_SALES_META,
    )

    if meta:

        st.success(
            "Fuente activa: "
            f"{meta.get('filename', 'ERP Ventas')} · "
            f"{meta.get('loaded_at', '')}"
        )

    else:

        st.info(
            "Aún no existe una fuente "
            "ERP Ventas guardada."
        )

    uploaded = st.file_uploader(
        "Cargar / reemplazar ERP Ventas",
        type=[
            "csv",
            "xls",
            "xlsx",
        ],
        key=_sales_uploader_key(),
    )

    if uploaded is not None:

        try:

            raw = uploaded.getvalue()

            df = read_sales_source(
                raw,
                uploaded.name,
            )

            info = validate_sales_source(
                df
            )

            save_source(
                raw,
                uploaded.name,
                ERP_SALES_FILE,
                ERP_SALES_META,
                info,
            )

            st.cache_data.clear()

            st.success(
                "✓ ERP Ventas actualizado · "
                f"{info['commercial_rows']:,} documentos · "
                f"{info['min_date']} → {info['max_date']} · "
                f"{format_clp(info['net_sales_with_vat'])}"
            )

            # Fuerza un uploader nuevo en el siguiente render.
            _advance_sales_uploader()

            st.rerun()

        except Exception as exc:

            st.error(
                f"Error cargando ERP Ventas: {exc}"
            )


def render(ctx):

    render_html(
        """
        <div class="tpl3-head">
            <div class="tpl3-title">
                Plantillas
            </div>

            <div class="tpl3-subtitle">
                Archivos base utilizados para generar
                las actualizaciones de Marketplace.
            </div>
        </div>

        <div class="tpl3-source">
            <strong>
                Stock Marketplace
            </strong>

            <span>
                Automático desde Llegadas_OK ·
                solo Casa Matriz.
                Aquí solo administras las plantillas.
            </span>
        </div>
        """
    )

    flash_success = st.session_state.pop(
        "tpl3_flash_success",
        None,
    )
    if flash_success:
        st.success(flash_success)

    paris_path = (
        MARKETPLACE_TEMPLATES.get(
            "Paris Marketplace"
        )
    )

    meli_path = (
        MARKETPLACE_TEMPLATES.get(
            "Mercado Libre"
        )
    )

    c1, c2 = st.columns(
        2,
        gap="medium",
    )

    with c1:

        if paris_path is None:
            st.error(
                "Paris no está configurado."
            )

        else:
            _render_template_card(
                "Paris Marketplace",
                paris_path,
            )

    with c2:

        if meli_path is None:
            st.error(
                "Mercado Libre no está configurado."
            )

        else:
            _render_template_card(
                "Mercado Libre",
                meli_path,
            )

    st.markdown("")

    with st.expander(
        "Fuente ERP Ventas",
        expanded=False,
    ):

        st.caption(
            "Usada por Métricas Vendedores, "
            "Resumen Ejecutivo y CRM. "
            "No interviene en el stock de Marketplace."
        )

        _render_sales_source()
