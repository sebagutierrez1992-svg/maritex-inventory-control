# Maritex Inventory Control — Nuevo Proyecto

Esta estructura está diseñada para reemplazar gradualmente el archivo monolítico actual
por una aplicación modular y mantenible.

## Arquitectura objetivo

```text
maritex_inventory_control_new_project/
│
├── app.py
├── requirements.txt
│
├── config/
│   └── settings.py
│
├── models/
│   └── schemas.py
│
├── services/
│   ├── erp_stock.py
│   ├── erp_sales.py
│   ├── marketplaces.py
│   ├── storage.py
│   └── validation.py
│
├── analytics/
│   ├── stock_metrics.py
│   ├── sales_metrics.py
│   └── projections.py
│
├── ui/
│   ├── styles.py
│   └── components.py
│
├── views/
│   ├── stock_general.py
│   ├── marketplaces.py
│   ├── metricas_stock.py
│   ├── metricas_vendedores.py
│   ├── resumen_ejecutivo.py
│   └── plantillas.py
│
├── utils/
│   ├── numbers.py
│   ├── dates.py
│   └── text.py
│
├── tests/
├── docs/
├── data/
├── templates/
├── assets/
└── legacy/
```

## Fuente de verdad

### ERP Stock
Alimenta:
- Stock General
- Métricas de Stock
- Marketplaces

### ERP Ventas
Alimenta:
- Métricas Vendedores
- Resumen Ejecutivo

### Plantillas
Es el único centro de carga/administración de:
- ERP Stock
- ERP Ventas
- Plantilla Paris
- Plantilla Mercado Libre

## Orden de migración recomendado

1. ERP Ventas
2. ERP Stock
3. Plantillas / almacenamiento
4. Métricas Vendedores
5. Resumen Ejecutivo
6. Stock General
7. Métricas de Stock
8. Marketplaces
9. Limpieza final de CSS
10. Tests y validación

El directorio `legacy/` contiene la aplicación actual como respaldo durante la migración.
