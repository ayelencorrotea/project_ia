"""Registra en SQLite las limitaciones verificadas de los portales sin lector."""

import argparse
from pathlib import Path

from asistente import ofertas

LIMITACIONES = {
    "bancochile": (
        "https://bancodechile.trabajando.cl/",
        "El portal restringe la búsqueda automatizada en sus términos y robots.txt.",
    ),
    "sky": (
        "https://www.skyairline.com/es/chile/skyers/jobsearch",
        "El listado requiere JavaScript y no se verificó un método permitido para importar fichas.",
    ),
    "cajalosandes": (
        "https://cajalosandes.trabajando.cl/",
        "El portal restringe la búsqueda automatizada en sus términos y robots.txt.",
    ),
    "coopeuch": (
        "https://coopeuch.trabajando.cl/",
        "El portal restringe la búsqueda automatizada en sus términos y robots.txt.",
    ),
}


def registrar(bd: Path, fuente: str) -> None:
    url, motivo = LIMITACIONES[fuente]
    ofertas.registrar_fallo(bd, fuente, ofertas.FalloFuente(f"No accesible: {motivo}", url))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("fuentes", nargs="+", choices=sorted(LIMITACIONES))
    args = parser.parse_args(argv)
    for fuente in dict.fromkeys(args.fuentes):
        registrar(args.bd, fuente)
        print(f"{fuente}: {LIMITACIONES[fuente][1]}")


if __name__ == "__main__":
    main()
