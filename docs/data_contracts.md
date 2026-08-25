# Contratos de datos

## ERP Ventas normalizado

Columnas mínimas esperadas después de `read_sales_source()`:

- Fecha_dt
- TipoDocto
- Grupo comercial
- VentaMonto_num
- VentaMontoCampo
- VentaFirmadaConIVA
- VentaFirmadaSinIVA

Columnas opcionales:
- Vendedor
- Bodega
- Numero
- RazonSocial

## ERP Stock normalizado

Columnas mínimas:
- Producto
- Código

Columnas normalizadas cuando existan:
- StockDisponible_num
- StockFisico_num
- PorLlegar_num
- PorDespachar_num

Columnas opcionales:
- Descripcion
- Familia
- Bodega
