"""Guarda contra um erro que já aconteceu: módulo colado duas vezes no mesmo arquivo."""
import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent / "app"
ARQUIVOS = sorted(RAIZ.rglob("*.py"))


@pytest.mark.parametrize("arquivo", ARQUIVOS, ids=lambda p: str(p.relative_to(RAIZ)))
def test_nenhuma_definicao_repetida_no_topo_do_modulo(arquivo):
    vistos = set()
    for no in ast.parse(arquivo.read_text(encoding="utf-8")).body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assert no.name not in vistos, f"{arquivo.name}: '{no.name}' definido duas vezes"
            vistos.add(no.name)
