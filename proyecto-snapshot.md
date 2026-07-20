# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)
**Generado:** 2026-06-01
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?
Plataforma (web + futura móvil) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa. Agrega información de fuentes oficiales (ANT, SRI, AMT, Fiscalía) en un **perfil consolidado** por temática, ofrece un **garage privado** (historial del dueño), un **marketplace de compra-venta** y un modelo de **microdesbloqueos por tokens**: consulta gratis con datos públicos + desbloqueo por tokens de los datos con costo/valor real. El usuario final es público general de clase media-baja; el tono visual es "confianza clara". Hoy el código cubre el MVP del Pilar 1 (consulta) + auth + garage + marketplace + billetera de tokens.

## 2. Stack tecnológico
**Backend** (`consulta_placas_ec`):
- Python 3.11+ · FastAPI · Pydantic 2.
- PostgreSQL 16 (Neon) · SQLAlchemy 2 · Alembic (migraciones manuales 0001–0016).
- Playwright async (Chromium) para scraping; `httpx` donde aplica.
- Auth: `passlib[bcrypt]` (`bcrypt<4.0` pineado) + `python-jose` (JWT HS256).
- Deploy: Docker (imagen oficial Playwright) en **Render** free.

**Frontend** (`consulta-placas-web`, repo aparte):
- Next.js 16 (App Router, RSC, Turbopack) · React 19 · Tailwind CSS 4 (`@theme` inline) · TypeScript estricto.
- Tema **claro** "Confianza clara" (gradiente azul→cian). Deploy en **Vercel** free.

## 3. Estado actual — AS-IS

### ✅ Completado
- **Consulta pública por placa** (`/consultar/{placa}` y `/consultar/{placa}/perfil`): ANT (matriculación + citaciones), SRI (valores; bloqueado por reCAPTCHA → enlace oficial), AMT/EPMTSD (infracciones municipales), FGE (consulta_externa por hCaptcha).
- **Perfil Consolidado** server-side (`services/consolidador.py`): arma `VehiculoConsolidadoResponse` por temática (datos básicos, identificación, titular, multas, valores, novedades) + `estado_fuentes`.
- **Caché en BD** (`consultas`) con TTL de doble velocidad (transaccional 12h / estático 90d).
- **Arquitectura híbrida**: modo síncrono (IP residencial EC) o worker (encola AMT/EPMTSD) para sortear el bloqueo de IPs de datacenter.
- **Auth**: registro, login, `/auth/me` (incluye `es_admin` según `ADMIN_EMAILS`).
- **Billetera de tokens**: saldo inicial 5, débito real (`debitar_tokens`), auditoría inmutable (`transacciones_tokens`). Saldo insuficiente → **HTTP 402**.
- **Microdesbloqueos por tokens (v2)**: catálogo en BD (`productos_consulta`) + `desbloqueos_consulta` (UK usuario+placa+producto → no doble cobro) + `costos_proveedor_consulta`. Router `routers/desbloqueos.py` (`GET /consultar/{placa}/productos`, `POST .../desbloquear/{codigo}` con 400/422/409/402 idempotente, `GET .../desbloqueos`).
  - **Reajuste Fase 2.5** (migración 0016): ficha pública **gratis** (`consulta_publica_base`, 0 tokens); solo se cobra por costo/dificultad/valor real. **1 token ≈ USD 0.04**. Catálogo: `identificadores_tecnicos` (3), `titular_validado` (5), `alertas_legales` (8), `multas_con_montos` (10), `valores_matricula_sri` (12), `reporte_compra_segura` (40), `verificacion_marketplace` (100).
- **Capa de proveedores vehiculares (Fase 3, `consulta/providers/`)**: contrato normalizado `ResultadoVehicular` + `MockProvider` funcional (default `PROVEEDOR_VEHICULAR_ACTIVO=mock`) + stubs `consultas_ec`/`placaapi_ec`/`webservices_ec` (sin API key → no ofrecen ni cobran). El proveedor entrega VIN/motor/chasis y validación de titular; se invoca **solo al desbloquear** (con caché en `consultas` fuente `PROVEEDOR`), nunca en el preview gratis; no se re-llama si hay caché. El **titular siempre sale ofuscado/validado, jamás el nombre crudo**. NO scraping, NO captcha.
- **Experiencia progresiva (frontend)**: preview gratis + sección **"Completa tu revisión del vehículo"** con tarjetas de desbloqueo (`UnlockCard`/`ProductoConsultaCard`/`ReporteCompraSeguraCard`/`TokenBadge`). Flujo UX: sin sesión→login, 402→CTA recargar, 409 dato no disponible, éxito sin recargar, idempotente.
- **Garage privado**: vehículos (con `ciudad_registro`), dueños históricos, kilometraje (monotónico), mantenimientos, favoritos.
- **Marketplace**: publicaciones internas (light gratis / premium cobra tokens) con `GET /marketplace/feed`; referencias aportadas (link externo → moderación admin → **detalle local** `/marketplace/referencias/{id}`, con botón explícito al anuncio original; sin scraping); token de compra-venta (`enlaces_compartidos`, scope + expiración ≤7d).
- **Frontend**: landing, consultar (perfil + desbloqueos), mi-garage, login/registro (sesión persistente), **precios por tokens** (paquetes $1=25 … $10=280), marketplace + publicar + referenciar + mis-referencias, admin/moderación + admin/verificaciones.

