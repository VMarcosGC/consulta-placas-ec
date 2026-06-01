# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)
**Generado:** 2026-05-31
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?
Plataforma (web + futura móvil) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa. Agrega información de fuentes oficiales (ANT, SRI, AMT, EPMTSD, Fiscalía) en un **perfil consolidado por temática** (datos, multas, matrícula, valores, legal). Además ofrece **garage privado** (historial del auto del usuario), **marketplace de compra-venta** (publicaciones propias + referencias a anuncios externos) y una **billetera de tokens** para funciones de pago. El MVP en producción cubre el Pilar 1 (consulta pública) y buena parte de los Pilares 3 y 4 (garage y compra-venta).

## 2. Stack tecnológico
**Backend** (repo `consulta_placas_ec`):
- Python 3.11+, **FastAPI** (monolito modular por dominio, DDD).
- **Playwright** async (Chromium) para scraping; `httpx` donde aplica.
- **PostgreSQL 16 (Neon)** + **SQLAlchemy 2** + **Alembic** (migraciones manuales 0001–0016).
- **Pydantic 2**; auth `passlib[bcrypt<4.0]` + `python-jose` (JWT HS256).
- Solvers de captcha: 2Captcha (hCaptcha), extractor vía **Apify** + proxy residencial gateado.
- Deploy: **Docker** (imagen oficial Playwright) en **Render**.

**Frontend** (repo `consulta-placas-web`):
- **Next.js 16** (App Router, Turbopack, RSC) + React 19 + **Tailwind CSS 4**.
- Tema claro "Confianza clara" (azul→cian). JWT en `localStorage`.
- Deploy: **Vercel**. Idioma del copy: **español de Ecuador (tuteo)**.

## 3. Estado actual — AS-IS

### ✅ Completado
- **Consulta pública por placa** → `GET /consultar/{placa}/perfil` (perfil consolidado) y `GET /consultar/{placa}` (vista por fuente).
- **Fuentes integradas**: ANT (matrícula + citaciones, funciona), AMT-Quito (infracciones, vía worker/síncrono), EPMTSD-Santo Domingo (AxisCloud), SRI (reCAPTCHA → `consulta_externa`, enlace al portal), FGE (hCaptcha → `consulta_externa`), ConsultasEcuador / EcuadorLegalOnline (no oficiales, enlaces).
- **Consolidador** server-side (`services/consolidador.py`): arma `VehiculoConsolidadoResponse` por temática + `estado_fuentes`.
- **Caché en BD** con TTL doble velocidad (transaccional 12h / estático 90d).
- **Arquitectura híbrida**: modo síncrono (IP residencial EC) o worker (encola AMT/EPMTSD) para sortear el bloqueo de IPs datacenter.
- **Auth**: registro, login, `/auth/me` (incluye `es_admin` según `ADMIN_EMAILS`).
- **Billetera de tokens**: saldo inicial 5, débito real (`debitar_tokens`), auditoría inmutable.
- **Microdesbloqueos por tokens (v2)**: catálogo en BD (`productos_consulta`) + registro `desbloqueos_consulta` (no doble cobro) + `costos_proveedor_consulta`. Router `routers/desbloqueos.py`: `GET /consultar/{placa}/productos`, `POST .../desbloquear/{producto_codigo}` (402/422/409, idempotente), `GET .../desbloqueos`. **Reajuste Fase 2.5 (migración 0016)**: ficha pública gratis (`consulta_publica_base`), solo se cobra por costo/dificultad/valor real. 1 token ≈ USD 0.04.
- **Garage privado**: vehículos (con `ciudad_registro`), dueños históricos, kilometraje (monotónico), mantenimientos, favoritos.
- **Marketplace**:
  - *Publicaciones internas* (`publicaciones_internas`): plan light (gratis) / premium (cobra tokens, destacado, verificable). `GET /marketplace/feed` (feed mixto en 3 niveles).
  - *Referencias aportadas* (`publicaciones_referenciadas`): el usuario pega un link de Facebook/OLX/etc.; entra en **moderación** (pendiente → admin aprueba) y se muestra como **enlace vivo** al anuncio original (sin scraping). Pantallas `/marketplace/referenciar`, `/marketplace/mis-referencias`, `/admin/moderacion`.
  - *Token de compra-venta* (`enlaces_compartidos`): enlace temporal de solo lectura con scope.
- **Frontend**: landing (tarjetas navegables), consultar (perfil en grid sobrio: Datos → Multas+Matrícula → Consulta oficial), mi-garage, login/registro (sesión persistente + nombre en header), precios, marketplace + publicar + referenciar + mis-referencias, admin/moderación.

