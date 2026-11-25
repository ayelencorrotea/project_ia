# 006 — Vista de revisión: PDF, respuestas y aprobar

Status: verifying | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "Vista de revisión (PDF + respuestas + aprobar)."
Relates: REQUERIMIENTOS.md (flujo 2–4, P1 y P2, «Interfaz» en Decisiones técnicas), 005 (candidaturas y huella)

Nivel de proceso: 4 — es la pantalla donde Ayelén aprueba lo que se enviará (la usa ella), muestra datos personales
(CV, respuestas) y es la puerta de la aprobación por huella. Un error de la vista puede aprobar un contenido distinto al
que ella vio.

## Goal
Una página local en `127.0.0.1` muestra, para una candidatura, la oferta (cargo, empresa, enlace), los requisitos con
cita y evidencia, el PDF exacto embebido, el destino, las respuestas y los pendientes, y un botón «Aprobar» que aprueba
solo la huella que se mostró.

## Scenarios
### S1 — Revisar y aprobar (P1)
Given una candidatura «listo», when Ayelén abre `http://127.0.0.1:8770/candidatura/<id>`, then ve oferta, requisitos con
cita y evidencia, el PDF, destino, respuestas y la huella; al pulsar «Aprobar» la candidatura queda «aprobado».
### S2 — Contenido cambió mientras miraba (P1)
Given la vista abierta con la huella H1, when otra acción cambia una respuesta (huella H2) y Ayelén pulsa «Aprobar»,
then la aprobación se rechaza con «el contenido cambió, revisa de nuevo» y la página muestra el contenido nuevo.
### S3 — Elegir otro CV (P1)
Given la vista, when Ayelén elige otra versión de CV, then se previsualiza ese PDF, la decisión se registra (tabla
`decisiones`) y la candidatura vuelve a «listo» con la huella nueva.

## Requirements
- R1: THE SYSTEM SHALL servir la vista solo en `127.0.0.1` y rechazar peticiones cuyo `Host` no sea local.
- R2: THE SYSTEM SHALL mostrar oferta, requisitos (tipo, cita literal, evidencia o «pendiente»), PDF, destino,
  respuestas, pendientes, estado y huella.
- R3: WHEN se pulsa «Aprobar» THE SYSTEM SHALL enviar la huella mostrada y aprobar solo si coincide con la actual (005 R4).
- R4: THE SYSTEM SHALL exigir un token de formulario por sesión (contra peticiones de otras páginas) en toda acción POST.
- R5: THE SYSTEM SHALL servir solo PDFs de la lista de versiones de CV configurada; nunca rutas arbitrarias.
- R6: THE SYSTEM SHALL verse bien en pantallas angostas (móvil) y respetar el modo claro u oscuro del sistema.
- R7: WHEN una respuesta está pendiente THE SYSTEM SHALL resaltarla y deshabilitar «Aprobar».

## Acceptance
- AC1 (R2, S1): la página de una candidatura ficticia contiene cargo, cita literal, nombre del PDF, respuestas y huella —
  check: `pytest tests/test_revision.py -k muestra`
- AC2 (R3, S1): POST de aprobación con la huella actual deja «aprobado» — check: `pytest tests/test_revision.py -k aprobar`
- AC3 (R3, S2, negativo): POST con una huella anterior responde 409 y el estado no cambia — check:
  `pytest tests/test_revision.py -k huella_vieja`
- AC4 (R4, negativo): POST sin token o con token inválido responde 403 — check: `pytest tests/test_revision.py -k token`
- AC5 (R5, negativo): pedir `/pdf/../../etc/passwd` o un PDF fuera de la lista responde 404 — check:
  `pytest tests/test_revision.py -k pdf_ruta`
- AC6 (R1, negativo): una petición con `Host: ejemplo.com` responde 403 — check: `pytest tests/test_revision.py -k host`
- AC7 (S3): elegir otro CV registra la decisión y vuelve a «listo» con huella nueva — check:
  `pytest tests/test_revision.py -k otro_cv`
- AC8 (R7, negativo): con una respuesta pendiente el botón «Aprobar» sale deshabilitado y el POST se rechaza — check:
  `pytest tests/test_revision.py -k pendiente`
- AC9 (R6, manual): la página se lee en 375 px de ancho y en modo oscuro — check: observación anotada en `## Verify`
  (navegador, ancho, modo, captura con datos ficticios).

## Edge cases
- PDF eliminado del disco → la vista lo indica y no permite aprobar.
- Candidatura «enviado» o «por verificar» → vista de solo lectura, sin botón «Aprobar».
- Dos pestañas abiertas → la segunda aprobación con la misma huella no cambia nada (ya está aprobada).

## Out of scope
- Editar respuestas en la vista (se hace con la CLI de 005; puede venir en otra spec). Enviar al portal.
- Acceso desde otra máquina o desde el celular por red; cuentas o contraseñas.

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- Puerto por defecto 8770 (el relay usa 8765). Se puede cambiar con `--puerto`.
- Los requisitos se muestran desde la ejecución de reglas guardada en `decisiones.requisitos`.

## Change log

## Verify
- AC9, 24 de noviembre de 2026 (Chile). Chromium 156.0.8078.79 a 375 × 812 px con datos ficticios.
  Se comprobó que la página no producía desplazamiento horizontal en modo oscuro, que el PDF se cargó,
  que el cambio de CV y la aprobación funcionaron y que se aplicó el fondo claro al cambiar el modo.
  [Captura en modo oscuro](verificacion-movil.png).

Verdict: verificado en la rama de T003, pendiente de integración.

## Observe (define now, read after ship)
- O1: candidaturas aprobadas desde la vista — where: `candidatura_eventos` (motivo «vista») — when: +14 días — success:
  ≥1 aprobación y 0 aprobaciones rechazadas por huella sin explicación — fail: Ayelén vuelve a revisar en otra
  herramienta porque la vista no muestra algo.
- O2: tiempo de revisión por candidatura — where: Ayelén (registro de 009) — when: +14 días — success: ≤5 min —
  fail: >15 min.

## As-built
