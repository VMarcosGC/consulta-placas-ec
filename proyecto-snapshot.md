# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)
**Generado:** 2026-05-29 18:30 (-05:00)
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?
Plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa. Agrega información de fuentes oficiales y no oficiales (matriculación, citaciones, infracciones municipales, valores tributarios, noticias del delito) en un **Perfil Consolidado** orientado a la entidad vehículo. El MVP en producción cubre el Pilar 1 (consulta pública por placa); el producto completo contempla además consulta por foto (OCR), historial privado del vehículo y modo compra-venta con token. Público objetivo: clase media-baja ecuatoriana; la web busca transmitir confianza y enganchar.

## 2. Stack tecnológico
- **Backend** (repo `consulta_placas_ec`): Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic, Pydantic 2, Playwright async (Chromium) para scraping, `httpx`, PostgreSQL (Neon). Auth con passlib[bcrypt<4.0] + python-jose (JWT HS256). Docker (imagen oficial Playwright) en Render.
- **Frontend** (repo `consulta-placas-web`): Next.js 16 (App Router, Turbopack, RSC), React 19, Tailwind CSS 4. Deploy en Vercel.
- **Worker híbrido** (`worker.py`): proceso pull-only que drena la cola `cola_scraping` desde IP residencial EC (las fuentes municipales bloquean IPs de datacenter).

## 3. Estado actual — AS-IS

### ✅ Completado
- **Arquitectura modular (DDD)**: backend por dominio en `src/modules/{auth,tokens,consulta,vehiculos,marketplace}` + `src/core`. Modelos registrados en `src/registry.py`.
- **Perfil Consolidado de Vehículo** (pivote nuevo): `services/catalogo_fuentes.py` (catálogo estático de 7 fuentes con prioridad/origen/categorías), `schemas.py` (`VehiculoConsolidadoResponse`: datos_basicos, identificacion ofuscada, valores_tributarios, multas_pendientes, novedades_legales, estado_fuentes), `services/consolidador.py` (agrega dicts por-fuente; `estado_fuentes` se arma **desde el catálogo**). Endpoint **`GET /consultar/{placa}/perfil`**; el legacy `/consultar/{placa}` (por fuente) se conserva.
- **7 fuentes integradas** (todas `implementada=True`):
  - **ANT** (oficial): Playwright directo + caché. Marca/modelo/año/color/clase + citaciones.
  - **SRI** (oficial): `consulta_externa` (reCAPTCHA Enterprise; passthrough al portal).
  - **AMT** Quito (oficial): plataforma AxisCloud (`ps_empresa=03`), vía worker híbrido.
  - **EPMTSD** Santo Domingo (oficial): **misma plataforma AxisCloud** (`ps_empresa=06`). Se extrajo el adaptador compartido `services/_axiscloud.py`; `amt.py`/`epmtsd.py` son wrappers. Vía worker. Verificado en vivo.
  - **FGE** Fiscalía (oficial): SIAF, vía worker; acepta placa o cédula.
  - **ConsultasEcuador** (no oficial): `consulta_externa` (reCAPTCHA + sitio de afiliado, no scrapeable).
  - **EcuadorLegalOnline** (no oficial): `consulta_externa` (ad-gate/reCAPTCHA + dato de pago/PII).
- **Resiliencia worker**: estado `error_fuente` tras agotar reintentos (backoff), ventana de enfriamiento; caché de doble velocidad (TTL transaccional 12h / estático 90d).
- **Auth + dominio**: registro/login/JWT, CRUD vehículos, dueños históricos, kilometraje, mantenimientos, favoritos, billetera de tokens (lectura + auditoría), marketplace + enlaces compartidos con token.
- **Frontend rebrandeado y rediseñado**: nombre **"Revisa tu Carro EC"** (antes ConsultaPlacas); **tema claro "Confianza clara"** (fondo claro, gradiente azul→cian, estados verde/ámbar/rojo, sombras suaves). `PerfilVehiculo.tsx` muestra el perfil por temática con polling, skeletons, reintento, sección Identificación, marcadores ⓘ no oficial + disclaimers, y chips de fuente clicables (consulta_externa). Todas las pantallas convertidas; `tsc` + `eslint` limpios.

### 🔄 En progreso / pendiente inmediato
- **Imágenes referenciales del vehículo**: pospuesto por el usuario. No hay foto del auto real por placa; enfoque recomendado: híbrido (render por marca/modelo vía CDN tipo imagin.studio, teñido con el color de ANT) + ilustración propia por `clase` como fallback, con sello "imagen referencial".
- **Deploy**: el frontend (Vercel) apunta al backend de prod (Render); falta desplegar el backend con los nuevos endpoints (`/perfil`) y servicios antes de que el front los consuma. Local usa `NEXT_PUBLIC_API_URL=http://localhost:8000`.

### ⚠️ Problemas o deuda técnica
- **IPs datacenter** (AGENTS.md §8): AMT/EPMTSD/FGE bloquean IPs cloud → requieren el worker en IP residencial EC. SRI bloqueado por reCAPTCHA en local y cloud.
- **Fuentes no oficiales no scrapeables**: ConsultasEcuador/EcuadorLegalOnline tras reCAPTCHA/afiliado/paywall → resueltas como `consulta_externa` (no se inventó scraper, §14/§15).
- **AGENTS.md §4 desactualizado**: aún describe el tema oscuro "moderno joven" (violeta-rosa-ámbar); el frontend ya es tema claro azul→cian. Actualizar al formalizar.
- **identificacion** (chasis/motor): en el schema pero sin fuente que la llene (ConsultasEcuador no es scrapeable); hoy se ofrece como enlace externo.
- **bitácora**: `docs/bitacora.md` es la fuente del día a día; el snapshot resume el AS-IS.

