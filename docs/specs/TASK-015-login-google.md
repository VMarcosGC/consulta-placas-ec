# TASK-015 — Login con Google (sin contraseña)

| Campo | Valor |
|---|---|
| **Ruteo** | `claude-code` |
| **Motivo** | migración Alembic + contrato de auth + verificación criptográfica (§16) |
| **Rama** | `feat/TASK-015-login-google` |
| **Revisor** | Codex, contra este archivo, `AGENTS.md` y el checklist §5 de `docs/plan_market_autos.md` |
| **Estado** | ✅ **APROBADA — lista para implementar** · revisión 5, tras 5 revisiones cruzadas Claude Code ↔ Codex (§16.1) · **no implementada** |

> **Revisión 2 — qué cambió respecto de la revisión 1.** La auditoría encontró un fallo
> crítico en la regla de vinculación por email y tres correcciones técnicas. Cambiaron:
> la **decisión 1** (§0, ahora restringida a identidad autoritativa de Google), la
> validación de **`azp`** (§5.2), la **selección de clave por `kid`** —que la revisión 1
> afirmaba mal— (§5.3) y el **pin de `python-jose`** (§5.1). Si estás leyendo esto para
> implementar, lee §0 completa antes que nada.
>
> **Revisión 3 — el `nonce` se elimina del diseño.** La revisión 2 proponía un `nonce`
> generado en el cliente como antirreplay, con el argumento de que "quien capture solo el
> token no puede usarlo". **El argumento era falso y la mitigación no mitigaba nada:** un
> JWT va **firmado, no cifrado**, y el `nonce` viaja en el payload en base64 dentro del
> mismo token. Quien captura el token captura el `nonce`. No existía un secreto
> independiente en ningún momento. §5.6 pasa a ser un **riesgo residual aceptado**, y
> `GoogleLoginEntrada` vuelve a `{ id_token }` — **desaparece el acoplamiento con el
> frontend** que la revisión 2 había introducido. También se resolvió una contradicción
> sobre el `kid` ausente (§5.3).
>
> **Revisión 4 — dos correcciones.** (a) La revisión 3 listaba "el JWT propio no hereda la
> vida del de Google" como **mitigación**; es lo contrario: con `JWT_EXPIRA_MINUTOS` en
> **1440**, canjear un ID token filtrado rinde **24 h de sesión propia**. Se elimina de la
> lista, §5.6 declara el impacto real y se anota como **decisión pendiente** bajar ese valor
> a 4-8 h (no se toca en esta tarea). (b) El "un refresco" del JWKS **debe ser atómico**:
> sin single-flight, una ráfaga concurrente de `kid` desconocidos lo supera por carrera y el
> piso de 5 minutos no protege — nueva §5.3.1, con prueba de ráfaga paralela obligatoria.
>
> **Revisión 5 — cierre.** Dos apuntes de alcance, sin cambios de diseño: los canjes
> repetidos emiten **sesiones concurrentes** y la exposición total llega a **~25 h** (§5.6);
> y el límite de un refresco del JWKS es **por proceso**, un techo conocido y no una carrera
> (§5.3.1). **La spec queda aprobada.**
>
> ### Historial de aprobación
>
> Aprobada tras **5 revisiones cruzadas** entre Claude Code y Codex, según §16.1 de
> `AGENTS.md` — la revisión la hace siempre la herramienta que **no** escribió el diff.
> Cada ronda encontró algo real, y por eso vale registrar qué:
>
> | Rev | Hallazgo |
> |---|---|
> | 1 → 2 | Vinculación por email a secas: **toma de cuenta**. Más `azp` sin validar, el `kid` mal descrito y `python-jose` sin pinear. |
> | 2 → 3 | El `nonce` de cliente **no protegía nada**: un JWT va firmado, no cifrado. |
> | 3 → 4 | La "mitigación" del JWT propio era una **amplificación** (24 h). El refresco del JWKS no era atómico. |
> | 4 → 5 | Sesiones concurrentes, exposición real de ~25 h, y el alcance por proceso del límite de refresco. |
>
> **Aprobada no significa cerrada a la evidencia.** Si al implementar aparece que algo de
> acá no se sostiene contra el código real, se reporta y se corrige la spec — no se
> implementa lo que dice el documento sabiendo que está mal. Lo que se cierra es la ronda
> de auditoría sobre el papel.

## Objetivo

Un usuario entra con su cuenta de Google y **nunca crea una contraseña**. El público
objetivo navega desde Android de gama baja y ya tiene sesión de Google iniciada en el
teléfono: pedirle que invente y recuerde una contraseña es la fricción más cara del
onboarding.

## 0. Decisiones ya tomadas — no se reabren

1. **Vinculación por email SOLO con identidad autoritativa de Google.** Ver §0.1: esta
   regla **revierte** la decisión original y es el punto más delicado de la tarea.
2. **`password_hash` pasa a nullable.** Un usuario de Google no tiene contraseña.
   Rellenarlo con un hash falso es peor: convierte "no puede entrar por contraseña" en
   "puede entrar si alguien adivina el placeholder".
3. **El backend sigue emitiendo SU propio JWT con `sub=<email>`.** El ID token de Google
   se valida y **se descarta**: no se guarda, no se reenvía, no se refresca.
   `usuario_actual`, `usuario_actual_opcional` y el contrato del frontend **no cambian**.

### 0.1 Vinculación por email — regla vigente, y por qué revierte a la anterior

> **ESTO REVIERTE UNA DECISIÓN PREVIA. NO LO "SIMPLIFIQUES".**
>
> La revisión 1 de esta spec decía: *"si el correo que llega de Google coincide con un
> usuario existente, es la misma cuenta; Google verifica el email"*. **Esa regla era una
> toma de cuenta** y se elimina. Si en una revisión futura alguien propone volver a
> vincular por email a secas porque "es más simple" o "Google ya verificó el correo", la
> respuesta está escrita abajo: ya se intentó, y este párrafo existe porque el argumento
> suena razonable y es falso.

**Por qué `email_verified: true` NO alcanza para tomar posesión de una cuenta existente.**
El claim afirma que *en algún momento* Google comprobó que quien creó esa cuenta de Google
controlaba ese buzón. No afirma que **hoy** lo controle. Para un correo que no es de un
dominio de Google, el dueño del buzón puede haber cambiado desde entonces: direcciones
corporativas que se reasignan al rotar el personal, dominios que caducan y alguien más
compra, proveedores que reciclan direcciones abandonadas. Quien reciba hoy ese correo
puede crear una cuenta de Google con él, y `email_verified` llegaría en `true` describiendo
una verificación vieja. Vincular por ese claim le entregaría la cuenta que otra persona
tiene en nuestra plataforma — con sus vehículos, su saldo y su historial.

**Regla vigente — auto-enlace solo con identidad autoritativa:**

Se considera **autoritativa** una identidad de Google que cumpla `email_verified is True`
**y además** alguna de estas dos:

| Caso | Condición sobre los claims | Por qué es autoritativa |
|---|---|---|
| **Gmail** | el dominio del `email` es `gmail.com` o `googlemail.com` | Google **es** el dueño del dominio y el operador del buzón: la dirección no puede haber cambiado de manos fuera de Google. `googlemail.com` es el dominio alterno del mismo servicio (Alemania/Rusia históricamente) y se acepta a propósito — omitirlo crearía cuentas duplicadas para el mismo buzón real. |
| **Workspace** | el claim **`hd`** viene presente y no vacío | `hd` significa que la cuenta pertenece a un dominio de Google Workspace: el control del buzón lo administra hoy ese dominio, y su administrador puede desactivarla. |

**Cualquier otro caso NO auto-enlaza.** Esto incluye el caso frecuente de una cuenta de
Google creada con un correo externo (`@hotmail.com`, `@yahoo.com`, un dominio propio sin
Workspace) aunque llegue con `email_verified: true`. Las salidas son dos, y solo dos:

- **El correo no existe en `usuarios` → alta normal.** Cuenta nueva, sin conflicto.
- **El correo ya existe en `usuarios` → NO se enlaza y NO se crea otra cuenta → `409`.**
  El usuario debe entrar con su contraseña y vincular Google **desde una sesión ya
  autenticada** (§3.1). Autenticarse primero es la prueba de posesión que el claim no da.

