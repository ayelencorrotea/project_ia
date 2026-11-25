# Asistente de postulaciones | Historia de usuario

**Como profesional de software interesada en datos, IA aplicada y automatización en Chile, quiero que un asistente encuentre vacantes nuevas, explique cuáles calzan con mi experiencia y prepare la candidatura con el CV que yo elija, para postular a tiempo con menos trabajo repetitivo y aprobar personalmente lo que se envía.**

## Flujo esperado

1. **Descubrir ofertas.** Consultar fuentes públicas y conservar cargo, empresa, ID de origen cuando exista, fecha de publicación si está disponible, fecha de detección, ubicación, enlace oficial y descripción. Buscar inicialmente en Itaú Chile, Bci, Banco de Chile, LATAM, SKY, Caja Los Andes y Coopeuch. Priorizar IA aplicada, automatización, datos y Python. Incluir BI, riesgo, inteligencia comercial y herramientas internas cuando el trabajo incluya programación, datos o automatización.
2. **Evaluar el encaje.** Separar requisitos obligatorios, deseables y sin clasificación explícita. Mostrar la frase del aviso y la experiencia que respalda cada requisito o dejarlo pendiente. El curso de Power BI queda fuera de las aptitudes acreditadas. Si Power BI es central, señalar la brecha y bajar la prioridad. Si solo existe el título o enlace, mostrar «pendiente de descripción» y limitarse a un filtro preliminar.
3. **Elegir el CV.** Recomendar Datos y analítica financiera, IA aplicada y automatización o Frontend y móvil. Explicar la recomendación, mostrar el PDF exacto, permitir elegir otro y registrar en SQLite la versión recomendada y la elegida. La matriz conserva hechos y evidencia del perfil. Los ejemplos publicados usan datos ficticios.
4. **Preparar y enviar.** Mostrar destino, cargo, adjuntos y respuestas exactas. Marcar los datos pendientes y permitir corregirlos. En una fase posterior, enviar tras una aprobación explícita por candidatura en los portales que admitan el flujo. Si cambian el destino, las respuestas o el PDF, pedir una nueva revisión. La persona inicia sesión directamente en el portal. Probar primero en un formulario de práctica y luego evaluar un portal real, con Banco de Chile como candidato por la dificultad de su formulario.
5. **Registrar el resultado.** Distinguir borrador, listo para revisar, aprobado, enviado y por verificar. Guardar fecha y comprobante cuando exista. Un envío incierto requiere comprobar su estado antes de reintentar. Más adelante, el seguimiento de correo puede asociar confirmaciones, entrevistas y rechazos con una candidatura existente.

## Criterios de aceptación

| Caso | Resultado esperado |
|---|---|
| Se importa dos veces la misma fuente | Una fila por ID de origen, con actualización de datos y conservación de una descripción existente si la consulta nueva solo trae el listado. Una coincidencia entre fuentes requiere enlace común o revisión cuando sea ambigua. |
| El aviso exige SQL Server y menciona Python como deseable | Los presenta con su tipo y cita. La mención de SQL Server en el perfil puede quedar pendiente si falta evidencia de uso. |
| Se procesa una ficha nueva completa | Extrae requisitos y recomienda un CV sin preparar una respuesta manual para esa oferta. Las reglas de Python cubren señales claras. La IA generativa puede ayudar con texto ambiguo o respuestas abiertas. |
| La persona elige un CV distinto | Puede previsualizarlo y el historial conserva recomendación, elección e identificación del archivo exacto. |
| Una fuente falla o entrega solo un título | El sistema indica la limitación de cobertura o el estado pendiente y conserva las ofertas ya obtenidas. |
| Se modifica una candidatura aprobada o falta confirmación del envío | Solicita una nueva revisión si cambió el contenido aprobado. Si el resultado es incierto, marca «por verificar» y evita duplicados. |

## Estado actual

- El reporte de cobertura cuenta ofertas y fallos en SQLite. El reconocimiento de Banco de Chile, SKY, Caja Los Andes y Coopeuch está documentado en la spec 007. Sus limitaciones se pueden registrar localmente.

