import pandas as pd
import streamlit as st
import altair as alt
from zoneinfo import ZoneInfo

from analytics.stock_metrics import consolidate_inventory
from ui.components import render_html
from utils.excel import dataframe_to_excel_bytes


# ============================================================
# HELPERS
# ============================================================

def _safe_int(value) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return 0


def _fmt_int(value) -> str:
    return f"{_safe_int(value):,}".replace(",", ".")


def _friendly_datetime(value) -> str:
    """
    Convierte la fecha/hora recibida desde Llegadas_OK a hora local de Chile.

    Llegadas_OK entrega el timestamp en UTC. Se convierte usando
    America/Santiago para respetar automáticamente horario de invierno
    y horario de verano de Chile.
    """
    if value is None:
        return "Sesión actual"

    text = str(value).strip()
    if not text:
        return "Sesión actual"

    try:
        dt = pd.to_datetime(text, utc=True, errors="raise")
        chile_dt = dt.tz_convert(ZoneInfo("America/Santiago"))
        return chile_dt.strftime("%d/%m/%Y · %H:%M · Chile")
    except Exception:
        return text


def _series_num(df: pd.DataFrame, column: str) -> pd.Series:
    if df is None or column not in df.columns:
        return pd.Series(0.0, index=df.index if df is not None else None)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _build_summary(
    inventory: pd.DataFrame,
    consolidated: pd.DataFrame,
) -> dict:
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
        consolidated.get(
            "Estado",
            pd.Series("", index=consolidated.index),
        )
        .fillna("")
        .astype(str)
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
            else len(consolidated)
        ),
        "units_available": _safe_int(
            _series_num(consolidated, "Disponible").sum()
        ),
        "units_incoming": _safe_int(
            _series_num(consolidated, "Por llegar").sum()
        ),
        "warehouses": warehouses,
        "available": int(states.eq("🟢 Disponible").sum()),
        "low": int(states.eq("🟡 Stock bajo").sum()),
        "zero": int(states.eq("🔴 Sin stock").sum()),
        "negative": int(states.eq("🔴 Negativo").sum()),
        "risk": int(states.eq("🟠 Riesgo despacho").sum()),
        "incoming_sku": int(states.eq("🔵 Por llegar").sum()),
    }


