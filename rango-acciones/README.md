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
| S&P 500 | `data/universes/sp500.csv` | 503 | `pytickersymbols` 1.17.10 (datos de Wikipedia) |
| BVL | `data/universes/bvl.csv` | pendiente | pendiente |

Para regenerar el S&P 500: `python -m src.universe sp500`. Intenta primero Wikipedia y,
si no hay acceso, usa el paquete `pytickersymbols` de PyPI.

Notas:
- Los tickers usan la notación de Yahoo (`BRK-B`, `BF-B`, no `BRK.B`).
- La lista es una foto de la composición del índice; no refleja altas y bajas posteriores.
  Regenerarla con Wikipedia cuando haya red para tener la versión al día.
- Con la fuente `pytickersymbols`, el sector se deduce de su lista de industrias y puede
  diferir del sector GICS oficial en casos ambiguos. Es solo informativo.

## Red

yfinance necesita llegar a `query1.finance.yahoo.com`, `query2.finance.yahoo.com`,
`fc.yahoo.com` y `guce.yahoo.com`. Para regenerar el S&P 500 desde Wikipedia hace falta
`en.wikipedia.org`.
