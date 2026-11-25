"""Reporte de evaluación: cobertura por fuente y calidad de la extracción contra una revisión manual.

Lee los archivos privados de `privado/evaluacion/` (fuera del repositorio) y solo lee la base.
"""

import argparse
import json
from datetime import date
from pathlib import Path

from asistente import cobertura, ofertas, reglas

ARCHIVOS = {
    "revision.jsonl": 'una línea por ficha revisada a mano: {"fuente": "bci", "id_origen": "123", '
                      '"requisitos": [{"cita": "frase literal del aviso", "tipo": "obligatorio"}]}',
    "interes.jsonl": 'una línea por oferta etiquetada: {"fuente": "bci", "id_origen": "123", '
                     '"interes": "sí"}',
}


def normalizar_cita(texto):
    return " ".join(texto.lower().split())


def leer_jsonl(ruta):
    if not ruta.exists():
        return None
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    return [json.loads(linea) for linea in lineas if linea.strip()]


def medir_cobertura(bd):
    return [
        {"fuente": fila["fuente"], "ofertas": fila["ofertas"], "completas": fila["completas"],
         "porcentaje": fila["porcentaje_completas"]}
        for fila in cobertura.reporte(bd) if fila["ofertas"]
    ]


def comparar_ficha(esperados, extraidos):
    """Compara por cita normalizada: omitidos, tipo incorrecto y extraídos que la revisión no respalda."""
    por_cita = {normalizar_cita(fila["cita"]): fila for fila in extraidos}
    citas_esperadas = {normalizar_cita(fila["cita"]) for fila in esperados}
    omitidos, tipo_incorrecto = [], []
    for esperado in esperados:
        extraido = por_cita.get(normalizar_cita(esperado["cita"]))
        if extraido is None:
            omitidos.append(esperado["cita"])
        elif extraido["tipo"] != esperado["tipo"]:
            tipo_incorrecto.append(
                {"cita": esperado["cita"], "esperado": esperado["tipo"], "extraido": extraido["tipo"]})
    sin_evidencia = [fila["cita"] for fila in extraidos
                     if normalizar_cita(fila["cita"]) not in citas_esperadas]
    return {"omitidos": omitidos, "tipo_incorrecto": tipo_incorrecto, "sin_evidencia": sin_evidencia}


def medir_extraccion(bd, revisiones, perfil):
    fichas, sin_oferta = [], 0
    for revision in revisiones:
        oferta = ofertas.leer_oferta(bd, revision["fuente"], revision["id_origen"])
        if oferta is None or oferta["estado"] != ofertas.COMPLETA:
            sin_oferta += 1
            continue
        try:
            extraidos = reglas.extraer(oferta["descripcion"], perfil)
        except ValueError:
            extraidos = []
        fichas.append({"fuente": revision["fuente"], "id_origen": str(revision["id_origen"]),
                       **comparar_ficha(revision["requisitos"], extraidos)})
    totales = {"fichas": len(fichas), "sin_oferta": sin_oferta}
    for clave in ("omitidos", "tipo_incorrecto", "sin_evidencia"):
        totales[clave] = sum(len(ficha[clave]) for ficha in fichas)
    return {"fichas": fichas, "totales": totales}


def evaluar(bd, carpeta, perfil):
    revisiones = leer_jsonl(carpeta / "revision.jsonl")
    return {
        "cobertura": medir_cobertura(bd),
        "extraccion": None if revisiones is None else medir_extraccion(bd, revisiones, perfil),
    }


def formatear(reporte, dia):
    lineas = [f"# Evaluación {dia}", "", "## Cobertura de fichas completas"]
    if not reporte["cobertura"]:
        lineas.append("Sin ofertas en la base.")
    for fila in reporte["cobertura"]:
        lineas.append(f"- {fila['fuente']} · {fila['ofertas']} ofertas · {fila['completas']} completas "
                      f"({fila['porcentaje']:g} %)")
    lineas += ["", "## Extracción contra revisión manual"]
    extraccion = reporte["extraccion"]
    if extraccion is None:
        lineas.append("Sin revision.jsonl: no hay fichas revisadas a mano.")
    else:
        t = extraccion["totales"]
        lineas.append(f"Total: {t['fichas']} fichas · {t['omitidos']} omitidos · "
                      f"{t['tipo_incorrecto']} con tipo incorrecto · {t['sin_evidencia']} sin evidencia · "
                      f"{t['sin_oferta']} sin oferta en la base")
        for ficha in extraccion["fichas"]:
            lineas.append(f"- {ficha['fuente']}:{ficha['id_origen']} · {len(ficha['omitidos'])} omitidos · "
                          f"{len(ficha['tipo_incorrecto'])} con tipo incorrecto · "
                          f"{len(ficha['sin_evidencia'])} sin evidencia")
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evalúa cobertura y extracción con datos privados.")
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--carpeta", type=Path, default=Path("privado/evaluacion"))
    parser.add_argument("--perfil", type=Path, default=Path("privado/perfil.json"),
                        help="Perfil con las señales que usan las reglas; sin él solo cuentan las secciones.")
    parser.add_argument("--fecha", default=date.today().isoformat(), help="Fecha del reporte (AAAA-MM-DD).")
    parser.add_argument("--json", action="store_true", help="Devuelve el reporte en JSON.")
    args = parser.parse_args(argv)
    if not args.carpeta.is_dir():
        print(f"Falta la carpeta {args.carpeta} (queda fuera del repositorio). Crea en ella:")
        for nombre, formato in ARCHIVOS.items():
            print(f"- {nombre}: {formato}")
        return
    perfil = json.loads(args.perfil.read_text(encoding="utf-8")) if args.perfil.exists() else {}
    reporte = evaluar(args.bd, args.carpeta, perfil)
    texto = formatear(reporte, args.fecha)
    (args.carpeta / f"reporte-{args.fecha}.md").write_text(texto, encoding="utf-8")
    print(json.dumps(reporte, ensure_ascii=False, indent=2) if args.json else texto, end="")


if __name__ == "__main__":
    main()