### 🔄 En progreso / parcial
- **Verificación "Verificado por la plataforma"**: premium queda en `pendiente`; el flip a `verificado` es un paso admin **aún no construido**.
- **Desbloqueo de PII**: el gateo/cobro está cableado, pero **ninguna fuente del flujo público entrega VIN/motor/chasis/dueño/traspasos en claro** todavía (ver deuda técnica) → hoy no hay nada que revelar y no cobra.
- **OCR / foto (Pilar 5)**: `routers/ocr.py` + `services/vision.py` esbozados; sin flujo completo.

### ⚠️ Problemas o deuda técnica identificada
- **SRI tras reCAPTCHA Enterprise**: no se puede leer el "valor a pagar" (matrícula/impuestos) automáticamente → solo se ofrece el enlace al portal. Es **la causa principal de que en muchos autos "no salga el valor a pagar"**. Vía definitiva pendiente: API oficial del SRI (trámite administrativo).
- **ANT no informa montos** de las citaciones (solo conteo por estado) → pendientes de ANT se muestran sin valor.
- **IPs de datacenter bloqueadas** (AMT/EPMTSD/FGE) desde Render → requieren worker residencial / proxy / modo síncrono. ANT y SRI no dependen de esto.
- **FGE y EPMTSD-municipal desactivados en la UI** (constante `FUENTES_INACTIVAS` en el frontend) hasta tener forma de traer datos accionables.
- **Cold start** del free tier (~30s) tras inactividad.
- **`consulta` depende de `auth`+`tokens`** (excepción documentada en AGENTS.md §1.1 por el desbloqueo).
- **Excepción de contrato**: flujos de pago con tokens devuelven **402** (no 422), documentado en AGENTS.md §10.2.

## 4. Estructura de archivos actual (backend)
```
main.py · run.py · worker.py · registry.py
alembic/versions/0001..0016   (migraciones manuales)
src/core/        database, validators, ofuscacion, proxy_apify
src/modules/
  auth/          models (Usuario, TransaccionToken), router, security, dependencies, schemas
  tokens/        service (debitar_tokens), router
  consulta/      routers/{consulta,ocr}  schemas
                 services/{ant,sri,amt,epmtsd,fiscalia,consultasecuador,ecuadorlegalonline,
                           consolidador,catalogo_fuentes,cache,cola,captcha,vision,
                           extractor_apify,_axiscloud}
                 models/{consulta,cola_scraping}
  vehiculos/     models+routers+schemas (vehiculo, dueno_historico, kilometraje, mantenimiento, favorito)
  marketplace/   models, schemas, routers/{marketplace,publicaciones,referencias,compartidos}
docs/            arquitectura(.md/_hibrida), bitacora, despliegue, worker
.claude/skills/  agregar-fuente-consulta, scraping-respetuoso, respuesta-api-estandar,
                 validacion-datos-ec, modelo-dominio-vehiculo, desplegar-mvp
```
Frontend (`../consulta-placas-web/src`): `app/{page,consultar,consultar/[placa],login,registro,mi-garage,precios,marketplace,marketplace/{publicar,referenciar,mis-referencias},admin/moderacion}` · `components/{Header,Footer,ConsultaForm,CampoTexto,PerfilVehiculo,BentoCard,ListingCard}` · `lib/{api,auth,perfil}` · `types/api.ts`.

## 5. Skills y herramientas configuradas
- `AGENTS.md` (fuente de verdad; `CLAUDE.md` es shim `@AGENTS.md`).
- Skills del proyecto: agregar-fuente-consulta, scraping-respetuoso, respuesta-api-estandar, validacion-datos-ec, modelo-dominio-vehiculo, desplegar-mvp, project-snapshot.
- Bitácora en `docs/bitacora.md`; diagramas Mermaid en `docs/arquitectura.md`.

## 6. Decisiones técnicas tomadas
- **Monolito modular por dominio** (no por tipo de archivo); comunicación por interfaz pública.
- **Identificadores del código en español**; **copy del frontend en español de Ecuador (tuteo)**.
- **Migraciones Alembic manuales** (sin autogenerate a ciegas).
- **IDs BigInteger** (no UUID); enums guardados como String (sin enum nativo PG).
- **Marketplace**: tablas nuevas separadas (`publicaciones_internas`, `publicaciones_referenciadas`) en vez de reusar `vehiculos.en_venta`.
- **Referencias externas**: NO se scrapean (FB exige login/bloquea bots); el usuario pega el link y completa datos → moderación admin → enlace vivo.
- **Tolerancia a fallos**: una fuente caída nunca rompe la respuesta (siempre 200, fuente marcada con su estado).
- **Pagos con tokens → HTTP 402**; validación de negocio → 422; "no es tuyo" → 404.

