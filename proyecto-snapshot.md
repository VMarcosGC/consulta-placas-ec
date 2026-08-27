# Proyecto Snapshot — Revisa tu Carro EC (consulta_placas_ec)

**Regenerado:** 2026-08-27 · **Estado del ciclo:** cierre, ola 1 en curso.

Foto AS-IS **autocontenida**: si para entender algo hay que abrir la bitácora o el código,
no está bien escrito acá. Complementa a [AGENTS.md](AGENTS.md) (reglas, fuente de verdad)
y [docs/bitacora.md](docs/bitacora.md) (cronología). Reemplaza al snapshot de 2026-06-01,
que hablaba de 16 migraciones y de "subir a Gemini".

---

## 1. Qué es

**Marketplace de autos usados para Ecuador** cuya propuesta es la transparencia: el
comprador ve la ficha que declara el vendedor junto a datos oficiales de fuentes públicas.
Público: compradores y vendedores particulares de clase media-baja, en celulares de gama
baja. **El marketplace es el producto**; la consulta por placa es un complemento
enriquecedor y hoy está en segundo plano (§4).

Etapa vigente: **particulares** (persona natural vende su auto). Patios = etapa 2, fuera
de alcance.

## 2. Stack y despliegue

**Backend** (`consulta_placas_ec`): Python 3.11+ · FastAPI · Pydantic 2 · SQLAlchemy 2 ·
Alembic (migraciones manuales) · Playwright async (scraping) · JWT HS256 + bcrypt.
Monolito modular DDD en `src/modules/` (`auth`, `tokens`, `consulta`, `vehiculos`,
`marketplace`) + `src/core`. Entrypoints: `main.py` (solo orquesta routers), `run.py`,
`worker.py`. Deploy: Docker en **Render** free.

**Frontend** (`consulta-placas-web`, repo aparte): Next.js 16 (App Router, Turbopack) ·
React 19 · Tailwind 4 (tokens en `src/app/globals.css`, sin `tailwind.config`) · TS
estricto. Tema claro "confianza clara". JWT en `localStorage`. Deploy: **Vercel** free.

**BD**: PostgreSQL 16 en **Neon** (externa). El Postgres de Render ya no se usa.

**Worker**: proceso `worker.py` en una máquina con IP residencial ecuatoriana (Task
Scheduler `ConsultaPlacasWorker`). Drena `cola_scraping` para AMT/EPMTSD, que bloquean IPs
de datacenter. La API en Render solo lee la caché que el worker llena.

URLs: backend `consulta-placas-ec.onrender.com` · frontend
`consulta-placas-web.vercel.app` · repos en `github.com/VMarcosGC/{consulta-placas-ec,
consulta-placas-web}`.

## 3. Qué hay (verificado 2026-08-27)

**Migración aplicada:** `alembic heads` = **0025** (local y Neon; `0025` = login con
Google, verificada sobre `information_schema` el 2026-08-25). Cadena `0001`→`0025`, cabeza
única.

**Backend:** `import main` → **69 rutas**. `python -m unittest discover tests` → **142
tests OK** (concentrados en login-Google y unos pocos campos de market; sin CI).

- **Auth**: registro, login por contraseña, `POST /auth/google` + `/auth/google/vincular`
  (canjea ID token de Google por el JWT propio; sin anti-replay — riesgo residual
  declarado), `GET /auth/me` (incluye `es_admin` por `ADMIN_EMAILS`).
- **Billetera de tokens**: saldo inicial 5, `debitar_tokens` (no-op si el monto es 0),
  auditoría inmutable en `transacciones_tokens`. **Nada cobra hoy** (§4).
- **Consulta por placa**: `GET /consultar/{placa}` y `/consultar/{placa}/perfil`
  (consolidado por temática). Fuentes: ANT (matriculación + citaciones) y AMT/EPMTSD
  (infracciones municipales, vía worker) activas; **SRI y FGE dormidas** por captcha
  (quedan como enlace oficial, ocultas en la web por `NEXT_PUBLIC_FUENTES_INACTIVAS`).
  Caché en `consultas` con TTL doble (transaccional 12h / estático 90d). `solo_cache=true`
  en el consumo del detalle público (no dispara scraping).
- **Garage privado**: vehículos (VIN/motor/chasis con 3 niveles de ofuscación), dueños
  históricos, kilometraje monotónico, mantenimientos, favoritos (placa como String, no FK).
