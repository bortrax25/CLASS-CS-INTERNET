# Plan: Top de acciones con mayor rango de precio en 2026

## Objetivo
Encontrar las empresas cotizadas cuya diferencia entre el precio máximo y el mínimo durante 2026 (desde el 1 de enero hasta la fecha de ejecución) sea la mayor, y entregar un ranking en Excel.

- **Fase 1 (este plan):** validar la lógica con yfinance sobre dos muestras, el S&P 500 y la Bolsa de Valores de Lima (BVL).
- **Fase 2 (después):** escalar a unas 50 mil empresas cambiando solo la fuente de datos.

---

## Decisiones de diseño (ya tomadas)

| Tema | Decisión | Por qué |
|---|---|---|
| Métrica principal | `rango_pct = (max - min) / min * 100` | Comparable entre acciones caras y baratas, y entre monedas |
| Métricas secundarias | `rango_abs = max - min` (en moneda local), `ratio = max / min` | Para consulta. No ordenan el top |
| Precio usado | Cierre ajustado (`auto_adjust=True`) | Evita que los splits y contrasplits inflen el rango |
| Opción alternativa | Flag `--intraday` que usa High/Low | Para comparar. No es la opción por defecto |
| Periodo | `2026-01-01` hasta hoy | Configurable en `config.yaml` |
| Cobertura mínima | Excluir tickers con menos del 80 % de días hábiles con dato | Deja fuera las IPO y los deslistados del año, que tienen periodos cortos. Configurable |
| Filtros anti-ruido | Precio mínimo (por ejemplo $1) y volumen promedio diario mínimo | Evita que el top se llene de penny stocks ilíquidas. Configurable, y desactivables |

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
│   ├── universes/         # sp500.csv, bvl.csv (lista de tickers fija, versionada)
│   └── cache/             # precios descargados en .parquet (en .gitignore)
├── output/                # rankings .xlsx (en .gitignore)
├── src/
│   ├── universe.py        # carga y genera la lista de tickers
│   ├── fetch.py           # descarga con caché, lotes y reintentos
│   ├── metrics.py         # cálculo de min, max, fechas, rango, cobertura
│   ├── filters.py         # filtros de precio, volumen y cobertura
│   └── report.py          # exporta el Excel
├── main.py                # CLI: python main.py --universe sp500 --top 50
└── tests/
    ├── test_universe.py
    ├── test_metrics.py    # con datos sintéticos, sin internet
    └── test_filters.py
```

La fuente de datos va aislada en `fetch.py` detrás de una función `get_prices(tickers, start, end) -> DataFrame`. En la Fase 2 solo se reemplaza esa función.

---

## Pasos de trabajo (en orden)

### Paso 0: Preparar el entorno en la nube
- [x] Crear el proyecto y abrirlo en Claude Code en la nube. *(Se creó como carpeta `rango-acciones/` dentro del repo `CLASS-CS-INTERNET`.)*
- [x] **Revisar el acceso a red del entorno.** *(2026-10-06: el proxy del entorno responde 403 para `query1.finance.yahoo.com`, `query2.finance.yahoo.com`, `fc.yahoo.com` y `guce.yahoo.com`, y también para `en.wikipedia.org`. Hay que agregarlos a los dominios permitidos o usar acceso completo.)*
- [ ] Prueba rápida: `python -c "import yfinance as yf; print(yf.download('AAPL', period='5d'))"` *(falla hasta habilitar los dominios de Yahoo)*

### Paso 1: Universos
- [x] `data/universes/sp500.csv` con las columnas `ticker,nombre,sector` (503 tickers). Se genera con `python -m src.universe sp500`: intenta Wikipedia con `pd.read_html` y, si no hay red, usa el paquete `pytickersymbols` de PyPI. Los tickers con punto van con guion (`BRK-B`, `BF-B`).
- [ ] Confirmar con yfinance que los 503 tickers devuelven datos *(pendiente de red; se hará en el Paso 2 con `fallidos.csv`)*.
- [ ] `data/universes/bvl.csv`. Yahoo usa el sufijo `.LM` para Lima (por ejemplo `VOLCABC1.LM`). **Hay que verificar ticker por ticker cuáles devuelven datos**, porque la cobertura de la BVL en Yahoo es irregular. Guarda solo los que respondan y anota los que fallan.

### Paso 2: Descarga con caché (`fetch.py`)
- [ ] Descargar en lotes de 50 a 100 tickers con `yf.download(..., group_by='ticker', auto_adjust=True, threads=True)`.
- [ ] Hacer una pausa entre lotes y reintentar con backoff si hay error 429 o una respuesta vacía.
- [ ] Guardar cada ticker en `data/cache/{ticker}.parquet` y, al repetir la corrida, descargar solo lo que falta.
- [ ] Registrar en `output/fallidos.csv` los tickers sin datos.

### Paso 3: Métricas (`metrics.py`)
Por ticker:
- [ ] `precio_min`, `fecha_min`, `precio_max`, `fecha_max`
- [ ] `rango_abs`, `rango_pct`, `ratio`
- [ ] `direccion`: si el mínimo fue antes que el máximo, la acción "subió"; si no, "cayó". Así se distinguen las que explotaron de las que colapsaron.
- [ ] `precio_actual`, `volumen_promedio`, `cobertura` (porcentaje de días con dato), `moneda`
- [ ] Tests con series sintéticas: una plana, una que sube, una que cae, una con NaN y una con un solo dato.

### Paso 4: Filtros (`filters.py`)
- [ ] Cobertura mínima, precio mínimo y volumen mínimo, todo leído desde `config.yaml`.
- [ ] Flag `--sin-filtros` para ver el ranking en bruto.

### Paso 5: Reporte (`report.py`)
Excel `output/top_{universo}_{fecha}.xlsx` con tres hojas:
1. **Top N**: ranking ordenado por `rango_pct`
2. **Todos**: todas las empresas que pasaron los filtros
3. **Excluidos**: ticker y motivo (sin datos, baja cobertura, ilíquida, etc.)

Con formato de porcentajes, fechas legibles y la fila de encabezados congelada.

### Paso 6: CLI (`main.py`)
```
python main.py --universe sp500 --top 50
python main.py --universe bvl --top 20 --sin-filtros
python main.py --universe sp500 --intraday
```

### Paso 7: Validación manual
- [ ] Revisar a mano 3 tickers del top contra un gráfico de Yahoo Finance o TradingView y confirmar que el mínimo y el máximo coinciden.
- [ ] Revisar si alguno del top tuvo un split en 2026 y confirmar que el ajuste funcionó.

---

## Criterios de "listo" (Fase 1)
- `pytest` pasa sin internet.
- La corrida del S&P 500 termina en menos de 10 minutos la primera vez y en menos de 1 minuto con caché.
- El Excel abre bien y el top 3 coincide con la verificación manual.
- La lista de tickers fallidos está documentada.

---

## Fase 2 (para después, no implementar aún)
- Cambiar `fetch.py` por un proveedor con descarga masiva por bolsa (EODHD, Financial Modeling Prep, Tiingo u otro). Comparar precio y cobertura antes de elegir.
- Universo global de unos 50 mil tickers desde el listado de bolsas del proveedor.
- Convertir `rango_abs` a USD si se quiere comparar en absoluto.
- Agregar capitalización de mercado como filtro.
