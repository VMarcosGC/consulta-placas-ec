# Orden de trabajo — ciclo marketplace

**Abierto:** 2026-08-04 · **Última actualización:** 2026-08-05

Este archivo es el **único planificador del ciclo**. La unidad de trabajo es la **spec
`TASK-NNN`** en [`docs/specs/`](specs/); aquí viven el estado, el orden y el porqué.

> **El eje M (M0→M5, MC1→MC3) deja de ser planificador.**
> [`plan_market_autos.md`](plan_market_autos.md) se conserva como **historia de lo
> construido** —qué se hizo en cada etapa, con qué decisiones y qué compuerta quedó
> abierta—, no como lo que viene. Cuando una etapa M siga viva, se dice aquí y se apunta
> a la spec TASK que la ejecuta. Tener dos ejes planificando a la vez fue lo que hizo que
> el mismo trabajo tuviera dos nombres (ver "Relación con el eje M", abajo).

---

## 1. Cerrado

Con evidencia. Nada de "hecho" sin dónde verificarlo.

### P0 — Proveedor `mock` cortado en producción ✅

`PROVEEDOR_VEHICULAR_ACTIVO=consultas_ec` en el dashboard de Render. Al no tener API key,
declara capacidades vacías y no ofrece ni cobra nada.

**Verificado en el catálogo público:** `identificadores_tecnicos`, `titular_validado` y
`reporte_compra_segura` responden `disponible: false`. Producción ya no cobra 3 y 5 tokens
por un VIN y un titular que el mock fabricaba.

El arreglo estructural —que el default sea nulo y `mock` requiera habilitación explícita—
sigue pendiente en **TASK-004**. Esto fue el corte inmediato.

### P1 — Frontend pusheado ✅

Los 3 commits que vivían solo en local desde el 20-25 de julio: `b953710..98372e4`
(`ad46440` M2.10 · `a4cb76d` MC2 · `98372e4` fix de `solo_cache`).

**Verificado sobre el sitio desplegado, no sobre el push:** los bundles de `/marketplace`
en Vercel contienen `solo_cache` y los marcadores de MC2. Con eso, la deuda de M2.6/M2.7
—el detalle público disparaba scraping en *cache miss* sobre una página indexable— queda
cerrada **para los usuarios**, no solo en la bitácora. Estuvo documentada como resuelta y
sin resolver durante once días.

### P2 — `AGENTS.md` §1 reorientado ✅

Commit `e9c969e`. §1 describe el marketplace como el producto y la consulta como
complemento, con el alcance del ciclo (§1.0.2), la monetización suspendida (§1.0.3) y las
etapas (§1.0.4). Los tres agentes ya leen la definición correcta.

### TASK-001 — Contacto comprador-vendedor (backend) ✅ *pendiente solo el merge*

Spec: [`specs/TASK-001-contacto-vendedor.md`](specs/TASK-001-contacto-vendedor.md) ·
Rama: `feat/TASK-001-contacto-vendedor` · Commit: `99e1fbf`.

Capa `Vendedor` (migración `0021`), `ContactoRevelado` anónimo (`0022`) y tres endpoints:
perfil del vendedor y `POST /marketplace/publicaciones/{id}/contacto`, público y gratis.
El teléfono nunca viaja en feed, `/buscar` ni detalle.

Recorrido: implementada → **auditada por Codex (§16.1: revisa quien no ejecutó)** →
corregida (invariante de `vendedor_id` poblada en el alta, fallback eliminado, upsert a
prueba de carreras, referencias en NULL a propósito, opt-in explícito del nombre) →
**migraciones probadas contra Postgres real**, con las 22 migraciones desde cero, el
backfill verificado con datos y el downgrade comparado por catálogo sin residuos.

**Lo único que falta es el merge.**

---

## 2. Numeración TASK — una sola serie

Hubo dos series en circulación con el mismo prefijo. Esta es la vigente:

| # | Tarea | Estado |
|---|---|---|
| TASK-001 | Contacto comprador-vendedor (backend) | ✅ falta merge |
| TASK-002 | Coherencia del bundle `reporte_compra_segura` | pendiente |
| TASK-003 | Precios a 0 y `/precios` honesto | pendiente |
| TASK-004 | Proveedor nulo por defecto | pendiente |
| TASK-005 | `compartidos.py:58` devuelve 402, no 422 | pendiente |
| TASK-006 | Auditoría de créditos en el ledger | pendiente |
| TASK-007 | `scripts/estado.py` | **spec lista** → [spec](specs/TASK-007-scripts-estado.md) |
| TASK-008 | Recuperación de locks del worker | pendiente |
| TASK-009 | Tests de parser con fixtures | pendiente |
| TASK-010 | Entorno local vs producción (`.env.local`) | spec lista |
| TASK-011 | **Frontend del contacto** | ✅ hecho |
| TASK-012 | Ciudad en publicaciones internas | ✅ hecho (backend + frontend, `0023` aplicada) |
| TASK-013 | Kilometraje declarado en publicaciones internas | ✅ hecho (backend + frontend, `0024` aplicada) |

