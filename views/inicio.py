

from datetime import date, timedelta
from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from ui.components import render_html
from utils.numbers import format_clp


# ============================================================
# HELPERS
# ============================================================

def _num(df: pd.DataFrame | None, column: str) -> pd.Series:
    if df is None:
        return pd.Series(dtype="float64")
    if column not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0.0)


def _money(value: float) -> str:
    return format_clp(float(value))


def _fmt_int(value: float | int) -> str:
    try:
        return f"{int(round(float(value))):,}".replace(",", ".")
    except Exception:
        return "0"


def _find_col(df: pd.DataFrame | None, candidates: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    lookup = {
        str(col).strip().lower(): col
        for col in df.columns
    }

    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lookup:
            return lookup[key]

    return None


def _find_contains(df: pd.DataFrame | None, tokens: list[str]) -> str | None:
    if df is None or df.empty:
        return None

    for col in df.columns:
        key = str(col).strip().lower()
        if any(token.lower() in key for token in tokens):
            return col

    return None


def _normalize_sku(series: pd.Series) -> pd.Series:
    return (
        series
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )


def _period_from_sales(sales: pd.DataFrame | None) -> tuple[date, date]:
    if sales is None or sales.empty or "Fecha_dt" not in sales.columns:
        end = date.today()
        return end - timedelta(days=30), end

    valid = pd.to_datetime(
        sales["Fecha_dt"],
        errors="coerce",
    ).dropna()

    if valid.empty:
        end = date.today()
    else:
        end = valid.max().date()

    return end - timedelta(days=30), end


def _prepare_sales(
    sales: pd.DataFrame | None,
    start: date,
    end: date,
) -> pd.DataFrame:
    if sales is None or sales.empty:
        return pd.DataFrame()

    work = sales.copy()

    if "Fecha_dt" not in work.columns:
        return pd.DataFrame()

    work["Fecha_dt"] = pd.to_datetime(
        work["Fecha_dt"],
        errors="coerce",
    )

    work = work[
        work["Fecha_dt"].notna()
        & (work["Fecha_dt"].dt.date >= start)
        & (work["Fecha_dt"].dt.date <= end)
    ].copy()

    if work.empty:
        return work

    if "Grupo comercial" in work.columns:
        allowed = {
            "Factura",
            "Boleta",
            "Nota de crédito",
        }
        work = work[
            work["Grupo comercial"].isin(allowed)
        ].copy()

    if "VentaMonto_num" not in work.columns:
        work["VentaMonto_num"] = 0.0

    work["VentaMonto_num"] = pd.to_numeric(
        work["VentaMonto_num"],
        errors="coerce",
    ).fillna(0.0).abs()

    work["VentaFirmadaConIVA"] = work["VentaMonto_num"]

    if "Grupo comercial" in work.columns:
        credit_mask = work["Grupo comercial"].eq(
            "Nota de crédito"
        )
        work.loc[
            credit_mask,
            "VentaFirmadaConIVA",
        ] *= -1

    if "Cantidad_num" not in work.columns:
        work["Cantidad_num"] = 0.0

    work["Cantidad_num"] = pd.to_numeric(
        work["Cantidad_num"],
        errors="coerce",
    ).fillna(0.0).abs()

    work["CantidadFirmada"] = work["Cantidad_num"]

    if "Grupo comercial" in work.columns:
        credit_mask = work["Grupo comercial"].eq(
            "Nota de crédito"
        )
        work.loc[
            credit_mask,
            "CantidadFirmada",
        ] *= -1

    if "SKU" in work.columns:
        work["SKU"] = _normalize_sku(work["SKU"])

    return work


def _channel_column(sales: pd.DataFrame | None) -> str | None:
    col = _find_col(
        sales,
        [
            "Marketplace",
            "MarketPlace",
            "Canal",
            "Tienda",
            "Origen",
        ],
    )

    if col:
        return col

    return _find_contains(
        sales,
        [
            "marketplace",
            "canal",
            "tienda",
            "origen",
        ],
    )


def _apply_channel(
    sales: pd.DataFrame,
    channel_col: str | None,
    channel_value: str,
) -> pd.DataFrame:
    if (
        sales is None
        or sales.empty
        or not channel_col
        or channel_col not in sales.columns
        or channel_value == "Todos"
    ):
        return sales

    values = (
        sales[channel_col]
        .fillna("Sin canal")
        .astype(str)
        .str.strip()
        .replace("", "Sin canal")
    )

    return sales[
        values.eq(channel_value)
    ].copy()


def _delta_text(
    current: float,
    previous: float,
    suffix: str = "",
) -> tuple[str, str]:
    if previous == 0:
        if current == 0:
            return "Sin variación", "neutral"
        return "Sin base comparable", "neutral"

    delta = ((current - previous) / abs(previous)) * 100

    if delta > 0.05:
        return f"▲ {abs(delta):.1f}%{suffix}", "positive"

    if delta < -0.05:
        return f"▼ {abs(delta):.1f}%{suffix}", "negative"

    return f"• {abs(delta):.1f}%{suffix}", "neutral"


def _status_counts(cons: pd.DataFrame) -> dict[str, int]:
    state = cons.get(
        "Estado",
        pd.Series("", index=cons.index),
    ).fillna("").astype(str)

    return {
        "healthy": int(
            state.eq("🟢 Disponible").sum()
        ),
        "low": int(
            state.eq("🟡 Stock bajo").sum()
        ),
        "zero": int(
            state.isin(
                [
                    "🔴 Sin stock",
                    "🔴 Negativo",
                ]
            ).sum()
        ),
        "risk": int(
            state.eq("🟠 Riesgo despacho").sum()
        ),
    }


def _daily_sales(sales: pd.DataFrame) -> pd.DataFrame:
    if sales is None or sales.empty:
        return pd.DataFrame()

    daily = (
        sales.assign(
            Día=sales["Fecha_dt"].dt.floor("D")
        )
        .groupby("Día", as_index=False)
        .agg(
            Venta=("VentaFirmadaConIVA", "sum"),
            Unidades=("CantidadFirmada", "sum"),
        )
        .sort_values("Día")
    )

    return daily


def _marketplace_data(
    sales: pd.DataFrame,
    channel_col: str | None,
) -> pd.DataFrame:
    if (
        sales is None
        or sales.empty
        or not channel_col
        or channel_col not in sales.columns
    ):
        return pd.DataFrame()

    work = sales.copy()

    work["CanalDashboard"] = (
        work[channel_col]
        .fillna("Sin canal")
        .astype(str)
        .str.strip()
        .replace("", "Sin canal")
    )

    result = (
        work.groupby(
            "CanalDashboard",
            as_index=False,
        )["VentaFirmadaConIVA"]
        .sum()
        .rename(
            columns={
                "CanalDashboard": "Canal",
                "VentaFirmadaConIVA": "Venta",
            }
        )
        .sort_values(
            "Venta",
            ascending=False,
        )
    )

    return result


def _top_products(
    stock: pd.DataFrame | None,
    sales: pd.DataFrame,
    limit: int = 6,
) -> pd.DataFrame:
    if (
        sales is None
        or sales.empty
        or "SKU" not in sales.columns
    ):
        return pd.DataFrame()

    work = (
        sales.groupby(
            "SKU",
            as_index=False,
        )
        .agg(
            Unidades=("CantidadFirmada", "sum"),
            Venta=("VentaFirmadaConIVA", "sum"),
        )
    )

    work["Unidades"] = work["Unidades"].clip(lower=0)

    work = work.sort_values(
        ["Unidades", "Venta"],
        ascending=False,
    ).head(limit)

    if (
        stock is not None
        and not stock.empty
        and "Código" in stock.columns
    ):
        stock_names = stock.copy()
        stock_names["SKU"] = _normalize_sku(
            stock_names["Código"]
        )

        if "Producto" not in stock_names.columns:
            stock_names["Producto"] = stock_names["SKU"]

        names = (
            stock_names[
                [
                    "SKU",
                    "Producto",
                ]
            ]
            .drop_duplicates("SKU")
        )

        work = work.merge(
            names,
            on="SKU",
            how="left",
        )

    if "Producto" not in work.columns:
        work["Producto"] = work["SKU"]

    work["Producto"] = (
        work["Producto"]
        .fillna(work["SKU"])
        .astype(str)
    )

    return work


def _operational_table(
    cons: pd.DataFrame,
    sales_30: pd.DataFrame,
) -> pd.DataFrame:
    if cons is None or cons.empty:
        return pd.DataFrame()

    stock = cons.copy()

    if "Código" not in stock.columns:
        return pd.DataFrame()

    stock["SKU"] = _normalize_sku(
        stock["Código"]
    )

    if "Producto" not in stock.columns:
        stock["Producto"] = stock["SKU"]

    if "Disponible" not in stock.columns:
        stock["Disponible"] = 0

    stock["Disponible"] = pd.to_numeric(
        stock["Disponible"],
        errors="coerce",
    ).fillna(0)

    stock_columns = [
        "SKU",
        "Producto",
        "Disponible",
    ]

    if "Estado" in stock.columns:
        stock_columns.append("Estado")

    stock = (
        stock[stock_columns]
        .drop_duplicates("SKU")
    )

    if (
        sales_30 is not None
        and not sales_30.empty
        and "SKU" in sales_30.columns
    ):
        demand = (
            sales_30.groupby(
                "SKU",
                as_index=False,
            )
            .agg(
                Venta30=("VentaFirmadaConIVA", "sum"),
                Unidades30=("CantidadFirmada", "sum"),
            )
        )

        demand["Unidades30"] = demand[
            "Unidades30"
        ].clip(lower=0)

        stock = stock.merge(
            demand,
            on="SKU",
            how="left",
        )

    if "Venta30" not in stock.columns:
        stock["Venta30"] = 0.0

    if "Unidades30" not in stock.columns:
        stock["Unidades30"] = 0.0

    stock["Venta30"] = pd.to_numeric(
        stock["Venta30"],
        errors="coerce",
    ).fillna(0.0)

    stock["Unidades30"] = pd.to_numeric(
        stock["Unidades30"],
        errors="coerce",
    ).fillna(0.0)

    daily_demand = stock["Unidades30"] / 30.0

    stock["Cobertura"] = (
        stock["Disponible"]
        / daily_demand.where(
            daily_demand > 0
        )
    )

    def priority(row: pd.Series) -> tuple[int, str]:
        available = float(row["Disponible"])
        demand30 = float(row["Unidades30"])
        coverage = row["Cobertura"]

        if demand30 > 0 and available <= 0:
            return 1, "🔴 Crítico"

        if (
            demand30 > 0
            and pd.notna(coverage)
            and coverage <= 7
        ):
            return 2, "🔴 Crítico"

        if demand30 > 0 and available <= 5:
            return 3, "🟠 Reponer"

        if (
            demand30 > 0
            and pd.notna(coverage)
            and coverage <= 15
        ):
            return 4, "🟡 Atención"

        if demand30 == 0 and available > 0:
            return 6, "⚪ Sin venta 30d"

        return 5, "🟢 Saludable"

    priorities = stock.apply(
        priority,
        axis=1,
        result_type="expand",
    )

    stock["PrioridadOrden"] = priorities[0]
    stock["Prioridad"] = priorities[1]

    stock["Cobertura días"] = stock["Cobertura"].apply(
        lambda value: (
            "—"
            if pd.isna(value)
            else f"{value:.1f}"
        )
    )

    stock["Stock"] = (
        stock["Disponible"]
        .round()
        .astype(int)
    )

    stock["Unidades 30d"] = (
        stock["Unidades30"]
        .round()
        .astype(int)
    )

    stock["Ventas 30d"] = stock["Venta30"].apply(
        _money
    )

    result = (
        stock.sort_values(
            [
                "PrioridadOrden",
                "Unidades30",
                "Disponible",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .head(15)
        [
            [
                "Prioridad",
                "SKU",
                "Producto",
                "Stock",
                "Unidades 30d",
                "Ventas 30d",
                "Cobertura días",
            ]
        ]
    )

    return result


def _kpi_card(
    label: str,
    value: str,
    helper: str,
    icon: str,
    tone: str = "lime",
    delta: str | None = None,
    delta_tone: str = "neutral",
) -> str:
    delta_html = ""

    if delta:
        delta_html = (
            f"<span class='mx-kpi-delta {delta_tone}'>"
            f"{escape(delta)}"
            f"</span>"
        )

    return f"""
    <div class="mx-kpi">
        <div class="mx-kpi-top">
            <div class="mx-kpi-icon {tone}">
                {escape(icon)}
            </div>
            {delta_html}
        </div>
        <div class="mx-kpi-label">{escape(label)}</div>
        <div class="mx-kpi-value">{escape(value)}</div>
        <div class="mx-kpi-helper">{escape(helper)}</div>
    </div>
    """


# ============================================================
# RENDER
# ============================================================

def render(ctx):
    raw = ctx.get("stock_normalized")
    cons = ctx.get("stock_consolidated")
    sales_df = ctx.get("sales_df")
    stock_meta = ctx.get("stock_meta") or {}
    sales_meta = ctx.get("sales_meta") or {}

    default_start, default_end = _period_from_sales(
        sales_df
    )

    if "home_period" not in st.session_state:
        st.session_state.home_period = (
            default_start,
            default_end,
        )

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    render_html(
        """
        <div class="mx-home-head">
            <div>
                <div class="mx-home-eyebrow">
                    MARITEX · CONTROL DE INVENTARIO
                </div>
                <div class="mx-home-title">
                    Panel ejecutivo
                </div>
                <div class="mx-home-subtitle">
                    Ventas, disponibilidad y alertas operacionales
                    en una sola vista.
                </div>
            </div>
            <div class="mx-home-live">
                <span></span>
                Datos de esta sesión
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # FILTER BAR
    # --------------------------------------------------------

    channel_col = _channel_column(sales_df)

    filter_cols = st.columns(
        [1.7, 1.0, 0.7],
        gap="small",
    )

    with filter_cols[0]:
        period = st.date_input(
            "Período",
            value=st.session_state.home_period,
            key="home_period_picker",
            format="DD/MM/YYYY",
        )

        if (
            isinstance(period, (tuple, list))
            and len(period) == 2
        ):
            start, end = period
        else:
            start = end = period

        st.session_state.home_period = (
            start,
            end,
        )

    channel_value = "Todos"

    with filter_cols[1]:
        if (
            channel_col
            and sales_df is not None
            and not sales_df.empty
        ):
            channel_options = (
                sales_df[channel_col]
                .fillna("Sin canal")
                .astype(str)
                .str.strip()
                .replace("", "Sin canal")
                .drop_duplicates()
                .sort_values()
                .tolist()
            )

            channel_value = st.selectbox(
                "Canal / Marketplace",
                ["Todos"] + channel_options,
                key="home_channel",
            )
        else:
            st.selectbox(
                "Canal / Marketplace",
                ["Todos"],
                disabled=True,
                key="home_channel_disabled",
            )

    with filter_cols[2]:
        st.markdown(
            """
            <div class="mx-source-status">
                <span>FUENTES</span>
                <strong>ERP Stock + Ventas</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------
    # DATA PREPARATION
    # --------------------------------------------------------

    current_sales = _prepare_sales(
        sales_df,
        start,
        end,
    )

    current_sales = _apply_channel(
        current_sales,
        channel_col,
        channel_value,
    )

    days = max(
        (end - start).days + 1,
        1,
    )

    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(
        days=days - 1
    )

    previous_sales = _prepare_sales(
        sales_df,
        prev_start,
        prev_end,
    )

    previous_sales = _apply_channel(
        previous_sales,
        channel_col,
        channel_value,
    )

    current_revenue = float(
        current_sales.get(
            "VentaFirmadaConIVA",
            pd.Series(dtype="float64"),
        ).sum()
    )

    previous_revenue = float(
        previous_sales.get(
            "VentaFirmadaConIVA",
            pd.Series(dtype="float64"),
        ).sum()
    )

    current_units_sold = max(
        float(
            current_sales.get(
                "CantidadFirmada",
                pd.Series(dtype="float64"),
            ).sum()
        ),
        0.0,
    )

    previous_units_sold = max(
        float(
            previous_sales.get(
                "CantidadFirmada",
                pd.Series(dtype="float64"),
            ).sum()
        ),
        0.0,
    )

    sales_delta, sales_delta_tone = _delta_text(
        current_revenue,
        previous_revenue,
    )

    units_delta, units_delta_tone = _delta_text(
        current_units_sold,
        previous_units_sold,
    )

    if cons is None or cons.empty:
        render_html(
            """
            <div class="mx-empty">
                <div class="mx-empty-icon">!</div>
                <div>
                    <strong>No hay inventario consolidado disponible.</strong>
                    <span>
                        Carga o conecta ERP Stock para habilitar
                        indicadores y alertas operacionales.
                    </span>
                </div>
            </div>
            """
        )

        if not current_sales.empty:
            render_html(
                f"""
                <div class="mx-sales-only">
                    Ventas del período:
                    <strong>{_money(current_revenue)}</strong>
                </div>
                """
            )

        return

    counts = _status_counts(cons)

    stock_units = int(
        round(
            _num(
                cons,
                "Disponible",
            )
            .clip(lower=0)
            .sum()
        )
    )

    sku_total = (
        int(cons["Código"].nunique())
        if "Código" in cons.columns
        else len(cons)
    )

    low = counts["low"]
    zero = counts["zero"]
    risk = counts["risk"]
    healthy = counts["healthy"]

    # --------------------------------------------------------
    # KPI ROW
    # --------------------------------------------------------

    kpis = "".join(
        [
            _kpi_card(
                "VENTAS DEL PERÍODO",
                _money(current_revenue),
                f"{days} días seleccionados",
                "$",
                "lime",
                sales_delta,
                sales_delta_tone,
            ),
            _kpi_card(
                "UNIDADES VENDIDAS",
                _fmt_int(current_units_sold),
                "venta neta en unidades",
                "↗",
                "blue",
                units_delta,
                units_delta_tone,
            ),
            _kpi_card(
                "STOCK DISPONIBLE",
                _fmt_int(stock_units),
                f"{_fmt_int(sku_total)} SKU consolidados",
                "▦",
                "purple",
            ),
            _kpi_card(
                "STOCK BAJO",
                _fmt_int(low),
                "SKU con ≤ 5 unidades",
                "!",
                "orange",
            ),
            _kpi_card(
                "SIN STOCK",
                _fmt_int(zero),
                "SKU sin disponibilidad",
                "×",
                "red",
            ),
        ]
    )

    render_html(
        f"""
        <div class="mx-kpi-grid">
            {kpis}
        </div>
        """
    )

    # --------------------------------------------------------
    # MAIN ROW
    # --------------------------------------------------------

    left, right = st.columns(
        [1.85, 1.0],
        gap="medium",
    )

    with left:
        with st.container(border=True):
            render_html(
                """
                <div class="mx-card-head">
                    <div>
                        <strong>Ventas diarias</strong>
                        <span>Evolución del período seleccionado</span>
                    </div>
                </div>
                """
            )

            daily = _daily_sales(
                current_sales
            )

            if daily.empty:
                render_html(
                    """
                    <div class="mx-chart-empty">
                        No hay ventas suficientes para
                        construir la evolución diaria.
                    </div>
                    """
                )
            else:
                chart = (
                    alt.Chart(daily)
                    .mark_area(
                        line={
                            "color": "#1f2937",
                            "strokeWidth": 2.4,
                        },
                        color={
                            "x1": 1,
                            "y1": 1,
                            "x2": 1,
                            "y2": 0,
                            "gradient": "linear",
                            "stops": [
                                {
                                    "offset": 0,
                                    "color": "#ffffff",
                                },
                                {
                                    "offset": 1,
                                    "color": "#d8ff00",
                                },
                            ],
                        },
                        opacity=0.48,
                    )
                    .encode(
                        x=alt.X(
                            "Día:T",
                            title=None,
                            axis=alt.Axis(
                                format="%d %b",
                                labelColor="#7b8490",
                                domain=False,
                                tickColor="#e8ebef",
                            ),
                        ),
                        y=alt.Y(
                            "Venta:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7b8490",
                                domain=False,
                                gridColor="#eef1f4",
                                format="~s",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Día:T",
                                title="Fecha",
                                format="%d/%m/%Y",
                            ),
                            alt.Tooltip(
                                "Venta:Q",
                                title="Ventas",
                                format=",.0f",
                            ),
                        ],
                    )
                    .properties(
                        height=300
                    )
                )

                st.altair_chart(
                    chart,
                    use_container_width=True,
                )

            render_html(
                f"""
                <div class="mx-chart-foot">
                    <div>
                        <span>Venta período</span>
                        <strong>{_money(current_revenue)}</strong>
                    </div>
                    <div>
                        <span>Promedio diario</span>
                        <strong>{_money(current_revenue / days)}</strong>
                    </div>
                    <div>
                        <span>Unidades</span>
                        <strong>{_fmt_int(current_units_sold)}</strong>
                    </div>
                </div>
                """
            )

    with right:
        with st.container(border=True):
            render_html(
                """
                <div class="mx-card-head">
                    <div>
                        <strong>Estado del inventario</strong>
                        <span>Distribución actual por condición</span>
                    </div>
                </div>
                """
            )

            status_df = pd.DataFrame(
                {
                    "Estado": [
                        "Disponible",
                        "Stock bajo",
                        "Riesgo despacho",
                        "Sin stock",
                    ],
                    "SKU": [
                        healthy,
                        low,
                        risk,
                        zero,
                    ],
                }
            )

            status_df = status_df[
                status_df["SKU"] > 0
            ].copy()

            if status_df.empty:
                render_html(
                    """
                    <div class="mx-chart-empty compact">
                        No hay estados disponibles.
                    </div>
                    """
                )
            else:
                donut = (
                    alt.Chart(status_df)
                    .mark_arc(
                        innerRadius=62,
                        outerRadius=93,
                        cornerRadius=4,
                    )
                    .encode(
                        theta=alt.Theta(
                            "SKU:Q"
                        ),
                        color=alt.Color(
                            "Estado:N",
                            scale=alt.Scale(
                                domain=[
                                    "Disponible",
                                    "Stock bajo",
                                    "Riesgo despacho",
                                    "Sin stock",
                                ],
                                range=[
                                    "#80c700",
                                    "#f4b942",
                                    "#f28c28",
                                    "#e84b4b",
                                ],
                            ),
                            legend=None,
                        ),
                        tooltip=[
                            "Estado:N",
                            alt.Tooltip(
                                "SKU:Q",
                                format=",.0f",
                            ),
                        ],
                    )
                    .properties(
                        height=220
                    )
                )

                st.altair_chart(
                    donut,
                    use_container_width=True,
                )

            total_status = max(
                healthy + low + risk + zero,
                1,
            )

            render_html(
                f"""
                <div class="mx-status-grid">
                    <div>
                        <i class="green"></i>
                        <span>Disponible</span>
                        <strong>{healthy / total_status * 100:.0f}%</strong>
                    </div>
                    <div>
                        <i class="yellow"></i>
                        <span>Stock bajo</span>
                        <strong>{low / total_status * 100:.0f}%</strong>
                    </div>
                    <div>
                        <i class="orange"></i>
                        <span>Riesgo</span>
                        <strong>{risk / total_status * 100:.0f}%</strong>
                    </div>
                    <div>
                        <i class="red"></i>
                        <span>Sin stock</span>
                        <strong>{zero / total_status * 100:.0f}%</strong>
                    </div>
                </div>
                """
            )

    # --------------------------------------------------------
    # ALERTS
    # --------------------------------------------------------

    sales_30 = _prepare_sales(
        sales_df,
        end - timedelta(days=29),
        end,
    )

    sales_30 = _apply_channel(
        sales_30,
        channel_col,
        channel_value,
    )

    operational = _operational_table(
        cons,
        sales_30,
    )

    critical_count = (
        int(
            operational["Prioridad"]
            .astype(str)
            .str.contains("Crítico", regex=False)
            .sum()
        )
        if not operational.empty
        else 0
    )

    alert_cards = f"""
    <div class="mx-alert-grid">
        <div class="mx-alert critical">
            <div class="mx-alert-icon">×</div>
            <div>
                <span>QUIEBRE DE STOCK</span>
                <strong>{_fmt_int(zero)} SKU sin stock</strong>
                <small>Revisar productos con demanda reciente.</small>
            </div>
        </div>
        <div class="mx-alert warning">
            <div class="mx-alert-icon">!</div>
            <div>
                <span>REPOSICIÓN</span>
                <strong>{_fmt_int(low)} SKU con stock bajo</strong>
                <small>Disponibilidad igual o inferior a 5 unidades.</small>
            </div>
        </div>
        <div class="mx-alert attention">
            <div class="mx-alert-icon">↻</div>
            <div>
                <span>COBERTURA</span>
                <strong>{_fmt_int(critical_count)} SKU críticos</strong>
                <small>Prioridad calculada con ventas de los últimos 30 días.</small>
            </div>
        </div>
    </div>
    """

    render_html(alert_cards)

    # --------------------------------------------------------
    # SECONDARY ROW
    # --------------------------------------------------------

    c1, c2 = st.columns(
        [1.15, 1.0],
        gap="medium",
    )

    with c1:
        with st.container(border=True):
            render_html(
                """
                <div class="mx-card-head">
                    <div>
                        <strong>Top productos</strong>
                        <span>Mayor venta en unidades</span>
                    </div>
                </div>
                """
            )

            top = _top_products(
                raw,
                current_sales,
                limit=6,
            )

            if top.empty:
                render_html(
                    """
                    <div class="mx-chart-empty compact">
                        No hay ventas por SKU disponibles.
                    </div>
                    """
                )
            else:
                max_units = max(
                    float(top["Unidades"].max()),
                    1.0,
                )

                rows = ""

                for idx, row in enumerate(
                    top.itertuples(index=False),
                    start=1,
                ):
                    units_value = max(
                        float(row.Unidades),
                        0.0,
                    )

                    width = min(
                        units_value / max_units * 100,
                        100,
                    )

                    product = escape(
                        str(row.Producto)[:55]
                    )

                    sku = escape(
                        str(row.SKU)
                    )

                    rows += f"""
                    <div class="mx-product-row">
                        <div class="mx-rank">{idx:02d}</div>
                        <div class="mx-product-main">
                            <strong>{product}</strong>
                            <span>SKU {sku}</span>
                            <div class="mx-mini-bar">
                                <i style="width:{width:.1f}%"></i>
                            </div>
                        </div>
                        <div class="mx-product-value">
                            <strong>{_fmt_int(units_value)}</strong>
                            <span>uds.</span>
                        </div>
                    </div>
                    """

                render_html(
                    f"""
                    <div class="mx-product-list">
                        {rows}
                    </div>
                    """
                )

    with c2:
        with st.container(border=True):
            render_html(
                """
                <div class="mx-card-head">
                    <div>
                        <strong>Ventas por canal</strong>
                        <span>Participación sobre la venta del período</span>
                    </div>
                </div>
                """
            )

            channel_data = _marketplace_data(
                current_sales,
                channel_col,
            )

            if channel_data.empty:
                render_html(
                    """
                    <div class="mx-chart-empty compact">
                        El ERP Ventas no contiene una columna
                        de canal o marketplace reconocible.
                    </div>
                    """
                )
            else:
                channel_chart = (
                    alt.Chart(
                        channel_data.head(8)
                    )
                    .mark_bar(
                        cornerRadiusEnd=5,
                        color="#22272e",
                    )
                    .encode(
                        y=alt.Y(
                            "Canal:N",
                            sort="-x",
                            title=None,
                            axis=alt.Axis(
                                labelLimit=160,
                                labelColor="#66717c",
                                domain=False,
                                ticks=False,
                            ),
                        ),
                        x=alt.X(
                            "Venta:Q",
                            title=None,
                            axis=alt.Axis(
                                labelColor="#7b8490",
                                domain=False,
                                gridColor="#eef1f4",
                                format="~s",
                            ),
                        ),
                        tooltip=[
                            alt.Tooltip(
                                "Canal:N",
                                title="Canal",
                            ),
                            alt.Tooltip(
                                "Venta:Q",
                                title="Venta",
                                format=",.0f",
                            ),
                        ],
                    )
                    .properties(
                        height=285
                    )
                )

                st.altair_chart(
                    channel_chart,
                    use_container_width=True,
                )

    # --------------------------------------------------------
    # OPERATIONAL TABLE
    # --------------------------------------------------------

    with st.container(border=True):
        render_html(
            """
            <div class="mx-card-head mx-table-head">
                <div>
                    <strong>Productos que requieren atención</strong>
                    <span>
                        Priorización según stock actual y demanda
                        de los últimos 30 días
                    </span>
                </div>
            </div>
            """
        )

        if operational.empty:
            render_html(
                """
                <div class="mx-chart-empty compact">
                    No hay información suficiente para
                    construir la tabla operacional.
                </div>
                """
            )
        else:
            st.dataframe(
                operational,
                use_container_width=True,
                hide_index=True,
                height=470,
                column_config={
                    "Prioridad": st.column_config.TextColumn(
                        "Estado",
                        width="small",
                    ),
                    "SKU": st.column_config.TextColumn(
                        "SKU",
                        width="small",
                    ),
                    "Producto": st.column_config.TextColumn(
                        "Producto",
                        width="large",
                    ),
                    "Stock": st.column_config.NumberColumn(
                        "Stock",
                        format="%d",
                    ),
                    "Unidades 30d": st.column_config.NumberColumn(
                        "Unidades 30d",
                        format="%d",
                    ),
                    "Ventas 30d": st.column_config.TextColumn(
                        "Ventas 30d",
                    ),
                    "Cobertura días": st.column_config.TextColumn(
                        "Cobertura días",
                    ),
                },
            )

    # --------------------------------------------------------
    # DATA FOOTER
    # --------------------------------------------------------

    stock_source = (
        stock_meta.get("loaded_at")
        or stock_meta.get("filename")
        or "Fuente activa"
    )

    sales_source = (
        sales_meta.get("loaded_at")
        or sales_meta.get("filename")
        or "Fuente activa"
    )

    render_html(
        f"""
        <div class="mx-data-foot">
            <div>
                <span class="ok"></span>
                <strong>Stock:</strong>
                {escape(str(stock_source))}
            </div>
            <div>
                <span class="ok"></span>
                <strong>Ventas:</strong>
                {escape(str(sales_source))}
            </div>
        </div>
        """
    )