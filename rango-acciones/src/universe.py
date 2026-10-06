"""Carga y generación de las listas de tickers (universos).

Las listas se guardan como CSV fijos en data/universes/ (columnas
ticker,nombre,sector) para no depender de la red en cada corrida.

Regenerar el S&P 500:
    python -m src.universe sp500                       # Wikipedia, con respaldo
    python -m src.universe sp500 --fuente pytickersymbols
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DIR_UNIVERSOS = RAIZ / "data" / "universes"
COLUMNAS = ["ticker", "nombre", "sector"]

URL_WIKI_SP500 = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

SECTORES_GICS = [
    "Communication Services", "Consumer Discretionary", "Consumer Staples",
    "Energy", "Financials", "Health Care", "Industrials",
    "Information Technology", "Materials", "Real Estate", "Utilities",
]
# Si pytickersymbols asigna más de un sector GICS, gana el primero de esta lista
# (p. ej. eléctricas: Utilities antes que Energy; REITs: Real Estate antes que Financials).
PRIORIDAD_SECTOR = ["Utilities", "Real Estate", "Financials",
                    "Consumer Discretionary", "Industrials"]


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


def _sp500_desde_wikipedia() -> pd.DataFrame:
    tabla = pd.read_html(URL_WIKI_SP500, attrs={"id": "constituents"})[0]
    return pd.DataFrame({
        "ticker": tabla["Symbol"].map(a_ticker_yahoo),
        "nombre": tabla["Security"],
        "sector": tabla["GICS Sector"],
    })


def _sector_gics(industrias: list[str]) -> str:
    candidatos = [s for s in SECTORES_GICS if s in industrias]
    for s in PRIORIDAD_SECTOR:
        if s in candidatos:
            return s
    return candidatos[0] if candidatos else ""


def _sp500_desde_pytickersymbols() -> pd.DataFrame:
    # Paquete de PyPI con la composición del índice extraída de Wikipedia.
    # El sector es aproximado (se deduce de su lista de industrias).
    from pytickersymbols import PyTickerSymbols

    filas = [
        {
            "ticker": a_ticker_yahoo(e["symbol"]),
            "nombre": e["name"],
            "sector": _sector_gics(e.get("industries", [])),
        }
        for e in PyTickerSymbols().get_stocks_by_index("S&P 500")
    ]
    return pd.DataFrame(filas)


def generar_sp500(fuente: str = "auto") -> pd.DataFrame:
    """Descarga la composición del S&P 500. 'auto' intenta Wikipedia y si falla usa pytickersymbols."""
    if fuente in ("auto", "wikipedia"):
        try:
            df = _sp500_desde_wikipedia()
            print(f"S&P 500 desde Wikipedia: {len(df)} tickers")
        except Exception as e:  # sin red, HTML cambiado, etc.
            if fuente == "wikipedia":
                raise
            print(f"Wikipedia no disponible ({type(e).__name__}); uso pytickersymbols")
            fuente = "pytickersymbols"
    if fuente == "pytickersymbols":
        df = _sp500_desde_pytickersymbols()
        print(f"S&P 500 desde pytickersymbols: {len(df)} tickers")
    df = df.drop_duplicates("ticker").sort_values("ticker").reset_index(drop=True)
    return df[COLUMNAS]


def main() -> None:
    p = argparse.ArgumentParser(description="Genera la lista de tickers de un universo")
    p.add_argument("universo", choices=["sp500"])
    p.add_argument("--fuente", choices=["auto", "wikipedia", "pytickersymbols"], default="auto")
    args = p.parse_args()

    df = generar_sp500(args.fuente)
    ruta = DIR_UNIVERSOS / f"{args.universo}.csv"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False)
    print(f"Guardado {ruta} ({len(df)} filas)")


if __name__ == "__main__":
    main()
