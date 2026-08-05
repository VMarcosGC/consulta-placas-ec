# TASK-010 — Separar el entorno local de producción (`.env.local` con precedencia)

| Campo | Valor |
|---|---|
| **Ruteo** | `codex` |
| **Motivo** | tarea cercada, un archivo de código y criterio de aceptación obvio (§16) |
| **Rama** | `fix/TASK-010-entorno-local` |
| **Revisor** | Claude Code (§16.1 — revisa quien no ejecutó) |

## Objetivo

Que trabajar en local **no requiera acordarse de nada**. Hoy el default local es
producción: si olvidas exportar `DATABASE_URL`, cualquier comando —incluido
`alembic upgrade head`— apunta a **Neon de producción**.

## El problema, con precisión

`alembic/env.py` toma la URL de `src/core/database.py`, que hace:

```python
load_dotenv()                                   # lee .env  → Neon (producción)
DATABASE_URL = os.getenv("DATABASE_URL", "...")
```

`load_dotenv()` lee **`.env` y nada más**. El archivo `.env.local` que existe en la raíz
**no lo lee nadie**: es documentación con forma de configuración. Lo único que hoy evita
correr contra Neon es exportar la variable a mano en cada invocación:

```bash
DATABASE_URL='postgresql+psycopg://postgres:dev@127.0.0.1:5433/mi_base' python -m alembic upgrade head
```

Funciona porque `load_dotenv()` **no sobrescribe** variables ya presentes en el entorno.
Pero el fallo es silencioso y asimétrico: si te olvidas, no hay error — la migración se
aplica, y se aplica en producción.

## Qué hay que hacer

En `src/core/database.py`, cargar `.env.local` **antes** que `.env`, ambos sin `override`
y ambos **anclados a la raíz del proyecto**:

```python
from pathlib import Path

# `database.py` vive en `src/core/`, así que parents[2] es la raíz del repo.
RAIZ = Path(__file__).resolve().parents[2]
load_dotenv(RAIZ / ".env.local")   # si existe, gana
load_dotenv(RAIZ / ".env")         # base; no pisa lo ya definido
```

### Por qué anclado a la raíz y NO con rutas relativas

Es el error que se cometió en la primera implementación y que la auditoría detectó. Con
`load_dotenv(".env.local")` y `load_dotenv()` a secas, los dos archivos se localizan por
mecanismos **distintos**:

- `load_dotenv(".env.local")` resuelve una ruta **relativa al CWD**.
- `load_dotenv()` sin argumentos usa `find_dotenv()`, que camina **hacia arriba desde el
  archivo del módulo**, y por eso encuentra `.env` sin importar el CWD.

Arrancando desde un **subdirectorio** del repo (`src/`, `alembic/`, `scripts/`, o cualquier
configuración de VS Code cuyo CWD sea la carpeta del archivo), `.env` se encuentra y
`.env.local` **no**: la app cae a `.env` —producción— **sin un solo aviso**. Es exactamente
el fallo silencioso que esta tarea existe para eliminar, solo que desplazado de "olvidé
exportar la variable" a "arranqué desde otra carpeta".

Anclar ambas rutas a `RAIZ` vuelve el comportamiento independiente del CWD. **Verifícalo
desde un subdirectorio**, no solo desde la raíz (ver criterio de aceptación).

### Por qué ese orden y NO `override=True`

`load_dotenv(..., override=False)` (el default) solo define lo que **todavía no** está
definido. Cargando `.env.local` primero, la precedencia resultante es:

**variable real del entorno > `.env.local` > `.env`**

Es la que queremos. Con `load_dotenv(".env.local", override=True)` la precedencia se
invierte y `.env.local` pisaría una variable exportada a propósito — y, peor, pisaría las
variables reales que inyecta Render si el archivo llegara a colarse en la imagen.

**No inventes un orden distinto ni agregues una variable de "entorno activo"**: el
mecanismo tiene que ser el mínimo que resuelve el problema.

## Alcance de archivos

**Permitido tocar:**

- `src/core/database.py` — las dos líneas de carga y un comentario que explique la
  precedencia.
- `.env.example` — documentar que `.env.local` existe, para qué sirve y que gana sobre
  `.env`.
- `docs/despliegue.md` — nota breve del flujo local vs producción.
- `.dockerignore` — **agregar `.env.local`. No es limpieza opcional: es requisito.**

### Por qué `.dockerignore` es parte de la tarea, no un extra

El archivo ya existe y excluye `.env`, pero **no** `.env.local`, y el `Dockerfile` hace
`COPY . .` (línea 18). Hoy eso es inocuo: nadie lee `.env.local` y, como está en
`.gitignore`, tampoco llega al build de Render, que clona el repo.

Cambia en cuanto esta tarea le dé **precedencia**. Un `docker build` local con un
`.env.local` presente hornearía dentro de la imagen un `DATABASE_URL` apuntando a
`127.0.0.1:5433`, y esa URL **ganaría sobre las variables reales** que inyecta el entorno
al arrancar el contenedor. El backend intentaría hablar con un Postgres que no existe ahí.
El cambio de precedencia y la exclusión del build tienen que entrar juntos.

**Prohibido tocar:** `alembic/env.py`, cualquier módulo de `src/modules/`, migraciones,
`render.yaml`, `Dockerfile`, y el repo frontend.

## Criterio de aceptación

- [ ] Con `.env.local` presente y `DATABASE_URL` **no** exportada, `python -c "from
      src.core.database import DATABASE_URL; print(DATABASE_URL)"` imprime la URL local.
- [ ] Con `DATABASE_URL` exportada a otro valor, **gana la exportada** (la variable real
      del entorno sigue teniendo la última palabra).
- [ ] Renombrando temporalmente `.env.local`, se vuelve a leer `.env` sin error.
- [ ] Los tres casos de precedencia anteriores se prueban tanto desde la raíz del
      proyecto como desde un subdirectorio, para comprobar que la ubicación de los
      archivos no depende del CWD.
- [ ] `python -c "import main"` sin error y con el mismo conteo de rutas que antes.
- [ ] `.env.local` sigue en `.gitignore` y `git status` no lo muestra.
- [ ] `.env.local` está en `.dockerignore`.
- [ ] `.env.example` explica el flujo.

## Fuera de alcance

Cualquier guardarraíl que **bloquee** migraciones contra hosts remotos (abortar si la URL
no es localhost, pedir confirmación, etc.). Es una idea razonable y separable: si el
implementador la ve necesaria, la propone como TASK-011, no la mete aquí. Tampoco entra
cambiar `alembic/env.py`, ni introducir `pydantic-settings` para la configuración.

## Condiciones de BLOCKED

- Si al cambiar el orden de carga alguna variable existente cambia de valor en local
  (revisar `.env` contra `.env.local`: `JWT_SECRET_KEY`, `CORS_ORIGINS`, credenciales de
  Cloudinary), **reportar antes de continuar**: la tarea es redirigir la BD, no alterar en
  silencio el resto de la configuración.

## Contexto útil

El ciclo de migraciones del 2026-08-05 (ver bitácora) se corrió contra el contenedor
`pg-dev` en `localhost:5433` (`postgres`/`dev`), que **queda levantado** junto con las
bases `task001_head`, `task001_backfill` y `task001_ref`. Sirven para probar esta tarea
sin crear nada nuevo.
