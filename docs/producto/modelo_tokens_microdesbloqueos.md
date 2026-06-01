# Modelo de microdesbloqueos por tokens — Revisa tu Carro EC

**Estado:** IMPLEMENTADO (backend + frontend) el 2026-05-31. **Reajuste comercial Fase 2.5
(2026-05-31, migración `0016`):** la ficha pública completa es **gratis** (`consulta_publica_base`,
0 tokens); solo se cobra por datos con costo/dificultad/valor real. Productos con datos reales
hoy: `multas_con_montos` y `identificadores_tecnicos` (cuando la fuente los aporta) + bundle.
`titular_validado`, `valores_matricula_sri` y `alertas_legales` quedan en el catálogo con
`disponible=false` (enlace oficial / sin proveedor confiable). `verificacion_marketplace` NO se
cableó al flujo de consulta (sigue siendo el flujo admin del marketplace, 100 tokens).
**1 token ≈ USD 0.04.**
**Fecha:** 2026-05-31.
**Relacionados:** [catalogo_productos_consulta.md](catalogo_productos_consulta.md) · [reglas_monetizacion_tokens.md](reglas_monetizacion_tokens.md) · [politica_datos_sensibles.md](politica_datos_sensibles.md) · [AGENTS.md](../../AGENTS.md) · [proyecto-snapshot.md](../../proyecto-snapshot.md).

---

## 1. Objetivo
Pasar del desbloqueo **monolítico** actual (un solo `POST /consultar/{placa}/desbloquear` que revela todos los identificadores) a un modelo de **microdesbloqueos progresivos**: el usuario hace una **consulta inicial gratuita** (teaser) y va **desbloqueando productos pequeños** de datos con tokens, según lo que necesita.

**Principio ético/legal (no negociable):** no se implementa evasión de captcha, bypass anti-bot ni scraping agresivo. Los datos provienen de: (a) **fuentes ya obtenidas** y cacheadas, (b) **proveedores externos autorizados** (APIs de pago/convenios), y (c) **enlaces oficiales asistidos** (ej. SRI vía su portal). El token cobra el **acceso/empaquetado del dato**, no el sorteo de un control de seguridad.

## 2. Estado actual (AS-IS) — qué ya existe y se reutiliza
- **Wallet + débito real**: `src/modules/tokens/service.py` → `debitar_tokens(sesion, usuario, monto, motivo)`; lanza `SaldoInsuficiente` → el endpoint traduce a **HTTP 402** (convención §10.2). Saldo inicial 5 tokens (cortesía).
- **Desbloqueo monolítico** (a generalizar): `src/modules/consulta/routers/consulta.py` → `POST /consultar/{placa}/desbloquear` con `TOKENS_DESBLOQUEO_PERFIL` (1); hoy solo revela identificadores y **no cobra si no hay dato** (`Identificacion.hay_dato_sensible`).
- **Consolidador**: `src/modules/consulta/services/consolidador.py` → `consolidar_placa(placa, resultados, desbloqueado: bool = False)`. Hoy `desbloqueado` es un booleano global; se reemplaza por un **conjunto de productos desbloqueados**.
- **Schemas**: `src/modules/consulta/schemas.py` → `VehiculoConsolidadoResponse`, `Identificacion` (con flag `bloqueado`).
- **Auth**: `usuario_actual`, `admin_actual` (`src/modules/auth/dependencies.py`).
- **Verificación marketplace** (admin): ya existe `estado_verificacion` + endpoints admin (se relaciona con el producto `verificacion_marketplace`, ver §7).
- **Frontend**: `PerfilVehiculo.tsx` pinta secciones; `Identificacion` se muestra ofuscada; **no hay aún botón de desbloqueo** en la UI.

## 3. Diseño TO-BE

### 3.1 Capas de acceso a un perfil
1. **Gratis (teaser)** — sin tokens, sin login: marca, modelo, año, color y un **veredicto binario** ("¿tiene pendientes? sí/no", **sin montos ni detalle**) + estado de matrícula (vigente/vencida). Suficiente para identificar el auto y generar interés.
2. **Microproductos** — desbloqueos puntuales con tokens (ver catálogo): básico completo, técnico, identificadores, multas con montos, titular validado.
3. **Bundle** — `reporte_compra_segura`: combo con descuento que agrupa varios microproductos + condición legal.
4. **Verificación marketplace** — `verificacion_marketplace`: producto premium ligado al sello "Verificado por la plataforma".

### 3.2 Modelo de datos (nuevo)
Tabla **`desbloqueos`** (un registro = un producto desbloqueado por un usuario para una placa; persistente para **no cobrar dos veces**):

