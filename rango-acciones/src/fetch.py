"""Descarga de precios diarios con caché, lotes y reintentos.

Único módulo que importa yfinance. En la Fase 2 solo se reemplaza
`_descargar_lote` (o `get_prices` completo) por otro proveedor.

Formato de salida de `get_prices`: DataFrame "largo" con columnas
    ticker, fecha, open, high, low, close, volume
Los precios son ajustados por splits y dividendos (auto_adjust=True), incluidos high y low.

Caché: un parquet por ticker en data/cache/{ticker}.parquet, más un manifiesto
(_manifiesto.json) con el rango pedido y el día de descarga. Una entrada sirve si
coincide el rango y se descargó hoy. No se descargan solo los días nuevos porque los
precios ajustados del pasado cambian con cada dividendo o split; se baja el rango completo.

Uso directo (descarga un universo y reporta):
    python -m src.fetch sp500
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

COLUMNAS = ["ticker", "fecha", "open", "high", "low", "close", "volume"]
MANIFIESTO = "_manifiesto.json"
SIN_DATOS = "sin datos"
# Fragmentos de mensajes de yfinance que indican un fallo pasajero (vale la pena reintentar)
TRANSITORIOS = ("rate limit", "too many requests", "429", "timed out", "timeout",
                "connection", "curl", "temporarily")

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- yfinance

class _CapturaErrores(logging.Handler):
    """Captura los motivos de fallo que yfinance solo escribe en su log."""

    PATRON = re.compile(r"\[([^\]]*)\]:\s*(.+)")

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.errores: dict[str, str] = {}

    def emit(self, record: logging.LogRecord) -> None:
        for linea in record.getMessage().splitlines():
            m = self.PATRON.search(linea)
            if not m:
                continue
            for t in re.findall(r"'([^']+)'", m.group(1)):
                self.errores[t] = m.group(2).strip()


def _descargar_lote(tickers: list[str], start: str, end: str) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Baja un lote con yfinance. Devuelve ({ticker: OHLCV}, {ticker: motivo de fallo})."""
    import yfinance as yf

    captura = _CapturaErrores()
    logger_yf = logging.getLogger("yfinance")
    logger_yf.addHandler(captura)
    propaga, logger_yf.propagate = logger_yf.propagate, False  # sin ruido en consola
    try:
        crudo = yf.download(tickers, start=start, end=end, group_by="ticker",
                            auto_adjust=True, threads=True, progress=False)
    except Exception as e:  # fallo de todo el lote (red, etc.)
        return {}, {t: f"{type(e).__name__}: {e}" for t in tickers}
    finally:
        logger_yf.removeHandler(captura)
        logger_yf.propagate = propaga

    datos: dict[str, pd.DataFrame] = {}
    errores: dict[str, str] = {}
    for t in tickers:
        if isinstance(crudo.columns, pd.MultiIndex) and t in crudo.columns.get_level_values(0):
            sub = crudo[t]
        elif not isinstance(crudo.columns, pd.MultiIndex) and len(tickers) == 1:
            sub = crudo
        else:
            sub = pd.DataFrame()
        if "Close" in sub.columns:
            sub = sub.dropna(subset=["Close"])
        if sub.empty or "Close" not in sub.columns:
            errores[t] = captura.errores.get(t, SIN_DATOS)
        else:
            datos[t] = sub
    return datos, errores


