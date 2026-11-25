"""Candidaturas locales, huella de revisión e historial de estados."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from asistente import ofertas

TRANSICIONES = {
    "borrador": {"listo"},
    "listo": {"aprobado", "listo"},
    "aprobado": {"enviado", "por_verificar", "listo"},
    "por_verificar": {"enviado", "aprobado"},
    "enviado": set(),
}

ESQUEMA = """
    CREATE TABLE IF NOT EXISTS candidaturas (
        id INTEGER PRIMARY KEY,
        fuente TEXT NOT NULL,
        id_origen TEXT NOT NULL,
        decision_id INTEGER NOT NULL REFERENCES decisiones(id),
        destino TEXT NOT NULL,
        cargo TEXT NOT NULL,
        cv_version TEXT NOT NULL,
        archivo TEXT NOT NULL,
        pdf_sha256 TEXT NOT NULL,
        respuestas TEXT NOT NULL,
        estado TEXT NOT NULL CHECK (estado IN ('borrador','listo','aprobado','enviado','por_verificar')),
        huella TEXT NOT NULL,
        aprobada_en TEXT,
        enviada_en TEXT,
        comprobante TEXT,
        FOREIGN KEY (fuente, id_origen) REFERENCES ofertas (fuente, id_origen)
    );
    CREATE UNIQUE INDEX IF NOT EXISTS candidatura_activa_por_oferta
        ON candidaturas(fuente, id_origen) WHERE estado <> 'enviado';
    CREATE TABLE IF NOT EXISTS candidatura_eventos (
        id INTEGER PRIMARY KEY,
        candidatura_id INTEGER NOT NULL REFERENCES candidaturas(id),
        estado_anterior TEXT NOT NULL,
        estado_nuevo TEXT NOT NULL,
        fecha TEXT NOT NULL,
        huella TEXT NOT NULL,
        motivo TEXT NOT NULL
    );
