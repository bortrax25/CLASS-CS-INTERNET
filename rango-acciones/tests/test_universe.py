"""Tests de src/universe.py. No usan internet."""
import pandas as pd
import pytest

from src.universe import _columna, _sector_gics, a_ticker_yahoo, cargar_universo


def test_ticker_yahoo_usa_guion():
    assert a_ticker_yahoo("BRK.B") == "BRK-B"
    assert a_ticker_yahoo(" aapl ") == "AAPL"


def test_sector_gics_prioridad():
    assert _sector_gics(["Energy", "Utilities"]) == "Utilities"
    assert _sector_gics(["Financials", "Real Estate", "REITs"]) == "Real Estate"
    assert _sector_gics(["Software", "Information Technology"]) == "Information Technology"
    assert _sector_gics(["Algo raro"]) == ""


def test_cargar_universo_ok(tmp_path):
    pd.DataFrame({"ticker": ["AAPL", "BRK-B"], "nombre": ["Apple", "Berkshire"],
                  "sector": ["IT", "Fin"]}).to_csv(tmp_path / "x.csv", index=False)
    df = cargar_universo("x", tmp_path)
    assert list(df.columns) == ["ticker", "nombre", "sector"]
    assert df["ticker"].tolist() == ["AAPL", "BRK-B"]


def test_cargar_universo_duplicados(tmp_path):
    (tmp_path / "x.csv").write_text("ticker,nombre,sector\nAAPL,a,b\nAAPL,a,b\n")
    with pytest.raises(ValueError, match="duplicados"):
        cargar_universo("x", tmp_path)


def test_cargar_universo_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        cargar_universo("nada", tmp_path)


def test_sp500_versionado():
    df = cargar_universo("sp500")
    assert 495 <= len(df) <= 510
    assert "BRK-B" in set(df["ticker"])
    assert not df["ticker"].str.contains(r"\.").any()
    assert (df["sector"] != "").all()


def test_columna_ignora_notas_de_wikipedia():
    tabla = pd.DataFrame({"Ticker": ["A"], "ICB Industry[1]": ["Technology"]})
    assert _columna(tabla, "ICB Industry").tolist() == ["Technology"]
    with pytest.raises(KeyError):
        _columna(tabla, "GICS Sector")


def test_nasdaq100_versionado():
    df = cargar_universo("nasdaq100")
    assert 95 <= len(df) <= 105
    assert {"AAPL", "MSFT", "GOOGL", "GOOG"} <= set(df["ticker"])
    assert (df["sector"] != "").all()