def _normalizar(t: str, ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = ohlcv.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.rename_axis("fecha").reset_index()
    df.insert(0, "ticker", t)
    return df[COLUMNAS]


# --------------------------------------------------------------------------- caché

def _ruta_cache(cache_dir: Path, ticker: str) -> Path:
    return cache_dir / f"{ticker}.parquet"


def _leer_manifiesto(cache_dir: Path) -> dict:
    ruta = cache_dir / MANIFIESTO
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("Manifiesto de caché corrupto; se ignora")
        return {}


def _guardar_manifiesto(cache_dir: Path, manifiesto: dict) -> None:
    tmp = cache_dir / (MANIFIESTO + ".tmp")
    tmp.write_text(json.dumps(manifiesto, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(cache_dir / MANIFIESTO)


def _entrada_vigente(entrada: dict | None, start: str, end: str, hoy: str) -> bool:
    return bool(entrada) and entrada.get("inicio") == start and entrada.get("fin") == end \
        and entrada.get("descargado") == hoy


# --------------------------------------------------------------------------- API

def resolver_fin(fin: str | None) -> str:
    """Fin exclusivo para yfinance. None = hasta hoy incluido (mañana)."""
    return fin if fin else (date.today() + timedelta(days=1)).isoformat()


def get_prices(
    tickers: list[str],
    start: str,
    end: str | None = None,
    *,
    cache_dir: Path | str,
    ruta_fallidos: Path | str | None = None,
    tamano_lote: int = 50,
    pausa_seg: float = 2.0,
    reintentos: int = 4,
    refrescar: bool = False,
) -> pd.DataFrame:
    """Precios diarios ajustados de `tickers` entre `start` (incluido) y `end` (excluido).

    Los tickers sin datos no aparecen en el resultado; se registran con su motivo en
    `ruta_fallidos` (CSV ticker,motivo) si se indica.
    """
    end = resolver_fin(end)
    hoy = date.today().isoformat()
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifiesto = _leer_manifiesto(cache_dir)
    tickers = list(dict.fromkeys(tickers))  # sin duplicados, conserva el orden

    pendientes = []
    for t in tickers:
        entrada = manifiesto.get(t)
        vigente = not refrescar and _entrada_vigente(entrada, start, end, hoy)
        if vigente and (entrada.get("motivo") or _ruta_cache(cache_dir, t).exists()):
            continue
        pendientes.append(t)
    log.info("%d tickers en caché, %d por descargar", len(tickers) - len(pendientes), len(pendientes))

    lotes = [pendientes[i:i + tamano_lote] for i in range(0, len(pendientes), tamano_lote)]
    for n, lote in enumerate(lotes, 1):
        if n > 1:
            time.sleep(pausa_seg)
        datos, errores = _descargar_lote(lote, start, end)
        for intento in range(1, reintentos + 1):
            transitorio = any(any(k in m.lower() for k in TRANSITORIOS) for m in errores.values())
            # Un fallo definitivo (deslistado, no existe) se reintenta una sola vez
            if not errores or (intento > 1 and not transitorio):
                break
            espera = pausa_seg * 2 ** intento
            log.info("Lote %d: %d sin datos%s; reintento %d/%d en %.0f s", n, len(errores),
                     " (fallo transitorio)" if transitorio else "", intento, reintentos, espera)
            time.sleep(espera)
            nuevos, errores = _descargar_lote(list(errores), start, end)
            datos.update(nuevos)

        for t, ohlcv in datos.items():
            _normalizar(t, ohlcv).to_parquet(_ruta_cache(cache_dir, t), index=False)
            manifiesto[t] = {"inicio": start, "fin": end, "descargado": hoy}
        for t, motivo in errores.items():
            _ruta_cache(cache_dir, t).unlink(missing_ok=True)
            manifiesto[t] = {"inicio": start, "fin": end, "descargado": hoy, "motivo": motivo}
        _guardar_manifiesto(cache_dir, manifiesto)  # tras cada lote, por si se corta
        log.info("Lote %d/%d: %d ok, %d fallidos", n, len(lotes), len(datos), len(errores))

    partes, fallidos = [], []
    for t in tickers:
        motivo = manifiesto.get(t, {}).get("motivo")
        ruta = _ruta_cache(cache_dir, t)
        if motivo or not ruta.exists():
            fallidos.append({"ticker": t, "motivo": motivo or SIN_DATOS})
        else:
            partes.append(pd.read_parquet(ruta))

    if ruta_fallidos is not None:
        ruta_fallidos = Path(ruta_fallidos)
        ruta_fallidos.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(fallidos, columns=["ticker", "motivo"]).to_csv(ruta_fallidos, index=False)

    if not partes:
        return pd.DataFrame(columns=COLUMNAS)
    precios = pd.concat(partes, ignore_index=True)
    # Solo el rango pedido (por si el proveedor devuelve días de más)
    precios = precios[(precios["fecha"] >= start) & (precios["fecha"] < end)]
    return precios.reset_index(drop=True)


def main() -> None:
    from src.config import cargar_config, ruta_proyecto
    from src.universe import cargar_universo

    p = argparse.ArgumentParser(description="Descarga (con caché) los precios de un universo")
    p.add_argument("universo")
    p.add_argument("--refrescar", action="store_true", help="ignora la caché")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    cfg = cargar_config()
    tickers = cargar_universo(args.universo)["ticker"].tolist()
    ruta_fallidos = ruta_proyecto(cfg["rutas"]["output"]) / f"fallidos_{args.universo}.csv"
    t0 = time.time()
    precios = get_prices(
        tickers, cfg["periodo"]["inicio"], cfg["periodo"]["fin"],
        cache_dir=ruta_proyecto(cfg["rutas"]["cache"]),
        ruta_fallidos=ruta_fallidos,
        tamano_lote=cfg["descarga"]["tamano_lote"],
        pausa_seg=cfg["descarga"]["pausa_seg"],
        reintentos=cfg["descarga"]["reintentos"],
        refrescar=args.refrescar,
    )
    ok = precios["ticker"].nunique()
    print(f"{ok}/{len(tickers)} tickers con datos, {len(precios)} filas, "
          f"{precios['fecha'].min():%Y-%m-%d} a {precios['fecha'].max():%Y-%m-%d}, "
          f"{time.time() - t0:.1f} s. Fallidos en {ruta_fallidos}")


if __name__ == "__main__":
    main()
