# TASK-007 — `scripts/estado.py`: comparar la documentación contra el sistema real

| Campo | Valor |
|---|---|
| **Ruteo** | `codex` |
| **Motivo** | script aislado, sin dependencias de dominio, criterio de aceptación obvio (§16) |
| **Rama** | `feat/TASK-007-scripts-estado` |
| **Revisor** | Claude Code (§16.1 — revisa quien no ejecutó) |

## Objetivo

Un comando que imprima **el estado verificado del sistema**, no el declarado. Su salida es
**precondición de cada entrada de bitácora**: antes de escribir "esto quedó hecho", se corre
y se mira.

## Por qué existe esta tarea

Todas las discrepancias que motivaron el diagnóstico de agosto comparten una causa: **la
documentación registraba intención, no estado verificado.** Casos reales, todos del mismo
repo y todos silenciosos:

- *"Marcos debe correr `alembic upgrade head`"* se arrastró **cinco entradas** de bitácora
  cuando ya estaba hecho.
- *"Commit sin push"* se repitió en **ocho entradas**: era falso para el backend y
  verdadero para el frontend, y nadie lo distinguía.
- **FGE** figuró como funcional en **tres documentos** durante dos meses, desde que su
  portal agregó hCaptcha.
- Producción cobró tokens por datos que fabricaba el proveedor `mock` **sin que nada lo
  dijera**.
- Dos veces en la misma semana **la base fue por delante del código**: una migración
  aplicada en Neon con el commit sin pushear.

Ninguno se detecta leyendo documentos: los cinco se detectan mirando el sistema. Este
script es esa mirada, y por eso vale más que casi todo lo que tiene por delante en el
backlog.

## Qué debe imprimir

Cinco bloques. Cada uno **dice explícitamente si hay desalineación**, no obliga a
interpretar dos números.

### 1. Migraciones — head local vs Neon

Head del repo (los archivos de `alembic/versions/`) contra `alembic_version` de Neon.
**Marcar si difieren, y en qué dirección**: no es lo mismo "falta aplicar una migración"
que "la base va por delante del código" (esto último ya pasó dos veces y es peor).

### 2. Git — commits sin pushear y ramas sin mergear

En **ambos repos** (`consulta_placas_ec` y `consulta-placas-web`): cuántos commits tiene
`main` que no estén en `origin/main`, y qué **ramas locales no están mergeadas a `main`**.
Hacer `fetch` antes de comparar, o el dato es el de la última vez que alguien lo hizo.

### 3. Proveedor vehicular activo en producción

**Desde el endpoint público, NO desde el `.env`.** El punto entero es detectar que el
dashboard de Render diga algo distinto de lo que creemos.

> **Límite verificado — léelo antes de buscar un endpoint que no existe.** Ningún endpoint
> público **nombra** el proveedor: `proveedor_usado` solo aparece en
> `DesbloqueoConsultaResponse`, o sea **solo tras pagar tokens**, y este script no gasta
> nada. Lo que sí se puede observar gratis son sus **capacidades**, en el array `productos`
> de `GET /consultar/{placa}/perfil?solo_cache=true`, donde `solo_cache` garantiza que **no
> dispara scraping**.
>
> **Ojo con el OpenAPI: ese endpoint aparece con `security`, pero la auth es OPCIONAL.**
> Usa `usuario_actual_opcional`, que nunca lanza 401; FastAPI lo marca igual porque hay una
> dependencia OAuth2 declarada. **Verificado con una llamada anónima real a producción:
> responde `200` y devuelve los 8 productos sin ningún token.** No lo leas del OpenAPI y
> concluyas que hace falta autenticarse — no es el caso, y no dispara la condición de
> BLOCKED.
> - `identificadores_tecnicos` o `titular_validado` con `disponible: true` → **hay un
>   proveedor con capacidades activo**. Si no hay credenciales reales cargadas, eso
>   significa que está el **`mock`**, que fabrica VIN y titular: **es una alerta**.
> - ambos en `disponible: false` → ningún proveedor ofrece datos. Es el estado correcto hoy.
>
> Repórtalo en esos términos ("hay/no hay proveedor con capacidades"), **sin afirmar cuál
> es**. Afirmar un nombre que no se puede observar sería exactamente el error que este
> script existe para atrapar.

Usa una placa que ya esté en caché para no depender de nada externo; si no hay datos, el
bloque igual debe poder responder (`productos` viene aunque el perfil esté vacío).

### 4. Fuentes con consultas en los últimos 7 días

De la tabla `consultas`: por `fuente`, cuántas y **cuándo fue la última**. Sirve para ver de
un vistazo que una fuente dejó de responder — es como se habría detectado lo de FGE, cuya
última consulta exitosa quedó congelada en mayo mientras tres documentos la daban por viva.
Incluir las fuentes **sin** consultas recientes: la ausencia es justamente la señal.

### 5. Cola del worker — pendientes y atascados

