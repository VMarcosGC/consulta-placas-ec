# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)
**Generado:** 2026-05-30 (-05:00) · rev. desbloqueo PII por tokens + marketplace (publicaciones/referencias/moderación)
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?
Plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa. Agrega fuentes oficiales y no oficiales (matriculación, citaciones, infracciones, valores tributarios, condición/antecedentes, noticias del delito) en un **Perfil Consolidado** orientado a la entidad vehículo. MVP en producción: Pilar 1 (consulta pública por placa). El producto completo contempla además consulta por foto (OCR), historial privado y modo compra-venta con token. Público: clase media-baja ecuatoriana; la web busca confianza y atracción.

## 2. Stack
- **Backend** (`consulta_placas_ec`): Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic, Pydantic 2, Playwright async, `httpx`, `apify-client` (opcional), PostgreSQL (Neon). Docker en Render.
- **Frontend** (`consulta-placas-web`): Next.js 16 (App Router/RSC), React 19, Tailwind 4. Vercel.
- **Worker híbrido** (`worker.py`): drena `cola_scraping` desde IP residencial EC. Corre en la máquina del dev como **tarea programada `ConsultaPlacasWorker`** (autoarranca al login, reinicio ante fallo).

## 3. Estado actual — AS-IS

### ✅ En producción y operativo
- **API pública** (Render) + **frontend** (Vercel, "Revisa tu Carro EC", tema claro azul→cian) + **worker** (máquina EC, tarea programada). Loop público verificado: Render encola AMT/EPMTSD → worker procesa → caché Neon → frontend muestra.
- **Perfil Consolidado** catálogo-driven: `GET /consultar/{placa}/perfil` → `VehiculoConsolidadoResponse`. `catalogo_fuentes.py` + `consolidador.py`. Legacy `/consultar/{placa}` conservado.
- **Modo de scraping dual** (`SCRAPING_SINCRONO`, router):
  - **Síncrono** (IP residencial EC): ANT/AMT/EPMTSD se scrapean **en paralelo** (`asyncio.gather`, sesión de caché propia c/u) → datos reales en UNA llamada (~16s), sin worker. Validado en vivo.
  - **Worker** (default, nube datacenter): ANT directo; AMT/EPMTSD encolan (`en_proceso`) y el worker (IP residencial) las llena. Validado en prod.
- **Fuentes con datos reales inline**: **ANT** (vehículo + citaciones por estado + fechas matrícula/vence), **AMT** (Quito) y **EPMTSD** (Santo Domingo) — infracciones por categoría con montos. Plataforma AxisCloud compartida (`_axiscloud.py`, `ps_empresa` 03/06).
- **Detalle de multas** (`multas_detalle`): por fuente, con ámbito, total, pendientes, total a pagar y categorías (Pendientes/Pagadas/Anuladas/…); ANT sin monto. El frontend lo pinta por bloques, sin repetir datos del vehículo.
- **Fuentes como enlace** (`consulta_externa`, no devuelven datos útiles/inline): **SRI** (reCAPTCHA Enterprise v3), **FGE** (ahora WAF Imperva + hCaptcha), **ConsultasEcuador** (reCAPTCHA + afiliado), **EcuadorLegalOnline** (ad-gate + paywall + PII), **EPMTSD Condición/“vehiculo_seguro”** (robo/prendas/remarcado/RTV/traspasos; ~50s y datos por placa inconsistentes → link destacado "Condición y antecedentes").
- **Auth + dominio**: JWT, CRUD vehículos/dueños/kilometraje/mantenimientos/favoritos, billetera (lectura+auditoría), enlaces compartidos.
- **Débito real de tokens (Paso 2)**: `tokens/service.py::debitar_tokens` (lanza `SaldoInsuficiente`→**402**). Cableado en **desbloqueo de PII**: `POST /consultar/{placa}/desbloquear` (JWT) revela vin/motor/chasis en claro (el consolidador ofusca por default, `desbloqueado=True` muestra); no cobra si no hay dato sensible.
- **Marketplace (Pilar 4) operativo de punta a punta**:
  - **Publicaciones internas** (`publicaciones_internas`, plan `light` gratis / `premium` cobra tokens→402): `POST/GET mias/PATCH/DELETE /marketplace/publicaciones`. Premium queda destacado + verificación `pendiente`.
  - **Referencias externas aportadas por el usuario** (`publicaciones_referenciadas`, decisión: **NO scraping** — el usuario pega el link de FB Marketplace/OLX/etc. y completa datos; `fuente` derivada del dominio; `url_externa` única): `POST/GET mias/PATCH/DELETE /marketplace/referencias`. Es **gratis**. Entran en **moderación `pendiente`**.
  - **Moderación admin**: `GET /marketplace/referencias/pendientes` + `POST /{id}/moderar` (aprobar/rechazar). Admin por env var **`ADMIN_EMAILS`** (sin rol en BD); `dependencies.admin_actual` (403) y `/auth/me` expone `es_admin`.
  - **Feed público mixto** `GET /marketplace/feed`: premium destacados → light → referenciadas (solo `aprobada`+`activa`). `selectinload` anti N+1. Frontend: `/marketplace`, `/marketplace/publicar`, `/marketplace/referenciar`, `/marketplace/mis-referencias`, `/admin/moderacion`.