- `app.py` calcula una recomendación, registra la elección en SQLite y guarda la huella del PDF. El ejemplo de Itaú usa una referencia manual y un perfil ficticio. La ruta opcional a OpenAI se probó con una respuesta simulada; falta validarla con un modelo real.
- `itau.py` importa listados y fichas HTML. En el Mac se importaron 25 ofertas de una copia real del listado. Desde Codex, la consulta directa a Itaú recibió HTTP 403.
- `asistente/bci.py` lee Bci desde la API pública que usa su sitio (prueba del 2026-11-24: 45 ofertas publicadas, listado y fichas completas con requisitos). Guarda en la tabla común `ofertas` y registra los fallos por fuente. `app.py --oferta-bd bci:<id> --reglas` lleva una ficha guardada hasta la recomendación con reglas de Python. Itaú escribe en la tabla común y conserva su tabla histórica. LATAM respondió con el HTML inicial de la página, sin requisitos en esa respuesta. Queda por validar una ficha renderizada.
- La búsqueda diaria en ChatGPT es independiente del repositorio. Consulta los siete empleadores y avisa si encuentra novedades relevantes. Su cobertura depende de las páginas públicas y de la indexación.
- La integración con formularios autenticados y el seguimiento por correo están pendientes. Los recolectores y servicios externos evaluados siguen siendo opciones sujetas a comprobar cobertura y acceso.

## Primera entrega propuesta para colaborar

Tomar **una ficha pública nueva de Bci o LATAM** y cerrar el flujo hasta la recomendación. La prueba debe recuperar cargo, descripción con requisitos y enlace oficial, importar dos veces sin duplicados y recomendar un CV con citas y evidencia usando un perfil ficticio. Bci ya ofrece un listado legible. LATAM es candidato para probar renderizado estándar en un navegador. La importación de HTML guardado sirve de respaldo para probar el procesamiento.

La decisión técnica principal es elegir qué fuente logra entregar fichas completas y actualizadas con acceso permitido y mantenimiento razonable. Después mediremos calidad de extracción y tiempo ahorrado. Cuando tengamos suficientes ofertas etiquetadas por la usuaria, podremos comparar un modelo de ranking contra las reglas usando ofertas reservadas para evaluar.

