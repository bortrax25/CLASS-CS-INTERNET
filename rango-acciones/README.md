# rango-acciones

Ranking de acciones por rango de precio (`(max - min) / min`) en 2026, sobre cierres ajustados.
Ver [PLAN.md](PLAN.md) para el diseño y el avance.

## Instalación

```bash
pip install -r requirements.txt
pytest            # no necesita internet
```

## Universos

| Universo | Archivo | Tickers | Fuente |
|---|---|---|---|
| S&P 500 | `data/universes/sp500.csv` | 503 (501 con datos) | `pytickersymbols` 1.17.10 (datos de Wikipedia) |
| BVL | `data/universes/bvl.csv` | pendiente | pendiente |

Para regenerar el S&P 500: `python -m src.universe sp500`. Intenta primero Wikipedia y,
si no hay acceso, usa el paquete `pytickersymbols` de PyPI.

Notas:
- Los tickers usan la notación de Yahoo (`BRK-B`, `BF-B`, no `BRK.B`).
- La lista es una foto de la composición del índice; no refleja altas y bajas posteriores.
  Regenerarla con Wikipedia cuando haya red para tener la versión al día.
- Con la fuente `pytickersymbols`, el sector se deduce de su lista de industrias y puede
  diferir del sector GICS oficial en casos ambiguos. Es solo informativo.

## Descarga de precios

```bash
python -m src.fetch sp500              # usa la caché si es del día
python -m src.fetch sp500 --refrescar  # fuerza la descarga
```

- Guarda cada ticker en `data/cache/{ticker}.parquet`. La caché vale por el día de descarga y por el rango de fechas pedido.
- Los tickers sin datos van a `output/fallidos_{universo}.csv` con el motivo que da Yahoo.
- Si se corre con el mercado abierto, la fila de hoy es parcial (precio y volumen del momento) y queda así en la caché hasta el día siguiente. Usar `--refrescar` después del cierre para tenerla completa.

### Fallidos conocidos del S&P 500 (2026-10-06)

| Ticker | Situación |
|---|---|
| CTRA (Coterra) | Sin datos en Yahoo ("possibly delisted") |
| HOLX (Hologic) | Sin datos en Yahoo ("possibly delisted") |
| AVB, EQR, EA | Yahoo solo devuelve 1 día suelto de agosto. Los excluirá el filtro de cobertura |
| BK (BNY) | Cambió de ticker a BNY; ya corregido en `sp500.csv` |

## Red

yfinance necesita llegar a `query1.finance.yahoo.com`, `query2.finance.yahoo.com`,
`fc.yahoo.com` y `guce.yahoo.com`. Para regenerar el S&P 500 desde Wikipedia hace falta
`en.wikipedia.org`.
