"""Carga y generación de las listas de tickers (universos).

Universos: sp500 y nasdaq100. Las listas se guardan como CSV fijos en
data/universes/ (columnas ticker,nombre,sector) para no depender de la red
en cada corrida.

Regenerar:
    python -m src.universe sp500          # Wikipedia, con respaldo en pytickersymbols
    python -m src.universe nasdaq100
    python -m src.universe sp500 --fuente pytickersymbols
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_UNIVERSOS = RAIZ / "data" / "universes"
COLUMNAS = ["ticker", "nombre", "sector"]

# Wikipedia rechaza (403) el user-agent por defecto de urllib
USER_AGENT = "rango-acciones/0.1 (proyecto de analisis de acciones)"

# Por universo: página de Wikipedia, columnas de su tabla "constituents"
# (ticker, nombre, sector) y nombre del índice en pytickersymbols.
# El S&P 500 usa sectores GICS; la página del Nasdaq-100 usa industrias ICB.
UNIVERSOS = {
    "sp500": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "columnas": ("Symbol", "Security", "GICS Sector"),
        "pytickersymbols": "S&P 500",
    },
    "nasdaq100": {
        "url": "https://en.wikipedia.org/wiki/List_of_NASDAQ-100_companies",
        "columnas": ("Ticker", "Company", "ICB Industry"),
        "pytickersymbols": "NASDAQ 100",
    },
}

SECTORES_GICS = [
    "Communication Services", "Consumer Discretionary", "Consumer Staples",
    "Energy", "Financials", "Health Care", "Industrials",
    "Information Technology", "Materials", "Real Estate", "Utilities",
]
# Si pytickersymbols asigna más de un sector GICS, gana el primero de esta lista
# (p. ej. eléctricas: Utilities antes que Energy; REITs: Real Estate antes que Financials).
PRIORIDAD_SECTOR = ["Utilities", "Real Estate", "Financials",
                    "Consumer Discretionary", "Industrials"]
# Cambios de ticker que la fuente pytickersymbols aún no refleja (verificados en Yahoo)
RENOMBRADOS = {"BK": "BNY"}


def a_ticker_yahoo(ticker: str) -> str:
    """Yahoo usa guion en vez de punto para las clases de acción (BRK.B -> BRK-B)."""
    return ticker.strip().upper().replace(".", "-")


def cargar_universo(nombre: str, dir_universos: Path = DIR_UNIVERSOS) -> pd.DataFrame:
    """Lee data/universes/{nombre}.csv y devuelve un DataFrame validado."""
    ruta = Path(dir_universos) / f"{nombre}.csv"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el universo '{nombre}': {ruta}")
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    faltan = set(COLUMNAS) - set(df.columns)
    if faltan:
        raise ValueError(f"{ruta} no tiene las columnas {sorted(faltan)}")
    df["ticker"] = df["ticker"].str.strip()
    df = df[df["ticker"] != ""]
    if df["ticker"].duplicated().any():
        dup = df.loc[df["ticker"].duplicated(), "ticker"].tolist()
        raise ValueError(f"{ruta} tiene tickers duplicados: {dup}")
    return df[COLUMNAS].reset_index(drop=True)


def _columna(tabla: pd.DataFrame, prefijo: str) -> pd.Series:
    """Columna cuyo nombre empieza por `prefijo` (Wikipedia añade notas como '[1]')."""
    for c in tabla.columns:
        if str(c).startswith(prefijo):
            return tabla[c]
    raise KeyError(f"La tabla no tiene la columna '{prefijo}': {list(tabla.columns)}")


def _desde_wikipedia(universo: str) -> pd.DataFrame:
    import requests

    cfg = UNIVERSOS[universo]
    r = requests.get(cfg["url"], headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    tabla = pd.read_html(io.StringIO(r.text), attrs={"id": "constituents"}, flavor="lxml")[0]
    col_ticker, col_nombre, col_sector = cfg["columnas"]
    return pd.DataFrame({
        "ticker": _columna(tabla, col_ticker).map(a_ticker_yahoo),
        "nombre": _columna(tabla, col_nombre),
        "sector": _columna(tabla, col_sector),
    })


def _sector_gics(industrias: list[str]) -> str:
    candidatos = [s for s in SECTORES_GICS if s in industrias]
    for s in PRIORIDAD_SECTOR:
        if s in candidatos:
            return s
    return candidatos[0] if candidatos else ""


def _desde_pytickersymbols(universo: str) -> pd.DataFrame:
    # Paquete de PyPI con la composición de los índices extraída de Wikipedia.
    # Puede ir por detrás de la composición real; el sector es aproximado.
    from pytickersymbols import PyTickerSymbols

    filas = []
    for e in PyTickerSymbols().get_stocks_by_index(UNIVERSOS[universo]["pytickersymbols"]):
        t = a_ticker_yahoo(e["symbol"])
        filas.append({"ticker": RENOMBRADOS.get(t, t), "nombre": e["name"],
                      "sector": _sector_gics(e.get("industries", []))})
    return pd.DataFrame(filas)


def generar_universo(universo: str, fuente: str = "auto") -> pd.DataFrame:
    """Composición actual del índice. 'auto' intenta Wikipedia y si falla usa pytickersymbols."""
    if universo not in UNIVERSOS:
        raise ValueError(f"Universo desconocido '{universo}'. Opciones: {sorted(UNIVERSOS)}")
    if fuente in ("auto", "wikipedia"):
        try:
            df = _desde_wikipedia(universo)
            print(f"{universo} desde Wikipedia: {len(df)} tickers")
        except Exception as e:  # sin red, HTML cambiado, etc.
            if fuente == "wikipedia":
                raise
            print(f"Wikipedia no disponible ({type(e).__name__}: {e}); uso pytickersymbols")
            fuente = "pytickersymbols"
    if fuente == "pytickersymbols":
        df = _desde_pytickersymbols(universo)
        print(f"{universo} desde pytickersymbols: {len(df)} tickers")
    df = df.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    return df[COLUMNAS]


def main() -> None:
    p = argparse.ArgumentParser(description="Genera la lista de tickers de un universo")
    p.add_argument("universo", choices=sorted(UNIVERSOS))
    p.add_argument("--fuente", choices=["auto", "wikipedia", "pytickersymbols"], default="auto")
    args = p.parse_args()

    df = generar_universo(args.universo, args.fuente)
    ruta = DIR_UNIVERSOS / f"{args.universo}.csv"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
    print(f"Guardado {ruta} ({len(df)} filas)")


if __name__ == "__main__":
    main()
