"""Tests de src/fetch.py. Sustituyen la descarga por datos sintéticos (sin internet)."""
import logging

import pandas as pd
import pytest

from src import fetch


def ohlcv(n=3, base=10.0, inicio="2026-01-02"):
    idx = pd.bdate_range(inicio, periods=n)
    c = [base + i for i in range(n)]
    return pd.DataFrame({"Open": c, "High": [x + 1 for x in c], "Low": [x - 1 for x in c],
                         "Close": c, "Volume": [1000] * n}, index=idx)


class Falso:
    """Descargador falso: registra las llamadas y responde según `datos` y `fallos`."""

    def __init__(self, datos, fallos=None, fallos_temporales=None):
        self.datos = datos
        self.fallos = fallos or {}
        self.temporales = dict(fallos_temporales or {})  # ticker -> veces que falla
        self.llamadas = []

    def __call__(self, tickers, start, end):
        self.llamadas.append(list(tickers))
        datos, errores = {}, {}
        for t in tickers:
            if self.temporales.get(t, 0) > 0:
                self.temporales[t] -= 1
                errores[t] = "YFRateLimitError: Too Many Requests"
            elif t in self.datos:
                datos[t] = self.datos[t]
            else:
                errores[t] = self.fallos.get(t, fetch.SIN_DATOS)
        return datos, errores


@pytest.fixture
def sin_esperas(monkeypatch):
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)


def correr(tmp_path, tickers, **kw):
    kw.setdefault("tamano_lote", 2)
    return fetch.get_prices(tickers, "2026-01-01", "2026-02-01", cache_dir=tmp_path / "cache",
                            ruta_fallidos=tmp_path / "fallidos.csv", **kw)


def test_formato_lotes_y_fallidos(tmp_path, monkeypatch, sin_esperas):
    falso = Falso({"A": ohlcv(), "B": ohlcv(base=50), "C": ohlcv(2)},
                  fallos={"X": "possibly delisted; no timezone found"})
    monkeypatch.setattr(fetch, "_descargar_lote", falso)

    df = correr(tmp_path, ["A", "B", "C", "X"])

    assert list(df.columns) == fetch.COLUMNAS
    assert sorted(df["ticker"].unique()) == ["A", "B", "C"]
    assert len(df) == 3 + 3 + 2
    assert df["fecha"].dtype.kind == "M"
    assert falso.llamadas[:2] == [["A", "B"], ["C", "X"]]
    # El fallo definitivo se reintenta una sola vez
    assert falso.llamadas[2:] == [["X"]]
    fallidos = pd.read_csv(tmp_path / "fallidos.csv")
    assert fallidos.to_dict("records") == [{"ticker": "X", "motivo": "possibly delisted; no timezone found"}]


def test_cache_evita_descargar_de_nuevo(tmp_path, monkeypatch, sin_esperas):
    falso = Falso({"A": ohlcv(), "B": ohlcv()})
    monkeypatch.setattr(fetch, "_descargar_lote", falso)
    primera = correr(tmp_path, ["A", "B", "X"])
    n = len(falso.llamadas)

    segunda = correr(tmp_path, ["A", "B", "X"])
    assert len(falso.llamadas) == n  # ni los buenos ni el fallido se vuelven a pedir
    pd.testing.assert_frame_equal(primera, segunda)

    correr(tmp_path, ["A", "B", "D"])  # solo falta D
    assert falso.llamadas[n] == ["D"]


def test_cache_se_invalida_si_cambia_el_rango_o_se_refresca(tmp_path, monkeypatch, sin_esperas):
    falso = Falso({"A": ohlcv()})
    monkeypatch.setattr(fetch, "_descargar_lote", falso)
    correr(tmp_path, ["A"])
    correr(tmp_path, ["A"], refrescar=True)
    fetch.get_prices(["A"], "2026-01-01", "2026-03-01", cache_dir=tmp_path / "cache")
    assert falso.llamadas == [["A"], ["A"], ["A"]]


def test_reintenta_fallos_transitorios(tmp_path, monkeypatch, sin_esperas):
    falso = Falso({"A": ohlcv(), "B": ohlcv()}, fallos_temporales={"B": 2})
    monkeypatch.setattr(fetch, "_descargar_lote", falso)
    df = correr(tmp_path, ["A", "B"], reintentos=4)
    assert sorted(df["ticker"].unique()) == ["A", "B"]
    assert falso.llamadas == [["A", "B"], ["B"], ["B"]]


def test_agota_reintentos(tmp_path, monkeypatch, sin_esperas):
    falso = Falso({"A": ohlcv()}, fallos_temporales={"A": 99})
    monkeypatch.setattr(fetch, "_descargar_lote", falso)
    df = correr(tmp_path, ["A"], reintentos=3)
    assert df.empty and list(df.columns) == fetch.COLUMNAS
    assert len(falso.llamadas) == 4
    assert "Too Many" in pd.read_csv(tmp_path / "fallidos.csv")["motivo"][0]


def test_recorta_al_rango_pedido(tmp_path, monkeypatch, sin_esperas):
    monkeypatch.setattr(fetch, "_descargar_lote", Falso({"A": ohlcv(30, inicio="2026-01-20")}))
    df = correr(tmp_path, ["A"])
    assert df["fecha"].max() < pd.Timestamp("2026-02-01")


def test_captura_errores_del_log():
    cap = fetch._CapturaErrores()
    rec = logging.LogRecord("yfinance", logging.ERROR, "", 0,
                            "\n2 Failed downloads:\n['AAA', 'BBB']: possibly delisted\n['CCC']: Timeout",
                            None, None)
    cap.emit(rec)
    assert cap.errores == {"AAA": "possibly delisted", "BBB": "possibly delisted", "CCC": "Timeout"}
