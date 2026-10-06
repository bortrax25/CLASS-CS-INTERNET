# Proyecto: rango-acciones
Ranking de acciones por rango de precio (max-min) en 2026. Leer PLAN.md antes de empezar.

- Python 3.11+, pandas, yfinance. Instalar con `pip install -r requirements.txt`.
- La métrica principal es rango_pct = (max-min)/min, sobre cierres ajustados. No cambiar sin preguntar.
- Toda la descarga pasa por src/fetch.py (get_prices). El resto del código no importa yfinance.
- Los tests no deben usar internet; usar datos sintéticos.
- Trabajar un paso de PLAN.md a la vez y marcar las casillas al terminar.
- Comentarios y mensajes de commit en español.