"""


def _conectar(database: str | Path) -> sqlite3.Connection:
    db = ofertas.conectar(database)
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(ESQUEMA)
        db.row_factory = sqlite3.Row
    except sqlite3.Error:
        db.close()
        raise
    return db


def _json_canonico(valor: dict) -> str:
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def huella(destino: str, cargo: str, pdf_sha256: str, respuestas: dict[str, str]) -> str:
    contenido = _json_canonico({
        "destino": destino, "cargo": cargo, "pdf_sha256": pdf_sha256, "respuestas": respuestas,
    })
    return hashlib.sha256(contenido.encode("utf-8")).hexdigest()


def _sha256_pdf(archivo: Path) -> str:
    try:
        return hashlib.sha256(archivo.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError("No se pudo leer el PDF de la candidatura.") from error


def _decision(db: sqlite3.Connection, decision_id: int, pdf: Path, pdf_sha256: str) -> sqlite3.Row:
    existe_tabla = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'decisiones'"
    ).fetchone()
    decision = db.execute(
        "SELECT cv_elegido, archivo, sha256 FROM decisiones WHERE id = ?", (decision_id,),
    ).fetchone() if existe_tabla else None
    if decision is None:
        raise ValueError("No existe la decisión de CV indicada.")
    if (pdf.name, pdf_sha256) != (decision["archivo"], decision["sha256"]):
        raise ValueError("El PDF no coincide con el registrado en la decisión de CV.")
    return decision


def crear(
    database: str | Path,
    fuente: str,
    id_origen: str,
    decision_id: int,
    archivo: str | Path,
    respuestas: dict[str, str] | None = None,
) -> int:
    """Crea un borrador a partir de una oferta y la decisión que registró el PDF."""
    pdf = Path(archivo).resolve()
    pdf_sha256 = _sha256_pdf(pdf)
    respuestas = {} if respuestas is None else respuestas
    with closing(_conectar(database)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        oferta = db.execute(
            "SELECT cargo, enlace FROM ofertas WHERE fuente = ? AND id_origen = ?",
            (fuente, id_origen),
        ).fetchone()
        if oferta is None:
            raise ValueError("No existe la oferta indicada.")
        decision = _decision(db, decision_id, pdf, pdf_sha256)
        destino, cargo = oferta["enlace"], oferta["cargo"]
        resultado = db.execute("""
            INSERT INTO candidaturas (
                fuente, id_origen, decision_id, destino, cargo, cv_version,
                archivo, pdf_sha256, respuestas, estado, huella
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'borrador', ?)
            ON CONFLICT(fuente, id_origen) WHERE estado <> 'enviado' DO NOTHING
        """, (
            fuente, id_origen, decision_id, destino, cargo, decision["cv_elegido"], str(pdf),
            pdf_sha256, _json_canonico(respuestas), huella(destino, cargo, pdf_sha256, respuestas),
        ))
        if resultado.rowcount != 1 or resultado.lastrowid is None:
            raise ValueError("Ya existe una candidatura activa para esta oferta.")
        return resultado.lastrowid


def _fila(db: sqlite3.Connection, candidatura_id: int) -> sqlite3.Row:
    fila = db.execute("SELECT * FROM candidaturas WHERE id = ?", (candidatura_id,)).fetchone()
    if fila is None:
        raise ValueError("No existe la candidatura indicada.")
    return fila


def _pendientes(respuestas: dict[str, str]) -> list[str]:
    return sorted(
        campo for campo, respuesta in respuestas.items()
        if not respuesta.strip() or "{pendiente}" in respuesta.casefold()
    )


def leer(database: str | Path, candidatura_id: int) -> dict:
    with closing(_conectar(database)) as db:
        candidatura = dict(_fila(db, candidatura_id))
    candidatura["respuestas"] = json.loads(candidatura["respuestas"])
    candidatura["pendientes"] = _pendientes(candidatura["respuestas"])
    return candidatura


def _registrar_transicion(
    db: sqlite3.Connection,
    fila: sqlite3.Row,
    nuevo_estado: str,
    *,
    motivo: str,
    comprobante: str | None = None,
) -> None:
    anterior = fila["estado"]
    if nuevo_estado not in TRANSICIONES[anterior]:
        raise ValueError(f"Transición no permitida: {anterior} → {nuevo_estado}.")
    fecha = ofertas.ahora()
    aprobada_en = fila["aprobada_en"]
    if nuevo_estado == "listo":
        aprobada_en = None
    elif anterior == "listo":
        aprobada_en = fecha
    enviada_en = fecha if nuevo_estado == "enviado" else None
    db.execute("""
        UPDATE candidaturas SET estado = ?, aprobada_en = ?, enviada_en = ?, comprobante = ?
        WHERE id = ?
    """, (nuevo_estado, aprobada_en, enviada_en, comprobante if enviada_en else None, fila["id"]))
    db.execute("""
        INSERT INTO candidatura_eventos (
            candidatura_id, estado_anterior, estado_nuevo, fecha, huella, motivo
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (fila["id"], anterior, nuevo_estado, fecha, fila["huella"], motivo))


