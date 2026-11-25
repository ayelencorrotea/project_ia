"""Vista local de candidaturas y de los PDF configurados en el perfil."""

import argparse
import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from app import DEMO, read_json, recommend, record
from asistente import candidaturas, ofertas, reglas

PERFIL_DEMO = DEMO / "perfil.json"
ESTILO = """
:root { color-scheme: light dark; --fondo: #f4f6fa; --superficie: #fff; --texto: #182332;
        --borde: #d0d9e4; --accion: #134a91; --aviso: #9b3219; }
@media (prefers-color-scheme: dark) {
  :root { --fondo: #111923; --superficie: #192534; --texto: #edf3fa;
          --borde: #40536a; --accion: #a0c9ff; --aviso: #ffc2a8; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--fondo); color: var(--texto); font: 1rem/1.5 system-ui, sans-serif; }
main { max-width: 48rem; margin: auto; padding: 1.25rem clamp(1rem, 4vw, 2rem) 3rem;
       overflow-wrap: anywhere; }
section { background: var(--superficie); border: 1px solid var(--borde); padding: 1rem;
          border-radius: .75rem; margin-block: 1rem; }
h1, h2 { line-height: 1.2; margin-top: 0; }
h2 { font-size: 1.2rem; }
a { color: var(--accion); }
[role=alert] { border-inline-start: .25rem solid var(--aviso); padding: .5rem; color: var(--aviso); }
embed { display: block; border: 1px solid var(--borde); width: 100%; height: min(62vh, 34rem); }
button, select { font: inherit; min-height: 2.75rem; max-width: 100%; margin-block: .25rem; }
button { padding: .45rem .8rem; }
button:enabled { cursor: pointer; }
"""


def _texto(valor: object) -> str:
    return escape(str(valor))


class ServidorRevision(ThreadingHTTPServer):
    def __init__(self, bd: Path, puerto: int, perfil: Path) -> None:
        datos = json.loads(perfil.read_text(encoding="utf-8"))
        self.pdfs = {
            version: (perfil.parent / datos_version["pdf"]).resolve()
            for version, datos_version in datos["versiones"].items()
        }
        self.evidencias: dict[str, str] = datos["evidencias"]
        self.bd = bd
        self.token = secrets.token_urlsafe(32)
        super().__init__(("127.0.0.1", puerto), VistaRevision)


def servidor(bd: Path, puerto: int = 8770, perfil: Path = PERFIL_DEMO) -> ServidorRevision:
    return ServidorRevision(bd, puerto, perfil)


class VistaRevision(BaseHTTPRequestHandler):
    server: ServidorRevision

    def _responder(
        self, cuerpo: bytes, codigo: HTTPStatus = HTTPStatus.OK, tipo: str = "text/html; charset=utf-8",
    ) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _pagina(self, titulo: str, contenido: str, codigo: HTTPStatus = HTTPStatus.OK) -> None:
        self._responder(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_texto(titulo)}</title>
