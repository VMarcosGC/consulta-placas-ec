# TASK-016 — Cierre de tarea obligatorio y ejecutable

| Campo | Valor |
|---|---|
| **Ruteo** | `claude-code` |
| **Motivo** | el entregable es un procedimiento cuya corrección depende de conocer el sistema entero (qué entra en un snapshot, qué cuenta como BLOCKED acá, qué documento es fuente de verdad de qué). Además toca `AGENTS.md`, que es la fuente de verdad. No es una tarea cercada con criterio de aceptación obvio (§16). |
| **Rama** | `feat/TASK-016-cierre-de-tarea` |
| **Revisor** | Codex (§16.1 — revisa quien no ejecutó) |
| **Depende de** | **TASK-007** (`scripts/estado.py`), sin absorberla — ver §2 |

## 1. Objetivo

Convertir el cierre de tarea en un **paso ejecutable y obligatorio**, no en una costumbre.

Hoy el cierre existe como intención repartida entre `AGENTS.md`, el ritual §3 de
`plan_market_autos.md` y el checklist §5. Nada de eso se ejecuta: son párrafos que alguien
recuerda o no. Por eso se salta, y cuando se salta **no queda rastro de que se saltó** —
que es lo que lo vuelve invisible en la revisión.

El entregable central es la skill **`.claude/skills/cierre-de-tarea/SKILL.md`**: un
procedimiento de cinco pasos que se corre al terminar cualquier TASK, produce salida
verificable y **falla ruidosamente** cuando algo no está.

## 2. La dependencia con TASK-007: depende, **no** la absorbe

**Decisión: TASK-016 depende de TASK-007 y no la absorbe.** Tres argumentos, en orden de
peso:

1. **Routing.** TASK-007 está ruteada a **Codex**, con el motivo escrito en su spec: script
   aislado, sin dependencias de dominio, criterio de aceptación obvio (§16). TASK-016 va a
   **Claude Code** por exactamente lo contrario. Absorberla obligaría a una sola tarea a
   cruzar la frontera de ruteo, y quien la ejecute hará la mitad que no le toca con el
   criterio equivocado.
2. **Los criterios de aceptación de TASK-007 se perderían.** Sus ocho criterios incluyen
   tres pruebas de degradación —Neon inalcanzable, backend caído, repo hermano ausente— y
   una prueba de que **no escribe** (`alembic_version` y `git log` idénticos antes y
   después, demostrado con la comparación). Enterrar eso dentro de una tarea procedimental
   garantiza que sea lo primero que se recorte: nadie prueba el modo de fallo de un script
   que figura como "el paso 1" de otra cosa.
3. **Son dos capacidades distintas.** TASK-007 *observa el sistema*. TASK-016 *obliga a
   mirar la observación y a dejarla escrita*. Un script sin ritual se corre una vez y se
   olvida; un ritual sin script es lo que ya tenemos.

### 2.1 Pero TASK-016 **no espera** a TASK-007, y esto es normativo

La trampa obvia sería escribir la skill dando por hecho `scripts/estado.py` y dejar el paso
1 apuntando a un archivo que no existe. **Eso reproduce exactamente el defecto que esta
misma tarea repara** (§3): un procedimiento que menciona algo que no está, y que por eso
pasa su propia lectura sin hacer nada.

Regla, entonces:

> Mientras `scripts/estado.py` no exista, el paso 1 **no se salta ni se finge**. La skill
> intenta ejecutarlo y, si falta o falla, **el reporte de cierre declara un BLOCKED
> explícito**: *"paso 1 no ejecutado: `scripts/estado.py` no existe (TASK-007 pendiente)"*.

Consecuencia deliberada: **cada cierre de tarea imprimirá ese BLOCKED hasta que TASK-007 se
implemente.** Esa es la presión que hace que se implemente, y es mucho mejor que un paso que
se cumple en silencio porque nadie comprobó que corriera.

Prohibido: sustituir el paso 1 por un resumen escrito a mano "mientras tanto". Un resumen
redactado por quien acaba de hacer el trabajo es la fuente de las cinco discrepancias que
motivaron TASK-007 — es estado **declarado**, que es justo lo que no sirve.

