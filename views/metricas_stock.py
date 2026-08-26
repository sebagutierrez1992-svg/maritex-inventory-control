import re

import altair as alt
import pandas as pd
import streamlit as st

from analytics.stock_metrics import consolidate_inventory
from ui.components import render_html


# ============================================================
# HELPERS
# ============================================================

def _num(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0.0, index=df.index)
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _first_existing(df: pd.DataFrame, candidates) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _normalize_key(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\.0$", "", regex=True)
    )


def _prepare_search(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["_search_codigo"] = (
        out["Código"].fillna("").astype(str).str.lower()
        if "Código" in out.columns
        else ""
    )
    out["_search_producto"] = (
        out["Producto"].fillna("").astype(str).str.lower()
        if "Producto" in out.columns
        else ""
    )
    return out


def _priority_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()
    available = _num(out, "Disponible")
    incoming = _num(out, "Por llegar")
    outgoing = _num(out, "Por despachar")
    state = out["Estado"].fillna("").astype(str)

    out["Prioridad_score"] = 0
    out["Prioridad"] = "Baja"
    out["Acción sugerida"] = "Monitorear"

    negative = state.eq("🔴 Negativo")
    zero = state.eq("🔴 Sin stock")
    risk = state.eq("🟠 Riesgo despacho") | ((outgoing > available) & (outgoing > 0))
    low = state.eq("🟡 Stock bajo")
    replenishment = state.eq("🔵 Por llegar")

    out.loc[replenishment, ["Prioridad_score", "Prioridad", "Acción sugerida"]] = [
        50, "Media", "Esperar reposición"
    ]
    out.loc[low, ["Prioridad_score", "Prioridad", "Acción sugerida"]] = [
        75, "Media", "Revisar reposición"
    ]
    out.loc[risk, ["Prioridad_score", "Prioridad", "Acción sugerida"]] = [
        90, "Alta", "Revisar despacho / reponer"
    ]
    out.loc[zero & (incoming > 0), ["Prioridad_score", "Prioridad", "Acción sugerida"]] = [
        94, "Alta", "Priorizar recepción"
    ]
    out.loc[zero & (incoming <= 0), ["Prioridad_score", "Prioridad", "Acción sugerida"]] = [
        98, "Alta", "Comprar / trasladar"
    ]
    out.loc[negative, ["Prioridad_score", "Prioridad", "Acción sugerida"]] = [
        100, "Alta", "Regularizar inventario"
    ]

    return (
        out[out["Prioridad_score"] > 0]
        .sort_values(["Prioridad_score", "Disponible"], ascending=[False, True])
        .reset_index(drop=True)
    )


def _sales_intelligence(
    inventory: pd.DataFrame,
    sales_df: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict]:
    """
    Cruza stock consolidado con ventas cuando el ERP Ventas contiene
    una llave SKU/código utilizable y una fecha.

    Es deliberadamente tolerante a distintos nombres de columnas.
    Si no encuentra una llave compatible, devuelve métricas vacías
    sin romper la página.
    """
    empty_meta = {
        "enabled": False,
        "reason": "ERP Ventas no disponible.",
        "sales_code_col": None,
        "sales_qty_col": None,
        "sales_amount_col": None,
        "sales_date_col": None,
    }

    if sales_df is None or sales_df.empty or inventory is None or inventory.empty:
        return inventory.copy(), empty_meta

    sales = sales_df.copy()

    code_col = _first_existing(
        sales,
        [
            "Código", "Codigo", "SKU", "Sku", "CodProducto",
            "CodArticulo", "CodigoProducto", "Código Producto",
            "Codigo Producto",
        ],
    )
    date_col = _first_existing(
        sales,
        ["Fecha_dt", "Fecha", "FechaEmision", "Fecha Emision", "Fecha emisión"],
    )
    qty_col = _first_existing(
        sales,
        [
            "CantidadFirmada", "Cantidad", "Cantidad_num", "Unidades",
            "Qty", "Cantidad Vendida",
        ],
    )
    amount_col = _first_existing(
        sales,
        [
            "VentaFirmadaConIVA", "VentaFirmadaSinIVA",
            "Venta Neta", "VentaNeta", "Total", "Monto",
        ],
    )

    if code_col is None:
        meta = empty_meta.copy()
        meta["reason"] = (
            "ERP Ventas está cargado, pero no se encontró una columna SKU/código "
            "compatible para cruzarlo con Stock."
        )
        return inventory.copy(), meta

    sales["_sku_key"] = _normalize_key(sales[code_col])

    if date_col is not None:
        sales["_fecha"] = pd.to_datetime(sales[date_col], errors="coerce")
        max_date = sales["_fecha"].max()
    else:
        sales["_fecha"] = pd.NaT
        max_date = pd.NaT

    if qty_col is not None:
        sales["_qty"] = pd.to_numeric(sales[qty_col], errors="coerce").fillna(0.0)
    else:
        # Si no hay cantidad, contamos documentos/líneas como proxy de movimiento.
        sales["_qty"] = 1.0

    if amount_col is not None:
        sales["_amount"] = pd.to_numeric(sales[amount_col], errors="coerce").fillna(0.0)
    else:
        sales["_amount"] = 0.0

    if pd.notna(max_date):
        start_30 = max_date - pd.Timedelta(days=29)
        start_90 = max_date - pd.Timedelta(days=89)
        s30 = sales[sales["_fecha"].between(start_30, max_date, inclusive="both")].copy()
        s90 = sales[sales["_fecha"].between(start_90, max_date, inclusive="both")].copy()
    else:
        s30 = sales.copy()
        s90 = sales.copy()

    g30 = (
        s30.groupby("_sku_key", as_index=False)
        .agg(Venta_30d=("_amount", "sum"), Unidades_30d=("_qty", "sum"))
    )
    g90 = (
        s90.groupby("_sku_key", as_index=False)
        .agg(Venta_90d=("_amount", "sum"), Unidades_90d=("_qty", "sum"))
    )

    out = inventory.copy()
    out["_sku_key"] = _normalize_key(out["Código"])
    out = out.merge(g30, on="_sku_key", how="left").merge(g90, on="_sku_key", how="left")

    for col in ["Venta_30d", "Unidades_30d", "Venta_90d", "Unidades_90d"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)

    # Evitar cantidades negativas por notas de crédito al calcular demanda.
    out["Unidades_30d_demanda"] = out["Unidades_30d"].clip(lower=0)
    out["Venta_90d_abc"] = out["Venta_90d"].clip(lower=0)

    daily = out["Unidades_30d_demanda"] / 30.0
    available = _num(out, "Disponible").clip(lower=0)

    out["Cobertura días"] = 0.0
    moving = daily > 0
    out.loc[moving, "Cobertura días"] = available[moving] / daily[moving]
    out.loc[~moving & (available > 0), "Cobertura días"] = 9999.0

    def coverage_label(days, units_30):
        if units_30 <= 0:
            return "Sin venta 30d"
        if days < 15:
            return "< 15 días"
        if days < 30:
            return "15-29 días"
        if days <= 90:
            return "30-90 días"
        return "> 90 días"

    out["Rango cobertura"] = [
        coverage_label(d, u)
        for d, u in zip(out["Cobertura días"], out["Unidades_30d_demanda"])
    ]

    # ABC por venta 90 días.
    abc_base = out.sort_values("Venta_90d_abc", ascending=False).copy()
    total_sales = float(abc_base["Venta_90d_abc"].sum())
    if total_sales > 0:
        abc_base["_cum"] = abc_base["Venta_90d_abc"].cumsum() / total_sales
        abc_base["ABC"] = "C"
        abc_base.loc[abc_base["_cum"] <= 0.80, "ABC"] = "A"
        abc_base.loc[(abc_base["_cum"] > 0.80) & (abc_base["_cum"] <= 0.95), "ABC"] = "B"
        # El primer SKU que cruza 80% sigue siendo A.
        if not abc_base.empty:
            first_over_80 = abc_base.index[abc_base["_cum"] > 0.80]
            if len(first_over_80):
                abc_base.loc[first_over_80[0], "ABC"] = "A"
    else:
        abc_base["ABC"] = "Sin clasificación"

    out = out.drop(columns=["ABC"], errors="ignore").merge(
        abc_base[["_sku_key", "ABC"]], on="_sku_key", how="left"
    )

    meta = {
        "enabled": True,
        "reason": "",
        "sales_code_col": code_col,
        "sales_qty_col": qty_col,
        "sales_amount_col": amount_col,
        "sales_date_col": date_col,
        "max_date": max_date,
    }
    return out.drop(columns=["_sku_key"], errors="ignore"), meta


def _clp(value: float) -> str:
    value = float(value or 0)
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.1f} mil MM"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.1f} MM"
    return f"${value:,.0f}"


