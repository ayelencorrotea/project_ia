"""Reporte de evaluación: cobertura por fuente, calidad de la extracción contra una revisión manual,
tiempo de preparación de las candidaturas y orden por reglas frente a un Naive Bayes entrenado con las
etiquetas de interés.

Lee los archivos privados de `privado/evaluacion/` (fuera del repositorio) y solo lee la base.
"""

import argparse
import json
import math
import re
import statistics
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timezone
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


TIEMPOS = """
    SELECT c.fuente, d.fecha AS inicio, MIN(e.fecha) AS aprobada
    FROM candidaturas c
    JOIN decisiones d ON d.id = c.decision_id
    JOIN candidatura_eventos e ON e.candidatura_id = c.id AND e.estado_nuevo = 'aprobado'
    GROUP BY c.id
"""


def _momento(texto):
    momento = datetime.fromisoformat(texto)
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)  # CURRENT_TIMESTAMP es UTC


def medir_tiempo(bd):
    """Mediana por fuente desde la decisión de CV que abre la candidatura hasta su primera aprobación."""
    with closing(ofertas.conectar(bd)) as db:
        tablas = {fila[0] for fila in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not {"candidaturas", "candidatura_eventos", "decisiones"} <= tablas:
            return []
        filas = db.execute(TIEMPOS).fetchall()
    por_fuente: dict[str, list[float]] = {}
    for fuente, inicio, aprobada in filas:
        minutos = (_momento(aprobada) - _momento(inicio)).total_seconds() / 60
        por_fuente.setdefault(fuente, []).append(minutos)
    return [{"fuente": fuente, "candidaturas": len(minutos),
             "mediana_minutos": round(statistics.median(minutos))}
            for fuente, minutos in sorted(por_fuente.items())]


MINIMO_ETIQUETAS = 60
MINIMO_POR_CLASE = 15
RESERVA = 0.25
TOP = 5


def palabras(oferta):
    return re.findall(r"\w+", reglas.normalizar(f"{oferta['cargo']} {oferta['descripcion'] or ''}"))


def puntaje_reglas(oferta, perfil):
    """Señales del perfil que calzan con los requisitos, con el peso de `app.recommend`."""
    try:
        filas = reglas.extraer(f"{oferta['cargo']}\n{oferta['descripcion'] or ''}", perfil)
    except ValueError:
        return 0
    return sum(2 if fila["tipo"] == "obligatorio" else 1 for fila in filas if fila["evidencia"])


def entrenar_bayes(entrenamiento):
    """Naive Bayes multinomial con suavizado de Laplace; devuelve una función de puntaje (log-razón)."""
    conteos: dict[bool, Counter[str]] = {True: Counter(), False: Counter()}
    documentos = Counter(interesa for _, interesa in entrenamiento)
    for oferta, interesa in entrenamiento:
        conteos[interesa].update(palabras(oferta))
    vocabulario = set(conteos[True]) | set(conteos[False])
    totales = {clase: sum(conteos[clase].values()) + len(vocabulario) for clase in conteos}

    def log_prob(oferta, clase):
        previa = math.log(documentos[clase] / len(entrenamiento))
        return previa + sum(math.log((conteos[clase][p] + 1) / totales[clase])
                            for p in palabras(oferta) if p in vocabulario)

    return lambda oferta: log_prob(oferta, True) - log_prob(oferta, False)


def precision_top(reservada, puntaje):
    orden = sorted(reservada, key=lambda par: -puntaje(par[0]))  # estable: empates por fecha de detección
    interesa = sum(1 for _, si in orden[:TOP] if si)
    return {"precision_5": round(interesa / TOP, 2), "interesa_top5": interesa}


def medir_ranking(bd, etiquetas, perfil):
    etiquetadas, sin_oferta = [], 0
    for etiqueta in etiquetas:
        oferta = ofertas.leer_oferta(bd, etiqueta["fuente"], etiqueta["id_origen"])
        if oferta is None:
            sin_oferta += 1
            continue
        etiquetadas.append((oferta, reglas.normalizar(str(etiqueta["interes"])) == "si"))
    interesa = sum(1 for _, si in etiquetadas if si)
    faltan = {
        "faltan": max(0, MINIMO_ETIQUETAS - len(etiquetadas)),
        "faltan_interesa": max(0, MINIMO_POR_CLASE - interesa),
        "faltan_no_interesa": max(0, MINIMO_POR_CLASE - (len(etiquetadas) - interesa)),
    }
    if any(faltan.values()):
        return {"suficiente": False, "etiquetas": len(etiquetadas), "sin_oferta": sin_oferta, **faltan}
    etiquetadas.sort(key=lambda par: (par[0]["fecha_deteccion"], par[0]["fuente"], par[0]["id_origen"]))
    corte = len(etiquetadas) - math.ceil(len(etiquetadas) * RESERVA)
    entrenamiento, reservada = etiquetadas[:corte], etiquetadas[corte:]
    modelo = entrenar_bayes(entrenamiento)
    return {
        "suficiente": True, "etiquetas": len(etiquetadas), "sin_oferta": sin_oferta,
        "entrenamiento": len(entrenamiento),
        "reservada": [f"{oferta['fuente']}:{oferta['id_origen']}" for oferta, _ in reservada],
        "reglas": precision_top(reservada, lambda oferta: puntaje_reglas(oferta, perfil)),
        "modelo": precision_top(reservada, modelo),
    }


def evaluar(bd, carpeta, perfil):
    revisiones = leer_jsonl(carpeta / "revision.jsonl")
    etiquetas = leer_jsonl(carpeta / "interes.jsonl")
    return {
        "cobertura": medir_cobertura(bd),
        "extraccion": None if revisiones is None else medir_extraccion(bd, revisiones, perfil),
        "tiempo": medir_tiempo(bd),
        "ranking": None if etiquetas is None else medir_ranking(bd, etiquetas, perfil),
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
    lineas += ["", "## Tiempo de preparación (decisión de CV → aprobación)"]
    if not reporte["tiempo"]:
        lineas.append("Sin candidaturas aprobadas.")
    for fila in reporte["tiempo"]:
        lineas.append(f"- {fila['fuente']} · {fila['candidaturas']} candidaturas aprobadas · "
                      f"mediana {fila['mediana_minutos']} min")
    lineas += ["", "## Ranking: reglas frente a modelo aprendido"]
    ranking = reporte["ranking"]
    if ranking is None:
        lineas.append("Sin interes.jsonl: no hay ofertas etiquetadas.")
    elif not ranking["suficiente"]:
        lineas.append(f"Datos insuficientes: {ranking['etiquetas']} etiquetas con oferta en la base "
                      f"({ranking['sin_oferta']} sin oferta); faltan {ranking['faltan']} etiquetas, "
                      f"{ranking['faltan_interesa']} «me interesa» y {ranking['faltan_no_interesa']} "
                      "«no me interesa». No se entrenó nada.")
    else:
        lineas.append(f"{ranking['entrenamiento']} para entrenar · {len(ranking['reservada'])} reservadas "
                      f"(las más recientes) · {ranking['sin_oferta']} sin oferta")
        for metodo, nombre in (("reglas", "Reglas"), ("modelo", "Naive Bayes")):
            fila = ranking[metodo]
            lineas.append(f"- {nombre} · precisión@5 {fila['precision_5']:g} · "
                          f"{fila['interesa_top5']} «me interesa» en el top 5")
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