## 3. El enlace muerto de `AGENTS.md` §1.1 — qué es realmente

`AGENTS.md:164` lista en la tabla de skills:

```
| [project-snapshot](.claude/skills/project-snapshot/SKILL.md) | global (regenera `proyecto-snapshot.md`) |
```

**Comprobado, no supuesto** (2026-08-25):

| Comprobación | Resultado |
|---|---|
| `.claude/skills/project-snapshot/` en el repo | **no existe** |
| `git log --all -- .claude/skills/project-snapshot` | **vacío** — nunca se commiteó |
| `C:\Users\vmarc\.claude\skills\project-snapshot\` | **sí existe** (nivel usuario, una máquina) |

O sea: **no es que la skill no exista; es que existe solo para una persona en una máquina.**
El enlace está muerto para todos los demás — para Codex, para cualquier agente que no corra
en esa cuenta, y para cualquiera que clone el repo. Y `AGENTS.md`, que es la fuente de
verdad **multi-agente**, la anuncia como si fuera del proyecto.

Peor: **su contenido no es de este proyecto.** La skill de nivel usuario es una plantilla
genérica que habla de *"subir a Gemini"*, de *notebooks `.ipynb`*, de `modelos/metricas/` y
de *"datos de pacientes"* — un remanente del proyecto de tesis. El `proyecto-snapshot.md`
que produjo lo prueba: su sección 8 se titula **"Para continuar en Gemini — instrucciones"**
y el archivo **no tiene ninguna sección de bloqueos**. No responde *qué está bloqueado y por
qué*, que es la mitad del valor.

**Qué hace TASK-016 con esto:** la fila de `project-snapshot` en la tabla §1.1 **se
reemplaza** por `cierre-de-tarea`, y la generación del snapshot pasa a ser el paso 2 de la
skill nueva, escrita para este repo. **No se porta la skill de usuario**: se escribe de
cero, porque lo único que valía la pena conservar de ella era el nombre. La versión de nivel
usuario queda donde está y deja de estar anunciada por `AGENTS.md`.

## 4. La skill: `.claude/skills/cierre-de-tarea/SKILL.md`

Frontmatter con `name` y `description`, en el formato de las skills existentes (ver
`respuesta-api-estandar/SKILL.md`). La `description` debe disparar con *"cerrar tarea"*,
*"terminé la TASK-X"*, *"cierre"*.

### Paso 1 — Estado verificado del sistema

Correr `python -m scripts.estado` y **pegar su salida literal** en el reporte. No resumirla,
no parafrasearla: la salida cruda es la evidencia. Si el script no existe o falla, ver §2.1.

### Paso 2 — Regenerar `docs/proyecto-snapshot.md`

**Éste es el paso que hace barato empezar un chat nuevo, y ese propósito tiene que estar
escrito dentro de la skill, no solo acá.** Todo lo demás del cierre sirve para que el
trabajo quede registrado; el snapshot sirve para que el **próximo** trabajo arranque sin
pagar el contexto otra vez. Un chat nuevo, un agente nuevo, Codex, o Marcos en tres semanas
deben poder leer **solo ese archivo** y retomar.

El criterio de "autocontenido" se verifica así, y la skill debe decirlo con estas palabras:

> Si para entender el snapshot hay que abrir la bitácora, la spec o el código, **no está
> autocontenido**. Un enlace es una referencia, no un sustituto del hecho.

Cuatro preguntas, obligatorias, en este orden:

1. **Qué hay.** Módulos, endpoints, migración aplicada (número **y dónde**: local y Neon
   pueden diferir), estado del frontend. Estado **verificado**, tomado del paso 1 — no el
   declarado.
2. **Qué se decidió.** Las decisiones vivas *y su porqué*, incluidas las que descartaron
   algo. Una decisión sin porqué se vuelve a discutir en el siguiente chat, que es
   exactamente el costo que el snapshot existe para evitar. Ejemplos que hoy calificarían:
   monetización suspendida con precios en 0 (§1.0.3), `mock` prohibido en producción, SRI y
   FGE apagados por captcha, sin nonce en el login con Google.
3. **Qué está bloqueado y por qué.** Sección propia, nunca una viñeta suelta. Cada bloqueo
   con **causa** y **condición de desbloqueo**. Distinguir *bloqueado por una limitación
   externa* (IPs de datacenter, captcha) de *pospuesto por decisión* (§1.0.2): se leen igual
   y no son lo mismo.
4. **Qué sigue.** Lo inmediato, no el roadmap entero.

Prohibido en el snapshot: secciones dirigidas a otra herramienta (la de "continuar en
Gemini" se elimina), datos sensibles o credenciales, y afirmaciones que el paso 1 no
respalde.

> **Movimiento de archivo — atención.** El snapshot vive hoy en la **raíz**
> (`proyecto-snapshot.md`) y esta tarea lo mueve a **`docs/proyecto-snapshot.md`**. Hay
> **dos referencias vivas** que quedan muertas si no se actualizan en el mismo commit:
> `AGENTS.md:166` y `docs/bitacora.md:6`. Mover un archivo sin corregir a quien lo apunta es
> literalmente el defecto de §3. Van en el mismo commit, o no se mueve.

### Paso 3 — Verificar que exista entrada de bitácora de la tarea

Comprobar que `docs/bitacora.md` tiene entrada **de esta tarea**, con el formato de la casa
(fecha · rama · qué se hizo · verificación · pendientes). **Verificar, no escribir**: si
falta, el cierre se detiene y lo dice. La skill no redacta la entrada — quien hizo el
trabajo la escribe, y el cierre comprueba que esté.

Chequeo mínimo: buscar el identificador (`TASK-016`) en la bitácora y confirmar que la
entrada más reciente que lo menciona corresponde al trabajo que se está cerrando, y no a una
mención de paso dentro de otra entrada.

### Paso 4 — Verificar que `ORDEN-DE-TRABAJO.md` refleje el estado real

Contrastar la fila de la tarea contra el paso 1. Los desajustes que ya ocurrieron y que este
paso tiene que atrapar:

- fila en "hecho" con la migración **sin aplicar** en Neon;
- fila en "hecho" con commits **sin pushear**;
- fila que dice "backend + frontend" cuando solo hay backend.

Si no coincide, se corrige la fila **en ese momento** y el cierre lo reporta como cambio.

### Paso 5 — Reportar en el formato corto

Cinco secciones, sin adornos:

```
Qué se hizo:            <2-4 líneas>
Verificado por comando: <comando → resultado literal, uno por línea>
Decisiones propias:     <las que tomó quien ejecutó, sin preguntar>
BLOCKED:                <lo que quedó trabado, con causa; "ninguno" si no hay>
Estado del repo:        <rama, commiteado/sin commitear, pusheado/no>
```

Reglas del formato:

- **"Verificado por comando" no admite prosa.** Va el comando y su resultado. Si no hay
  comando, no está verificado: se dice en BLOCKED o no se afirma.
- **"Decisiones propias" no puede quedar vacía por costumbre.** Si de verdad no hubo, se
  escribe "ninguna"; pero toda tarea real tiene alguna, y no declararla es cómo se cuelan
  las que nadie acordó.
- **BLOCKED incluye el de §2.1** mientras TASK-007 siga pendiente.

## 5. Alcance de archivos

**Permitido crear/tocar:**

| Archivo | Qué |
|---|---|
| `.claude/skills/cierre-de-tarea/SKILL.md` | **nuevo** — el entregable central |
| `AGENTS.md` | §1.1: reemplazar la fila `project-snapshot` por `cierre-de-tarea`; corregir la ruta del snapshot en la nota de cierre (línea 166) |
| `docs/proyecto-snapshot.md` | **movido** desde la raíz (`git mv`) y regenerado con el formato del paso 2 |
| `docs/bitacora.md` | línea 6: corregir la ruta del snapshot + entrada de la tarea |
| `docs/plan_market_autos.md` | §5: agregar el ítem del checklist (ver §5.1) |
| `docs/ORDEN-DE-TRABAJO.md` | fila de TASK-016 |

**Prohibido tocar:** todo `src/`, migraciones, tests, `requirements.txt`, `render.yaml`,
`Dockerfile` y el repo frontend. Esta tarea no cambia el comportamiento del sistema.

### 5.1 El ítem del checklist §5 de `plan_market_autos.md`

Se agrega **al final** de la lista, y va al final a propósito: es la última compuerta.

```markdown
- [ ] **Cierre de tarea ejecutado** (skill [cierre-de-tarea](../.claude/skills/cierre-de-tarea/SKILL.md)): estado verificado, snapshot regenerado, bitácora y ORDEN-DE-TRABAJO al día, reporte corto entregado. **Una tarea sin cierre no está terminada** — no importa que el código funcione.
```

La frase en negrita es el punto de la tarea entera y no se reformula: mientras "terminada"
signifique "el código anda", el cierre se seguirá saltando.

## 6. Criterio de aceptación

- [ ] `.claude/skills/cierre-de-tarea/SKILL.md` existe, con frontmatter válido, y **está
      commiteado en el repo** (no en `~/.claude/skills/`). Comprobarlo con
      `git ls-files .claude/skills/cierre-de-tarea/`.
- [ ] La skill contiene, textualmente, el propósito del snapshot: **hacer barato empezar un
      chat nuevo**.
- [ ] La skill describe los 5 pasos y el formato corto de reporte.
- [ ] El paso 1 tiene escrita la degradación de §2.1 (BLOCKED explícito; prohibido el
      resumen a mano).
- [ ] `AGENTS.md` §1.1 **ya no enlaza** `.claude/skills/project-snapshot/SKILL.md`.
      Comprobar con `grep -rn "project-snapshot" AGENTS.md` → sin coincidencias.
- [ ] **Ningún enlace roto nuevo.** Comprobar que todas las rutas relativas hacia el
      snapshot en `AGENTS.md` y `docs/bitacora.md` resuelven a un archivo existente.
- [ ] `docs/proyecto-snapshot.md` existe, la raíz ya no tiene `proyecto-snapshot.md`, y el
      movimiento se hizo con `git mv` (el historial se conserva).
- [ ] El snapshot regenerado tiene las **cuatro secciones** del paso 2, con la de bloqueos
      como sección propia, y **no** tiene la sección de Gemini.
- [ ] **Prueba de autocontención:** el snapshot no contiene frases que deleguen el hecho al
      lector ("ver la bitácora para el detalle", "según la spec"). Los enlaces pueden estar;
      el hecho tiene que estar también.
- [ ] `docs/plan_market_autos.md` §5 termina con el ítem de §5.1.
- [ ] La propia TASK-016 **se cierra con su propia skill**, y el reporte de cierre queda en
      la bitácora. Si la skill no se puede aplicar a sí misma, está mal escrita.

## 7. Fuera de alcance

- **Implementar `scripts/estado.py`.** Es TASK-007 (§2).
- Automatizar el cierre con un hook, un pre-commit o CI. Primero el procedimiento se usa a
  mano y se valida; engancharlo antes fija en piedra algo que no se probó.
- Un modo `--json` o cualquier salida legible por máquina.
- Portar o corregir la skill `project-snapshot` de nivel usuario: se deja de anunciar, no se
  toca (está fuera del repo).
- Reescribir el ritual §3 de `plan_market_autos.md`. Solo se agrega el ítem al checklist §5.

## 8. Condiciones de BLOCKED

- Si mover el snapshot a `docs/` rompiera una referencia que **no** está en la lista de §5
  (por ejemplo, algo del repo frontend o un enlace ya publicado), **detenerse y reportarlo**
  en vez de arreglarlo por cuenta propia: el alcance de archivos es cerrado.
- Si al regenerar el snapshot un dato del paso 1 **contradice** lo que dicen `AGENTS.md` o
  la bitácora, **no resolver la contradicción por decisión propia**. Escribir en el snapshot
  lo que el sistema dice, marcar la contradicción explícitamente y reportarla. Elegir en
  silencio cuál de los dos tiene razón es como se fabrica documentación falsa.
