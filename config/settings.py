import os
from pathlib import Path


APP_VERSION = "V61.7.3 - Render Ready"
APP_TITLE = "Maritex Inventory Control"


# ============================================================
# RUTAS PRINCIPALES
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]


def _resolve_data_dir() -> Path:
    """
    Determina dónde guardar los archivos persistentes de la aplicación.

    Local:
        Usa <proyecto>/data

    Render:
        Si existe la variable de entorno MARITEX_DATA_DIR,
        utiliza esa ubicación.

    Ejemplo en Render:
        MARITEX_DATA_DIR=/opt/render/project/src/data
    """
    configured_dir = os.getenv("MARITEX_DATA_DIR", "").strip()

    if configured_dir:
        return Path(configured_dir).expanduser().resolve()

    return BASE_DIR / "data"


DATA_DIR = _resolve_data_dir()

# Las plantillas y assets forman parte del repositorio.
TEMPLATES_DIR = BASE_DIR / "templates"
ASSETS_DIR = BASE_DIR / "assets"


# Crear directorios si todavía no existen.
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

DEFAULT_VAT_RATE = 0.19


# ============================================================
# ARCHIVOS ERP
# ============================================================

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
    unique_candidates = list(dict.fromkeys(candidates))

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


# ============================================================
# PÁGINAS
# ============================================================

PAGES = {
    "stock_general": "Stock General",
    "marketplace": "Marketplace",
    "metricas": "Métricas Stock",
    "vendedores": "Métricas Vendedores",
    "ventas": "Resumen Ejecutivo",
    "configuracion": "Plantillas",
}