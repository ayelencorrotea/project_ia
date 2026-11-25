"""Revisa los recorridos de portales: secciones completas, observado o supuesto, sin datos personales."""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = Path(__file__).parent / "fixtures" / "portales" / "ejemplo.md"
DOCUMENTOS = sorted((RAIZ / "docs" / "portales").glob("*.md")) + [EJEMPLO]
SECCIONES = (
    "URL y fecha", "robots.txt y términos", "Inicio de sesión", "Pasos", "Campos obligatorios", "Documentos",
    "Vista previa", "Confirmación", "Duplicados y reintentos", "Bloqueos o CAPTCHA observados",
    "Propuesta de receta",
)
MARCA = re.compile(r"Observado \(\d{4}-\d{2}-\d{2}\)|Supuesto")
DATOS_PERSONALES = {
    "RUT": re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b"),
    "correo": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "teléfono": re.compile(r"(?:\+?56[\s-]?)?\b9[\s-]?\d{4}[\s-]?\d{4}\b"),
}


def secciones(texto):
    partes = re.split(r"^## +(.+?)\s*$", texto, flags=re.MULTILINE)
    return dict(zip(partes[1::2], partes[2::2], strict=True))


def problemas_de_secciones(texto):
    encontradas = secciones(texto)
    faltan = [f"falta la sección «{s}»" for s in SECCIONES if s not in encontradas]
    sin_marca = [f"«{s}» no dice «Observado (fecha)» ni «Supuesto»"
                 for s in SECCIONES if s in encontradas and not MARCA.search(encontradas[s])]
    return faltan + sin_marca


def datos_personales(texto):
    return [nombre for nombre, patron in DATOS_PERSONALES.items() if patron.search(texto)]


@pytest.mark.parametrize("documento", DOCUMENTOS, ids=lambda d: d.name)
def test_secciones_completas_y_marcadas(documento):
    assert problemas_de_secciones(documento.read_text(encoding="utf-8")) == []


def test_secciones_detecta_faltante_y_sin_marca():
    texto = EJEMPLO.read_text(encoding="utf-8")
    texto = texto.replace("## Vista previa\n", "## Otra cosa\n")
    texto = texto.replace("Observado (2026-11-25): ninguno.", "Ninguno.")
    assert problemas_de_secciones(texto) == [
        "falta la sección «Vista previa»",
        "«Bloqueos o CAPTCHA observados» no dice «Observado (fecha)» ni «Supuesto»",
    ]


@pytest.mark.parametrize("documento", DOCUMENTOS, ids=lambda d: d.name)
def test_sin_datos_personales(documento):
    assert datos_personales(documento.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(("dato", "tipo"), [
    ("RUT 12.345.678-9", "RUT"), ("RUT 9876543-k", "RUT"), ("correo persona@example.org", "correo"),
    ("teléfono +56 9 1234 5678", "teléfono"), ("teléfono 912345678", "teléfono"),
])
def test_datos_personales_hacen_fallar(dato, tipo):
    texto = EJEMPLO.read_text(encoding="utf-8").replace("ninguno.", f"ninguno. {dato}")
    assert datos_personales(texto) == [tipo]
