import json

from asistente import evaluacion, ofertas

FICHA = """Analista de datos
Requisitos
Experiencia con Python
Manejo de SQL Server
Deseable
Conocimiento de Power BI
Funciones
Inglés intermedio para reuniones
"""
BASE = {"cargo": "Analista", "empresa": "Empresa ficticia", "enlace": "https://example.org/oferta"}


def preparar(tmp_path, revisiones=None):
    bd = tmp_path / "postulaciones.sqlite3"
    ofertas.guardar(bd, [
        {**BASE, "fuente": "bci", "id_origen": "1", "descripcion": FICHA},
        {**BASE, "fuente": "bci", "id_origen": "2"},
    ], momento="2026-11-24T10:00:00+00:00")
    carpeta = tmp_path / "evaluacion"
    carpeta.mkdir()
    if revisiones is not None:
        texto = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in revisiones)
        (carpeta / "revision.jsonl").write_text(texto, encoding="utf-8")
    return bd, carpeta


def test_extraccion_omitido_tipo_y_sin_evidencia(tmp_path):
    bd, carpeta = preparar(tmp_path, [{
        "fuente": "bci", "id_origen": "1", "requisitos": [
            {"cita": "Experiencia con  PYTHON", "tipo": "obligatorio"},
            {"cita": "Manejo de SQL Server", "tipo": "deseable"},
            {"cita": "Inglés intermedio para reuniones", "tipo": "obligatorio"},
        ],
    }])
    reporte = evaluacion.evaluar(bd, carpeta, perfil={})
    ficha = reporte["extraccion"]["fichas"][0]
    assert ficha["omitidos"] == ["Inglés intermedio para reuniones"]
    assert ficha["tipo_incorrecto"] == [
        {"cita": "Manejo de SQL Server", "esperado": "deseable", "extraido": "obligatorio"},
    ]
    assert ficha["sin_evidencia"] == ["Conocimiento de Power BI"]
    assert reporte["extraccion"]["totales"] == {
        "fichas": 1, "omitidos": 1, "tipo_incorrecto": 1, "sin_evidencia": 1, "sin_oferta": 0,
    }


def test_extraccion_sin_oferta_se_cuenta(tmp_path):
    bd, carpeta = preparar(tmp_path, [
        {"fuente": "bci", "id_origen": "99", "requisitos": [{"cita": "Python", "tipo": "obligatorio"}]},
        {"fuente": "bci", "id_origen": "2", "requisitos": [{"cita": "Python", "tipo": "obligatorio"}]},
    ])
    totales = evaluacion.evaluar(bd, carpeta, perfil={})["extraccion"]["totales"]
    assert totales["fichas"] == 0 and totales["sin_oferta"] == 2


def test_cobertura_por_fuente(tmp_path):
    bd, carpeta = preparar(tmp_path)
    reporte = evaluacion.evaluar(bd, carpeta, perfil={})
    assert reporte["cobertura"] == [{"fuente": "bci", "ofertas": 2, "completas": 1, "porcentaje": 50}]
    assert reporte["extraccion"] is None


def test_cobertura_guarda_reporte_del_dia(tmp_path, capsys):
    bd, carpeta = preparar(tmp_path)
    evaluacion.main(["--bd", str(bd), "--carpeta", str(carpeta), "--fecha", "2026-11-25"])
    salida = capsys.readouterr().out
    guardado = (carpeta / "reporte-2026-11-25.md").read_text(encoding="utf-8")
    assert "bci · 2 ofertas · 1 completas (50 %)" in guardado
    assert guardado.strip() in salida
    evaluacion.main(["--bd", str(bd), "--carpeta", str(carpeta), "--fecha", "2026-11-25", "--json"])
    assert json.loads(capsys.readouterr().out)["cobertura"][0]["fuente"] == "bci"


def test_sin_archivos_explica_y_sale_bien(tmp_path, capsys):
    carpeta = tmp_path / "privado" / "evaluacion"
    evaluacion.main(["--bd", str(tmp_path / "x.sqlite3"), "--carpeta", str(carpeta)])
    salida = capsys.readouterr().out
    assert "revision.jsonl" in salida and "interes.jsonl" in salida
    assert not carpeta.exists()


def etiquetar(tmp_path, cantidad, interesa_cada=2):
    """Ofertas ficticias detectadas un día distinto cada una; las de datos interesan, las de ventas no."""
    bd = tmp_path / "ranking.sqlite3"
    etiquetas = []
    for i in range(cantidad):
        interesa = i % interesa_cada == 0
        descripcion = "Requisitos\n" + ("Python y SQL para datos" if interesa else "Ventas en terreno")
        ofertas.guardar(bd, [{**BASE, "fuente": "bci", "id_origen": str(i), "descripcion": descripcion,
                              "cargo": "Analista de datos" if interesa else "Ejecutivo comercial"}],
                        momento=f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T10:00:00+00:00")
        etiquetas.append({"fuente": "bci", "id_origen": str(i), "interes": "sí" if interesa else "no"})
    etiquetas.append({"fuente": "bci", "id_origen": "no-existe", "interes": "sí"})
    carpeta = tmp_path / "evaluacion"
    carpeta.mkdir()
    texto = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in etiquetas)
    (carpeta / "interes.jsonl").write_text(texto, encoding="utf-8")
    return bd, carpeta


PERFIL = {"señales": {"python": {"palabras": ["python"], "respaldo": True}}}


def test_ranking_muestra_reservada_no_entrena(tmp_path, monkeypatch):
    bd, carpeta = etiquetar(tmp_path, 80)
    vistas: list[str] = []
    original = evaluacion.entrenar_bayes

    def espiar(entrenamiento):
        vistas.extend(f"{oferta['fuente']}:{oferta['id_origen']}" for oferta, _ in entrenamiento)
        return original(entrenamiento)

    monkeypatch.setattr(evaluacion, "entrenar_bayes", espiar)
    ranking = evaluacion.evaluar(bd, carpeta, perfil=PERFIL)["ranking"]
    assert ranking["suficiente"] and ranking["sin_oferta"] == 1
    assert ranking["entrenamiento"] == 60 and len(ranking["reservada"]) == 20
    assert not set(vistas) & set(ranking["reservada"])
    numero = lambda clave: int(clave.split(":")[1])  # noqa: E731
    assert min(map(numero, ranking["reservada"])) > max(map(numero, vistas))
    for metodo in ("reglas", "modelo"):
        assert ranking[metodo] == {"precision_5": 1.0, "interesa_top5": 5}


def test_ranking_insuficientes_no_entrena(tmp_path, monkeypatch):
    bd, carpeta = etiquetar(tmp_path, 20)

    def no_entrenar(entrenamiento):
        raise AssertionError("no debe entrenar")

    monkeypatch.setattr(evaluacion, "entrenar_bayes", no_entrenar)
    ranking = evaluacion.evaluar(bd, carpeta, perfil=PERFIL)["ranking"]
    assert ranking == {"suficiente": False, "etiquetas": 20, "sin_oferta": 1, "faltan": 40,
                       "faltan_interesa": 5, "faltan_no_interesa": 5}
    texto = evaluacion.formatear(evaluacion.evaluar(bd, carpeta, perfil=PERFIL), "2026-11-25")
    assert "faltan 40 etiquetas" in texto
