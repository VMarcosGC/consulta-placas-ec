# TASK-015 — Login con Google (sin contraseña)

| Campo | Valor |
|---|---|
| **Ruteo** | `claude-code` |
| **Motivo** | migración Alembic + contrato de auth + verificación criptográfica (§16) |
| **Rama** | `feat/TASK-015-login-google` |
| **Revisor** | Codex, contra este archivo, `AGENTS.md` y el checklist §5 de `docs/plan_market_autos.md` |
| **Estado** | spec lista — **no implementada** |

## Objetivo

Un usuario entra con su cuenta de Google y **nunca crea una contraseña**. El público
objetivo navega desde Android de gama baja y ya tiene sesión de Google iniciada en el
teléfono: pedirle que invente y recuerde una contraseña es la fricción más cara del
onboarding.

## Decisiones ya tomadas — no se reabren

1. **Vinculación por email.** Si el correo que llega de Google coincide con un usuario
   existente, es la **misma cuenta**. Google verifica el email; no se crea cuenta
   duplicada ni se pide confirmación adicional.
2. **`password_hash` pasa a nullable.** Un usuario de Google no tiene contraseña.
   Rellenarlo con un hash falso es peor: convierte "no puede entrar por contraseña" en
   "puede entrar si alguien adivina el placeholder".
3. **El backend sigue emitiendo SU propio JWT con `sub=<email>`.** El ID token de Google
   se valida y **se descarta**: no se guarda, no se reenvía, no se refresca.
   `usuario_actual`, `usuario_actual_opcional` y el contrato del frontend **no cambian**.

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
  `cryptography` (48.0.0) y `httpx` (0.28.1). Ver §5 de esta spec: **no hace falta
  ninguna dependencia nueva**.
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
  `--sql` (mismo cuidado que tomó `0021`).

---

## 3. `POST /auth/google` — resolución de la cuenta

Entrada: `GoogleLoginEntrada { id_token: str }` (JSON). Salida: el schema **`Token`** ya
existente, idéntico al de `/auth/login`. El frontend no distingue de dónde salió el JWT.

**Orden de resolución — este orden es normativo:**

1. **Por `id_google == sub`.** Si existe, esa es la cuenta, aunque su `email` ya no
   coincida con el que manda Google hoy. **El `email` guardado NO se actualiza**: es el
   `sub` de nuestro propio JWT y la clave de negocio de toda la app; reescribirlo
   invalidaría las sesiones vivas y podría chocar contra el índice único de `email`.
2. **Por `email` (comparación insensible a mayúsculas).** Si existe, se **vincula**:
   `id_google = sub`, `email_verificado = True`. `proveedor_autenticacion` **no se toca**
   (la cuenta se creó local y eso no cambia). **No se acreditan tokens** (§4).
3. **No existe → alta.** `Usuario(email=<email del claim>, password_hash=None,
   nombre=<claim name>, proveedor_autenticacion="google", id_google=sub,
   email_verificado=True)` **+ el saldo de cortesía** (§4).

> **La comparación por email debe ser insensible a mayúsculas y es un requisito, no un
> detalle.** `/auth/registro` guarda el email tal como lo escribió el usuario y todas las
> búsquedas actuales usan `==` exacto. Google devuelve el correo en minúsculas. Una cuenta
> registrada como `Marcos@Gmail.com` **no** haría match y el flujo crearía una segunda
> cuenta con el mismo correo real — violando la decisión 1 en silencio. Usar
> `func.lower(Usuario.email) == email.lower()`. Que `/auth/registro` siga siendo sensible
> a mayúsculas es deuda preexistente y **queda fuera de alcance**.

### Contrato de errores (§10.2 — nunca un 500)