# ============================================================
# RENDER
# ============================================================

def render(ctx):
    raw = ctx.get("stock_normalized")
    cons = ctx.get("stock_consolidated")
    df = ctx.get("stock_df")
    sales_df = ctx.get("sales_df")
    meta = ctx.get("stock_meta") or {}

    render_html(
        """
        <div class="gm-page-head">
            <div class="gm-page-title">Métricas de Stock</div>
            <div class="gm-page-subtitle">
                Salud, cobertura, reposición y oportunidades del inventario.
            </div>
        </div>
        """
    )

    if raw is None or raw.empty:
        if df is None or df.empty:
            st.info("Carga ERP Stock desde Plantillas.")
        else:
            st.warning(
                "El contexto optimizado de Stock no está disponible. "
                "Verifica que app.py entregue stock_normalized y stock_consolidated."
            )
        return

    if cons is None or cons.empty:
        st.warning("No existe inventario consolidado para analizar.")
        return

    raw = _prepare_search(raw)
    cons = cons.copy()

    render_html(
        f"""
        <div class="metrics-stock-v60-top">
            <span>Análisis / Métricas de Stock</span>
            <span>Última actualización:
                <strong>{meta.get("loaded_at", "sesión actual")}</strong>
            </span>
        </div>
        """
    )

    # ========================================================
    # FILTROS
    # ========================================================

    f1, f2, f3, f4 = st.columns([2, 1, 1, 1], gap="small")

    with f1:
        search = st.text_input(
            "Buscar",
            placeholder="Buscar SKU o producto",
            label_visibility="collapsed",
            key="ms_search_v700",
        )

    with f2:
        fams = sorted(
            cons["Familia"].replace("", pd.NA).dropna().astype(str).unique().tolist()
        )
        sf = st.multiselect(
            "Familia",
            fams,
            placeholder="Familia",
            label_visibility="collapsed",
            key="ms_fam_v700",
        )

    with f3:
        sts = sorted(
            cons["Estado"].fillna("").astype(str).replace("", pd.NA).dropna().unique().tolist()
        )
        ss = st.multiselect(
            "Estado",
            sts,
            placeholder="Estado",
            label_visibility="collapsed",
            key="ms_status_v700",
        )

    with f4:
        whs = sorted(
            raw["Bodega"].replace("", pd.NA).dropna().astype(str).unique().tolist()
        )
        sw = st.multiselect(
            "Bodega",
            whs,
            placeholder="Bodega",
            label_visibility="collapsed",
            key="ms_wh_v700",
        )

    # ========================================================
    # FILTRADO
    # ========================================================

    fr = raw.copy()

    if search:
        term = search.lower().strip()
        fr = fr[
            fr["_search_codigo"].str.contains(term, regex=False)
            | fr["_search_producto"].str.contains(term, regex=False)
        ]

    if sf:
        fr = fr[fr["Familia"].fillna("").astype(str).isin(sf)]

    if sw:
        fr = fr[fr["Bodega"].fillna("").astype(str).isin(sw)]

    fr_clean = fr.drop(
        columns=["_search_codigo", "_search_producto"],
        errors="ignore",
    )

    has_base_filters = bool(search or sf or sw)
    filtered = consolidate_inventory(fr_clean) if has_base_filters else cons.copy()

    if ss:
        filtered = filtered[
            filtered["Estado"].fillna("").astype(str).isin(ss)
        ].copy()

    if filtered.empty:
        st.info("No existen registros para los filtros seleccionados.")
        return

    # ========================================================
    # INTELIGENCIA DE VENTAS
    # ========================================================

    intel, sales_meta = _sales_intelligence(filtered, sales_df)

    state = filtered["Estado"].fillna("").astype(str)
    sku = int(filtered["Código"].nunique())
    units = int(round(_num(filtered, "Disponible").sum()))
    incoming = int(round(_num(filtered, "Por llegar").sum()))
    low = int(state.eq("🟡 Stock bajo").sum())
    zero = int(state.isin(["🔴 Sin stock", "🔴 Negativo"]).sum())
    risk = int(state.eq("🟠 Riesgo despacho").sum())
    ok = int(state.eq("🟢 Disponible").sum())

    # Valor de inventario usando Precio disponible en ERP Stock.
    inventory_value = float(
        (_num(filtered, "Disponible").clip(lower=0) * _num(filtered, "Precio")).sum()
    )

    # ========================================================
    # KPI EJECUTIVOS
    # ========================================================

    if sales_meta["enabled"]:
        moving = intel["Unidades_30d_demanda"] > 0
        total_demand_30 = float(intel["Unidades_30d_demanda"].sum())
        coverage_total = (
            units / (total_demand_30 / 30.0)
            if total_demand_30 > 0
            else 0.0
        )
        abc_a_zero = int(
            (
                intel["ABC"].eq("A")
                & (_num(intel, "Disponible") <= 0)
            ).sum()
        )
        overstock = int(
            (
                (intel["Cobertura días"] > 90)
                & moving
                & (_num(intel, "Disponible") > 0)
            ).sum()
        )
    else:
        coverage_total = 0.0
        abc_a_zero = 0
        overstock = 0

    render_html(
        f"""
        <div class="metrics-stock-v60-kpis">
            <div class="metrics-stock-v60-kpi">
                <span>Unidades disponibles</span>
                <strong>{units:,}</strong>
                <small>inventario vendible</small>
            </div>
            <div class="metrics-stock-v60-kpi">
                <span>Valor inventario</span>
                <strong>{_clp(inventory_value)}</strong>
                <small>disponible × precio ERP</small>
            </div>
            <div class="metrics-stock-v60-kpi">
                <span>Sin stock</span>
                <strong>{zero:,}</strong>
                <small>SKU sin disponibilidad</small>
            </div>
            <div class="metrics-stock-v60-kpi">
                <span>Stock crítico</span>
                <strong>{low + risk:,}</strong>
                <small>bajo + riesgo despacho</small>
            </div>
            <div class="metrics-stock-v60-kpi">
                <span>Por llegar</span>
                <strong>{incoming:,}</strong>
                <small>unidades en reposición</small>
            </div>
            <div class="metrics-stock-v60-kpi">
                <span>Cobertura</span>
                <strong>{"{:.0f}".format(coverage_total) if sales_meta["enabled"] and coverage_total else "—"}</strong>
                <small>{"días estimados" if sales_meta["enabled"] and coverage_total else "requiere cruce ventas"}</small>
            </div>
        </div>
        """
    )

    # ========================================================
    # ALERTAS EJECUTIVAS
    # ========================================================

    house = fr_clean[
        fr_clean["Bodega"]
        .fillna("")
        .astype(str)
        .str.upper()
        .str.contains("CASA MATRIZ", regex=False)
    ].copy()

    house_cons = consolidate_inventory(house) if not house.empty else pd.DataFrame()
    other = fr_clean[
        ~fr_clean.index.isin(house.index)
    ].copy()
    other_cons = consolidate_inventory(other) if not other.empty else pd.DataFrame()

    transfer_count = 0
    transfer_df = pd.DataFrame()
    if not house_cons.empty and not other_cons.empty:
        h = house_cons[["Código", "Producto", "Disponible"]].rename(
            columns={"Disponible": "Casa Matriz"}
        )
        o = other_cons[["Código", "Disponible"]].rename(
            columns={"Disponible": "Otras bodegas"}
        )
        transfer_df = h.merge(o, on="Código", how="left")
        transfer_df["Otras bodegas"] = pd.to_numeric(
            transfer_df["Otras bodegas"], errors="coerce"
        ).fillna(0)
        transfer_df = transfer_df[
            (pd.to_numeric(transfer_df["Casa Matriz"], errors="coerce").fillna(0) <= 0)
            & (transfer_df["Otras bodegas"] > 0)
        ].sort_values("Otras bodegas", ascending=False)
        transfer_count = len(transfer_df)

    render_html(
        f"""
        <div class="metrics-stock-v60-insights">
            <div class="gm-card-title">Alertas ejecutivas</div>
            <div class="metrics-stock-v60-insights-grid">
                <div><strong>{zero:,} SKU</strong> están sin stock o negativos.</div>
                <div><strong>{transfer_count:,} SKU</strong> agotados en Casa Matriz tienen stock en otras bodegas.</div>
                <div><strong>{abc_a_zero if sales_meta["enabled"] else "—"}</strong> {"SKU Clase A están agotados." if sales_meta["enabled"] else "Clase A disponible al cruzar SKU con ERP Ventas."}</div>
                <div><strong>{overstock if sales_meta["enabled"] else "—"}</strong> {"SKU tienen más de 90 días de cobertura." if sales_meta["enabled"] else "Sobrestock disponible al cruzar SKU con ERP Ventas."}</div>
            </div>
        </div>
        """
    )

    # ========================================================
    # SALUD + FAMILIA
    # ========================================================

    c1, c2 = st.columns(2, gap="medium")

    with c1:
        st.markdown("#### Salud del inventario")
        status_df = pd.DataFrame(
            {
                "Estado": [
                    "Disponible",
                    "Stock bajo",
                    "Riesgo despacho",
                    "Sin stock / negativo",
                ],
                "SKU": [ok, low, risk, zero],
            }
        )
        status_df = status_df[status_df["SKU"] > 0]

        if not status_df.empty:
            chart = (
                alt.Chart(status_df)
                .mark_arc(innerRadius=58, outerRadius=88)
                .encode(
                    theta=alt.Theta("SKU:Q"),
                    color=alt.Color("Estado:N", legend=alt.Legend(title=None)),
                    tooltip=[
                        alt.Tooltip("Estado:N", title="Estado"),
                        alt.Tooltip("SKU:Q", title="SKU", format=","),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True)

    with c2:
        st.markdown("#### Stock disponible por familia")
        fam = (
            filtered.assign(
                Familia=filtered["Familia"].replace("", "Sin familia")
            )
            .groupby("Familia", as_index=False)["Disponible"]
            .sum()
        )
        fam["Disponible"] = pd.to_numeric(fam["Disponible"], errors="coerce").fillna(0)
        fam = fam.sort_values("Disponible", ascending=False).head(10)

        if not fam.empty:
            chart = (
                alt.Chart(fam)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    y=alt.Y("Familia:N", sort="-x", title=None),
                    x=alt.X("Disponible:Q", title=None),
                    tooltip=[
                        alt.Tooltip("Familia:N"),
                        alt.Tooltip("Disponible:Q", format=","),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True)

    # ========================================================
    # BODEGAS + REPOSICIÓN
    # ========================================================

    c3, c4 = st.columns(2, gap="medium")

    with c3:
        st.markdown("#### Distribución por bodega")
        wh = (
            fr_clean.assign(Bodega=fr_clean["Bodega"].replace("", "Sin bodega"))
            .groupby("Bodega", as_index=False)["Disponible"]
            .sum()
        )
        wh["Disponible"] = pd.to_numeric(wh["Disponible"], errors="coerce").fillna(0)
        wh = wh.sort_values("Disponible", ascending=False).head(10)

        if not wh.empty:
            chart = (
                alt.Chart(wh)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    y=alt.Y("Bodega:N", sort="-x", title=None),
                    x=alt.X("Disponible:Q", title=None),
                    tooltip=[
                        alt.Tooltip("Bodega:N"),
                        alt.Tooltip("Disponible:Q", format=","),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True)

    with c4:
        st.markdown("#### Reposición por bodega")
        inc = (
            fr_clean.groupby("Bodega", as_index=False)["Por llegar"].sum()
            if "Por llegar" in fr_clean.columns
            else pd.DataFrame()
        )
        if not inc.empty:
            inc["Por llegar"] = pd.to_numeric(inc["Por llegar"], errors="coerce").fillna(0)
            inc = inc[inc["Por llegar"] > 0].sort_values(
                "Por llegar", ascending=False
            ).head(10)

        if not inc.empty:
            chart = (
                alt.Chart(inc)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    y=alt.Y("Bodega:N", sort="-x", title=None),
                    x=alt.X("Por llegar:Q", title=None),
                    tooltip=[
                        alt.Tooltip("Bodega:N"),
                        alt.Tooltip("Por llegar:Q", format=","),
                    ],
                )
                .properties(height=280)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No existen unidades por llegar en la selección.")

    # ========================================================
    # COBERTURA + ABC
    # ========================================================

    render_html('<div class="gm-section-title">Cobertura, rotación y clasificación ABC</div>')

    if sales_meta["enabled"]:
        c5, c6 = st.columns(2, gap="medium")

        with c5:
            coverage = (
                intel.groupby("Rango cobertura", as_index=False)
                .agg(SKU=("Código", "nunique"))
            )
            order = ["< 15 días", "15-29 días", "30-90 días", "> 90 días", "Sin venta 30d"]
            coverage["orden"] = coverage["Rango cobertura"].map(
                {name: i for i, name in enumerate(order)}
            )
            coverage = coverage.sort_values("orden")

            chart = (
                alt.Chart(coverage)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    y=alt.Y("Rango cobertura:N", sort=order, title=None),
                    x=alt.X("SKU:Q", title=None),
                    tooltip=["Rango cobertura", alt.Tooltip("SKU:Q", format=",")],
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)

        with c6:
            abc = (
                intel.groupby("ABC", as_index=False)
                .agg(
                    SKU=("Código", "nunique"),
                    Venta_90d=("Venta_90d", "sum"),
                )
            )
            chart = (
                alt.Chart(abc)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("ABC:N", title="Clasificación"),
                    y=alt.Y("SKU:Q", title="SKU"),
                    tooltip=[
                        "ABC",
                        alt.Tooltip("SKU:Q", format=","),
                        alt.Tooltip("Venta_90d:Q", title="Venta 90d", format=",.0f"),
                    ],
                )
                .properties(height=260)
            )
            st.altair_chart(chart, use_container_width=True)

        action = intel.copy()
        action["Disponible"] = _num(action, "Disponible")
        action["Cobertura días"] = pd.to_numeric(
            action["Cobertura días"], errors="coerce"
        ).fillna(0)

        def action_label(row):
            if row["ABC"] == "A" and row["Disponible"] <= 0:
                return "Comprar / trasladar urgente"
            if row["Unidades_30d_demanda"] > 0 and row["Cobertura días"] < 15:
                return "Reponer"
            if row["Unidades_30d_demanda"] > 0 and row["Cobertura días"] > 90:
                return "Revisar sobrestock"
            if row["Unidades_30d_demanda"] <= 0 and row["Disponible"] > 0:
                return "Revisar baja rotación"
            return "Monitorear"

        action["Acción"] = action.apply(action_label, axis=1)
        action = action[action["Acción"] != "Monitorear"].copy()

        priority_order = {
            "Comprar / trasladar urgente": 1,
            "Reponer": 2,
            "Revisar sobrestock": 3,
            "Revisar baja rotación": 4,
        }
        action["_order"] = action["Acción"].map(priority_order).fillna(99)
        action = action.sort_values(
            ["_order", "Venta_90d"],
            ascending=[True, False],
        ).head(20)

        st.markdown("#### Productos que requieren acción comercial")
        columns = [
            c for c in [
                "Código", "Producto", "ABC", "Disponible",
                "Unidades_30d", "Venta_90d", "Cobertura días", "Acción",
            ]
            if c in action.columns
        ]
        st.dataframe(
            action[columns],
            hide_index=True,
            use_container_width=True,
            height=480,
            column_config={
                "Código": st.column_config.TextColumn("SKU"),
                "Producto": st.column_config.TextColumn("Producto", width="large"),
                "Disponible": st.column_config.NumberColumn("Disponible", format="%d"),
                "Unidades_30d": st.column_config.NumberColumn("Venta uds. 30d", format="%.0f"),
                "Venta_90d": st.column_config.NumberColumn("Venta $ 90d", format="$%.0f"),
                "Cobertura días": st.column_config.NumberColumn("Cobertura", format="%.1f días"),
            },
        )

        if sales_meta.get("sales_qty_col") is None:
            st.caption(
                "Nota: ERP Ventas no contiene una columna de cantidad reconocida; "
                "la cobertura usa cantidad de líneas como proxy. Conviene mapear la "
                "columna real de unidades vendidas para máxima precisión."
            )

    else:
        st.info(
            "Cobertura, rotación y ABC están preparados, pero no se pudieron activar: "
            f"{sales_meta['reason']}"
        )

    # ========================================================
    # TRASPASOS CASA MATRIZ
    # ========================================================

    render_html(
        f'<div class="gm-section-title">Oportunidades de redistribución · {transfer_count:,}</div>'
    )

    if not transfer_df.empty:
        st.caption(
            "SKU sin disponibilidad en Casa Matriz que sí tienen unidades disponibles en otras bodegas."
        )
        st.dataframe(
            transfer_df.head(20),
            hide_index=True,
            use_container_width=True,
            height=min(500, 44 + 38 * min(20, len(transfer_df))),
            column_config={
                "Código": st.column_config.TextColumn("SKU"),
                "Producto": st.column_config.TextColumn("Producto", width="large"),
                "Casa Matriz": st.column_config.NumberColumn("Casa Matriz", format="%d"),
                "Otras bodegas": st.column_config.NumberColumn("Otras bodegas", format="%d"),
            },
        )
    else:
        st.success("No se detectaron oportunidades de traslado hacia Casa Matriz.")

    # ========================================================
    # PRIORIDAD OPERATIVA
    # ========================================================

    critical = _priority_table(filtered)
    render_html(
        f'<div class="gm-section-title">Prioridad operativa · {len(critical):,} SKU</div>'
    )

    if not critical.empty:
        cols = [
            c for c in [
                "Código", "Producto", "Disponible", "Por llegar",
                "Por despachar", "Estado", "Prioridad", "Acción sugerida",
            ]
            if c in critical.columns
        ]
        st.dataframe(
            critical[cols].head(20),
            hide_index=True,
            use_container_width=True,
            height=500,
            column_config={
                "Código": st.column_config.TextColumn("SKU"),
                "Producto": st.column_config.TextColumn("Producto", width="large"),
                "Disponible": st.column_config.NumberColumn("Disponible", format="%d"),
                "Por llegar": st.column_config.NumberColumn("Por llegar", format="%d"),
                "Por despachar": st.column_config.NumberColumn("Por despachar", format="%d"),
            },
        )
    else:
        st.success("No se detectaron SKU críticos.")

    # ========================================================
    # DETALLE COMPLETO
    # ========================================================

    with st.expander("Ver detalle completo del inventario", expanded=False):
        detail = fr_clean.copy()

        if ss:
            allowed_codes = set(
                filtered["Código"].dropna().astype(str).tolist()
            )
            detail = detail[
                detail["Código"].fillna("").astype(str).isin(allowed_codes)
            ].copy()

        numeric_columns = [
            "Stock físico", "Disponible", "Por llegar", "Por despachar", "Precio"
        ]
        for col in numeric_columns:
            if col in detail.columns:
                detail[col] = pd.to_numeric(detail[col], errors="coerce").fillna(0)

        movement = pd.Series(False, index=detail.index)
        for col in ["Stock físico", "Disponible", "Por llegar", "Por despachar"]:
            if col in detail.columns:
                movement = movement | detail[col].ne(0)

        detail = detail[movement].copy()

        detail_columns = [
            c for c in [
                "Estado", "Código", "Producto", "Familia", "Subfamilia",
                "Bodega", "Stock físico", "Disponible", "Por llegar",
                "Por despachar", "Precio",
            ]
            if c in detail.columns
        ]

        detail = detail[detail_columns].sort_values(
            [c for c in ["Código", "Bodega"] if c in detail_columns]
        )

        st.caption(
            f"{detail['Código'].nunique() if 'Código' in detail.columns else 0:,} SKU · "
            f"{detail['Bodega'].replace('', pd.NA).dropna().nunique() if 'Bodega' in detail.columns else 0:,} bodegas · "
            f"{int(_num(detail, 'Disponible').sum()):,} unidades disponibles"
        )

        st.dataframe(
            detail,
            hide_index=True,
            use_container_width=True,
            height=520,
            column_config={
                "Código": st.column_config.TextColumn("SKU"),
                "Producto": st.column_config.TextColumn("Producto", width="large"),
                "Bodega": st.column_config.TextColumn("Bodega", width="medium"),
                "Stock físico": st.column_config.NumberColumn("Stock físico", format="%d"),
                "Disponible": st.column_config.NumberColumn("Disponible", format="%d"),
                "Por llegar": st.column_config.NumberColumn("Por llegar", format="%d"),
                "Por despachar": st.column_config.NumberColumn("Por despachar", format="%d"),
                "Precio": st.column_config.NumberColumn("Precio", format="$%d"),
            },
        )