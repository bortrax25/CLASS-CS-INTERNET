"""Filtros de cobertura, precio y volumen en USD, y marca de revisión por saltos.

`aplicar_filtros` separa las métricas en dos tablas:
- pasan: las acciones que entran al ranking, con la columna `revisar`
- excluidas: ticker y motivo (puede haber varios motivos, separados por "; ")

Las marcas de revisión no excluyen: solo avisan de una variación de un día mayor a
`salto_pct` (posible spin-off o split sin ajustar). Se ponen también sin filtros.

Uso directo (resumen de filtros de un universo):
    python -m src.filters sp500
"""
from __future__ import annotations

import argparse

import pandas as pd

SIN_DATOS = "sin datos"


def _motivos(fila: pd.Series, cfg: dict) -> list[str]:
    if pd.isna(fila["rango_pct"]) or not fila["dias_con_dato"]:
        return [SIN_DATOS]
    motivos = []
    if fila["cobertura"] < cfg["cobertura_min"]:
        motivos.append(f"baja cobertura ({fila['cobertura']:.0%} < {cfg['cobertura_min']:.0%})")
    if fila["precio_actual"] < cfg["precio_actual_min"]:
        motivos.append(f"precio bajo ({fila['precio_actual']:,.2f} < {cfg['precio_actual_min']:,.2f})")
    vol = fila["volumen_usd_promedio"]
    if pd.isna(vol) or vol < cfg["volumen_usd_prom_min"]:
        motivos.append(f"ilíquida (volumen promedio {0 if pd.isna(vol) else vol:,.0f} USD/día "
                       f"< {cfg['volumen_usd_prom_min']:,.0f})")
    return motivos


def marcar_revision(metricas: pd.DataFrame, salto_pct: float) -> pd.Series:
    """Texto de aviso para las acciones con un salto de un día mayor a `salto_pct` (vacío si no)."""
    def aviso(fila):
        s = fila["salto_max_pct"]
        if pd.notna(s) and abs(s) >= salto_pct:
            return f"salto de {s:+.1f}% el {fila['fecha_salto']:%Y-%m-%d}: revisar si falta un ajuste"
        return ""
    if metricas.empty:
        return pd.Series(dtype=str)
    return metricas.apply(aviso, axis=1)


def aplicar_filtros(
    metricas: pd.DataFrame,
    cfg_filtros: dict,
    *,
    salto_pct: float = 50,
    activos: bool | None = None,
    tickers_universo: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (pasan, excluidas), conservando el orden de `metricas`.

    `activos=None` toma el valor de `cfg_filtros["activos"]`. Sin filtros solo se excluyen
    las acciones sin datos. Los tickers de `tickers_universo` que no aparecen en
    `metricas` (la descarga no trajo nada) se añaden a excluidas como "sin datos".
    """
    if activos is None:
        activos = cfg_filtros.get("activos", True)

    m = metricas.copy()
    m["revisar"] = marcar_revision(m, salto_pct)
    motivos = m.apply(lambda f: _motivos(f, cfg_filtros), axis=1) if not m.empty else pd.Series(dtype=object)
    if not activos:
        motivos = motivos.map(lambda ms: [x for x in ms if x == SIN_DATOS])
    excluir = motivos.map(bool) if not m.empty else pd.Series(dtype=bool)

    pasan = m[~excluir].reset_index(drop=True)
    excluidas = pd.DataFrame({"ticker": m.loc[excluir, "ticker"],
                              "motivo": motivos[excluir].map("; ".join)})
    if tickers_universo is not None:
        faltan = [t for t in tickers_universo if t not in set(m["ticker"])]
        excluidas = pd.concat([excluidas, pd.DataFrame({"ticker": faltan, "motivo": SIN_DATOS})])
    return pasan, excluidas.reset_index(drop=True)


def main() -> None:
    from src.config import cargar_config, ruta_proyecto
    from src.fetch import get_prices
    from src.metrics import calcular_metricas
    from src.universe import cargar_universo

    p = argparse.ArgumentParser(description="Resumen de filtros de un universo")
    p.add_argument("universo")
    p.add_argument("--sin-filtros", action="store_true")
    p.add_argument("--top", type=int, default=10)
    args = p.parse_args()

    cfg = cargar_config()
    tickers = cargar_universo(args.universo)["ticker"].tolist()
    precios = get_prices(tickers, cfg["periodo"]["inicio"], cfg["periodo"]["fin"],
                         cache_dir=ruta_proyecto(cfg["rutas"]["cache"]))
    pasan, excluidas = aplicar_filtros(
        calcular_metricas(precios), cfg["filtros"], salto_pct=cfg["revision"]["salto_pct"],
        activos=False if args.sin_filtros else None, tickers_universo=tickers)

    print(f"{len(tickers)} tickers: {len(pasan)} pasan, {len(excluidas)} excluidos")
    if not excluidas.empty:
        print(excluidas.to_string(index=False))
    marcadas = pasan[pasan["revisar"] != ""]
    if not marcadas.empty:
        print("\nPara revisar:")
        print(marcadas[["ticker", "rango_pct", "revisar"]].to_string(index=False))
    print(f"\nTop {args.top}:")
    print(pasan.head(args.top)[["ticker", "rango_pct", "direccion", "precio_actual",
                                "volumen_usd_promedio", "cobertura"]].to_string(index=False))


if __name__ == "__main__":
    main()