## 7. Últimos cambios (sesión 2026-05-30/31)
- **Reajuste comercial del catálogo — Fase 2.5** (migración **0016**): no se cobran datos
  públicos simples (clase, servicio, marca, modelo, año, color, estado de matrícula) → **gratis**
  en `consulta_publica_base` (0 tokens). Solo se cobra por **costo de proveedor / dificultad /
  valor comercial**. Renombres: `vehiculo_identificadores`→`identificadores_tecnicos` (3t),
  `vehiculo_titular_validado`→`titular_validado` (5t), `vehiculo_multas`→`multas_con_montos` (10t);
  desactivados `vehiculo_basico`/`vehiculo_tecnico`; nuevos `valores_matricula_sri` (12t),
  `alertas_legales` (8t); reprecio `reporte_compra_segura` 40t y `verificacion_marketplace` 100t.
  Valor del token USD 0.05 → **USD 0.04**. `titular_validado`/`valores_matricula_sri`/
  `alertas_legales` `disponible=false` (enlace oficial / sin proveedor confiable). Paquetes de
  recarga referenciales ($1→25t … $10→280t). Sin proveedores reales ni evasión de captcha.
  **Frontend alineado** (commit `ac418ed`): precios reescritos al modelo por tokens; ficha
  pública sin candado (gratis); `PerfilVehiculo` con códigos nuevos; copy corregido ("Conoce";
  no se promete SRI/Fiscalía automáticos). Listo para iniciar **Fase 3** sin inconsistencias.
- **Microdesbloqueos por tokens v2** (migración **0015**): catálogo **en BD**
  (`productos_consulta`, fuente de verdad de precios; seed canónico en
  `services/catalogo_productos.py`) + `desbloqueos_consulta` (auditoría comercial:
  tokens_cobrados, precio_referencial_usd, proveedor_usado, costo_estimado_usd,
  resultado_cache_id; UK usuario+placa+producto → no doble cobro) + `costos_proveedor_consulta`.
  Router dedicado `routers/desbloqueos.py`: `GET /consultar/{placa}/productos`,
  `POST /consultar/{placa}/desbloquear/{producto_codigo}` (400/422-inactivo/409/402, idempotente),
  alias `.../desbloquear`, `GET /consultar/{placa}/desbloqueos`. Teaser gratis (marca/modelo/
  año/color + matrícula vigente + veredicto); gateo en el consolidador.
  Validación: `scripts/validar_desbloqueos.py`. (Reajustado por la Fase 2.5, ver arriba.)
- **Verificación premium del marketplace** (sello "Verificado por la plataforma"): flujo admin
  (`/admin/verificaciones`) + `verificado_en` (migración 0013). Reconciliado: destacar premium
  = 3 tokens; **solicitar verificación = 100 tokens** (`/solicitar-verificacion`, pantalla
  `/marketplace/mis-publicaciones`).
- Saldo de tokens visible en el header. Perfil sobrio; sesión persistente; ciudad en el garage;
  referencias como enlace vivo a Facebook; español de Ecuador; landing navegable.

**Git** — backend HEAD: `19fafd0` (+ docs) · frontend HEAD: `ac418ed`. Ambos repos limpios. **Prod**:
Render + Vercel · BD Neon en `alembic head` **0016** (aplicar `alembic upgrade head`).

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
1. **Resolver el "valor a pagar" del SRI**: definir si se gestiona la **API oficial del SRI** (trámite) o se deja claramente como enlace al portal. Es el dato más buscado y hoy no se muestra.
2. **Cerrar el flujo premium del marketplace**: construir el paso admin de **verificación** ("Verificado por la plataforma") que hoy queda en `pendiente`.
3. **Reactivar FGE/EPMTSD** cuando exista solución de captcha/datos, removiéndolas de `FUENTES_INACTIVAS`.
4. **OCR / consulta por foto (Pilar 5)**: completar `ocr.py` + `vision.py` (extraer placa de imagen → flujo de consulta).
5. **Mantenimientos en el garage (UI)**: exponer alta/listado de mantenimientos y consumos (hoy modelados, parcialmente en UI) para alimentar los argumentos premium del marketplace.
6. **Mobile + pagos**: app móvil e integración con gateway local (PlaceToPay/MercadoPago) para activar la billetera de tokens de verdad.
