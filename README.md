# Asistente de postulaciones

Primer prototipo de portafolio. Convierte una oferta en requisitos con citas,
los compara con evidencia del perfil y recomienda un CV. La persona revisa el
PDF y elige qué versión registrar en SQLite.

## Desarrollo

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
ruff check . && mypy app.py itau.py asistente relay tests && pytest
```

CI ejecuta lo mismo en cada push y pull request. Para proponer cambios, lee `CONTRIBUTING.md`; las reglas para agentes de código están en `AGENTS.md`.

## Demo local

Requiere Python 3.10 o posterior. Usa la biblioteca estándar.

```sh
python app.py
python app.py --elegir datos --motivo "Destaca mi experiencia analítica"
```

Abre cualquiera de los PDF que muestra el primer comando para previsualizarlo.
La segunda instrucción guarda el nombre y el hash del PDF, la recomendación,
la elección y su motivo. Cada elección agrega una fila al historial local.

Esta demo reproduce la referencia manual de una ficha pública de Itaú y usa
un perfil ficticio. Un requisito respaldado y obligatorio aporta dos puntos a
cada CV que contiene la evidencia. Los otros requisitos respaldados aportan
un punto. Si ningún CV obtiene puntos o hay empate arriba, se pide elegir sin
recomendación.

### Evidencia por versión de CV

La salida muestra las citas que aportan puntos a cada versión y las citas
respaldadas por el perfil cuya evidencia queda fuera de esa versión. Los
requisitos por confirmar se muestran en el análisis general y quedan fuera
del puntaje. El mapa de evidencias de cada versión se mantiene en el JSON y
debe reflejar el contenido de su PDF. La demo de Bci permite comprobarlo con
el requisito de ETL del cargo Especialista Procesos y Proyectos Tarjeta.

## Análisis con IA

Configura `OPENAI_API_KEY` en tu entorno local y ejecuta
`python app.py --modelo NOMBRE_DEL_MODELO` con un modelo habilitado en tu cuenta.
Para analizar otra vacante, pasa un archivo de texto con `--oferta`. Puedes
pasar `--perfil privado/perfil.json` con el formato de `demo/perfil.json`. Las
rutas de los PDF son relativas al JSON. Incluye solo la evidencia profesional
que quieras pasar a la API. Los PDF se mantienen locales.

Compara la salida del modelo con `demo/referencia.json` para revisar la
clasificación de SQL Server y Python, los requisitos omitidos y los casos en
que la evidencia es insuficiente. La validación comprueba las citas y las
referencias al perfil. La correspondencia entre ambos requiere revisión humana.

Esta etapa termina al registrar la versión elegida. La lectura automática
de portales y el envío quedan para una fase posterior.

## Lector de ofertas públicas de Itaú

Instala la dependencia del lector dentro de un entorno virtual.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 itau.py
```

El lector consulta `robots.txt`, limita el ritmo de las consultas y recorre
hasta dos páginas del buscador por defecto. Puedes pedir hasta diez fichas
con `--detalles 3`, por ejemplo. Si el portal rechaza la solicitud, el lector
se detiene y muestra el código HTTP.

También puedes guardar las páginas públicas como HTML desde el navegador e
importarlas localmente. Para incluir una descripción, guarda la ficha en
`privado/fichas` con el identificador numérico de su enlace y extensión
`.html`, por ejemplo `1338411962.html`.

```sh
python3 itau.py --html privado/search.html --fichas privado/fichas
```

La tabla común `ofertas` guarda título, enlace, ubicación, fecha y, cuando está
disponible, descripción. Los registros de `ofertas_itau` se copian sin borrar la
tabla histórica. Para migrar sin consultar el portal, usa `python3 itau.py --solo-migrar`. El identificador numérico evita duplicados al volver
a importar. El lector funciona sin un modelo y prepara los datos para
conectarlos al recomendador.

## Lector de ofertas públicas de Bci

El portal `trabajaenbci.cl` es una aplicación web que obtiene sus datos de una API JSON pública, sin sesión:
el listado sale de `POST /api/v3/bci_portals/_search` y cada ficha de `GET /api/v3/bci_portals/proceso/<id>`.
El lector usa esas mismas rutas con la biblioteca estándar, consulta `robots.txt`, espera al menos un segundo
entre consultas y se detiene si el portal rechaza el listado.

