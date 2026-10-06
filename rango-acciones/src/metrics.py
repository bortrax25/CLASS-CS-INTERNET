"""Cálculo de métricas de rango de precio por ticker.

Entrada: el DataFrame largo de `fetch.get_prices` (ticker, fecha, open, high, low,
close, volume), con precios ajustados.

Salida: una fila por ticker con
    precio_min, fecha_min, precio_max, fecha_max   (cierre ajustado; con intraday,
                                                    mínimo de low y máximo de high)
    rango_abs = max - min
    rango_pct = (max - min) / min * 100            <- métrica principal del ranking
    ratio     = max / min
    direccion: "subió" (mínimo antes que el máximo), "cayó" (al revés) o
               "sin cambio" (mismo día: serie plana o un solo dato)
    precio_actual, fecha_actual   último cierre disponible
    volumen_promedio              media diaria de acciones negociadas
    volumen_usd_promedio          media diaria de cierre x volumen (liquidez en USD)
    dias_con_dato, cobertura      cobertura = dias_con_dato / sesiones del periodo
    salto_max_pct, fecha_salto    mayor variación de cierre a cierre (con signo). Sirve
                                  para detectar ajustes que faltan: p. ej. CTVA cayó 84 %
                                  en un día por un spin-off que Yahoo no ajustó
    moneda

Uso directo (top sin filtros, para revisar):
    python -m src.metrics sp500
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

SUBIO, CAYO, SIN_CAMBIO = "subió", "cayó", "sin cambio"

COLUMNAS = [
    "ticker", "precio_min", "fecha_min", "precio_max", "fecha_max",
    "rango_abs", "rango_pct", "ratio", "direccion",
    "precio_actual", "fecha_actual", "volumen_promedio", "volumen_usd_promedio",
    "dias_con_dato", "cobertura", "salto_max_pct", "fecha_salto", "moneda",
]


def _metricas_ticker(df: pd.DataFrame, intraday: bool) -> dict:
    """Métricas de un solo ticker. `df` viene ordenado por fecha."""
    col_min, col_max = ("low", "high") if intraday else ("close", "close")
    con_cierre = df.dropna(subset=["close"])
    # Precios <= 0 no tienen sentido y romperían rango_pct
    serie_min = df.loc[df[col_min] > 0, ["fecha", col_min]]
    serie_max = df.loc[df[col_max] > 0, ["fecha", col_max]]

    cambios = con_cierre["close"].pct_change()
    i_salto = cambios.abs().idxmax() if cambios.notna().any() else None
    fila = {
        "salto_max_pct": cambios.at[i_salto] * 100 if i_salto is not None else np.nan,
        "fecha_salto": con_cierre.at[i_salto, "fecha"] if i_salto is not None else pd.NaT,
        "dias_con_dato": len(con_cierre),
        "volumen_promedio": df["volume"].mean() if df["volume"].notna().any() else np.nan,
        "volumen_usd_promedio": (con_cierre["close"] * con_cierre["volume"]).mean()
        if con_cierre["volume"].notna().any() else np.nan,
        "precio_actual": con_cierre["close"].iloc[-1] if len(con_cierre) else np.nan,
        "fecha_actual": con_cierre["fecha"].iloc[-1] if len(con_cierre) else pd.NaT,
    }
    if serie_min.empty or serie_max.empty:
        return fila | {"precio_min": np.nan, "fecha_min": pd.NaT, "precio_max": np.nan,
                       "fecha_max": pd.NaT, "direccion": None}

    # idxmin/idxmax devuelven la primera aparición si el valor se repite
    i_min = serie_min[col_min].idxmin()
    i_max = serie_max[col_max].idxmax()
    fecha_min, fecha_max = serie_min.at[i_min, "fecha"], serie_max.at[i_max, "fecha"]
    if fecha_min < fecha_max:
        direccion = SUBIO
    elif fecha_min > fecha_max:
        direccion = CAYO
    else:
        direccion = SIN_CAMBIO
    return fila | {
        "precio_min": serie_min.at[i_min, col_min], "fecha_min": fecha_min,
        "precio_max": serie_max.at[i_max, col_max], "fecha_max": fecha_max,
        "direccion": direccion,
    }


def calcular_metricas(
    precios: pd.DataFrame,
    *,
    intraday: bool = False,
    sesiones: int | None = None,
    moneda: str = "USD",
) -> pd.DataFrame:
    """Una fila por ticker, ordenada por rango_pct de mayor a menor.

    `sesiones` es el número de días hábiles del periodo, base de la cobertura. Si no se
    indica, se usa el número de fechas distintas en `precios` (con cientos de tickers,
    equivale a las sesiones de mercado del periodo).
    """
    if precios.empty:
        return pd.DataFrame(columns=COLUMNAS)
    if sesiones is None:
        sesiones = precios["fecha"].nunique()

    filas = []
    for ticker, df in precios.sort_values(["ticker", "fecha"]).groupby("ticker", sort=False):
        filas.append({"ticker": ticker} | _metricas_ticker(df, intraday))
    m = pd.DataFrame(filas)

    m["rango_abs"] = m["precio_max"] - m["precio_min"]
    m["ratio"] = m["precio_max"] / m["precio_min"]
    m["rango_pct"] = (m["ratio"] - 1) * 100
    m["cobertura"] = (m["dias_con_dato"] / sesiones).clip(upper=1.0) if sesiones else np.nan
    m["moneda"] = moneda

    m = m.sort_values(["rango_pct", "ticker"], ascending=[False, True], na_position="last")
    return m[COLUMNAS].reset_index(drop=True)


def main() -> None:
    from src.config import cargar_config, periodo, ruta_proyecto
    from src.fetch import get_prices
    from src.universe import cargar_universo

    p = argparse.ArgumentParser(description="Métricas de rango (sin filtros) de un universo")
    p.add_argument("universo")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--intraday", action="store_true", help="usa high/low en vez del cierre")
    args = p.parse_args()

    cfg = cargar_config()
    tickers = cargar_universo(args.universo)["ticker"].tolist()
    precios = get_prices(tickers, *periodo(cfg),
                         cache_dir=ruta_proyecto(cfg["rutas"]["cache"]))
    m = calcular_metricas(precios, intraday=args.intraday)
    pd.set_option("display.width", 200)
    print(m.head(args.top).to_string(
        index=False,
        columns=["ticker", "precio_min", "fecha_min", "precio_max", "fecha_max",
                 "rango_pct", "direccion", "precio_actual", "cobertura", "salto_max_pct"],
        formatters={"rango_pct": "{:,.1f}%".format, "cobertura": "{:.0%}".format,
                    "salto_max_pct": "{:+,.1f}%".format,
                    "precio_min": "{:,.2f}".format, "precio_max": "{:,.2f}".format,
                    "precio_actual": "{:,.2f}".format},
    ))


if __name__ == "__main__":
    main()
