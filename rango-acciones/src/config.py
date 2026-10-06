"""Lectura de config.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent


def cargar_config(ruta: Path | str = RAIZ / "config.yaml") -> dict:
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ruta_proyecto(relativa: str) -> Path:
    """Convierte una ruta de config.yaml (relativa a la raíz del proyecto) en absoluta."""
    p = Path(relativa)
    return p if p.is_absolute() else RAIZ / p
