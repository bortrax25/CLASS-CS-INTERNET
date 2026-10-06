# rango-acciones

Ranking de acciones por rango de precio (`(max - min) / min`) en 2026, sobre cierres ajustados.
Ver [PLAN.md](PLAN.md) para el diseño y el avance.

## Instalación

```bash
pip install -r requirements.txt
pytest            # no necesita internet
```

## Uso

```bash
python main.py --universe sp500 --top 50
python main.py --universe nasdaq100 --top 20 --sin-filtros
python main.py --universe sp500 --intraday
python main.py --universe sp500 --hasta 2026-09-25   # otra fecha de corte, solo esta corrida
python main.py --universe sp500 --refrescar          # ignora la caché
```

Genera `output/top_{universo}_{fecha de corte}.xlsx` (con `_intraday` o `_sinfiltros` al final
en esas variantes) y muestra el top 10 en consola.

## Universos

| Universo | Archivo | Tickers | Fuente |
|---|---|---|---|
| S&P 500 | `data/universes/sp500.csv` | 503 | Wikipedia, 2026-10-06 (sector GICS) |
| Nasdaq 100 | `data/universes/nasdaq100.csv` | 101 | Wikipedia, 2026-10-06 (industria ICB) |

Para regenerarlas: `python -m src.universe sp500` y `python -m src.universe nasdaq100`.
Intentan primero Wikipedia y, si no hay acceso, usan el paquete `pytickersymbols` de PyPI
(que va por detrás de la composición real).

Notas:
- Los tickers usan la notación de Yahoo (`BRK-B`, `BF-B`, no `BRK.B`).
- Cada lista es una foto de la composición del índice el día que se generó; no refleja
  altas y bajas posteriores ni las empresas que salieron durante 2026.
- El Nasdaq 100 tiene 101 tickers porque Alphabet cotiza con dos clases (GOOGL y GOOG).
  Muchos también están en el S&P 500; la caché de precios es compartida.
- Con la fuente `pytickersymbols`, el sector se deduce de su lista de industrias y puede
  diferir del sector GICS oficial en casos ambiguos. Es solo informativo.

## Periodo

En `config.yaml`, `periodo.inicio` y `periodo.fin` son fechas incluidas. Hoy: del
2026-01-01 al 2026-10-05. Con `fin: null` se usa hasta hoy. El Excel lleva en el nombre
la fecha de corte (`top_sp500_2026-10-05.xlsx`).

## Descarga de precios

```bash
python -m src.fetch sp500              # usa la caché si es del día
python -m src.fetch sp500 --refrescar  # fuerza la descarga
```

- Guarda cada ticker en `data/cache/{ticker}.parquet`. La caché vale por el día de descarga y por el rango de fechas pedido.
- Los tickers sin datos van a `output/fallidos_{universo}.csv` con el motivo que da Yahoo.
- Si se corre con el mercado abierto, la fila de hoy es parcial (precio y volumen del momento) y queda así en la caché hasta el día siguiente. Usar `--refrescar` después del cierre para tenerla completa.

### Fallidos

Ver `output/fallidos_sp500.csv` y `output/fallidos_nasdaq100.csv` tras cada corrida.

## Red

yfinance necesita llegar a `query1.finance.yahoo.com`, `query2.finance.yahoo.com`,
`fc.yahoo.com` y `guce.yahoo.com`. Para regenerar el S&P 500 desde Wikipedia hace falta
`en.wikipedia.org`.
