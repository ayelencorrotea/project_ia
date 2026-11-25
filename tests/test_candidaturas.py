import hashlib
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

from app import record
from asistente import candidaturas, ofertas


@pytest.fixture
def candidatura(tmp_path):
    bd = tmp_path / "postulaciones.sqlite3"
    pdf = tmp_path / "datos.pdf"
    pdf.write_bytes(b"%PDF-1.4 ejemplo ficticio")
    ofertas.guardar(bd, [{
        "fuente": "bci", "id_origen": "1", "empresa": "Banco de prueba",
        "cargo": "Analista", "enlace": "https://example.org/oferta",
    }])
    decision = record(bd, "reglas", "Analista", [], "datos", "datos", pdf, "Ejemplo")
    identificador = candidaturas.crear(
        bd, "bci", "1", decision, pdf, {"motivación": "Análisis", "experiencia": "Python"},
    )
    return bd, identificador, decision, pdf


def test_aprobar(candidatura):
    bd, identificador, decision, pdf = candidatura
    fila = candidaturas.leer(bd, identificador)
    pdf_sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    contenido = (
        '{"cargo":"Analista","destino":"https://example.org/oferta",'
        f'"pdf_sha256":"{pdf_sha}","respuestas":{{"experiencia":"Python","motivación":"Análisis"}}}}'
    )
    assert fila["huella"] == hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    assert fila["decision_id"] == decision
    assert fila["estado"] == "borrador"

    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, fila["huella"])

    aprobada = candidaturas.leer(bd, identificador)
    assert aprobada["estado"] == "aprobado"
    assert aprobada["aprobada_en"]
    assert aprobada["huella"] == fila["huella"]


def test_huella_distinta(candidatura):
    bd, identificador, _, _ = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    with pytest.raises(ValueError, match="huella"):
        candidaturas.aprobar(bd, identificador, "0" * 64)
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


def test_aprobar_rechaza_pdf_modificado(candidatura):
    bd, identificador, _, pdf = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    fila = candidaturas.leer(bd, identificador)
    pdf.write_bytes(b"%PDF-1.4 contenido distinto")
    with pytest.raises(ValueError, match="PDF"):
        candidaturas.aprobar(bd, identificador, fila["huella"])
    assert candidaturas.leer(bd, identificador)["estado"] == "listo"


@pytest.mark.parametrize("estado", ["borrador", "listo"])
def test_transicion_directa_a_enviado_se_rechaza(candidatura, estado):
    bd, identificador, _, _ = candidatura
    if estado == "listo":
        candidaturas.cambiar_estado(bd, identificador, "listo")
    with pytest.raises(ValueError, match="Transición"):
        candidaturas.cambiar_estado(bd, identificador, "enviado")
    assert candidaturas.leer(bd, identificador)["estado"] == estado


def test_eventos(candidatura):
    bd, identificador, _, _ = candidatura
    fila = candidaturas.leer(bd, identificador)
    candidaturas.cambiar_estado(bd, identificador, "listo", motivo="Revisión preparada")
    candidaturas.aprobar(bd, identificador, fila["huella"])

    with closing(sqlite3.connect(bd)) as db:
        eventos = db.execute("""
            SELECT estado_anterior, estado_nuevo, fecha, huella, motivo
            FROM candidatura_eventos WHERE candidatura_id = ? ORDER BY id
        """, (identificador,)).fetchall()
    assert [(anterior, nuevo) for anterior, nuevo, *_ in eventos] == [
        ("borrador", "listo"), ("listo", "aprobado"),
    ]
    assert eventos[0][-1] == "Revisión preparada"
    assert all(fecha and huella == fila["huella"] and motivo for _, _, fecha, huella, motivo in eventos)


def test_eventos_y_estado_se_guardan_en_la_misma_transaccion(candidatura):
    bd, identificador, _, _ = candidatura
    with closing(sqlite3.connect(bd)) as db, db:
        db.execute("""
            CREATE TRIGGER impedir_evento BEFORE INSERT ON candidatura_eventos
            BEGIN
                SELECT RAISE(ABORT, 'error de prueba');
            END
        """)
    with pytest.raises(sqlite3.IntegrityError, match="error de prueba"):
        candidaturas.cambiar_estado(bd, identificador, "listo")
    assert candidaturas.leer(bd, identificador)["estado"] == "borrador"


