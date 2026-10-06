"""Tests de src/metrics.py con series sintéticas (sin internet)."""
import numpy as np
import pandas as pd
import pytest

from src.metrics import CAYO, COLUMNAS, SIN_CAMBIO, SUBIO, calcular_metricas


def serie(ticker, cierres, high=None, low=None, volumen=1000, inicio="2026-01-02"):
    fechas = pd.bdate_range(inicio, periods=len(cierres))
    c = pd.Series(cierres, dtype=float)
    return pd.DataFrame({
        "ticker": ticker, "fecha": fechas,
        "open": c, "high": c + 1 if high is None else high,
        "low": c - 1 if low is None else low, "close": c, "volume": volumen,
    })


def una(df, **kw):
    m = calcular_metricas(df, **kw)
    assert len(m) == 1
    return m.iloc[0]


def test_columnas():
    m = calcular_metricas(serie("A", [1, 2, 3]))
    assert list(m.columns) == COLUMNAS


def test_plana():
    r = una(serie("A", [10, 10, 10, 10]))
    assert r.precio_min == r.precio_max == 10
    assert r.rango_abs == 0 and r.rango_pct == 0 and r.ratio == 1
    assert r.direccion == SIN_CAMBIO  # el primer mínimo y el primer máximo son el mismo día


def test_sube():
    r = una(serie("A", [10, 8, 12, 20, 15]))
    assert (r.precio_min, r.precio_max) == (8, 20)
    assert r.fecha_min == pd.Timestamp("2026-01-05")
    assert r.fecha_max == pd.Timestamp("2026-01-07")
    assert r.rango_abs == 12
    assert r.rango_pct == pytest.approx(150.0)
    assert r.ratio == pytest.approx(2.5)
    assert r.direccion == SUBIO
    assert r.precio_actual == 15 and r.fecha_actual == pd.Timestamp("2026-01-08")


def test_cae():
    r = una(serie("A", [100, 120, 60, 30, 40]))
    assert (r.precio_min, r.precio_max) == (30, 120)
    assert r.rango_pct == pytest.approx(300.0)
    assert r.direccion == CAYO


def test_con_nan():
    df = serie("A", [10, np.nan, 5, np.nan, 20])
    df.loc[1, "volume"] = np.nan
    r = una(df, sesiones=5)
    assert (r.precio_min, r.precio_max) == (5, 20)
    assert r.dias_con_dato == 3
    assert r.cobertura == pytest.approx(0.6)
    assert r.volumen_promedio == 1000
    assert r.precio_actual == 20


def test_ultimo_dato_nan_usa_el_ultimo_cierre_valido():
    r = una(serie("A", [10, 12, np.nan]))
    assert r.precio_actual == 12 and r.fecha_actual == pd.Timestamp("2026-01-05")


def test_un_solo_dato():
    r = una(serie("A", [42]), sesiones=10)
    assert r.precio_min == r.precio_max == 42
    assert r.rango_pct == 0
    assert r.direccion == SIN_CAMBIO
    assert r.cobertura == pytest.approx(0.1)


def test_sin_datos_validos():
    r = una(serie("A", [np.nan, np.nan]), sesiones=2)
    assert np.isnan(r.precio_min) and np.isnan(r.rango_pct)
    assert r.direccion is None
    assert r.dias_con_dato == 0 and r.cobertura == 0


def test_intraday_usa_high_y_low():
    df = serie("A", [10, 10, 10], high=[11, 30, 12], low=[5, 9, 9])
    cierre = una(df)
    intra = una(df, intraday=True)
    assert cierre.rango_pct == 0
    assert (intra.precio_min, intra.precio_max) == (5, 30)
    assert intra.rango_pct == pytest.approx(500.0)
    assert intra.direccion == SUBIO
    assert intra.precio_actual == 10  # el precio actual siempre es el cierre


def test_intraday_mismo_dia():
    r = una(serie("A", [10], high=[12], low=[8]), intraday=True)
    assert r.rango_pct == pytest.approx(50.0)
    assert r.direccion == SIN_CAMBIO


def test_ignora_precios_no_positivos():
    r = una(serie("A", [0, 10, 20]))
    assert r.precio_min == 10


def test_varios_tickers_orden_y_cobertura_por_defecto():
    df = pd.concat([
        serie("BAJO", [100, 110, 105, 108]),         # +10 %
        serie("ALTO", [10, 40, 20, 25]),             # +300 %
        serie("CORTO", [50, 75], inicio="2026-01-06"),  # +50 %, 2 de 4 sesiones
    ])
    m = calcular_metricas(df)
    assert m["ticker"].tolist() == ["ALTO", "CORTO", "BAJO"]
    cob = m.set_index("ticker")["cobertura"]
    assert cob["ALTO"] == 1.0 and cob["CORTO"] == pytest.approx(0.5)
    assert (m["moneda"] == "USD").all()


def test_orden_no_depende_del_orden_de_entrada():
    df = serie("A", [10, 20, 5, 15])
    r1 = una(df)
    r2 = una(df.sample(frac=1, random_state=1))
    assert (r1.fecha_min, r1.fecha_max, r1.precio_actual) == (r2.fecha_min, r2.fecha_max, r2.precio_actual)


def test_vacio():
    m = calcular_metricas(pd.DataFrame(columns=["ticker", "fecha", "open", "high", "low", "close", "volume"]))
    assert m.empty and list(m.columns) == COLUMNAS


def test_salto_maximo_con_signo():
    r = una(serie("A", [100, 102, 15, 16]))  # caída de 85 % en un día
    assert r.salto_max_pct == pytest.approx(-85.29, abs=0.01)
    assert r.fecha_salto == pd.Timestamp("2026-01-06")
    r = una(serie("B", [10, 11, np.nan, 33]))  # el NaN no corta la comparación
    assert r.salto_max_pct == pytest.approx(200.0)


def test_salto_un_solo_dato():
    r = una(serie("A", [42]))
    assert np.isnan(r.salto_max_pct) and pd.isna(r.fecha_salto)


def test_volumen_en_usd():
    df = serie("A", [10, 20, np.nan], volumen=[100, 300, 999])
    r = una(df)
    assert r.volumen_usd_promedio == pytest.approx((10 * 100 + 20 * 300) / 2)  # solo días con cierre