def actualizar_contenido(
    database: str | Path,
    candidatura_id: int,
    *,
    destino: str | None = None,
    cargo: str | None = None,
    archivo: str | Path | None = None,
    respuestas: dict[str, str] | None = None,
    decision_id: int | None = None,
) -> None:
    """Guarda el contenido y, si cambia su huella, vuelve a revisión."""
    with closing(_conectar(database)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        _actualizar_contenido(db, candidatura_id, destino, cargo, archivo, respuestas, decision_id)


def _actualizar_contenido(
    db: sqlite3.Connection,
    candidatura_id: int,
    destino: str | None = None,
    cargo: str | None = None,
    archivo: str | Path | None = None,
    respuestas: dict[str, str] | None = None,
    decision_id: int | None = None,
) -> None:
    fila = _fila(db, candidatura_id)
    if fila["estado"] in {"enviado", "por_verificar"}:
        raise ValueError(f"No se puede editar una candidatura en estado {fila['estado']}.")
    pdf = Path(fila["archivo"]) if archivo is None else Path(archivo).resolve()
    pdf_sha256 = _sha256_pdf(pdf)
    cv_version = fila["cv_version"]
    if decision_id is not None:
        cv_version = _decision(db, decision_id, pdf, pdf_sha256)["cv_elegido"]
    else:
        decision_id = fila["decision_id"]
        if str(pdf) != fila["archivo"]:
            raise ValueError("Indica la decisión de CV para el nuevo archivo.")
    destino = fila["destino"] if destino is None else destino
    cargo = fila["cargo"] if cargo is None else cargo
    respuestas_actuales = json.loads(fila["respuestas"]) if respuestas is None else respuestas
    nueva_huella = huella(destino, cargo, pdf_sha256, respuestas_actuales)
    db.execute("""
        UPDATE candidaturas
        SET destino = ?, cargo = ?, archivo = ?, pdf_sha256 = ?, respuestas = ?, huella = ?,
            decision_id = ?, cv_version = ?
        WHERE id = ?
    """, (
        destino, cargo, str(pdf), pdf_sha256, _json_canonico(respuestas_actuales), nueva_huella,
        decision_id, cv_version, candidatura_id,
    ))
    cambio = nueva_huella != fila["huella"] or cv_version != fila["cv_version"]
    if cambio and fila["estado"] in {"listo", "aprobado"}:
        _registrar_transicion(
            db, _fila(db, candidatura_id), "listo", motivo="Cambio de contenido",
        )


def elegir_cv(
    database: str | Path, candidatura_id: int, version: str, archivo: Path, huella_vista: str,
) -> None:
    """Registra la elección y modifica la candidatura en la misma transacción."""
    pdf = archivo.read_bytes()
    if not pdf.startswith(b"%PDF-"):
        raise ValueError("La versión no apunta a un PDF válido.")
    sha256 = hashlib.sha256(pdf).hexdigest()
    with closing(_conectar(database)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        fila = _fila(db, candidatura_id)
        if fila["huella"] != huella_vista:
            raise ValueError("El contenido cambió, revisa de nuevo.")
        if fila["estado"] not in {"listo", "aprobado"}:
            raise ValueError("La candidatura debe estar lista o aprobada para cambiar su CV.")
        if (version, str(archivo), sha256) == (fila["cv_version"], fila["archivo"], fila["pdf_sha256"]):
            return
        nueva = db.execute("""
            INSERT INTO decisiones
                (modo, oferta, requisitos, cv_recomendado, cv_elegido, archivo, sha256, motivo)
            SELECT modo, oferta, requisitos, cv_recomendado, ?, ?, ?, ?
            FROM decisiones WHERE id = ?
        """, (version, archivo.name, sha256, "Elección desde la vista", fila["decision_id"]))
        if nueva.rowcount != 1 or nueva.lastrowid is None:
            raise ValueError("No existe la decisión de CV anterior.")
        _actualizar_contenido(db, candidatura_id, archivo=archivo, decision_id=nueva.lastrowid)


def cambiar_estado(
    database: str | Path,
    candidatura_id: int,
    nuevo_estado: str,
    *,
    huella_vista: str | None = None,
    motivo: str | None = None,
    comprobante: str | None = None,
) -> None:
    """Valida la transición y guarda el nuevo estado y el evento juntos."""
    with closing(_conectar(database)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        fila = _fila(db, candidatura_id)
        anterior = fila["estado"]
        if nuevo_estado not in TRANSICIONES[anterior]:
            raise ValueError(f"Transición no permitida: {anterior} → {nuevo_estado}.")
        if nuevo_estado == "listo" and anterior != "borrador":
            raise ValueError("Transición a listo reservada para cambios de contenido.")
        if anterior == "listo" and huella_vista != fila["huella"]:
            raise ValueError("La huella de aprobación no coincide con la candidatura.")
        if nuevo_estado == "listo" or anterior == "listo":
            pendientes = _pendientes(json.loads(fila["respuestas"]))
            if pendientes:
                raise ValueError(f"Respuestas pendientes: {', '.join(pendientes)}.")
        if anterior in {"listo", "aprobado"}:
            if _sha256_pdf(Path(fila["archivo"])) != fila["pdf_sha256"]:
                raise ValueError("El PDF cambió desde que se guardó la candidatura.")
        _registrar_transicion(
            db, fila, nuevo_estado, motivo=motivo or nuevo_estado, comprobante=comprobante,
        )


def aprobar(database: str | Path, candidatura_id: int, huella_vista: str) -> None:
    cambiar_estado(database, candidatura_id, "aprobado", huella_vista=huella_vista, motivo="Aprobación")


def marcar_envio(
    database: str | Path,
    candidatura_id: int,
    resultado: str,
    *,
    comprobante: str | None = None,
) -> None:
    """Registra un resultado observado. En por_verificar solo se resuelve el intento previo."""
    estados = {"enviado": "enviado", "incierto": "por_verificar", "no_enviado": "aprobado"}
    if resultado not in estados:
        raise ValueError(f"Resultado de envío desconocido: {resultado}.")
    cambiar_estado(
        database, candidatura_id, estados[resultado],
        motivo=f"Resultado de envío: {resultado}", comprobante=comprobante,
    )


def historial(database: str | Path, candidatura_id: int) -> list[dict]:
    with closing(_conectar(database)) as db:
        _fila(db, candidatura_id)
        eventos = db.execute("""
            SELECT estado_anterior, estado_nuevo, fecha, huella, motivo
            FROM candidatura_eventos WHERE candidatura_id = ? ORDER BY id
        """, (candidatura_id,))
        return [dict(evento) for evento in eventos]


def _leer_respuestas(archivo: Path) -> dict[str, str]:
    respuestas = json.loads(archivo.read_text(encoding="utf-8"))
    if not isinstance(respuestas, dict) or any(not isinstance(valor, str) for valor in respuestas.values()):
        raise ValueError("Las respuestas deben ser un objeto JSON con valores de texto.")
    return respuestas


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara y revisa candidaturas guardadas en SQLite.")
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    comandos = parser.add_subparsers(dest="comando", required=True)
    nuevo = comandos.add_parser("crear", help="Crea un borrador con una oferta y un CV registrados.")
    nuevo.add_argument("oferta", metavar="FUENTE:ID")
    nuevo.add_argument("decision", type=int)
    nuevo.add_argument("pdf", type=Path)

    for comando, ayuda in (
        ("responder", "Reemplaza las respuestas con las de un archivo JSON."),
        ("listo", "Marca el borrador como listo para revisar."),
        ("mostrar", "Muestra el contenido, las respuestas pendientes y la huella."),
        ("aprobar", "Aprueba la huella que revisaste."),
        ("enviado", "Registra la confirmación de un envío previo."),
        ("incierto", "Registra un envío sin confirmación."),
        ("no-enviado", "Confirma que el envío incierto no se realizó."),
        ("historial", "Muestra los cambios de estado en orden."),
    ):
        subcomando = comandos.add_parser(comando, help=ayuda)
        subcomando.add_argument("id", type=int)
        if comando == "responder":
            subcomando.add_argument("respuestas", type=Path, metavar="RESPUESTAS_JSON")
        elif comando == "aprobar":
            subcomando.add_argument("huella")
        elif comando == "enviado":
            subcomando.add_argument("--comprobante")

    args = parser.parse_args()
    try:
        if args.comando == "crear":
            fuente, _, id_origen = args.oferta.partition(":")
            if not fuente or not id_origen:
                raise ValueError("Indica la oferta como FUENTE:ID.")
            print(crear(args.bd, fuente, id_origen, args.decision, args.pdf))
        elif args.comando == "responder":
            actualizar_contenido(args.bd, args.id, respuestas=_leer_respuestas(args.respuestas))
        elif args.comando == "listo":
            cambiar_estado(args.bd, args.id, "listo")
        elif args.comando == "mostrar":
            print(json.dumps(leer(args.bd, args.id), ensure_ascii=False, indent=2))
        elif args.comando == "aprobar":
            aprobar(args.bd, args.id, args.huella)
        elif args.comando == "historial":
            print(json.dumps(historial(args.bd, args.id), ensure_ascii=False, indent=2))
        else:
            marcar_envio(
                args.bd, args.id, args.comando.replace("-", "_"),
                comprobante=getattr(args, "comprobante", None),
            )
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
