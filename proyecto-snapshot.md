# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)
**Generado:** 2026-05-30 (-05:00)
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?
Plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa. Agrega información de fuentes oficiales y no oficiales (matriculación, citaciones, infracciones municipales, valores tributarios, noticias del delito) en un **Perfil Consolidado** orientado a la entidad vehículo. El MVP en producción cubre el Pilar 1 (consulta pública por placa); el producto completo contempla además consulta por foto (OCR), historial privado del vehículo y modo compra-venta con token. Público objetivo: clase media-baja ecuatoriana; la web busca transmitir confianza y enganchar.

## 2. Stack tecnológico
- **Backend** (repo `consulta_placas_ec`): Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic, Pydantic 2, Playwright async (Chromium), `httpx`, `apify-client` (extracción en la nube, opcional), PostgreSQL (Neon). Auth passlib[bcrypt<4.0] + python-jose (JWT HS256). Docker (imagen Playwright) en Render.
- **Frontend** (repo `consulta-placas-web`): Next.js 16 (App Router, Turbopack, RSC), React 19, Tailwind CSS 4. Vercel.
- **Worker híbrido** (`worker.py`): proceso pull-only que drena `cola_scraping` desde IP residencial EC (las fuentes municipales/judiciales bloquean IPs de datacenter).

## 3. Estado actual — AS-IS

### ✅ Completado y en producción
- **Arquitectura modular (DDD)**: `src/modules/{auth,tokens,consulta,vehiculos,marketplace}` + `src/core`. Modelos en `src/registry.py`.
- **Perfil Consolidado de Vehículo**: `services/catalogo_fuentes.py` (catálogo de 7 fuentes), `schemas.py` (`VehiculoConsolidadoResponse`), `services/consolidador.py` (agrega por-fuente; `estado_fuentes` **catálogo-driven**). Endpoint **`GET /consultar/{placa}/perfil`** — **desplegado y verificado en prod** (HTTP 200 con datos reales de ANT). Legacy `/consultar/{placa}` conservado.
- **7 fuentes** (todas `implementada=True`):
  - **ANT** (oficial, Playwright directo) — funciona en cloud y local.
  - **AMT** (`ps_empresa=03`) y **EPMTSD** (`ps_empresa=06`): misma plataforma AxisCloud → adaptador compartido `services/_axiscloud.py`; `amt.py`/`epmtsd.py` son wrappers. Vía worker híbrido.
  - **FGE** (SIAF, worker; acepta placa o cédula).
  - **SRI**, **ConsultasEcuador**, **EcuadorLegalOnline**: `consulta_externa` (reCAPTCHA / afiliado / paywall+PII → no scrapeables; enlace + disclaimer).
- **Rebranding "Revisa tu Carro EC"** + **tema claro "Confianza clara"** (azul→cian) en todo el frontend — desplegado en Vercel. `PerfilVehiculo.tsx` consume `/perfil` y pinta por secciones; helpers de solo-lectura en `src/lib/perfil.ts` (antes `consolidar.ts`).
- **Extracción en la nube (Apify)**: `services/extractor_apify.py` (`ApifyExtractor.obtener_datos(url)` con `ApifyClientAsync`, actor `apify/playwright-scraper`). **Validado en vivo** contra `example.com`. Responsabilidad única (solo HTML). Import perezoso (no rompe el arranque sin la dependencia).
- **Proxy residencial gateado**: `src/core/proxy_apify.py` (`proxy_playwright()` lee `SCRAPER_PROXY_URL` de cualquier proveedor, o `APIFY_PROXY_*`). Cableado en `_axiscloud.py` y `fiscalia.py` (ANT queda directo). Sin config → scraping directo (comportamiento actual).
- **Resiliencia worker**: `error_fuente` tras reintentos, ventana de enfriamiento; caché doble velocidad (12h transaccional / 90d estático).
- **Auth + dominio**: JWT, CRUD vehículos, dueños, kilometraje, mantenimientos, favoritos, billetera (lectura+auditoría), marketplace + enlaces compartidos.

### ⚠️ Bloqueante para "100% operativo" en la nube (hallazgo 2026-05-30)
- **AMT/EPMTSD/FGE quedan `en_proceso` en la nube**: necesitan IP **residencial** (datacenter bloqueado, §8). Hoy dependen del worker en IP residencial.
- Se evaluó **Apify** para resolverlo: la cuenta es **plan FREE** → solo proxy **datacenter** (`BUYPROXIES94952`), **sin residencial** (todas las pruebas de proxy residencial dieron **403**). El plan free NO sirve para estas fuentes (ni por proxy ni por Actor, ambos requieren residencial).
- La infra de proxy ya está lista y gateada; **se activa** con: (1) Apify de pago con residencial, (2) otro proveedor residencial vía `SCRAPER_PROXY_URL` (IPs de Ecuador), o (3) seguir con el worker en una máquina residencial EC (gratis; la IP local del dev ya es EC/Telconet).