<style>{ESTILO}</style></head><body><main>{contenido}</main></body></html>""".encode(), codigo)

    def _host_local(self) -> bool:
        host = self.headers.get_all("Host", [])
        if host == [f"127.0.0.1:{self.server.server_port}"] or host == ["127.0.0.1"]:
            return True
        self.send_error(HTTPStatus.FORBIDDEN)
        return False

    def do_GET(self) -> None:
        if not self._host_local():
            return
        url = urlsplit(self.path)
        partes = url.path.split("/")
        try:
            if url.path == "/":
                self._lista()
            elif len(partes) == 3 and partes[1] == "candidatura":
                self._detalle(int(partes[2]))
            elif len(partes) == 3 and partes[1] == "pdf":
                pdf = self._pdf(unquote(partes[2]), parse_qs(url.query))
                self._responder(pdf, tipo="application/pdf")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, OSError):
            self.send_error(HTTPStatus.NOT_FOUND)
        except sqlite3.Error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        if not self._host_local():
            return
        partes = urlsplit(self.path).path.split("/")
        if len(partes) != 4 or partes[1] != "candidatura" or partes[3] not in {"aprobar", "cv"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            identificador = int(partes[2])
            largo = int(self.headers.get("Content-Length", "0"))
            tipo = self.headers.get_content_type()
            if not 0 < largo <= 4096 or tipo != "application/x-www-form-urlencoded":
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            campos = parse_qs(self.rfile.read(largo).decode("utf-8"), max_num_fields=8)
        except ValueError:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        token = campos.get("token", [])
        if len(token) != 1 or not hmac.compare_digest(token[0].encode(), self.server.token.encode()):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        try:
            huella_vista = campos.get("huella", [""])[0]
            if partes[3] == "aprobar":
                self._aprobar(identificador, huella_vista)
            else:
                self._elegir_cv(identificador, campos.get("version", [""])[0], huella_vista)
        except (ValueError, OSError):
            self.send_error(HTTPStatus.NOT_FOUND)
        except sqlite3.Error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def _aprobar(self, identificador: int, huella_vista: str) -> None:
        fila = candidaturas.leer(self.server.bd, identificador)
        if huella_vista != fila["huella"]:
            self._detalle(identificador, HTTPStatus.CONFLICT, "El contenido cambió, revisa de nuevo.")
            return
        if fila["estado"] != "aprobado":
            try:
                self._pdf(fila["cv_version"], {"id": [str(identificador)], "huella": [huella_vista]})
                candidaturas.cambiar_estado(
                    self.server.bd, identificador, "aprobado", huella_vista=huella_vista, motivo="vista",
                )
            except (ValueError, OSError) as error:
                actual = candidaturas.leer(self.server.bd, identificador)
                if actual["huella"] != huella_vista:
                    self._detalle(identificador, HTTPStatus.CONFLICT, "El contenido cambió, revisa de nuevo.")
                    return
                if actual["estado"] != "aprobado":
                    aviso = "El PDF no está disponible." if isinstance(error, OSError) else str(error)
                    self._detalle(identificador, HTTPStatus.CONFLICT, aviso)
                    return
        self._detalle(identificador)

    def _elegir_cv(self, identificador: int, version: str, huella_vista: str) -> None:
        archivo = self.server.pdfs.get(version)
        if archivo is None:
            self._detalle(identificador, HTTPStatus.CONFLICT, "La versión del CV no está configurada.")
            return
        try:
            candidaturas.elegir_cv(self.server.bd, identificador, version, archivo, huella_vista)
        except (ValueError, OSError) as error:
            aviso = "El PDF no está disponible." if isinstance(error, OSError) else str(error)
            self._detalle(identificador, HTTPStatus.CONFLICT, aviso)
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/candidatura/{identificador}")
        self.end_headers()

    def _lista(self) -> None:
        with closing(candidaturas._conectar(self.server.bd)) as db:
            filas = db.execute("SELECT id, cargo, estado FROM candidaturas ORDER BY id DESC").fetchall()
        enlaces = "".join(
            f'<li><a href="/candidatura/{fila["id"]}">{_texto(fila["cargo"])}</a>'
            f' · {_texto(fila["estado"])}</li>'
            for fila in filas
        )
        contenido = f"<ul>{enlaces}</ul>" if enlaces else """
<p>Esta base todavía no tiene candidaturas.
Las ofertas importadas aparecen aquí después de crear una candidatura.</p>
<p>Si ya creaste una, inicia la vista con <code>--bd RUTA</code> y apunta a esa misma base.</p>
<p>Para probar con un ejemplo ficticio, reinicia con <code>python3 -m asistente.revision --demo</code>.</p>"""
        self._pagina("Candidaturas", f"<h1>Candidaturas</h1>{contenido}")

    def _pdf(self, version: str, consulta: dict[str, list[str]]) -> bytes:
        archivo = self.server.pdfs.get(version)
        if archivo is None:
            raise ValueError("Versión desconocida")
        pdf = archivo.read_bytes()
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("Archivo PDF inválido")
        if consulta:
            fila = candidaturas.leer(self.server.bd, int(consulta.get("id", [""])[0]))
            if (
                version != fila["cv_version"] or str(archivo) != fila["archivo"]
                or consulta.get("huella") != [fila["huella"]]
                or hashlib.sha256(pdf).hexdigest() != fila["pdf_sha256"]
            ):
                raise ValueError("El PDF ya no coincide con la candidatura")
        return pdf

    def _detalle(
        self, identificador: int, codigo: HTTPStatus = HTTPStatus.OK, aviso: str = "",
    ) -> None:
        fila = candidaturas.leer(self.server.bd, identificador)
        with closing(candidaturas._conectar(self.server.bd)) as db:
            oferta = db.execute(
                "SELECT empresa, enlace, descripcion FROM ofertas WHERE fuente=? AND id_origen=?",
                (fila["fuente"], fila["id_origen"]),
            ).fetchone()
            decision = db.execute(
                "SELECT requisitos FROM decisiones WHERE id=?", (fila["decision_id"],),
            ).fetchone()
        requisitos = "".join(
            f'<li>{_texto(row["tipo"])} · <q>{_texto(row["cita"])}</q>'
            f' · {_texto(self.server.evidencias.get(row.get("evidencia"), "Pendiente"))}</li>'
            for row in json.loads(decision["requisitos"])
        )
        respuestas = "".join(
            f'<li><strong>{_texto(campo)}</strong> · {_texto(valor)}'
            f'{" <strong>Pendiente</strong>" if campo in fila["pendientes"] else ""}</li>'
            for campo, valor in fila["respuestas"].items()
        )
        consulta = {"id": [str(identificador)], "huella": [fila["huella"]]}
        pdf_disponible = False
        try:
            self._pdf(fila["cv_version"], consulta)
            pdf_disponible = True
            ruta = f'/pdf/{quote(fila["cv_version"], safe="")}?{urlencode(consulta, doseq=True)}'
            pdf = (
                f'<embed src="{_texto(ruta)}" type="application/pdf" title="Vista previa del CV">'
                f'<p><a href="{_texto(ruta)}" target="_blank" rel="noopener noreferrer">Abrir PDF</a></p>'
            )
        except (OSError, ValueError):
            pdf = "<p>El PDF guardado falta o cambió. Actualiza la candidatura antes de aprobar.</p>"
        sin_descripcion = "<p>Oferta pendiente de descripción.</p>" if not oferta["descripcion"] else ""
        aprobacion = ""
        if fila["estado"] == "listo":
            deshabilitado = " disabled" if fila["pendientes"] or not pdf_disponible else ""
            aprobacion = f"""
