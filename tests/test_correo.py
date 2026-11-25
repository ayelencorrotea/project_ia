import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from app import record
from asistente import candidaturas, correo, ofertas

CORREOS = Path(__file__).parent / "fixtures" / "correo"


@pytest.fixture
def bd(tmp_path):
    bd = tmp_path / "postulaciones.sqlite3"
    pdf = tmp_path / "datos.pdf"
    pdf.write_bytes(b"%PDF-1.4 ejemplo ficticio")
    ofertas.guardar(bd, [{
        "fuente": "bci", "id_origen": "1", "empresa": "Bci", "cargo": "Analista",
        "enlace": "https://example.org/oferta",
    }])
    decision = record(bd, "reglas", "Analista", [], "datos", "datos", pdf, "Ejemplo")
    candidaturas.crear(bd, "bci", "1", decision, pdf, {})
    return bd


def eventos(bd):
    with closing(sqlite3.connect(bd)) as db:
        db.row_factory = sqlite3.Row
        return [dict(fila) for fila in db.execute("SELECT * FROM correo_eventos ORDER BY id")]


def importar_uno(bd, tmp_path, nombre):
    carpeta = tmp_path / "correos"
    carpeta.mkdir(exist_ok=True)
    shutil.copy(CORREOS / nombre, carpeta / nombre)
    return correo.importar(bd, carpeta)


def test_clasifica_entrevista_desde_html(bd, tmp_path):
    importar_uno(bd, tmp_path, "entrevista_bci.eml")
    [evento] = eventos(bd)
    assert evento["clase"] == "entrevista"
    assert evento["cita"] == "Te invitamos a una entrevista por videollamada el jueves a las 10:00."
    assert evento["remitente"] == "seleccion@bci.cl"
    assert evento["fecha"] == "2026-11-25T09:00:00-03:00"


def test_clasifica_rechazo_en_iso_8859_1(bd, tmp_path):
    importar_uno(bd, tmp_path, "rechazo_bci.eml")
    [evento] = eventos(bd)
    assert evento["clase"] == "rechazo"
    assert evento["cita"] == "Lamentablemente no continuarás en el proceso de selección."
    assert evento["asunto"] == "Resultado del proceso"


def test_guarda_solo_datos_minimos_sin_cuerpo(bd, tmp_path):
    importar_uno(bd, tmp_path, "confirmacion_bci.eml")
    [evento] = eventos(bd)
    assert evento["clase"] == "confirmacion"
    assert evento["cita"] == "Hemos recibido tu postulación al cargo Analista."
    volcado = "\n".join(sqlite3.connect(bd).iterdump())
    assert "ZX-0042" not in volcado and "Persona Ficticia" not in volcado


def test_no_relacionado_no_deja_filas(bd, tmp_path):
    resumen = importar_uno(bd, tmp_path, "no_relacionado.eml")
    assert eventos(bd) == []
    assert resumen["ignorados"] == 1
    assert "DESC-777" not in "\n".join(sqlite3.connect(bd).iterdump())


def test_reimportar_no_duplica(bd):
    primero = correo.importar(bd, CORREOS)
    cantidad = len(eventos(bd))
    segundo = correo.importar(bd, CORREOS)
    # muestra.mbox repite la confirmación del .eml: misma huella, un solo evento.
    assert cantidad == primero["importados"] == 3 and primero["repetidos"] == 1
    assert segundo["importados"] == 0 and segundo["repetidos"] == 4
    assert len(eventos(bd)) == cantidad


def test_lee_mbox(bd):
    resumen = correo.importar(bd, CORREOS / "muestra.mbox")
    assert resumen == {"importados": 1, "repetidos": 0, "ignorados": 1}
    assert [e["clase"] for e in eventos(bd)] == ["confirmacion"]