| Columna | Tipo | Notas |
|---|---|---|
| `id` | BigInteger PK | autoincrement |
| `usuario_id` | BigInteger FK→usuarios (CASCADE) | index |
| `placa` | String(10) | normalizada con `validar_placa`, index |
| `producto` | String(40) | código del catálogo |
| `tokens_cobrados` | Integer | lo que costó al momento (auditoría histórica) |
| `creado_en` | timestamp tz | `server_default now()` |

- **UK** `(usuario_id, placa, producto)` → idempotencia: re-desbloquear es no-op (no recobra).
- Migración manual `0014_desbloqueos.py` (no autogenerate).
- Registrar `Desbloqueo` en `src/registry.py`.

> El catálogo de productos **no** va en BD: vive en código (`services/catalogo_productos.py`) como fuente de verdad de precios/descripciones, igual que `catalogo_fuentes.py`. Así el precio se versiona con el código y no requiere migración.

### 3.3 Catálogo (en código)
`src/modules/consulta/services/catalogo_productos.py`: dict `CATALOGO_PRODUCTOS[codigo] -> ProductoConsulta(nombre, tokens, descripcion, fuente, sensibilidad, incluye=[...])`. Precios iniciales en [catalogo_productos_consulta.md](catalogo_productos_consulta.md). `reporte_compra_segura` declara `incluye=[...]` (los códigos que agrupa) → al desbloquearlo se marcan todos.

### 3.4 Endpoints (contrato §6 / skill respuesta-api-estandar)
- `GET /consultar/{placa}/productos` — catálogo con estado por producto: `{codigo, nombre, tokens, sensibilidad, desbloqueado: bool, disponible: bool}`. Con JWT marca `desbloqueado` según la tabla; anónimo → todo `desbloqueado=false`. `disponible=false` si la fuente no entrega ese dato para esa placa (no se podrá cobrar).
- `POST /consultar/{placa}/desbloquear/{producto}` (JWT) — desbloquea un producto:
  - `producto` no existe en catálogo → **400**.
  - placa inválida → **400**.
  - dato **no disponible** para esa placa → **409** (o `{estado: "sin_dato"}`), **no cobra**.
  - ya desbloqueado → **200** idempotente, **no recobra**, devuelve la sección.
  - saldo insuficiente → **402**.
  - éxito → `debitar_tokens(tokens)` + insertar `Desbloqueo` (atómico, un solo commit) → **200** con la sección de datos ya revelada.
- `GET /consultar/{placa}/perfil` — pasa a aceptar al usuario (opcional) y gatear secciones según sus desbloqueos.
- **Compatibilidad**: el actual `POST /consultar/{placa}/desbloquear` se mantiene como **alias** de `vehiculo_identificadores` (o se deprecia con aviso) para no romper el frontend ya desplegado.

### 3.5 Gating en el consolidador
`consolidar_placa(placa, resultados, productos_desbloqueados: set[str] = frozenset())`:
- Por cada sección, si su producto no está en `productos_desbloqueados`, se devuelve **ofuscada/resumida** (no se omite la clave: se marca `bloqueado=True` + `tokens` para desbloquear, así el frontend pinta el candado).
- Mapeo sección→producto documentado en el catálogo. El titular **siempre** sale ofuscado/validado aunque se desbloquee (ver [politica_datos_sensibles.md](politica_datos_sensibles.md)).

### 3.6 Frontend (Next.js, es-EC tuteo)
- `types/api.ts`: tipos `ProductoConsulta`, `EstadoProducto`, y secciones con `bloqueado`/`tokens`.
- `lib/api.ts`: `listarProductosConsulta(placa)`, `desbloquearProducto(placa, producto)`.
- `components/PerfilVehiculo.tsx`: cada sección bloqueada muestra un **`BotonDesbloqueo`** ("Desbloquear · N tokens") con el saldo del usuario; al hacer clic llama al endpoint, maneja **402** ("No te alcanzan los tokens — recarga") y refresca la sección. Mostrar el saldo de tokens en el header o en la vista.
- Nuevo componente `BotonDesbloqueo.tsx` reutilizable.

## 4. Flujo (secuencia)
1. Usuario consulta placa → ve el **teaser gratis** + lista de productos con su precio y candado.
2. Hace clic en "Desbloquear · 8 tokens" sobre Multas → `POST .../desbloquear/vehiculo_multas`.
3. Backend obtiene/lee de caché las multas; si hay dato y saldo: debita 8, guarda `Desbloqueo`, responde con el detalle.
4. La sección se revela; futuras visitas a esa placa por ese usuario la muestran sin recobrar.

## 5. Convenciones aplicadas
- Identificadores en **español** (`desbloqueos`, `producto`, `tokens_cobrados`, `CATALOGO_PRODUCTOS`).
- Copy del frontend en **español de Ecuador (tuteo)**.
- Alembic **manual** (0014).
- **402** para saldo insuficiente; **no cobrar** si el dato no está disponible.
- Tolerancia a fallos: una fuente caída no rompe el perfil; el producto queda `disponible=false`.

