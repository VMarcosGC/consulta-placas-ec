# TASK-001 — Capa Vendedor y contacto comprador-vendedor

| Campo | Valor |
|---|---|
| **Ruteo** | `claude-code` |
| **Motivo** | migración Alembic + cambio de modelo que cruza módulos (§16) |
| **Rama** | `feat/TASK-001-contacto-vendedor` |
| **Revisor** | Codex, contra este archivo, `AGENTS.md` y el checklist §5 de `docs/plan_market_autos.md` |

## Objetivo

Un comprador puede contactar al vendedor de una publicación por WhatsApp desde el
detalle del anuncio. Hoy no existe ninguna vía: el marketplace no cierra el circuito.

## Contexto mínimo

- `Usuario` es una cuenta de autenticación (email, password, nombre, saldo). No
  tiene teléfono, y el teléfono de contacto **no va ahí**: es un dato comercial,
  no de cuenta.
- `PublicacionInterna` y `PublicacionReferenciada` cuelgan hoy de `usuario_id`.
- Solo hay 2 publicaciones internas y 3 referencias en producción. La capa
  `Vendedor` cuesta casi nada ahora y evita una migración de cuatro tablas con
  datos reales cuando lleguen los patios (§1.0.4).
- Última migración: `0020_favorito_precio.py`.

## Alcance de archivos

> **Corregido el 2026-08-04.** La versión original de esta spec permitía tocar
> `src/modules/marketplace/router.py`, que **no existe**: el módulo tiene varios
> grupos de endpoints y por eso están repartidos en `routers/` (`marketplace.py`,
> `publicaciones.py`, `referencias.py`, `compartidos.py`), que es lo que manda
> AGENTS §5. La spec estaba mal escrita, no el repo. Alcance corregido abajo.

**Permitido tocar:**

- `alembic/versions/0021_vendedor.py` (nuevo)
- `alembic/versions/0022_contacto_revelado.py` (nuevo)
- `src/modules/marketplace/models.py`
- `src/modules/marketplace/schemas.py`
- `src/modules/marketplace/routers/vendedor.py` (nuevo) — los dos endpoints de
  `vendedor/mi-perfil`, con `APIRouter(prefix="/marketplace/vendedor")`
- `src/modules/marketplace/routers/publicaciones.py` — solo para agregar
  `POST /publicaciones/{id}/contacto`, junto a las demás rutas de ese prefijo
- `main.py` — **una sola línea** de `include_router` del router nuevo
- `src/registry.py`
- `tests/test_contacto_vendedor.py` (nuevo)

**Prohibido tocar:** `src/modules/auth/`, `src/modules/tokens/`,
`src/modules/consulta/`, `Dockerfile`, `render.yaml`, cualquier archivo de
despliegue, y el repo frontend (va en tarea aparte).

## Modelo

### `Vendedor` (nuevo)

| Campo | Tipo | Nota |
|---|---|---|
| `id` | BigInteger PK | |
| `usuario_id` | FK `usuarios.id` ON DELETE CASCADE, **UNIQUE** | la UK impone 1:1 en etapa 1; se levanta en etapa 2 |
| `tipo` | Enum `particular` \| `patio` | `particular` por defecto y único valor usado en este ciclo |
| `nombre_publico` | String(120) | por defecto el nombre del usuario |
| `telefono` | String(20) nullable | E.164 sin `+` (ej. `593987654321`) |
| `telefono_verificado` | Boolean default false | reservado; no se usa en este ciclo |
| `creado_en` / `actualizado_en` | timestamptz | patrón existente |

`PublicacionInterna` y `PublicacionReferenciada` reciben `vendedor_id`.
`usuario_id` **se conserva** en ambas: en referenciadas documenta al aportante,
que no siempre es el vendedor. No se borra ninguna columna en esta tarea.

### `ContactoRevelado` (nuevo)

Registro anónimo de cada revelación: `id`, `publicacion_interna_id` (nullable),
`publicacion_referenciada_id` (nullable), `creado_en`. **Sin identificar al
comprador**: no se guarda IP, user-agent ni usuario. Es una métrica de producto,
no de vigilancia (§9).

Exactamente uno de los dos FK debe estar presente: CheckConstraint.

### Migraciones

