from pathlib import Path

APP_VERSION = "V61.7.2 - Marketplace Templates Auto Detect"
APP_TITLE = "Maritex Inventory Control"

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"

DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_VAT_RATE = 0.19

ERP_STOCK_FILE = DATA_DIR / "erp_stock_source.bin"
ERP_STOCK_META = DATA_DIR / "erp_stock_source.json"

ERP_SALES_FILE = DATA_DIR / "erp_sales_source.bin"
ERP_SALES_META = DATA_DIR / "erp_sales_source.json"


# ============================================================
# PLANTILLAS MARKETPLACE
# ============================================================

def _find_template(
    preferred_name: str,
    patterns: tuple[str, ...],
) -> Path:
    """
    Busca primero el nombre oficial esperado.
    Si no existe, intenta detectar automáticamente una planilla
    compatible dentro de /templates.

    Si no encuentra ninguna, devuelve la ruta oficial para que
    Marketplace pueda informar correctamente que falta la plantilla.
    """
    preferred = TEMPLATES_DIR / preferred_name

    if preferred.exists():
        return preferred

    candidates: list[Path] = []

    for pattern in patterns:
        candidates.extend(
            path
            for path in TEMPLATES_DIR.glob(pattern)
            if (
                path.is_file()
                and path.suffix.lower() == ".xlsx"
                and "actualizado" not in path.name.lower()
            )
        )

    # Eliminar duplicados manteniendo orden.
    unique_candidates = list(
        dict.fromkeys(candidates)
    )

    if unique_candidates:
        return unique_candidates[0]

    return preferred


PARIS_TEMPLATE = _find_template(
    "plantilla_paris.xlsx",
    (
        "*paris*.xlsx",
        "*Paris*.xlsx",
        "*PARIS*.xlsx",
    ),
)

MELI_TEMPLATE = _find_template(
    "plantilla_meli.xlsx",
    (
        "*meli*.xlsx",
        "*Meli*.xlsx",
        "*MELI*.xlsx",
        "*mercado*libre*.xlsx",
        "*Mercado*Libre*.xlsx",
        "*MERCADO*LIBRE*.xlsx",
    ),
)

MARKETPLACE_TEMPLATES = {
    "Paris Marketplace": PARIS_TEMPLATE,
    "Mercado Libre": MELI_TEMPLATE,
}


PAGES = {
    "stock_general": "Stock General",
    "marketplace": "Marketplace",
    "metricas": "Métricas Stock",
    "vendedores": "Métricas Vendedores",
    "ventas": "Resumen Ejecutivo",
    "configuracion": "Plantillas",
}
