# AGENTS.md — Proyecto `consulta_placas_ec`

Este archivo es la fuente de verdad para cualquier agente o desarrollador que toque el proyecto. Léelo completo antes de hacer cambios.

> **Nombre del archivo:** antes era `CLAUDE.md`; se renombró a `AGENTS.md` (estándar multi-agente). Queda un `CLAUDE.md` mínimo que solo importa este archivo (`@AGENTS.md`) para que Claude Code lo siga auto-cargando. No edites el shim; edita siempre `AGENTS.md`.

---

## 1. Propósito del proyecto

Plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa, sus características o una foto. Cuatro pilares:

1. **Consulta pública por placa** — agrega información de fuentes oficiales: ANT (matriculación, citaciones), SRI (valores tributarios), AMT Quito (infracciones municipales), **Fiscalía General del Estado / FGE** (noticias del delito asociadas a placa, cédula o nombres — accidentes, robos, denuncias).
2. **Consulta por foto** — el usuario fotografía el vehículo o la placa; OCR/visión extrae la placa y dispara el flujo de consulta.
3. **Historial privado del vehículo** — usuarios autenticados pueden registrar y mantener actualizado: kilometraje, dueños (histórico), mantenimientos, documentos, novedades. Estos datos NO son públicos.
4. **Modo compra-venta con token** — el dueño genera un enlace/token temporal que muestra a un comprador interesado el historial del vehículo sin que este necesite cuenta.

---

## 1.1 Arquitectura: monolito modular (DDD) y mapa de skills

Desde la **Fase 0 (2026-05-29)** el backend se organiza **por dominio de negocio** en `src/`,
no por tipo de archivo. Un módulo = una capacidad de negocio (no una tabla). 5 módulos + `core`:

```
src/
  registry.py              # importa TODOS los modelos → Base.metadata (lo usa Alembic)
  core/                    # infra y utils compartidos: src/core/database.py, validators.py, ofuscacion.py
  modules/
    auth/                  # identidad: login, registro, JWT, Usuario (+ TransaccionToken)
    tokens/                # billetera: débito (service.py), saldo/auditoría (router.py)
    consulta/              # Pilar 1+2: services/{ant,sri,amt,fiscalia,cache,cola,vision},
                           #            models/{consulta,cola_scraping}, routers/{consulta,ocr}
    vehiculos/             # Pilar 3: vehículo, dueños, kilometraje, mantenimientos, favoritos
    marketplace/           # Pilar 4: listado público + enlaces compartidos (token)
```

**Entrypoints en la raíz** (procesos, no módulos): `main.py` (solo `app` + CORS + `include_router`),
`run.py`, `worker.py`, `scripts/discover.py`.

**Dependencias entre módulos (dirección permitida):** `tokens`→`auth`, `vehiculos`→`auth`,
`marketplace`→`vehiculos`+`tokens`, `consulta`→`core`+`auth`+`tokens`; todos→`core`.
(`consulta`→`auth`+`tokens` se agregó al cablear el desbloqueo de identificadores por tokens:
`POST /consultar/{placa}/desbloquear` usa `usuario_actual` y `debitar_tokens`, ambas interfaces públicas.)
**Regla de oro:** los módulos se comunican por la **interfaz pública** del otro (funciones de
servicio expuestas, ej. `debitar_tokens`); no se importan internals ajenos fuera de esa dirección.
Un cambio en un dominio debe quedar contenido en su carpeta; si cruza módulos, queda como un
import explícito y rastreable.

**Notas de cohesión (heredadas de la mudanza, no tocar sin acordar):** `Usuario` y
`TransaccionToken` viven juntos en `src/modules/auth/models.py` (tokens los importa); los schemas
de token (`SaldoTokens`, `TransaccionTokenSalida`) viven en `src/modules/auth/schemas.py`.

### Qué skill aplica a qué módulo

| Skill | Módulo(s) donde aplica |
|---|---|
| [agregar-fuente-consulta](.claude/skills/agregar-fuente-consulta/SKILL.md) | `consulta` (nuevo `services/<fuente>.py` + registrar en `routers/consulta.py`) |
| [scraping-respetuoso](.claude/skills/scraping-respetuoso/SKILL.md) | `consulta` (todo `services/` de fuentes + `worker.py`) |
| [respuesta-api-estandar](.claude/skills/respuesta-api-estandar/SKILL.md) | `consulta` (funciones `consultar_*` y endpoints públicos) |
| [validacion-datos-ec](.claude/skills/validacion-datos-ec/SKILL.md) | `core` (`validators.py`, `ofuscacion.py`) + donde entren identificadores |
| [modelo-dominio-vehiculo](.claude/skills/modelo-dominio-vehiculo/SKILL.md) | `vehiculos`, `marketplace`, `auth` (modelos + Alembic) |
| [desplegar-mvp](.claude/skills/desplegar-mvp/SKILL.md) | global (Docker/Render/Vercel, no específico de módulo) |
| [project-snapshot](.claude/skills/project-snapshot/SKILL.md) | global (regenera `proyecto-snapshot.md`) |

> El día a día se registra en [docs/bitacora.md](docs/bitacora.md); el estado completo AS-IS en [proyecto-snapshot.md](proyecto-snapshot.md).

