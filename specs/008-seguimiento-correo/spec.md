# 008 — Seguimiento por correo (opcional, solo lectura)

Status: in-progress | Phase: solid | Domain: code | Created: 2026-11-24 | Base commit: 910e767
Request: "Seguimiento por correo (opcional, solo lectura)."
Relates: REQUERIMIENTOS.md (flujo 5, P3), 005 (candidaturas y estados)

Nivel de proceso: 4 — procesa correos personales de Ayelén (datos personales, forzado ≥ 3) y asocia mensajes con
candidaturas, lo que puede influir en el estado de un envío. Poco entendido aún: el formato de los correos de cada
portal no se conoce.

## Goal
A partir de correos que Ayelén exporta ella misma (archivos `.eml` o `.mbox`), el asistente reconoce confirmaciones de
postulación, citaciones a entrevista y rechazos, y los asocia como eventos a una candidatura existente. Solo lee: no
envía, no borra, no se conecta a la cuenta de correo y no cambia estados sin que Ayelén lo confirme.

## Scenarios
### S1 — Confirmación de una candidatura por verificar (P1)
Given una candidatura «por verificar» de Bci y un correo exportado de confirmación de Bci para ese cargo, when se ejecuta
`python -m asistente.correo importar <carpeta>`, then se crea un evento «confirmación» ligado a esa candidatura y se
propone pasar a «enviado» con el correo como comprobante; el cambio ocurre solo cuando Ayelén lo confirma.
### S2 — Correo ambiguo (P1)
Given un correo que podría corresponder a dos candidaturas (misma empresa, cargos parecidos), when se importa, then queda
«por revisar» con las candidatas y no se asocia solo.
### S3 — Correo no relacionado (P2)
Given un correo que no menciona una empresa con candidaturas, when se importa, then se ignora y no se guarda su contenido.

## Requirements
- R1: THE SYSTEM SHALL leer solo archivos `.eml` y `.mbox` locales indicados por la persona; nunca se conecta a un
  servidor de correo ni guarda credenciales.
- R2: THE SYSTEM SHALL clasificar cada correo como `confirmacion`, `entrevista`, `rechazo` u `otro` con reglas
  (remitente, asunto, frases) y guardar la frase que justificó la clase como cita literal.
- R3: THE SYSTEM SHALL asociar un correo a una candidatura solo si coincide la empresa y el cargo o el ID de origen;
  si hay más de una candidata, queda «por revisar».
- R4: THE SYSTEM SHALL guardar de cada correo asociado solo: fecha, remitente, asunto, clase, cita y huella del archivo;
  nunca el cuerpo completo ni adjuntos.
- R5: WHEN un correo confirma una candidatura THE SYSTEM SHALL proponer el cambio de estado y aplicarlo solo con la
  confirmación de la persona (`python -m asistente.correo confirmar <evento>`).
- R6: THE SYSTEM SHALL no reprocesar un correo ya importado (misma huella).

## Acceptance
- AC1 (R2, R3, S1): un `.eml` ficticio de confirmación de Bci se asocia a la candidatura correcta con clase y cita —
  check: `pytest tests/test_correo.py -k confirmacion`
- AC2 (R5, negativo): importar no cambia el estado de la candidatura; `confirmar` sí, y deja el comprobante — check:
  `pytest tests/test_correo.py -k confirmar`
- AC3 (R3, S2, negativo): un correo que calza con dos candidaturas queda «por revisar» sin asociarse — check:
  `pytest tests/test_correo.py -k ambiguo`
- AC4 (R4, negativo): después de importar, la base no contiene el cuerpo del correo (se busca una frase del cuerpo que
  no es la cita) — check: `pytest tests/test_correo.py -k sin_cuerpo`
- AC5 (S3): un correo sin empresa conocida no deja filas — check: `pytest tests/test_correo.py -k no_relacionado`
- AC6 (R6): importar la misma carpeta dos veces no duplica eventos — check: `pytest tests/test_correo.py -k reimportar`
- AC7 (R2): entrevista y rechazo se clasifican con su cita — check: `pytest tests/test_correo.py -k "entrevista or rechazo"`
- AC8 (manual): con correos reales exportados por Ayelén, la clasificación se revisa a mano — check: observación en
  `## Verify` (cantidad, aciertos, errores), sin copiar contenido de los correos.

## Edge cases
- Correo en HTML sin texto plano → se convierte a texto con la biblioteca estándar antes de clasificar.
- Codificaciones distintas (ISO-8859-1) → `email` con `policy=default` decodifica; si falla, el correo queda «otro».
- Correo reenviado por Ayelén → se usa la fecha y el remitente originales si están en el cuerpo; si no, «por revisar».

## Out of scope
- Conectarse por IMAP o a la API de un proveedor de correo; responder o archivar correos; adjuntos.

## Method (locked)
See plan.md → Approach. Changing it requires a Change log line here.

## Decisions & assumptions
- Se elige importar archivos exportados en vez de IMAP para no manejar credenciales ni tokens (AGENTS.md). Si más
  adelante se quiere IMAP, va en otra spec de nivel 4.
- Los correos de prueba son ficticios y se escriben a mano en `tests/fixtures/correo/`.

## Change log
- 2026-11-25 (T001): `correo_eventos` agrega `candidatas` (lista JSON de IDs de candidatura) para que un correo
  «por revisar» conserve con qué candidaturas calzó (S2). La huella es la del mensaje (en un `.mbox`, cada mensaje):
  el mismo correo exportado como `.eml` y dentro de un `.mbox` se importa una vez. En T001 todo correo relacionado
  queda `por_revisar`; la asociación por cargo o ID llega en T002.
- 2026-11-25 (T002): `confirmar <evento> --candidatura <id>` resuelve un correo «por revisar» eligiendo una de sus
  candidatas (S2); sin `--candidatura` falla y no cambia nada. Un reenvío (asunto `RV:`, `Fwd:`…) toma remitente y
  fecha de las líneas `De:`/`Fecha:` del cuerpo; si falta alguno, queda «por revisar».

## Verify
Verdict: pending.

## Observe (define now, read after ship)
- O1: correos asociados correctamente — where: revisión de Ayelén de los eventos — when: tras la primera importación
  real — success: ≥90 % bien clasificados y 0 asociados a la candidatura equivocada — fail: cualquier asociación
  equivocada.

## As-built