- **Marketplace** (el producto):
  - `PublicacionInterna` (la publica un usuario sobre su placa) con ciclo
    `borrador → activa → pausada/vendida`. Activar exige ficha ≥ `UMBRAL_FICHA_PUBLICACION`
    (30%, env). Plan `light`/`premium`: premium = `destacado` + elegible para el sello;
    **hoy gratis**.
  - `FichaPublicacion` 1:1: 3 bloques (`motor_suspension`, `carroceria`, `interiores`) +
    `extras`, JSONB validado por Pydantic (`extra="forbid"`), con `completitud` derivada.
    Registrar/editar es gratis.
  - `FotoPublicacion`: sube el navegador a Cloudinary con firma del backend; la BD guarda
    la URL. Máx. 12 por publicación.
  - `PublicacionReferenciada`: el usuario pega un link externo (FB/OLX); NO se raspa; entra
    `pendiente` y un admin la aprueba. Admite contenido rico (descripción, ciudad, km, ≤5
    fotos). Detalle local `/marketplace/referencias/{id}` con botón al anuncio original.
  - `GET /marketplace/feed` (portada curada: premium / estándar / referenciadas) y
    `GET /marketplace/buscar` (lista plana filtrable, paginada por cursor keyset).
  - **Contacto** (`POST /marketplace/publicaciones/{id}/contacto`): público y gratis;
    devuelve teléfono + `whatsapp_url`. Registra `ContactoRevelado` anónimo (métrica de
    demanda; sin IP/user-agent/usuario). El teléfono no viaja en feed ni detalle.
  - Capa `Vendedor` (identidad comercial, 1:1 con la cuenta en etapa 1; `TipoVendedor.PATIO`
    declarado para etapa 2). `nombre_publico` y `telefono` son opt-in explícito.
  - Verificación "Verificado por la plataforma": el dueño la solicita (gratis) → `pendiente`
    → un admin marca `verificado`/`rechazado` (`/marketplace/publicaciones/{id}/verificar`,
    `ADMIN_EMAILS`). Solo premium.
  - Token de compra-venta (`enlaces_compartidos`): enlace temporal (TTL ≤ 7 días) con
    `scope` opt-in para mostrarle el historial a un comprador sin cuenta.

**Frontend:** ~20 páginas, ~26 componentes. `tsc --noEmit` limpio · `npm run lint` **0
errores** · `npm run build` OK (17 rutas). Portada market-first, feed curado (MC1) +
búsqueda server-side (MC2), wizard de publicar de 3 pasos, ficha por bloques con
completitud, favoritos con badge de baja de precio, contacto por WhatsApp, `mi-garage`,
`mi-cuenta`, login/registro con Google, panel admin (moderación de referencias +
verificaciones). Sistema de diseño "confianza clara" documentado en `docs/DISENO.md`
(migración de tokens TASK-017 fases 1–3 aplicadas).

## 4. Qué se decidió (decisiones vivas y su porqué)

- **El market es el producto; la consulta por placa es complemento y hoy va en segundo
  plano** (§1.0.1–1.0.2 de AGENTS). Motivo: SRI/FGE tras captcha y AMT/EPMTSD dependen de
  un worker residencial frágil. "Más adelante vemos placas y costos."
- **Monetización suspendida en toda la superficie del producto** (Marcos, 2026-08-27).
  Motivo: la doc decía "precios en 0" mientras el código de market cobraba 3–100 tokens y
  `/precios` vendía paquetes — contradicción. Estado aplicado:
  `TOKENS_PUBLICACION_PREMIUM`, `TOKENS_VERIFICACION_MARKETPLACE`, `COSTO_COMPARTIR_TOKENS`
  → 0 (env-overridables, débito y ramas 402 cableados para reactivar). Frontend: `/precios`,
  `TokenBadge`, microdesbloqueos de la consulta y todo copy de "N tokens" **retirados**.
  El módulo `tokens` y `transacciones_tokens` quedan como plomería dormida (auditoría del
  ledger sigue siendo obligatoria). Dónde y cuánto se cobra se decide con usuarios reales.
