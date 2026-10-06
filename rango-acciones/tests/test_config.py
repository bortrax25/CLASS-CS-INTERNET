"""Tests de src/config.py."""
from datetime import date

from src.config import cargar_config, periodo


def test_fin_inclusivo_pasa_a_exclusivo():
    assert periodo({"periodo": {"inicio": "2026-01-01", "fin": "2026-10-05"}}) == ("2026-01-01", "2026-10-06")
    # YAML sin comillas entrega un date
    assert periodo({"periodo": {"inicio": date(2026, 1, 1), "fin": date(2026, 12, 31)}}) == ("2026-01-01", "2027-01-01")


def test_fin_nulo_es_hasta_hoy():
    assert periodo({"periodo": {"inicio": "2026-01-01", "fin": None}}) == ("2026-01-01", None)


def test_config_del_proyecto():
    cfg = cargar_config()
    assert cfg["periodo"]["inicio"] == "2026-01-01"
    assert periodo(cfg)[1] is None or periodo(cfg)[1] > "2026-01-01"