def test_una_sola_candidatura_activa_por_oferta(candidatura):
    bd, identificador, decision, pdf = candidatura
    with pytest.raises(ValueError, match="activa"):
        candidaturas.crear(bd, "bci", "1", decision, pdf)

    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, candidaturas.leer(bd, identificador)["huella"])
    candidaturas.cambiar_estado(bd, identificador, "enviado")
    assert candidaturas.crear(bd, "bci", "1", decision, pdf) != identificador


@pytest.mark.parametrize("campo", ["respuestas", "archivo", "destino"])
def test_cambio_invalida_aprobacion(candidatura, campo):
    bd, identificador, _, pdf = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    anterior = candidaturas.leer(bd, identificador)["huella"]
    candidaturas.aprobar(bd, identificador, anterior)

    cambios = {
        "respuestas": {"experiencia": "Análisis con Python"},
        "archivo": pdf,
        "destino": "https://example.org/nueva-oferta",
    }
    if campo == "archivo":
        pdf.write_bytes(b"%PDF-1.4 contenido actualizado")
    candidaturas.actualizar_contenido(bd, identificador, **{campo: cambios[campo]})

    fila = candidaturas.leer(bd, identificador)
    assert fila["estado"] == "listo"
    assert fila["huella"] != anterior
    assert fila["aprobada_en"] is None
    with pytest.raises(ValueError, match="huella"):
        candidaturas.aprobar(bd, identificador, anterior)
    with closing(sqlite3.connect(bd)) as db:
        eventos = db.execute("""
            SELECT estado_nuevo, huella FROM candidatura_eventos
            WHERE candidatura_id = ? ORDER BY id
        """, (identificador,)).fetchall()
    assert eventos[-2:] == [("aprobado", anterior), ("listo", fila["huella"])]


def test_cambio_equivalente_conserva_aprobacion(candidatura):
    bd, identificador, _, _ = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    anterior = candidaturas.leer(bd, identificador)["huella"]
    candidaturas.aprobar(bd, identificador, anterior)
    candidaturas.actualizar_contenido(
        bd, identificador, respuestas={"experiencia": "Python", "motivación": "Análisis"},
    )
    assert candidaturas.leer(bd, identificador)["estado"] == "aprobado"


def test_pendiente_impide_listo_y_aprobacion(candidatura):
    bd, identificador, _, _ = candidatura
    respuestas = {"experiencia": "  ", "fecha": "Inicio: {pendiente}", "cargo": "Analista"}
    candidaturas.actualizar_contenido(bd, identificador, respuestas=respuestas)
    assert candidaturas.leer(bd, identificador)["pendientes"] == ["experiencia", "fecha"]
    with pytest.raises(ValueError, match="experiencia, fecha"):
        candidaturas.cambiar_estado(bd, identificador, "listo")
    assert candidaturas.leer(bd, identificador)["estado"] == "borrador"

    candidaturas.actualizar_contenido(bd, identificador, respuestas={"cargo": "Analista"})
    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, candidaturas.leer(bd, identificador)["huella"])
    candidaturas.actualizar_contenido(bd, identificador, respuestas=respuestas)
    fila = candidaturas.leer(bd, identificador)
    assert fila["estado"] == "listo"
    with pytest.raises(ValueError, match="experiencia, fecha"):
        candidaturas.aprobar(bd, identificador, fila["huella"])


def test_por_verificar_bloquea_reintento_hasta_no_enviado(candidatura):
    bd, identificador, _, _ = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, candidaturas.leer(bd, identificador)["huella"])
    antes = candidaturas.leer(bd, identificador)
    candidaturas.marcar_envio(bd, identificador, "incierto")
    with pytest.raises(ValueError, match="por_verificar"):
        candidaturas.marcar_envio(bd, identificador, "incierto")
    with pytest.raises(ValueError, match="por_verificar"):
        candidaturas.actualizar_contenido(bd, identificador, respuestas={"dato": "otro"})
    candidaturas.marcar_envio(bd, identificador, "no_enviado")
    assert candidaturas.leer(bd, identificador) == antes
    candidaturas.marcar_envio(bd, identificador, "enviado", comprobante="folio-123")
    fila = candidaturas.leer(bd, identificador)
    assert fila["estado"] == "enviado"
    assert fila["enviada_en"]
    assert fila["comprobante"] == "folio-123"


