"""CLI de rango-acciones: descarga, métricas, filtros y Excel en un solo paso.

Uso:
    python main.py --universe sp500 --top 50
    python main.py --universe nasdaq100 --top 20 --sin-filtros
    python main.py --universe sp500 --intraday
    python main.py --universe sp500 --hasta 2026-09-25     # otra fecha de corte
    python main.py --universe sp500 --refrescar            # ignora la caché

El periodo sale de config.yaml (inicio y fin, ambos incluidos); --hasta cambia el fin
solo para esa corrida. El Excel queda en output/top_{universo}_{fin}[_intraday][_sinfiltros].xlsx.
"""
from __future__ import annotations

import argparse
import copy
import logging
import sys
import time
from datetime import date
from pathlib import Path

from src.config import cargar_config, periodo, ruta_proyecto
from src.fetch import get_prices
from src.filters import aplicar_filtros
from src.metrics import calcular_metricas
from src.report import exportar_excel
from src.universe import UNIVERSOS, cargar_universo


def nombre_archivo(universo: str, hasta: date, intraday: bool, sin_filtros: bool) -> str:
    sufijo = ("_intraday" if intraday else "") + ("_sinfiltros" if sin_filtros else "")
    return f"top_{universo}_{hasta.isoformat()}{sufijo}.xlsx"


def ejecutar(
    universo: str,
    *,
    top: int = 50,
    sin_filtros: bool = False,
    intraday: bool = False,
    refrescar: bool = False,
    hasta: str | None = None,
    cfg: dict | None = None,
) -> Path:
    """Corre todo el proceso y devuelve la ruta del Excel."""
    cfg = copy.deepcopy(cfg if cfg is not None else cargar_config())
    if hasta:
        cfg["periodo"]["fin"] = hasta
    inicio, fin_exclusivo = periodo(cfg)
    fin = cfg["periodo"]["fin"]
    corte = date.fromisoformat(str(fin)) if fin else date.today()
    if corte < date.fromisoformat(inicio):
        raise ValueError(f"La fecha final ({corte}) es anterior al inicio ({inicio})")

    uni = cargar_universo(universo)
    tickers = uni["ticker"].tolist()
    dir_output = ruta_proyecto(cfg["rutas"]["output"])
    t0 = time.time()

    precios = get_prices(
        tickers, inicio, fin_exclusivo,
        cache_dir=ruta_proyecto(cfg["rutas"]["cache"]),
        ruta_fallidos=dir_output / f"fallidos_{universo}.csv",
        tamano_lote=cfg["descarga"]["tamano_lote"],
        pausa_seg=cfg["descarga"]["pausa_seg"],
        reintentos=cfg["descarga"]["reintentos"],
        refrescar=refrescar,
    )
    if precios.empty:
        raise RuntimeError("No se obtuvo ningún precio; revisa la red o el periodo")

    metricas = calcular_metricas(precios, intraday=intraday)
    pasan, excluidas = aplicar_filtros(
        metricas, cfg["filtros"], salto_pct=cfg["revision"]["salto_pct"],
        activos=False if sin_filtros else None, tickers_universo=tickers,
    )

    f = cfg["filtros"]
    filtros_txt = ("ninguno (ranking en bruto)" if sin_filtros or not f.get("activos", True) else
                   f"cobertura >= {f['cobertura_min']:.0%}, precio actual >= {f['precio_actual_min']} USD, "
                   f"volumen >= {f['volumen_usd_prom_min']:,} USD/día")
    parametros = {
        "Universo": universo,
        "Desde (incluido)": inicio,
        "Hasta (incluido)": corte.isoformat(),
        "Datos": f"{precios['fecha'].min():%Y-%m-%d} a {precios['fecha'].max():%Y-%m-%d}, "
                 f"{precios['fecha'].nunique()} sesiones",
        "Precio": ("intraday: mínimo de low y máximo de high (ajustados)" if intraday
                   else "cierre ajustado por splits y dividendos"),
        "Filtros": filtros_txt,
        "Revisar": f"salto de un día >= {cfg['revision']['salto_pct']}% (marca, no excluye)",
        "Resultado": f"{len(pasan)} en el ranking, {len(excluidas)} excluidas de {len(tickers)}",
        "Fuente": "Yahoo Finance (yfinance)",
        "Generado": date.today().isoformat(),
    }
    ruta = exportar_excel(pasan, excluidas, dir_output / nombre_archivo(universo, corte, intraday, sin_filtros),
                          top_n=top, universo=uni, parametros=parametros)

    print(f"\n{universo}: {len(pasan)} en el ranking, {len(excluidas)} excluidas "
          f"({parametros['Datos']}) en {time.time() - t0:.1f} s")
    cols = ["ticker", "rango_pct", "direccion", "fecha_min", "fecha_max"]
    print(pasan.head(min(top, 10))[cols].to_string(
        index=False, formatters={"rango_pct": "{:,.1f}%".format,
                                 "fecha_min": "{:%Y-%m-%d}".format, "fecha_max": "{:%Y-%m-%d}".format}))
    revisar = pasan.head(top)
    revisar = revisar[revisar["revisar"] != ""]
    if not revisar.empty:
        print("\nPara revisar en el top:")
        for t, r in zip(revisar["ticker"], revisar["revisar"]):
            print(f"  {t}: {r}")
    print(f"\nExcel: {ruta}")
    return ruta


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ranking de acciones por rango de precio (max-min) en 2026")
    p.add_argument("--universe", required=True, choices=sorted(UNIVERSOS), help="universo de tickers")
    p.add_argument("--top", type=int, default=50, help="tamaño de la hoja Top N (por defecto 50)")
    p.add_argument("--sin-filtros", action="store_true", help="ranking en bruto, sin filtros")
    p.add_argument("--intraday", action="store_true", help="usa high/low en vez del cierre ajustado")
    p.add_argument("--hasta", metavar="AAAA-MM-DD", help="fecha final incluida (por defecto, la de config.yaml)")
    p.add_argument("--refrescar", action="store_true", help="ignora la caché y descarga todo")
    args = p.parse_args(argv)

    if args.top < 1:
        p.error("--top debe ser al menos 1")
    if args.hasta:
        try:
            date.fromisoformat(args.hasta)
        except ValueError:
            p.error(f"--hasta no es una fecha AAAA-MM-DD: {args.hasta}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        ejecutar(args.universe, top=args.top, sin_filtros=args.sin_filtros, intraday=args.intraday,
                 refrescar=args.refrescar, hasta=args.hasta)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
