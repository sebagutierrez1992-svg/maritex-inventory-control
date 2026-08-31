from pathlib import Path

import pandas as pd

from services.erp_movements import (
    read_inventory_movements_pdf,
)

from services.erp_stock import (
    read_stock_source,
)

from analytics.rotation_metrics import (
    combine_movement_periods,
    build_rotation_metrics,
    add_stock_coverage,
    classify_coverage,
)


# ============================================================
# ARCHIVOS
# ============================================================

MOVEMENT_FILES = [
    Path("movimientos_cm_junio_2026.pdf"),
    Path("movimientos_cm_julio_2026.pdf"),
    Path("movimientos_cm_agosto_2026.pdf"),
]

# Cambia este nombre si tu archivo ERP Stock
# se llama diferente.
STOCK_FILE = Path("stock 26-08.csv")


# ============================================================
# 1. LEER MOVIMIENTOS
# ============================================================

frames = []

for pdf in MOVEMENT_FILES:

    print()
    print("=" * 80)
    print(f"Procesando movimientos: {pdf.name}")
    print("=" * 80)

    raw = pdf.read_bytes()

    df, meta = read_inventory_movements_pdf(
        raw,
        filename=pdf.name,
        local="Casa Matriz",
    )

    print(
        f"SKU: {meta['sku']:,}"
    )

    print(
        f"Movimientos: "
        f"{meta['movements']:,}"
    )

    print(
        f"Salidas: "
        f"{meta['total_salidas']:,.0f}"
    )

    frames.append(
        df
    )


# ============================================================
# 2. CONSOLIDAR MOVIMIENTOS
# ============================================================

combined = combine_movement_periods(
    frames
)

print()
print("=" * 80)
print("MOVIMIENTOS CONSOLIDADOS")
print("=" * 80)

print(
    f"Filas: {len(combined):,}"
)


# ============================================================
# 3. CALCULAR ROTACIÓN
# ============================================================

rotation = build_rotation_metrics(
    combined,
    windows=(
        30,
        60,
        90,
    ),
    preferred_window=90,
    end_date="2026-08-27",
)

print()
print("=" * 80)
print("ROTACIÓN CALCULADA")
print("=" * 80)

print(
    f"SKU analizados: "
    f"{len(rotation):,}"
)


# ============================================================
# 4. LEER ERP STOCK
# ============================================================

print()
print("=" * 80)
print("CARGANDO ERP STOCK")
print("=" * 80)

if not STOCK_FILE.exists():

    raise FileNotFoundError(
        f"No se encontró el archivo: "
        f"{STOCK_FILE}"
    )


stock_raw = STOCK_FILE.read_bytes()

stock = read_stock_source(
    stock_raw,
    STOCK_FILE.name,
)

print(
    f"Filas stock: "
    f"{len(stock):,}"
)

print(
    f"Columnas stock: "
    f"{list(stock.columns)}"
)


# ============================================================
# 5. FILTRAR CASA MATRIZ
# ============================================================

if "Bodega" not in stock.columns:

    raise ValueError(
        "El ERP Stock no contiene "
        "la columna Bodega."
    )


mask_cm = (
    stock["Bodega"]
    .fillna("")
    .astype(str)
    .str.upper()
    .str.contains(
        "CASA MATRIZ",
        regex=False,
    )
)

stock_cm = stock[
    mask_cm
].copy()

print()
print("=" * 80)
print("STOCK CASA MATRIZ")
print("=" * 80)

print(
    f"Filas CM: "
    f"{len(stock_cm):,}"
)

print(
    f"SKU CM: "
    f"{stock_cm['Código'].nunique():,}"
)

print(
    f"Stock disponible CM: "
    f"{stock_cm['StockDisponible_num'].sum():,.0f}"
)


# ============================================================
# 6. CRUZAR ROTACIÓN + STOCK
# ============================================================

coverage = add_stock_coverage(
    rotation,
    stock_cm,
    stock_code_col="Código",
    stock_qty_col="StockDisponible_num",
)

coverage = classify_coverage(
    coverage
)


# ============================================================
# 7. MOSTRAR RESULTADO
# ============================================================

print()
print("=" * 80)
print("COBERTURA CASA MATRIZ")
print("=" * 80)


cols = [
    "SKU",
    "Producto",

    "Stock CM",

    "Salida 30d",
    "Salida 60d",
    "Salida 90d",

    "Velocidad ponderada",

    "Cobertura días",

    "Estado cobertura",

    "Tendencia",

    "Última salida",
    "Días sin salida",
]


show = coverage[
    [
        c
        for c in cols
        if c in coverage.columns
    ]
].copy()


# ============================================================
# 8. ORDENAR POR MAYOR RIESGO
# ============================================================

show["_coverage_sort"] = (
    pd.to_numeric(
        show["Cobertura días"],
        errors="coerce",
    )
)


show = (
    show.sort_values(
        [
            "_coverage_sort",
            "Velocidad ponderada",
        ],
        ascending=[
            True,
            False,
        ],
        na_position="last",
    )
    .drop(
        columns=[
            "_coverage_sort"
        ]
    )
)


print(
    show
    .head(50)
    .to_string(
        index=False
    )
)


# ============================================================
# 9. KPIs RÁPIDOS
# ============================================================

print()
print("=" * 80)
print("RESUMEN")
print("=" * 80)


states = (
    coverage[
        "Estado cobertura"
    ]
    .value_counts(
        dropna=False
    )
)


for state, count in states.items():

    print(
        f"{state}: "
        f"{count:,} SKU"
    )


moving = (
    pd.to_numeric(
        coverage[
            "Velocidad ponderada"
        ],
        errors="coerce",
    )
    .fillna(0)
    > 0
)


print()
print(
    "SKU con movimiento: "
    f"{int(moving.sum()):,}"
)


critical = (
    coverage[
        "Estado cobertura"
    ]
    .isin(
        [
            "🔴 Sin stock",
            "🔴 Quiebre inminente",
            "🟠 Crítico",
        ]
    )
)


print(
    "SKU críticos: "
    f"{int(critical.sum()):,}"
)