---

## 2. MVP en producción (mayo 2026)

| Componente | URL | Plataforma |
|---|---|---|
| **Backend** (FastAPI + Playwright en Docker) | [consulta-placas-ec.onrender.com](https://consulta-placas-ec.onrender.com) | Render free tier |
| **Frontend** (Next.js 16 + Tailwind 4) | [consulta-placas-web.vercel.app](https://consulta-placas-web.vercel.app) | Vercel free |
| **PostgreSQL 16** | (cadena de conexión externa) | Neon |
| **Repo backend** | [VMarcosGC/consulta-placas-ec](https://github.com/VMarcosGC/consulta-placas-ec) | GitHub |
| **Repo frontend** | [VMarcosGC/consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web) | GitHub |

Ver detalle de deploy en [docs/despliegue.md](docs/despliegue.md) y skill [desplegar-mvp](.claude/skills/desplegar-mvp/SKILL.md).

---

## 3. Estado por fase

### Fase 1 — Consultas estables ✅ cerrada
- [main.py](main.py) — FastAPI con endpoints públicos `/consultar/{placa}`, `/consultar-judicial/{cedula}` y `/health`.
- [src/modules/consulta/services/ant.py](src/modules/consulta/services/ant.py) — ANT con Playwright. Funcional local y cloud.
- [src/modules/consulta/services/sri.py](src/modules/consulta/services/sri.py) — SRI. Devuelve `bloqueado_captcha` (reCAPTCHA Enterprise invisible).
- [src/modules/consulta/services/amt.py](src/modules/consulta/services/amt.py) — AMT con iframe detection y manejo de overlay "Consultando". Funcional local; bloqueado en cloud (ver sección 8).
- [src/modules/consulta/services/fiscalia.py](src/modules/consulta/services/fiscalia.py) — Fiscalía SIAF. Funcional local; bloqueado en cloud.
- [src/modules/consulta/services/cache.py](src/modules/consulta/services/cache.py) — Caché en Postgres con TTL configurable. Solo cachea `consulta_realizada` y `sin_resultados`.

### Fase 2 — Auth + dominio + deploy ✅ cerrada
- [src/modules/auth/security.py](src/modules/auth/security.py) — bcrypt (pin `<4.0` por bug con passlib) + JWT HS256.
- [src/modules/auth/dependencies.py](src/modules/auth/dependencies.py) — `usuario_actual` y `vehiculo_propio` dependencies.
- [src/modules/auth/router.py](src/modules/auth/router.py) — `POST /auth/registro`, `POST /auth/login`, `GET /auth/me`.
- [src/modules/vehiculos/routers/vehiculos.py](src/modules/vehiculos/routers/vehiculos.py) — CRUD completo de vehículos del usuario (con VIN, motor, chasis).
- [src/modules/vehiculos/routers/duenos.py](src/modules/vehiculos/routers/duenos.py) — Histórico de dueños con cierre automático del anterior.
- [src/modules/vehiculos/routers/kilometraje.py](src/modules/vehiculos/routers/kilometraje.py) — Lecturas inmutables con validación monotónica.
- Modelos por módulo (ver §1.1): `Consulta`, `Usuario`, `Vehiculo`, `DuenoHistorico`, `KilometrajeLectura` — repartidos en `src/modules/<dominio>/models/` y registrados en [src/registry.py](src/registry.py).
- [src/modules/vehiculos/schemas/vehiculo.py](src/modules/vehiculos/schemas/vehiculo.py) — 3 niveles de visibilidad: `Completa`, `Compartida` (ofuscado), `Publica`.
- [src/core/validators.py](src/core/validators.py) — `validar_placa`, `validar_cedula`, `validar_vin` (ISO 3779/3780).
- [src/core/ofuscacion.py](src/core/ofuscacion.py) — `ofuscar_vin`, `decodificar_origen_vin`, tabla `PAISES_VIN` (WMI).
- **Deploy**: Docker (imagen oficial de Playwright) en Render + Vercel para el frontend.
- **Frontend**: Next.js 16 App Router + Tailwind 4 + tema oscuro con gradient brand. Landing comercial + consulta pública + auth + mi-garage + precios. Vive en repo separado [consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web).

### Fase 3 — Billetera + Favoritos + Mantenimientos ✅ cerrada
- **BD en Neon** (PostgreSQL 16, externa). Migraciones `0004`–`0006`. El Postgres de Render ya no se usa.
- [src/modules/auth/models.py](src/modules/auth/models.py) — `Usuario.saldo_tokens` (default 5, CHECK `>= 0`, constante `SALDO_INICIAL_TOKENS`) + modelo `TransaccionToken` (auditoría inmutable). Migración `0004`.
- [src/modules/vehiculos/models/vehiculo.py](src/modules/vehiculos/models/vehiculo.py) — campos de perfil `transmision`, `tipo_motor`, `ciudad_registro`. Migración `0004`.
- [src/modules/tokens/router.py](src/modules/tokens/router.py) — `GET /tokens/saldo`, `GET /tokens/transacciones` (lectura). El registro graba la transacción `saldo_inicial` (+5).
- [src/modules/vehiculos/models/vehiculo_favorito.py](src/modules/vehiculos/models/vehiculo_favorito.py) + [src/modules/vehiculos/routers/favoritos.py](src/modules/vehiculos/routers/favoritos.py) — `POST/GET/DELETE /favoritos`; placa como `String` (no FK), validada con `validar_placa`, única por usuario+placa. Migración `0005`.
- [src/modules/vehiculos/models/mantenimiento.py](src/modules/vehiculos/models/mantenimiento.py) + [src/modules/vehiculos/routers/mantenimientos.py](src/modules/vehiculos/routers/mantenimientos.py) — `POST/GET/DELETE /vehiculos/{id}/mantenimientos`; inmutables, con validación monotónica de `fecha` y `kilometraje_relacionado` (422) y propiedad por JWT. Migración `0006`.
- **Pendiente del débito real**: el servicio que descuenta tokens (con `422` por saldo insuficiente) se implementará junto a la primera función de pago. Por ahora la billetera es solo lectura + auditoría inicial.

### Fase 4 — Compra-venta: Marketplace + token ✅ cerrada
- **Marketplace público** (migración `0007`): columnas `en_venta` (bool, default `false`), `precio_venta_usd` (Numeric 12,2) y `url_externa` (String 500) en `vehiculos`. [src/modules/marketplace/routers/marketplace.py](src/modules/marketplace/routers/marketplace.py) — `GET /marketplace` anónimo; lista solo `en_venta = True AND precio_venta_usd > 0` y no eliminados. Usa `selectinload(Vehiculo.mantenimientos)` para derivar `total_mantenimientos` sin N+1. Vista pública `VehiculoSalidaMarketplace` (en [src/modules/vehiculos/schemas/vehiculo.py](src/modules/vehiculos/schemas/vehiculo.py)): nunca expone VIN completo (nivel `oculto`, solo país) ni nombre del dueño.
- **Token de compra-venta** (migración `0008`): [src/modules/marketplace/models.py](src/modules/marketplace/models.py) — `enlaces_compartidos` con `token` único (UK, índice único), `scope` JSONB opt-in (claves válidas: `kilometraje`, `mantenimientos`, `duenos_historico`) y `fecha_expiracion`. [src/modules/marketplace/routers/compartidos.py](src/modules/marketplace/routers/compartidos.py) — `POST /vehiculos/{id}/compartir` (dueño vía `vehiculo_propio`, TTL ≤ 7 días) y `GET /compartido/{token}` (público) que devuelve `VehiculoSalidaCompartida` ofuscado. Token inexistente o expirado → `404` (no se distingue de "no es tuyo").
- **Pendiente**: el `scope` se persiste y valida, pero la vista compartida actual (`VehiculoSalidaCompartida`) solo muestra características del auto; el gateo de kilometraje/mantenimientos/dueños se cableará cuando esas secciones se agreguen a la vista compartida.

### Próximas fases
| Fase | Objetivo | Entregables clave |
|---|---|---|
| **5** | OCR / foto | Endpoint que recibe imagen → extrae placa (Tesseract o servicio cloud) → flujo normal. |
| **6** | Mobile + features de pago | App móvil, integración con gateway local (PlaceToPay/MercadoPago). |

No saltar fases. Cada una asume las anteriores estables. Las reglas de negocio inmutables de las fases 3 y 4 están en la sección 10.

---

## 4. Stack estándar

### Backend (repo `consulta_placas_ec`)
- **Lenguaje**: Python 3.11+ (en producción: imagen Docker con Python 3.10 vía Playwright official).
- **API**: FastAPI con routers organizados en `routers/`.
- **Scraping**: Playwright async con Chromium. Preferir `httpx` si la fuente sirve HTML estático o JSON.
- **BD**: PostgreSQL (JSONB para respuestas crudas; índices compuestos en `consultas`).
- **ORM/Migraciones**: SQLAlchemy 2 + Alembic (migraciones manuales para versionado predecible).
- **Validación/serialización**: Pydantic 2.
- **Auth**: `passlib[bcrypt]` (con `bcrypt<4.0` pineado) + `python-jose` (JWT HS256).
- **Deploy**: Docker (imagen `mcr.microsoft.com/playwright/python:v1.48.0-jammy`) en Render.

### Frontend (repo `consulta-placas-web`)
- **Marca**: **"Revisa tu Carro EC"** (monograma RC). Rebranding desde "ConsultaPlacas" (2026-05-29).
  Se descartó "Carro Seguro EC" por su ambigüedad con seguro/póliza.
- **Framework**: Next.js 16 (App Router, Turbopack, RSC).
- **UI**: React 19 + Tailwind CSS 4 (theme inline con `@theme`).
- **Tono visual**: **"Confianza clara"** — **tema claro** (fondo `#f6f8fc`), gradiente de marca
  **azul → cian** (`--color-brand-from #2563eb → via #0ea5e9 → to #06b6d4`, en `src/app/globals.css`),
  estados verde="al día" / ámbar / rojo="pendiente", sombras suaves (`.sombra-tarjeta`), glow
  azul del hero (`.hero-glow`). Objetivo: serio y confiable pero atractivo, legible en celulares de
  gama baja, pensado para público de clase media-baja. (Antes era tema oscuro neón violeta-rosa-ámbar.)
- **Vista de resultados**: `PerfilVehiculo.tsx` consume el **perfil consolidado** del backend
  (`GET /consultar/{placa}/perfil` → `VehiculoConsolidadoResponse`) y lo pinta por secciones
  temáticas (Identificación, Valores, Multas, Legal). Las fuentes no oficiales se marcan con
  **ⓘ + disclaimer**. El frontend ya **no transforma**: solo lee y pinta (helpers en `src/lib/consolidar.ts`).
- **Cliente HTTP**: `fetch` nativo en wrapper tipado (`src/lib/api.ts`).
- **Auth**: JWT en `localStorage` (sin SSR para páginas privadas).
- **Deploy**: Vercel free.

**No agregar dependencias nuevas sin justificación documentada** en el PR o commit.

---

## 5. Convenciones de código

- **Idioma**: nombres de funciones, variables, rutas, columnas y campos JSON en **español**, en ambos repos. Ejemplos: `consultar_ant`, `validar_placa`, `/consultar/{placa}`, `kilometraje_lecturas.fecha_lectura`, componente `ConsultaForm`. Mantener.
- **Código por módulo de dominio** (ver §1.1): todo lo de un dominio vive en `src/modules/<dominio>/`. Lo transversal (BD, config, validadores, ofuscación) en `src/core/`. Al crear un modelo nuevo, registrarlo en `src/registry.py`.
- **Servicios externos**: viven en `src/modules/consulta/services/<fuente>.py` y exponen `async def consultar_<fuente>(arg) -> dict`.
- **Routers**: cada grupo de endpoints en `src/modules/<dominio>/router.py` (o `routers/<grupo>.py` si el módulo tiene varios) con `APIRouter(prefix=..., tags=[...])`. `main.py` solo orquesta `include_router`.
- **Schemas Pydantic**: en `src/modules/<dominio>/schemas.py` (o `schemas/<entidad>.py` si hay varios). Convención: `<Entidad>Crear`, `<Entidad>Actualizar`, `<Entidad>Salida` (más variantes de visibilidad si aplica, ver vehículo).
- **Validadores**: `src/core/validators.py`. Una función por tipo (`validar_placa`, `validar_cedula`, `validar_vin`) que devuelve el valor normalizado o lanza `ValueError`.
- **Manejo de errores en servicios**: un servicio externo **nunca debe propagar excepciones al endpoint**. Captura todo y devuelve `{"estado": "error", "error": "..."}`.

Ver skills en [.claude/skills/](.claude/skills/) para procedimientos detallados.

---

## 6. Estructura de respuesta estándar

Toda función `consultar_<fuente>` devuelve:

```json
{
  "fuente": "ANT|SRI|AMT|FGE",
  "placa": "ABC1234",
  "estado": "consulta_realizada|error|pendiente_integracion|sin_resultados|bloqueado_captcha|en_proceso|error_fuente|consulta_externa",
  "datos": { ... } | null,
  "error": "string (solo cuando estado=error, bloqueado_captcha o error_fuente)",
  "url_consulta": "string (solo cuando estado=consulta_externa)"
}
```

`bloqueado_captcha`: la fuente respondió pero la submission fue bloqueada silenciosamente (caso SRI con reCAPTCHA invisible). El servicio detecta el bloqueo porque la respuesta vino vacía sin error técnico.

`error_fuente`: el worker híbrido agotó los reintentos (default 4) consultando AMT/FGE — la fuente oficial está caída o bloqueando. La API lo devuelve durante una ventana de enfriamiento (12h) en vez de re-encolar a ciegas, para que el cliente deje de pollear. El frontend muestra "Reintentar conexión con la fuente", que llama a `POST /consultar/{identificador}/reintentar/{fuente}` y reencola el trabajo. No se cachea en `consultas` (vive solo en `cola_scraping`).

`consulta_externa`: la fuente no se scrapea; se expone el **servicio oficial** para que el usuario consulte el detalle ahí. Devuelve `url_consulta` (enlace al portal) y `datos: null`. **Caso SRI**: usa reCAPTCHA Enterprise v3 (score-based) que rechaza tokens de solvers; en vez de pelearlo, el frontend muestra un botón que abre el portal del SRI (no se puede iframe: `X-Frame-Options: SAMEORIGIN`). El solver (vía A, Capsolver/2Captcha) queda DORMIDO en `_consultar_sri_scraping`. La vía definitiva (B = API oficial SRI) queda pendiente. Ver [docs/bitacora.md](docs/bitacora.md).

Para la Fiscalía (FGE), el campo de identificación se llama `termino` en vez de `placa` porque el portal acepta placa, cédula, RUC, nombres o NDD.

El endpoint público adiciona un objeto `resumen` con indicadores derivados. Ver skill [respuesta-api-estandar](.claude/skills/respuesta-api-estandar/SKILL.md).

---

## 7. Identificadores sensibles y ofuscación

Los datos en `vehiculos` incluyen identificadores que NO deben mostrarse completos a terceros:
- `vin` (17 caracteres, ISO 3779/3780)
- `numero_motor`
- `numero_chasis`

Tres niveles de visibilidad implementados en [src/modules/vehiculos/schemas/vehiculo.py](src/modules/vehiculos/schemas/vehiculo.py) y [src/core/ofuscacion.py](src/core/ofuscacion.py):

| Nivel | Uso | Qué muestra |
|---|---|---|
| `completo` | Dueño autenticado en `/vehiculos/{id}` | Valor sin ofuscar. |
| `origen` | Token de compra-venta (Fase 4) | Primeros 3 caracteres + país decodificado del WMI. |
| `oculto` | Vistas públicas mínimas | Solo país de origen; el valor literal nunca aparece. |

Ver skill [validacion-datos-ec](.claude/skills/validacion-datos-ec/SKILL.md) para reglas de validación y decodificación.

---

## 8. Dependencias externas frágiles y limitaciones conocidas

ANT, SRI, AMT y Fiscalía (FGE) son sitios públicos que cambian sin aviso. Reglas:

- **Tolerancia a fallos**: una fuente caída NO debe romper la respuesta global. El endpoint siempre responde 200, marcando la fuente fallida con `estado: error`.
- **Capturas de debug**: guardar `debug_<fuente>_*.png` en errores de scraping (gitignored).
- **Caché en BD**: respuestas con `estado in {consulta_realizada, sin_resultados}` se guardan; errores, `bloqueado_captcha` y `error_fuente` NO se cachean (para reintentar).
- **TTL de doble velocidad** ([src/modules/consulta/services/cache.py](src/modules/consulta/services/cache.py)): el TTL depende de la naturaleza del dato. Transaccional (multas/citaciones, infracciones, denuncias, valores) → **12h** (`CACHE_TTL_TRANSACCIONAL_MINUTOS`). Estático (características del vehículo) → **90 días** (`CACHE_TTL_ESTATICO_MINUTOS`). AS-IS: hoy cada fuente es un solo blob y ANT mezcla ambos, así que se rige por el TTL transaccional (gana la frescura). El TTL estático queda **reservado** para el TO-BE, cuando el perfil del vehículo se cachee como entrada propia.

### Limitación 1: SRI bloqueado por reCAPTCHA
El portal SRI usa **Google reCAPTCHA Enterprise invisible**. Playwright es detectable y la submission falla silenciosamente sin challenge visual. Resultado: `estado: bloqueado_captcha`. Pasa **tanto en local como en cloud**. Workarounds futuros:
- Servicios pagos de captcha-solving (2captcha, anti-captcha): ~$1-3 por 1000 resoluciones.
- `playwright-stealth` para reducir detectabilidad (no garantiza).
- Solicitar acceso al API oficial de SRI (proceso administrativo).

### Limitación 2: IPs de datacenter bloqueadas (AMT y FGE)
Descubierto al desplegar en Render (mayo 2026). Los portales de **AMT y Fiscalía** detectan IPs de proveedores cloud (Render, AWS, GCP) y sirven páginas distintas o desafíos anti-bot. Diferencia observada:

| Fuente | Local (IP residencial Ecuador/SA) | Render (IP datacenter US) |
|---|---|---|
| ANT | ✅ funciona | ✅ funciona |
| SRI | 📌 reCAPTCHA invisible | 📌 reCAPTCHA invisible |
| AMT | ✅ funciona | ❌ sirve `inputCode.jsp` (challenge) |
| FGE | ✅ funciona | ❌ sirve página sin `input#pwd` |

**No es un bug del código** — el código corre idéntico, los servidores responden distinto según IP origen.

Opciones para mitigar:
1. **Aceptar la limitación en cloud** (estado actual del MVP). Para demos: usar local. Para producción de bajo volumen: ANT puede ser suficiente.
2. **Proxy residencial pago** (Bright Data, Smartproxy, IPRoyal): $50–300/mes. Configurar en el cliente Playwright.
3. **Arquitectura híbrida**: backend FastAPI en cloud + workers de scraping en local/raspberry con IP residencial, que pushean resultados a la BD del cloud.
4. **API oficial** con cada institución: proceso administrativo, lento pero definitivo.

Antes de proponer cambios en `src/modules/consulta/services/amt.py` o `src/modules/consulta/services/fiscalia.py` para "arreglar" un error en producción, verificar si está corriendo desde IP residencial (local) o datacenter (Render). El skill [scraping-respetuoso](.claude/skills/scraping-respetuoso/SKILL.md) tiene la matriz de síntomas.

---

## 9. Privacidad y datos sensibles

| Tipo de dato | Acceso |
|---|---|
| Consultas a fuentes públicas (ANT/SRI/AMT/FGE) | Anónimo. Sin auth. |
| Vehículos guardados, dueños históricos, kilometraje, mantenimientos | Requiere cuenta del dueño. Filtrar por `usuario_id` en cada query. |
| VIN, motor, chasis | Mostrar completos solo al dueño autenticado; ofuscar para terceros. |
| Compartir compra-venta | Token con expiración ≤ 7 días, scope explícito (qué campos muestra). |

Reglas duras:
- Nunca devolver datos privados en el endpoint público `/consultar/{placa}`.
- Usar `Depends(usuario_actual)` o `Depends(vehiculo_propio)` para todo endpoint que toque datos del usuario.
- El scope del token define qué se ve; default mínimo, opt-in para cada campo sensible.

---

## 10. Reglas de Negocio del MVP (Fases 3 y 4)

Reglas arquitectónicas **inmutables** para Billetera, Favoritos, Mantenimientos y Marketplace. Aplican a todo código nuevo de estas fases; no se negocian sin acordarlo explícitamente. Se agrupan en tres bloques: infraestructura (requisitos previos), arquitectura/código y reglas de negocio.

### 10.1 Infraestructura (requisitos previos antes de codear las fases 3 y 4)
- **Base de datos definitiva**: el Postgres de Render free expira a los 90 días (ver sección 8 y 12). El MVP debe construirse sobre el proveedor definitivo — **Supabase o Neon** (PostgreSQL 16+). Crear el proyecto, obtener la `DATABASE_URL` y colocarla en el `.env` local y en las variables de entorno de Render.
- **`.env` jamás se sube a Git** (ya está en `.gitignore`). Toda config sensible va por env var (ver sección 11 y 12).
- **Variables requeridas del MVP**:
  - `DATABASE_URL` — cadena de conexión a la BD definitiva (Supabase/Neon).
  - `JWT_SECRET_KEY` — secreto de firma de los JWT. (El spec lo llamó `SECRET_KEY`; el nombre real en el código es `JWT_SECRET_KEY`, ver [src/core/database.py](src/core/database.py) y [src/modules/auth/security.py](src/modules/auth/security.py). No renombrar sin un refactor acordado.)
  - `CORS_ORIGINS` — orígenes permitidos para que el frontend en Vercel hable con el backend.

### 10.2 Arquitectura y código (restricciones técnicas)
- **Separación CRUD ↔ scraping**: las operaciones **CRUD del MVP** (Billetera, Favoritos, Mantenimientos, Marketplace) tocan **única y exclusivamente** la BD propia (PostgreSQL). **Bajo ningún concepto invocan ni alteran los servicios de Playwright** (`src/modules/consulta/services/ant.py`, `src/modules/consulta/services/sri.py`, etc.). El scraping sigue siendo de solo lectura.
  - **Por qué**: el scraping es lento, frágil y dependiente de IP (ver sección 8); acoplarlo a un CRUD haría que un portal caído rompa operaciones que no lo necesitan.
- **Migraciones manuales** (SQLAlchemy 2 + Alembic): no usar `--autogenerate` a ciegas. Cada archivo en `alembic/versions/` se revisa a mano y lleva nombre descriptivo (ej. `0004_billetera.py`). Ver skill [modelo-dominio-vehiculo](.claude/skills/modelo-dominio-vehiculo/SKILL.md).
- **Eager loading en Marketplace**: las consultas de SQLAlchemy que carguen vehículos con sus relaciones para el Marketplace deben usar **`selectinload`** para evitar el problema N+1 y optimizar el listado.
- **Idioma español estricto** (ver sección 5): tablas (`mantenimientos`, `vehiculos_favoritos`, `transacciones_tokens`), columnas (`kilometraje_relacionado`, `precio_venta_usd`, `url_externa`, `en_venta`), rutas (`/favoritos`, `/marketplace`) y variables.
- **Contrato de API estándar** (ver sección 6 y skill [respuesta-api-estandar](.claude/skills/respuesta-api-estandar/SKILL.md)): todo error de negocio se maneja elegantemente con un JSON estructurado — **nunca un crash / HTTP 500**. Códigos según el precedente del proyecto: **422** para validación de negocio (ej. kilometraje no monotónico), **404** para "no es tu vehículo" (no distinguir 403 de 404, para no filtrar IDs ajenos), **400** para formato de input inválido, **409** para conflictos (placa/email duplicado). **Excepción acordada (2026-05-30):** los **flujos de pago con tokens** (saldo insuficiente al desbloquear un perfil o publicar premium) devuelven **402 Payment Required**, no 422. El servicio `debitar_tokens` sigue lanzando `SaldoInsuficiente`; el endpoint la traduce a 402. (Antes el spec decía 422 también para tokens; se reservó 422 para validación pura y 402 para "te falta saldo".)

### 10.3 Reglas de negocio — Billetera de tokens
- **Saldo inicial**: todo usuario nuevo nace con **5 tokens** por defecto (saldo de cortesía).
- **Límite inferior**: el saldo **nunca puede ser negativo** (`>= 0`). Toda operación de débito valida saldo suficiente antes de aplicar; si no alcanza, rechaza la operación con error de negocio (ver contrato HTTP en 10.2).
- **Auditoría**: toda alteración del saldo genera un registro **obligatorio** en la tabla `transacciones_tokens`.
- **Microdesbloqueos por tokens** (consulta por placa): el catálogo vive en BD (`productos_consulta`, fuente de verdad de precios; seed canónico en `services/catalogo_productos.py`). Cada compra se registra en `desbloqueos_consulta` (UK `usuario_id+placa+producto_codigo` → **no doble cobro**; idempotente). Reglas: **un producto inactivo no se desbloquea** (422); **no se cobra si el dato no está disponible** (409); saldo insuficiente → 402. Endpoints en `routers/desbloqueos.py`. Detalle en [docs/producto/modelo_tokens_microdesbloqueos.md](docs/producto/modelo_tokens_microdesbloqueos.md). **1 token ≈ USD 0.04.** **Reajuste Fase 2.5 (migración 0016):** los **datos públicos simples** (clase, servicio, marca, modelo, año, color, estado de matrícula) son **gratis** (`consulta_publica_base`, 0 tokens); solo se cobra por datos con **costo de proveedor / dificultad / valor comercial** (`identificadores_tecnicos` 3, `multas_con_montos` 10, `titular_validado` 5, `valores_matricula_sri` 12, `alertas_legales` 8, `reporte_compra_segura` 40, `verificacion_marketplace` 100). Sin proveedor confiable (titular, SRI, alertas legales) → enlace oficial, no cobro.

### 10.4 Reglas de negocio — Favoritos (`vehiculos_favoritos`)
- **Desacoplamiento**: la tabla guarda la **placa como `String`**, **no** como clave foránea (FK) a `vehiculos`. Un usuario puede agregar a favoritos una placa que NO existe en nuestra BD ni le pertenece.
- **Validación**: toda placa que entre a `vehiculos_favoritos` debe aprobar **`validar_placa`** (formato ecuatoriano válido, de [src/core/validators.py](src/core/validators.py)) y guardarse normalizada.

### 10.5 Reglas de negocio — Mantenimientos
- **Inmutabilidad monotónica**: al registrar un mantenimiento, la `fecha` y el `kilometraje_relacionado` deben ser **iguales o mayores** al último registro de ese vehículo. No se puede retroceder en el tiempo ni bajar el odómetro.
  - **Por qué**: el historial debe ser coherente y creciente, igual que las lecturas de kilometraje de Fase 2 ([src/modules/vehiculos/routers/kilometraje.py](src/modules/vehiculos/routers/kilometraje.py)).
- **Propiedad**: un usuario solo puede registrar mantenimientos sobre un `vehiculo_id` que le pertenezca, validado por el token JWT (`Depends(vehiculo_propio)`, ver sección 9).

### 10.6 Reglas de negocio — Marketplace (público) y token de compra-venta
Coexisten dos mecanismos de compra-venta:

- **Token privado** (modelo de la Fase 4 original): enlace temporal (`enlaces_compartidos`, `VehiculoSalidaCompartida`) que un comprador puntual ve sin cuenta, con scope explícito y expiración ≤ 7 días (ver secciones 7 y 9). No es un listado público.
- **Marketplace público** (`GET /marketplace`):
  - **Condición de venta**: un auto aparece en el listado solo si `en_venta` es `True` **y** `precio_venta_usd` es mayor a `0`.
  - **Privacidad**: el listado **nunca** expone el **VIN completo** (usar nivel `oculto` u `origen`, ver sección 7) ni el **nombre real del dueño**. Solo se publican las características del auto y la `url_externa` de contacto.
- **Publicaciones internas + verificación premium** (`publicaciones_internas`): plan `light` (gratis) / `premium` (cobra tokens, ver §10.3). El estado de verificación (`estado_verificacion`: `no_verificado` / `pendiente` / `verificado` / `rechazado`) gobierna el sello **"Verificado por la plataforma"**:
  - Una premium nace `pendiente`. Solo un **admin** (`admin_actual`, lista `ADMIN_EMAILS`) la marca `verificado` o `rechazado` vía `POST /marketplace/publicaciones/{id}/verificar` (decisión terminal). La cola se lee con `GET /marketplace/publicaciones/pendientes-verificacion` (solo admin). Verificar registra `verificado_en` (auditoría, migración 0013).
  - Solo las **premium** se verifican (verificar una light → 422). El sello solo se muestra cuando `estado_verificacion == verificado`. Mismo patrón que la moderación de referencias (§ referencias).
- **Referencias aportadas** (`publicaciones_referenciadas`): el usuario pega un link externo (FB/OLX/…); NO se raspa; entra `pendiente` y un admin la aprueba/rechaza (`/marketplace/referencias/...`). En el feed es un **enlace vivo** al anuncio original.
- **Ficha técnica de la publicación** (`fichas_publicacion`, migración 0017 — market de autos): 1:1 con la publicación interna. **3 bloques** (`motor_suspension`, `carroceria`, `interiores`) + `extras` (láminas de seguridad, llantas nuevas, …), guardados como JSONB pero **validados por Pydantic con `extra="forbid"`** (catálogos `Literal` es-EC; el shape lo exige la API, no la BD). Registro: `PATCH /marketplace/publicaciones/{id}/ficha` (solo dueño, upsert parcial por `model_fields_set`, **gratis** — la transparencia no se cobra). Consulta: `GET /marketplace/publicaciones/{id}` (público, solo `activa`) devuelve feed + ficha + **`completitud`** (% de campos llenos, señal de transparencia; también va en el feed como `completitud_ficha`). Regla de rutas: la dinámica `{publicacion_id}` se declara AL FINAL del router para no capturar `mias`/`pendientes-verificacion`.

---

## 11. Cómo correr localmente (Windows + PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env   # primera vez; ajustar DATABASE_URL y JWT_SECRET_KEY
alembic upgrade head
python run.py
```

Probar:
```powershell
curl http://localhost:8000/consultar/ABC1234
```

**Importante**:
- Usar `python run.py`, NO `uvicorn main:app --reload`. En Windows, uvicorn deja activa `WindowsSelectorEventLoopPolicy` en el worker, lo cual rompe Playwright con `NotImplementedError`. El launcher [run.py](run.py) fija `WindowsProactorEventLoopPolicy` correctamente.
- En local, las 3 fuentes (ANT/AMT/FGE) funcionan. SRI siempre devuelve `bloqueado_captcha`.

### Frontend local (en repo separado)

```powershell
cd ..\consulta-placas-web
npm install
# .env.local apunta a http://localhost:8000 por default
npm run dev      # http://localhost:3000
```

---

## 12. Despliegue (MVP en cloud)

Ver guía completa en [docs/despliegue.md](docs/despliegue.md). Resumen:

- **Backend**: Render web service plan free, **runtime Docker** (no native Python). Imagen base `mcr.microsoft.com/playwright/python:v1.48.0-jammy`. Blueprint en [render.yaml](render.yaml).
- **BD**: PostgreSQL en Render free (90 días gratis, después $7/mes o migrar a Supabase/Neon).
- **Frontend**: Vercel free. `NEXT_PUBLIC_API_URL` apunta al servicio Render. CORS estricto en backend con `CORS_ORIGINS`.

### Reglas duras del deploy
- **Toda config sensible va en env vars** (`.env` local, dashboard de Render/Vercel en prod). Nada hardcodeado.
- **`HOST=0.0.0.0` y `PORT` dinámico** en producción (ya soportado en [run.py](run.py)).
- **CORS estricto**: solo la URL del frontend más localhost para dev.
- **Cold start del free tier**: ~30s tras 15 min de inactividad. Mitigar con cron externo (UptimeRobot) que toque `/health` cada 10 min.
- **DATABASE_URL prefix**: Render emite `postgresql://`, psycopg 3 requiere `postgresql+psycopg://`. `src/core/database.py` reescribe automático.
- **bcrypt fix**: `bcrypt<4.0` pineado por incompatibilidad con `passlib==1.7.4` (`AttributeError: __about__`).

Skill paso a paso: [desplegar-mvp](.claude/skills/desplegar-mvp/SKILL.md).

---

## 13. Diagramas de arquitectura

Diagramas vivos del sistema en [docs/arquitectura.md](docs/arquitectura.md) (Mermaid). Renderizan nativos en VSCode, GitHub y GitLab. Mantener actualizados:
- Cada vez que cierre un bloque del roadmap → marcar el nodo correspondiente.
- Cuando se agregue una fuente → sumar a la topología y la secuencia.
- Cuando se cree una entidad → sumar al ER.

---

## 14. Disciplina de iteración (anti trial-and-error)

Cada iteración fallida cuesta tiempo del usuario. Reglas obligatorias antes de proponer código nuevo de scraping o parsing:

1. **Evidencia antes que suposición**. Si vamos a tocar una fuente nueva o desconocida: primero un paso de descubrimiento (screenshot + dump de frames) y solo después escribir el scraper completo. No iterar a ciegas sobre selectores.
2. **Aprovechar lecciones documentadas**. Antes de escribir un servicio nuevo, leer el skill [scraping-respetuoso](.claude/skills/scraping-respetuoso/SKILL.md) y los gotchas registrados (iframe, componentes custom, captcha invisible, overlay de loading, IPs datacenter).
3. **Parser sobre HTML real, no sobre regex adivinados**. Si no se vio el HTML/screenshot, el parser es especulativo. Decirlo explícitamente y dejar TODO claro.
4. **Higiene de refactor**. Al cambiar nombres de variables o estructuras, hacer grep del nombre viejo y eliminarlo completamente — no dejar referencias muertas que aparecen en runtime (NameError, KeyError).
5. **Tests de parser con muestras de texto** antes de pegarlo al scraper. Un parser que no se probó con texto crudo real es deuda técnica.
6. **Una sola pregunta clarificadora a la vez**. Si hay dudas críticas, preguntar antes de codear. No suponer.
7. **Local vs cloud**: si un servicio falla solo en cloud y no en local, casi siempre es IP o ENV — NO código. Verificar antes de "arreglar".

Aplicación práctica: para AMT terminamos en ~6 rondas porque saltamos estos pasos. Para futuras fuentes, seguir el orden.

---

## 15. Qué NO hacer

- No reescribir nombres al inglés.
- No mockear las fuentes en tests de integración — usar fixtures HTML guardados.
- No exponer respuestas crudas de scraping al usuario final; siempre pasar por el parser.
- No agregar dependencias nuevas sin justificación documentada.
- No saltar fases del roadmap sin acordarlo explícitamente.
- No paralelizar requests contra la misma fuente (ver skill `scraping-respetuoso`).
- No commitear `.env` o variables sensibles. Todas las claves se generan o se piden por env var.
- No mezclar lógica de UI con lógica de scraping — frontend y backend están separados a propósito.
- No agregar campos sensibles (VIN, motor, chasis, kilometraje real) a respuestas públicas — usar schemas con nivel de visibilidad apropiado.
