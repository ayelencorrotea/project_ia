# 007 — Más fuentes con cobertura medida

Status: in-progress | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "Más fuentes (Itaú vía relay, Banco de Chile, SKY, Caja Los Andes, Coopeuch) con cobertura medida."
Relates: REQUERIMIENTOS.md (flujo 1, P0 y P3, «Fuentes» en Decisiones técnicas, pregunta 1), 001 (relay), 002 (modelo
común), 003 (calibrar recetas)

Nivel de proceso: 4 — cinco portales nuevos (forzado ≥ 3), cada uno con acceso desconocido hoy, y un cambio de formato
público (Itaú pasa de `ofertas_itau` a la tabla común). Cada fuente es una tarea independiente del tamaño de un agente.

## Goal
Cada empleador de la lista entrega ofertas a la tabla común `ofertas` por el método permitido más simple (lectura
directa, receta del relay o importación manual), con su método, fecha y límites anotados, y un reporte muestra por
fuente cuántas ofertas hay, cuántas con ficha completa y el último fallo.

## Scenarios
### S1 — Reconocer una fuente (P1)
Given un empleador nuevo, when se revisa su portal de empleos, then queda anotado en Decisions: URL oficial, fecha,
robots.txt, términos, si el listado y las fichas se leen sin navegador, con navegador o no se pueden leer, y el método
elegido.
### S2 — Importar una fuente (P1)
Given el método elegido, when se importa, then las ofertas quedan en `ofertas` con la `fuente` del empleador y las
reglas de 002; un rechazo queda en `fallos` y las otras fuentes siguen.
### S3 — Medir cobertura (P1)
Given varias fuentes importadas, when se ejecuta `python -m asistente.cobertura`, then se ve por fuente: ofertas,
completas, pendientes, % completas, última importación y último fallo.

## Requirements
- R1: THE SYSTEM SHALL elegir por fuente el primer método permitido en este orden: API o HTML público con `urllib`
  (como `asistente/bci.py`), receta del relay en el Chrome de la persona (como 003), importación de HTML guardado.
  Nunca evasión de bloqueos.
- R2: THE SYSTEM SHALL guardar cada fuente en `ofertas` con un valor `fuente` estable (`itau`, `bancochile`, `sky`,
  `cajalosandes`, `coopeuch`) y las reglas de 002.
- R3: THE SYSTEM SHALL migrar Itaú a `ofertas` conservando las filas de `ofertas_itau` existentes (migración idempotente)
  y dejar de escribir en `ofertas_itau`.
- R4: WHEN una fuente no se puede leer con un método permitido THE SYSTEM SHALL registrarlo como «no accesible» con
  motivo y fecha en Decisions y en `fallos`, sin bloquear las demás.
- R5: THE SYSTEM SHALL entregar un reporte de cobertura por fuente (texto y `--json`).

## Acceptance
- AC1 (R2, R3): la migración pasa las filas de `ofertas_itau` a `ofertas` con `fuente='itau'` y una segunda ejecución
  no duplica — check: `pytest tests/test_itau.py -k migrar`
- AC2 (R3, negativo): con `ofertas_itau` vacía o inexistente la migración no falla ni crea filas — check:
  `pytest tests/test_itau.py -k migrar_vacia`
- AC3 (R1, R2): por cada fuente implementada, el listado y una ficha grabados producen filas completas — check:
  `pytest tests/test_fuentes.py -k <fuente>` (una prueba por fuente: `itau`, `bancochile`, `sky`, `cajalosandes`, `coopeuch`)
- AC4 (R4, negativo): por cada fuente, un 403 grabado deja un fallo con código y motivo y conserva las filas previas —
  check: `pytest tests/test_fuentes.py -k "<fuente> and refused"`
- AC5 (R5): el reporte cuenta ofertas, completas y pendientes por fuente sobre una base de prueba — check:
  `pytest tests/test_cobertura.py`
- AC6 (R5, negativo): con una base sin ofertas el reporte dice «sin datos» y sale con código 0 — check:
  `pytest tests/test_cobertura.py -k vacia`