## 4. Estructura de archivos actual
```
consulta_placas_ec/
├── AGENTS.md (+ CLAUDE.md shim @AGENTS.md)
├── main.py · run.py · worker.py · Dockerfile · render.yaml · requirements.txt
├── alembic/versions/0001..0009  (migraciones manuales)
├── docs/  arquitectura.md · arquitectura_hibrida.md · bitacora.md · despliegue.md · worker.md
├── scripts/  discover.py (descubrimiento de portales) · worker_*.ps1
├── .claude/skills/  agregar-fuente-consulta · scraping-respetuoso · respuesta-api-estandar ·
│                    validacion-datos-ec · modelo-dominio-vehiculo · desplegar-mvp
└── src/
    ├── registry.py
    ├── core/  database.py · validators.py · ofuscacion.py
    └── modules/
        ├── auth/  (Usuario + TransaccionToken, JWT, dependencies)
        ├── tokens/  (router lectura + service débito)
        ├── consulta/
        │   ├── routers/  consulta.py (incl. /consultar/{placa}/perfil) · ocr.py
        │   ├── models/   consulta.py · cola_scraping.py
        │   ├── schemas.py  (VehiculoConsolidadoResponse + EstadoFuente)
        │   └── services/  ant · sri · amt · epmtsd · _axiscloud (compartido) ·
        │                  fiscalia · consultasecuador · ecuadorlegalonline ·
        │                  catalogo_fuentes · consolidador · cache · cola · captcha · vision
        ├── vehiculos/  (vehiculo, dueno_historico, kilometraje, mantenimiento, favorito)
        └── marketplace/  (listado público + enlaces compartidos)
```
Frontend (repo `consulta-placas-web`): `src/app/{page,layout,consultar,login,registro,precios,mi-garage}` · `src/components/{PerfilVehiculo,ConsultaForm,Header,Footer,CampoTexto}` · `src/lib/{api,auth,consolidar}` · `src/types/api.ts` · `src/app/globals.css`.

## 5. Skills y herramientas configuradas
6 skills de dominio en `.claude/skills/`: agregar-fuente-consulta, scraping-respetuoso, respuesta-api-estandar, validacion-datos-ec, modelo-dominio-vehiculo, desplegar-mvp. `AGENTS.md` es la fuente de verdad (con shim `CLAUDE.md`).

## 6. Decisiones técnicas tomadas
- **`estado_fuentes` catálogo-driven**: agregar una fuente = catálogo + scraper + ruteo, sin tocar el consolidador.
- **Adaptador AxisCloud compartido** (`_axiscloud.py`): AMT y EPMTSD son la misma plataforma (solo cambia `ps_empresa`); se evitó duplicar ~180 líneas y se re-verificó AMT sin regresión.
- **Fuentes tras captcha/paywall/afiliado → `consulta_externa`** (enlace + disclaimer), nunca un scraper especulativo (precedente SRI; reglas §14/§15).
- **Separación CRUD ↔ scraping**: el CRUD del MVP nunca invoca Playwright.
- **Rebranding** a "Revisa tu Carro EC" (descartado "Carro Seguro EC" por ambigüedad con póliza).
- **Tema "Confianza clara"** (claro + azul→cian) elegido con el usuario; prioridad atracción + legibilidad para clase media-baja.
- **Privacidad**: VIN/motor/chasis solo al dueño; ofuscados para terceros; nunca PII de propietario en consulta pública.

## 7. Últimos cambios (git log)
```
55d07c0 feat: integrar EPMTSD + ConsultasEcuador + EcuadorLegalOnline (perfil consolidado catálogo-driven)
f43b12f perf: acortar timeouts de scraping y backoff del worker
7e9b901 docs: regenerar snapshot (resiliencia worker + caché doble velocidad + frontend Instrucción 3)
ad9ff42 fix: reintentar FGE acepta placa o cédula según el flujo de origen
d162370 chore: declarar CACHE_TTL_TRANSACCIONAL/ESTATICO_MINUTOS en render.yaml
2b0f40f feat: resiliencia worker (error_fuente) + caché de doble velocidad
```
Frontend (repo separado): `cd77d47 feat: rebranding a 'Revisa tu Carro EC' + rediseño a tema claro + perfil consolidado`.

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
1. **Imágenes referenciales del vehículo** (decisión pendiente): implementar el enfoque elegido (híbrido render-por-modelo + ilustración por clase) con sello "referencial"; si se usa CDN externo, revisar licencia para producción.
2. **Desplegar backend** en Render con los nuevos endpoints/servicios y apuntar Vercel; verificar que las fuentes worker (AMT/EPMTSD/FGE) corran en el worker con IP residencial EC.
3. **Actualizar AGENTS.md §4** (tono visual) y el diagrama `docs/arquitectura.md` con las 7 fuentes y el flujo consolidado.
4. **Reducir `consolidar.ts`** del frontend ahora que el backend entrega el contrato consolidado (quedan solo helpers de lectura).
5. **Cablear identificación real** si se consigue una fuente de chasis/motor scrapeable (o API oficial), respetando ofuscación.
6. Avanzar el roadmap: Fase 5 (OCR por foto) y débito real de tokens.
