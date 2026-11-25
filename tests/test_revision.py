import re
import sqlite3
from contextlib import closing
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from app import record
from asistente import candidaturas, ofertas, revision

PERFIL = Path(__file__).resolve().parents[1] / "demo" / "perfil.json"


@pytest.fixture
def vista(tmp_path):
    bd = tmp_path / "postulaciones.sqlite3"
    pdf = PERFIL.parent / "cv" / "datos.pdf"
    ofertas.guardar(bd, [{
        "fuente": "demo", "id_origen": "1", "empresa": "Banco de prueba",
        "cargo": "Analista", "enlace": "https://example.org/oferta",
    }])
    decision = record(bd, "reglas", "Analista", [
        {"tipo": "obligatorio", "cita": "Uso de Python", "evidencia": "python", "estado": "respaldado"},
    ], "datos", "datos", pdf, "Ejemplo")
    identificador = candidaturas.crear(bd, "demo", "1", decision, pdf, {"motivación": "Datos <b>"})
    candidaturas.cambiar_estado(bd, identificador, "listo")
    with revision.servidor(bd, 0, PERFIL) as servidor:
        hilo = Thread(target=servidor.serve_forever)
        hilo.start()
        try:
            yield bd, identificador, f"http://127.0.0.1:{servidor.server_port}"
        finally:
            servidor.shutdown()
            hilo.join()


def test_muestra_candidatura_y_pdf(vista):
    bd, identificador, base = vista
    fila = candidaturas.leer(bd, identificador)
    with urlopen(base + "/") as respuesta:
        assert f"/candidatura/{identificador}" in respuesta.read().decode()
    with urlopen(f"{base}/candidatura/{identificador}") as respuesta:
        html = respuesta.read().decode()
    for texto in ("Analista", "Banco de prueba", "Uso de Python", "validación de archivos", "datos.pdf",
                  "example.org/oferta", "Datos &lt;b&gt;", fila["huella"]):
        assert texto in html
    assert "Datos <b>" not in html
    with urlopen(f"{base}/pdf/datos?id={identificador}&huella={fila['huella']}") as respuesta:
        assert respuesta.headers.get_content_type() == "application/pdf"
        assert respuesta.read() == (PERFIL.parent / "cv" / "datos.pdf").read_bytes()


@pytest.mark.parametrize("ruta", ["/pdf/../../etc/passwd", "/pdf/desconocido", "/pdf/%2e%2e%2fetc%2fpasswd"])
def test_pdf_ruta_fuera_de_lista(vista, ruta):
    _, _, base = vista
    with pytest.raises(HTTPError) as error:
        urlopen(base + ruta)
    assert error.value.code == 404


def test_host_no_local_rechazado(vista):
    _, _, base = vista
    with pytest.raises(HTTPError) as error:
        urlopen(Request(base, headers={"Host": "ejemplo.com"}))
    assert error.value.code == 403


def _formulario(base, identificador):
    with urlopen(f"{base}/candidatura/{identificador}") as respuesta:
        html = respuesta.read().decode()
    return html, dict(re.findall(r'name="(token|huella)" value="([^"]+)"', html))


def _post(base, identificador, accion, campos):
    return urlopen(f"{base}/candidatura/{identificador}/{accion}", urlencode(campos).encode())


def test_aprobar_huella_actual_y_repetir(vista):
    bd, identificador, base = vista
    _, campos = _formulario(base, identificador)
    for _ in range(2):
        with _post(base, identificador, "aprobar", campos) as respuesta:
            assert "aprobado" in respuesta.read().decode()
    assert [evento["motivo"] for evento in candidaturas.historial(bd, identificador)].count("vista") == 1


def test_huella_vieja_muestra_contenido_actual(vista):
    bd, identificador, base = vista
    _, campos = _formulario(base, identificador)
    candidaturas.actualizar_contenido(bd, identificador, respuestas={"motivación": "Respuesta nueva"})
    with pytest.raises(HTTPError) as error:
        _post(base, identificador, "aprobar", campos)
    assert error.value.code == 409
    html = error.value.read().decode()
    assert "El contenido cambió" in html
    assert "Respuesta nueva" in html
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


@pytest.mark.parametrize("token", ["", "inválido"])
def test_token_requerido(vista, token):
    bd, identificador, base = vista
    _, campos = _formulario(base, identificador)
    if token:
        campos["token"] = token
    else:
        campos.pop("token", None)
    with pytest.raises(HTTPError) as error:
        _post(base, identificador, "aprobar", campos)
    assert error.value.code == 403
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


def test_pendiente_bloquea_aprobacion(vista):
    bd, identificador, base = vista
    candidaturas.actualizar_contenido(bd, identificador, respuestas={"motivación": "{pendiente}"})
    html, campos = _formulario(base, identificador)
    assert "<button disabled>Aprobar</button>" in html
    with pytest.raises(HTTPError) as error:
        _post(base, identificador, "aprobar", campos)
    assert error.value.code == 409
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


def test_otro_cv_registra_decision_y_vuelve_a_listo(vista):
    bd, identificador, base = vista
    _, campos = _formulario(base, identificador)
    with _post(base, identificador, "aprobar", campos):
        pass
    anterior = candidaturas.leer(bd, identificador)
    _, campos = _formulario(base, identificador)
    with _post(base, identificador, "cv", {**campos, "version": "automatizacion"}) as respuesta:
        assert "automatizacion.pdf" in respuesta.read().decode()
    fila = candidaturas.leer(bd, identificador)
    assert fila["estado"] == "listo"
    assert fila["huella"] != anterior["huella"]
    assert fila["cv_version"] == "automatizacion"
    assert fila["decision_id"] != anterior["decision_id"]
    with closing(sqlite3.connect(bd)) as db:
        assert db.execute(
            "SELECT cv_recomendado, cv_elegido, archivo FROM decisiones WHERE id=?",
            (fila["decision_id"],),
        ).fetchone() == ("datos", "automatizacion", "automatizacion.pdf")
    with pytest.raises(HTTPError) as error:
        _post(base, identificador, "cv", {**campos, "version": "datos"})
    assert error.value.code == 409


def test_otro_cv_invalido_no_crea_decision(vista):
    bd, identificador, base = vista
    _, campos = _formulario(base, identificador)
    with pytest.raises(HTTPError) as error:
        _post(base, identificador, "cv", {**campos, "version": "../../etc/passwd"})
    assert error.value.code == 409
    with closing(sqlite3.connect(bd)) as db:
        assert db.execute("SELECT COUNT(*) FROM decisiones").fetchone()[0] == 1


def test_demo_crea_candidatura_lista_con_pdf_y_evidencia(tmp_path):
    bd = tmp_path / "demo.sqlite3"
    identificador = revision._crear_demo(bd)
    fila = candidaturas.leer(bd, identificador)
    assert (fila["fuente"], fila["estado"]) == ("demo", "listo")
    assert fila["pendientes"] == []

    with revision.servidor(bd, 0, revision.PERFIL_DEMO) as servidor:
        hilo = Thread(target=servidor.serve_forever)
        hilo.start()
        try:
            base = f"http://127.0.0.1:{servidor.server_port}"
            html, campos = _formulario(base, identificador)
            assert "Analista" in html and "Python" in html and "datos.pdf" in html
            with _post(base, identificador, "aprobar", campos):
                pass
            assert candidaturas.leer(bd, identificador)["estado"] == "aprobado"
        finally:
            servidor.shutdown()
            hilo.join()
