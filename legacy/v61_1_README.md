# Maritex Inventory Control — V61.1

## Objetivo de esta etapa
Primer paso de estabilización del proyecto.

No se modificó la lógica de:
- ERP Stock
- ERP Ventas
- Marketplaces
- Métricas de Stock
- Métricas Vendedores
- Resumen Ejecutivo
- filtros, IVA, metas o proyecciones

## Cambio estructural
Todo el CSS que antes estaba incrustado dentro de `app.py` se movió a:

`styles.css`

La carga se realiza desde:

`ui/styles.py`

## Ejecución

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Próximo paso recomendado — V61.2
Separar ERP Ventas en `services/erp_sales.py` y construir una única fuente de verdad comercial.