### ⚠️ Otra deuda técnica
- SRI/ConsultasEcuador/EcuadorLegalOnline: reCAPTCHA → `consulta_externa` permanente (ningún proxy lo arregla).
- `identificacion` (chasis/motor) en el schema pero sin fuente scrapeable; se ofrece enlace externo.
- Imágenes referenciales del vehículo: pospuesto (no hay foto por placa; plan híbrido render-por-modelo + ilustración por clase).
- Token Apify compartido por chat → **rotar**.

## 4. Estructura de archivos actual
```
consulta_placas_ec/
├── AGENTS.md (+ CLAUDE.md shim) · main.py · run.py · worker.py · Dockerfile · render.yaml · requirements.txt
├── alembic/versions/0001..0009 (migraciones manuales)
├── docs/ arquitectura.md · arquitectura_hibrida.md · bitacora.md · despliegue.md · worker.md
├── scripts/ discover.py · worker_*.ps1
├── .claude/skills/ (6 skills de dominio)
└── src/
    ├── registry.py
    ├── core/ database.py · validators.py · ofuscacion.py · proxy_apify.py
    └── modules/
        ├── auth/ · tokens/ · vehiculos/ · marketplace/
        └── consulta/
            ├── routers/ consulta.py (incl. /perfil) · ocr.py
            ├── models/ consulta.py · cola_scraping.py
            ├── schemas.py (VehiculoConsolidadoResponse + EstadoFuente)
            └── services/ ant · sri · amt · epmtsd · _axiscloud · fiscalia ·
                          consultasecuador · ecuadorlegalonline · catalogo_fuentes ·
                          consolidador · extractor_apify · cache · cola · captcha · vision
```
Frontend: `src/app/{page,layout,consultar,login,registro,precios,mi-garage}` · `src/components/{PerfilVehiculo,ConsultaForm,Header,Footer,CampoTexto}` · `src/lib/{api,auth,perfil}` · `src/types/api.ts` · `globals.css`.

## 5. Skills y herramientas configuradas
6 skills de dominio en `.claude/skills/`: agregar-fuente-consulta, scraping-respetuoso, respuesta-api-estandar, validacion-datos-ec, modelo-dominio-vehiculo, desplegar-mvp. `AGENTS.md` es la fuente de verdad (§4 ya actualizada con marca/tema claro).

## 6. Decisiones técnicas tomadas
- `estado_fuentes` catálogo-driven; adaptador AxisCloud compartido (AMT/EPMTSD).
- Fuentes tras captcha/paywall/afiliado → `consulta_externa` (no scrapers especulativos, §14/§15).
- Frontend no transforma: lee el contrato consolidado del backend.
- Proxy residencial **provider-agnostic** (`SCRAPER_PROXY_URL`) para no atarse a Apify; ANT sin proxy.
- Apify free NO tiene residencial → para 100% cloud hace falta residencial de pago o worker residencial.
- Privacidad: VIN/motor/chasis ofuscados para terceros; nunca PII de propietario en consulta pública.

## 7. Últimos cambios (git log)
```
backend:
f18d43e feat: soporte de proxy residencial (gateado) para AMT/EPMTSD/FGE
9ff5e06 fix: ApifyExtractor compatible con apify-client v3 (run_timeout timedelta + Run modelo)
d19686c feat: cliente de extracción Apify + docs al día (marca, tema claro, 7 fuentes)
33c5d3f docs: regenerar snapshot (7 fuentes + rebranding + tema claro)
55d07c0 feat: integrar EPMTSD + ConsultasEcuador + EcuadorLegalOnline (catálogo-driven)
frontend:
919eed3 refactor: consolidar.ts -> perfil.ts (solo lectura)
cd77d47 feat: rebranding 'Revisa tu Carro EC' + tema claro + perfil consolidado
```

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
1. **Decidir la vía residencial para AMT/EPMTSD/FGE** (el bloqueante de "100% operativo"): Apify de pago con residencial, otro proveedor vía `SCRAPER_PROXY_URL` con IPs de Ecuador, o worker en máquina residencial EC. Validar en vivo a través del proxy elegido.
2. **Desplegar el worker** (en la nube con proxy residencial, o en máquina EC) para que AMT/EPMTSD/FGE pasen de `en_proceso` a datos en producción.
3. Rotar el token de Apify (se compartió por chat).
4. Imágenes referenciales del vehículo (híbrido render-por-modelo + ilustración por clase, con sello "referencial").
5. Actualizar `docs/arquitectura.md` si cambia la vía de egreso (proxy vs worker residencial).
6. Roadmap: Fase 5 (OCR por foto) y débito real de tokens.