| Código | Cuándo |
|---|---|
| **401** | firma inválida · `aud` distinto de nuestro `client_id` · `iss` desconocido · token expirado · `alg` fuera de `RS256`. Mensaje **genérico** ("Credenciales de Google inválidas"): no se detalla cuál claim falló. |
| **422** | `email_verified` es `false`, o el token no trae `email`. El token es legítimo pero la cuenta no sirve para identificar a nadie: es validación de negocio, no credencial mala. |
| **409** | la cuenta hallada por email ya tiene un `id_google` **distinto**; o la búsqueda insensible a mayúsculas devuelve **más de una** fila. Conflicto real que un humano debe resolver — nunca elegir una fila a dedo. |
| **503** | `GOOGLE_CLIENT_ID` sin configurar, o el JWKS es inalcanzable y no hay caché válida. Es fallo de despliegue, no del usuario (mismo precedente que `POST /consultar-foto` sin `GOOGLE_VISION_API_KEY`). |
| **422** (FastAPI) | body sin `id_token`. Lo produce Pydantic solo; no hay que escribirlo. |

---

## 4. Saldo de cortesía: exactamente una vez

`SALDO_INICIAL_TOKENS = 5` (§10.3) se acredita **solo en el caso 3** de §3 — la rama que
construye un `Usuario` nuevo. **Los casos 1 y 2 no acreditan nada.**

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

Vive en **`src/modules/auth/google.py`**, no en el router. Expone una sola función
pública: `verificar_id_token_google(id_token: str) -> ClaimsGoogle`.

### Librería: `python-jose` — **sin dependencias nuevas**

`python-jose[cryptography]` **ya está en `requirements.txt`** (lo usa `security.py` para
el JWT propio) y su `jose.jws._get_keys` acepta un **JWK Set completo** (`{"keys": [...]}`)
seleccionando la clave por `kid` — verificado en `.venv/Lib/site-packages/jose/jws.py:221-233`.
`httpx` ya está para traer el JWKS. **Cero dependencias nuevas** (§4).

La alternativa canónica sería `google-auth` (`id_token.verify_oauth2_token`), que trae el
JWKS y las validaciones empaquetadas. **Se descarta**: sumaría `google-auth` + `rsa` +
`pyasn1` + `pyasn1-modules` + `cachetools` a una imagen Docker que ya arrastra Playwright
y Chromium, para reemplazar unas 40 líneas que podemos escribir con lo instalado. La
contrapartida honesta es que las validaciones quedan a nuestro cargo — y por eso el
bloque siguiente es **normativo** y cada punto tiene una prueba negativa obligatoria.

### Llamada exacta y por qué cada opción está ahí

```python
jwt.decode(
    id_token,
    jwks,                      # el JWK Set completo; jose elige por `kid`
    algorithms=["RS256"],
    audience=GOOGLE_CLIENT_ID,
    issuer=("https://accounts.google.com", "accounts.google.com"),
    options={
        "require_aud": True,
        "require_exp": True,
        "require_iat": True,
        "require_sub": True,
        "verify_at_hash": False,
    },
)
```

Cada línea corrige un default de `python-jose` que, dejado como viene, **abre un agujero
de autenticación**. Verificado leyendo `.venv/Lib/site-packages/jose/jwt.py`:

- **`require_aud: True` es obligatorio.** `_validate_aud` (línea 354) hace
  `if "aud" not in claims: return` — **un token sin `aud` pasa en silencio**, porque
  `require_aud` viene en `False` (línea 142). Sin esto, un ID token emitido por Google
  para **cualquier otra aplicación** entraría a nuestra plataforma: es el fallo clásico
  de este flujo y el motivo por el que `aud` se valida contra **nuestro** `client_id`.
- **`issuer=` hay que pasarlo explícito.** `_validate_iss` (línea 384) hace
  `if issuer is not None:` — si no se pasa, **no valida nada**. Google emite las **dos**
  formas del issuer, con y sin esquema, así que se acepta la tupla de ambas y nada más.
- **`require_exp: True` es obligatorio.** `verify_exp` viene en `True`, pero
  `require_exp` en `False` (línea 143): un token **sin** `exp` no expira nunca y pasa.
- **`verify_at_hash: False` es obligatorio o el flujo no funciona.** `_validate_at_hash`
  (línea 440) lanza `JWTClaimsError` si el claim `at_hash` está presente y no se le pasó
  un `access_token`. En este flujo no existe access token que comparar. Desactivarlo no
  debilita nada: `at_hash` solo liga el ID token a un access token que aquí no hay.