def test_rechaza_otro_tipo_de_archivo(bd, tmp_path):
    archivo = tmp_path / "notas.txt"
    archivo.write_text("Hemos recibido tu postulación", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\.eml"):
        correo.importar(bd, archivo)


def test_clasificar_otro_sin_frase():
    assert correo.clasificar("Boletín", "Novedades del mes.") == ("otro", None)


def por_verificar(bd, tmp_path, fuente="bci", id_origen="1"):
    [fila] = [c for c in todas(bd) if (c["fuente"], c["id_origen"]) == (fuente, id_origen)]
    candidaturas.cambiar_estado(bd, fila["id"], "listo")
    candidaturas.aprobar(bd, fila["id"], candidaturas.leer(bd, fila["id"])["huella"])
    candidaturas.marcar_envio(bd, fila["id"], "incierto")
    return fila["id"]


def todas(bd):
    with closing(sqlite3.connect(bd)) as db:
        db.row_factory = sqlite3.Row
        return [dict(f) for f in db.execute("SELECT id, fuente, id_origen, estado FROM candidaturas")]


def test_confirmacion_se_asocia_a_su_candidatura(bd, tmp_path):
    identificador = por_verificar(bd, tmp_path)
    importar_uno(bd, tmp_path, "confirmacion_bci.eml")
    [evento] = eventos(bd)
    assert evento["candidatura_id"] == identificador and evento["estado"] == "asociado"
    assert evento["clase"] == "confirmacion"
    assert evento["cita"] == "Hemos recibido tu postulación al cargo Analista."
    assert "confirmar" in correo.pendientes_texto(bd)


def test_importar_no_cambia_estado_y_confirmar_si(bd, tmp_path):
    identificador = por_verificar(bd, tmp_path)
    importar_uno(bd, tmp_path, "confirmacion_bci.eml")
    assert candidaturas.leer(bd, identificador)["estado"] == "por_verificar"
    [evento] = eventos(bd)
    correo.confirmar(bd, evento["id"])
    fila = candidaturas.leer(bd, identificador)
    assert fila["estado"] == "enviado"
    assert evento["huella"] in fila["comprobante"]
    assert eventos(bd)[0]["estado"] == "confirmado"
    with pytest.raises(ValueError, match="ya fue confirmado"):
        correo.confirmar(bd, evento["id"])


def test_confirmar_entrevista_no_cambia_estado(bd, tmp_path):
    identificador = por_verificar(bd, tmp_path)
    importar_uno(bd, tmp_path, "entrevista_bci.eml")
    [evento] = eventos(bd)
    assert evento["estado"] == "por_revisar"  # sin cargo ni ID en el texto
    with pytest.raises(ValueError, match="--candidatura"):
        correo.confirmar(bd, evento["id"])
    correo.confirmar(bd, evento["id"], candidatura=identificador)
    assert candidaturas.leer(bd, identificador)["estado"] == "por_verificar"
    assert eventos(bd)[0]["candidatura_id"] == identificador


def test_ambiguo_queda_por_revisar(bd, tmp_path):
    pdf = tmp_path / "datos.pdf"
    ofertas.guardar(bd, [{"fuente": "bci", "id_origen": "2", "empresa": "Bci", "cargo": "Analista de datos",
                          "enlace": "https://example.org/oferta-2"}])
    decision = record(bd, "reglas", "Analista de datos", [], "datos", "datos", pdf, "Ejemplo")
    candidaturas.crear(bd, "bci", "2", decision, pdf, {})
    carpeta = tmp_path / "correos"
    carpeta.mkdir()
    texto = (CORREOS / "confirmacion_bci.eml").read_text(encoding="utf-8")
    (carpeta / "ambiguo.eml").write_text(texto.replace("cargo Analista.", "cargo Analista de datos."),
                                         encoding="utf-8")
    correo.importar(bd, carpeta)
    [evento] = eventos(bd)
    assert evento["estado"] == "por_revisar" and evento["candidatura_id"] is None
    assert len(json.loads(evento["candidatas"])) == 2
    with pytest.raises(ValueError, match="no es candidata"):
        correo.confirmar(bd, evento["id"], candidatura=999)


def test_reenviado_usa_remitente_original(bd, tmp_path):
    por_verificar(bd, tmp_path)
    carpeta = tmp_path / "correos"
    carpeta.mkdir()
    (carpeta / "reenviado.eml").write_text(
        "From: Persona Ficticia <postulante@example.org>\nSubject: RV: Postulación al cargo Analista\n"
        "Date: Fri, 27 Nov 2026 08:00:00 -0300\nContent-Type: text/plain; charset=utf-8\n\n"
        "---------- Mensaje reenviado ---------\nDe: Equipo de Selección <empleos@bci.cl>\n"
        "Fecha: Tue, 24 Nov 2026 10:15:00 -0300\nAsunto: Postulación al cargo Analista\n\n"
        "Hemos recibido tu postulación al cargo Analista.\n", encoding="utf-8")
    correo.importar(bd, carpeta)
    [evento] = eventos(bd)
    assert evento["remitente"] == "empleos@bci.cl"
    assert evento["fecha"] == "2026-11-24T10:15:00-03:00"
    assert evento["estado"] == "asociado"
