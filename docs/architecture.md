# Arquitectura objetivo

## Regla principal

Las vistas nunca deben leer directamente archivos ERP.

```text
Archivo ERP
   ↓
services/*
   ↓
DataFrame normalizado
   ↓
analytics/*
   ↓
views/*
```

## ERP Stock

`services/erp_stock.py`

Responsabilidades:
- leer CSV/XLS/XLSX;
- normalizar códigos;
- convertir cantidades;
- consolidar stock.

Consumidores:
- Stock General
- Métricas de Stock
- Marketplaces

## ERP Ventas

`services/erp_sales.py`

Responsabilidades:
- leer CSV/XLS/XLSX/XLS-HTML;
- interpretar fechas;
- clasificar documentos;
- detectar Total/TotalIngreso;
- crear VentaFirmadaConIVA;
- crear VentaFirmadaSinIVA.

Consumidores:
- Métricas Vendedores
- Resumen Ejecutivo

## Analytics

No lee archivos.
Solo recibe DataFrames ya normalizados.

## Views

No debe contener reglas comerciales complejas.
Solo filtros, presentación y acciones del usuario.