- **Un solo modelo de marketplace.** El endpoint legacy `GET /marketplace` (sobre
  `Vehiculo.en_venta`) se retiró: estaba huérfano. El market vive en `PublicacionInterna` /
  `PublicacionReferenciada`. Las columnas `en_venta`/`precio_venta_usd`/`url_externa` de
  `Vehiculo` quedan en el modelo sin uso (borrarlas = migración, no urgente).
- **El proveedor `mock` no se usa en producción.** Un proveedor que fabrica datos no puede
  alimentar un producto cuya propuesta es la transparencia. El default correcto de
  `PROVEEDOR_VEHICULAR_ACTIVO` en prod es `consultas_ec` (sin API key → capacidades vacías,
  no ofrece ni cobra). Que el default de código siga siendo `mock` es deuda (TASK-004).
- **Contrato de errores**: 400 formato · 402 pago con tokens · 404 "no es tuyo"
  (indistinto) · 409 conflicto / dato no disponible · 422 validación de negocio. Nunca 500.
- **Privacidad**: VIN/motor/chasis ofuscados salvo dueño autenticado; titular nunca en
  crudo. `Depends(usuario_actual)` / `vehiculo_propio` en todo lo privado. El CRUD del
  market **nunca** invoca scraping (§10.2).
- **Login con Google**: auto-enlace de una cuenta existente solo con identidad autoritativa
  (`gmail.com` o `hd` de Workspace); el resto recibe 409 y debe vincular autenticándose.
  `proveedor_autenticacion` es el origen, no una exclusividad (una cuenta puede tener
  contraseña y Google).
- **Migraciones manuales**, revisadas a mano, con `downgrade`. Sin `--autogenerate` a
  ciegas. `selectinload` en todo listado del market (sin N+1).

## 5. Qué está bloqueado o pospuesto

Distinguir bloqueado por límite externo de pospuesto por decisión.

| Tema | Tipo | Causa | Condición de desbloqueo |
|---|---|---|---|
| SRI y FGE (valores de matrícula, alertas legales) | bloqueado | reCAPTCHA Enterprise / hCaptcha; Playwright es detectable | API oficial o convenio; hoy quedan como enlace oficial y ocultas en la web |
| AMT/EPMTSD y FGE desde la nube | bloqueado | los portales sirven challenge a IPs de datacenter | worker residencial (existe) o proxy residencial pago |
| **Datos oficiales dentro de la tarjeta del feed** | bloqueado | el feed no lleva procedencia por campo y la caché del worker está fría (no drena desde ~20-jul; job colgado `en_proceso` desde 29-jul, sin recuperación de locks efectiva) | arreglar el worker (TASK-008) → llevar el estado oficial al schema del feed → pintar el "registro oficial" (`DISENO.md §5`, Fase 2) |
| Cobro y pasarela de pago | pospuesto | decisión: nada de costos hasta operar con usuarios reales | tener una versión estable con uso real |
| Cuentas de patio e ingesta masiva | pospuesto | etapa 2 | que el flujo de particulares funcione con usuarios reales |
| Catálogo `productos_consulta` con tokens > 0 en BD | pospuesto | dormido y sin UI que lo alcance | se pone en 0 (migración) al retomar la consulta por placa |
| App móvil / feed tipo reels | pospuesto | fuera de alcance del ciclo | web validada + fotos de calidad en volumen |
| Anti-replay del login con Google | deuda declarada | necesita Redis (guard por `jti`) | mitigación provisional: bajar `JWT_EXPIRA_MINUTOS` a 4–8h |

Sin CI en ninguno de los dos repos. Sin `tests/fixtures/` para los parsers de scraping
(TASK-009). `scripts/estado.py` (TASK-007) todavía no existe: el estado se verifica a mano.

## 6. Qué sigue (inmediato)

1. **Merge** de la rama `chore/cierre-market-sin-precios` en ambos repos (aprueba Marcos).
   No requiere migración.
2. Cerrar la ola 1 en la bitácora con el estado de merge.
3. Ola 2 (a priorizar con Marcos): pulir y cerrar de punta a punta los ciclos del vendedor
   (publicar → borrador → activar → editar) y del comprador (portada → buscar → detalle →
   favorito → contacto); correr el guión de prueba integrador; unificar planificadores
   (`plan_market_autos.md` = historia, `ORDEN-DE-TRABAJO.md` = plan); `scripts/estado.py`.
4. El worker (TASK-008) y todo lo de consulta por placa quedan pospuestos por decisión
   hasta que el market opere con usuarios reales.
