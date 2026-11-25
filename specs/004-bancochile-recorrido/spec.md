# 004 — Recorrido real de postulación en Banco de Chile (solo reconocimiento)

Status: in-progress | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "Recorrido real de postulación en Banco de Chile (solo reconocimiento y documentación, sin enviar)."
Relates: REQUERIMIENTOS.md (flujo 4, P2, pregunta 3 de la revisión técnica), 001 (relay), 005 (estados de candidatura)

Nivel de proceso: 3 — toca un portal real con la sesión de Ayelén (forzado ≥ 3), pero solo produce documentación: no hay
código de envío y nada es irreversible si se respeta la regla de no enviar. Mini-spec en un solo archivo.

## Goal
Documentar, con Ayelén manejando su propio Chrome, cómo es una postulación en el portal de empleos de Banco de Chile:
inicio de sesión, pasos, campos obligatorios, documentos, vista previa y señal de confirmación, para diseñar después la
receta de envío. No se envía ninguna postulación.

## Scenarios
### S1 — Recorrer hasta antes de enviar (P1)
Given Ayelén con sesión iniciada por ella en el portal de Banco de Chile, when recorre una oferta real hasta la última
pantalla antes de «Enviar», then queda documentado cada paso con sus campos, validaciones y documentos, sin pulsar «Enviar».
### S2 — Señal de confirmación (P1)
Given que no se envía nada, when se documenta la confirmación, then se registra cómo se reconoce un envío exitoso según
lo que el portal muestra o publica (ayuda, preguntas frecuentes, correos de ejemplo de postulaciones anteriores de
Ayelén si ella los comparte), marcando qué es observado y qué es supuesto.

## Requirements
- R1: THE SYSTEM SHALL tener `docs/portales/banco-de-chile.md` con las secciones: URL y fecha, robots.txt y términos,
  inicio de sesión, pasos, campos obligatorios, documentos, vista previa, confirmación, duplicados y reintentos,
  bloqueos o CAPTCHA observados, propuesta de receta.
- R2: THE SYSTEM SHALL separar en cada sección lo observado (con fecha) de lo supuesto.
- R3: THE SYSTEM SHALL no contener datos personales (RUT, correos, teléfonos, direcciones) ni capturas con ellos.
- R4: WHEN el portal muestra CAPTCHA o verificación THE SYSTEM SHALL documentarlo y no buscar cómo evitarlo.

## Acceptance
- AC1 (R1, R2): el documento tiene todas las secciones y cada una marca «Observado (fecha)» o «Supuesto» — check:
  `pytest tests/test_docs_portales.py -k secciones`
- AC2 (R3, negativo): un documento con un RUT o un correo hace fallar la prueba; el documento real la pasa — check:
  `pytest tests/test_docs_portales.py -k datos_personales`
- AC3 (S1, manual): recorrido real hasta la pantalla previa al envío, sin enviar — check: observación anotada en
  `## Verify` (fecha, oferta usada, último paso alcanzado, confirmación de Ayelén de que no se envió).

## Edge cases
- La oferta exige preguntas propias → se documentan los tipos de pregunta, no las respuestas de Ayelén.
- El portal guarda borradores automáticamente → se documenta, porque cambia cómo se evitan duplicados.
- El portal es de un proveedor externo (otro dominio) → se anota el dominio, su robots.txt y sus términos.

## Out of scope
- Escribir la receta de envío o pulsar «Enviar». Automatizar el inicio de sesión. Guardar capturas con datos reales.

## Method (locked)
Sesión guiada: Ayelén maneja su Chrome; el agente anota. Capturas solo si se recortan o tapan los datos personales
(van en `docs/portales/img/`). La prueba `tests/test_docs_portales.py` revisa secciones y busca patrones de RUT
(`\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]`), correo y teléfono chileno. Changing it requires a Change log line here.

## Decisions & assumptions
- La URL del portal no está verificada; se registra en el documento al iniciar el recorrido.

## Change log

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: la spec de envío para Banco de Chile se puede escribir solo con este documento — where: revisión de la spec
  siguiente — when: al redactarla — success: sin preguntas abiertas sobre campos o confirmación — fail: hace falta un
  segundo recorrido.

## Tasks
- [x] T001 Prueba de documentos de portales (secciones + datos personales, con un ejemplo negativo) — files:
  tests/test_docs_portales.py — check: AC1, AC2 (con un documento de ejemplo)
- [ ] T002 Recorrido con Ayelén y documento — files: docs/portales/banco-de-chile.md, docs/portales/img/* — check:
  AC1, AC2, AC3

| AC | Task |
|---|---|
| AC1 | T001, T002 |
| AC2 | T001, T002 |
| AC3 | T002 |

## As-built
