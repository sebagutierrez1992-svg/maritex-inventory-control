import pandas as pd
import streamlit as st
import altair as alt

from analytics.stock_metrics import consolidate_inventory
from ui.components import render_html
from utils.excel import dataframe_to_excel_bytes


def _safe_int(value) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def _build_summary(
    inventory: pd.DataFrame,
    consolidated: pd.DataFrame,
) -> dict:
    """
    Calcula los KPI usando dataframes ya procesados.

    Evita llamar stock_summary(df), porque esa función vuelve a ejecutar:
    - stock_view()
    - consolidate_inventory()

    Esto reduce bastante el tiempo de carga.
    """
    if consolidated is None or consolidated.empty:
        return {
            "sku_total": 0,
            "units_available": 0,
            "units_incoming": 0,
            "warehouses": 0,
            "available": 0,
            "low": 0,
            "zero": 0,
            "negative": 0,
            "risk": 0,
            "incoming_sku": 0,
        }

    states = (
        consolidated["Estado"]
        .fillna("")
        .astype(str)
    )

    units_available = _safe_int(
        pd.to_numeric(
            consolidated["Disponible"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    units_incoming = _safe_int(
        pd.to_numeric(
            consolidated["Por llegar"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
    )

    warehouses = 0

    if (
        inventory is not None
        and not inventory.empty
        and "Bodega" in inventory.columns
    ):
        warehouses = int(
            inventory["Bodega"]
            .replace("", pd.NA)
            .dropna()
            .astype(str)
            .str.strip()
            .nunique()
        )

    return {
        "sku_total": int(
            consolidated["Código"].nunique()
            if "Código" in consolidated.columns
            else 0
        ),
        "units_available": units_available,
        "units_incoming": units_incoming,
        "warehouses": warehouses,
        "available": int(
            states.eq("🟢 Disponible").sum()
        ),
        "low": int(
            states.eq("🟡 Stock bajo").sum()
        ),
        "zero": int(
            states.eq("🔴 Sin stock").sum()
        ),
        "negative": int(
            states.eq("🔴 Negativo").sum()
        ),
        "risk": int(
            states.eq("🟠 Riesgo despacho").sum()
        ),
        "incoming_sku": int(
            states.eq("🔵 Por llegar").sum()
        ),
    }


def _prepare_search_columns(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Precalcula texto normalizado para búsqueda.
    Así no repetimos .astype().str.lower() en cada condición.
    """
    out = df.copy()

    out["_search_codigo"] = (
        out["Código"]
        .fillna("")
        .astype(str)
        .str.lower()
    )

    out["_search_producto"] = (
        out["Producto"]
        .fillna("")
        .astype(str)
        .str.lower()
    )

    return out


def render(ctx):
    # ============================================================
    # FUENTE
    # ============================================================
    df = ctx.get("stock_df")
    inventory = ctx.get("stock_normalized")
    consolidated = ctx.get("stock_consolidated")
    meta = ctx.get("stock_meta") or {}

    # ============================================================
    # HEADER
    # ============================================================
    render_html(
        """
        <div class="gm-page-head">
            <div class="gm-page-title">
                Stock General
            </div>

            <div class="gm-page-subtitle">
                Consulta y administra el inventario consolidado
                proveniente de Flexline.
            </div>
        </div>
        """
    )

    if (
        df is None
        or df.empty
        or inventory is None
        or inventory.empty
        or consolidated is None
        or consolidated.empty
    ):
        st.info(
            "Carga ERP Stock desde Plantillas."
        )
        return

    # ============================================================
    # DATOS YA PREPARADOS EN APP.PY
    #
    # app.py entrega:
    # - stock_df
    # - stock_normalized
    # - stock_consolidated
    #
    # Así evitamos volver a ejecutar stock_view() y la
    # consolidación completa cada vez que Streamlit hace rerun.
    # ============================================================
    summary = _build_summary(
        inventory,
        consolidated,
    )

    # Preparar búsqueda sobre el inventario normalizado.
    inventory_search = _prepare_search_columns(
        inventory
    )

    # ============================================================
    # ARCHIVO ACTIVO
    # ============================================================
    render_html(
        f"""
        <div class="stock-v60-file">

            <div class="stock-v60-file-icon">
                ▤
            </div>

            <div>
                <div class="stock-v60-file-name">
                    {meta.get("filename", "ERP Stock")}
                    <span style="color:#27b66f">●</span>
                </div>

                <div class="stock-v60-file-meta">
                    {len(inventory):,} registros ·
                    Compartido con Métricas de Stock y Marketplaces ·
                    {meta.get("loaded_at", "sesión actual")}
                </div>
            </div>

        </div>
        """
    )

    # ============================================================
    # KPI
    # ============================================================
    unavailable = (
        summary["zero"]
        + summary["negative"]
    )

    attention = (
        unavailable
        + summary["low"]
        + summary["risk"]
    )

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
                            Stock Totales
                        </div>

                        <div class="stock-v60-kpi-value">
                            {summary["sku_total"]:,}
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
                            Unidades Totales
                        </div>

                        <div class="stock-v60-kpi-value">
                            {summary["units_available"]:,}
                        </div>
                    </div>
                </div>

                <div class="stock-v60-kpi-foot">
                    Disponibles en todas las bodegas
                </div>
            </div>

            <div class="stock-v60-kpi">
                <div class="stock-v60-kpi-row">
                    <div class="stock-v60-kpi-icon blue">
                        ⌂
                    </div>

                    <div>
                        <div class="stock-v60-kpi-label">
                            Bodegas Activas
                        </div>

                        <div class="stock-v60-kpi-value">
                            {summary["warehouses"]:,}
                        </div>
                    </div>
                </div>

                <div class="stock-v60-kpi-foot">
                    Distribución operativa
                </div>
            </div>

            <div class="stock-v60-kpi">
                <div class="stock-v60-kpi-row">
                    <div class="stock-v60-kpi-icon orange">
                        □
                    </div>

                    <div>
                        <div class="stock-v60-kpi-label">
                            Sin Stock
                        </div>

                        <div class="stock-v60-kpi-value">
                            {unavailable:,}
                        </div>
                    </div>
                </div>

                <div class="stock-v60-kpi-foot">
                    Sin disponibilidad
                </div>
            </div>

        </div>
        """
    )

    # ============================================================
    # ALERTA OPERACIONAL
    # ============================================================
    render_html(
        f"""
        <div class="stock-v60-alert">

            <div class="stock-v60-alert-icon">
                !
            </div>

            <div>
                <div class="stock-v60-alert-title">
                    Requiere atención ·
                    {attention:,} incidencias operativas
                </div>

                <div class="stock-v60-alert-items">

                    <span>
                        <strong>
                            {summary["negative"]:,}
                        </strong>
                        negativos
                    </span>

                    <span>
                        <strong>
                            {summary["zero"]:,}
                        </strong>
                        sin stock
                    </span>

                    <span>
                        <strong>
                            {summary["low"]:,}
                        </strong>
                        stock bajo
                    </span>

                    <span>
                        <strong>
                            {summary["risk"]:,}
                        </strong>
                        riesgo despacho
                    </span>

                    <span>
                        <strong>
                            {summary["incoming_sku"]:,}
                        </strong>
                        con reposición en camino
                    </span>

                </div>
            </div>

        </div>
        """
    )

    # ============================================================
    # ANALÍTICA
    # ============================================================
    c1, c2 = st.columns(
        [1, 1.15],
        gap="medium",
    )

    # ------------------------------------------------------------
    # SEMÁFORO
    # ------------------------------------------------------------
    with c1:
        render_html(
            """
            <div class="gm-card">

                <div class="gm-card-title">
                    Semáforo de disponibilidad
                </div>

                <div class="gm-card-subtitle">
                    Distribución consolidada por estado
                </div>
            """
        )

        dist = pd.DataFrame(
            {
                "Estado": [
                    "Disponible",
                    "Stock bajo",
                    "Riesgo despacho",
                    "Sin stock / negativo",
                    "Por llegar",
                ],
                "SKU": [
                    summary["available"],
                    summary["low"],
                    summary["risk"],
                    unavailable,
                    summary["incoming_sku"],
                ],
            }
        )

        dist = dist[
            dist["SKU"] > 0
        ]

        if not dist.empty:
            chart = (
                alt.Chart(dist)
                .mark_arc(
                    innerRadius=58,
                    outerRadius=88,
                )
                .encode(
                    theta=alt.Theta(
                        "SKU:Q"
                    ),
                    color=alt.Color(
                        "Estado:N",
                        legend=alt.Legend(
                            title=None,
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "Estado:N",
                            title="Estado",
                        ),
                        alt.Tooltip(
                            "SKU:Q",
                            title="SKU",
                            format=",",
                        ),
                    ],
                )
                .properties(
                    height=260,
                )
            )

            st.altair_chart(
                chart,
                use_container_width=True,
            )

        render_html(
            "</div>"
        )

    # ------------------------------------------------------------
    # STOCK POR FAMILIA
    # ------------------------------------------------------------
    with c2:
        render_html(
            """
            <div class="gm-card">

                <div class="gm-card-title">
                    Stock disponible por familia
                </div>

                <div class="gm-card-subtitle">
                    Top familias por unidades disponibles
                </div>
            """
        )

        if (
            "Familia" in consolidated.columns
            and "Disponible" in consolidated.columns
        ):
            fam = (
                consolidated.assign(
                    Familia=consolidated[
                        "Familia"
                    ].replace(
                        "",
                        "Sin familia",
                    )
                )
                .groupby(
                    "Familia",
                    as_index=False,
                )["Disponible"]
                .sum()
                .sort_values(
                    "Disponible",
                    ascending=False,
                )
                .head(10)
            )
        else:
            fam = pd.DataFrame()

        if not fam.empty:
            chart = (
                alt.Chart(fam)
                .mark_bar(
                    cornerRadiusEnd=4,
                    color="#6536f3",
                )
                .encode(
                    y=alt.Y(
                        "Familia:N",
                        sort="-x",
                        title=None,
                    ),
                    x=alt.X(
                        "Disponible:Q",
                        title=None,
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "Familia:N",
                            title="Familia",
                        ),
                        alt.Tooltip(
                            "Disponible:Q",
                            title="Disponible",
                            format=",",
                        ),
                    ],
                )
                .properties(
                    height=260,
                )
            )

            st.altair_chart(
                chart,
                use_container_width=True,
            )

        render_html(
            "</div>"
        )

    # ============================================================
    # FILTROS
    # ============================================================
    render_html(
        """
        <div class="stock-v60-filter">
            <div class="gm-card-title">
                Vista y filtros
            </div>
        """
    )

    mode = st.radio(
        "Vista",
        [
            "Consolidado por producto",
            "Por bodega",
        ],
        horizontal=True,
        key="stock_mode_v618",
    )

    f1, f2, f3 = st.columns(
        [1.55, 1, 1]
    )

    with f1:
        search = st.text_input(
            "Buscar",
            placeholder="Buscar producto, código, SKU…",
            key="stock_search_v618",
        )

    with f2:
        warehouses = sorted(
            inventory["Bodega"]
            .replace("", pd.NA)
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_wh = st.multiselect(
            "Bodega",
            warehouses,
            placeholder="Todas las bodegas",
            key="stock_wh_v618",
        )

    with f3:
        families = sorted(
            inventory["Familia"]
            .replace("", pd.NA)
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_fam = st.multiselect(
            "Familia",
            families,
            placeholder="Todas las familias",
            key="stock_fam_v618",
        )

    f4, f5 = st.columns(
        [1, 1.65]
    )

    with f4:
        subfamilies = sorted(
            inventory["Subfamilia"]
            .replace("", pd.NA)
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_sub = st.multiselect(
            "Subfamilia",
            subfamilies,
            placeholder="Todas las subfamilias",
            key="stock_sub_v618",
        )

    with f5:
        status = st.radio(
            "Estado",
            [
                "Todos",
                "Disponible",
                "Stock bajo",
                "Sin stock",
                "Negativo",
                "Riesgo despacho",
                "Por llegar",
            ],
            horizontal=True,
            key="stock_status_v618",
        )

    render_html(
        "</div>"
    )

    # ============================================================
    # FILTRAR INVENTARIO
    # ============================================================
    filtered = inventory_search.copy()

    if search:
        term = (
            search
            .lower()
            .strip()
        )

        mask = (
            filtered[
                "_search_codigo"
            ].str.contains(
                term,
                regex=False,
            )
            |
            filtered[
                "_search_producto"
            ].str.contains(
                term,
                regex=False,
            )
        )

        filtered = filtered[
            mask
        ]

    if selected_wh:
        filtered = filtered[
            filtered[
                "Bodega"
            ].isin(
                selected_wh
            )
        ]

    if selected_fam:
        filtered = filtered[
            filtered[
                "Familia"
            ].isin(
                selected_fam
            )
        ]

    if selected_sub:
        filtered = filtered[
            filtered[
                "Subfamilia"
            ].isin(
                selected_sub
            )
        ]

    # Quitar columnas auxiliares.
    filtered = filtered.drop(
        columns=[
            "_search_codigo",
            "_search_producto",
        ],
        errors="ignore",
    )

    # ============================================================
    # VISTA
    # ============================================================
    if mode == "Consolidado por producto":

        has_inventory_filters = bool(
            search
            or selected_wh
            or selected_fam
            or selected_sub
        )

        # Sin filtros reutilizamos el consolidado global cacheado.
        if has_inventory_filters:
            display = consolidate_inventory(
                filtered
            )
        else:
            display = consolidated.copy()

    else:
        display = filtered.copy()

    status_map = {
        "Disponible": "🟢 Disponible",
        "Stock bajo": "🟡 Stock bajo",
        "Sin stock": "🔴 Sin stock",
        "Negativo": "🔴 Negativo",
        "Riesgo despacho": "🟠 Riesgo despacho",
        "Por llegar": "🔵 Por llegar",
    }

    if status != "Todos":
        display = display[
            display[
                "Estado"
            ].eq(
                status_map[status]
            )
        ].copy()

    # ============================================================
    # LIMPIEZA PARA TABLA
    # ============================================================
    numeric_columns = [
        "Stock físico",
        "Disponible",
        "Por llegar",
        "Por despachar",
        "Precio",
        "Bodegas",
    ]

    for col in numeric_columns:
        if col in display.columns:
            display[col] = (
                pd.to_numeric(
                    display[col],
                    errors="coerce",
                )
                .fillna(0)
                .round()
                .astype("Int64")
            )

    # ============================================================
    # RESUMEN FILTRADO
    # ============================================================
    result_rows = len(display)

    result_products = (
        int(
            display[
                "Código"
            ].nunique()
        )
        if (
            not display.empty
            and "Código" in display.columns
        )
        else 0
    )

    result_available = (
        _safe_int(
            pd.to_numeric(
                display["Disponible"],
                errors="coerce",
            )
            .fillna(0)
            .sum()
        )
        if "Disponible" in display.columns
        else 0
    )

    summary_col, export_col = st.columns(
        [4.7, 1]
    )

    with summary_col:
        render_html(
            f"""
            <div class="stock-v60-result">

                <span>
                    Mostrando
                    <strong>{result_rows:,}</strong>
                    registros ·
                    <strong>{result_products:,}</strong>
                    productos
                </span>

                <span>
                    Disponible filtrado:
                    <strong>{result_available:,}</strong>
                    uds
                </span>

            </div>
            """
        )

    # ============================================================
    # EXPORTAR BAJO DEMANDA
    #
    # Evita reconstruir el Excel cada vez que se cambia un filtro,
    # un SKU o cualquier otro widget de la página.
    # ============================================================
    with export_col:

        # Si cambió la tabla filtrada, invalidamos una exportación
        # anterior para no descargar datos desactualizados.
        export_signature = (
            mode,
            search,
            tuple(selected_wh),
            tuple(selected_fam),
            tuple(selected_sub),
            status,
            len(display),
            result_products,
            result_available,
        )

        if (
            st.session_state.get(
                "stock_export_signature"
            )
            != export_signature
        ):
            st.session_state.pop(
                "stock_export_bytes",
                None,
            )
            st.session_state[
                "stock_export_signature"
            ] = export_signature

        if st.button(
            "Preparar Excel",
            use_container_width=True,
            key="stock_prepare_export_v619",
        ):
            with st.spinner(
                "Preparando Excel..."
            ):
                st.session_state[
                    "stock_export_bytes"
                ] = dataframe_to_excel_bytes(
                    display,
                    sheet_name="Stock_Filtrado",
                )

        export_bytes = st.session_state.get(
            "stock_export_bytes"
        )

        if export_bytes:
            st.download_button(
                "⬇ Descargar",
                data=export_bytes,
                file_name=(
                    "Stock_General_Filtrado.xlsx"
                ),
                mime=(
                    "application/"
                    "vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="stock_download_v619",
            )

    # ============================================================
    # TABLA PRINCIPAL
    # ============================================================
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=570,
        column_config={
            "Estado": st.column_config.TextColumn(
                "Estado",
                width="medium",
            ),
            "Código": st.column_config.TextColumn(
                "SKU",
                width="medium",
            ),
            "Producto": st.column_config.TextColumn(
                "Producto",
                width="large",
            ),
            "Bodega": st.column_config.TextColumn(
                "Bodega",
                width="medium",
            ),
            "Disponible": st.column_config.NumberColumn(
                "Disponible",
                format="%d",
            ),
            "Stock físico": st.column_config.NumberColumn(
                "Stock físico",
                format="%d",
            ),
            "Por llegar": st.column_config.NumberColumn(
                "Por llegar",
                format="%d",
            ),
            "Por despachar": st.column_config.NumberColumn(
                "Por despachar",
                format="%d",
            ),
            "Precio": st.column_config.NumberColumn(
                "Precio",
                format="$%d",
            ),
        },
    )

    # ============================================================
    # DETALLE POR PRODUCTO / BODEGA
    # ============================================================
    codes = (
        display["Código"]
        .dropna()
        .astype(str)
        .drop_duplicates()
        .tolist()
        if "Código" in display.columns
        else []
    )

    if codes:
        st.markdown(
            "### Detalle por producto"
        )

        code = st.selectbox(
            "Seleccionar SKU",
            codes,
            key="stock_detail_v618",
        )

        # IMPORTANTE:
        # Se consulta sobre inventory, que mantiene bodega.
        sku = inventory[
            inventory["Código"]
            .astype(str)
            .eq(str(code))
        ].copy()

        # Respetar filtros de bodega/familia/subfamilia.
        if selected_wh:
            sku = sku[
                sku["Bodega"].isin(
                    selected_wh
                )
            ]

        if selected_fam:
            sku = sku[
                sku["Familia"].isin(
                    selected_fam
                )
            ]

        if selected_sub:
            sku = sku[
                sku["Subfamilia"].isin(
                    selected_sub
                )
            ]

        if not sku.empty:
            # Solo bodegas con stock o movimiento.
            movement = (
                pd.to_numeric(
                    sku["Disponible"],
                    errors="coerce",
                ).fillna(0).ne(0)
                |
                pd.to_numeric(
                    sku["Stock físico"],
                    errors="coerce",
                ).fillna(0).ne(0)
                |
                pd.to_numeric(
                    sku["Por llegar"],
                    errors="coerce",
                ).fillna(0).ne(0)
                |
                pd.to_numeric(
                    sku["Por despachar"],
                    errors="coerce",
                ).fillna(0).ne(0)
            )

            sku_detail = sku[
                movement
            ].copy()

            if sku_detail.empty:
                sku_detail = sku.copy()

            render_html(
                f"""
                <div class="stock-v60-detail">

                    <div class="gm-card-title">
                        {sku["Producto"].iloc[0]}
                    </div>

                    <div class="gm-card-subtitle">
                        SKU {code}
                    </div>

                    <div class="stock-v60-detail-grid">

                        <div>
                            <span>Disponible</span>
                            <strong>
                                {_safe_int(sku["Disponible"].sum()):,}
                            </strong>
                        </div>

                        <div>
                            <span>Stock físico</span>
                            <strong>
                                {_safe_int(sku["Stock físico"].sum()):,}
                            </strong>
                        </div>

                        <div>
                            <span>Por llegar</span>
                            <strong>
                                {_safe_int(sku["Por llegar"].sum()):,}
                            </strong>
                        </div>

                        <div>
                            <span>Por despachar</span>
                            <strong>
                                {_safe_int(sku["Por despachar"].sum()):,}
                            </strong>
                        </div>

                    </div>

                </div>
                """
            )

            st.caption(
                f"Stock distribuido en "
                f"{sku_detail['Bodega'].replace('', pd.NA).dropna().nunique():,} "
                f"bodega(s)"
            )

            st.dataframe(
                sku_detail[
                    [
                        "Bodega",
                        "Stock físico",
                        "Disponible",
                        "Por llegar",
                        "Por despachar",
                    ]
                ],
                hide_index=True,
                use_container_width=True,
                height=min(
                    360,
                    44 + len(sku_detail) * 36,
                ),
                column_config={
                    "Bodega": st.column_config.TextColumn(
                        "Bodega",
                        width="large",
                    ),
                    "Stock físico": st.column_config.NumberColumn(
                        "Stock físico",
                        format="%d",
                    ),
                    "Disponible": st.column_config.NumberColumn(
                        "Disponible",
                        format="%d",
                    ),
                    "Por llegar": st.column_config.NumberColumn(
                        "Por llegar",
                        format="%d",
                    ),
                    "Por despachar": st.column_config.NumberColumn(
                        "Por despachar",
                        format="%d",
                    ),
                },
            )