- **`algorithms=["RS256"]` fija el algoritmo.** Nunca leer el `alg` de la cabecera del
  token para decidir con qué verificarlo: es la puerta de la confusión de algoritmos
  (`none`, o HS256 firmado con el JWKS público como secreto).

Todas las excepciones de jose (`ExpiredSignatureError`, `JWTClaimsError`) derivan de
`JWTError`: capturar `JWTError` y traducir a **401**, sin dejar escapar el mensaje
original al cliente.

### Claims que jose no conoce y hay que revisar a mano

- **`email_verified` debe ser exactamente `True`.** Es la única razón por la que la
  decisión 1 (vincular por email) es segura. Sin esa comprobación, cualquiera que cree
  una cuenta de Google Workspace con un correo ajeno sin verificar se apodera de la
  cuenta existente de esa persona. `false`, ausente o cualquier valor que no sea `True`
  → **422**.
- **`email` debe venir y no estar vacío** → si falta, **422**.
- **`sub` debe venir** (lo cubre `require_sub`, pero el código igual lo verifica antes de
  escribirlo en la columna).

### Caché de JWKS

Google rota sus claves y publicarlas es su único canal, así que el JWKS se pide por red —
pero **una vez por token sería abusivo y frágil**: si Google tarda, todos los logins se
caen. Reglas:

- Caché **en memoria del proceso**, TTL **1 hora**, honrando el `max-age` del header
  `Cache-Control` de la respuesta cuando sea parseable.
- **Refresco forzado ante un `kid` desconocido** (así se absorbe una rotación sin esperar
  al TTL), con un **piso de 5 minutos entre refrescos forzados**: sin ese piso, un token
  basura con un `kid` inventado convierte cada request en un golpe a Google — justo lo que
  el skill `scraping-respetuoso` prohíbe.
- Cliente **`httpx.Client` síncrono**, timeout de 5 s. Los handlers de `auth/router.py`
  son `def` síncronos; meter `AsyncClient` ahí obligaría a cambiar el router.
- JWKS inalcanzable **y** sin caché válida → **503**. Con caché aún válida, se sirve de
  caché y **no** se falla.

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
- `src/modules/auth/schemas.py` — `GoogleLoginEntrada`
- `src/modules/auth/router.py` — el endpoint `/auth/google` **y** la guarda de
  `password_hash IS NULL` en `/auth/login` (§6)
- `.env.example`, `render.yaml`, `docs/despliegue.md` — la variable nueva
- `docs/ORDEN-DE-TRABAJO.md`, `docs/bitacora.md`

**Prohibido tocar:** `src/modules/auth/security.py` y `src/modules/auth/dependencies.py`
(los fija la decisión 3), `src/core/database.py` (la config se lee en el módulo, como
`GOOGLE_VISION_API_KEY`), `src/registry.py` (no hay modelo nuevo), `main.py` (el router
de auth ya está incluido en la línea 48), cualquier otro módulo de `src/`, `Dockerfile`,
`requirements.txt` y el repo frontend.

**Si crees necesitar algo fuera de esta lista, repórtalo en vez de agregarlo.** En
particular: si te encuentras editando `requirements.txt`, detente — §5 de esta spec dice
que no hace falta, y si hiciera falta es que el enfoque cambió y hay que acordarlo.

---

## Criterio de aceptación

Cada punto se comprueba corriendo algo. Nada de "funciona bien".