**Por qué no "crear una cuenta nueva" en ese caso**, aunque la instrucción original lo
ofrezca como alternativa: `Usuario.email` es **`unique=True`**
(`src/modules/auth/models.py:22-24`, verificado). Insertar una segunda fila con el mismo
correo **viola el índice único** y termina en `IntegrityError` → 500. La alternativa
"cuenta nueva" solo aplica cuando el correo **no** está tomado; cuando lo está, la única
salida segura es el enlace explícito. Que quede escrito para que nadie intente resolverlo
relajando el índice único: relajarlo rompería `sub=<email>` del JWT propio (decisión 3),
que asume que el email identifica a **una** cuenta.

**Lo que esta regla cuesta, dicho de frente:** un usuario con cuenta local
`juan@hotmail.com` que toque "Entrar con Google" recibe un 409 en vez de entrar. Es
fricción real y deliberada. El copy debe explicarle qué hacer, en es-EC y sin culparlo:
*"Ya tienes una cuenta con este correo. Entra con tu contraseña y vincula Google desde tu
perfil."*

## Contexto mínimo — verificado en el repo, no lo re-derives

- `src/modules/auth/router.py` tiene exactamente 3 endpoints: `/auth/registro`,
  `/auth/login`, `/auth/me`. El prefijo `/auth` **no tiene ninguna ruta dinámica**, así
  que la regla de orden literal-antes-que-dinámica (§5) no aplica aquí. Se cumple igual
  declarando `/auth/google` junto a las otras literales.
- `crear_token_acceso(subject=usuario.email)` (`security.py:22`) ya produce el JWT propio
  con `sub=<email>`. **Se reutiliza tal cual**: por eso `security.py` está prohibido tocar.
- El saldo de cortesía se audita hoy en `router.py:39-41`:
  `usuario.transacciones_tokens.append(TransaccionToken(monto=SALDO_INICIAL_TOKENS,
  motivo="saldo_inicial"))`. Es el único punto del código donde se acredita el alta.
- **Última migración: `0024_kilometraje_publicacion.py`.** La siguiente es **`0025`** —
  coincide con lo previsto en el encargo.
- **Ya están instaladas y en `requirements.txt`:** `python-jose[cryptography]` (3.5.0),
  `cryptography` (48.0.0) y `httpx` (0.28.1). Ver §5.1 de esta spec: **no hace falta ninguna
  dependencia nueva**, pero `python-jose` **sí se pinea a `==3.5.0`** (§5.1) — es el único
  cambio permitido en `requirements.txt`.
- **El repo NO tiene pytest.** Las pruebas usan `unittest` de la stdlib y se corren con
  `python -m unittest tests.test_x -v` (ver el docstring de `tests/test_ciudad_publicacion.py`).
  La mención a `pytest` en la spec de TASK-001 quedó obsoleta; **no la copies**.
- Estado actual del OpenAPI, medido: **51 paths / 64 operaciones**.
- Precedente de config: `GOOGLE_VISION_API_KEY` y `CLOUDINARY_*` se leen con `os.getenv`
  **dentro de su módulo de servicio**, no en `src/core/database.py`. Se sigue ese
  precedente → **`src/core/database.py` no se toca**.
- No hay modelo nuevo (solo columnas en `usuarios`) → **`src/registry.py` no se toca**.

---

## 1. Flujo elegido: Google Identity Services (ID token verificado en el backend)

**Recomendación: GIS con ID token.** El frontend obtiene el `credential` (un JWT firmado
por Google) y lo manda **una sola vez** a `POST /auth/google`; el backend verifica la
firma y responde con su propio JWT. **No** se implementa el redirect OAuth completo
(authorization code + callback + intercambio con `client_secret`).

Argumento, en orden de peso para este proyecto:

1. **El backend duerme.** Render free tarda ~20-30 s en el primer request (§12,
   `docs/despliegue.md`). Con redirect OAuth, Google devuelve al usuario a una ruta
   **del backend** (`/auth/google/callback`): el usuario queda mirando una pantalla en
   blanco durante el cold start, sin app, sin spinner y sin forma de saber que no se
   colgó. Con GIS el redirect nunca toca el backend — el usuario sigue dentro de la app
   Next.js, que puede mostrar "Entrando…" mientras el POST despierta a Render. Este
   punto solo, en el hosting que tenemos, ya decide.
2. **Menos pasos y menos peso en Android de gama baja.** GIS renderiza el botón (o One
   Tap) y, con la sesión de Google ya activa en el teléfono, el alta es **un toque sin
   salir de la página**. El redirect OAuth cuesta dos navegaciones completas más una
   recarga en frío del bundle de Next.js al volver.
3. **Un secreto menos en producción.** El flujo de ID token **no usa `client_secret`**:
   el backend solo necesita el `client_id`, que es público por diseño. Con authorization
   code habría que custodiar y rotar un secreto en Render para no ganar nada: no
   queremos ni Gmail, ni Drive, ni acceso continuo — queremos **una** afirmación de
   identidad, una vez.
4. **Encaja con la decisión 3 sin residuos.** No hay `refresh_token` que guardar ni
   sesión de Google que mantener viva: se verifica, se emite el JWT propio, se descarta
   el de Google. Un flujo de authorization code produce artefactos (refresh token,
   `state`, PKCE verifier) que este producto tendría que almacenar sin usar jamás.

**Lo que se pierde y por qué no importa:** sin authorization code no hay acceso a APIs de
Google en nombre del usuario. No lo necesitamos y está fuera del alcance del ciclo (§1.0.2).

---

## 2. Modelo y migración `0025`

### Columnas en `usuarios`

| Columna | Tipo | Null | Default | Índice / constraint |
|---|---|---|---|---|
| `password_hash` | String(255) | **pasa a NULL** | — | — (columna existente, se altera) |
| `proveedor_autenticacion` | String(16) | NOT NULL | `'local'` | CHECK `IN ('local','google')` |
| `id_google` | String(255) | NULL | — | **índice ÚNICO** `ix_usuarios_id_google` |
| `email_verificado` | Boolean | NOT NULL | `false` | — |

