# 009 — Evaluación: cobertura, extracción, tiempo y ranking aprendido

Status: in-progress | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "Evaluación: métricas de cobertura/extracción/tiempo y ranking aprendido vs reglas con muestra reservada."
Relates: REQUERIMIENTOS.md (P3, pregunta 4, «IA y ranking», paso 3 de «Prueba de integración»), 002 (reglas), 005
(candidaturas), 007 (cobertura por fuente)

Nivel de proceso: 3 — comportamiento nuevo acotado a un módulo de evaluación que solo lee la base y escribe un reporte;
es reversible y no toca portales ni envíos. Usa etiquetas de interés de Ayelén (dato personal), lo que fuerza ≥ 3.
Mini-spec en un solo archivo.

## Goal
Un comando produce un reporte con: cobertura de fichas completas por fuente, calidad de extracción de requisitos contra
una revisión manual, tiempo de preparación por candidatura y, si hay suficientes ofertas etiquetadas, la comparación del
orden por reglas contra un ranking aprendido sobre una muestra reservada.

## Scenarios
### S1 — Calidad de extracción (P1)
Given fichas revisadas a mano (requisitos esperados con su tipo), when se ejecuta `python -m asistente.evaluacion`, then el
reporte muestra requisitos omitidos, tipo incorrecto y afirmaciones sin evidencia, por ficha y en total.
### S2 — Ranking con datos suficientes (P2)
Given ≥60 ofertas etiquetadas por Ayelén (≥15 «me interesa» y ≥15 «no me interesa»), when se evalúa, then se entrena con
las más antiguas, se reserva el 25 % más reciente por fecha de detección y se informa precisión@5 de reglas y del modelo
sobre la muestra reservada.
### S3 — Datos insuficientes (P1)
Given menos etiquetas que el mínimo, when se evalúa, then el reporte dice cuántas faltan y no entrena nada.

## Requirements
- R1: THE SYSTEM SHALL leer etiquetas de interés y revisiones manuales desde `privado/evaluacion/` (fuera del repo):
  `interes.jsonl` (`fuente`, `id_origen`, `interes` sí/no) y `revision.jsonl` (`fuente`, `id_origen`, requisitos
  esperados con `cita` y `tipo`).
- R2: THE SYSTEM SHALL calcular cobertura (completas / total por fuente), omitidos, tipo incorrecto y sin evidencia
  comparando por cita normalizada (minúsculas, espacios colapsados).
- R3: THE SYSTEM SHALL calcular el tiempo de preparación como la diferencia entre la creación de la candidatura y su
  aprobación (`candidatura_eventos` de 005) y mostrar mediana por fuente.
- R4: WHEN hay datos suficientes THE SYSTEM SHALL separar la muestra reservada por fecha de detección (sin mezclar) y
  no usarla para entrenar.
- R5: WHEN faltan datos THE SYSTEM SHALL informar cuántos faltan y no entrenar.
- R6: THE SYSTEM SHALL guardar el reporte en `privado/evaluacion/reporte-AAAA-MM-DD.md` y mostrarlo; `--json` para
  máquinas.

## Acceptance
- AC1 (R2, S1): con una revisión ficticia, el reporte cuenta 1 omitido, 1 tipo incorrecto y 1 sin evidencia — check:
  `pytest tests/test_evaluacion.py -k extraccion`
- AC2 (R2): cobertura por fuente sobre una base de prueba — check: `pytest tests/test_evaluacion.py -k cobertura`
- AC3 (R3): mediana de tiempo de preparación con eventos ficticios — check: `pytest tests/test_evaluacion.py -k tiempo`
- AC4 (R4, S2): con 80 etiquetas ficticias, ninguna oferta reservada aparece en el entrenamiento y el reporte trae
  precisión@5 de reglas y modelo — check: `pytest tests/test_evaluacion.py -k reservada`
- AC5 (R5, S3, negativo): con 20 etiquetas el reporte dice cuántas faltan y no entrena — check:
  `pytest tests/test_evaluacion.py -k insuficientes`
- AC6 (R1, negativo): sin `privado/evaluacion/` el comando explica qué archivos crear y sale con código 0 — check:
  `pytest tests/test_evaluacion.py -k sin_archivos`
- AC7 (manual): primer reporte real con las etiquetas de Ayelén — check: observación en `## Verify` (fecha, cantidad de
  etiquetas, métricas principales), sin copiar ofertas ni etiquetas.

## Edge cases
- Una etiqueta apunta a una oferta que no está en la base → se ignora y se cuenta como «sin oferta».
- Empate en el puntaje de reglas → orden estable por fecha de detección.

## Out of scope
- Usar el ranking aprendido para ordenar las ofertas en la app (solo se compara). Modelos externos o de pago.

## Method (locked)
`asistente/evaluacion.py` con la biblioteca estándar. Puntaje de reglas = señales del perfil que calzan con los
requisitos (como `app.recommend`). Modelo aprendido = Naive Bayes multinomial sobre palabras de cargo y descripción,
escrito a mano (sin dependencias nuevas), con suavizado de Laplace. Métrica principal precisión@5 en la muestra reservada;
también se informa cuántos «me interesa» quedan en el top 5 de cada método. Changing it requires a Change log line here.

## Decisions & assumptions
- El mínimo de 60 etiquetas (≥15 por clase) es un punto de partida para que la muestra reservada tenga ≥15 ofertas;
  se puede ajustar con una línea en Change log.
- Las etiquetas de interés son distintas de la elección de CV (REQUERIMIENTOS: «Mantener la decisión de interés por
  una oferta como un dato distinto de la elección de CV»).
- «Sin evidencia» = requisito extraído cuya cita no está en la revisión manual (la extracción afirma algo que la
  revisión no respalda). La extracción evaluada es la de `asistente.reglas` sobre la descripción guardada; las fichas
  pendientes de descripción cuentan como «sin oferta».

## Change log

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: decisión sobre el ranking — where: reporte de evaluación — when: cuando haya datos suficientes — success: el
  modelo supera a las reglas en precisión@5 por ≥0,2 en dos reportes seguidos (entonces se abre una spec para usarlo) —
  fail: no la supera (se sigue con reglas).

## Tasks
Toma una tarea marcándola `[~] (agente: nombre)`; una tarea por PR; `[x]` solo con la evidencia del `check:` en la PR.

- [x] T001 Lectura de archivos privados, cobertura y extracción — files: asistente/evaluacion.py,
  tests/test_evaluacion.py — check: AC1, AC2, AC6
- [ ] T002 Tiempo de preparación (requiere 005) — files: asistente/evaluacion.py, tests/test_evaluacion.py — check: AC3
- [x] T003 Ranking por reglas vs Naive Bayes con muestra reservada — files: asistente/evaluacion.py,
  tests/test_evaluacion.py — check: AC4, AC5
- [ ] T004 Primer reporte real con Ayelén y documentación — files: specs/009-evaluacion/spec.md, README.md — check: AC7

| AC | Task |
|---|---|
| AC1 | T001 |
| AC2 | T001 |
| AC3 | T002 |
| AC4 | T003 |
| AC5 | T003 |
| AC6 | T001 |
| AC7 | T004 |

## As-built
