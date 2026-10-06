# Plan: Top de acciones con mayor rango de precio en 2026

## Objetivo
Encontrar las empresas cotizadas cuya diferencia entre el precio máximo y el mínimo durante 2026 (desde el 1 de enero hasta la fecha de ejecución) sea la mayor, y entregar un ranking en Excel.

- **Fase 1 (este plan):** validar la lógica con yfinance sobre dos índices de EE. UU., el S&P 500 y el Nasdaq 100. Todo cotiza en USD.
- **Fase 2 (después):** escalar a unas 50 mil empresas cambiando solo la fuente de datos.

---

## Decisiones de diseño (ya tomadas)

| Tema | Decisión | Por qué |
|---|---|---|
| Métrica principal | `rango_pct = (max - min) / min * 100` | Comparable entre acciones caras y baratas, y entre monedas |
| Métricas secundarias | `rango_abs = max - min` (en moneda local), `ratio = max / min` | Para consulta. No ordenan el top |
| Precio usado | Cierre ajustado (`auto_adjust=True`) | Evita que los splits y contrasplits inflen el rango |
| Opción alternativa | Flag `--intraday` que usa High/Low | Para comparar. No es la opción por defecto |
| Periodo | `2026-01-01` al `2026-10-05`, ambos incluidos | Configurable en `config.yaml` (`fin: null` = hasta hoy). El corte al 5 de octubre se pidió para que los Excel no usen datos posteriores |
| Cobertura mínima | Excluir tickers con menos del 80 % de días hábiles con dato | Deja fuera las IPO y los deslistados del año, que tienen periodos cortos. Configurable |
| Filtros anti-ruido | Precio actual mínimo ($1) y volumen promedio diario mínimo **en USD** (cierre × volumen, $5 M) | Evita que el top se llene de penny stocks ilíquidas. En USD y no en acciones para no castigar acciones caras (NVR). Configurable, y desactivables |
| Saltos de un día > 50 % | Se marcan para revisión en la columna `revisar`, no se excluyen | Pueden ser spin-offs sin ajustar (CTVA) o noticias reales (MRNA) |

---

## Estructura del repositorio

El proyecto vive en la carpeta `rango-acciones/` del repo `CLASS-CS-INTERNET`.

```
rango-acciones/
├── CLAUDE.md              # Contexto para Claude Code
├── PLAN.md                # Este archivo
├── README.md
├── requirements.txt       # pandas, yfinance, openpyxl, pyyaml, pyarrow, pytest
├── config.yaml            # fechas, filtros, universo, rutas
├── pytest.ini
├── data/
│   ├── universes/         # sp500.csv, nasdaq100.csv (lista de tickers fija, versionada)
│   └── cache/             # precios descargados en .parquet (en .gitignore)
├── output/                # rankings .xlsx (en .gitignore)
├── src/
│   ├── config.py          # lee config.yaml
│   ├── universe.py        # carga y genera la lista de tickers
│   ├── fetch.py           # descarga con caché, lotes y reintentos
│   ├── metrics.py         # cálculo de min, max, fechas, rango, cobertura
│   ├── filters.py         # filtros de precio, volumen y cobertura
│   └── report.py          # exporta el Excel
├── main.py                # CLI: python main.py --universe sp500 --top 50
└── tests/
    ├── test_universe.py
    ├── test_fetch.py      # descarga simulada, sin internet
    ├── test_metrics.py    # con datos sintéticos, sin internet
    └── test_filters.py
```

La fuente de datos va aislada en `fetch.py` detrás de una función `get_prices(tickers, start, end) -> DataFrame`. En la Fase 2 solo se reemplaza esa función.

---

## Pasos de trabajo (en orden)

### Paso 0: Preparar el entorno en la nube
- [x] Crear el proyecto y abrirlo en Claude Code en la nube. *(Se creó como carpeta `rango-acciones/` dentro del repo `CLASS-CS-INTERNET`.)*
- [x] **Revisar el acceso a red del entorno.** *(2026-10-06: al inicio el proxy bloqueaba `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com`, `guce.yahoo.com` y `en.wikipedia.org`. Ya están habilitados.)*
- [x] Prueba rápida: `python -c "import yfinance as yf; print(yf.download('AAPL', period='5d'))"`

### Paso 1: Universos
- [x] `data/universes/sp500.csv` con las columnas `ticker,nombre,sector` (503 tickers, sector GICS). Se genera con `python -m src.universe sp500` desde Wikipedia (composición al 2026-10-06); si no hay red, usa el paquete `pytickersymbols` de PyPI, que va atrasado. Los tickers con punto van con guion (`BRK-B`, `BF-B`).
- [x] `data/universes/nasdaq100.csv` (101 tickers: Alphabet tiene GOOGL y GOOG; sector según la industria ICB de Wikipedia). Se genera con `python -m src.universe nasdaq100`.
- [x] Confirmar con yfinance que todos devuelven datos: 503/503 y 101/101. Con historia corta en 2026: HONA y FDXF (spin-offs) y SPCX (IPO); el filtro de cobertura los dejará fuera.

### Paso 2: Descarga con caché (`fetch.py`)
- [x] Descargar en lotes de 50 a 100 tickers con `yf.download(..., group_by='ticker', auto_adjust=True, threads=True)`. *(`python -m src.fetch sp500`)*
- [x] Hacer una pausa entre lotes y reintentar con backoff si hay error 429 o una respuesta vacía. Los fallos definitivos (deslistado) se reintentan una sola vez.
- [x] Guardar cada ticker en `data/cache/{ticker}.parquet` y, al repetir la corrida, descargar solo lo que falta. La caché vale por el día de descarga y el rango pedido; al día siguiente se baja todo de nuevo, porque los precios ajustados del pasado cambian con cada dividendo o split.
- [x] Registrar los tickers sin datos, con su motivo, en `output/fallidos_{universo}.csv` (uno por universo para que no se pisen).