- **Solvers/infra listos (gateados, no cableados)**: `extractor_apify.py` (Apify, validado vs example.com), `proxy_apify.py` (proxy residencial provider-agnostic `SCRAPER_PROXY_URL`), `captcha.py` con `resolver_recaptcha`/`resolver_hcaptcha`/Capsolver.

### ⚠️ Decisiones/limitaciones clave
- **AMT/EPMTSD desde la nube** requieren IP residencial → hoy dependen del **worker en la máquina EC** (debe estar encendida y con sesión). Alternativa cloud-independiente: proxy residencial de pago (Apify free NO tiene residencial; solo datacenter, que esas fuentes bloquean).
- **FGE** escaló a **WAF Imperva + hCaptcha** (sitekey `dd6e16a7-…`). Reactivable con 2Captcha (solver hCaptcha ya escrito), pero frágil y necesita `TWOCAPTCHA_API_KEY` fondeada para implementar+validar el handoff de Incapsula. Hoy es enlace.
- **SRI** reCAPTCHA Enterprise v3 (score) → solver poco fiable; queda enlace.
- **ConsultasEcuador/EcuadorLegalOnline**: ni captcha-solver ni proxy los vuelven útiles (sin endpoint de datos / paywall+PII). Enlace.
- **identificacion** (chasis/motor) en el schema pero sin fuente scrapeable → enlace a ConsultasEcuador.
- **Imágenes de referencias**: hoy el usuario pega una URL de imagen (`imagen_url` ampliado a 2048). Las URLs de **fbcdn (Facebook) son firmadas y EXPIRAN** en días → la foto se romperá. TO-BE: subir el archivo a hosting propio en vez de pegar URL ajena.
- **Moderación sin UI de bandeja avanzada**: `/admin/moderacion` lista pendientes y aprueba/rechaza, pero no hay historial de decisiones ni reportes/anti-spam más allá del gate `ADMIN_EMAILS`.
- Pendientes operativos: rotar el token de Apify (se compartió por chat); configurar `ADMIN_EMAILS` en Render (hecho por el usuario).

