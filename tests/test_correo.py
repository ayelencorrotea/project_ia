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
    assert evento["estado"] == "por_revisar" and evento["candidatura_id"] is None
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