**`proveedor_autenticacion` es el origen de la cuenta, NO una exclusividad.** Guarda con
qué proveedor **se creó** la cuenta y sirve para copy y métricas ("te registraste con
Google"). **Nunca se usa para decidir si alguien puede entrar por una vía u otra**: eso
lo dicen las columnas de hecho — `password_hash IS NOT NULL` habilita el login por
contraseña, `id_google IS NOT NULL` habilita el login por Google, y **una cuenta puede
tener las dos** (un usuario local que después entra con Google conserva su contraseña).
Si se implementara como bandera exclusiva, vincular una cuenta local a Google le
apagaría su propia contraseña en silencio. Queda fijado aquí para que la revisión lo
verifique.

**`id_google` guarda el claim `sub`** del ID token: el identificador estable de la cuenta
de Google, que **no cambia aunque el usuario cambie su correo**. El índice **único** es
la barrera contra el secuestro: impide que dos cuentas de la plataforma queden colgadas
del mismo Google. Postgres permite múltiples `NULL` bajo un índice único, así que todas
las cuentas locales conviven sin problema.

**`email_verificado`** nace en `false` para todas las filas existentes y **no se
backfillea**: nunca verificamos el correo de los usuarios locales, y afirmar lo
contrario sería inventar un hecho. Solo se pone en `true` cuando Google lo afirma.

### Migración `alembic/versions/0025_login_google.py`

Manual, numerada, con `downgrade`, revisada a mano (§10.2). **Nunca `--autogenerate`.**

- `upgrade`: `alter_column` de `password_hash` a `nullable=True`, `add_column` de las
  tres columnas nuevas (las NOT NULL entran con `server_default`, que rellena las filas
  existentes sin un UPDATE aparte), `create_check_constraint` del proveedor y
  `create_index` único de `id_google`.
- `downgrade`: en orden inverso — drop index, drop check, drop de las tres columnas y
  **por último** `password_hash` de vuelta a `NOT NULL`.
- **El `downgrade` debe abortar con un mensaje explícito si quedan filas con
  `password_hash IS NULL`.** Volver a `NOT NULL` con usuarios de Google existentes falla
  con un error de Postgres ilegible, y la "solución" tentadora — rellenar con un hash
  placeholder — es exactamente lo que la decisión 2 prohíbe. Que se detenga y lo diga.
  Guardar ese chequeo tras `if not context.is_offline_mode():` para no romper el modo
  `--sql`.

  > **Corrección (2026-08-25).** Una versión previa de este párrafo decía *"mismo cuidado
  > que tomó `0021`"*. **No existe tal precedente**: `grep is_offline_mode alembic/` sólo
  > da `env.py` y la propia `0025`. `0021_vendedor.py` usa `op.execute`, que en modo
  > `--sql` se emite como texto y nunca abre una conexión, así que jamás tuvo el problema.
  > `0025` es la **primera** migración del repo que necesita *leer* estado de la base
  > dentro de un `downgrade`, y por eso la primera que necesita la guarda. Se deja
  > anotado porque una cita a un precedente inexistente hace que la próxima revisión dé
  > por verificado algo que nadie verificó.

---

## 3. `POST /auth/google` — resolución de la cuenta

Entrada: `GoogleLoginEntrada { id_token: str }` (JSON). Salida: el schema **`Token`** ya
existente, idéntico al de `/auth/login`. El frontend no distingue de dónde salió el JWT.

**Orden de resolución — este orden es normativo:**

1. **Por `id_google == sub`.** Si existe, esa es la cuenta, aunque su `email` ya no
   coincida con el que manda Google hoy. **El `email` guardado NO se actualiza**: es el
   `sub` de nuestro propio JWT y la clave de negocio de toda la app; reescribirlo
   invalidaría las sesiones vivas y podría chocar contra el índice único de `email`.
2. **Por `email` (comparación insensible a mayúsculas).** Si existe una cuenta con ese
   correo y **no** tiene `id_google`, la salida depende de si la identidad es
   **autoritativa** según §0.1:
   - **Autoritativa** (`gmail.com` / `googlemail.com`, o `hd` presente) → se **vincula**:
     `id_google = sub`, `email_verificado = True`. `proveedor_autenticacion` **no se toca**
     (la cuenta se creó local y eso no cambia). **No se acreditan tokens** (§4).
   - **No autoritativa** → **`409`**, sin escribir nada. Ni se vincula ni se crea una
     segunda cuenta (el índice único de `email` lo impediría de todos modos, §0.1). El
     camino del usuario es §3.1.
3. **No existe → alta.** `Usuario(email=<email del claim>, password_hash=None,
   nombre=<claim name>, proveedor_autenticacion="google", id_google=sub,
   email_verificado=True)` **+ el saldo de cortesía** (§4). Esta rama **no** depende de si
   la identidad es autoritativa: sin cuenta previa no hay nada que tomar, y el correo
   queda asociado a quien lo controla hoy. La autoritatividad solo gobierna el **enlace a
   una cuenta ajena preexistente**, que es donde está el riesgo.

**La comprobación de autoritatividad vive en una función propia y testeable**,
`identidad_google_autoritativa(claims) -> bool`, en `src/modules/auth/google.py`. No se
escribe inline en el router: es la regla de seguridad de §0.1 y tiene que poder probarse
sola, sin levantar el endpoint.

> **La comparación por email debe ser insensible a mayúsculas y es un requisito, no un
> detalle.** `/auth/registro` guarda el email tal como lo escribió el usuario y todas las
> búsquedas actuales usan `==` exacto. Google devuelve el correo en minúsculas. Una cuenta
> registrada como `Marcos@Gmail.com` **no** haría match: el flujo saltaría a la rama de
> alta (paso 3) e intentaría insertar una segunda fila con el mismo correo real, chocando
> contra el índice único de `email` → `IntegrityError` → **500**, justo lo que §10.2
> prohíbe. Usar `func.lower(Usuario.email) == email.lower()`. Que `/auth/registro` siga
> siendo sensible a mayúsculas es deuda preexistente y **queda fuera de alcance**.

### 3.1 `POST /auth/google/vincular` — enlace explícito desde sesión autenticada

Es la salida obligatoria del `409` de §0.1: sin este endpoint, un usuario con correo no
autoritativo queda **permanentemente fuera** del login con Google, y la regla de seguridad
se vuelve un callejón sin salida. Por eso forma parte de esta tarea y no de una posterior.

- **Requiere `Depends(usuario_actual)`.** Ese JWT propio es la prueba de posesión de la
  cuenta que el claim `email_verified` no da: quien pide el enlace ya demostró que sabe la
  contraseña. Con eso, la autoritatividad **deja de importar** y no se comprueba.
- Entrada: el mismo `GoogleLoginEntrada { id_token: str }`. Se verifica igual que en
  `/auth/google` (§5, sin excepciones ni atajos).
- **El `email` del token NO tiene que coincidir** con el de la cuenta. Vincular es
  justamente decir "esta cuenta de Google, aunque use otro correo, soy yo".
- Efecto: `id_google = sub`. **`email_verificado` NO se toca** — sigue describiendo el
  correo *de la cuenta*, que Google no verificó. `proveedor_autenticacion` tampoco.
- **No acredita tokens** en ningún caso (§4): la cuenta ya existía.
- Errores: **`409`** si esa cuenta ya tiene un `id_google` distinto, o si ese `sub` ya está
  vinculado a **otra** cuenta (lo garantiza el índice único, pero se comprueba antes para
  devolver 409 y no un 500). **`401`** si el token de Google no valida. **`401`** si falta
  o vence el JWT propio (lo da `usuario_actual`).

### Contrato de errores (§10.2 — nunca un 500)

| Código | Cuándo |
|---|---|
| **401** | firma inválida · `aud` distinto de nuestro `client_id` · `aud` múltiple con `azp` que no es el nuestro (§5.2) · `iss` desconocido · token expirado · `kid` ausente, o presente y aún desconocido tras un refresco del JWKS (§5.3) · `alg` fuera de `RS256`. Mensaje **genérico** ("Credenciales de Google inválidas"): no se detalla cuál claim falló, y **nunca se registra el token** (§5.6). |
| **422** | `email_verified` es `false`, o el token no trae `email`. El token es legítimo pero la cuenta no sirve para identificar a nadie: es validación de negocio, no credencial mala. |
| **409** | **identidad no autoritativa (§0.1) sobre un correo que ya existe** — el caso más frecuente de los tres, y el único con copy propio: *"Ya tienes una cuenta con este correo. Entra con tu contraseña y vincula Google desde tu perfil."* · la cuenta hallada por email ya tiene un `id_google` **distinto** · la búsqueda insensible a mayúsculas devuelve **más de una** fila. Conflicto real que un humano debe resolver — nunca elegir una fila a dedo. |
| **503** | `GOOGLE_CLIENT_ID` sin configurar, o el JWKS es inalcanzable y no hay caché válida. Es fallo de despliegue, no del usuario (mismo precedente que `POST /consultar-foto` sin `GOOGLE_VISION_API_KEY`). |
| **422** (FastAPI) | body sin `id_token`. Lo produce Pydantic solo; no hay que escribirlo. |

---

## 4. Saldo de cortesía: exactamente una vez

`SALDO_INICIAL_TOKENS = 5` (§10.3) se acredita **solo en el caso 3** de §3 — la rama que
construye un `Usuario` nuevo. **Los casos 1 y 2 no acreditan nada, ni en su rama de
vinculación ni en la de `409`, y `POST /auth/google/vincular` (§3.1) tampoco.**

**El punto exacto del código:** dentro de la rama de alta de `/auth/google`, replicando
`router.py:39-41` — se instancia el `Usuario` y, antes del `sesion.add`, se le agrega
`TransaccionToken(monto=SALDO_INICIAL_TOKENS, motivo="saldo_inicial")` por la relación
`usuario.transacciones_tokens`. **El mismo `motivo` y el mismo monto que el registro
local**, para que el ledger sea una sola serie legible y no dos dialectos.

**Por qué la vinculación (caso 2) no acredita:** el usuario ya recibió sus 5 al
registrarse y la fila `saldo_inicial` ya está en `transacciones_tokens`. Acreditar otra
vez daría 10 tokens a quien descubra que puede entrar por Google, y el ledger mostraría
dos `saldo_inicial` para la misma cuenta. La regla se hace **estructural, no confiada a
un `if`**: el crédito vive dentro del bloque que construye el `Usuario`, nunca después de
resolverlo. Nada de un `if usuario.saldo_tokens == 0` ni de contar transacciones previas.

El default de columna (`saldo_tokens` server_default `"5"`) cubre el saldo; la
`TransaccionToken` cubre la auditoría. **Las dos son obligatorias** aunque los precios
estén en 0 (§1.0.3): un crédito sin fila en el ledger es un hueco imposible de cerrar
cuando existan saldos reales.

---

## 5. Verificación del ID token — el punto donde esto se rompe

Vive en **`src/modules/auth/google.py`**, no en el router. Expone dos funciones públicas:
`verificar_id_token_google(id_token: str) -> ClaimsGoogle` y
`identidad_google_autoritativa(claims) -> bool` (§3).

### 5.1 Librería: `python-jose` **pineado a `==3.5.0`** — sin dependencias nuevas

`python-jose[cryptography]` **ya está en `requirements.txt`** (lo usa `security.py` para el
JWT propio) y `httpx` ya está para traer el JWKS. **Cero dependencias nuevas** (§4).

**Pero la línea cambia de `python-jose[cryptography]>=3.3.0` a
`python-jose[cryptography]==3.5.0`.** Es obligatorio y es el **único** cambio permitido en
`requirements.txt`.

**Por qué el pin, y por qué no es paranoia de versiones:** todo §5.2–§5.5 está escrito
contra el comportamiento **interno** de esta versión — qué valida `_validate_aud` y qué
deja pasar, qué opciones vienen en `False`, cómo `_get_keys` trata un JWK Set. Son
detalles de implementación, no API pública documentada: pueden cambiar en un patch sin
aviso, en cualquier dirección. Con `>=3.3.0`, un `pip install` en un build futuro de Render
puede traer una versión cuyos defaults ya no coincidan con lo auditado aquí, y el resultado
no sería un error visible sino **una validación que silenciosamente deja de hacerse**. Un
agujero de autenticación no falla ruidosamente: sigue devolviendo 200. Versión fija,
auditoría fija; para subirla, se repite la auditoría de §5.2–§5.5 y se actualizan los
números de línea de esta spec.

La alternativa canónica sería `google-auth` (`id_token.verify_oauth2_token`), que trae el
JWKS y las validaciones empaquetadas. **Se descarta**: sumaría `google-auth` + `rsa` +
`pyasn1` + `pyasn1-modules` + `cachetools` a una imagen Docker que ya arrastra Playwright
y Chromium, para reemplazar unas 40 líneas que podemos escribir con lo instalado. La
contrapartida honesta es que las validaciones quedan a nuestro cargo — y por eso lo que
sigue es **normativo** y cada punto tiene una prueba negativa obligatoria.

### 5.2 `aud` y `azp` — la audiencia debe ser exactamente la nuestra

`jose` **no** exige que `aud` sea nuestro `client_id`: exige que **esté entre** los valores
de `aud`. Verificado en `_validate_aud` (`jwt.py:368`):

```python
if isinstance(audience_claims, str):
    audience_claims = [audience_claims]
...
if audience not in audience_claims:      # <-- pertenencia, no igualdad
    raise JWTClaimsError("Invalid audience")
```

Un token con `aud: ["<nuestro_client_id>", "<otro_client_id>"]` **pasa**. Un ID token con
audiencia múltiple no fue emitido para nosotros en exclusiva, y aceptarlo permite que otra
aplicación reutilice contra nuestro backend un token que sus usuarios le entregaron a ella.

**Regla normativa, comprobada a mano después de `jwt.decode`:**

1. **`aud` debe ser exactamente `GOOGLE_CLIENT_ID`**: o el string, o una lista de **un solo
   elemento** igual a él. Cualquier otra cosa se rechaza con **401**.
2. **Si por alguna razón futura se decidiera aceptar `aud` con varios valores** —hoy no se
   acepta—, entonces es **obligatorio** exigir `azp == GOOGLE_CLIENT_ID`. El claim `azp`
   (*authorized party*) nombra a la aplicación **a la que Google entregó el token**, que es
   la pregunta que importa. Sin `azp`, "nuestro id aparece en la lista" no distingue un
   token emitido para nosotros de uno emitido para un tercero que nos incluyó.
3. **Si `azp` viene presente, debe ser `GOOGLE_CLIENT_ID`** aunque `aud` ya sea exacto.
   Presente-y-distinto es una contradicción: rechazar con **401**, nunca ignorarlo.

Las tres comprobaciones son código nuestro. `jose` no mira `azp` en absoluto.

### 5.3 Selección de clave por `kid` — hay que hacerla nosotros

> **Corrección de la revisión 1.** Esta spec afirmaba que `jose.jws._get_keys` "selecciona
> la clave por `kid`". **Es falso.** Verificado en `.venv/Lib/site-packages/jose/jws.py`:

```python
def _sig_matches_keys(keys, signing_input, signature, alg):
    for key in keys:                      # <-- prueba TODAS, en orden
        ...
        if key.verify(signing_input, signature):
            return True
    return False

def _get_keys(key):
    ...
    if "keys" in key:
        return key["keys"]                # <-- devuelve el set entero, sin filtrar
```

Pasarle el JWK Set completo hace que `jose` **pruebe cada clave hasta que alguna valide**,
ignorando el `kid` de la cabecera. Con el JWKS legítimo de Google el resultado final
coincide, pero el comportamiento es el equivocado: gasta verificaciones RSA por token,
depende del orden del set, y —lo que importa— **deja el `kid` sin validar**, que es
justamente el dato que liga el token a una clave concreta y publicada.

**Regla normativa:**

1. **Leer y validar la cabecera ANTES de `jwt.decode`**, con `jwt.get_unverified_header`.
   La cabecera no está autenticada todavía: se trata como entrada hostil y solo se usa
   para **seleccionar**, nunca para decidir cómo verificar.
2. **`alg` de la cabecera debe ser `RS256`.** Si no, **401** sin tocar el JWKS.
3. **`kid` ausente o vacío → `401` inmediato, SIN pedir el JWKS.** Un ID token de Google
   siempre trae `kid`: si falta, el token está malformado y no hay nada que buscar.
   **Refrescar el JWKS ante un `kid` ausente sería un vector de DoS** contra el endpoint de
   claves de Google — un atacante manda tokens basura sin `kid` y cada uno nos empuja a
   golpear a Google, justo lo que prohíbe el skill `scraping-respetuoso`. No hay excepción
   ni "por si acaso".
4. **`kid` presente pero desconocido en el JWKS cacheado → se fuerza UN refresco** (§5.5,
   con su piso de 5 minutos entre refrescos forzados) y se reintenta; si sigue sin estar,
   **401**. Este caso sí lo merece: es cómo se absorbe una rotación legítima de claves de
   Google sin esperar al TTL. **Ese "un refresco" debe ser atómico — ver §5.3.1.**

### 5.3.1 El refresco forzado debe ser atómico (single-flight)

**"Un refresco, con piso de 5 minutos" no es una regla, es una intención, hasta que se
implementa de forma atómica.** Leer el último-refresco, decidir, y escribirlo son tres
pasos; sin exclusión mutua, N peticiones concurrentes con `kid` desconocido leen todas el
mismo valor viejo, todas concluyen "puedo refrescar" y **todas golpean a Google a la vez**.
El piso de 5 minutos no protege de nada, porque nadie llegó todavía a escribirlo cuando
las demás decidieron. Es una carrera clásica, y el atacante no necesita saber nada del
sistema: le basta mandar en paralelo tokens con `kid` inventados. Cada ráfaga se convierte
en una ráfaga nuestra contra el endpoint de claves de Google — exactamente el DoS que §5.3
punto 3 evita para el `kid` ausente, reintroducido por la puerta de al lado.

**Regla normativa:**

1. **El refresco se serializa con un `threading.Lock`** del módulo. Los handlers de
   `auth/router.py` son `def` síncronos, así que FastAPI los corre en el threadpool: la
   concurrencia es de **hilos**, y un `Lock` es la primitiva correcta. (Si alguna vez el
   endpoint pasara a `async def`, esto debe revisarse: un `Lock` de `threading` bloquearía
   el event loop.)
2. **Patrón single-flight, con doble comprobación dentro del lock.** Quien toma el lock
   vuelve a mirar si el `kid` ya apareció y si el piso de 5 min ya se cumplió, **después**
   de adquirirlo. Las peticiones que esperaban encuentran el JWKS ya actualizado por la
   primera y **no** refrescan: una ráfaga de N produce **una** llamada a Google, no N.
3. **El piso de 5 minutos se lee y se escribe dentro del lock.** Fuera de él, el valor que
   se lee ya puede ser obsoleto.
4. **Nunca se sostiene el lock mientras se sirve el resto de la petición** — solo alrededor
   del refresco. El `httpx.Client` tiene timeout de 5 s (§5.5), que acota cuánto puede
   durar la sección crítica en el peor caso.

**Prueba obligatoria — ráfaga paralela.** No es opcional y no se puede sustituir por una
prueba secuencial: la carrera **solo** aparece con concurrencia real. Lanzar **N ≥ 20**
peticiones **en paralelo** (`ThreadPoolExecutor`) con el mismo `kid` desconocido contra un
doble del JWKS que **cuente sus invocaciones**, y afirmar que el contador quedó en
**exactamente 1**. Con la implementación ingenua ese contador da un número cercano a N y la
prueba falla, que es justo lo que tiene que hacer.

**Alcance del límite: es por proceso, y eso es sabido y aceptado.** El lock y el piso de
5 minutos viven en la memoria del proceso, así que garantizan **una llamada por proceso**,
no una llamada en total. Varios workers de uvicorn, varias instancias de Render o un
reinicio entre peticiones producen **una llamada cada uno**. Esto **no es la carrera que
§5.3.1 corrige** —esa era ilimitada dentro de un mismo proceso, N peticiones → N llamadas—
sino un techo conocido y acotado: el total queda en el número de procesos vivos, no en el
número de peticiones. Hoy Render free corre **una** instancia y el orden de magnitud es
irrelevante.

Queda anotado para que nadie lo lea como un fallo pendiente ni lo "arregle" a medias: la
coordinación distribuida (el mismo Redis de §5.6, o el JWKS cacheado en Postgres) es una
**mejora para cuando se escale**, no un requisito de esta tarea. Si algún día hay varias
instancias y las llamadas al JWKS molestan, ahí se decide — con datos, no ahora.
5. **A `jwt.decode` se le pasa esa única JWK**, no el set. Así `jose` verifica contra la
   clave que el emisor dijo haber usado, y un token cuyo `kid` miente falla en vez de
   colarse porque otra clave del set casualmente validó.

> **Los puntos 3 y 4 son casos distintos y la revisión 2 los confundía en una sola regla.**
> `kid` **ausente** = token malformado → 401 seco. `kid` **presente y desconocido** =
> posible rotación → un refresco. Escribirlos juntos como "si no está, refresca" era la
> contradicción con el criterio de aceptación, y la conducta correcta es la de arriba.

### 5.4 Llamada exacta y por qué cada opción está ahí

```python
jwt.decode(
    id_token,
    jwk_elegida,               # UNA sola JWK, seleccionada por `kid` (§5.3)
    algorithms=["RS256"],
    audience=GOOGLE_CLIENT_ID,
    issuer=("https://accounts.google.com", "accounts.google.com"),
    options={
        "require_aud": True,
        "require_exp": True,
        "require_iat": True,
        "require_sub": True,
        "require_iss": True,
        "verify_at_hash": False,
    },
)
```

Cada línea corrige un default de `python-jose` 3.5.0 que, dejado como viene, **abre un
agujero de autenticación**. Verificado leyendo `.venv/Lib/site-packages/jose/jwt.py`:

- **`require_aud: True` es obligatorio.** `_validate_aud` (línea 354) hace
  `if "aud" not in claims: return` — y el `raise` está **comentado en el código fuente de
  la librería**. Un token **sin** `aud` pasa en silencio, porque `require_aud` viene en
  `False` (línea 142). Sin esto, un ID token emitido por Google para **cualquier otra
  aplicación** entraría a nuestra plataforma: es el fallo clásico de este flujo. Y ojo:
  esto solo garantiza que `aud` **exista y nos incluya** — que sea *exactamente* el nuestro
  lo impone §5.2, no esta opción.
- **`issuer=` hay que pasarlo explícito. Esta es la corrección principal del issuer.**
  `_validate_iss` (línea 384) hace `if issuer is not None:` — si no se pasa el parámetro,
  **no valida absolutamente nada**, haya o no `require_iss`. Google emite las **dos** formas
  del issuer, con y sin esquema, así que se acepta la tupla de ambas y nada más.
- **`require_iss: True` es defensa en profundidad, no la corrección principal.** Solo exige
  que el claim **esté presente**; quien comprueba su **valor** es el parámetro `issuer=`
  del punto anterior. Se incluye para que un token sin `iss` falle por sí mismo en vez de
  depender de que el otro chequeo esté bien puesto, pero **no aporta seguridad si se olvida
  `issuer=`**. No confundir uno con otro: son cosas distintas y solo una protege.
- **`require_exp: True` es obligatorio.** `verify_exp` viene en `True`, pero `require_exp`
  en `False` (línea 143): un token **sin** `exp` no expira nunca y pasa. Esta es la
  **única** protección temporal real del token.
- **`require_iat: True` NO es una protección temporal.** Exige que el claim `iat` exista y
  nada más: **no limita la antigüedad del token**. Un token emitido hace 50 minutos con
  `exp` todavía vigente lo satisface igual que uno recién emitido. Se incluye porque `iat`
  es obligatorio en un ID token de OIDC y su ausencia indica un token mal formado — no
  porque acote nada en el tiempo. Quien acota es `exp` (arriba) y, contra la reutilización
  dentro de esa ventana, el antirreplay de §5.6. **Si alguna vez se quiere una ventana más
  corta que la de Google, hay que comprobar `iat` a mano contra `now`; esta opción no lo
  hace.**
- **`require_sub: True`**, porque `sub` es lo que se escribe en `id_google` y una cuenta sin
  identificador estable no sirve.
- **`verify_at_hash: False` es obligatorio o el flujo no funciona.** `_validate_at_hash`
  (línea 440) lanza `JWTClaimsError` si el claim `at_hash` está presente y no se le pasó un
  `access_token`. En este flujo no existe access token que comparar. Desactivarlo no
  debilita nada: `at_hash` solo liga el ID token a un access token que aquí no hay.
- **`algorithms=["RS256"]` fija el algoritmo.** Nunca leer el `alg` de la cabecera del
  token para decidir con qué verificarlo: es la puerta de la confusión de algoritmos
  (`none`, o HS256 firmado con el JWKS público como secreto).

Todas las excepciones de jose (`ExpiredSignatureError`, `JWTClaimsError`) derivan de
`JWTError`: capturar `JWTError` y traducir a **401**, sin dejar escapar el mensaje
original al cliente.

### 5.4.1 Claims que jose no conoce y hay que revisar a mano

- **`aud` exacto y `azp`** → §5.2. `jose` no mira `azp` en absoluto.
- **`email_verified` debe ser exactamente `True`.** Es condición **necesaria pero NO
  suficiente** para vincular una cuenta existente: la suficiente la define §0.1
  (`gmail.com`/`googlemail.com` o `hd` presente). No se debe presentar esta comprobación
  como "la razón por la que vincular por email es seguro" — la revisión 1 lo hacía y es
  precisamente el error que §0.1 corrige. `false`, ausente o cualquier valor que no sea
  `True` → **422**.
- **`hd`**, si viene, se usa **solo** para decidir autoritatividad (§0.1). No se persiste:
  no hay columna para él y la etapa 1 no tiene nada que hacer con dominios de Workspace.
- **`email` debe venir y no estar vacío** → si falta, **422**.
- **`sub` debe venir** (lo cubre `require_sub`, pero el código igual lo verifica antes de
  escribirlo en la columna).

### 5.5 Caché de JWKS

Google rota sus claves y publicarlas es su único canal, así que el JWKS se pide por red —
pero **una vez por token sería abusivo y frágil**: si Google tarda, todos los logins se
caen. Reglas:

- Caché **en memoria del proceso**, TTL **1 hora**, honrando el `max-age` del header
  `Cache-Control` de la respuesta cuando sea parseable.
- **Refresco forzado ante un `kid` presente pero desconocido** (así se absorbe una rotación
  sin esperar al TTL), con un **piso de 5 minutos entre refrescos forzados**: sin ese piso,
  un token basura con un `kid` inventado convierte cada request en un golpe a Google —
  justo lo que el skill `scraping-respetuoso` prohíbe. **Un `kid` ausente no refresca
  nunca** (§5.3 punto 3): se rechaza antes de llegar acá. **El refresco y la lectura del
  piso van dentro del lock de §5.3.1** — fuera de él, el piso no protege.
- Cliente **`httpx.Client` síncrono**, timeout de 5 s. Los handlers de `auth/router.py`
  son `def` síncronos; meter `AsyncClient` ahí obligaría a cambiar el router.
- JWKS inalcanzable **y** sin caché válida → **503**. Con caché aún válida, se sirve de
  caché y **no** se falla.

### 5.6 Replay del ID token — **riesgo residual aceptado**

**No se implementa antirreplay en esta tarea.** Esta sección declara el riesgo en vez de
esconderlo detrás de una mitigación que no mitiga.

**El riesgo, sin adornos:** el ID token de Google vale **~1 hora** y `/auth/google` lo
acepta **cuantas veces se lo manden**. Quien obtenga una copia dentro de esa ventana puede
canjearla por un JWT **nuestro**, repetidamente, sin la cuenta de Google y sin la
contraseña. `exp` acota la ventana; **no impide la reutilización dentro de ella**. Esto se
acepta a conciencia, no por descuido.

> **Impacto real, medido en el repo: ~1 hora para canjear el token filtrado, hasta
> 24 horas de sesión propia resultante.**
>
> `JWT_EXPIRA_MINUTOS` vale **1440** (`src/core/database.py:28` y `.env.example:16`,
> verificado). El JWT que emitimos al canjear dura **24 horas** y **no hay revocación de
> sesiones** en el producto (está en "Fuera de alcance"). O sea: el atacante tiene una
> ventana de ~1 h para usar el ID token filtrado, y lo que obtiene con él es acceso durante
> **un día entero**, que sobrevive a que Google expire su propio token y a que el usuario
> legítimo cambie su contraseña.
>
> La revisión 3 listaba "el JWT propio no hereda la vida del de Google" como una
> *mitigación*. **No lo es: es una amplificación.** No heredar la vida del token de Google
> significa aquí durar **24× más**, no menos. Se elimina de la lista y queda escrito para
> que no reaparezca con esa etiqueta.
>
> **Los canjes repetidos emiten sesiones concurrentes, no una sola.** Cada POST a
> `/auth/google` con el mismo ID token emite un JWT **nuevo e independiente**: no se
> invalida el anterior, no hay registro de sesiones activas y no hay forma de contarlas ni
> de cortarlas. Un atacante que canjee el token filtrado N veces se queda con **N sesiones
> vivas a la vez**, cada una con sus propias 24 h. Revocar no es "más difícil": hoy es
> **imposible**, porque el JWT es autocontenido y nadie lleva la cuenta de cuáles se
> emitieron.
>
> **La exposición total no son 24 h, son hasta ~25 h.** Las dos ventanas se **suman**, no se
> solapan: el atacante puede esperar hasta el filo del vencimiento del ID token (~1 h desde
> la filtración) para hacer su último canje, y ese canje todavía le rinde 24 h completas.
> **~1 h + 24 h ≈ 25 h desde el momento de la filtración**, en el peor caso — y el peor caso
> es el que hay que asumir, porque esperar al final no le cuesta nada al atacante y le rinde
> el máximo.

#### Lo evaluado y descartado

- **`nonce` generado en el cliente — descartado, no funcionaba.** La revisión 2 lo proponía
  argumentando que "quien capture solo el token no puede usarlo". **Es falso: un JWT va
  firmado, no cifrado.** El `nonce` viaja en el payload, en base64, **dentro del mismo
  token**; cualquiera que lea el token lee el `nonce`. Nunca fue un secreto independiente
  del token, así que no agregaba ninguna barrera — solo la apariencia de una, que es peor
  que nada porque desalienta buscar la real. Queda escrito para que no se reproponga.
- **`nonce` emitido por el servidor — descartado por costo de UX.** Es la variante que sí
  funciona (valor de un solo uso que el backend guarda antes de mostrar el botón), pero
  **exige un GET al backend antes de que el botón sirva**. Eso devuelve exactamente el
  problema que hizo descartar el redirect OAuth en §1: en Render free el usuario esperaría
  ~20-30 s de cold start **antes** de poder tocar "Entrar con Google". Se paga un costo de
  entrada cierto y grande, en el flujo que §1 optimizó, por cerrar un riesgo que requiere
  que el token ya se haya filtrado.
- **Guard de un solo uso en memoria del proceso — descartado por no ser un cierre real.**
  Dos motivos, ambos suficientes: **(a)** el registro vive en el proceso y **se pierde en
  cada reinicio o redeploy** — en Render free, que además duerme, la ventana de "ya lo
  usé" desaparece sola; **(b)** `(sub, iat)` **no identifica un token único**: `iat` tiene
  resolución de segundo, así que dos tokens legítimos emitidos en el mismo segundo para el
  mismo usuario colisionan, y el guard rechazaría un login válido. Un mecanismo que se
  olvida solo y produce falsos positivos no es una defensa, es una fuente de bugs.

#### Mitigaciones exigidas — estas sí son obligatorias

1. **HTTPS extremo a extremo.** Producción ya lo es en Vercel y Render; ningún entorno que
   exponga este endpoint puede servirlo por HTTP.
2. **El token viaja en el cuerpo del POST**, nunca en la query string ni en la URL. Una
   query string queda en logs de acceso, en el `Referer` y en el historial del navegador;
   un body, no.
3. **El ID token NUNCA se registra.** Ni en logs de acceso, ni en logs de error, ni en
   trazas, ni en un `print` de depuración, ni serializado dentro de un reporte de
   excepción. Al capturar `JWTError` se registra **el tipo de fallo**, jamás el token que
   lo causó. Es la mitigación que más importa: la vía realista de filtración de un ID token
   no es la red, es **nuestro propio logging**. Tiene criterio de aceptación propio.

**Son tres, no cuatro.** El ID token de Google se verifica, se usa para resolver la cuenta
y se descarta (decisión 3) — eso es higiene, no una mitigación del replay: no acorta la
ventana de canje ni la de la sesión resultante.

#### Decisión pendiente (NO se toca en esta tarea): bajar `JWT_EXPIRA_MINUTOS`

**Recomendación: bajar de 1440 a 4-8 horas.** No forma parte de TASK-015 y **no se cambia
aquí** — afecta a todos los logins, no solo a los de Google, y merece decidirse aparte.
Queda anotado con el argumento para que se decida, no para que se aplique de contrabando:

- **Es lo que acota el impacto de esta sección.** Sin antirreplay (y sin Redis para el
  guard por `jti`), la duración del JWT propio **es** la superficie del riesgo. Bajarla a
  8 h la reduce 3×; a 4 h, 6×. Es la palanca disponible hoy, sin infraestructura nueva.
- **Volver a entrar cuesta un clic.** Con login de Google el usuario ya tiene sesión activa
  en el teléfono: reautenticarse es tocar el botón, no recordar una contraseña. El motivo
  histórico de una sesión de 24 h —no querer que la gente reescriba su contraseña en un
  teclado de celular— desaparece justamente con esta tarea.
- **No hay refresh token** (está en "Fuera de alcance"), así que un `exp` largo es hoy el
  único mecanismo de continuidad. Ese es el argumento real a favor de 1440, y por eso la
  recomendación es **4-8 h y no 1 h**: hay que equilibrar, no minimizar.
- Si se aplica, es un cambio de una línea en `.env` / Render, sin migración ni código.

#### El cierre real, para cuando haya Redis

**Guard por `jti` con TTL en Redis.** Cuando exista Redis en producción —hoy no hay—, se
registra el `jti` del ID token con TTL igual al `exp` restante y se rechaza el segundo
canje del mismo token. `jti` **sí** identifica un token único, que es lo que `(sub, iat)`
no hace, y Redis sobrevive al reinicio del proceso y se comparte entre instancias, que es
lo que la memoria del proceso no hace. Las dos objeciones al guard en memoria caen a la
vez, y por eso este es el cierre correcto y no una versión mejor del descartado.

**Queda fuera de esta tarea** porque introducir Redis es una decisión de infraestructura
con su propio costo y su propia tarea. Si el `jti` no viniera en los ID tokens de Google,
la clave sería el hash del token completo — pero eso se verifica al implementarlo, no
ahora.

**Consecuencia de contrato:** `GoogleLoginEntrada` es **`{ id_token: str }`** y nada más.
El frontend **no** inicializa GIS con `nonce` ni manda nada extra; el acoplamiento que la
revisión 2 había creado con la tarea de frontend **desaparece**.

---

## 6. Consecuencia obligatoria en `/auth/login`

Hoy `router.py:60` hace `verificar_password(form.password, usuario.password_hash)`. Con
`password_hash` nullable, un usuario creado por Google que intente entrar por el
formulario de contraseña llega a `passlib` con `None` y revienta con `TypeError` →
**HTTP 500**. Sería un 500 por una condición de negocio perfectamente esperable, que es
exactamente lo que §10.2 prohíbe.

**`/auth/login` debe tratar `password_hash IS NULL` como credencial inválida y responder
401**, con el **mismo mensaje genérico** que hoy ("Email o password incorrectos"). No
decir "esa cuenta usa Google": revelaría qué correos están registrados y con qué
proveedor, a cualquiera que pruebe. La pista de que existe login con Google la da el
botón en la pantalla, no la respuesta de la API.

Este es el cambio no obvio de la tarea y **tiene prueba propia** en el criterio de
aceptación.

---

## 7. Credenciales y variables de entorno

**Costo: gratis.** Google Identity Services / Sign in with Google no tiene cuota ni
facturación. Solo hace falta un proyecto en Google Cloud Console con una **credencial
OAuth 2.0 de tipo "Aplicación web"** y la pantalla de consentimiento configurada.

**Un único `client_id` para backend y frontend.** El mismo valor va a los dos lados: el
frontend lo usa para pedir el token, el backend para exigirlo en `aud`. Si difieren,
**todos** los logins dan 401 — y es el primer sitio donde mirar si eso pasa.

| Dónde | Variable | Valor | Secreto |
|---|---|---|---|
| Backend (Render + `.env`) | `GOOGLE_CLIENT_ID` | `<id>.apps.googleusercontent.com` | no lo es, pero va como `sync: false` en `render.yaml` por consistencia con el resto |
| Frontend (Vercel + `.env.local`) | `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | **el mismo valor** | público por diseño: se inlinea en el build y viaja en el HTML |

**No se necesita `client_secret`** (§1): el flujo de ID token no lo usa. Si aparece uno en
la configuración de Render, sobra y hay que quitarlo.

El issuer y la URL del JWKS (`https://www.googleapis.com/oauth2/v3/certs`) van como
**constantes del módulo**, no como env vars: no son secretos, no cambian por entorno y
cada variable de más es una forma más de desplegar mal. Los tests las sustituyen por
monkeypatch, no por entorno.

**En Google Cloud Console hay que registrar "Orígenes de JavaScript autorizados"**
(no "URIs de redireccionamiento", que este flujo no usa): la URL de producción del
frontend (`https://consulta-placas-web.vercel.app`) y `http://localhost:3000` para dev.
**Limitación conocida, no es un bug:** los *preview deploys* de Vercel reciben un
subdominio distinto en cada push y GIS los rechazará. Se prueba en local y en producción.

---

## Alcance de archivos

**Permitido crear:**

- `alembic/versions/0025_login_google.py`
- `src/modules/auth/google.py` — verificación del ID token + caché de JWKS
- `tests/test_login_google.py`

**Permitido modificar:**

- `src/modules/auth/models.py` — las 3 columnas nuevas + `password_hash` a `str | None`
- `src/modules/auth/schemas.py` — `GoogleLoginEntrada` (**solo `id_token`**, §5.6)
- `src/modules/auth/router.py` — los endpoints `/auth/google` y `/auth/google/vincular`
  (§3.1) **y** la guarda de `password_hash IS NULL` en `/auth/login` (§6)
- **`requirements.txt` — SOLO** para cambiar `python-jose[cryptography]>=3.3.0` por
  `python-jose[cryptography]==3.5.0` (§5.1). **Ninguna línea más**: agregar un paquete
  sigue prohibido.
- `.env.example`, `render.yaml`, `docs/despliegue.md` — la variable nueva
- `docs/ORDEN-DE-TRABAJO.md`, `docs/bitacora.md`

**Prohibido tocar:** `src/modules/auth/security.py` y `src/modules/auth/dependencies.py`
(los fija la decisión 3), `src/core/database.py` (la config se lee en el módulo, como
`GOOGLE_VISION_API_KEY`), `src/registry.py` (no hay modelo nuevo), `main.py` (el router
de auth ya está incluido en la línea 48), cualquier otro módulo de `src/`, `Dockerfile`
y el repo frontend.

**Si crees necesitar algo fuera de esta lista, repórtalo en vez de agregarlo.** En
particular: si te encuentras **agregando un paquete** a `requirements.txt`, detente — §5.1
dice que no hace falta ninguno, y si hiciera falta es que el enfoque cambió y hay que
acordarlo. El pin de `python-jose` es la única edición prevista de ese archivo.

---

## Criterio de aceptación

Cada punto se comprueba corriendo algo. Nada de "funciona bien".

- [ ] `python -c "import main"` termina sin error.
- [ ] `python -c "import main; p=main.app.openapi()['paths']; print(len(p), sum(len(v) for v in p.values())); print('/auth/google' in p, '/auth/google/vincular' in p)"`
      imprime **`53 66`** y **`True True`** (hoy son 51/64, medido; entran **dos**
      endpoints, §3 y §3.1).
- [ ] `grep -n "python-jose" requirements.txt` muestra **`python-jose[cryptography]==3.5.0`**
      y `git diff requirements.txt` no toca ninguna otra línea (§5.1).
- [ ] `alembic heads` resuelve a **una sola cabeza**, y es `0025`.
- [ ] `alembic upgrade head` corre limpio contra Postgres real y
      `psql "$DATABASE_URL" -c "\d usuarios"` muestra `password_hash` **nullable**, las 3
      columnas nuevas, el CHECK del proveedor y el índice **único** `ix_usuarios_id_google`.
- [ ] `psql "$DATABASE_URL" -c "SELECT count(*) FROM usuarios WHERE proveedor_autenticacion <> 'local' OR email_verificado IS NOT false;"`
      devuelve **0** tras el upgrade: ninguna cuenta preexistente cambió de significado.
- [ ] `alembic downgrade -1` corre limpio **cuando no hay usuarios de Google**, y
      **aborta con mensaje legible** (no con un error de Postgres) cuando existe al menos
      una fila con `password_hash IS NULL`. Demostrar los dos casos.
- [ ] `python -m unittest tests.test_login_google -v` pasa, cubriendo **como mínimo**:
  - [ ] alta nueva → 200 con JWT propio válido (`decodificar_token` devuelve el email),
        `id_google` poblado, `password_hash IS NULL`, `saldo_tokens == 5` y **exactamente
        una** `TransaccionToken` con `motivo="saldo_inicial"`.
  - [ ] usuario **de gmail.com** existente por email → 200, **`saldo_tokens` no cambia** y
        **no** se agrega una segunda `TransaccionToken` (prueba de "solo una vez").
  - [ ] email con distinta capitalización (`Marcos@Gmail.com` en BD, `marcos@gmail.com`
        en el token) → **vincula la cuenta existente**, no crea una segunda.
  - **Autoritatividad (§0.1) — el bloque crítico de esta revisión:**
    - [ ] cuenta existente `juan@hotmail.com` + token `email_verified: true` **sin `hd`**
          → **409**, y en la BD **no** cambia nada: `id_google` sigue `NULL`, no se creó
          una segunda fila, `saldo_tokens` intacto. Es la prueba de que la toma de cuenta
          quedó cerrada.
    - [ ] la misma cuenta pero con token que **sí** trae `hd` → **200** y vincula.
    - [ ] `googlemail.com` se trata igual que `gmail.com` → vincula.
    - [ ] correo **no autoritativo que NO existe** en `usuarios` → **200 y alta normal**
          (la autoritatividad no bloquea altas, solo enlaces).
    - [ ] `identidad_google_autoritativa` probada **como función**, sin HTTP, con la matriz
          de casos: gmail / googlemail / `hd` presente / `hd` vacío / sin `hd` /
          `email_verified: false`.
  - [ ] **`/auth/google/vincular` (§3.1):** con JWT propio válido, vincula un token **no
        autoritativo** → **200** (autenticarse reemplaza la autoritatividad); sin JWT
        propio → **401**; sobre una cuenta que ya tiene otro `id_google` → **409**; con un
        `sub` ya vinculado a otra cuenta → **409, no 500**; y **no acredita tokens**.
  - [ ] `aud` de otro `client_id` → **401**.
  - [ ] **token sin claim `aud`** → **401** (prueba directa de `require_aud`).
  - [ ] **`aud` como lista `[nuestro_client_id, otro_client_id]`** → **401** (§5.2). Sin
        esta prueba, el bug pasa desapercibido: `jose` lo acepta.
  - [ ] **`azp` presente y distinto de `GOOGLE_CLIENT_ID`**, con `aud` correcto → **401**.
  - [ ] **token sin claim `exp`** → **401** (prueba directa de `require_exp`).
  - [ ] `iss` desconocido → **401**; token **sin** `iss` → **401**; y los **dos** issuers
        legítimos de Google → 200.
  - [ ] token con `exp` en el pasado → **401**.
  - [ ] firma hecha con otra clave RSA → **401**.
  - [ ] **`kid` de la cabecera que apunta a una clave distinta de la que firmó** → **401**
        (§5.3). Con el set completo pasado a `jose` esto daría 200: es la prueba de que se
        selecciona **una** JWK por `kid` y no se prueban todas.
  - [ ] **cabecera sin `kid`** → **401**, y el doble de prueba del JWKS registra **cero**
        llamadas (§5.3 punto 3: no refrescar ante `kid` ausente).
  - [ ] **`kid` presente y desconocido** → se fuerza **un** refresco y, si sigue sin estar,
        **401** (§5.3 punto 4). Distinguir este caso del anterior es el objetivo de las dos
        pruebas: contar las llamadas al JWKS en cada una.
  - [ ] **Ráfaga paralela (§5.3.1) — obligatoria, no sustituible por una secuencial.**
        `ThreadPoolExecutor` con **N ≥ 20** peticiones simultáneas, mismo `kid` desconocido,
        contra un doble del JWKS que cuente invocaciones → el contador vale **exactamente
        1** y las 20 responden **401**. Sin el lock esto da ~N y la prueba debe fallar.
  - [ ] Un segundo `kid` desconocido **dentro** de los 5 min → **cero** llamadas nuevas al
        JWKS (el piso, leído dentro del lock).
  - [ ] token con `alg: none` o `alg: HS256` → **401**, nunca 200.
  - [ ] **`GoogleLoginEntrada` acepta solo `id_token`**: un body con un campo extra
        (`nonce`, por ejemplo) no lo exige el schema ni lo usa el endpoint (§5.6).
  - [ ] `email_verified: false` → **422**, y **no** se crea ni se vincula ninguna cuenta.
  - [ ] cuenta con `id_google` distinto al del token → **409**.
  - [ ] `GOOGLE_CLIENT_ID` vacío → **503**.
  - [ ] **`/auth/login` con un usuario de `password_hash IS NULL` → 401**, con el mensaje
        genérico y **sin excepción** (§6).
  - [ ] Ningún caso devuelve 500.
- [ ] `python -m unittest discover tests -v` — la suite completa sigue pasando.
- [ ] `git diff --stat` no toca ningún archivo fuera del alcance (`requirements.txt` sí
      aparece, con **una** línea cambiada: el pin de §5.1).
- [ ] `grep -rn "client_secret" src/ .env.example render.yaml` no devuelve nada.
- [ ] **El ID token nunca se registra (§5.6, mitigación 3).** `grep -rn "id_token"
      src/modules/auth/` — ninguna aparición dentro de un `print`, `logger.*`, f-string de
      log o `detail` de excepción; no se persiste en la BD. El handler de `JWTError`
      registra el **tipo** de fallo, no el token. Es la vía realista de filtración y por
      eso tiene criterio propio.
- [ ] Copy es-EC, tuteo, no agresivo, en todos los `detail` de error.

---

## Fuera de alcance

Frontend (repo hermano, tarea aparte — **sin acoplamientos**: solo manda `id_token`).
Redirect OAuth / authorization code. **Todo antirreplay** (§5.6): el `nonce` de cliente
(descartado por no funcionar), el `nonce` de servidor y el guard en memoria (descartados
con motivo), y el **guard por `jti` en Redis**, que es el cierre correcto y espera a que
haya Redis en producción. Login con Apple, Facebook o cualquier otro proveedor.
Desvincular Google de una cuenta. Ponerle
contraseña después a una cuenta creada por Google, y su inverso. Recuperación de
contraseña. Verificación de email para cuentas locales. Normalizar a minúsculas los
emails de `/auth/registro` (deuda preexistente). Migrar `email` a `citext` o a un índice
único funcional. Refresh tokens. Revocación de sesiones.

---

## Condiciones de BLOCKED

- ~~`BLOCKED: ¿qué proyecto de Google Cloud se usa y en qué estado está su pantalla de consentimiento?`~~
  **DECIDIDO el 2026-08-24 — proyecto nuevo, separado del de Vision.** Configuración
  acordada, a crear en `console.cloud.google.com` (paso manual del humano, no automatizable
  desde el repo):

  | Qué | Valor |
  |---|---|
  | Proyecto | **nuevo**, independiente del que tiene `GOOGLE_VISION_API_KEY` |
  | Pantalla de consentimiento | tipo **Externo** |
  | Scopes | **solo `email`, `profile`, `openid`** — ninguno más |
  | Credencial | ID de cliente OAuth → **Aplicación web** |
  | Orígenes de JavaScript autorizados | la URL de producción en Vercel + `http://localhost:3000` |
  | `client_secret` | **no hace falta** con GIS (§1, §7) |

  **Por qué proyecto separado:** aísla el radio de daño. Una credencial comprometida o una
  cuota agotada en el proyecto de Vision no toca el login, y al revés. Son capacidades sin
  relación entre sí y con ciclos de vida distintos.

  **Lo que queda pendiente y NO bloquea implementar:** el `client_id` que salga de ahí es lo
  único que la implementación necesita, y entra por env var (§7) — no se commitea.
  **Mientras la pantalla siga en *Testing* se puede desarrollar y probar** con hasta 100
  cuentas agregadas a mano, que sobra para el desarrollo.

  **Lo que sí bloquea el lanzamiento: publicar la pantalla.** En *Testing*, cualquier cuenta
  fuera de esa lista falla aunque el código esté perfecto. **Conviene iniciar la publicación
  pronto porque la verificación de Google demora** — es tiempo de espera de un tercero, no
  trabajo nuestro, y es el tipo de plazo que solo se descubre tarde. Arrancarlo temprano no
  cuesta nada; descubrirlo el día del lanzamiento, sí.
- ~~`BLOCKED: ¿hay en producción emails que difieran solo en mayúsculas?`~~
  **RESUELTO el 2026-08-24 — no hay ninguno.** Consultado contra la BD de producción
  (Neon): **6 usuarios en total, 0 grupos duplicados** con
  `SELECT lower(email), count(*) FROM usuarios GROUP BY 1 HAVING count(*) > 1;` → `[]`.
  La búsqueda insensible a mayúsculas de §3 no encontrará más de una fila y el 409 por esa
  causa no se disparará con los datos actuales.
  **Sigue haciendo falta el manejo del caso**, no se elimina del código: `/auth/registro`
  continúa siendo sensible a mayúsculas (deuda preexistente, fuera de alcance), así que
  **una colisión nueva se puede crear en cualquier momento** después de esta medición. El
  409 se implementa igual y se prueba igual; lo que este chequeo descarta es tener que
  arreglar datos existentes antes de desplegar.
- ~~Si al implementar aparece que `python-jose` no selecciona la clave por `kid`…~~
  **RESUELTO en la revisión 2: efectivamente no lo hace** (`jws.py`, verificado — prueba
  todas las claves del set). No es un BLOCKED, es un requisito: la selección por `kid` la
  hacemos nosotros según §5.3. **No** se agrega `google-auth` por esto.
- Si `email_verified` llegara como string `"true"` en vez de booleano en alguna variante
  del token, reportarlo en vez de ampliar la comparación por cuenta propia. La regla
  escrita es `is True`, a propósito.
