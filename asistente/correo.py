"""Seguimiento por correo, solo lectura: clasifica correos exportados (.eml, .mbox) y guarda datos mínimos.

Nunca se conecta a un servidor de correo. De cada correo relacionado con una candidatura guarda solo
fecha, remitente, asunto, clase, la frase que justificó la clase y la huella del mensaje; nunca el cuerpo
ni adjuntos.
"""

import argparse
import hashlib
import json
import mailbox
import re
import sqlite3
from contextlib import closing
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

from asistente import candidaturas, ofertas, reglas

ESQUEMA = """
    CREATE TABLE IF NOT EXISTS correo_eventos (
        id INTEGER PRIMARY KEY,
        huella TEXT NOT NULL UNIQUE,
        candidatura_id INTEGER REFERENCES candidaturas(id),
        candidatas TEXT,
        clase TEXT NOT NULL CHECK (clase IN ('confirmacion','entrevista','rechazo','otro')),
        cita TEXT,
        fecha TEXT,
        remitente TEXT,
        asunto TEXT,
        estado TEXT NOT NULL CHECK (estado IN ('asociado','por_revisar','confirmado'))
    );
"""
# El rechazo va primero: suele empezar agradeciendo la postulación.
FRASES = {
    "rechazo": ("no continuaras en el proceso", "no seguiras en el proceso",
                "no continuaremos con tu postulacion", "continuar con otros candidatos",
                "continuar con otros postulantes", "no fuiste seleccionad", "no has sido seleccionad"),
    "entrevista": ("entrevista", "agendar una reunion", "agendar una llamada"),
    "confirmacion": ("hemos recibido tu postulacion", "recibimos tu postulacion",
                     "tu postulacion fue recibida", "postulacion recibida", "gracias por postular"),
}
DOMINIOS = {
    "bci": ("bci.cl",), "itau": ("itau.cl",), "bancochile": ("bancochile.cl",), "latam": ("latam.com",),
    "sky": ("skyairline.com",), "cajalosandes": ("cajalosandes.cl",), "coopeuch": ("coopeuch.cl",),
}
BLOQUES = {"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "table"}


class _Texto(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes: list[str] = []
        self._omitir = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._omitir += 1
        elif tag in BLOQUES:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._omitir = max(0, self._omitir - 1)
        elif tag in BLOQUES:
            self.partes.append("\n")

    def handle_data(self, data):
        if not self._omitir:
            self.partes.append(data)


def html_a_texto(html):
    parser = _Texto()
    parser.feed(html)
    return "".join(parser.partes)


def frases(texto):
    for linea in texto.splitlines():
        for frase in re.split(r"(?<=[.!?])\s+", linea.strip()):
            if frase:
                yield " ".join(frase.split())


def clasificar(asunto, cuerpo):
    """Devuelve (clase, cita literal). La primera frase que calza con una regla es la cita."""
    candidatas = [asunto, *frases(cuerpo)]
    for clase, claves in FRASES.items():
        for frase in candidatas:
            plana = reglas.normalizar(frase)
            if any(clave in plana for clave in claves):
                return clase, frase
    return "otro", None


def _cuerpo(mensaje):
    try:
        parte = mensaje.get_body(preferencelist=("plain", "html"))
        if parte is None:
            return ""
        contenido = parte.get_content()
    except (LookupError, UnicodeError, KeyError, AttributeError):
        return ""
    return html_a_texto(contenido) if parte.get_content_subtype() == "html" else contenido


def _fecha(mensaje):
    try:
        return parsedate_to_datetime(str(mensaje["date"])).isoformat()
    except (TypeError, ValueError):
        return None


def mensajes(ruta):
    """Entrega (huella, bytes) de cada mensaje de un .eml, un .mbox o una carpeta con ellos."""
    ruta = Path(ruta)
    if ruta.is_dir():
        for archivo in sorted(ruta.rglob("*")):
            if archivo.suffix.lower() in {".eml", ".mbox"}:
                yield from mensajes(archivo)
        return
    if ruta.suffix.lower() == ".eml":
        datos = ruta.read_bytes()
        yield hashlib.sha256(datos).hexdigest(), datos
    elif ruta.suffix.lower() == ".mbox":
        caja = mailbox.mbox(ruta, create=False)
        try:
            for clave in caja.keys():
                datos = caja.get_bytes(clave)
                yield hashlib.sha256(datos).hexdigest(), datos
        finally:
            caja.close()
    else:
        raise ValueError(f"Solo se leen archivos .eml o .mbox: {ruta.name}")


def _conectar(bd):
    db = ofertas.conectar(bd)
    db.executescript(candidaturas.ESQUEMA + ESQUEMA)
    db.row_factory = sqlite3.Row
    return db


def relacionadas(db, remitente, texto):
    """Candidaturas cuya empresa calza por dominio del remitente o por nombre en el texto."""
    dominio = remitente.rpartition("@")[2].lower()
    plano = reglas.normalizar(texto)
    filas = []
    for fila in db.execute("""
        SELECT c.id, c.fuente, c.id_origen, c.cargo, o.empresa FROM candidaturas c
        JOIN ofertas o ON o.fuente = c.fuente AND o.id_origen = c.id_origen ORDER BY c.id
    """):
        por_dominio = any(dominio == d or dominio.endswith("." + d) for d in DOMINIOS.get(fila["fuente"], ()))
        if por_dominio or _contiene(plano, fila["empresa"]):
            filas.append(fila)
    return filas


def _contiene(plano, valor):
    valor = reglas.normalizar(str(valor or "")).strip()
    return bool(valor) and re.search(rf"\b{re.escape(valor)}\b", plano) is not None


def asociar(filas, texto):
    """Asocia solo si una única candidatura de la empresa calza además por cargo o ID de origen."""
    plano = reglas.normalizar(texto)
    calzan = [f["id"] for f in filas if _contiene(plano, f["cargo"]) or _contiene(plano, f["id_origen"])]
    if len(calzan) == 1:
        return calzan[0], calzan
    return None, calzan or [f["id"] for f in filas]


def _reenvio(asunto, cuerpo):
    """En un reenvío, remitente y fecha originales desde el cuerpo; None si no es reenvío."""
    if not re.match(r"\s*(rv|fw|fwd|reenviado)\s*:", asunto, re.IGNORECASE):
        return None
    remitente = fecha = None
    for linea in cuerpo.splitlines():
        clave, _, valor = linea.partition(":")
        clave = reglas.normalizar(clave.strip())
        if remitente is None and clave in {"de", "from"} and "@" in valor:
            remitente = parseaddr(valor.strip())[1].lower()
        elif fecha is None and clave in {"fecha", "date", "enviado", "sent"}:
            try:
                fecha = parsedate_to_datetime(valor.strip()).isoformat()
            except (TypeError, ValueError):
                pass
    return remitente, fecha


def importar(bd, ruta):
    """Importa correos exportados. Solo guarda los relacionados con una candidatura, sin cambiar estados."""
    resumen = {"importados": 0, "repetidos": 0, "ignorados": 0}
    with closing(_conectar(bd)) as db, db:
        for huella, datos in mensajes(ruta):
            if db.execute("SELECT 1 FROM correo_eventos WHERE huella = ?", (huella,)).fetchone():
                resumen["repetidos"] += 1
                continue
            mensaje = BytesParser(policy=policy.default).parsebytes(datos)
            asunto = " ".join(str(mensaje["subject"] or "").split())
            remitente = parseaddr(str(mensaje["from"] or ""))[1].lower()
            fecha = _fecha(mensaje)
            cuerpo = _cuerpo(mensaje)
            original = _reenvio(asunto, cuerpo)
            if original:
                remitente, fecha = original[0] or remitente, original[1] or fecha
            texto = f"{asunto}\n{cuerpo}"
            filas = relacionadas(db, remitente, texto)
            if not filas:
                resumen["ignorados"] += 1
                continue
            clase, cita = clasificar(asunto, cuerpo)
            candidatura, candidatas = asociar(filas, texto)
            if original is not None and None in original:
                candidatura = None  # reenvío sin remitente o fecha originales: lo revisa la persona
            db.execute("""
                INSERT INTO correo_eventos (huella, candidatura_id, candidatas, clase, cita, fecha, remitente,
                                            asunto, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (huella, candidatura, json.dumps(candidatas), clase, cita, fecha, remitente, asunto,
                  "asociado" if candidatura else "por_revisar"))
            resumen["importados"] += 1
    return resumen


def pendientes(bd):
    with closing(_conectar(bd)) as db:
        filas = db.execute("SELECT * FROM correo_eventos WHERE estado <> 'confirmado' ORDER BY id").fetchall()
    return [dict(fila) for fila in filas]


def pendientes_texto(bd):
    lineas = []
    for evento in pendientes(bd):
        lineas.append(f"Evento {evento['id']} · {evento['clase']} · {evento['fecha'] or 'sin fecha'} · "
                      f"{evento['remitente']} · «{evento['cita'] or evento['asunto']}»")
        if evento["candidatura_id"]:
            accion = "marcar como enviada" if evento["clase"] == "confirmacion" else "registrar el correo"
            lineas.append(f"  Candidatura {evento['candidatura_id']}: propuesta {accion} → "
                          f"python -m asistente.correo confirmar {evento['id']}")
        else:
            ids = ", ".join(map(str, json.loads(evento["candidatas"])))
            lineas.append(f"  Por revisar; candidatas {ids} → "
                          f"python -m asistente.correo confirmar {evento['id']} --candidatura <id>")
    return "\n".join(lineas) if lineas else "Sin correos por revisar."


def confirmar(bd, evento_id, candidatura=None):
    """Aplica lo que propone un correo, solo por orden de la persona. Una confirmación marca el envío."""
    with closing(_conectar(bd)) as db:
        evento = db.execute("SELECT * FROM correo_eventos WHERE id = ?", (evento_id,)).fetchone()
    if evento is None:
        raise ValueError("No existe el evento de correo indicado.")
    if evento["estado"] == "confirmado":
        raise ValueError("El evento ya fue confirmado.")
    elegida = candidatura or evento["candidatura_id"]
    if elegida is None:
        raise ValueError("El correo está por revisar: indica la candidatura con --candidatura <id>.")
    if elegida not in json.loads(evento["candidatas"]):
        raise ValueError(f"La candidatura {elegida} no es candidata para este correo.")
    if evento["clase"] == "confirmacion" and candidaturas.leer(bd, elegida)["estado"] != "enviado":
        comprobante = (f"correo {evento['huella']} · {evento['fecha']} · {evento['remitente']} · "
                       f"«{evento['cita']}»")
        candidaturas.marcar_envio(bd, elegida, "enviado", comprobante=comprobante)
    with closing(_conectar(bd)) as db, db:
        db.execute("UPDATE correo_eventos SET candidatura_id = ?, estado = 'confirmado' WHERE id = ?",
                   (elegida, evento_id))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Lee correos exportados (.eml, .mbox); nunca se conecta.")
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    sub = parser.add_subparsers(dest="comando", required=True)
    importar_cmd = sub.add_parser("importar", help="Importa un archivo .eml, .mbox o una carpeta.")
    importar_cmd.add_argument("ruta", type=Path)
    sub.add_parser("pendientes", help="Muestra los correos sin confirmar y lo que proponen.")
    confirmar_cmd = sub.add_parser("confirmar", help="Aplica lo que propone un correo.")
    confirmar_cmd.add_argument("evento", type=int)
    confirmar_cmd.add_argument("--candidatura", type=int, help="Candidatura elegida si está por revisar.")
    args = parser.parse_args(argv)
    try:
        if args.comando == "importar":
            resumen = importar(args.bd, args.ruta)
            print(f"Importados: {resumen['importados']} · repetidos: {resumen['repetidos']} · "
                  f"sin candidatura relacionada (no se guardan): {resumen['ignorados']}")
        elif args.comando == "pendientes":
            print(pendientes_texto(args.bd))
        else:
            confirmar(args.bd, args.evento, args.candidatura)
            print(f"Evento {args.evento} confirmado.")
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Error: {error}\n")


if __name__ == "__main__":
    main()