def _prepare_search_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["_search_codigo"] = (
        out.get(
            "Código",
            pd.Series("", index=out.index),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    out["_search_producto"] = (
        out.get(
            "Producto",
            pd.Series("", index=out.index),
        )
        .fillna("")
        .astype(str)
        .str.lower()
    )

    return out


def _warehouse_summary(inventory: pd.DataFrame) -> pd.DataFrame:
    if (
        inventory is None
        or inventory.empty
        or "Bodega" not in inventory.columns
        or "Disponible" not in inventory.columns
    ):
        return pd.DataFrame()

    work = inventory.copy()

    work["Bodega"] = (
        work["Bodega"]
        .replace("", pd.NA)
        .fillna("Sin bodega")
        .astype(str)
        .str.strip()
    )

    work["Disponible"] = pd.to_numeric(
        work["Disponible"],
        errors="coerce",
    ).fillna(0)

    result = (
        work.groupby("Bodega", as_index=False)["Disponible"]
        .sum()
        .sort_values("Disponible", ascending=False)
    )

    return result


def _low_stock_products(
    consolidated: pd.DataFrame,
    limit: int = 10,
) -> pd.DataFrame:
    if consolidated is None or consolidated.empty:
        return pd.DataFrame()

    required = {"Código", "Producto", "Disponible"}
    if not required.issubset(consolidated.columns):
        return pd.DataFrame()

    work = consolidated.copy()

    work["Disponible"] = pd.to_numeric(
        work["Disponible"],
        errors="coerce",
    ).fillna(0)

    # Prioridad operacional:
    # 1) primero sin stock/negativos
    # 2) luego stock bajo
    # 3) ordenar por menor disponibilidad
    state = work.get(
        "Estado",
        pd.Series("", index=work.index),
    ).fillna("").astype(str)

    work["_priority"] = 99
    work.loc[
        state.isin(["🔴 Sin stock", "🔴 Negativo"]),
        "_priority",
    ] = 1
    work.loc[
        state.eq("🟡 Stock bajo"),
        "_priority",
    ] = 2

    low = work[
        work["_priority"].isin([1, 2])
    ].copy()

    if low.empty:
        return pd.DataFrame()

    if "Por llegar" not in low.columns:
        low["Por llegar"] = 0

    low["Por llegar"] = pd.to_numeric(
        low["Por llegar"],
        errors="coerce",
    ).fillna(0)

    low = low.sort_values(
        ["_priority", "Disponible", "Por llegar"],
        ascending=[True, True, False],
    ).head(limit)

    return low[
        [
            "Código",
            "Producto",
            "Disponible",
            "Por llegar",
            "Estado",
        ]
    ].reset_index(drop=True)


def _kpi_card(
    label: str,
    value: str,
    helper: str,
    icon: str,
    tone: str,
    badge: str | None = None,
) -> str:
    badge_html = (
        f"<span class='sg-kpi-badge {tone}'>{badge}</span>"
        if badge
        else ""
    )

    return f"""
    <div class="sg-kpi">
        <div class="sg-kpi-top">
            <div class="sg-kpi-icon {tone}">{icon}</div>
            {badge_html}
        </div>
        <div class="sg-kpi-label">{label}</div>
        <div class="sg-kpi-value">{value}</div>
        <div class="sg-kpi-helper">{helper}</div>
    </div>
    """


# ============================================================
# RENDER
# ============================================================

def render(ctx):
    # --------------------------------------------------------
    # FUENTE
    # --------------------------------------------------------
    df = ctx.get("stock_df")
    inventory = ctx.get("stock_normalized")
    consolidated = ctx.get("stock_consolidated")
    meta = ctx.get("stock_meta") or {}

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------
    render_html(
        """
        <div class="sg-head">
            <div>
                <div class="sg-eyebrow">MARITEX · OPERACIÓN</div>
                <div class="sg-title">Stock General</div>
                <div class="sg-subtitle">
                    Disponibilidad consolidada, alertas y distribución
                    del inventario por producto, familia y bodega.
                </div>
            </div>
            <div class="sg-head-badge">
                <i></i>
                Inventario conectado
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
        st.info("Carga ERP Stock desde Plantillas.")
        return

    summary = _build_summary(
        inventory,
        consolidated,
    )

    inventory_search = _prepare_search_columns(
        inventory
    )

    unavailable = (
        summary["zero"]
        + summary["negative"]
    )

    attention = (
        unavailable
        + summary["low"]
        + summary["risk"]
    )

    total_states = max(
        summary["available"]
        + summary["low"]
        + summary["zero"]
        + summary["negative"]
        + summary["risk"]
        + summary["incoming_sku"],
        1,
    )

    healthy_pct = (
        summary["available"] / total_states * 100
    )

    # --------------------------------------------------------
    # SOURCE STRIP
    # --------------------------------------------------------
    source_name = meta.get(
        "filename",
        "ERP Stock",
    )

    source_loaded = _friendly_datetime(
        meta.get(
            "loaded_at",
            "sesión actual",
        )
    )

    render_html(
        f"""
        <div class="sg-source">
            <div class="sg-source-brand">
                <div class="sg-source-icon">▤</div>

                <div class="sg-source-copy">
                    <div class="sg-source-name">
                        {source_name}
                        <span class="sg-source-live">
                            <i></i> Automático
                        </span>
                    </div>

                    <div class="sg-source-meta">
                        Fuente activa de inventario
                    </div>
                </div>
            </div>

            <div class="sg-source-metrics">
                <div class="sg-source-pill">
                    <span>REGISTROS</span>
                    <strong>{_fmt_int(len(inventory))}</strong>
                </div>

                <div class="sg-source-pill">
                    <span>BODEGAS</span>
                    <strong>{_fmt_int(summary["warehouses"])}</strong>
                </div>

                <div class="sg-source-update">
                    <span>ÚLTIMA ACTUALIZACIÓN</span>
                    <strong>{source_loaded}</strong>
                </div>
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # KPIs
    # --------------------------------------------------------
    kpis_html = "".join(
        [
            _kpi_card(
                "SKU TOTALES",
                _fmt_int(summary["sku_total"]),
                "Productos únicos consolidados",
                "◇",
                "purple",
            ),
            _kpi_card(
                "UNIDADES DISPONIBLES",
                _fmt_int(summary["units_available"]),
                "Stock utilizable en todas las bodegas",
                "▤",
                "green",
            ),
            _kpi_card(
                "STOCK BAJO",
                _fmt_int(summary["low"]),
                "SKU con disponibilidad reducida",
                "!",
                "orange",
                "Revisar",
            ),
            _kpi_card(
                "SIN STOCK",
                _fmt_int(unavailable),
                "SKU sin disponibilidad",
                "×",
                "red",
            ),
            _kpi_card(
                "INVENTARIO SALUDABLE",
                f"{healthy_pct:.1f}%",
                f"{_fmt_int(summary['available'])} SKU disponibles",
                "✓",
                "lime",
            ),
        ]
    )

    render_html(
        f"""
        <div class="sg-kpi-grid">
            {kpis_html}
        </div>
        """
    )

    # --------------------------------------------------------
    # ALERT STRIP
    # --------------------------------------------------------
    alert_tone = (
        "critical"
        if unavailable > 0
        else "warning"
        if attention > 0
        else "ok"
    )

    render_html(
        f"""
        <div class="sg-alert {alert_tone}">
            <div class="sg-alert-main">
                <div class="sg-alert-icon">!</div>
                <div>
                    <span>ATENCIÓN OPERACIONAL</span>
                    <strong>{_fmt_int(attention)} incidencias requieren revisión</strong>
                </div>
            </div>

            <div class="sg-alert-stats">
                <div>
                    <span>Negativos</span>
                    <strong>{_fmt_int(summary["negative"])}</strong>
                </div>
                <div>
                    <span>Sin stock</span>
                    <strong>{_fmt_int(summary["zero"])}</strong>
                </div>
                <div>
                    <span>Stock bajo</span>
                    <strong>{_fmt_int(summary["low"])}</strong>
                </div>
                <div>
                    <span>Riesgo despacho</span>
                    <strong>{_fmt_int(summary["risk"])}</strong>
                </div>
                <div>
                    <span>Por llegar</span>
                    <strong>{_fmt_int(summary["incoming_sku"])}</strong>
                </div>
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # ANALYTICS
    # --------------------------------------------------------
    c1, c2 = st.columns(
        [0.95, 1.55],
        gap="medium",
    )

    # Estado
    with c1:
        with st.container(border=True):
            render_html(
                """
                <div class="sg-card-head">
                    <div>
                        <strong>Estado del inventario</strong>
                        <span>Distribución consolidada por condición</span>
                    </div>
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
                        innerRadius=56,
                        outerRadius=86,
                        cornerRadius=3,
                    )
                    .encode(
                        theta=alt.Theta("SKU:Q"),
                        color=alt.Color(
                            "Estado:N",
                            scale=alt.Scale(
                                domain=[
                                    "Disponible",
                                    "Stock bajo",
                                    "Riesgo despacho",
                                    "Sin stock / negativo",
                                    "Por llegar",
                                ],
                                range=[
                                    "#7fc800",
                                    "#f2b84b",
                                    "#f28c28",
                                    "#e84b4b",
                                    "#4f7cd7",
                                ],
                            ),
                            legend=None,
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
                    .properties(height=205)
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

            render_html(
                f"""
                <div class="sg-status-list">
                    <div>
                        <i class="green"></i>
                        <span>Disponible</span>
                        <strong>{summary["available"]:,}</strong>
                    </div>
                    <div>
                        <i class="yellow"></i>
                        <span>Stock bajo</span>
                        <strong>{summary["low"]:,}</strong>
                    </div>
                    <div>
                        <i class="orange"></i>
                        <span>Riesgo</span>
                        <strong>{summary["risk"]:,}</strong>
                    </div>
                    <div>
                        <i class="red"></i>
                        <span>Sin stock / negativo</span>
                        <strong>{unavailable:,}</strong>
                    </div>
                </div>
                """
            )

    # Bodegas
    with c2:
        with st.container(border=True):
            render_html(
                """
                <div class="sg-card-head">
                    <div>
                        <strong>Stock por bodega</strong>
                        <span>Unidades disponibles por ubicación</span>
                    </div>
                </div>
                """
            )

            wh = _warehouse_summary(
                inventory
            )

            if not wh.empty:
                chart = (
                    alt.Chart(
                        wh.head(8)
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#22272e",
                    )
                    .encode(
                        y=alt.Y(
                            "Bodega:N",
                            sort="-x",
                            title=None,
                            axis=alt.Axis(
                                labelLimit=155,
                                labelColor="#68727c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "Disponible:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7e8892",
                                domain=False,
                                gridColor="#eef1f4",
                                format="~s",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Bodega:N",
                                title="Bodega",
                            ),
                            alt.Tooltip(
                                "Disponible:Q",
                                title="Disponible",
                                format=",",
                            ),
                        ],
                    )
                    .properties(height=285)
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )
            else:
                render_html(
                    """
                    <div class="sg-empty-chart">
                        No hay información de bodegas disponible.
                    </div>
                    """
                )

    # --------------------------------------------------------
    # PRODUCTOS CON STOCK BAJO · HORIZONTAL
    # --------------------------------------------------------
    render_html(
        """
        <div class="sg-section-head sg-low-section-head">
            <div>
                <strong>Productos con stock bajo</strong>
                <span>SKU que requieren revisión inmediata</span>
            </div>
        </div>
        """
    )

    low_products = _low_stock_products(
        consolidated,
        limit=10,
    )

    with st.container(border=True):
        if low_products.empty:
            render_html(
                """
                <div class="sg-low-empty-horizontal">
                    <div class="sg-low-empty-icon">✓</div>
                    <div>
                        <strong>Sin alertas críticas</strong>
                        <span>No hay SKU con stock bajo o sin disponibilidad.</span>
                    </div>
                </div>
                """
            )
        else:
            cards = ""

            for idx, row in low_products.iterrows():
                available = _safe_int(
                    row.get("Disponible", 0)
                )

                incoming = _safe_int(
                    row.get("Por llegar", 0)
                )

                state = str(
                    row.get("Estado", "")
                )

                tone = (
                    "red"
                    if (
                        "Sin stock" in state
                        or "Negativo" in state
                        or available <= 0
                    )
                    else "orange"
                )

                product = str(
                    row.get("Producto", "")
                )[:46]

                code = str(
                    row.get("Código", "")
                )

                incoming_label = (
                    f"+{_fmt_int(incoming)} por llegar"
                    if incoming > 0
                    else "Sin reposición informada"
                )

                cards += f"""
                <div class="sg-low-card">
                    <div class="sg-low-card-top">
                        <span class="sg-low-card-rank {tone}">
                            {idx + 1:02d}
                        </span>

                        <span class="sg-low-card-stock {tone}">
                            {_fmt_int(available)} uds.
                        </span>
                    </div>

                    <div class="sg-low-card-product">
                        {product}
                    </div>

                    <div class="sg-low-card-sku">
                        SKU {code}
                    </div>

                    <div class="sg-low-card-foot">
                        <span>{incoming_label}</span>
                        <i class="{tone}"></i>
                    </div>
                </div>
                """

            render_html(
                f"""
                <div class="sg-low-horizontal">
                    {cards}
                </div>
                """
            )

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------
    render_html(
        """
        <div class="sg-section-head">
            <div>
                <strong>Explorar inventario</strong>
                <span>Filtra y consulta productos o stock por bodega</span>
            </div>
        </div>
        """
    )

    with st.container(border=True):
        mode = st.radio(
            "Vista",
            [
                "Consolidado por producto",
                "Por bodega",
            ],
            horizontal=True,
            key="stock_mode_v700",
        )

        f1, f2, f3, f4 = st.columns(
            [1.45, 1.0, 1.0, 1.0],
            gap="small",
        )

        with f1:
            search = st.text_input(
                "Buscar",
                placeholder="Producto, código o SKU…",
                key="stock_search_v700",
            )

        with f2:
            warehouses = (
                sorted(
                    inventory["Bodega"]
                    .replace("", pd.NA)
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )
                if "Bodega" in inventory.columns
                else []
            )

            selected_wh = st.multiselect(
                "Bodega",
                warehouses,
                placeholder="Todas",
                key="stock_wh_v700",
            )

        with f3:
            families = (
                sorted(
                    inventory["Familia"]
                    .replace("", pd.NA)
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )
                if "Familia" in inventory.columns
                else []
            )

            selected_fam = st.multiselect(
                "Familia",
                families,
                placeholder="Todas",
                key="stock_fam_v700",
            )

        with f4:
            subfamilies = (
                sorted(
                    inventory["Subfamilia"]
                    .replace("", pd.NA)
                    .dropna()
                    .astype(str)
                    .unique()
                    .tolist()
                )
                if "Subfamilia" in inventory.columns
                else []
            )

            selected_sub = st.multiselect(
                "Subfamilia",
                subfamilies,
                placeholder="Todas",
                key="stock_sub_v700",
            )

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
            key="stock_status_v700",
        )

    # --------------------------------------------------------
    # FILTER INVENTORY
    # --------------------------------------------------------
    filtered = inventory_search.copy()

    if search:
        term = search.lower().strip()

        mask = (
            filtered["_search_codigo"].str.contains(
                term,
                regex=False,
            )
            |
            filtered["_search_producto"].str.contains(
                term,
                regex=False,
            )
        )

        filtered = filtered[
            mask
        ]

    if (
        selected_wh
        and "Bodega" in filtered.columns
    ):
        filtered = filtered[
            filtered["Bodega"].isin(
                selected_wh
            )
        ]

    if (
        selected_fam
        and "Familia" in filtered.columns
    ):
        filtered = filtered[
            filtered["Familia"].isin(
                selected_fam
            )
        ]

    if (
        selected_sub
        and "Subfamilia" in filtered.columns
    ):
        filtered = filtered[
            filtered["Subfamilia"].isin(
                selected_sub
            )
        ]

    filtered = filtered.drop(
        columns=[
            "_search_codigo",
            "_search_producto",
        ],
        errors="ignore",
    )

    # --------------------------------------------------------
    # DISPLAY VIEW
    # --------------------------------------------------------
    if mode == "Consolidado por producto":
        has_inventory_filters = bool(
            search
            or selected_wh
            or selected_fam
            or selected_sub
        )

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

    if (
        status != "Todos"
        and "Estado" in display.columns
    ):
        display = display[
            display["Estado"].eq(
                status_map[status]
            )
        ].copy()

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

    # --------------------------------------------------------
    # FILTERED SUMMARY / EXPORT
    # --------------------------------------------------------
    result_rows = len(display)

    result_products = (
        int(
            display["Código"].nunique()
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
        [4.5, 1.15],
        gap="small",
    )

    with summary_col:
        render_html(
            f"""
            <div class="sg-result">
                <div>
                    <span>RESULTADOS</span>
                    <strong>
                        {_fmt_int(result_rows)} registros ·
                        {_fmt_int(result_products)} productos
                    </strong>
                </div>
                <div>
                    <span>DISPONIBLE FILTRADO</span>
                    <strong>{_fmt_int(result_available)} uds.</strong>
                </div>
            </div>
            """
        )

    with export_col:
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
            key="stock_prepare_export_v700",
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
                "⬇ Descargar Excel",
                data=export_bytes,
                file_name="Stock_General_Filtrado.xlsx",
                mime=(
                    "application/"
                    "vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                use_container_width=True,
                key="stock_download_v700",
            )

    # --------------------------------------------------------
    # TABLE
    # --------------------------------------------------------
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=520,
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
            "Familia": st.column_config.TextColumn(
                "Familia",
                width="medium",
            ),
            "Subfamilia": st.column_config.TextColumn(
                "Subfamilia",
                width="medium",
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

    # --------------------------------------------------------
    # PRODUCT DETAIL
    # --------------------------------------------------------
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
        render_html(
            """
            <div class="sg-section-head sg-detail-head">
                <div>
                    <strong>Detalle por producto</strong>
                    <span>Distribución del SKU seleccionado por bodega</span>
                </div>
            </div>
            """
        )

        code = st.selectbox(
            "Seleccionar SKU",
            codes,
            key="stock_detail_v700",
        )

        sku = inventory[
            inventory["Código"]
            .astype(str)
            .eq(str(code))
        ].copy()

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
            movement = (
                _series_num(
                    sku,
                    "Disponible",
                ).ne(0)
                |
                _series_num(
                    sku,
                    "Stock físico",
                ).ne(0)
                |
                _series_num(
                    sku,
                    "Por llegar",
                ).ne(0)
                |
                _series_num(
                    sku,
                    "Por despachar",
                ).ne(0)
            )

            sku_detail = sku[
                movement
            ].copy()

            if sku_detail.empty:
                sku_detail = sku.copy()

            product_name = (
                str(sku["Producto"].iloc[0])
                if "Producto" in sku.columns
                else str(code)
            )

            render_html(
                f"""
                <div class="sg-detail">
                    <div class="sg-detail-title">
                        <div>
                            <span>SKU {code}</span>
                            <strong>{product_name}</strong>
                        </div>
                    </div>

                    <div class="sg-detail-grid">
                        <div>
                            <span>Disponible</span>
                            <strong>{_fmt_int(_series_num(sku, "Disponible").sum())}</strong>
                        </div>
                        <div>
                            <span>Stock físico</span>
                            <strong>{_fmt_int(_series_num(sku, "Stock físico").sum())}</strong>
                        </div>
                        <div>
                            <span>Por llegar</span>
                            <strong>{_fmt_int(_series_num(sku, "Por llegar").sum())}</strong>
                        </div>
                        <div>
                            <span>Por despachar</span>
                            <strong>{_fmt_int(_series_num(sku, "Por despachar").sum())}</strong>
                        </div>
                    </div>
                </div>
                """
            )

            detail_columns = [
                col
                for col in [
                    "Bodega",
                    "Stock físico",
                    "Disponible",
                    "Por llegar",
                    "Por despachar",
                ]
                if col in sku_detail.columns
            ]

            st.dataframe(
                sku_detail[
                    detail_columns
                ],
                hide_index=True,
                use_container_width=True,
                height=min(
                    350,
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