Manuales, numeradas, con `downgrade`, revisadas a mano (nunca `--autogenerate`
a ciegas). Backfill en `0021`: un `Vendedor` por cada usuario con publicaciones,
`nombre_publico` = `usuario.nombre`, `telefono` NULL, y `vendedor_id` poblado en
ambas tablas. `alembic heads` debe resolver a una sola cabeza.

## Endpoints

**`PATCH /marketplace/vendedor/mi-perfil`** — el vendedor fija su
`nombre_publico` y `telefono`. `Depends(usuario_actual)`. Crea el `Vendedor` si
no existe. Valida formato de teléfono ecuatoriano: celular de 10 dígitos
(`09XXXXXXXX`) o E.164 (`5939XXXXXXXX`); se normaliza a E.164 al guardar.
Teléfono inválido → **422**.

**`GET /marketplace/vendedor/mi-perfil`** — devuelve el perfil propio.

**`POST /marketplace/publicaciones/{publicacion_id}/contacto`** — devuelve el
teléfono y registra la revelación. **Público**, sin auth y **sin cobro**.

- Vendedor sin teléfono cargado → **409** ("dato no disponible"), nunca 500.
- Publicación inexistente o no visible públicamente → **404**.
- Devuelve `{ "telefono": "...", "nombre_publico": "...", "whatsapp_url": "..." }`.
- `whatsapp_url` se arma como `https://wa.me/<telefono>` con un mensaje
  prellenado en español es-EC, no agresivo.

**Orden de declaración:** las rutas literales van **antes** que las dinámicas del
mismo prefijo (§5). Con el alcance corregido, `vendedor/mi-perfil` vive en su
propio router con prefijo `/marketplace/vendedor`, así que **no puede colisionar**
con `/marketplace/publicaciones/{id}`. Donde sí aplica la regla es dentro de
`routers/publicaciones.py`: `POST /publicaciones/{id}/contacto` debe declararse
**antes** de `GET /publicaciones/{publicacion_id}`, que hoy está deliberadamente
al final del archivo para no capturar `mias` ni `pendientes-verificacion`.

## Visibilidad del teléfono

El teléfono **no aparece** en `GET /feed`, `GET /buscar` ni en el detalle de la
publicación. Solo lo devuelve el endpoint de contacto, bajo una acción explícita
del comprador.

Esto es **privacidad, no monetización** (§1.0.3: el contacto es libre). Un
teléfono servido en listados públicos lo cosechan bots en días. La acción
explícita es la barrera contra scraping automatizado, y de paso produce la
métrica de contactos.

## Criterio de aceptación

- [ ] `python -c "import main"` sin error
- [ ] `alembic heads` resuelve a una sola cabeza
- [ ] `alembic upgrade head` y luego `downgrade` de ambas migraciones corren limpio
- [ ] Las 3 rutas nuevas existen en `app.openapi()["paths"]`
- [ ] `pytest tests/test_contacto_vendedor.py -q` pasa, cubriendo: teléfono válido
      normalizado a E.164; teléfono inválido → 422; contacto sin teléfono cargado
      → 409; publicación inexistente → 404; contacto exitoso inserta exactamente
      una fila en `ContactoRevelado`
- [ ] `grep -r "telefono" src/modules/marketplace/schemas.py` — el campo no
      aparece en ningún schema de listado ni de detalle
- [ ] Backfill verificado: toda publicación existente quedó con `vendedor_id`

## Fuera de alcance

Frontend (tarea aparte, repo hermano). Mensajería interna. Verificación del
teléfono por SMS/OTP. Cobro por revelar el contacto. Tipo `patio` y relación N:1.
Eliminar `usuario_id` de las tablas de publicación. Métricas agregadas de contacto.

## Condiciones de BLOCKED

- Si el backfill de `0021` encuentra publicaciones cuyo `usuario_id` no existe en
  `usuarios`, detenerse y reportar: hay datos inconsistentes que decidir antes.
- Si `src/modules/marketplace/router.py` no existe o los routers están repartidos
  de otra forma, reportar la estructura real antes de crear archivos.
- Si el formato de teléfono ecuatoriano acordado no cubre un caso real en datos
  existentes, preguntar en vez de ampliar la validación por cuenta propia.
