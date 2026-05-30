# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)
**Generado:** 2026-05-30 (-05:00) · rev. modo síncrono + detalle de multas + solvers
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
- **Auth + dominio**: JWT, CRUD vehículos/dueños/kilometraje/mantenimientos/favoritos, billetera (lectura+auditoría), marketplace + enlaces compartidos.
- **Solvers/infra listos (gateados, no cableados)**: `extractor_apify.py` (Apify, validado vs example.com), `proxy_apify.py` (proxy residencial provider-agnostic `SCRAPER_PROXY_URL`), `captcha.py` con `resolver_recaptcha`/`resolver_hcaptcha`/Capsolver.

### ⚠️ Decisiones/limitaciones clave
- **AMT/EPMTSD desde la nube** requieren IP residencial → hoy dependen del **worker en la máquina EC** (debe estar encendida y con sesión). Alternativa cloud-independiente: proxy residencial de pago (Apify free NO tiene residencial; solo datacenter, que esas fuentes bloquean).
- **FGE** escaló a **WAF Imperva + hCaptcha** (sitekey `dd6e16a7-…`). Reactivable con 2Captcha (solver hCaptcha ya escrito), pero frágil y necesita `TWOCAPTCHA_API_KEY` fondeada para implementar+validar el handoff de Incapsula. Hoy es enlace.
- **SRI** reCAPTCHA Enterprise v3 (score) → solver poco fiable; queda enlace.
- **ConsultasEcuador/EcuadorLegalOnline**: ni captcha-solver ni proxy los vuelven útiles (sin endpoint de datos / paywall+PII). Enlace.
- **identificacion** (chasis/motor) en el schema pero sin fuente scrapeable → enlace a ConsultasEcuador.
- Pendientes operativos: rotar el token de Apify (se compartió por chat); imágenes referenciales del vehículo (pospuesto).

## 4. Estructura (backend)
```
src/
  registry.py
  core/  database.py · validators.py · ofuscacion.py · proxy_apify.py
  modules/
    auth · tokens · vehiculos · marketplace
    consulta/
      routers/ consulta.py (perfil + sync/worker) · ocr.py
      models/ consulta.py · cola_scraping.py
      schemas.py  (VehiculoConsolidadoResponse, MultaDetalle/CategoriaMulta, EstadoFuente)
      services/ ant · sri · amt · epmtsd · _axiscloud · fiscalia (dormido+passthrough) ·
                consultasecuador · ecuadorlegalonline · catalogo_fuentes · consolidador ·
                extractor_apify · captcha (recaptcha+hcaptcha) · cache · cola · vision
worker.py (tarea ConsultaPlacasWorker) · run.py · main.py · scripts/worker_*.ps1
```
Frontend: `src/components/PerfilVehiculo.tsx` (tarjeta vehículo + Multas detalle + Antecedentes(link) + Identificación + Valores + Legal), `src/lib/{api,perfil}`, `src/types/api.ts`.

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
d05e13a feat: solver de hCaptcha (2Captcha) reusable para el muro de FGE
c47ad54 feat: detalle de multas/citaciones por fuente (ANT/AMT/EPMTSD) + fechas de matrícula
71902e2 feat: modo síncrono (sin worker) + FGE a consulta_externa (hCaptcha en SIAF)
f18d43e feat: soporte de proxy residencial (gateado) para AMT/EPMTSD/FGE
9ff5e06 fix: ApifyExtractor compatible con apify-client v3
d19686c feat: cliente de extracción Apify + docs al día
```
Frontend: `8fd87e3 feat: sección 'Condición y antecedentes' (link EPMTSD) + reordena multas`,
`b34fcb7 feat: vista de detalle de multas por fuente + matrícula/vence`.

## 8. Para continuar en Gemini — instrucciones
> Eres un asistente de arquitectura y planificación de software con el contexto completo arriba.
> El usuario quiere planificar el TO-BE. Ante cada pedido responde con: 1) impacto sobre lo
> existente, 2) archivos a crear/modificar, 3) skills a activar, 4) estructura sugerida,
> 5) riesgos/dependencias.

## 9. Próximos pasos sugeridos
1. **Persistencia/independencia del worker**: hoy corre en la máquina EC (debe estar encendida). Evaluar proxy residencial de pago + worker en la nube para 100% sin depender del equipo.
2. **FGE con 2Captcha** (si se quiere reactivar): fondear `TWOCAPTCHA_API_KEY` y cablear el solver hCaptcha + handoff Incapsula, validando en vivo (es frágil; el enlace es el fallback).
3. **Rotar el token de Apify** (expuesto por chat).
4. **Imágenes referenciales** del vehículo (híbrido render-por-modelo + ilustración por clase).
5. Roadmap: Fase 5 (OCR por foto) y débito real de tokens.