[Repositorio del proyecto](https://github.com/ayelencorrotea/project_ia)

## Alcance y orden de entrega

| Fase | Entregable verificable |
|---|---|
| P0 · Descubrimiento | Un portal público entrega fichas completas de forma reproducible. Dos ejecuciones conservan una sola fila por oferta y un problema de acceso queda visible. |
| P1 · Evaluación y revisión | Una ficha nueva se procesa con reglas de base. La persona ve citas, evidencia, brechas, recomendación y PDF, y puede guardar su elección. |
| P2 · Postulación asistida | Un formulario de práctica se completa hasta una vista previa. Después se valida un portal real, con sesión iniciada por la persona y aprobación vinculada al contenido exacto. |
| P3 · Seguimiento y mejora | Se incorporan canales adicionales, confirmaciones por correo y, si hay datos etiquetados suficientes, evaluación de un ranking aprendido. |

## Datos y comportamiento mínimo

- **Oferta.** Identificador de fuente o URL canónica, empresa, cargo, ubicación, fechas de publicación y detección, descripción, enlace de postulación y estado de verificación. La fecha de detección nunca sustituye a la de publicación. Conservar el origen al combinar registros de distintas fuentes.
- **Requisito y evidencia.** Guardar el tipo de requisito, su cita literal, la evidencia del perfil si existe y su estado de respaldo. Mantener la decisión de interés por una oferta como un dato distinto de la elección de CV.
- **Candidatura.** Vincular oferta, versión y huella del PDF, respuestas revisadas, estado, momento de aprobación y comprobante si existe. Una confirmación incierta conserva el historial y requiere verificar antes de intentar otro envío.
- **Operación.** Cada fuente puede detenerse por acceso, cambios de estructura o falta de descripción. Registrar fuente, fecha y motivo del fallo. Conservar los registros anteriores y permitir que las otras fuentes sigan aportando ofertas.
- **Datos privados.** El CV real, tokens, credenciales y sesiones de navegador se gestionan fuera del repositorio. Las pruebas reproducibles usan datos ficticios y formularios de práctica.

## Preguntas para la revisión técnica

1. ¿Qué fuente probar primero para obtener fichas completas y qué alternativa usar si falla? El piloto tiene dos candidatos: Bci por su listado legible y LATAM por sus fichas públicas renderizadas en navegador.
2. ¿Cómo ejecutar la búsqueda periódica de la app y reutilizar resultados entre corridas? La búsqueda diaria actual ya funciona como una automatización independiente en ChatGPT.
3. ¿Cuál es el recorrido real de una candidatura en Banco de Chile? Identificar inicio de sesión, campos obligatorios, documentos, vista previa y señal de confirmación antes de diseñar el envío.
4. ¿Cuánto mejora el flujo? Medir cobertura de fichas completas, requisitos extraídos correctamente, correcciones necesarias y tiempo de preparación comparado con una candidatura manual.

## Ejemplo de principio a fin

Usar como referencia la ficha pública de Itaú «Analista Inteligencia Cobranza». Para probar el comportamiento, usar un perfil ficticio con automatización de validaciones en Python, SQL Server listado sin un proyecto asociado y experiencia operativa sin duración acreditada en cobranza.

| Dato de la ficha | Salida esperada |
|---|---|
| «Manejo de SQL Server» | Obligatorio. Pendiente de confirmar con un ejemplo de uso. |
| «Conocimientos de Python (deseable)» | Deseable. Respaldado por el ejemplo de automatización de validaciones. |
| «Experiencia de al menos 2 años en funciones similares» | Obligatorio. Pendiente de confirmar con fechas y funciones comparables. |
| «Dominio avanzado de Excel» | Obligatorio. Pendiente de confirmar si el perfil no aporta evidencia del nivel. |

Al recomendar una versión, explicar qué experiencia específica quedaría más visible. Si hay empate entre dos versiones o la evidencia es insuficiente, presentar las opciones sin asignar un ganador. Una recomendación de CV tampoco certifica que se cumplan los requisitos de la vacante.

## Prueba de integración para el piloto

1. Elegir Bci o LATAM y anotar la URL oficial, la fecha de la prueba y el método de lectura. Verificar un listado y al menos una ficha individual nueva. Registrar si el listado aporta solo títulos y si la ficha aporta requisitos suficientes.
2. Importar la misma ficha dos veces. Comprobar que conserva un solo registro. Si se modifica un campo en el ejemplo de prueba, verificar que se actualiza la fila y conserva su primera fecha de detección.
3. Comparar la extracción con una revisión manual de la ficha. Registrar requisitos omitidos, clasificación incorrecta y afirmaciones sin evidencia. La revisión manual sirve como referencia de evaluación.
4. Elegir un PDF distinto al recomendado. Verificar que el historial distingue ambos y conserva la huella del archivo elegido.
5. Simular un listado sin fichas, una ficha sin descripción y un fallo de acceso. Mostrar el motivo de cada caso y preservar los datos importados en corridas anteriores.

## Decisiones técnicas para tomar en conjunto

- **Fuentes.** Comparar lectura directa, navegador estándar y proveedor externo autorizado para cada portal. Registrar cobertura, facilidad de mantenimiento, costo y si entrega fichas completas. Una importación manual permite probar el procesamiento mientras se valida el acceso en vivo.
- **Interfaz.** Para el piloto sirve una salida de terminal con evidencias. Para la revisión de una candidatura, evaluar una vista que reúna el PDF, las respuestas y la aprobación.
- **IA y ranking.** Primero medir qué cubren las reglas. Registrar por separado interés por la oferta y elección de CV. Usar IA generativa en pasos que requieran interpretación o redacción y revisar su salida contra la fuente. El modelo de ranking se evalúa después con ejemplos etiquetados y una muestra reservada.
- **Envío verificado.** En la prueba de formulario, documentar cómo se identifica un envío exitoso y cómo se evita repetir una candidatura si se corta la conexión. Validar este recorrido antes de habilitarlo en un portal real.
