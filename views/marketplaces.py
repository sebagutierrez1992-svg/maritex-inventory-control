

from io import BytesIO
import re
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd
import streamlit as st
from openpyxl import Workbook, load_workbook

from analytics.stock_metrics import (
    stock_view,
    consolidate_inventory,
)
from config.settings import MARKETPLACE_TEMPLATES
from ui.components import page_header, render_html


# ============================================================
# HELPERS GENERALES
# ============================================================

def _safe_int(value) -> int:
    try:
        if pd.isna(value):
            return 0
        return int(round(float(value)))
    except Exception:
        return 0




def _fmt_int(value) -> str:
    return f"{_safe_int(value):,}".replace(",", ".")


def _format_loaded_at(value) -> str:
    if value is None:
        return "actualización automática"

    text = str(value).strip()
    if not text:
        return "actualización automática"

    try:
        dt = pd.to_datetime(text, utc=True)
        if pd.isna(dt):
            return text
        dt = dt.tz_convert("America/Santiago")
        return dt.strftime("%d-%m-%Y · %H:%M")
    except Exception:
        return text


def _inject_marketplace_contrast_css():
    st.markdown(
        """
        <style>
        /* =====================================================
           MARKETPLACE · MARITEX DARK UI
           ===================================================== */
        :root {
            --mk-bg: #05080b;
            --mk-panel: #0b1117;
            --mk-panel-2: #101820;
            --mk-border: #26323d;
            --mk-text: #f6f8fa;
            --mk-muted: #9eacb9;
            --mk-yellow: #ffd400;
            --mk-green: #2ed47a;
            --mk-amber: #ffbf00;
            --mk-red: #ff4d4f;
            --mk-blue: #29a9ff;
        }

        .stApp {
            background: var(--mk-bg) !important;
        }

        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        section.main {
            background: var(--mk-bg) !important;
        }

        .block-container {
            max-width: 1500px !important;
            padding-top: 1.25rem !important;
            padding-bottom: 2.5rem !important;
        }

        /* Header */
        .mkx-page-head {
            display:flex; align-items:center; justify-content:space-between;
            gap:20px; margin:2px 0 18px 0;
        }
        .mkx-title-wrap { display:flex; align-items:center; gap:16px; }
        .mkx-brand-mark {
            width:56px; height:56px; border-radius:14px; display:flex; align-items:center;
            justify-content:center; background:linear-gradient(145deg,#1878f2,#0aa6ff);
            color:#fff; font-size:28px; font-weight:850; box-shadow:0 8px 24px rgba(0,130,255,.22);
        }
        .mkx-title { color:#fff; font-size:34px; line-height:1.05; font-weight:850; letter-spacing:-.03em; }
        .mkx-subtitle { color:var(--mk-muted); font-size:14px; margin-top:6px; }
        .mkx-live {
            display:inline-flex; align-items:center; gap:8px; padding:9px 13px;
            border:1px solid #2a3945; border-radius:999px; color:#d8e1e8;
            background:#0b1117; font-size:12px; font-weight:700;
        }
        .mkx-live i { width:8px; height:8px; border-radius:50%; background:var(--mk-green); box-shadow:0 0 0 4px rgba(46,212,122,.11); }

        /* Source bar */
        .mkx-source {
            display:grid; grid-template-columns:1.35fr 1fr; gap:0;
            background:linear-gradient(180deg,#0d141b,#091017);
            border:1px solid var(--mk-border); border-radius:16px; overflow:hidden;
            margin-bottom:16px; box-shadow:0 10px 28px rgba(0,0,0,.18);
        }
        .mkx-source-col { display:flex; align-items:center; gap:16px; padding:20px 22px; min-height:96px; }
        .mkx-source-col + .mkx-source-col { border-left:1px solid #42515d; }
        .mkx-source-icon {
            width:56px; height:56px; border-radius:14px; display:flex; align-items:center;
            justify-content:center; flex:0 0 auto; background:#fff2b8; color:#111; font-weight:900;
            box-shadow:inset 0 0 0 1px rgba(255,212,0,.22);
        }
        .mkx-source-kicker { color:#8fa0ae; font-size:11px; font-weight:800; text-transform:uppercase; letter-spacing:.08em; }
        .mkx-source-title { color:#fff; font-size:18px; font-weight:800; margin:4px 0; }
        .mkx-source-meta { color:#aab6c0; font-size:12px; line-height:1.5; }

        /* KPIs */
        .mkx-kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:16px 0 18px; }
        .mkx-kpi {
            position:relative; min-height:112px; padding:18px 18px 16px 18px;
            border-radius:16px; border:1px solid var(--mk-border);
            background:linear-gradient(145deg,#101820,#0b1117); overflow:hidden;
        }
        .mkx-kpi.good { background:linear-gradient(145deg,rgba(13,60,43,.72),rgba(8,31,24,.75)); border-color:#1e5d46; }
        .mkx-kpi.warn { background:linear-gradient(145deg,rgba(78,61,10,.58),rgba(37,29,8,.72)); border-color:#5f4f1d; }
        .mkx-kpi.blue { background:linear-gradient(145deg,rgba(15,52,76,.65),rgba(8,26,38,.72)); border-color:#214b64; }
        .mkx-kpi-label { color:#cbd5dd; font-size:12px; font-weight:750; }
        .mkx-kpi-value { color:#fff; font-size:31px; line-height:1; font-weight:880; margin:9px 0 8px; letter-spacing:-.03em; }
        .mkx-kpi-help { color:#a5b1bc; font-size:12px; }
        .mkx-kpi-badge {
            position:absolute; top:16px; right:16px; border-radius:999px; padding:6px 9px;
            font-size:11px; font-weight:850;
        }
        .mkx-kpi-badge.good { background:rgba(46,212,122,.15); color:#78efaf; }
        .mkx-kpi-badge.warn { background:rgba(255,191,0,.16); color:#ffd85c; }

        /* Section heads */
        .mkx-section-head {
            display:flex; align-items:center; justify-content:space-between; gap:16px;
            margin:16px 0 8px;
        }
        .mkx-section-title { color:#fff; font-size:15px; font-weight:800; }
        .mkx-section-sub { color:#8fa0ae; font-size:12px; margin-top:3px; }
        .mkx-pill {
            display:inline-flex; align-items:center; border:1px solid #33414d; border-radius:999px;
            padding:6px 10px; color:#d6dee5; background:#0a1016; font-size:11px; font-weight:750;
        }

        /* Download banner */
        .mkx-download-banner {
            display:flex; align-items:center; justify-content:space-between; gap:18px;
            border:1px solid var(--mk-border); background:linear-gradient(180deg,#0d141b,#0a1016);
            border-radius:15px; padding:16px 18px; margin-top:14px;
        }
        .mkx-download-copy strong { color:#fff; font-size:14px; display:block; }
        .mkx-download-copy span { color:#9caab6; font-size:12px; display:block; margin-top:4px; }

        /* Recommendations */
        .mkx-reco {
            border:1px solid var(--mk-border); background:linear-gradient(180deg,#0d141b,#090f14);
            border-radius:15px; margin-top:14px; overflow:hidden;
        }
        .mkx-reco-title { padding:14px 18px 8px; color:#fff; font-size:15px; font-weight:850; }
        .mkx-reco-title b { color:var(--mk-yellow); }
        .mkx-reco-grid { display:grid; grid-template-columns:repeat(3,1fr); }
        .mkx-reco-item { padding:14px 18px 18px; min-height:88px; }
        .mkx-reco-item + .mkx-reco-item { border-left:1px solid #25313b; }
        .mkx-reco-item strong { color:#fff; display:block; font-size:13px; margin-bottom:4px; }
        .mkx-reco-item span { color:#98a6b2; font-size:12px; line-height:1.45; }

        /* Streamlit tabs */
        .stTabs [data-baseweb="tab-list"] { gap:10px; border-bottom:1px solid #202b34; }
        .stTabs [data-baseweb="tab"] {
            color:#a7b4bf !important; font-weight:750 !important; padding:10px 14px !important;
        }
        .stTabs [aria-selected="true"] { color:#fff !important; border-bottom-color:var(--mk-yellow) !important; }

        /* Inputs */
        div[data-testid="stTextInput"] input {
            background:#080d12 !important; color:#f7f9fb !important; border:1px solid #2a3742 !important;
            border-radius:11px !important;
        }
        div[data-testid="stTextInput"] input::placeholder { color:#7f8c97 !important; }
        div[data-testid="stRadio"] label { color:#dce3e9 !important; font-weight:700 !important; }

        /* Dataframe */
        div[data-testid="stDataFrame"] {
            border:1px solid #26313b !important; border-radius:14px !important; overflow:hidden !important;
            background:#080d12 !important;
        }
        div[data-testid="stDataFrame"] * { color:#e9eef2; }

        /* Buttons */
        .stDownloadButton > button[kind="primary"],
        button[kind="primary"] {
            background:var(--mk-yellow) !important; color:#111 !important; border:1px solid #f4c900 !important;
            border-radius:11px !important; font-weight:850 !important; box-shadow:none !important;
        }
        .stDownloadButton > button[kind="primary"] p,
        button[kind="primary"] p { color:#111 !important; font-weight:850 !important; }

        /* Alerts */
        div[data-testid="stAlert"] {
            background:#15120a !important; border:1px solid #5d4b16 !important; color:#ffe38a !important;
            border-radius:12px !important;
        }

        /* Legacy classes still used elsewhere */
        .mk2-platform-head, .mk2-summary-grid, .mk2-source, .mk3-compact-summary { display:none !important; }

        @media (max-width: 1000px) {
            .mkx-kpis { grid-template-columns:repeat(2,1fr); }
            .mkx-source { grid-template-columns:1fr; }
            .mkx-source-col + .mkx-source-col { border-left:0; border-top:1px solid #42515d; }
            .mkx-reco-grid { grid-template-columns:1fr; }
            .mkx-reco-item + .mkx-reco-item { border-left:0; border-top:1px solid #25313b; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _normalize_sku(value) -> str:
    """
    Normaliza SKU para cruces entre Llegadas_OK y marketplaces.

    Ejemplos:
        13051205  -> 13051205
        1305120-5 -> 13051205
        200122.0  -> 200122
    """
    if value is None:
        return ""

    text = str(value).strip().upper()

    if not text:
        return ""

    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"[^A-Z0-9]", "", text)

    return text


def _prepare_house_stock(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Fuente Marketplace:
        Llegadas_OK
        -> stock_view
        -> SOLO CASA MATRIZ
        -> consolidación por SKU

    CD, Patronato y Concepción NO participan.
    """
    stock = stock_view(df)

    if stock is None or stock.empty:
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

    house = consolidate_inventory(
        house
    )

    house["_sku_match"] = (
        house["Código"]
        .map(_normalize_sku)
    )

    house = house[
        house["_sku_match"].ne("")
    ].copy()

    if house["_sku_match"].duplicated().any():
        agg = {
            "Código": "first",
            "Producto": "first",
            "Disponible": "sum",
        }

        for col in [
            "Stock físico",
            "Por llegar",
            "Por despachar",
        ]:
            if col in house.columns:
                agg[col] = "sum"

        house = (
            house.groupby(
                "_sku_match",
                as_index=False,
            )
            .agg(agg)
        )

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
    Stock a publicar:
        max(Disponible Casa Matriz - reserva, 0)
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


def _change_status(
    current_stock,
    new_stock,
    found: bool,
) -> tuple[str, int]:
    current = _safe_int(current_stock)
    new = _safe_int(new_stock)
    delta = new - current

    if not found:
        return "Sin coincidencia", delta

    if new == current:
        return "Sin cambios", delta

    if new == 0 and current != 0:
        return "Queda en cero", delta

    if delta > 0:
        return "Sube stock", delta

    return "Baja stock", delta


def _stats_from_preview(
    preview: pd.DataFrame,
    base_stats: dict,
) -> dict:
    stats = dict(base_stats)

    if preview is None or preview.empty:
        stats.update(
            {
                "up": 0,
                "down": 0,
                "zero": 0,
                "same": 0,
                "match_pct": 0.0,
            }
        )
        return stats

    status = (
        preview["Cambio"]
        if "Cambio" in preview.columns
        else pd.Series("", index=preview.index)
    )

    stats["up"] = int(
        status.eq("Sube stock").sum()
    )
    stats["down"] = int(
        status.eq("Baja stock").sum()
    )
    stats["zero"] = int(
        status.eq("Queda en cero").sum()
    )
    stats["same"] = int(
        status.eq("Sin cambios").sum()
    )

    rows = max(
        _safe_int(
            stats.get("rows", 0)
        ),
        0,
    )

    matched = max(
        _safe_int(
            stats.get("matched_rows", 0)
        ),
        0,
    )

    stats["match_pct"] = (
        (matched / rows) * 100
        if rows > 0
        else 0.0
    )

    return stats


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
    Paris:
        Hoja       -> stock
        Cruce      -> sku_seller
        Stock base -> stock
        Escribe    -> nuevo_stock
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

        # Paris publica exactamente el Disponible de Casa Matriz.
        # Si el SKU no existe en CM, nuevo_stock queda en 0.
        available_cm = max(
            int(stock_lookup.get(sku_key, 0)),
            0,
        )
        new_stock = available_cm

        current_stock = (
            ws.cell(
                row=row,
                column=current_stock_col,
            ).value
            if current_stock_col
            else 0
        )

        change, delta = _change_status(
            current_stock,
            new_stock,
            found,
        )

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

        publishable_units += new_stock

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
                "Stock actual": _safe_int(
                    current_stock
                ),
                "Disponible Casa Matriz": available_cm,
                "Nuevo stock": new_stock,
                "Diferencia": delta,
                "Cambio": change,
                "Coincidencia Stock CM": (
                    "Encontrado"
                    if found
                    else "Sin coincidencia"
                ),
            }
        )

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    preview = pd.DataFrame(
        preview_rows
    )

    stats = _stats_from_preview(
        preview,
        {
            "rows": processed_rows,
            "matched_rows": matched_rows,
            "unmatched_rows": unmatched_rows,
            "matched_skus": len(matched_skus),
            "unmatched_skus": len(unmatched_skus),
            "units": publishable_units,
        },
    )

    return (
        output.getvalue(),
        preview,
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
    Mercado Libre - conserva el formato oficial:
        - Lee SKU y QUANTITY desde la hoja Publicaciones.
        - Cruza SKU contra Disponible de Casa Matriz.
        - Modifica SOLO las celdas QUANTITY dentro del XLSX original.
        - Conserva todas las hojas, columnas, estilos, validaciones y metadatos.

    Importante: NO se guarda el libro con openpyxl. El XLSX se copia como ZIP
    y se parchean únicamente las celdas de QUANTITY en el XML de Publicaciones.
    """
    stock_lookup = dict(stock_items)

    # --------------------------------------------------------
    # 1) Leer estructura/filas de forma secuencial
    # --------------------------------------------------------
    source_wb = load_workbook(
        BytesIO(template_bytes),
        data_only=False,
        read_only=True,
    )

    if "Publicaciones" not in source_wb.sheetnames:
        source_wb.close()
        raise ValueError(
            "La plantilla Mercado Libre no contiene la hoja 'Publicaciones'."
        )

    ws = source_wb["Publicaciones"]
    rows = ws.iter_rows(values_only=True)

    header_row = None
    header_values = None

    for row_number, values in enumerate(rows, start=1):
        if row_number > 12:
            break

        normalized = [
            re.sub(r"[^A-Z0-9]", "", str(v).strip().upper())
            if v is not None else ""
            for v in values
        ]

        if "SKU" in normalized and "QUANTITY" in normalized:
            header_row = row_number
            header_values = normalized
            break

    if header_row is None or header_values is None:
        source_wb.close()
        raise ValueError(
            "No se encontraron las columnas 'SKU' y 'QUANTITY' "
            "en la plantilla Mercado Libre."
        )

    sku_idx = header_values.index("SKU")
    quantity_idx = header_values.index("QUANTITY")

    def _excel_col_letter(index_zero_based: int) -> str:
        n = index_zero_based + 1
        out = ""
        while n:
            n, rem = divmod(n - 1, 26)
            out = chr(65 + rem) + out
        return out

    quantity_col_letter = _excel_col_letter(quantity_idx)

    preview_rows = []
    replacements = {}
    matched_rows = 0
    unmatched_rows = 0
    publishable_units = 0
    matched_skus = set()
    unmatched_skus = set()

    for row_number, values in enumerate(rows, start=header_row + 1):
        if not values or sku_idx >= len(values):
            continue

        raw_sku = values[sku_idx]
        if raw_sku is None:
            continue

        sku_text = str(raw_sku).strip()
        if not sku_text:
            continue

        sku_key = _normalize_sku(raw_sku)
        if not sku_key:
            continue

        current_stock = (
            values[quantity_idx]
            if quantity_idx < len(values)
            else 0
        )

        found = sku_key in stock_lookup
        new_stock = max(int(stock_lookup.get(sku_key, 0)), 0)

        change, delta = _change_status(
            current_stock,
            new_stock,
            found,
        )

        if found:
            matched_rows += 1
            matched_skus.add(sku_key)
        else:
            unmatched_rows += 1
            unmatched_skus.add(sku_key)

        publishable_units += new_stock
        replacements[f"{quantity_col_letter}{row_number}"] = new_stock

        preview_rows.append({
            "SKU": sku_text,
            "Stock actual": _safe_int(current_stock),
            "Nuevo stock": new_stock,
            "Diferencia": delta,
            "Cambio": change,
            "Coincidencia Stock CM": (
                "Encontrado" if found else "Sin coincidencia"
            ),
        })

    source_wb.close()

    # --------------------------------------------------------
    # 2) Localizar el XML exacto de la hoja Publicaciones
    # --------------------------------------------------------
    with zipfile.ZipFile(BytesIO(template_bytes), "r") as zin:
        workbook_xml = ET.fromstring(zin.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(zin.read("xl/_rels/workbook.xml.rels"))

        ns_main = {
            "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        ns_rel = {
            "p": "http://schemas.openxmlformats.org/package/2006/relationships",
        }

        rel_id = None
        for sheet in workbook_xml.findall("m:sheets/m:sheet", ns_main):
            if sheet.attrib.get("name") == "Publicaciones":
                rel_id = sheet.attrib.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                break

        if not rel_id:
            raise ValueError(
                "No fue posible localizar la relación de la hoja Publicaciones."
            )

        target = None
        for rel in rels_xml.findall("p:Relationship", ns_rel):
            if rel.attrib.get("Id") == rel_id:
                target = rel.attrib.get("Target")
                break

        if not target:
            raise ValueError(
                "No fue posible localizar el XML de la hoja Publicaciones."
            )

        if target.startswith("/"):
            sheet_path = target.lstrip("/")
        elif target.startswith("xl/"):
            sheet_path = target
        else:
            sheet_path = "xl/" + target.lstrip("./")

        sheet_bytes = zin.read(sheet_path)

        # ----------------------------------------------------
        # 3) Parche raw-byte: SOLO las celdas QUANTITY
        # ----------------------------------------------------
        patched = sheet_bytes
        changed_cells = 0

        for ref, new_stock in replacements.items():
            ref_b = ref.encode("ascii")
            value_b = str(int(new_stock)).encode("ascii")

            # Celda normal: <c ... r="H6" ...>...</c>
            pattern = re.compile(
                rb'<c(?P<attrs>[^>]*\br="' + re.escape(ref_b) + rb'"[^>]*)>'
                rb'(?P<body>.*?)</c>',
                re.DOTALL,
            )

            match = pattern.search(patched)
            if match:
                attrs = match.group("attrs")
                # QUANTITY puede venir como shared string (t="s").
                # Al escribir un número removemos SOLO ese atributo.
                attrs_clean = re.sub(
                    rb'\s+t="[^"]*"',
                    b'',
                    attrs,
                    count=1,
                )
                replacement = (
                    b'<c' + attrs_clean + b'><v>' + value_b + b'</v></c>'
                )
                patched = (
                    patched[:match.start()]
                    + replacement
                    + patched[match.end():]
                )
                changed_cells += 1
                continue

            # Caso excepcional de celda autocerrada: <c ... r="H6" .../>
            pattern_empty = re.compile(
                rb'<c(?P<attrs>[^>]*\br="' + re.escape(ref_b) + rb'"[^>]*)/>',
                re.DOTALL,
            )
            match = pattern_empty.search(patched)
            if match:
                attrs = match.group("attrs")
                attrs_clean = re.sub(
                    rb'\s+t="[^"]*"',
                    b'',
                    attrs,
                    count=1,
                ).rstrip()
                replacement = (
                    b'<c' + attrs_clean + b'><v>' + value_b + b'</v></c>'
                )
                patched = (
                    patched[:match.start()]
                    + replacement
                    + patched[match.end():]
                )
                changed_cells += 1

        if changed_cells == 0 and replacements:
            raise ValueError(
                "No fue posible actualizar las celdas QUANTITY del archivo Mercado Libre."
            )

        # ----------------------------------------------------
        # 4) Copiar el XLSX completo; sustituir SOLO sheet XML
        # ----------------------------------------------------
        output = BytesIO()
        with zipfile.ZipFile(output, "w") as zout:
            for info in zin.infolist():
                data = patched if info.filename == sheet_path else zin.read(info.filename)
                zout.writestr(info, data)

    output.seek(0)

    preview = pd.DataFrame(preview_rows)
    stats = _stats_from_preview(
        preview,
        {
            "rows": len(preview_rows),
            "matched_rows": matched_rows,
            "unmatched_rows": unmatched_rows,
            "matched_skus": len(matched_skus),
            "unmatched_skus": len(unmatched_skus),
            "units": publishable_units,
            "changed_cells": changed_cells,
        },
    )

    return (
        output.getvalue(),
        preview,
        stats,
    )


def _marketplace_header(
    name: str,
    filename: str,
    stats: dict,
):
    pct = float(
        stats.get(
            "match_pct",
            0.0,
        )
    )

    badge_class = (
        "ok"
        if pct >= 98
        else "warn"
        if pct >= 90
        else "risk"
    )

    render_html(
        f"""
        <div class="mk2-platform-head">
            <div class="mk2-platform-title">
                <div class="mk2-platform-mark">
                    {"P" if "Paris" in name else "ML"}
                </div>
                <div>
                    <strong>{name}</strong>
                    <span>Plantilla oficial · {filename}</span>
                </div>
            </div>

            <div class="mk2-platform-badges">
                <span class="mk2-badge neutral">CASA MATRIZ</span>
                <span class="mk2-badge {badge_class}">
                    {pct:.1f}% MATCH
                </span>
            </div>
        </div>
        """
    )


def _filter_preview(
    preview: pd.DataFrame,
    search: str,
    change_filter: str,
) -> pd.DataFrame:
    view = preview.copy()

    if search:
        term = search.strip().lower()

        text_columns = [
            col
            for col in view.columns
            if (
                view[col].dtype == object
                or pd.api.types.is_string_dtype(
                    view[col]
                )
            )
        ]

        mask = pd.Series(
            False,
            index=view.index,
        )

        for col in text_columns:
            mask = (
                mask
                |
                view[col]
                .fillna("")
                .astype(str)
                .str.lower()
                .str.contains(
                    term,
                    regex=False,
                )
            )

        view = view[
            mask
        ].copy()

    if change_filter == "Sin coincidencia":
        if "Coincidencia Stock CM" in view.columns:
            view = view[
                view["Coincidencia Stock CM"].eq("Sin coincidencia")
            ].copy()

    elif change_filter == "Con cambio":
        if "Cambio" in view.columns:
            view = view[
                ~view["Cambio"].eq("Sin cambios")
            ].copy()

    return view


# ============================================================
# PANEL MARKETPLACE
# ============================================================

def _render_marketplace_panel(
    name: str,
    key_name: str,
    house: pd.DataFrame,
    loaded_at: str = "actualización automática",
):
    path = MARKETPLACE_TEMPLATES[name]

    if not path.exists():
        st.error(
            f"No existe la plantilla oficial de {name}. "
            "Cárgala desde Plantillas."
        )
        return

    # --------------------------------------------------------
    # PROCESAR PLANTILLA
    # --------------------------------------------------------
    reserve = 0
    lookup = _stock_map(house, reserve)
    stock_items = tuple(sorted(lookup.items()))
    template_bytes = path.read_bytes()

    try:
        if name == "Paris Marketplace":
            output_bytes, preview, stats = _build_paris_workbook(
                template_bytes,
                stock_items,
            )
            download_name = "Paris_stock_actualizado.xlsx"
            button_label = "Descargar archivo actualizado"
        else:
            output_bytes, preview, stats = _build_meli_workbook(
                template_bytes,
                stock_items,
            )
            download_name = path.name
            button_label = "Descargar Mercado Libre actualizado"
    except Exception as exc:
        st.error(f"No fue posible procesar la plantilla: {exc}")
        return

    match_pct = float(stats.get("match_pct", 0.0))
    unmatched_pct = max(0.0, 100.0 - match_pct)

    # --------------------------------------------------------
    # ENCABEZADO GLOBAL
    # --------------------------------------------------------
    subtitle = (
        "Genera tu archivo de actualización de stock para Paris."
        if name == "Paris Marketplace"
        else "Actualiza QUANTITY usando exclusivamente el Disponible de Casa Matriz."
    )

    page_header(
        title=name.upper(),
        subtitle=subtitle,
        status="Stock automático · Casa Matriz",
        updated=loaded_at,
    )

    render_html(
        f"""
        <div class="mkx-source">
            <div class="mkx-source-col">
                <div class="mkx-source-icon">CM</div>
                <div>
                    <div class="mkx-source-kicker">Fuente de stock</div>
                    <div class="mkx-source-title">Stock automático · Llegadas_OK</div>
                    <div class="mkx-source-meta">
                        Bodega utilizada: <b style="color:#fff">CASA MATRIZ</b>
                        &nbsp;&nbsp;·&nbsp;&nbsp; Actualizado: {loaded_at}
                    </div>
                </div>
            </div>
            <div class="mkx-source-col">
                <div class="mkx-source-icon" style="background:#182028;color:#fff">⚙</div>
                <div>
                    <div class="mkx-source-kicker">Regla de publicación</div>
                    <div class="mkx-source-title">Solo Casa Matriz</div>
                    <div class="mkx-source-meta">CD, Patronato y Concepción excluidos</div>
                </div>
            </div>
        </div>

        <div class="mkx-kpis">
            <div class="mkx-kpi">
                <div class="mkx-kpi-label">Total filas plantilla</div>
                <div class="mkx-kpi-value">{_fmt_int(stats['rows'])}</div>
                <div class="mkx-kpi-help">registros procesados</div>
            </div>
            <div class="mkx-kpi good">
                <div class="mkx-kpi-badge good">{match_pct:.1f}%</div>
                <div class="mkx-kpi-label">SKU encontrados</div>
                <div class="mkx-kpi-value">{_fmt_int(stats['matched_rows'])}</div>
                <div class="mkx-kpi-help">coinciden con Casa Matriz</div>
            </div>
            <div class="mkx-kpi warn">
                <div class="mkx-kpi-badge warn">{unmatched_pct:.1f}%</div>
                <div class="mkx-kpi-label">Sin coincidencia</div>
                <div class="mkx-kpi-value">{_fmt_int(stats['unmatched_rows'])}</div>
                <div class="mkx-kpi-help">se exportarán con stock 0</div>
            </div>
            <div class="mkx-kpi blue">
                <div class="mkx-kpi-label">Stock a publicar</div>
                <div class="mkx-kpi-value">{_fmt_int(stats['units'])}</div>
                <div class="mkx-kpi-help">unidades disponibles Casa Matriz</div>
            </div>
        </div>
        """
    )

    # --------------------------------------------------------
    # CONTROLES DE VISTA
    # --------------------------------------------------------
    c1, c2 = st.columns([1.7, 1.0], gap="medium")

    with c1:
        change_filter = st.radio(
            "Vista",
            ["Todos", "Sin coincidencia", "Con cambio", "Sin cambio"],
            horizontal=True,
            key=f"market_change_filter_v3_{key_name}",
            label_visibility="collapsed",
        )

    with c2:
        search = st.text_input(
            "Buscar",
            placeholder="Buscar por SKU, producto o talla...",
            key=f"market_search_v3_{key_name}",
            label_visibility="collapsed",
        )

    # filtro compatible con la función existente
    preview_view = preview.copy()
    if search:
        preview_view = _filter_preview(preview_view, search, "Todos")

    if change_filter == "Sin coincidencia":
        if "Coincidencia Stock CM" in preview_view.columns:
            preview_view = preview_view[
                preview_view["Coincidencia Stock CM"].eq("Sin coincidencia")
            ].copy()
    elif change_filter == "Con cambio":
        if "Cambio" in preview_view.columns:
            preview_view = preview_view[
                ~preview_view["Cambio"].eq("Sin cambios")
            ].copy()
    elif change_filter == "Sin cambio":
        if "Cambio" in preview_view.columns:
            preview_view = preview_view[
                preview_view["Cambio"].eq("Sin cambios")
            ].copy()

    render_html(
        f"""
        <div class="mkx-section-head">
            <div>
                <div class="mkx-section-title">Vista previa</div>
                <div class="mkx-section-sub">{_fmt_int(len(preview_view))} de {_fmt_int(len(preview))} registros visibles</div>
            </div>
            <div class="mkx-pill">Disponible Casa Matriz → nuevo_stock</div>
        </div>
        """
    )

    # --------------------------------------------------------
    # TABLA
    # --------------------------------------------------------
    column_config = {
        "Stock actual": st.column_config.NumberColumn("STOCK ACTUAL", format="%d"),
        "Disponible Casa Matriz": st.column_config.NumberColumn("DISPONIBLE CM", format="%d"),
        "Nuevo stock": st.column_config.NumberColumn("NUEVO STOCK", format="%d"),
        "Diferencia": st.column_config.NumberColumn("DIFERENCIA", format="%+d"),
        "Cambio": st.column_config.TextColumn("CAMBIO", width="small"),
        "Coincidencia Stock CM": st.column_config.TextColumn("COINCIDENCIA", width="medium"),
    }

    st.dataframe(
        preview_view,
        hide_index=True,
        use_container_width=True,
        height=430,
        column_config=column_config,
    )

    # --------------------------------------------------------
    # ALERTA + DESCARGA
    # --------------------------------------------------------
    if stats["unmatched_rows"] > 0:
        target_field = "QUANTITY" if name == "Mercado Libre" else "nuevo_stock"
        st.warning(
            f"{_fmt_int(stats['unmatched_rows'])} fila(s) no tienen coincidencia "
            "con Casa Matriz. "
            f"Se exportarán con {target_field} = 0."
        )

    render_html(
        f"""
        <div class="mkx-download-banner">
            <div class="mkx-download-copy">
                <strong>Archivo listo para descargar</strong>
                <span>Se generará un Excel manteniendo la plantilla oficial y actualizando solo el stock.</span>
            </div>
            <div class="mkx-pill">{path.name}</div>
        </div>
        """
    )

    st.download_button(
        button_label,
        data=output_bytes,
        file_name=download_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        type="primary",
        icon=":material/download:",
        key=f"market_download_v3_{key_name}",
    )

    # --------------------------------------------------------
    # RECOMENDACIONES OPERATIVAS
    # --------------------------------------------------------
    render_html(
        f"""
        <div class="mkx-reco">
            <div class="mkx-reco-title"><b>◉</b> Recomendaciones</div>
            <div class="mkx-reco-grid">
                <div class="mkx-reco-item">
                    <strong>Revisa los SKU sin coincidencia ({_fmt_int(stats['unmatched_rows'])})</strong>
                    <span>Verifica si el SKU existe en Casa Matriz o si requiere corrección en la plantilla.</span>
                </div>
                <div class="mkx-reco-item">
                    <strong>Revisa cambios significativos</strong>
                    <span>Prioriza disminuciones fuertes de stock antes de publicar el archivo.</span>
                </div>
                <div class="mkx-reco-item">
                    <strong>Mantén el stock actualizado</strong>
                    <span>Genera el archivo nuevamente cuando Llegadas_OK actualice Casa Matriz.</span>
                </div>
            </div>
        </div>
        """
    )


# ============================================================
# RENDER PRINCIPAL
# ============================================================

def render(ctx):
    df = ctx.get("stock_df")
    meta = ctx.get("stock_meta") or {}

    _inject_marketplace_contrast_css()

    if df is None or df.empty:
        st.info("No hay stock disponible desde Llegadas_OK.")
        return

    house = _prepare_house_stock(df)
    if house.empty:
        st.warning("Llegadas_OK no contiene registros asociados a Casa Matriz.")
        return

    loaded_at = _format_loaded_at(
        meta.get("loaded_at") or meta.get("generated_at")
    )

    paris_tab, meli_tab = st.tabs(["Paris", "Mercado Libre"])

    with paris_tab:
        _render_marketplace_panel(
            name="Paris Marketplace",
            key_name="paris",
            house=house,
            loaded_at=loaded_at,
        )

    with meli_tab:
        _render_marketplace_panel(
            name="Mercado Libre",
            key_name="meli",
            house=house,
            loaded_at=loaded_at,
        )

