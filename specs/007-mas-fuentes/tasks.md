# 007 — Tasks

Las tareas T002–T006 son independientes entre sí (una fuente por agente). Cada una empieza con el reconocimiento
anotado en Decisions. Si una fuente resulta «no accesible» (R4), su tarea se cierra con ese reconocimiento y la prueba
del fallo registrado (AC4); su AC3 queda «no aplica» con el motivo. Toma una tarea marcándola `[~] (agente: nombre)`; una tarea por PR; `[x]` solo con la evidencia
del `check:` en la PR.

- [x] T001 Reporte de cobertura — files: asistente/cobertura.py, tests/test_cobertura.py — check: AC5, AC6
- [x] T002 Itaú al modelo común (migración + `save()` con `guardar()`; receta del relay si la lectura directa sigue en
  403) — files: itau.py, tests/test_itau.py, tests/test_fuentes.py, relay/recipes/itau_ofertas.json (opcional) —
  check: AC1, AC2, AC3 (itau), AC4 (itau), AC7
- [x] T003 Banco de Chile (listado y fichas) — files: asistente/bancochile.py o receta, tests/test_fuentes.py,
  tests/fixtures/bancochile/* — check: AC3 (bancochile), AC4 (bancochile), AC7
- [x] T004 SKY — files: asistente/sky.py o receta, tests/test_fuentes.py, tests/fixtures/sky/* — check: AC3 (sky),
  AC4 (sky), AC7
- [x] T005 Caja Los Andes — files: asistente/cajalosandes.py o receta, tests/test_fuentes.py,
  tests/fixtures/cajalosandes/* — check: AC3 (cajalosandes), AC4 (cajalosandes), AC7
- [ ] T006 Coopeuch — files: asistente/coopeuch.py o receta, tests/test_fuentes.py, tests/fixtures/coopeuch/* —
  check: AC3 (coopeuch), AC4 (coopeuch), AC7
- [ ] T007 Corrida en vivo de las fuentes accesibles y reporte en Verify; README — files: specs/007-mas-fuentes/spec.md,
  README.md, REQUERIMIENTOS.md — check: AC8

| AC | Task |
|---|---|
| AC1 | T002 |
| AC2 | T002 |
| AC3 | T002, T003, T004, T005, T006 |
| AC4 | T002, T003, T004, T005, T006 |
| AC5 | T001 |
| AC6 | T001 |
| AC7 | T002, T003, T004, T005, T006 |
| AC8 | T007 |