De `cola_scraping`: trabajos en `pendiente` y `en_proceso`, **con su antigüedad**. Un
`en_proceso` de hace días es un lock colgado, no trabajo en curso. Hoy mismo hay trabajos
sin tomar desde julio y uno tomado que nunca terminó.

## Restricciones duras

1. **Solo lectura. Jamás escribe en ninguna BD ni en ningún repo.** Nada de `INSERT`,
   `UPDATE`, `DELETE`, `alembic upgrade/stamp`, `git fetch --prune`, `git checkout`,
   `git commit`. Un `git fetch` (sin `--prune`) es la única operación de red sobre los
   repos y es aceptable.
2. **Consulta Neon de forma EXPLÍCITA, sin depender de renombrar `.env.local`.** Desde
   TASK-010, `src.core.database` resuelve con precedencia *entorno real > `.env.local` >
   `.env`*, así que en una máquina de desarrollo apunta a la BD **local**. Para leer
   producción, **lee `DATABASE_URL` directamente de `.env`**, así:
   ```python
   from dotenv import dotenv_values
   dsn = dotenv_values(RAIZ / ".env")["DATABASE_URL"].replace(
       "postgresql+psycopg://", "postgresql://"
   )
   ```
   **No importes `src.core.database`** para esto: te daría la URL equivocada y en silencio.
3. **Si una fuente no responde, lo reporta y sigue.** Nunca aborta. Neon caída, Render
   dormido, el repo hermano ausente o un `git` que falla → ese bloque dice qué pasó y los
   otros cuatro se imprimen igual. Un script de estado que se muere ante el primer problema
   es inútil justo cuando más se necesita.
4. **Sin dependencias nuevas.** Ya están `psycopg`, `httpx`, `python-dotenv` y `alembic`.

## Detalles ya verificados — no los re-derives

- **Columnas reales.** `consultas`: `id, placa, fuente, estado, respuesta, creado_en`.
  `cola_scraping`: `id, identificador, fuente, estado, intentos, max_intentos, payload,
  error, disponible_en, tomado_en, creado_en, actualizado_en`.
- **Head local sin tocar la BD:** `alembic.config.Config` + `ScriptDirectory` sirve para
  leer el head de los archivos sin conectarse. Evita invocar el comando `alembic`, que
  carga `env.py` y resuelve la URL con la precedencia de TASK-010.
- **Backend en producción:** `https://consulta-placas-ec.onrender.com`. Está en plan free y
  **duerme**: el primer request tarda **~20-30 s**. Usa un timeout generoso (≥60 s) y, si
  tardó, dilo — un arranque en frío no es un fallo.
- **El repo hermano** está en `../consulta-placas-web` respecto de este. Si no existe, es el
  caso de la restricción 3, no un error fatal.

## Alcance de archivos

**Permitido tocar:** `scripts/estado.py` (nuevo) y `docs/ORDEN-DE-TRABAJO.md` (marcar
TASK-007 y anotar que su salida precede a cada entrada de bitácora).

**Prohibido tocar:** cualquier archivo de `src/`, migraciones, tests existentes,
`requirements.txt`, `render.yaml`, `Dockerfile` y el repo frontend. Si crees necesitar algo
de `src/`, **repórtalo en vez de agregarlo**.

## Criterio de aceptación

- [ ] `python -m scripts.estado` imprime los **cinco bloques** y termina con **exit 0**.
- [ ] Cada bloque dice explícitamente si hay desalineación, sin obligar a comparar cifras a
      ojo.
- [ ] **Con Neon inalcanzable** (probar con una `DATABASE_URL` a un host inexistente y
      timeout corto): el bloque de migraciones y los de BD reportan el fallo, **los demás se
      imprimen igual** y el exit sigue siendo 0.
- [ ] **Con el backend caído** (probar apuntando a un puerto muerto): el bloque del
      proveedor reporta el fallo y el resto se imprime.
- [ ] **Sin el repo hermano** (probar renombrándolo temporalmente): el bloque de git reporta
      lo que pudo y sigue.
- [ ] **Prueba de que no escribe:** `alembic_version` de Neon y `git log` de ambos repos son
      idénticos antes y después de correrlo. Demuéstralo con la comparación, no lo afirmes.
- [ ] Copy **es-EC**, legible en una terminal angosta.
- [ ] Sin dependencias nuevas.

## Fuera de alcance

Cualquier acción correctiva: el script **informa, no arregla**. Nada de aplicar migraciones,
pushear, reencolar trabajos ni cambiar variables. Tampoco entra integrarlo a un hook, a CI o
a un cron, ni un modo `--json`: si hacen falta, son tareas aparte una vez que la salida
humana esté validada.

## Condiciones de BLOCKED

- Si para leer alguno de los cinco datos hiciera falta **autenticarse** o **gastar tokens**,
  detente y repórtalo: este script no tiene credenciales de usuario y no compra nada.
- Si `.env` no tiene `DATABASE_URL`, repórtalo como configuración faltante y sigue con los
  bloques que no dependen de la BD — no inventes un valor por defecto ni caigas a la BD
  local, que daría un estado falso de producción.