> **⚠️ Renumeración (2026-08-05) — no busques el número viejo.**
> La versión anterior de este archivo llamaba **TASK-002** al *frontend del contacto*,
> mientras el backlog usaba TASK-002 para la *coherencia del bundle*. Del 003 al 007
> ambas series ya coincidían, y 008/009/010 solo existían en la segunda. Se conserva la
> del backlog y **el frontend del contacto pasa a TASK-011**. Si encuentras "TASK-002 —
> frontend del contacto" en algún documento o commit anterior a esta fecha, se refiere a
> lo que hoy es **TASK-011**.

---

## 3. Pendiente, en orden

El orden importa más que el calendario.

1. **TASK-010 — entorno local vs producción.** Va primero porque hoy el default local
   **es producción**: `load_dotenv()` lee `.env`, que apunta a Neon, y lo único que evita
   correr migraciones contra ella es exportar `DATABASE_URL` a mano. Ruteo `codex`.
2. **Merge de TASK-001** a `main`.
3. **`alembic upgrade head` en Neon** (migraciones `0021` y `0022`). Lo corre Marcos.
   Llega con el ciclo completo ya probado contra Postgres real, backfill y downgrade
   incluidos.
4. **TASK-011 — frontend del contacto.** Botón "Ver teléfono", enlace a WhatsApp y
   formulario de perfil de vendedor. Repo hermano. Ruteo `claude-code` (`dev-frontend`):
   toca el mirror de types y el contrato de errores. Ojo con el 404 de
   `GET /marketplace/vendedor/mi-perfil`, que es **estado de onboarding, no fallo**.
5. **Cerrar compuertas** (ver §5).

## 4. Backlog, por riesgo

1. **TASK-007 — `scripts/estado.py`.** Head de alembic local vs Neon, commits sin pushear
   en ambos repos, proveedor activo en producción y fuentes con consultas en los últimos
   7 días. Su salida es **precondición de cada entrada de bitácora**. Es la que evita que
   el diagnóstico vuelva a hacer falta: las discrepancias encontradas comparten causa —la
   documentación registraba intención, no estado verificado— y un comando que mira el
   sistema real las cierra todas. Ruteo `codex`.
2. **TASK-009 — tests de parser con fixtures.** Cada scraper es un parser sin red de
   seguridad ante un cambio de DOM; `tests/fixtures/` no existe (§14.5, §16.2). Incluye
   decidir el runner (pytest vs `unittest`). El hueco de restricciones de BD ya quedó
   cubierto por el ciclo del 2026-08-05.
3. **TASK-004 — proveedor nulo por defecto.** El arreglo estructural de P0.
4. **TASK-002 — coherencia del bundle.** `reporte_compra_segura` cobra 40 tokens y dos de
   sus componentes están `disponible: false`. Definir si valida componentes o no.
5. **TASK-006 — auditoría del ledger.** 51 tokens sin explicar entre tres usuarios,
   entrados por SQL manual. Sin consecuencia económica hoy; imposible de cerrar cuando
   existan saldos reales.
6. **TASK-008 — locks del worker.** La cola no drena desde el 21-jul y hay un trabajo
   `en_proceso` colgado desde el 29-jul, sin recuperación de locks.
7. **TASK-003 — precios a 0 y `/precios` honesto.** Hoy promete un gateway que no llega
   en este ciclo; con el alcance de §1.0.2 eso es publicidad de algo inexistente.
8. **TASK-005 — `compartidos.py:58` → 402.** Latente mientras el costo sea 0; se activa
   el día que se cobre.

### Anotado sin número todavía

Sale de ejecutar TASK-011. No se les asigna `TASK-NNN` hasta que tengan spec: numerar sin
spec es lo que produjo la doble serie que hubo que reconciliar.

