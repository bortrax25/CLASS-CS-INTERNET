"""Tests de src/filters.py con métricas sintéticas (sin internet)."""
import numpy as np
import pandas as pd

from src.filters import SIN_DATOS, aplicar_filtros, marcar_revision

CFG = {"activos": True, "cobertura_min": 0.8, "precio_actual_min": 1.0, "volumen_usd_prom_min": 5_000_000}


def metricas(*filas):
    base = {"rango_pct": 50.0, "dias_con_dato": 190, "cobertura": 1.0, "precio_actual": 20.0,
            "volumen_usd_promedio": 5e7, "salto_max_pct": 5.0, "fecha_salto": pd.Timestamp("2026-03-02")}
    return pd.DataFrame([base | f for f in filas])


def motivos(excluidas):
    return dict(zip(excluidas["ticker"], excluidas["motivo"]))


def test_pasa_todo_lo_sano():
    pasan, excl = aplicar_filtros(metricas({"ticker": "A"}, {"ticker": "B"}), CFG)
    assert pasan["ticker"].tolist() == ["A", "B"] and excl.empty


def test_cada_filtro_y_motivo():
    m = metricas(
        {"ticker": "OK"},
        {"ticker": "COB", "cobertura": 0.42, "dias_con_dato": 80},
        {"ticker": "PENNY", "precio_actual": 0.5},
        {"ticker": "ILIQ", "volumen_usd_promedio": 900_000},
        {"ticker": "VOLNAN", "volumen_usd_promedio": np.nan},
    )
    pasan, excl = aplicar_filtros(m, CFG)
    assert pasan["ticker"].tolist() == ["OK"]
    mot = motivos(excl)
    assert mot["COB"].startswith("baja cobertura (42%")
    assert mot["PENNY"].startswith("precio bajo (0.50")
    assert mot["ILIQ"].startswith("ilíquida")
    assert mot["VOLNAN"].startswith("ilíquida")


def test_limites_inclusivos():
    m = metricas({"ticker": "JUSTO", "cobertura": 0.8, "precio_actual": 1.0, "volumen_usd_promedio": 5_000_000})
    pasan, excl = aplicar_filtros(m, CFG)
    assert pasan["ticker"].tolist() == ["JUSTO"] and excl.empty


def test_varios_motivos_juntos():
    m = metricas({"ticker": "X", "cobertura": 0.1, "precio_actual": 0.2, "volumen_usd_promedio": 10})
    _, excl = aplicar_filtros(m, CFG)
    assert excl.loc[0, "motivo"].count("; ") == 2


def test_sin_datos_y_tickers_que_no_bajaron():
    m = metricas({"ticker": "A"}, {"ticker": "VACIO", "rango_pct": np.nan, "dias_con_dato": 0})
    pasan, excl = aplicar_filtros(m, CFG, tickers_universo=["A", "VACIO", "FALLIDO"])
    assert pasan["ticker"].tolist() == ["A"]
    assert motivos(excl) == {"VACIO": SIN_DATOS, "FALLIDO": SIN_DATOS}


def test_sin_filtros_solo_excluye_sin_datos():
    m = metricas({"ticker": "PENNY", "precio_actual": 0.5, "cobertura": 0.1},
                 {"ticker": "VACIO", "rango_pct": np.nan, "dias_con_dato": 0})
    pasan, excl = aplicar_filtros(m, CFG, activos=False)
    assert pasan["ticker"].tolist() == ["PENNY"]
    assert motivos(excl) == {"VACIO": SIN_DATOS}
    # También desde config
    pasan2, _ = aplicar_filtros(m, CFG | {"activos": False})
    assert pasan2["ticker"].tolist() == ["PENNY"]


def test_conserva_el_orden_del_ranking():
    m = metricas({"ticker": "C", "rango_pct": 300.0}, {"ticker": "X", "precio_actual": 0.1},
                 {"ticker": "A", "rango_pct": 100.0})
    pasan, _ = aplicar_filtros(m, CFG)
    assert pasan["ticker"].tolist() == ["C", "A"]


def test_marca_revision_sin_excluir():
    m = metricas({"ticker": "CTVA", "salto_max_pct": -83.8, "fecha_salto": pd.Timestamp("2026-10-01")},
                 {"ticker": "MRNA", "salto_max_pct": 177.0, "fecha_salto": pd.Timestamp("2026-08-19")},
                 {"ticker": "NORMAL", "salto_max_pct": 49.9},
                 {"ticker": "NAN", "salto_max_pct": np.nan, "fecha_salto": pd.NaT})
    pasan, excl = aplicar_filtros(m, CFG, salto_pct=50)
    assert excl.empty
    r = dict(zip(pasan["ticker"], pasan["revisar"]))
    assert r["CTVA"].startswith("salto de -83.8% el 2026-10-01")
    assert r["MRNA"].startswith("salto de +177.0% el 2026-08-19")
    assert r["NORMAL"] == "" and r["NAN"] == ""


def test_revision_tambien_sin_filtros():
    m = metricas({"ticker": "CTVA", "salto_max_pct": -83.8, "precio_actual": 0.5})
    pasan, _ = aplicar_filtros(m, CFG, activos=False)
    assert pasan.loc[0, "revisar"] != ""


def test_vacio():
    m = metricas({"ticker": "A"}).iloc[0:0]
    pasan, excl = aplicar_filtros(m, CFG, tickers_universo=["A"])
    assert pasan.empty and motivos(excl) == {"A": SIN_DATOS}
    assert marcar_revision(m, 50).empty
