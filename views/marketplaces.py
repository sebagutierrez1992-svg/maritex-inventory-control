from io import BytesIO
import re

import pandas as pd
import streamlit as st
from openpyxl import load_workbook

from analytics.stock_metrics import (
    stock_view,
    consolidate_inventory,
)
from config.settings import MARKETPLACE_TEMPLATES
from ui.components import render_html


# ============================================================
# HELPERS GENERALES
# ============================================================

def _safe_int(value) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def _normalize_sku(value) -> str:
    """
    Normaliza SKU para permitir cruces entre formatos como:

    ERP:
        13051205

    Paris:
        1305120-5

    Ambos quedan como:
        13051205

    También corrige casos tipo:
        200122.0 -> 200122
    """
    if value is None:
        return ""

    text = str(value).strip().upper()

    if not text:
        return ""

    # Excel a veces convierte códigos numéricos en texto con .0
    text = re.sub(
        r"\.0$",
        "",
        text,
    )

    # Dejar únicamente letras y números.
    text = re.sub(
        r"[^A-Z0-9]",
        "",
        text,
    )

    return text


def _prepare_house_stock(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Obtiene exclusivamente CASA MATRIZ.

    Orden correcto:
        ERP Stock
        -> normalizar
        -> filtrar Casa Matriz
        -> consolidar SKU

    IMPORTANTE:
    Nunca consolidamos todas las bodegas antes de filtrar.
    """

    stock = stock_view(df)

    if stock.empty:
        return pd.DataFrame()

    warehouse = (
        stock["Bodega"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    house = stock[
        warehouse.str.contains(
            "CASA MATRIZ",
            regex=False,
        )
    ].copy()

    if house.empty:
        return pd.DataFrame()

    # Consolidar solamente las filas de Casa Matriz.
    house = consolidate_inventory(
        house
    )

    # Código normalizado para cruce contra marketplaces.
    house["_sku_match"] = (
        house["Código"]
        .map(_normalize_sku)
    )

    # Eliminar eventuales filas sin código.
    house = house[
        house["_sku_match"].ne("")
    ].copy()

    # Si por algún motivo quedara un código duplicado,
    # consolidamos nuevamente por código normalizado.
    if house["_sku_match"].duplicated().any():
        grouped = (
            house.groupby(
                "_sku_match",
                as_index=False,
            )
            .agg(
                Código=("Código", "first"),
                Producto=("Producto", "first"),
                Disponible=("Disponible", "sum"),
                **{
                    "Stock físico": (
                        "Stock físico",
                        "sum",
                    ),
                    "Por llegar": (
                        "Por llegar",
                        "sum",
                    ),
                    "Por despachar": (
                        "Por despachar",
                        "sum",
                    ),
                },
            )
        )

        house = grouped

    # Texto auxiliar para búsqueda.
    house["_search_codigo"] = (
        house["Código"]
        .fillna("")
        .astype(str)
        .str.lower()
    )

    house["_search_producto"] = (
        house["Producto"]
        .fillna("")
        .astype(str)
        .str.lower()
    )

    return house.reset_index(
        drop=True
    )


def _stock_map(
    house: pd.DataFrame,
    reserve: int,
) -> dict:
    """
    Genera:
        SKU normalizado -> stock marketplace

    Regla:
        max(Disponible Casa Matriz - Reserva, 0)
    """

    available = pd.to_numeric(
        house["Disponible"],
        errors="coerce",
    ).fillna(0)

    publishable = (
        available
        - int(reserve)
    ).clip(
        lower=0
    ).round().astype(int)

    return dict(
        zip(
            house["_sku_match"],
            publishable,
        )
    )


def _find_header_column(
    ws,
    row_number: int,
    expected_names,
):
    """
    Encuentra columna por nombre, tolerando espacios,
    mayúsculas, guiones y underscore.
    """

    expected = {
        re.sub(
            r"[^A-Z0-9]",
            "",
            str(name).upper(),
        )
        for name in expected_names
    }

    for cell in ws[row_number]:
        value = cell.value

        if value is None:
            continue

        normalized = re.sub(
            r"[^A-Z0-9]",
            "",
            str(value).strip().upper(),
        )

        if normalized in expected:
            return cell.column

    return None


# ============================================================
# PARIS
# ============================================================

@st.cache_data(
    show_spinner=False,
)
def _build_paris_workbook(
    template_bytes: bytes,
    stock_items: tuple,
):
    """
    Conserva la plantilla Paris original.

    Hoja:
        stock

    Cruce:
        sku_seller

    Actualiza:
        nuevo_stock
    """

    stock_lookup = dict(
        stock_items
    )

    wb = load_workbook(
        BytesIO(template_bytes)
    )

    if "stock" not in wb.sheetnames:
        raise ValueError(
            "La plantilla Paris no contiene la hoja 'stock'."
        )

    ws = wb["stock"]

    sku_col = _find_header_column(
        ws,
        1,
        [
            "sku_seller",
            "sku seller",
        ],
    )

    target_col = _find_header_column(
        ws,
        1,
        [
            "nuevo_stock",
            "nuevo stock",
        ],
    )

    current_stock_col = _find_header_column(
        ws,
        1,
        [
            "stock",
        ],
    )

    title_col = _find_header_column(
        ws,
        1,
        [
            "titulo",
            "título",
        ],
    )

    size_col = _find_header_column(
        ws,
        1,
        [
            "talla",
        ],
    )

    mkp_col = _find_header_column(
        ws,
        1,
        [
            "sku_mkp",
            "sku mkp",
        ],
    )

    if sku_col is None:
        raise ValueError(
            "No se encontró la columna 'sku_seller' "
            "en la plantilla Paris."
        )

    if target_col is None:
        raise ValueError(
            "No se encontró la columna 'nuevo_stock' "
            "en la plantilla Paris."
        )

    preview_rows = []

    matched_rows = 0
    unmatched_rows = 0
    publishable_units = 0
    processed_rows = 0

    matched_skus = set()
    unmatched_skus = set()

    for row in range(
        2,
        ws.max_row + 1,
    ):
        raw_sku = ws.cell(
            row=row,
            column=sku_col,
        ).value

        if raw_sku is None:
            continue

        sku_text = str(
            raw_sku
        ).strip()

        if not sku_text:
            continue

        processed_rows += 1

        sku_key = _normalize_sku(
            raw_sku
        )

        found = (
            sku_key in stock_lookup
        )

        new_stock = int(
            stock_lookup.get(
                sku_key,
                0,
            )
        )

        # Actualizar SOLAMENTE nuevo_stock.
        ws.cell(
            row=row,
            column=target_col,
        ).value = new_stock

        if found:
            matched_rows += 1
            matched_skus.add(
                sku_key
            )
        else:
            unmatched_rows += 1
            unmatched_skus.add(
                sku_key
            )

        publishable_units += (
            new_stock
        )

        preview_rows.append(
            {
                "SKU Marketplace": (
                    ws.cell(
                        row=row,
                        column=mkp_col,
                    ).value
                    if mkp_col
                    else ""
                ),
                "SKU Seller": sku_text,
                "Producto": (
                    ws.cell(
                        row=row,
                        column=title_col,
                    ).value
                    if title_col
                    else ""
                ),
                "Talla": (
                    ws.cell(
                        row=row,
                        column=size_col,
                    ).value
                    if size_col
                    else ""
                ),
                "Stock actual": (
                    ws.cell(
                        row=row,
                        column=current_stock_col,
                    ).value
                    if current_stock_col
                    else ""
                ),
                "Nuevo stock": (
                    new_stock
                ),
                "Coincidencia ERP": (
                    "Encontrado"
                    if found
                    else "Sin coincidencia"
                ),
            }
        )

    output = BytesIO()

    wb.save(
        output
    )

    output.seek(0)

    stats = {
        "rows": processed_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "matched_skus": len(matched_skus),
        "unmatched_skus": len(unmatched_skus),
        "units": publishable_units,
    }

    return (
        output.getvalue(),
        pd.DataFrame(
            preview_rows
        ),
        stats,
    )


# ============================================================
# MERCADO LIBRE
# ============================================================

@st.cache_data(
    show_spinner=False,
)
def _build_meli_workbook(
    template_bytes: bytes,
    stock_items: tuple,
):
    """
    Conserva el archivo Mercado Libre completo:

        Ayuda
        hidden
        Publicaciones

    En Publicaciones:

        SKU       -> columna de cruce
        QUANTITY  -> Stock en tu depósito

    Los datos comienzan desde fila 6.
    """

    stock_lookup = dict(
        stock_items
    )

    wb = load_workbook(
        BytesIO(template_bytes)
    )

    if "Publicaciones" not in wb.sheetnames:
        raise ValueError(
            "La plantilla Mercado Libre no contiene "
            "la hoja 'Publicaciones'."
        )

    ws = wb["Publicaciones"]

    # Encabezados técnicos de MELI están en fila 1.
    sku_col = _find_header_column(
        ws,
        1,
        [
            "SKU",
        ],
    )

    quantity_col = _find_header_column(
        ws,
        1,
        [
            "QUANTITY",
        ],
    )

    title_col = _find_header_column(
        ws,
        1,
        [
            "TITLE",
        ],
    )

    variation_col = _find_header_column(
        ws,
        1,
        [
            "VARIATIONS",
        ],
    )

    item_col = _find_header_column(
        ws,
        1,
        [
            "ITEM_ID",
        ],
    )

    if sku_col is None:
        raise ValueError(
            "No se encontró la columna 'SKU' "
            "en la plantilla Mercado Libre."
        )

    if quantity_col is None:
        raise ValueError(
            "No se encontró la columna 'QUANTITY' "
            "en la plantilla Mercado Libre."
        )

    preview_rows = []

    matched_rows = 0
    unmatched_rows = 0
    publishable_units = 0
    processed_rows = 0

    matched_skus = set()
    unmatched_skus = set()

    # La plantilla real comienza en fila 6.
    for row in range(
        6,
        ws.max_row + 1,
    ):
        raw_sku = ws.cell(
            row=row,
            column=sku_col,
        ).value

        if raw_sku is None:
            continue

        sku_text = str(
            raw_sku
        ).strip()

        if not sku_text:
            continue

        processed_rows += 1

        sku_key = _normalize_sku(
            raw_sku
        )

        found = (
            sku_key in stock_lookup
        )

        new_stock = int(
            stock_lookup.get(
                sku_key,
                0,
            )
        )

        # Actualizar únicamente QUANTITY.
        ws.cell(
            row=row,
            column=quantity_col,
        ).value = new_stock

        if found:
            matched_rows += 1
            matched_skus.add(
                sku_key
            )
        else:
            unmatched_rows += 1
            unmatched_skus.add(
                sku_key
            )

        publishable_units += (
            new_stock
        )

        # ====================================================
        # PRODUCTO / TITLE REAL
        # ====================================================
        raw_title = (
            ws.cell(
                row=row,
                column=title_col,
            ).value
            if title_col
            else ""
        )

        product_title = raw_title or ""

        # Mercado Libre utiliza fórmulas para repetir el
        # título del producto padre en las variaciones.
        #
        # Ejemplo:
        # ="     "&F6
        #
        # En ese caso buscamos hacia arriba el último TITLE
        # que sea texto real y no una fórmula.
        if (
            title_col
            and isinstance(raw_title, str)
            and raw_title.strip().startswith("=")
        ):
            for previous_row in range(
                row - 1,
                5,
                -1,
            ):
                previous_title = ws.cell(
                    row=previous_row,
                    column=title_col,
                ).value

                if previous_title is None:
                    continue

                previous_title = str(
                    previous_title
                ).strip()

                if not previous_title:
                    continue

                # Ignorar otras fórmulas.
                if previous_title.startswith("="):
                    continue

                product_title = previous_title
                break

        preview_rows.append(
            {
                "Publicación": (
                    ws.cell(
                        row=row,
                        column=item_col,
                    ).value
                    if item_col
                    else ""
                ),
                "SKU": sku_text,
                "Producto": product_title,
                "Variación": (
                    ws.cell(
                        row=row,
                        column=variation_col,
                    ).value
                    if variation_col
                    else ""
                ),
                "Stock actualizado": (
                    new_stock
                ),
                "Coincidencia ERP": (
                    "Encontrado"
                    if found
                    else "Sin coincidencia"
                ),
            }
        )

    output = BytesIO()

    wb.save(
        output
    )

    output.seek(0)

    stats = {
        "rows": processed_rows,
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "matched_skus": len(matched_skus),
        "unmatched_skus": len(unmatched_skus),
        "units": publishable_units,
    }

    return (
        output.getvalue(),
        pd.DataFrame(
            preview_rows
        ),
        stats,
    )


# ============================================================
# PANEL MARKETPLACE
# ============================================================

def _render_marketplace_panel(
    name: str,
    key_name: str,
    house: pd.DataFrame,
):
    path = MARKETPLACE_TEMPLATES[
        name
    ]

    if not path.exists():
        render_html(
            f"""
            <div class="market-v60-card">
                <div>
                    <strong>
                        {name}
                    </strong>
                    <span>
                        Plantilla pendiente
                    </span>
                </div>

                <div class="market-v60-badge">
                    Casa Matriz
                </div>
            </div>
            """
        )

        st.warning(
            f"No existe la plantilla oficial de {name}. "
            "Cárgala desde Plantillas."
        )

        return

    render_html(
        f"""
        <div class="market-v60-card">

            <div>
                <strong>
                    {name}
                </strong>

                <span>
                    Plantilla oficial disponible ·
                    {path.name}
                </span>
            </div>

            <div class="market-v60-badge">
                Casa Matriz
            </div>

        </div>
        """
    )

    # ========================================================
    # CONTROLES
    # ========================================================
    c1, c2 = st.columns(
        [1.4, 1]
    )

    with c1:
        search = st.text_input(
            "Buscar SKU",
            placeholder=(
                "Buscar código o producto"
            ),
            key=f"market_search_real_{key_name}",
        )

    with c2:
        reserve = st.number_input(
            "Stock de reserva",
            min_value=0,
            value=0,
            step=1,
            help=(
                "Se descuenta esta cantidad del stock "
                "disponible de Casa Matriz antes de "
                "actualizar la plantilla."
            ),
            key=f"market_reserve_real_{key_name}",
        )

    # ========================================================
    # MAPA DE STOCK
    # ========================================================
    lookup = _stock_map(
        house,
        reserve,
    )

    stock_items = tuple(
        sorted(
            lookup.items()
        )
    )

    template_bytes = (
        path.read_bytes()
    )

    # ========================================================
    # GENERAR PLANTILLA REAL
    # ========================================================
    try:
        if name == "Paris Marketplace":
            (
                output_bytes,
                preview,
                stats,
            ) = _build_paris_workbook(
                template_bytes,
                stock_items,
            )

            download_name = (
                "Paris_stock_actualizado.xlsx"
            )

            button_label = (
                "⬇ Descargar plantilla Paris actualizada"
            )

        else:
            (
                output_bytes,
                preview,
                stats,
            ) = _build_meli_workbook(
                template_bytes,
                stock_items,
            )

            download_name = (
                "Mercado_Libre_stock_actualizado.xlsx"
            )

            button_label = (
                "⬇ Descargar plantilla Mercado Libre actualizada"
            )

    except Exception as exc:
        st.error(
            f"No fue posible procesar la plantilla: {exc}"
        )
        return

    # ========================================================
    # KPI CRUCE
    # ========================================================
    render_html(
        f"""
        <div class="market-v60-summary">

            <div>
                <span>
                    Filas plantilla
                </span>
                <strong>
                    {stats["rows"]:,}
                </strong>
            </div>

            <div>
                <span>
                    Coincidencias ERP
                </span>
                <strong>
                    {stats["matched_rows"]:,}
                </strong>
            </div>

            <div>
                <span>
                    Sin coincidencia
                </span>
                <strong>
                    {stats["unmatched_rows"]:,}
                </strong>
            </div>

            <div>
                <span>
                    Stock a publicar
                </span>
                <strong>
                    {stats["units"]:,}
                </strong>
            </div>

        </div>
        """
    )

    # ========================================================
    # BUSCAR EN PREVIEW
    # ========================================================
    preview_view = (
        preview.copy()
    )

    if search:
        term = (
            search
            .strip()
            .lower()
        )

        text_columns = [
            col
            for col in preview_view.columns
            if preview_view[col].dtype == object
        ]

        mask = pd.Series(
            False,
            index=preview_view.index,
        )

        for col in text_columns:
            mask = (
                mask
                |
                preview_view[col]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.contains(
                    term,
                    regex=False,
                )
            )

        preview_view = preview_view[
            mask
        ].copy()

    # ========================================================
    # FILTRO DE COINCIDENCIA
    # ========================================================
    match_filter = st.radio(
        "Mostrar",
        [
            "Todos",
            "Encontrados",
            "Sin coincidencia",
        ],
        horizontal=True,
        key=f"market_match_filter_{key_name}",
    )

    if (
        match_filter == "Encontrados"
        and "Coincidencia ERP" in preview_view.columns
    ):
        preview_view = preview_view[
            preview_view[
                "Coincidencia ERP"
            ].eq(
                "Encontrado"
            )
        ]

    elif (
        match_filter == "Sin coincidencia"
        and "Coincidencia ERP" in preview_view.columns
    ):
        preview_view = preview_view[
            preview_view[
                "Coincidencia ERP"
            ].eq(
                "Sin coincidencia"
            )
        ]

    # ========================================================
    # TABLA
    # ========================================================
    st.dataframe(
        preview_view,
        hide_index=True,
        use_container_width=True,
        height=440,
    )

    # ========================================================
    # AVISO SKU SIN MATCH
    # ========================================================
    if stats["unmatched_rows"] > 0:
        st.warning(
            f"{stats['unmatched_rows']:,} fila(s) de la plantilla "
            "no tienen coincidencia con el ERP Stock de Casa Matriz. "
            "Esas filas se exportarán con stock 0."
        )

    # ========================================================
    # DESCARGA PLANTILLA ORIGINAL ACTUALIZADA
    # ========================================================
    st.download_button(
        button_label,
        data=output_bytes,
        file_name=download_name,
        mime=(
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
        key=f"market_download_real_{key_name}",
    )


# ============================================================
# RENDER PRINCIPAL
# ============================================================

def render(ctx):
    df = ctx.get(
        "stock_df"
    )

    meta = (
        ctx.get(
            "stock_meta"
        )
        or {}
    )

    # ========================================================
    # HEADER
    # ========================================================
    render_html(
        """
        <div class="gm-page-head">

            <div class="gm-page-title">
                Marketplaces
            </div>

            <div class="gm-page-subtitle">
                Actualiza las plantillas oficiales de Paris y
                Mercado Libre utilizando exclusivamente el
                stock de Casa Matriz.
            </div>

        </div>
        """
    )

    if df is None or df.empty:
        st.info(
            "Carga ERP Stock desde Plantillas."
        )
        return

    # ========================================================
    # CASA MATRIZ
    # ========================================================
    house = _prepare_house_stock(
        df
    )

    if house.empty:
        st.warning(
            "No se encontraron registros asociados "
            "a Casa Matriz en ERP Stock."
        )
        return

    # ========================================================
    # TOTALES CASA MATRIZ
    # ========================================================
    available = pd.to_numeric(
        house["Disponible"],
        errors="coerce",
    ).fillna(0)

    total_skus = int(
        house["_sku_match"]
        .nunique()
    )

    total_available = _safe_int(
        available.sum()
    )

    positive_skus = int(
        (available > 0).sum()
    )

    zero_skus = int(
        (available <= 0).sum()
    )

    # ========================================================
    # FUENTE ACTIVA
    # ========================================================
    render_html(
        f"""
        <div class="stock-v60-file">

            <div class="stock-v60-file-icon">
                ▤
            </div>

            <div>

                <div class="stock-v60-file-name">

                    {meta.get("filename", "ERP Stock")}

                    <span style="color:#27b66f">
                        ●
                    </span>

                </div>

                <div class="stock-v60-file-meta">

                    Fuente de inventario ·
                    {meta.get("loaded_at", "sesión actual")}

                </div>

            </div>

        </div>
        """
    )

    # ========================================================
    # KPI
    # ========================================================
    render_html(
        f"""
        <div class="stock-v60-kpis">

            <div class="stock-v60-kpi">
                <div class="stock-v60-kpi-row">

                    <div class="stock-v60-kpi-icon purple">
                        ◇
                    </div>

                    <div>
                        <div class="stock-v60-kpi-label">
                            SKU Casa Matriz
                        </div>

                        <div class="stock-v60-kpi-value">
                            {total_skus:,}
                        </div>
                    </div>

                </div>

                <div class="stock-v60-kpi-foot">
                    SKU únicos consolidados
                </div>
            </div>


            <div class="stock-v60-kpi">
                <div class="stock-v60-kpi-row">

                    <div class="stock-v60-kpi-icon green">
                        ▤
                    </div>

                    <div>
                        <div class="stock-v60-kpi-label">
                            Unidades disponibles
                        </div>

                        <div class="stock-v60-kpi-value">
                            {total_available:,}
                        </div>
                    </div>

                </div>

                <div class="stock-v60-kpi-foot">
                    Stock proyectado Casa Matriz
                </div>
            </div>


            <div class="stock-v60-kpi">
                <div class="stock-v60-kpi-row">

                    <div class="stock-v60-kpi-icon blue">
                        ✓
                    </div>

                    <div>
                        <div class="stock-v60-kpi-label">
                            SKU con stock
                        </div>

                        <div class="stock-v60-kpi-value">
                            {positive_skus:,}
                        </div>
                    </div>

                </div>

                <div class="stock-v60-kpi-foot">
                    Disponibles para publicación
                </div>
            </div>


            <div class="stock-v60-kpi">
                <div class="stock-v60-kpi-row">

                    <div class="stock-v60-kpi-icon orange">
                        !
                    </div>

                    <div>
                        <div class="stock-v60-kpi-label">
                            Sin disponibilidad
                        </div>

                        <div class="stock-v60-kpi-value">
                            {zero_skus:,}
                        </div>
                    </div>

                </div>

                <div class="stock-v60-kpi-foot">
                    SKU en cero o negativo
                </div>
            </div>

        </div>
        """
    )

    # ========================================================
    # REGLA
    # ========================================================
    render_html(
        """
        <div class="market-v60-rule">

            <strong>
                Regla activa:
            </strong>

            únicamente el stock disponible de
            <strong>Casa Matriz</strong>
            puede actualizar las plantillas de Paris
            y Mercado Libre.

        </div>
        """
    )

    # ========================================================
    # TABS
    # ========================================================
    paris_tab, meli_tab = st.tabs(
        [
            "Paris Marketplace",
            "Mercado Libre",
        ]
    )

    with paris_tab:
        _render_marketplace_panel(
            name="Paris Marketplace",
            key_name="paris",
            house=house,
        )

    with meli_tab:
        _render_marketplace_panel(
            name="Mercado Libre",
            key_name="meli",
            house=house,
        )