### 🔄 En progreso / parcial
- **Proveedor real de datos vehiculares (POC `consultas_ec`)**: integración HTTP real implementada (httpx + mapeo defensivo + costo en `costos_proveedor_consulta`) + harness `scripts/evaluar_proveedor.py` + doc `docs/producto/evaluacion_proveedor_real.md`. **Medición real pendiente** de `CONSULTAS_EC_API_KEY`+`BASE_URL` y confirmación del contrato; hoy corre con `MockProvider` (dry-run 60 placas = 100% éxito). Decisión de activar según criterio del doc.
- **Verificación "Verificado por la plataforma"**: el dueño solicita el sello (100 tokens) → `pendiente`; el flip a `verificado` es paso admin (`/admin/verificaciones`).
- **OCR / foto (Pilar 5)**: `routers/ocr.py` + `services/vision.py` esbozados; sin flujo completo.

### ⚠️ Problemas o deuda técnica identificada
- **SRI tras reCAPTCHA Enterprise**: no se puede leer el valor a pagar automáticamente → solo enlace al portal (`valores_matricula_sri` queda `disponible=false`). Vía definitiva: API oficial del SRI (trámite).
- **Fiscalía (FGE)**: portal SIAF con hCaptcha → `consulta_externa`. `alertas_legales` se trata como enlace oficial / no producto de exposición de PII hasta tener fuente estructurada legalmente segura.
- **ANT no informa montos** de citaciones (solo conteo) → pendientes de ANT sin valor.
- **IPs de datacenter bloqueadas** (AMT/EPMTSD/FGE) desde Render → requieren worker residencial / proxy / modo síncrono. ANT y SRI no dependen de esto.
- **FGE y EPMTSD-municipal desactivados en la UI** (`FUENTES_INACTIVAS` en el frontend) hasta tener datos accionables.
- **Cold start** del free tier (~30s) tras inactividad.
- **`consulta` depende de `auth`+`tokens`** (excepción documentada en AGENTS.md §1.1 por el desbloqueo).
- **Excepción de contrato**: flujos de pago con tokens devuelven **402** (no 422), documentado en AGENTS.md §10.2.
- **Lint frontend**: 4 errores pre-existentes `react-hooks/set-state-in-effect` en `Header.tsx` y `marketplace/mis-publicaciones`.

## 4. Estructura de archivos actual

### Backend (`consulta_placas_ec`)
```
main.py · run.py · worker.py · registry.py · render.yaml · requirements.txt · .env.example
alembic/versions/0001..0016      (migraciones manuales)
src/core/        database, validators, ofuscacion (+ofuscar_nombre), proxy_apify
src/modules/
  auth/          models (Usuario, TransaccionToken), router, security, dependencies, schemas
  tokens/        service (debitar_tokens, SaldoInsuficiente), router
  consulta/      routers/{consulta, ocr, desbloqueos}   schemas
                 services/{ant, sri, amt, epmtsd, fiscalia, consultasecuador,
                           ecuadorlegalonline, consolidador, catalogo_fuentes,
                           catalogo_productos, desbloqueos, proveedor, cache, cola,
                           captcha, vision, extractor_apify, _axiscloud}
                 providers/{base, mock_provider, consultas_ec, placaapi_ec,
                            webservices_ec, selector}      ← Fase 3
                 models/{consulta, cola_scraping, desbloqueos}
  vehiculos/     routers/{vehiculos, duenos, kilometraje, mantenimientos, favoritos}
                 models/{vehiculo, dueno_historico, kilometraje, mantenimiento, favorito}  schemas
  marketplace/   routers/{marketplace, compartidos, publicaciones}  models  schemas
scripts/         discover.py · validar_desbloqueos.py · evaluar_proveedor.py
docs/            AGENTS espejo, bitacora, despliegue, arquitectura, producto/*.md
```

### Frontend (`consulta-placas-web`)
```
src/app/         page (landing) · layout · globals.css · precios · consultar/[placa]
                 login · registro · mi-garage · marketplace(+publicar/referenciar/mis-*)
                 admin/{moderacion, verificaciones}
src/components/  PerfilVehiculo · UnlockCard · ProductoConsultaCard · ReporteCompraSeguraCard
                 TokenBadge · BentoCard · ConsultaForm · Header · Footer · ListingCard · CampoTexto
src/lib/         api.ts · auth.ts · perfil.ts
src/types/       api.ts  (mirror de los schemas Pydantic)
```

## 5. Skills y herramientas configuradas
- **AGENTS.md** (fuente de verdad; `CLAUDE.md` es shim `@AGENTS.md`). Backend y frontend con su CLAUDE.md.
- Skills del proyecto en `.claude/skills/`: `agregar-fuente-consulta`, `scraping-respetuoso`, `respuesta-api-estandar`, `validacion-datos-ec`, `modelo-dominio-vehiculo`, `desplegar-mvp`, `project-snapshot`.
- Bitácora viva en `docs/bitacora.md`; diagramas Mermaid en `docs/arquitectura.md`; producto en `docs/producto/*.md`.

