from pathlib import Path

APP_VERSION = "V61.7.1 - Fix Stock Metrics"
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

MARKETPLACE_TEMPLATES = {
    "Paris Marketplace": TEMPLATES_DIR / "plantilla_paris.xlsx",
    "Mercado Libre": TEMPLATES_DIR / "plantilla_meli.xlsx",
}

PAGES = {
    "stock_general": "Stock General",
    "marketplace": "Marketplaces",
    "metricas": "Métricas de Stock",
    "vendedores": "Métricas Vendedores",
    "ventas": "Resumen Ejecutivo",
    "configuracion": "Plantillas",
}
