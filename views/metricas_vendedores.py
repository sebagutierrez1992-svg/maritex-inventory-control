from datetime import datetime
import re

import altair as alt
import pandas as pd
import streamlit as st

from analytics.sales_metrics import (
    build_seller_summary,
    calculate_commercial_totals,
    filter_sales,
    previous_period_bounds,
)
from ui.components import render_html
from utils.dates import available_months, month_bounds, month_label_es
from utils.excel import dataframe_to_excel_bytes
from utils.numbers import format_clp


def render(ctx):
    # ============================================================
    # HEADER V60
    # ============================================================
    render_html("""
    <div class="seller-head">
        <div>
            <div class="seller-title">Métricas Vendedores</div>
            <div class="seller-subtitle">
                Analiza ventas, cumplimiento y desempeño comercial por vendedor.
            </div>
        </div>
        <div class="seller-rule">● Venta final = Facturas + Boletas − NC</div>
    </div>
    """)

    base_df = ctx.get("sales_df")

    if base_df is None or base_df.empty:
        st.info(
            "No existe una fuente ERP Ventas activa. "
            "Cárgala desde Plantillas → Fuentes ERP → ERP Ventas."
        )
        return

    commercial_all = base_df[
        base_df["Grupo comercial"].isin(
            ["Factura", "Boleta", "Nota de crédito"]
        )
    ].copy()

    if commercial_all.empty:
        st.warning("No se encontraron Facturas, Boletas o Notas de crédito.")
        return

    # ============================================================
    # FILTROS V60
    # ============================================================
    seller_months = available_months(commercial_all, date_col="Fecha_dt")

    if not seller_months:
        st.warning("No existen meses válidos en ERP Ventas.")
        return

    seller_month_labels = [month_label_es(m) for m in seller_months]
    seller_month_map = dict(zip(seller_month_labels, seller_months))

    f1, f2, f3, f4 = st.columns([1.15, 1, 1.2, 1.2])

    with f1:
        selected_seller_month_label = st.selectbox(
            "Mes",
            seller_month_labels,
            index=0,
            key="seller_month_filter_v60_modular",
            help="Selecciona el mes base para el análisis comercial.",
        )

        selected_seller_month = seller_month_map[
            selected_seller_month_label
        ]

        seller_month_start, seller_month_end = month_bounds(
            selected_seller_month
        )

        seller_month_rows_for_default = commercial_all[
            (commercial_all["Fecha_dt"].dt.date >= seller_month_start)
            & (commercial_all["Fecha_dt"].dt.date <= seller_month_end)
        ]

        seller_default_end = seller_month_end

        if (
            not seller_month_rows_for_default.empty
            and seller_month_rows_for_default["Fecha_dt"].notna().any()
        ):
            seller_default_end = min(
                seller_month_end,
                seller_month_rows_for_default["Fecha_dt"].max().date(),
            )

        seller_day_range = st.date_input(
            "Días",
            value=(seller_month_start, seller_default_end),
            min_value=seller_month_start,
            max_value=seller_month_end,
            key=f"seller_day_range_v60_modular_{selected_seller_month}",
            help="Filtra un rango de días dentro del mes seleccionado.",
        )

    with f2:
        vat_percent = st.number_input(
            "IVA %",
            min_value=0.0,
            max_value=100.0,
            value=19.0,
            step=1.0,
            key="seller_vat_rate_v60_modular",
        )
        vat_rate = float(vat_percent) / 100.0

    with f3:
        type_options = sorted(
            commercial_all["TipoDocto"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        type_filter = st.multiselect(
            "Tipo de documento",
            type_options,
            placeholder="Facturas + Boletas + NC",
            key="seller_document_type_filter_v60_modular",
        )

    with f4:
        seller_options = sorted(
            commercial_all["Vendedor"]
            .fillna("Sin vendedor")
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )

        seller_filter = st.multiselect(
            "Vendedor",
            seller_options,
            placeholder="Todos",
            key="seller_filter_v60_modular",
        )

    g1, g2 = st.columns([1, 1.4])

    with g1:
        warehouse_options = (
            sorted(
                commercial_all["Bodega"]
                .fillna("Sin bodega")
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
            if "Bodega" in commercial_all.columns
            else []
        )

        warehouse_filter = st.multiselect(
            "Bodega",
            warehouse_options,
            placeholder="Todas",
            key="seller_warehouse_filter_v60_modular",
        )

    with g2:
        client_filter = st.text_input(
            "Cliente",
            placeholder="Buscar cliente y mostrar sus documentos…",
            key="seller_client_filter_v60_modular",
        )

    current_start = seller_month_start
    current_end = seller_default_end

    if (
        seller_day_range
        and isinstance(seller_day_range, (tuple, list))
        and len(seller_day_range) == 2
    ):
        current_start, current_end = seller_day_range

    view = filter_sales(
        commercial_all,
        start_date=current_start,
        end_date=current_end,
        sellers=seller_filter,
        warehouses=warehouse_filter,
        document_types=type_filter,
        client_text=client_filter,
    )

    # ============================================================
    # COBERTURA DE DATOS V60
    # ============================================================
    month_rows = commercial_all[
        (commercial_all["Fecha_dt"].dt.date >= current_start)
        & (commercial_all["Fecha_dt"].dt.date <= current_end)
    ]

    month_data_max = (
        month_rows["Fecha_dt"].max().date()
        if not month_rows.empty and month_rows["Fecha_dt"].notna().any()
        else None
    )

    if month_data_max is not None:
        data_status_class = (
            "sales-data-status-warn"
            if month_data_max < current_end
            else "sales-data-status-ok"
        )

        note = (
            "El total utiliza todas las ventas disponibles dentro del rango seleccionado."
            if month_data_max < current_end
            else "El ERP cubre el rango de días seleccionado."
        )

        render_html(f"""
        <div class="sales-data-status {data_status_class}">
            <div>
                <span>Mes seleccionado</span>
                <strong>{selected_seller_month_label}</strong>
            </div>
            <div>
                <span>Días analizados</span>
                <strong>{pd.Timestamp(current_start).strftime("%d/%m")} – {pd.Timestamp(current_end).strftime("%d/%m/%Y")}</strong>
            </div>
            <div>
                <span>Datos ERP disponibles hasta</span>
                <strong>{pd.Timestamp(month_data_max).strftime("%d/%m/%Y")}</strong>
            </div>
            <div class="sales-data-status-note">{note}</div>
        </div>
        """)

    # ============================================================
    # TOTALES + REGLA
    # ============================================================
    totals = calculate_commercial_totals(
        view,
        vat_rate=vat_rate,
    )

    render_html(f"""
    <div class="sales-rule-strip">
        <strong>Regla aplicada:</strong>
        Facturas y Boletas suman al total. Las Notas de crédito se restan.
        El valor sin IVA se calcula usando una tasa de {vat_percent:.0f}%.
        <strong>Haz clic en cualquier indicador para ver qué documentos lo componen.</strong>
    </div>
    """)

    if "selected_sales_metric_v60_modular" not in st.session_state:
        st.session_state.selected_sales_metric_v60_modular = None

    k1, k2, k3, k4 = st.columns(4, gap="small")

    with k1:
        render_html('<div class="sales-kpi-button-wrap">')
        if st.button(
            f"Ventas brutas con IVA\n\n{format_clp(totals['ventas_brutas_con_iva'])}\n\nFacturas + Boletas antes de NC",
            key="sales_metric_gross_v60_modular",
            use_container_width=True,
        ):
            st.session_state.selected_sales_metric_v60_modular = "gross"
        render_html("</div>")

    with k2:
        render_html('<div class="sales-kpi-button-wrap credit">')
        if st.button(
            f"Notas de crédito\n\n− {format_clp(totals['notas_credito_con_iva'])}\n\nMonto descontado",
            key="sales_metric_credits_v60_modular",
            use_container_width=True,
        ):
            st.session_state.selected_sales_metric_v60_modular = "credits"
        render_html("</div>")

    with k3:
        render_html('<div class="sales-kpi-button-wrap main">')
        if st.button(
            f"Venta final con IVA\n\n{format_clp(totals['venta_neta_con_iva'])}\n\nFacturas + Boletas − NC",
            key="sales_metric_net_vat_v60_modular",
            use_container_width=True,
        ):
            st.session_state.selected_sales_metric_v60_modular = "net_vat"
        render_html("</div>")

    with k4:
        render_html('<div class="sales-kpi-button-wrap main">')
        if st.button(
            f"Venta final sin IVA\n\n{format_clp(totals['venta_neta_sin_iva'])}\n\nIVA neto: {format_clp(totals['iva_neto'])}",
            key="sales_metric_net_no_vat_v60_modular",
            use_container_width=True,
        ):
            st.session_state.selected_sales_metric_v60_modular = "net_no_vat"
        render_html("</div>")

    # ============================================================
    # META V60
    # ============================================================
    goal_col1, goal_col2 = st.columns([1, 1])

    with goal_col1:
        sales_goal = st.number_input(
            "Meta de ventas",
            min_value=0,
            value=int(
                st.session_state.get(
                    "seller_sales_goal_v60_modular",
                    20_000_000,
                )
            ),
            step=100_000,
            key="seller_sales_goal_input_v60_modular",
            help="Meta del período filtrado.",
        )
        st.session_state["seller_sales_goal_v60_modular"] = int(sales_goal)

    with goal_col2:
        goal_basis = st.selectbox(
            "Base para medir la meta",
            ["Venta final con IVA", "Venta final sin IVA"],
            index=0,
            key="seller_goal_basis_v60_modular",
        )

    goal_current = float(
        totals["venta_neta_con_iva"]
        if goal_basis == "Venta final con IVA"
        else totals["venta_neta_sin_iva"]
    )

    goal_value = float(sales_goal)
    goal_missing = max(goal_value - goal_current, 0)
    goal_over = max(goal_current - goal_value, 0)

    if goal_value > 0:
        goal_progress = max(min(goal_current / goal_value, 1.0), 0.0)
        goal_progress_pct = goal_current / goal_value * 100
    else:
        goal_progress = 0.0
        goal_progress_pct = 0.0

    goal_footer = (
        "Meta superada por " + format_clp(goal_over)
        if goal_over > 0
        else "Faltan " + format_clp(goal_missing) + " para alcanzar la meta"
    )

    render_html(f"""
    <div class="seller-goal-wrap">
        <div class="seller-goal-head">
            <div>
                <div class="seller-goal-title">Cumplimiento de meta</div>
                <div class="seller-goal-sub">
                    Base: {goal_basis} · período y filtros actualmente seleccionados.
                </div>
            </div>
            <div class="seller-goal-values">
                <div class="seller-goal-item">
                    <span>Meta</span>
                    <strong>{format_clp(goal_value)}</strong>
                </div>
                <div class="seller-goal-item">
                    <span>Venta actual</span>
                    <strong>{format_clp(goal_current)}</strong>
                </div>
                <div class="seller-goal-item">
                    <span>Faltante</span>
                    <strong>{format_clp(goal_missing)}</strong>
                </div>
                <div class="seller-goal-item">
                    <span>Cumplimiento</span>
                    <strong>{goal_progress_pct:.1f}%</strong>
                </div>
            </div>
        </div>

        <div class="seller-goal-bar">
            <div class="seller-goal-fill" style="width:{goal_progress*100:.2f}%"></div>
        </div>

        <div class="seller-goal-foot">
            <span>Avance: <strong>{goal_progress_pct:.1f}%</strong></span>
            <span>{goal_footer}</span>
        </div>
    </div>
    """)

    # ============================================================
    # DETALLE KPI V60
    # ============================================================
    selected_metric = st.session_state.get(
        "selected_sales_metric_v60_modular"
    )

    if selected_metric:
        detail_view = view.copy()

        if selected_metric == "gross":
            detail_view = detail_view[
                detail_view["Grupo comercial"].isin(["Factura", "Boleta"])
            ].copy()
            detail_title = "Ventas brutas con IVA"
            detail_subtitle = (
                "Se contabilizan únicamente Facturas y Boletas. "
                "Las Notas de crédito todavía no se descuentan en este indicador."
            )

        elif selected_metric == "credits":
            detail_view = detail_view[
                detail_view["Grupo comercial"].eq("Nota de crédito")
            ].copy()
            detail_title = "Notas de crédito"
            detail_subtitle = (
                "Estos documentos se restan del total de Facturas + Boletas."
            )

        else:
            detail_view = detail_view[
                detail_view["Grupo comercial"].isin(
                    ["Factura", "Boleta", "Nota de crédito"]
                )
            ].copy()

            if selected_metric == "net_vat":
                detail_title = "Venta final con IVA"
                detail_subtitle = (
                    "Facturas y Boletas suman; las Notas de crédito restan. "
                    "El cálculo conserva IVA."
                )
            else:
                detail_title = "Venta final sin IVA"
                detail_subtitle = (
                    "Facturas y Boletas suman; las Notas de crédito restan. "
                    f"Luego se elimina el IVA usando una tasa de {vat_percent:.0f}%."
                )

        detail_view["VentaMonto_num"] = pd.to_numeric(
            detail_view["VentaMonto_num"],
            errors="coerce",
        ).fillna(0.0)

        detail_view["Impacto con IVA"] = detail_view.apply(
            lambda r: (
                -abs(float(r["VentaMonto_num"]))
                if r["Grupo comercial"] == "Nota de crédito"
                else float(r["VentaMonto_num"])
            ),
            axis=1,
        )

        detail_view["Impacto sin IVA"] = (
            detail_view["Impacto con IVA"] / (1 + vat_rate)
            if (1 + vat_rate)
            else 0.0
        )

        detail_count = (
            detail_view["Numero"].nunique()
            if "Numero" in detail_view.columns
            else len(detail_view)
        )

        signed_total_vat = float(detail_view["Impacto con IVA"].sum())
        signed_total_no_vat = float(detail_view["Impacto sin IVA"].sum())

        render_html(f"""
        <div class="sales-detail-box">
            <div class="sales-detail-title">{detail_title}</div>
            <div class="sales-detail-subtitle">
                {detail_subtitle}<br>
                <strong>{detail_count:,}</strong> documentos ·
                Total con IVA: <strong>{format_clp(signed_total_vat)}</strong> ·
                Total sin IVA: <strong>{format_clp(signed_total_no_vat)}</strong>
            </div>
        </div>
        """)

        detail_columns = [
            c for c in [
                "Fecha",
                "TipoDocto",
                "Numero",
                "RazonSocial",
                "Vendedor",
                "Bodega",
                "Grupo comercial",
                "Total",
                "TotalIngreso",
                "ReferenciaExterna",
            ]
            if c in detail_view.columns
        ]

        detail_display = detail_view[detail_columns].copy()

        detail_display["Efecto"] = detail_view["Grupo comercial"].map(
            lambda x: "− Resta" if x == "Nota de crédito" else "+ Suma"
        ).values

        detail_display["Impacto con IVA"] = (
            detail_view["Impacto con IVA"].round().astype("Int64").values
        )
        detail_display["Impacto sin IVA"] = (
            detail_view["Impacto sin IVA"].round().astype("Int64").values
        )

        if {"TipoDocto", "Numero"}.issubset(detail_display.columns):
            detail_display = detail_display.drop_duplicates(
                subset=["TipoDocto", "Numero"],
                keep="first",
            )

        st.dataframe(
            detail_display,
            hide_index=True,
            use_container_width=True,
            height=min(470, max(190, 45 + len(detail_display) * 34)),
            column_config={
                "Impacto con IVA": st.column_config.NumberColumn(
                    "Impacto con IVA",
                    format="$%d",
                ),
                "Impacto sin IVA": st.column_config.NumberColumn(
                    "Impacto sin IVA",
                    format="$%d",
                ),
                "Total": st.column_config.TextColumn("Total documento"),
            },
        )

        export_detail = dataframe_to_excel_bytes(
            detail_display,
            sheet_name="Detalle_Metrica",
        )

        e1, e2 = st.columns([1, 4])

        with e1:
            st.download_button(
                "⬇ Exportar detalle",
                data=export_detail,
                file_name=f"Detalle_{selected_metric}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_metric_detail_v60_modular_{selected_metric}",
                use_container_width=True,
            )

        with e2:
            if st.button(
                "Cerrar detalle",
                key="close_sales_metric_detail_v60_modular",
            ):
                st.session_state.selected_sales_metric_v60_modular = None
                st.rerun()

    # ============================================================
    # DOCUMENTOS DEL CLIENTE V60
    # ============================================================
    if client_filter:
        if not view.empty:
            client_names = (
                view["RazonSocial"]
                .fillna("Sin cliente")
                .astype(str)
                .str.strip()
                .drop_duplicates()
                .tolist()
            )

            client_label = (
                client_names[0]
                if len(client_names) == 1
                else f"{len(client_names)} clientes encontrados"
            )

            document_count = (
                view["Numero"].nunique()
                if "Numero" in view.columns
                else len(view)
            )

            render_html(f"""
            <div class="client-search-summary">
                <div>
                    <div class="client-search-title">
                        Documentos · {client_label}
                    </div>
                    <div class="client-search-meta">
                        Incluye Facturas, Boletas y Notas de crédito según los filtros activos.
                    </div>
                </div>
                <div class="client-search-kpis">
                    <div class="client-search-kpi">
                        <span>Documentos</span>
                        <strong>{document_count:,}</strong>
                    </div>
                    <div class="client-search-kpi">
                        <span>Venta final con IVA</span>
                        <strong>{format_clp(totals["venta_neta_con_iva"])}</strong>
                    </div>
                    <div class="client-search-kpi">
                        <span>Venta final sin IVA</span>
                        <strong>{format_clp(totals["venta_neta_sin_iva"])}</strong>
                    </div>
                </div>
            </div>
            """)

            document_columns = [
                c for c in [
                    "Fecha",
                    "TipoDocto",
                    "Numero",
                    "RazonSocial",
                    "Vendedor",
                    "Bodega",
                    "Total",
                    "TotalIngreso",
                    "Vigencia",
                    "Emitido",
                    "ReferenciaExterna",
                ]
                if c in view.columns
            ]

            client_docs = view[document_columns].copy()

            if {"TipoDocto", "Numero"}.issubset(client_docs.columns):
                client_docs = client_docs.drop_duplicates(
                    subset=["TipoDocto", "Numero"],
                    keep="first",
                )

            type_map = (
                view[["TipoDocto", "Grupo comercial"]]
                .drop_duplicates("TipoDocto")
                .set_index("TipoDocto")["Grupo comercial"]
                if "TipoDocto" in view.columns
                else pd.Series(dtype=str)
            )

            client_docs.insert(
                0,
                "Efecto",
                client_docs["TipoDocto"].map(type_map).map(
                    lambda x: "− Resta" if x == "Nota de crédito" else "+ Suma"
                ),
            )

            st.dataframe(
                client_docs,
                hide_index=True,
                use_container_width=True,
                height=min(470, max(190, 45 + len(client_docs) * 35)),
            )

            client_export = dataframe_to_excel_bytes(
                client_docs,
                sheet_name="Documentos_Cliente",
            )

            st.download_button(
                "⬇ Exportar documentos del cliente",
                data=client_export,
                file_name=(
                    "Documentos_Cliente_"
                    + re.sub(r"[^A-Za-z0-9_-]+", "_", client_filter.strip())
                    + ".xlsx"
                ),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_client_documents_v60_modular",
            )
        else:
            st.warning(
                "No existen documentos para el cliente y filtros seleccionados."
            )

    # ============================================================
    # RESUMEN POR VENDEDOR V60
    # ============================================================
    render_html('<div class="seller-section-title">Ventas por vendedor</div>')

    work = view.copy()

    if work.empty:
        st.info("No existen ventas para los filtros seleccionados.")
        return

    work["VentaMonto_num"] = pd.to_numeric(
        work["VentaMonto_num"],
        errors="coerce",
    ).fillna(0.0)

    work["Impacto con IVA"] = work.apply(
        lambda r: (
            -float(r["VentaMonto_num"])
            if r["Grupo comercial"] == "Nota de crédito"
            else float(r["VentaMonto_num"])
        ),
        axis=1,
    )

    work["Impacto sin IVA"] = (
        work["Impacto con IVA"] / (1 + vat_rate)
        if (1 + vat_rate)
        else 0.0
    )

    seller_summary = build_seller_summary(
        work,
        vat_rate=vat_rate,
    )

    basis_col = (
        "Venta_con_IVA"
        if goal_basis == "Venta final con IVA"
        else "Venta_sin_IVA"
    )

    basis_total = float(seller_summary[basis_col].sum())

    if basis_total > 0 and goal_value > 0:
        seller_summary["Meta referencia"] = (
            seller_summary[basis_col] / basis_total * goal_value
        )
    else:
        seller_summary["Meta referencia"] = 0.0

    seller_summary["Faltante meta"] = (
        seller_summary["Meta referencia"] - seller_summary[basis_col]
    ).clip(lower=0)

    seller_summary["Cumplimiento meta %"] = seller_summary.apply(
        lambda r: (
            r[basis_col] / r["Meta referencia"] * 100
            if r["Meta referencia"] > 0
            else 0.0
        ),
        axis=1,
    )

    # ============================================================
    # PERÍODO ANTERIOR V60
    # ============================================================
    overall_previous = 0.0
    overall_variation = 0.0

    prev_start, prev_end = previous_period_bounds(
        current_start,
        current_end,
    )

    if (
        prev_start is not None
        and prev_end is not None
        and "Fecha_dt" in commercial_all.columns
    ):
        prev_view = commercial_all[
            (commercial_all["Fecha_dt"] >= prev_start)
            & (commercial_all["Fecha_dt"] <= prev_end)
        ].copy()

        prev_view = filter_sales(
            prev_view,
            sellers=seller_filter,
            warehouses=warehouse_filter,
            document_types=type_filter,
            client_text=client_filter,
        )

        if not prev_view.empty:
            previous_summary = build_seller_summary(
                prev_view,
                vat_rate=vat_rate,
            )[
                ["Vendedor", "Venta_con_IVA"]
            ].rename(
                columns={"Venta_con_IVA": "Venta_anterior"}
            )

            overall_previous = float(
                previous_summary["Venta_anterior"].sum()
            )

            current_total_cmp = float(
                seller_summary["Venta_con_IVA"].sum()
            )

            overall_variation = (
                ((current_total_cmp - overall_previous) / overall_previous) * 100
                if overall_previous != 0
                else (100.0 if current_total_cmp > 0 else 0.0)
            )

            seller_summary = seller_summary.merge(
                previous_summary,
                on="Vendedor",
                how="left",
            )

            seller_summary["Venta_anterior"] = (
                seller_summary["Venta_anterior"].fillna(0)
            )

            seller_summary["Variación vs anterior %"] = seller_summary.apply(
                lambda r: (
                    (
                        (r["Venta_con_IVA"] - r["Venta_anterior"])
                        / r["Venta_anterior"]
                        * 100
                    )
                    if r["Venta_anterior"] != 0
                    else (100.0 if r["Venta_con_IVA"] > 0 else 0.0)
                ),
                axis=1,
            )
        else:
            seller_summary["Venta_anterior"] = 0.0
            seller_summary["Variación vs anterior %"] = 0.0
    else:
        seller_summary["Venta_anterior"] = 0.0
        seller_summary["Variación vs anterior %"] = 0.0

    gross_amount = float(
        work.loc[
            work["Grupo comercial"].isin(["Factura", "Boleta"]),
            "VentaMonto_num",
        ].sum()
    )

    credit_amount = float(
        work.loc[
            work["Grupo comercial"].eq("Nota de crédito"),
            "VentaMonto_num",
        ].abs().sum()
    )

    credit_rate = (
        credit_amount / gross_amount * 100
        if gross_amount > 0
        else 0.0
    )

    top_seller = (
        seller_summary.iloc[0]["Vendedor"]
        if not seller_summary.empty
        else "—"
    )

    top_seller_value = (
        float(seller_summary.iloc[0]["Venta_con_IVA"])
        if not seller_summary.empty
        else 0.0
    )

    sale_docs = work[
        work["Grupo comercial"].isin(["Factura", "Boleta"])
    ]

    avg_ticket = (
        float(sale_docs["VentaMonto_num"].sum())
        / max(int(sale_docs["Numero"].nunique()), 1)
        if "Numero" in sale_docs.columns
        else 0.0
    )

    exec1, exec2, exec3, exec4 = st.columns(4, gap="small")

    exec1.metric(
        "Mejor vendedor",
        str(top_seller),
        format_clp(top_seller_value),
    )
    exec2.metric(
        "Ticket promedio",
        format_clp(avg_ticket),
    )
    exec3.metric(
        "Variación vs período anterior",
        f"{overall_variation:+.1f}%",
    )
    exec4.metric(
        "Tasa notas de crédito",
        f"{credit_rate:.1f}%",
    )

    # ============================================================
    # INSIGHTS V60
    # ============================================================
    insights = []

    if not seller_summary.empty:
        leader = seller_summary.iloc[0]
        insights.append(
            f"🏆 {leader['Vendedor']} lidera el período con "
            f"{format_clp(leader['Venta_con_IVA'])} y "
            f"{leader['Participación %']:.1f}% de participación."
        )

        if len(seller_summary) > 1:
            movers = seller_summary.sort_values(
                "Variación vs anterior %",
                ascending=False,
            )

            best_growth = movers.iloc[0]
            worst_growth = movers.iloc[-1]

            if best_growth["Venta_anterior"] > 0:
                insights.append(
                    f"📈 Mayor crecimiento: {best_growth['Vendedor']} "
                    f"({best_growth['Variación vs anterior %']:+.1f}% vs período anterior)."
                )

            if (
                worst_growth["Venta_anterior"] > 0
                and worst_growth["Variación vs anterior %"] < 0
            ):
                insights.append(
                    f"⚠️ Mayor caída: {worst_growth['Vendedor']} "
                    f"({worst_growth['Variación vs anterior %']:+.1f}% vs período anterior)."
                )

        if credit_rate >= 5:
            insights.append(
                f"🔴 Las notas de crédito equivalen al {credit_rate:.1f}% "
                "de las ventas brutas del período."
            )
        elif credit_rate > 0:
            insights.append(
                f"↩️ Las notas de crédito equivalen al {credit_rate:.1f}% "
                "de las ventas brutas."
            )

        below_goal = int(
            (seller_summary["Cumplimiento meta %"] < 80).sum()
        )

        if below_goal:
            insights.append(
                f"🎯 {below_goal} vendedor(es) están bajo 80% "
                "de su meta de referencia."
            )

    if insights:
        render_html(
            '<div class="seller-section-title">Insights automáticos</div>'
        )
        for insight in insights[:5]:
            st.info(insight)

    # ============================================================
    # RANKING + COMPOSICIÓN V60
    # ============================================================
    rank_col, mix_col = st.columns(
        [1.3, 1],
        gap="medium",
    )

    with rank_col:
        render_html(
            '<div class="seller-card"><div class="seller-card-title">'
            'Ranking venta final con IVA</div>'
        )

        chart_data = seller_summary.head(15)

        chart = (
            alt.Chart(chart_data)
            .mark_bar(cornerRadiusEnd=5)
            .encode(
                y=alt.Y(
                    "Vendedor:N",
                    sort="-x",
                    title=None,
                ),
                x=alt.X(
                    "Venta_con_IVA:Q",
                    title=None,
                ),
                tooltip=[
                    alt.Tooltip("Vendedor:N"),
                    alt.Tooltip(
                        "Venta_con_IVA:Q",
                        title="Con IVA",
                        format=",",
                    ),
                    alt.Tooltip(
                        "Venta_sin_IVA:Q",
                        title="Sin IVA",
                        format=",",
                    ),
                    alt.Tooltip(
                        "Documentos:Q",
                        format=",",
                    ),
                ],
            )
            .properties(height=330)
        )

        st.altair_chart(
            chart,
            use_container_width=True,
        )

        render_html("</div>")

    with mix_col:
        render_html(
            '<div class="seller-card"><div class="seller-card-title">'
            'Composición documental</div>'
        )

        mix = (
            work.groupby(
                "Grupo comercial",
                as_index=False,
            )
            .agg(
                Monto=("VentaMonto_num", "sum"),
                Documentos=("Numero", "nunique"),
            )
        )

        mix["Monto"] = pd.to_numeric(
            mix["Monto"],
            errors="coerce",
        ).fillna(0).abs()

        mix_chart = (
            alt.Chart(mix)
            .mark_arc(innerRadius=65)
            .encode(
                theta="Monto:Q",
                color=alt.Color(
                    "Grupo comercial:N",
                    legend=alt.Legend(title=None),
                ),
                tooltip=[
                    alt.Tooltip("Grupo comercial:N"),
                    alt.Tooltip("Monto:Q", format=","),
                    alt.Tooltip("Documentos:Q", format=","),
                ],
            )
            .properties(height=330)
        )

        st.altair_chart(
            mix_chart,
            use_container_width=True,
        )

        render_html("</div>")

    # ============================================================
    # EVOLUCIÓN V60
    # ============================================================
    render_html(
        '<div class="seller-section-title">Evolución de venta neta</div>'
    )

    if "Fecha_dt" in work.columns and work["Fecha_dt"].notna().any():
        daily = (
            work.dropna(subset=["Fecha_dt"])
            .assign(
                Dia=lambda d: d["Fecha_dt"].dt.floor("D")
            )
            .groupby("Dia", as_index=False)
            .agg(
                Venta_con_IVA=("Impacto con IVA", "sum"),
                Venta_sin_IVA=("Impacto sin IVA", "sum"),
            )
            .sort_values("Dia")
        )

        evo = (
            alt.Chart(daily)
            .transform_fold(
                ["Venta_con_IVA", "Venta_sin_IVA"],
                as_=["Serie", "Monto"],
            )
            .mark_line(
                point=True,
                strokeWidth=2,
            )
            .encode(
                x=alt.X(
                    "Dia:T",
                    title=None,
                    axis=alt.Axis(format="%d %b"),
                ),
                y=alt.Y(
                    "Monto:Q",
                    title=None,
                ),
                color=alt.Color(
                    "Serie:N",
                    legend=alt.Legend(
                        title=None,
                        labelExpr=(
                            "datum.label == 'Venta_con_IVA' "
                            "? 'Con IVA' : 'Sin IVA'"
                        ),
                    ),
                ),
                tooltip=[
                    alt.Tooltip(
                        "Dia:T",
                        format="%d/%m/%Y",
                    ),
                    alt.Tooltip("Serie:N"),
                    alt.Tooltip(
                        "Monto:Q",
                        format=",",
                    ),
                ],
            )
            .properties(height=300)
        )

        st.altair_chart(
            evo,
            use_container_width=True,
        )

    # ============================================================
    # TABLA V60
    # ============================================================
    render_html(
        '<div class="seller-section-title">Ranking detallado</div>'
    )

    seller_table = seller_summary.rename(
        columns={
            "Venta_con_IVA": "Venta final con IVA",
            "Venta_sin_IVA": "Venta final sin IVA",
        }
    ).copy()

    for col in [
        "Venta final con IVA",
        "Venta final sin IVA",
        "Ticket promedio",
        "Meta referencia",
        "Faltante meta",
    ]:
        if col in seller_table.columns:
            seller_table[col] = (
                seller_table[col]
                .round()
                .astype("Int64")
            )

    seller_table["Participación %"] = (
        seller_table["Participación %"].round(1)
    )

    seller_table["Cumplimiento meta %"] = (
        seller_table["Cumplimiento meta %"].round(1)
    )

    if "Venta_anterior" in seller_table.columns:
        seller_table["Venta_anterior"] = (
            seller_table["Venta_anterior"]
            .round()
            .astype("Int64")
        )

    if "Variación vs anterior %" in seller_table.columns:
        seller_table["Variación vs anterior %"] = (
            seller_table["Variación vs anterior %"].round(1)
        )

    st.dataframe(
        seller_table,
        hide_index=True,
        use_container_width=True,
        height=570,
        column_config={
            "Venta final con IVA": st.column_config.NumberColumn(
                "Venta final con IVA",
                format="$%d",
            ),
            "Venta final sin IVA": st.column_config.NumberColumn(
                "Venta final sin IVA",
                format="$%d",
            ),
            "Ticket promedio": st.column_config.NumberColumn(
                "Ticket promedio",
                format="$%d",
            ),
            "Participación %": st.column_config.NumberColumn(
                "Participación",
                format="%.1f%%",
            ),
            "Meta referencia": st.column_config.NumberColumn(
                "Meta referencia",
                format="$%d",
            ),
            "Faltante meta": st.column_config.NumberColumn(
                "Faltante meta",
                format="$%d",
            ),
            "Cumplimiento meta %": st.column_config.NumberColumn(
                "Cumplimiento meta",
                format="%.1f%%",
            ),
            "Venta_anterior": st.column_config.NumberColumn(
                "Venta período anterior",
                format="$%d",
            ),
            "Variación vs anterior %": st.column_config.NumberColumn(
                "Variación vs anterior",
                format="%.1f%%",
            ),
        },
    )

    st.caption(
        "Facturas y Boletas suman. Notas de crédito restan. "
        f"Montos sin IVA calculados con tasa {vat_percent:.0f}%."
    )