## 6. Decisiones técnicas tomadas
- **Monolito modular (DDD)** por dominio en `src/modules/` + `src/core`; modelos registrados en `registry.py`; comunicación por interfaz pública.
- **Idioma español (es-EC, tuteo)** en código, rutas, columnas y copy. Copy NO agresivo (nada de "paga para ver el dueño").
- **Contrato de respuesta estándar**: 200 siempre por fuente; estados `consulta_realizada/error/consulta_externa/...`. Negocio: 422 validación, 404 "no es tuyo", 409 conflicto/sin dato, **402 pago con tokens**.
- **Monetización**: datos públicos gratis; solo se cobra por costo de proveedor / dificultad / valor comercial. 1 token ≈ USD 0.04. Cobrar **solo lo entregado** (no se cobra si no hay dato). Idempotencia por UK.
- **Privacidad/PII**: VIN/motor/chasis ofuscados salvo desbloqueo; **titular nunca crudo** (validación + iniciales). Sin evasión de captcha; SRI/Fiscalía como enlace oficial.
- **Capa de proveedores** desacoplada (contrato normalizado + selector por env var); el proveedor se invoca solo al desbloquear y se cachea.
- **Migraciones manuales** (sin autogenerate a ciegas). **Eager loading** (`selectinload`) en marketplace.

## 7. Últimos cambios (sesión 2026-05-30 / 06-01)
- **POC proveedor real `consultas_ec`**: HTTP real (httpx + mapeo defensivo), costo en
  `costos_proveedor_consulta`, harness `scripts/evaluar_proveedor.py` y doc de evaluación.
  Sin credenciales degrada limpio; dry-run con mock OK. Medición real pendiente de API key.
  Fix: la home mostraba el modelo de suscripción viejo (Pro $4.99/mes) → reescrita al modelo por tokens.
- **Fase 3 — capa de proveedores + experiencia progresiva** (backend `4c4e3f8`, frontend `67f9429`):
  `consulta/providers/` (contrato `ResultadoVehicular`, `MockProvider`, 3 stubs reales, `selector`),
  `services/proveedor.py` (capacidades sin llamar, caché, "asegurar" solo al desbloquear), schema
  `Titular` + `ofuscar_nombre`, consolidador alimentado por proveedor (gateado), `.env.example` con
  `PROVEEDOR_VEHICULAR_ACTIVO`/`*_API_KEY`. Frontend: componentes de desbloqueo + sección "Completa
  tu revisión del vehículo". Sin proveedores reales (mock por defecto). Sin migración nueva.
- **Fase 2.5 — reajuste comercial** (migración 0016): datos públicos gratis; token USD 0.05→0.04;
  renombres/reprecios de catálogo; verificación marketplace 80→100; precios reescritos en la web;
  copy corregido ("Conoce"; no se promete SRI/Fiscalía automáticos).
- **Microdesbloqueos v2** (migración 0015): catálogo en BD + auditoría comercial + router dedicado.

**Git** — backend HEAD `4c4e3f8` · frontend HEAD `67f9429`. Ambos repos **limpios y pusheados**.
**Prod**: Render (backend) + Vercel (frontend) · BD Neon en `alembic head` **0016** (`alembic upgrade head` ya aplicado para 0016; Fase 3 no agrega migración).

## 8. Para continuar en Gemini — instrucciones
> Eres un asistente de arquitectura y planificación de software.
> Tienes el contexto completo del proyecto arriba.
> El usuario quiere planificar el TO-BE: próximos pasos, mejoras, nuevas funcionalidades.
> Cuando el usuario describa qué quiere hacer, responde con:
> 1. Evaluación de impacto sobre lo existente
> 2. Archivos a crear o modificar
> 3. Skills de Claude Code a activar
> 4. Estructura sugerida de la solución
> 5. Posibles riesgos o dependencias

## 9. Próximos pasos sugeridos
1. **Integrar un proveedor real** de datos vehiculares: implementar la llamada HTTP en uno de los stubs (`providers/consultas_ec.py` u otro), mapear su respuesta al contrato, cargar la `*_API_KEY` y poner `PROVEEDOR_VEHICULAR_ACTIVO=<x>` en Render. Validar costo/margen vs `costos_proveedor_consulta`.
2. **Mostrar saldo de tokens y recarga** en el flujo de desbloqueo (ya hay CTA a /precios en 402); preparar el gateway de pago local (PlaceToPay/MercadoPago) para vender tokens reales.
3. **Cerrar SRI**: gestionar API oficial del SRI o un proveedor confiable para activar `valores_matricula_sri` (hoy enlace oficial).
4. **Pilar 5 (OCR/foto)**: completar el flujo `foto → placa → consulta` (`routers/ocr.py` + `services/vision.py`).
5. **Limpieza de deuda**: resolver los 4 errores de lint `set-state-in-effect` del frontend y revisar la UI de FGE/EPMTSD desactivadas.
