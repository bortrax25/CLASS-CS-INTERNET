"""Lectura de config.yaml."""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


def cargar_config(ruta: Path | str = RAIZ / "config.yaml") -> dict:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def periodo(cfg: dict) -> tuple[str, str | None]:
    """(inicio, fin) para get_prices. En config.yaml `fin` es inclusivo; get_prices lo
    quiere exclusivo (como yfinance), así que se le suma un día. None = hasta hoy."""
    inicio, fin = str(cfg["periodo"]["inicio"]), cfg["periodo"].get("fin")
    if fin is None:
        return inicio, None
    return inicio, (date.fromisoformat(str(fin)) + timedelta(days=1)).isoformat()


def ruta_proyecto(relativa: str) -> Path:
    """Convierte una ruta de config.yaml (relativa a la raíz del proyecto) en absoluta."""
    p = Path(relativa)
    return p if p.is_absolute() else RAIZ / p
