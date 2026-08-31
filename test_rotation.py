from pathlib import Path

import pandas as pd

from services.erp_movements import (
    read_inventory_movements_pdf,
)

from analytics.rotation_metrics import (
    combine_movement_periods,
    build_rotation_metrics,
)


FILES = [
    Path("movimientos_cm_junio_2026.pdf"),
    Path("movimientos_cm_julio_2026.pdf"),
    Path("movimientos_cm_agosto_2026.pdf"),
]


frames = []


for pdf in FILES:

    print()
    print("=" * 80)
    print(f"Procesando: {pdf.name}")
    print("=" * 80)

    raw = pdf.read_bytes()

    df, meta = (
        read_inventory_movements_pdf(
            raw,
            filename=pdf.name,
            local="Casa Matriz",
        )
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


combined = (
    combine_movement_periods(
        frames
    )
)


print()
print("=" * 80)
print("MOVIMIENTOS CONSOLIDADOS")
print("=" * 80)

print(
    f"Filas: {len(combined):,}"
)


rotation = (
    build_rotation_metrics(
        combined,
        windows=(
            30,
            60,
            90,
        ),
        preferred_window=90,
        end_date="2026-08-27",
    )
)


print()
print("=" * 80)
print("ROTACIÓN")
print("=" * 80)

cols = [
    "SKU",
    "Producto",
    "Salida 30d",
    "Salida 60d",
    "Salida 90d",
    "Promedio diario 30d",
    "Promedio diario 60d",
    "Promedio diario 90d",
    "Velocidad ponderada",
    "Tendencia",
    "Variación tendencia",
    "Última salida",
    "Días sin salida",
]
print(
    rotation[
        [
            c
            for c in cols
            if c in rotation.columns
        ]
    ]
    .sort_values(
        "Salida 90d",
        ascending=False,
    )
    .head(30)
    .to_string(
        index=False
    )
)