- AC7 (S1, manual): cada fuente tiene su reconocimiento anotado (URL, fecha, robots.txt, método) — check: revisión de
  `## Decisions & assumptions` en la PR de esa fuente.
- AC8 (S3, manual): corrida en vivo de todas las fuentes accesibles con el reporte pegado en `## Verify` — check:
  observación con fecha.

## Edge cases
- Una fuente publica en un sistema de reclutamiento externo compartido por varias empresas → `fuente` es el empleador;
  el enlace oficial es el del sistema externo.
- Una misma oferta aparece en dos fuentes → no se combinan en esta spec; se anota para una spec de coincidencias.
- Itaú responde 403 a la lectura directa (observado antes) → se usa receta del relay o HTML guardado, como indica R1.

## Out of scope
- Coincidencias entre fuentes (enlace común o revisión). Fuentes fuera de la lista. Postular.

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- Itaú: `itau.py` ya lee listado y fichas HTML; la lectura directa recibió HTTP 403 desde un servidor (observado
  antes de 2026-11-24). El reconocimiento de cada fuente se anota aquí al tomar su tarea, con este formato:
  `- <fuente> (AAAA-MM-DD): URL · robots.txt · términos · listado/ficha sin navegador sí/no · método elegido · motivo`.

- Itaú (2026-11-24, Chile). `https://trabajaenitau.cl/search` respondió HTTP 403 desde el entorno de trabajo.
  `robots.txt` respondió HTTP 200 y no excluye `/search` ni las fichas públicas. El rechazo impidió revisar los
  términos desde el listado y se detuvo la consulta de fichas. Se mantiene la importación de HTML guardado,
  verificada con copias de prueba del listado y de una ficha. El método directo queda registrado como no accesible
  desde este entorno.

- Banco de Chile (2026-11-24, Chile). [Portal](https://bancodechile.trabajando.cl/) ·
  [robots.txt](https://bancodechile.trabajando.cl/robots.txt) (HTTP 200, excluye ChatGPT-User) ·
  [términos](https://bancodechile.trabajando.cl/terminos-y-condiciones) (restringen agentes de búsqueda y copia).
  El listado inicial muestra la estructura de la página, sin fichas en el HTML observado. Sin método de
  importación autorizado verificado. AC3 no aplica. La prueba de AC4 registra el motivo de la limitación,
  sin inventar un código HTTP, y comprueba que conserva las ofertas previas.

- SKY (2026-11-24, Chile). El HTML inicial del [portal](https://www.skyairline.com/es/chile/skyers/jobsearch) pide JavaScript. La ruta [robots.txt](https://www.skyairline.com/robots.txt) devolvió HTTP 200 con HTML en vez de reglas. Se identificó una ficha pública indexada, sin verificar extracción de requisitos ni términos aplicables a una integración. Sin API pública o captura autorizada verificada. AC3 no aplica. AC4 comprueba que la limitación se registra y conserva las ofertas previas.

- Caja Los Andes (2026-11-24, Chile). El [portal](https://cajalosandes.trabajando.cl/) presenta el título del listado sin fichas en el HTML observado. [robots.txt](https://cajalosandes.trabajando.cl/robots.txt) respondió HTTP 200 y excluye ChatGPT-User. Sus [términos](https://cajalosandes.trabajando.cl/terminos-y-condiciones) restringen agentes de búsqueda y copia. Sin método autorizado verificado. AC3 no aplica. AC4 comprueba que la limitación se registra y conserva las ofertas previas.

## Change log

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: % de fichas completas por fuente — where: `python -m asistente.cobertura --json` — when: +7 días de uso —
  success: ≥80 % en cada fuente accesible — fail: <50 % en alguna (revisar extracción o método).
- O2: fallos de acceso por fuente — where: `fallos` — when: +7 días — success: 0 rechazos 403/429 — fail: cualquiera
  (pausar esa fuente y revisar términos y ritmo).

## As-built