- [ ] `python -c "import main"` termina sin error.
- [ ] `python -c "import main; p=main.app.openapi()['paths']; print(len(p), sum(len(v) for v in p.values())); print('/auth/google' in p)"`
      imprime **`52 65`** y **`True`** (hoy son 51/64, medido).
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
  - [ ] usuario existente por email → 200, **`saldo_tokens` no cambia** y **no** se agrega
        una segunda `TransaccionToken` (esta es la prueba de "solo una vez").
  - [ ] email con distinta capitalización (`Marcos@Gmail.com` en BD, `marcos@gmail.com`
        en el token) → **vincula la cuenta existente**, no crea una segunda.
  - [ ] `aud` de otro `client_id` → **401**.
  - [ ] **token sin claim `aud`** → **401** (prueba directa de `require_aud`).
  - [ ] **token sin claim `exp`** → **401** (prueba directa de `require_exp`).
  - [ ] `iss` desconocido → **401**; y los **dos** issuers legítimos de Google → 200.
  - [ ] token con `exp` en el pasado → **401**.
  - [ ] firma hecha con otra clave RSA → **401**.
  - [ ] token con `alg: none` o `alg: HS256` → **401**, nunca 200.
  - [ ] `email_verified: false` → **422**, y **no** se crea ni se vincula ninguna cuenta.
  - [ ] cuenta con `id_google` distinto al del token → **409**.
  - [ ] `GOOGLE_CLIENT_ID` vacío → **503**.
  - [ ] **`/auth/login` con un usuario de `password_hash IS NULL` → 401**, con el mensaje
        genérico y **sin excepción** (§6).
  - [ ] JWKS con `kid` desconocido → se fuerza **un** refresco; un segundo intento dentro
        de los 5 min **no** vuelve a pedir el JWKS (contar las llamadas al doble de prueba).
  - [ ] Ningún caso devuelve 500.
- [ ] `python -m unittest discover tests -v` — la suite completa sigue pasando.
- [ ] `git diff --stat` no toca `requirements.txt` ni ningún archivo fuera del alcance.
- [ ] `grep -rn "client_secret" src/ .env.example render.yaml` no devuelve nada.
- [ ] `grep -n "id_token" src/modules/auth/router.py` — el ID token de Google **no** se
      persiste en la BD ni se escribe en ningún log.
- [ ] Copy es-EC, tuteo, no agresivo, en todos los `detail` de error.

---

## Fuera de alcance

Frontend (repo hermano, tarea aparte). Redirect OAuth / authorization code. Login con
Apple, Facebook o cualquier otro proveedor. Desvincular Google de una cuenta. Ponerle
contraseña después a una cuenta creada por Google, y su inverso. Recuperación de
contraseña. Verificación de email para cuentas locales. Normalizar a minúsculas los
emails de `/auth/registro` (deuda preexistente). Migrar `email` a `citext` o a un índice
único funcional. Refresh tokens. Revocación de sesiones.

---

## Condiciones de BLOCKED

- `BLOCKED: ¿qué proyecto de Google Cloud se usa — el que ya tiene la GOOGLE_VISION_API_KEY o uno nuevo — y en qué estado de publicación está su pantalla de consentimiento OAuth?`
  No es determinable leyendo el repo y **es bloqueante para producción**: una pantalla en
  estado *Testing* solo admite hasta 100 usuarios de prueba listados explícitamente; con
  cualquier otro, el login falla para usuarios reales aunque el código esté perfecto. Hay
  que pasarla a *In production*. El código se puede escribir y probar sin esta respuesta;
  **el despliegue no**.
- `BLOCKED: ¿hay en producción emails que difieran solo en mayúsculas?`
  Comprobarlo antes de exponer el endpoint, con
  `SELECT lower(email), count(*) FROM usuarios GROUP BY 1 HAVING count(*) > 1;`.
  Si devuelve filas, la búsqueda insensible a mayúsculas de §3 encontrará más de una
  cuenta y el endpoint responderá 409 para esas personas. **No resolverlo por cuenta
  propia eligiendo una fila**: es una decisión de datos que toma un humano.
- Si al implementar aparece que `python-jose` **no** selecciona la clave por `kid` dentro
  de un JWK Set con las versiones instaladas, **detenerse y reportarlo** antes de agregar
  `google-auth`: cambia la justificación de dependencias de §5 y hay que acordarlo.
- Si `email_verified` llegara como string `"true"` en vez de booleano en alguna variante
  del token, reportarlo en vez de ampliar la comparación por cuenta propia. La regla
  escrita es `is True`, a propósito.
