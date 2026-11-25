# 005 — Candidatura con estados y aprobación ligada a la huella del contenido

Status: verifying | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "Flujo de candidatura con estados (borrador → listo → aprobado → enviado → por verificar) y aprobación ligada
al hash del contenido."
Relates: REQUERIMIENTOS.md (flujo 4 y 5, criterio «Se modifica una candidatura aprobada…», «Candidatura» en Datos),
002 (ofertas), 001 (aprobaciones por huella del relay)

Nivel de proceso: 4 — define el modelo que controla qué se envía (regla no negociable de AGENTS.md), guarda datos
personales (respuestas, CV elegido) y crea un formato público (tabla `candidaturas`). Un error aquí permite un envío no
aprobado, que no se puede deshacer.

## Goal
Cada candidatura vincula una oferta, el PDF exacto, las respuestas y un estado. La aprobación vale solo para la huella
SHA-256 del contenido aprobado: cualquier cambio vuelve a «listo» y exige aprobar de nuevo. Un envío incierto queda
«por verificar» y bloquea reintentos hasta comprobarlo.

## Scenarios
### S1 — Preparar y aprobar (P1)
Given una oferta guardada y un CV elegido, when Ayelén crea la candidatura, completa las respuestas y la marca lista,
then ve destino, cargo, archivo y respuestas con su huella; al aprobar, queda «aprobado» con fecha y esa huella.
### S2 — Cambio después de aprobar (P1)
Given una candidatura «aprobado», when cambia una respuesta, el PDF o el destino, then vuelve a «listo», la aprobación
anterior queda en el historial y no se puede enviar hasta aprobar la huella nueva.
### S3 — Envío incierto (P1)
Given una candidatura «aprobado», when el envío se corta sin confirmación, then queda «por verificar»; un nuevo intento
se rechaza hasta que Ayelén indique «enviado» (con comprobante si existe) o «no enviado» (vuelve a «aprobado»).

## Requirements
- R1: THE SYSTEM SHALL guardar candidaturas con oferta (`fuente`, `id_origen`), destino (URL de postulación), cv
  (versión, archivo, sha256 del PDF), respuestas (JSON), estado, huella, aprobada_en, enviada_en, comprobante.
- R2: THE SYSTEM SHALL calcular la huella como SHA-256 del JSON canónico (claves ordenadas, UTF-8, sin espacios) de
  destino, cargo, sha256 del PDF y respuestas.
- R3: THE SYSTEM SHALL permitir solo estas transiciones: borrador→listo, listo→aprobado, aprobado→enviado,
  aprobado→por verificar, por verificar→enviado, por verificar→aprobado, y listo/aprobado→listo al cambiar el contenido.
- R4: WHEN se aprueba THE SYSTEM SHALL exigir la huella que la persona vio y rechazar si no coincide con la actual.
- R5: WHEN cambia el contenido de una candidatura «aprobado» THE SYSTEM SHALL volver a «listo» y conservar la
  aprobación anterior en un historial.
- R6: WHEN una candidatura está «por verificar» THE SYSTEM SHALL rechazar cualquier intento de envío.
- R7: THE SYSTEM SHALL marcar como pendientes las respuestas vacías o con `{pendiente}` y no permitir pasar a «listo».
- R8: THE SYSTEM SHALL registrar cada transición (estado anterior, nuevo, fecha, huella, motivo) en `candidatura_eventos`.

## Acceptance
- AC1 (R1, R2, S1): crear, completar y aprobar deja «aprobado» con la huella calculada — check:
  `pytest tests/test_candidaturas.py -k aprobar`
- AC2 (R4, negativo): aprobar con una huella distinta a la actual se rechaza y el estado no cambia — check:
  `pytest tests/test_candidaturas.py -k huella_distinta`
- AC3 (R5, S2): cambiar una respuesta o el PDF tras aprobar vuelve a «listo» y deja la aprobación en el historial —
  check: `pytest tests/test_candidaturas.py -k cambio`
- AC4 (R3, negativo): una transición no permitida (borrador→enviado, listo→enviado) se rechaza — check:
  `pytest tests/test_candidaturas.py -k transicion`
- AC5 (R6, S3, negativo): con «por verificar», un intento de envío se rechaza; tras «no enviado» vuelve a «aprobado» —
  check: `pytest tests/test_candidaturas.py -k por_verificar`
- AC6 (R7, negativo): una respuesta pendiente impide pasar a «listo» y se lista como pendiente — check:
  `pytest tests/test_candidaturas.py -k pendiente`
- AC7 (R8): cada transición queda en `candidatura_eventos` — check: `pytest tests/test_candidaturas.py -k eventos`
- AC8 (S1): la CLI recorre crear → listo → aprobar → enviado con el perfil ficticio — check:
  `pytest tests/test_candidaturas.py -k cli`

## Edge cases
- Dos candidaturas para la misma oferta → se permite solo una activa (no «enviado»); la segunda se rechaza.
- El PDF elegido cambia en disco sin cambiar el nombre → la huella cambia porque usa el sha256 del archivo.
- La oferta pasa a «pendiente de descripción» → la candidatura sigue; la vista lo advierte (006).

## Out of scope
- Enviar a un portal real (lo hará una receta del relay en otra spec, usando esta tabla). La vista web (006).
- Seguimiento por correo (008).

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- «Enviado» lo marca la persona o una receta del relay que recibió la confirmación del portal; esta spec no envía.
- La tabla `decisiones` de `app.py` sigue igual: registra recomendación y elección de CV; la candidatura apunta a la
  decisión que eligió el CV.

## Change log

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: candidaturas que vuelven de «aprobado» a «listo» — where: `candidatura_eventos` — when: +14 días de uso —
  success: se registran y ninguna llega a «enviado» sin aprobación de su huella final — fail: cualquier envío con huella
  distinta a la aprobada.
- O2: candidaturas «por verificar» abiertas más de 3 días — where: `candidaturas` — when: +14 días — success: 0 — fail: ≥1.

## As-built