## 4. Estructura (backend)
```
src/
  registry.py
  core/  database.py · validators.py · ofuscacion.py · proxy_apify.py
  modules/
    auth (router+dependencies: admin_actual/es_admin) · tokens (service.debitar_tokens→402)
    vehiculos · marketplace (models · schemas · routers/{marketplace,publicaciones,referencias,compartidos})
    consulta/
      routers/ consulta.py (perfil + sync/worker) · ocr.py
      models/ consulta.py · cola_scraping.py
      schemas.py  (VehiculoConsolidadoResponse, MultaDetalle/CategoriaMulta, EstadoFuente)
      services/ ant · sri · amt · epmtsd · _axiscloud · fiscalia (dormido+passthrough) ·
                consultasecuador · ecuadorlegalonline · catalogo_fuentes · consolidador ·
                extractor_apify · captcha (recaptcha+hcaptcha) · cache · cola · vision
worker.py (tarea ConsultaPlacasWorker) · run.py · main.py · scripts/worker_*.ps1
alembic/versions/ 0001…0012 (0010 publicaciones, 0011 referencias+moderación, 0012 imagen_url 2048)
```
Frontend: `src/components/PerfilVehiculo.tsx` (tarjeta vehículo + Multas detalle + Antecedentes(link) + Identificación + Valores + Legal) + `Header.tsx` (enlace "Moderar" si `es_admin`); páginas `marketplace/{,publicar,referenciar,mis-referencias}` y `admin/moderacion`; `src/lib/{api,perfil,auth}`, `src/types/api.ts`.

## 5. Skills
6 skills en `.claude/skills/` (agregar-fuente-consulta, scraping-respetuoso, respuesta-api-estandar, validacion-datos-ec, modelo-dominio-vehiculo, desplegar-mvp). `AGENTS.md` fuente de verdad (§4 al día con marca/tema claro).

## 6. Decisiones técnicas
- `estado_fuentes` catálogo-driven; adaptador AxisCloud compartido (AMT/EPMTSD).
- Fuente tras captcha/paywall/afiliado/lentitud-inconsistencia → `consulta_externa` (link), nunca scraper especulativo (§14/§15).
- Modo síncrono = correr el backend en IP residencial EC (datos inmediatos, sin worker).
- Proxy residencial provider-agnostic; ANT siempre directo.
- Privacidad: VIN/motor/chasis ofuscados a terceros; nunca PII de propietario en consulta pública.

## 7. Últimos cambios (git log backend)
```
396aa7c feat: exponer es_admin en /auth/me (habilita pantallas de moderación)
3acab1b fix: ampliar imagen_url a 2048 (URLs de CDN de Facebook superan 500)
39a42bc chore: documentar ADMIN_EMAILS en render.yaml
6cae4cd feat: marketplace de referencias aportadas por el usuario (link externo + moderación)
9246484 feat: desbloqueo de identificadores por tokens + marketplace de publicaciones
bab748f docs: regenerar snapshot (modo síncrono + worker + detalle multas + solvers)
```
Frontend (`consulta-placas-web`):
`30d586a feat: pantalla "mis referencias" (estado de moderación + eliminar)`,
`2ef2017 feat: pantalla de moderación de referencias (admin)`,
`233dec6 fix: mostrar errores de validación 422 legibles (no más "[object Object]")`,
`42d286b feat: apartado para referenciar anuncios externos (link de Facebook/OLX/etc.)`.

## 8. Para continuar en Gemini — instrucciones
> Eres un asistente de arquitectura y planificación de software con el contexto completo arriba.
> El usuario quiere planificar el TO-BE. Ante cada pedido responde con: 1) impacto sobre lo
> existente, 2) archivos a crear/modificar, 3) skills a activar, 4) estructura sugerida,
> 5) riesgos/dependencias.

## 9. Próximos pasos sugeridos
1. **Imágenes de referencias estables**: reemplazar pegar-URL por **subir archivo** a hosting propio (las URLs de fbcdn expiran). Es el pendiente directo del flujo recién terminado.
2. **Persistencia/independencia del worker**: hoy corre en la máquina EC (debe estar encendida). Evaluar proxy residencial de pago + worker en la nube para 100% sin depender del equipo.
3. **FGE con 2Captcha** (si se quiere reactivar): fondear `TWOCAPTCHA_API_KEY` y cablear el solver hCaptcha + handoff Incapsula (frágil; el enlace es el fallback).
4. **Rotar el token de Apify** (expuesto por chat).
5. **Recarga real de tokens** (gateway de pago local) ahora que el débito ya cobra (desbloqueo PII + premium). Roadmap: Fase 5 (OCR por foto), Fase 6 (mobile + pagos).