## 6. Archivos a crear/modificar (siguiente etapa) — ver §"Plan de archivos" abajo
Resumen en la sección final de este documento y en el mensaje de la tarea.

## 7. Decisiones abiertas (a confirmar antes de implementar)
1. **Teaser gratis exacto**: ¿qué campos quedan 100% gratis? Propuesta: marca/modelo/año/color + veredicto binario + matrícula vigente/vencida. (Hoy el perfil muestra más; habría que recortar el gratis para que los microproductos tengan valor.)
2. **`verificacion_marketplace` (80 tokens)** vs el flujo admin ya construido: hoy publicar premium cuesta `TOKENS_PUBLICACION_PREMIUM=3` y la verificación admin es gratis. Opción: el sello "Verificado" pasa a ser un producto de 80 tokens que el dueño **solicita** (entra a la cola admin), separando "destacar premium" (3) de "verificar" (80). Reconciliar con [docs/producto/checklist_verificacion_marketplace.md](checklist_verificacion_marketplace.md).
3. **Titular validado**: definir el proveedor autorizado y si se muestra ofuscado o solo "validación" (coincide/no coincide). Ver política.
4. **Reembolso/idempotencia de bundle**: si el usuario ya desbloqueó multas (8) y luego compra `reporte_compra_segura` (30), ¿se descuenta lo ya pagado? Propuesta inicial: no se descuenta (el bundle ya es barato); documentarlo.
5. **Saldo inicial 5 vs precios**: con 5 tokens de cortesía ($0.25) el usuario alcanza 1–2 microproductos. Confirmar si está bien como "prueba".

## 8. Resoluciones (2026-05-31)
- **#2 `verificacion_marketplace`** → RESUELTO: separado del premium. Publicar premium = 3 tokens (destaca, nace `no_verificado`); el dueño **solicita** el sello con `POST /marketplace/publicaciones/{id}/solicitar-verificacion` = **80 tokens** → `pendiente` → cola admin. Saldo en el header ya visible.
- **#3 titular / #técnico (seam de proveedor)** → BLOQUEADO por dependencia externa: requieren un **proveedor de datos autorizado** (API/convenio) que aún no existe. Por eso `titular_validado`, `valores_matricula_sri` y `alertas_legales` quedan en el catálogo con `disponible=false` (no se ofrecen ni cobran; se muestra enlace oficial). **Punto de integración**: cuando exista el proveedor, se agrega un servicio `services/proveedor_<x>.py` que pueble esos campos en `consolidar_placa`, y el producto pasará a `disponible=true` automáticamente (la lógica de cobro/gateo ya está lista). No se implementa scraping de padrones (límite ético/legal).

## 9. Reajuste comercial — Fase 2.5 (2026-05-31, migración `0016`)
Motivo: no cobrar tokens por **datos públicos simples** que ya vienen de fuentes públicas
(clase, servicio, marca, modelo, año, color, estado de matrícula). Solo se cobra por datos con
**costo de proveedor externo, dificultad real o valor comercial relevante**.

- **Valor del token:** USD 0.05 → **USD 0.04**. Precios `precio_referencial_usd = tokens × 0.04`.
- **Gratis** (`consulta_publica_base`, 0 tokens): ficha pública completa + estado de matrícula +
  enlaces oficiales + estado de fuentes + veredicto sí/no. El consolidador ya **no gatea**
  `datos_basicos`.
- **Desactivados** (migración `0016`, `activo=false`): `vehiculo_basico`, `vehiculo_tecnico`
  (cobraban datos públicos poco relevantes).
- **Renombrados:** `vehiculo_identificadores`→`identificadores_tecnicos` (3t),
  `vehiculo_titular_validado`→`titular_validado` (5t), `vehiculo_multas`→`multas_con_montos`
  (10t). El alias `POST /consultar/{placa}/desbloquear` ahora apunta a `identificadores_tecnicos`.
- **Nuevos:** `valores_matricula_sri` (12t, SRI vía enlace oficial), `alertas_legales` (8t, FGE).
- **Reprecio:** `reporte_compra_segura` 30→40t; `verificacion_marketplace` 80→100t (constante
  `TOKENS_VERIFICACION_MARKETPLACE`).
- **Regla técnica:** la consulta gratuita **no** llama a proveedores externos; el proveedor se
  invoca solo al desbloquear un producto pagado y su respuesta se cachea; si otro producto usa
  un dato ya cacheado, no se vuelve a llamar (ver [reglas_monetizacion_tokens.md](reglas_monetizacion_tokens.md) §6).
- **Catálogo y precios** en [catalogo_productos_consulta.md](catalogo_productos_consulta.md);
  paquetes de recarga en [reglas_monetizacion_tokens.md](reglas_monetizacion_tokens.md) §1.1.
