from pathlib import Path

from services.erp_movements import (
    read_inventory_movements_pdf,
    movement_operation_summary,
    demand_by_sku,
)


PDF = Path(
    "detalle de inventario unidades.pdf"
)

raw = PDF.read_bytes()


df, meta = read_inventory_movements_pdf(
    raw,
    filename=PDF.name,
    local="Casa Matriz",
)


print("\n===== META =====")
print(meta)


print("\n===== PRIMEROS MOVIMIENTOS =====")
print(
    df.head(30).to_string(
        index=False
    )
)


print("\n===== TIPOS DE OPERACIÓN =====")
print(
    movement_operation_summary(
        df
    ).to_string(
        index=False
    )
)


print("\n===== DEMANDA CANDIDATA =====")
print(
    demand_by_sku(
        df
    ).head(30).to_string(
        index=False
    )
)