<form method="post" action="/candidatura/{identificador}/aprobar">
<input type="hidden" name="token" value="{self.server.token}">
<input type="hidden" name="huella" value="{_texto(fila["huella"])}">
<button{deshabilitado}>Aprobar</button></form>"""
        elegir = ""
        if fila["estado"] in {"listo", "aprobado"}:
            opciones = "".join(
                f'<option value="{_texto(version)}">{_texto(version)}</option>'
                for version in self.server.pdfs if version != fila["cv_version"]
            )
            if opciones:
                elegir = f"""
<form method="post" action="/candidatura/{identificador}/cv">
<input type="hidden" name="token" value="{self.server.token}">
<input type="hidden" name="huella" value="{_texto(fila["huella"])}">
<label for="version">Otra versión del CV</label>
<select id="version" name="version">{opciones}</select>
<button>Cambiar CV</button></form>"""
        mensaje = f'<p role="alert">{_texto(aviso)}</p>' if aviso else ""
        self._pagina(fila["cargo"], f"""
<p><a href="/">Candidaturas</a></p><h1>{_texto(fila["cargo"])}</h1>
{mensaje}<p>{_texto(oferta["empresa"])} · {_texto(fila["estado"])}</p>
<p>Oferta: {_texto(oferta["enlace"])}</p>{sin_descripcion}
<p>Destino: {_texto(fila["destino"])}</p>
<section><h2>Requisitos</h2><ul>{requisitos}</ul></section>
<section><h2>CV</h2><p>{_texto(Path(fila["archivo"]).name)}</p>{pdf}{elegir}</section>
<section><h2>Respuestas</h2><ul>{respuestas}</ul>
<p>Huella <code>{_texto(fila["huella"])}</code></p>{aprobacion}</section>""", codigo)


def _crear_demo(bd: Path) -> int:
    cargo = "Analista de datos (demo)"
    descripcion = "Requisitos\nExperiencia con Python.\nExperiencia en análisis de datos."
    ofertas.guardar(bd, [{
        "fuente": "demo", "id_origen": "1", "empresa": "Banco ficticio", "cargo": cargo,
        "enlace": "https://example.org/oferta-demo", "descripcion": descripcion,
    }])
    perfil = read_json(PERFIL_DEMO)
    requisitos = reglas.extraer(descripcion, perfil)
    recomendacion, _ = recommend(requisitos, perfil["versiones"])
    pdf = PERFIL_DEMO.parent / perfil["versiones"]["datos"]["pdf"]
    decision = record(bd, "reglas", descripcion, requisitos, recomendacion, "datos", pdf, "Demo ficticia")
    identificador = candidaturas.crear(
        bd, "demo", "1", decision, pdf, {"Motivación": "Me interesa automatizar análisis con Python."},
    )
    candidaturas.cambiar_estado(bd, identificador, "listo")
    return identificador


def _servir(bd: Path, puerto: int, perfil: Path) -> None:
    with servidor(bd, puerto, perfil) as vista:
        print(f"http://127.0.0.1:{vista.server_port}", flush=True)
        vista.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre la vista local de candidaturas.")
    parser.add_argument("--bd", type=Path)
    parser.add_argument("--demo", action="store_true", help="Carga una candidatura ficticia temporal.")
    parser.add_argument("--puerto", type=int, default=8770)
    parser.add_argument("--perfil", type=Path)
    args = parser.parse_args()
    if args.demo and (args.bd is not None or args.perfil is not None):
        parser.error("La demo usa una base temporal y el perfil ficticio.")
    try:
        if args.demo:
            with TemporaryDirectory(prefix="candidaturas-demo-") as temporal:
                bd = Path(temporal) / "demo.sqlite3"
                _crear_demo(bd)
                _servir(bd, args.puerto, PERFIL_DEMO)
        else:
            _servir(args.bd or Path("postulaciones.sqlite3"), args.puerto, args.perfil or PERFIL_DEMO)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