def test_por_verificar_permite_confirmar_envio_anterior(candidatura):
    bd, identificador, _, _ = candidatura
    candidaturas.cambiar_estado(bd, identificador, "listo")
    candidaturas.aprobar(bd, identificador, candidaturas.leer(bd, identificador)["huella"])
    candidaturas.marcar_envio(bd, identificador, "incierto")
    candidaturas.marcar_envio(bd, identificador, "enviado", comprobante="folio-anterior")
    assert candidaturas.leer(bd, identificador)["comprobante"] == "folio-anterior"


def test_cambio_de_version_usa_la_nueva_decision(candidatura):
    bd, identificador, _, pdf = candidatura
    otro_pdf = pdf.with_name("automatizacion.pdf")
    otro_pdf.write_bytes(b"%PDF-1.4 otro CV ficticio")
    decision = record(
        bd, "reglas", "Analista", [], "datos", "automatizacion", otro_pdf, "Ejemplo",
    )
    candidaturas.cambiar_estado(bd, identificador, "listo")
    anterior = candidaturas.leer(bd, identificador)["huella"]
    candidaturas.aprobar(bd, identificador, anterior)

    candidaturas.actualizar_contenido(bd, identificador, archivo=otro_pdf, decision_id=decision)
    fila = candidaturas.leer(bd, identificador)
    assert fila["decision_id"] == decision
    assert fila["cv_version"] == "automatizacion"
    assert fila["archivo"] == str(otro_pdf)
    assert fila["estado"] == "listo"
    assert fila["huella"] != anterior
    candidaturas.aprobar(bd, identificador, fila["huella"])


def test_cli_recorrido(tmp_path):
    bd = tmp_path / "demo.sqlite3"
    pdf = Path(__file__).resolve().parents[1] / "demo" / "cv" / "datos.pdf"
    ofertas.guardar(bd, [{
        "fuente": "demo", "id_origen": "1", "empresa": "Banco de prueba",
        "cargo": "Analista", "enlace": "https://example.org/oferta",
    }])
    decision = record(bd, "reglas", "Analista", [], "datos", "datos", pdf, "Prueba ficticia")

    def cli(*args, check=True):
        return subprocess.run(  # noqa: S603 - invokes the test interpreter with fixture arguments
            [sys.executable, "-m", "asistente.candidaturas", "--bd", str(bd), *args],
            text=True, capture_output=True, check=check,
        )

    identificador = cli("crear", "demo:1", str(decision), str(pdf)).stdout.strip()
    respuestas = tmp_path / "respuestas.json"
    respuestas.write_text('{"motivación":"{pendiente}"}', encoding="utf-8")
    cli("responder", identificador, str(respuestas))
    error = cli("listo", identificador, check=False)
    assert error.returncode == 1
    assert "motivación" in error.stderr
    respuestas.write_text('{"motivación":"Análisis con Python"}', encoding="utf-8")
    cli("responder", identificador, str(respuestas))
    cli("listo", identificador)
    fila = json.loads(cli("mostrar", identificador).stdout)
    assert fila["archivo"] == str(pdf)
    assert fila["estado"] == "listo"
    assert fila["respuestas"] == {"motivación": "Análisis con Python"}

    error = cli("aprobar", identificador, "0" * 64, check=False)
    assert error.returncode == 1
    assert "huella" in error.stderr
    cli("aprobar", identificador, fila["huella"])
    cli("incierto", identificador)
    cli("no-enviado", identificador)
    cli("enviado", identificador, "--comprobante", "folio-demo")
    resultado = json.loads(cli("mostrar", identificador).stdout)
    assert resultado["comprobante"] == "folio-demo"
    assert resultado["estado"] == "enviado"
    eventos = json.loads(cli("historial", identificador).stdout)
    assert [evento["estado_nuevo"] for evento in eventos] == [
        "listo", "aprobado", "por_verificar", "aprobado", "enviado",
    ]
