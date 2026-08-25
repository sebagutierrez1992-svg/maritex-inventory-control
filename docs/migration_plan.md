# Plan de migración

## Etapa 1 — Proyecto modular
Estado: creado.

## Etapa 2 — ERP Ventas
Mover y validar:
- XLS/XLSX/CSV
- fechas DD/MM vs MM/DD
- Total vs TotalIngreso
- documentos comerciales
- notas de crédito
- IVA

Criterio de aceptación:
el mismo vendedor + mismo período + misma base IVA devuelve el mismo valor
en Métricas Vendedores y Resumen Ejecutivo.

## Etapa 3 — ERP Stock
Mover:
- normalización SKU
- bodegas
- consolidación
- estados de inventario

## Etapa 4 — Plantillas
Unificar:
- carga ERP Stock
- carga ERP Ventas
- Paris
- Mercado Libre
- metadata de fuentes

## Etapa 5 — Marketplaces
Mover:
- Casa Matriz
- stock de seguridad
- stock máximo
- comparación SKU
- generación de archivos

## Etapa 6 — Vistas analíticas
Mover gradualmente sin duplicar cálculos.

## Etapa 7 — CSS
Reconstruir una única hoja final.

## Etapa 8 — Tests
Validar fechas, ventas, IVA, NC, stock y marketplaces.