- **Navegación principal inexistente en celular.** La barra del Header es `hidden md:flex`:
  **bajo 768px no hay forma de llegar a Marketplace, Publicar, Consulta ni Precios** salvo
  por el logo o enlaces dentro del contenido. Los accesos de admin (Moderar / Verificar)
  viven en esa misma barra, así que un admin en celular tampoco los alcanza. Y a 768px
  exactos la barra desborda el viewport. Es grave para un producto cuyo público declarado
  navega en **celulares de gama baja** (§1). El menú de cuenta de TASK-011 resolvió el
  acceso a *la cuenta*, no esto. Pide su propia tarea: hamburguesa o barra inferior.
- **Error de lint preexistente en `Header.tsx`** (`setState` síncrono dentro de un efecto,
  hoy en `38:7`). Es uno de los 4 que arrastra el repo. **No se arregló a propósito** al
  tocar la navegación: mezclado con un cambio funcional ensucia la auditoría. Va junto con
  los otros 3 (`admin/moderacion`, `admin/verificaciones`, `mis-publicaciones`), que tienen
  la misma causa y conviene resolver de una sola pasada.
- **Las referencias externas no tienen entrada desde la navegación.**
  `marketplace/referenciar` y `marketplace/mis-referencias` **sí son alcanzables**, pero
  solo desde dentro del contenido: `/marketplace` enlaza a ambas y `DestacadosMarket` (en
  la home) enlaza a `referenciar`. No aparecen en el Header, ni en `MenuCuenta`, ni en la
  barra móvil, así que hay que toparse con el bloque correcto mientras se navega. "Mis
  referencias" es además una vista **de gestión propia**, hermana de "Mis publicaciones",
  que sí quedó en el menú de cuenta. Al revisarlo, decidir si aportar una referencia es
  una acción de navegación o se queda como descubrimiento contextual dentro del feed.
  *(Nota: el enunciado original de este seguimiento decía que no tenían entrada "desde
  ningún lado"; se verificó y no es así — el problema es de descubribilidad, no de
  orfandad como pasó con `mi-perfil-vendedor`.)*

## 5. Compuertas abiertas

Hay **ocho** a la vez: **M2, M2.5, M2.6, M2.7, M2.8, M2.10, MC1 y MC2**, todas con la
misma frase, *"código implementado, compuerta ABIERTA a la espera de la prueba manual"*.
Los guiones v2 a v6 nunca se corrieron.

*(Antes este archivo decía "siete" y enumeraba ocho.)*

**Recomendación: no cerrarlas una por una.** El código cambió seis veces encima; correr
seis guiones verifica un estado que ya no existe. Después de TASK-011, correr **solo el
guión de MC2** más el flujo de contacto de punta a punta, y declarar las anteriores
cerradas por inclusión donde el flujo las atraviese.

Documentar esa decisión en la bitácora **con el motivo**: es una desviación deliberada del
ritual de §3 del plan, no un olvido más.

## 6. Relación con el eje M

`plan_market_autos.md` es historia. Dos etapas suyas necesitan aclaración porque el ciclo
las tocó o las reubicó:

- **M5 — Contacto comprador-vendedor:** su **backend está hecho** en TASK-001, incluido el
  "contador de clics como métrica de demanda" (`ContactoRevelado`). El frontend es
  TASK-011. Era el mismo trabajo con dos nombres.
- **M4 — Cuentas de patio:** pasa a **etapa 2** por AGENTS §1.0.2, fuera de este ciclo.
  Se reactiva cuando el flujo de particulares funcione con usuarios reales. El plan la
  listaba antes de M5; ese orden ya no aplica.

## 7. Candidatos a discutir por separado

Cosas que aparecieron ejecutando el ciclo, que **no son deuda ni bug**, sino decisiones de
producto que merecen su propia conversación en vez de colarse dentro de otra tarea.

- **Jerarquía de CTAs en el detalle del anuncio.** Al implementar el contacto (TASK-011)
  se ascendió "Ver teléfono" a CTA primario y "Verificar esta placa" bajó a secundario.
  **Se revirtió** en la auditoría: hoy manda "Verificar esta placa", como antes. El
  argumento a favor del cambio es real —en un market, contactar es la acción de conversión—
  pero cambiar qué acción manda en un anuncio afecta al posicionamiento del producto
  (§1.0.1: la consulta es complemento, el market es el producto) y no debía decidirse
  dentro de una tarea de contacto. Decidir con el guión de prueba en la mano, o con datos
  de `ContactoRevelado` cuando haya tráfico real.

## 8. Fuera de este ciclo

Patios e ingesta masiva (etapa 2). Pasarela de pago. SRI y FGE. Feed tipo reels y app
móvil. Mensajería interna. Verificación de teléfono por OTP.

Criterio de reactivación de cada uno: tabla de `AGENTS.md` §1.0.2.
