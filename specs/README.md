# Specs

Cada carpeta `NNN-slug/` describe un cambio con objetivo, criterios de aceptación verificables y tareas. Están escritas
para que una persona o un agente de código (Codex, Claude Code u otro) pueda tomar una sin contexto previo.

## Índice

| NNN | Título | Status | Fase | Nivel | Depende de |
|---|---|---|---|---|---|
| [001](001-browser-relay/spec.md) | Relay de navegador propio: recetas en el Chrome de la persona | done | P0 · P2 | 4 | — |
| [002](002-bci-p0/spec.md) | P0: lector público de Bci y modelo genérico de oferta | done | P0 | 4 | — |
| [003](003-latam-relay/spec.md) | Fichas de LATAM renderizadas vía relay en vivo | ready | P0 | 4 | 001 |
| [004](004-bancochile-recorrido/spec.md) | Recorrido real de postulación en Banco de Chile (solo reconocimiento) | ready | P2 | 3 | — |
| [005](005-candidatura-estados/spec.md) | Candidatura con estados y aprobación ligada a la huella del contenido | ready | P2 | 4 | 002 |
| [006](006-vista-revision/spec.md) | Vista de revisión: PDF, respuestas y aprobar | ready | P1 · P2 | 4 | 005 |
| [007](007-mas-fuentes/spec.md) | Más fuentes con cobertura medida | in-progress | P0 · P3 | 4 | 001, 002 |
| [008](008-seguimiento-correo/spec.md) | Seguimiento por correo (opcional, solo lectura) | ready | P3 | 4 | 005 |
| [009](009-evaluacion/spec.md) | Evaluación: cobertura, extracción, tiempo y ranking aprendido | in-progress | P3 | 3 | 002, 005 |

Status: `draft` (en redacción) → `ready` (se puede tomar) → `in-progress` (alguna tarea tomada) → `verifying` (todas las
tareas hechas, falta evidencia) → `done` (con `## As-built`).

## Cómo tomar una spec

### 0. Triaje (Organic Driven Development, Gentle-AI)

Antes de tocar código, decide cuánto proceso necesita el cambio. Se usan los cuatro niveles de Organic Driven Development
([artículo](https://cursosdesarrolloweb.com/articulos/organic-driven-development-odd),
[Gentle-AI](https://github.com/Gentleman-Programming/gentle-ai)):

| Nivel | Cuándo | Qué se escribe |
|---|---|---|
| 1 · Directo | Texto, valor o configuración en un archivo; sin cambio de comportamiento | Nada; el commit explica |
| 2 · Error | Algo que debía funcionar y no funciona | Prueba que falla primero, luego el arreglo |
| 3 · Mini-spec | Comportamiento nuevo acotado y bien entendido | `spec.md` única (objetivo, criterios con `check:` y un caso negativo, tareas) |
| 4 · Spec completa | Cambio amplio, riesgoso o poco entendido | `spec.md` + `plan.md` + `tasks.md` |

Criterios para elegir:
- **Archivos tocados**: uno → 1–2; un módulo → 3; varios módulos o un componente nuevo → 4.
- **Riesgo**: ¿qué se rompe si sale mal? Datos perdidos, envío equivocado o bloqueo de una cuenta suben el nivel.
- **Quién lo ve**: si lo usa Ayelén o lo ve un empleador, sube al menos un nivel.
- **Reversible**: si no se puede deshacer con un `git revert` (un envío, un correo, un bloqueo del portal), nivel ≥ 3.
- **Qué tan entendido está**: si no se sabe cómo responde el portal o qué pide el formulario, nivel 4 o una spec de
  reconocimiento primero.
- **Forzado ≥ 3**: portales (lectores, recetas), envío de postulaciones, datos personales y formatos públicos
  (esquema de SQLite, formato de recetas, protocolo del relay).

Regla: **escalar, nunca bajar en silencio**. Si durante el trabajo el cambio resulta más grande o riesgoso, sube de nivel
y anótalo. Bajar de nivel requiere una línea en el `Change log` con el motivo.

Solo los niveles 3 y 4 llevan spec: nivel 3 = un `spec.md` (mini-spec, con sus tareas al final); nivel 4 = `spec.md`,
`plan.md` y `tasks.md`.

### 1. Leer
Lee `spec.md` → `plan.md` → `tasks.md` (o la sección `## Tasks` en nivel 3). El enfoque de `plan.md` está **bloqueado**:
si no estás de acuerdo, detente y explícalo en la PR o en un *issue*; no lo cambies por tu cuenta.

### 2. Tomar una tarea
Marca la tarea en `tasks.md` con `[~] (agente: nombre)` en el mismo commit con que empiezas, y cambia el `Status` de la
spec a `in-progress` si era `ready`. Una tarea por PR. No tomes una tarea ya marcada `[~]`.

### 3. Pruebas primero
Escribe primero la prueba del criterio (incluido el caso negativo) y comprueba que falla. Luego implementa. Las pruebas
no consultan portales reales: usan HTML o JSON grabado con datos ficticios.

### 4. Verificar con evidencia
Corre el `check:` de cada criterio que toca la tarea y además `ruff check .`, `mypy app.py itau.py asistente relay tests`
y `pytest`. Marca la tarea `[x]` y pega en la PR la salida o el resumen del `check:`. Un criterio con verificación
manual (observación) se cumple solo con lo observado anotado en `## Verify` (fecha, qué se vio). Una casilla marcada sin
evidencia no cuenta.

### 5. Cerrar
Cuando todas las tareas están `[x]`, la spec pasa a `verifying`. Para dejarla en `done`, agrega `## As-built`: commits
integrados, ADDED / CHANGED / DROPPED, trabajo fuera de la spec y lo que no se verificó. Si algo quedó pendiente, se
anota y pasa a otra spec.

## Crear una spec nueva
Copia `_plantilla/` a `specs/NNN-slug/` con el siguiente número libre, borra lo que no aplique al nivel y agrega la fila
al índice. Cada criterio tiene `check:` (comando o una observación con nombre) y al menos uno es un caso negativo.

## Reservar una tarea (issues)

Cada tarea de una spec tiene un *issue* titulado `[NNN-T00X] título`, con etiquetas `spec:NNN`, `nivel:N` y `estado:libre |
en-curso | en-revision`. Se crean o actualizan con `python scripts/issues_desde_specs.py` (agrega `--dry-run` para ver los cambios sin
escribir). El script es idempotente: no duplica issues ni toca los estados ni las asignaciones.

Antes de empezar:
1. Revisa que no tengas otro issue en `estado:en-curso`: **un agente, una tarea a la vez**.
2. Si el issue ya está en curso o tiene a alguien asignado, elige otro.
3. Comenta «Tomo esta tarea (agente: tu-nombre)», asígnate y cambia la etiqueta a `estado:en-curso`.
4. Trabaja en la rama `tarea/NNN-T00X-descripcion-corta`; el PR dice `Closes #N` y pasa el issue a `estado:en-revision`.
5. Si dejas la tarea, coméntalo, quítate la asignación y vuelve a `estado:libre`.