```sh
python3 -m asistente.bci --detalles 3
python3 app.py --oferta-bd bci:39410 --reglas
```

La primera instrucción guarda las ofertas en la tabla común `ofertas` (una fila por fuente e ID de origen) con
cargo, empresa, ubicación, fecha de publicación, fecha de detección, enlace oficial y, si se leyó la ficha,
la descripción con sus secciones «Funciones», «Requisitos» y «Deseable». Las ofertas sin ficha quedan
«pendiente de descripción». Una nueva importación actualiza los datos sin borrar una descripción ni la primera
fecha de detección. Los rechazos HTTP y las fichas que no llegan quedan en la tabla `fallos` con fuente, fecha,
URL, código y motivo.

La segunda instrucción extrae los requisitos con reglas: las secciones «Requisitos» y «Deseable» dan el tipo y
las `señales` del perfil (`demo/perfil.json`) asocian la evidencia. Si la frase exige años o un nivel avanzado,
el requisito queda por confirmar aunque haya evidencia. Para revisar sin conexión, guarda las respuestas JSON
y usa `python3 -m asistente.bci --json listado.json --fichas carpeta/` con fichas `proceso_<id>.json`.

## Revisión local de candidaturas

Usa la misma base SQLite al importar la oferta, elegir el CV y crear la candidatura.
El siguiente ejemplo supone que la oferta `bci:39410` ya está guardada. Usa el ID
de tu oferta y el número que imprime «Decisión guardada» en lugar de `1`.

```sh
python3 app.py --oferta-bd bci:39410 --reglas --elegir datos
python3 -m asistente.candidaturas crear bci:39410 1 demo/cv/datos.pdf
```

`crear` imprime el ID de la candidatura. Usa ese ID en los comandos siguientes.
El archivo `privado/respuestas.json` contiene un objeto con los nombres de los
campos y valores de texto, por ejemplo `{"motivación": "Experiencia con Python"}`.
`responder` reemplaza el conjunto de respuestas. Los valores vacíos o que
contienen `{pendiente}` aparecen en `mostrar` y bloquean la aprobación.

```sh
python3 -m asistente.candidaturas responder 1 privado/respuestas.json
python3 -m asistente.candidaturas listo 1
python3 -m asistente.candidaturas mostrar 1
python3 -m asistente.candidaturas aprobar 1 HUELLA_MOSTRADA
python3 -m asistente.candidaturas historial 1
```

Revisa el PDF y las respuestas antes de copiar la huella. Si cambian las
respuestas o el contenido del PDF, usa `responder` con el JSON completo y revisa
la nueva huella. Para usar otra base, coloca `--bd RUTA` antes del subcomando.

La CLI solo registra resultados en SQLite. Después de una postulación
confirmada, usa `enviado 1 --comprobante FOLIO` (el comprobante es opcional).
Si el resultado es incierto, usa `incierto 1`. Al verificar el resultado, usa
`enviado 1` si se realizó o `no-enviado 1` si se confirma que no se realizó.

### Revisar en el navegador

Ejecuta este comando y abre la dirección local que imprime:

```sh
python3 -m asistente.revision
```

Para practicar desde cero, ejecuta `python3 -m asistente.revision --demo`.
Verás una candidatura ficticia lista para revisar. Los cambios quedan en una
base temporal que se elimina al cerrar la demo. Usa `--puerto 8771` si ya
tienes otra instancia abierta.

La vista normal lista las candidaturas de la base indicada. Las ofertas
importadas aparecen después de preparar una candidatura con `crear`.

Abre una candidatura marcada como `listo` para revisar la oferta, las citas,
las respuestas y el PDF. Si eliges otro CV, la vista registra la decisión,
muestra el PDF seleccionado y vuelve a pedir aprobación cuando cambia el
contenido. La aprobación queda registrada localmente en SQLite.

`--bd RUTA` selecciona la misma base que usaste en la CLI. Usa `--perfil RUTA`
para cargar el perfil con el que guardaste tu CV y `--puerto` para cambiar el
puerto predeterminado de 8770. La aplicación se sirve en `127.0.0.1`.

## Relay de navegador

La carpeta `relay/` contiene una extensión de Chrome y un servicio local para ejecutar recetas en el navegador
de la persona (leer portales que necesitan renderizado o sesión, completar un formulario hasta una vista previa)
y guardar los resultados en esta misma base. Nada se envía sin aprobar el contenido exacto. Ver
`relay/README.md`.