Resultado (2026-10-06): S&P 500 503/503 con datos, 95 s sin caché y 1,3 s con caché. Nasdaq 100 101/101; comparte caché con el S&P 500 y solo bajó los 15 tickers que no están en él.

### Paso 3: Métricas (`metrics.py`)
Por ticker:
- [x] `precio_min`, `fecha_min`, `precio_max`, `fecha_max` (con `--intraday`: mínimo de low y máximo de high)
- [x] `rango_abs`, `rango_pct`, `ratio`
- [x] `direccion`: si el mínimo fue antes que el máximo, la acción "subió"; si no, "cayó". Así se distinguen las que explotaron de las que colapsaron. Si caen el mismo día (serie plana o un solo dato): "sin cambio".
- [x] `precio_actual` (y `fecha_actual`), `volumen_promedio`, `dias_con_dato`, `cobertura` (días con dato / sesiones del periodo), `moneda` (siempre USD en estos dos índices)
- [x] Extra: `salto_max_pct` y `fecha_salto`, la mayor variación de un día. Detecta ajustes que Yahoo no aplicó: CTVA cae 84 % el 2026-10-01 por el spin-off de Corteva y queda 2.º del S&P 500 con un rango falso. HON y FDX sí están ajustados por sus spin-offs. Decisión: se marcan para revisar, no se excluyen (Paso 4).
- [x] Tests con series sintéticas: una plana, una que sube, una que cae, una con NaN y una con un solo dato (más intraday, varios tickers y saltos).

Revisión rápida: `python -m src.metrics sp500 --top 15` (sin filtros).

### Paso 4: Filtros (`filters.py`)
- [x] Cobertura mínima, precio actual mínimo y volumen mínimo en USD, todo leído desde `config.yaml`. Las excluidas salen con su motivo (pueden ser varios), y los tickers sin datos de la descarga también.
- [x] Volumen en USD en vez de acciones: con 100 mil acciones/día NVR quedaba excluida como ilíquida aunque mueve ~200 M USD al día. Se añadió `volumen_usd_promedio` a las métricas.
- [x] Marca `revisar` para saltos de un día ≥ `revision.salto_pct` (50 %). No excluye y se aplica también sin filtros.
- [x] Sin filtros (`activos=False` o `filtros.activos: false`) para ver el ranking en bruto; solo se excluyen las que no tienen datos. El flag `--sin-filtros` de `main.py` llega en el Paso 6.

Resultado (2026-10-06): S&P 500 501/503 pasan (fuera HONA y FDXF por cobertura); Nasdaq 100 99/101 (fuera SPCX y HONA). Para revisar: CTVA y MRNA.
Revisión rápida: `python -m src.filters sp500` (o `--sin-filtros`).

### Paso 5: Reporte (`report.py`)
Excel `output/top_{universo}_{fecha}.xlsx` con tres hojas:
1. **Top N**: ranking ordenado por `rango_pct`
2. **Todos**: todas las empresas que pasaron los filtros
3. **Excluidos**: ticker y motivo (sin datos, baja cobertura, ilíquida, etc.)

Con formato de porcentajes, fechas legibles y la fila de encabezados congelada.

- [x] `src/report.py` con `exportar_excel`: hojas "Top N", "Todos", "Excluidos" y una cuarta, "Parámetros", con el periodo y los filtros usados.
- [x] Nombre y sector de cada empresa; `Rango abs`, `Rango %` y `Ratio` como fórmulas sobre el mínimo y el máximo; porcentajes guardados como fracciones; fechas `yyyy-mm-dd`; Arial; autofiltro; encabezados y ticker congelados; comentarios que explican las columnas clave.
- [x] Filas con salto sospechoso (`Revisar`) resaltadas en amarillo.
- [x] Verificado con LibreOffice (2026-10-06): 1.653 fórmulas en el S&P 500 y 447 en el Nasdaq 100, sin errores y con los mismos valores que calcula Python.

### Paso 6: CLI (`main.py`)
```
python main.py --universe sp500 --top 50
python main.py --universe nasdaq100 --top 20 --sin-filtros
python main.py --universe sp500 --intraday
```

### Paso 7: Validación manual
- [ ] Revisar a mano 3 tickers del top contra un gráfico de Yahoo Finance o TradingView y confirmar que el mínimo y el máximo coinciden.
- [ ] Revisar si alguno del top tuvo un split en 2026 y confirmar que el ajuste funcionó.

---

## Criterios de "listo" (Fase 1)
- `pytest` pasa sin internet.
- La corrida del S&P 500 (y la del Nasdaq 100) termina en menos de 10 minutos la primera vez y en menos de 1 minuto con caché.
- El Excel abre bien y el top 3 coincide con la verificación manual.
- La lista de tickers fallidos está documentada.

---

## Fase 2 (para después, no implementar aún)
- Cambiar `fetch.py` por un proveedor con descarga masiva por bolsa (EODHD, Financial Modeling Prep, Tiingo u otro). Comparar precio y cobertura antes de elegir.
- Universo global de unos 50 mil tickers desde el listado de bolsas del proveedor.
- Convertir `rango_abs` a USD si se quiere comparar en absoluto.
- Agregar capitalización de mercado como filtro.
