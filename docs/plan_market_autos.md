# Plan del Market de Autos — etapas, agentes y control de calidad

**Fecha:** 2026-07-18 · **Estado:** vigente
**Contexto:** el pilar de consulta llegó a su techo razonable (SRI/FGE passthrough, AMT
vía worker, proveedor real pendiente de API key). El foco pasa al **market de autos**
para uso particular y patios. La etapa M0 (ficha técnica: 3 bloques + extras) ya está
implementada en backend (migración `0017`).

**Modelo de trabajo:**
- **Controller (Claude en Cowork):** planifica, define compuertas de salida por etapa,
  revisa el código al cierre de cada etapa y mantiene este plan y la bitácora.
- **Agentes de desarrollo (Claude Code en VS Code):** ejecutan el trabajo de cada etapa.
  Definidos en `.claude/agents/` (ver §4). Claude Code los detecta automáticamente.
- **Marcos:** decide alcance y prioridades, corre las migraciones contra Neon, aprueba
  los merges.

---

## 1. Lanzar el entorno de desarrollo desde VS Code

### Backend (este repo)

```powershell
cd C:\Users\vmarc\OneDrive\Documentos\porpuestas_code\consulta_placas_ec
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt      # solo si cambió requirements
alembic upgrade head                 # ⬅ aplica 0017 (fichas_publicacion) contra Neon
python run.py                        # NUNCA `uvicorn --reload` (rompe Playwright en Windows)
```

Smoke test rápido:
```powershell
curl http://localhost:8000/health                      # {"status":"ok"}
start http://localhost:8000/docs                       # Swagger: probar PATCH .../ficha y GET detalle
```

### Frontend (repo hermano)

```powershell
cd ..\consulta-placas-web
npm install
npm run dev                          # http://localhost:3000 (apunta al backend local por .env.local)
```

### Worker residencial (solo si se prueba AMT/FGE)
Ya autoarranca con Task Scheduler (`ConsultaPlacasWorker`). Manual: `scripts\worker_run.ps1`.

### Claude Code (agentes)
Abrir la carpeta del repo en VS Code y lanzar `claude` en la terminal integrada. Los
agentes de `.claude/agents/` quedan disponibles; se invocan pidiéndolo explícito
("usa el agente dev-backend para…") o Claude delega solo según la descripción del agente.

---

## 2. Etapas del market (M0 → M5)

Regla heredada del proyecto: **no saltar etapas sin acordarlo**. Cada etapa tiene una
**compuerta de salida** que el controller verifica antes de dar paso a la siguiente.

### M0 — Ficha técnica (backend) ✅ hecha (2026-07-18)
3 bloques (`motor_suspension`, `carroceria`, `interiores`) + `extras`, JSONB validado por
Pydantic (`extra="forbid"`), completitud derivada, `PATCH .../ficha` (dueño, gratis) y
`GET /marketplace/publicaciones/{id}` (público). Migración `0017`.
**Compuerta:** ✅ cerrada — `0017` aplicada en Neon (`alembic current` = `0017`), revisión
`revisor-calidad` APTA, commit `45c7da9`.

### M1 — Ficha técnica (frontend) ✅ hecha (2026-07-18)
**Repo:** `consulta-placas-web` · **Agente:** dev-frontend · commit `1c0bd95`
- Página de detalle `consultar` → `/marketplace/[id]`: anuncio + ficha por bloques
  (tarjetas: Motor y suspensión / Carrocería / Interiores / Extras), barra de
  **completitud**, etiqueta "declarado por el vendedor" en campos sensibles
  (`choques_reparados`, `estado_motor`).
- Formulario del vendedor por bloques (en `mis-publicaciones`): 3 pestañas + extras,
  guardado parcial por bloque (un PATCH por bloque), sin obligar ningún campo.
- Feed: chip "Ficha N% completa" en `ListingCard` cuando `completitud_ficha != null`.
- Actualizar `src/types/api.ts` (mirror de los schemas nuevos).
**Compuerta M1:** ✅ cerrada — `tsc --noEmit` limpio (sin lint nuevo; 4 preexistentes),
revisión `revisor-calidad` APTA (contrato fiel, guardado parcial correcto, privacidad/copy es-EC).
Deuda menor anotada: mapear el 422 de rango a copy es-EC; editar ficha de publicación pausada
requeriría un GET de ficha con scope de dueño (hoy el prellenado usa el GET público que solo
sirve `activa`).

### M2 — Fotos de la publicación ← **etapa vigente**
**Repos:** ambos · **Agentes:** dev-backend + dev-frontend
- **Decisión tomada (2026-07-19, Marcos): Cloudinary free tier** — sube el navegador con
  upload preset firmado; el backend solo guarda URLs. Configurar **alerta al 80 % de los
  25 créditos/mes** desde el día 1 (Cloudinary suspende, no cobra overage). Presupuesto y
  triggers de upgrade en [docs/producto/plan_costos.md](producto/plan_costos.md).
- Decisiones de infra asociadas (plan de costos F0/F1): Render Starter $7 ya; Vercel Pro
  $20 al vender el primer paquete de tokens.
- Backend: tabla `fotos_publicacion` (publicacion_id FK, url, bloque opcional
  `motor_suspension|carroceria|interiores|general`, orden, límite p. ej. 12 por
  publicación). Migración `0018`. Endpoints CRUD del dueño + salida en el detalle.
- Frontend: uploader por bloque + galería en el detalle.
**Compuerta M2:** subir/borrar/reordenar funciona; URLs largas no truncadas (aprender de
`imagen_url` 2048); el feed usa la primera foto como portada.

### M2.5 — Publicación transparente: las 3 vías del vendedor ← **etapa vigente**
**Decisión de producto (Marcos, 2026-07-19).** Un vendedor publica de tres formas:
1. **Manual (F1, la base):** wizard de 3 pasos — datos básicos → **ficha técnica completa
   (3 bloques, todos los campos visibles)** → fotos. Al crear la publicación se lo lleva
   directo a la ficha (hoy queda suelto y la ficha nace vacía). Puede posponer, pero con
   CTA persistente "Completa tu ficha (N %)" y, bajo 30 % de completitud, el feed/detalle
   muestran "Ficha incompleta" en vez del chip de porcentaje.
2. **Con IA por fotos (futuro, etapa M6):** de las fotos se extrae el detalle para
   prellenar los 3 bloques; el vendedor valida antes de guardar. No se construye ahora.
3. **Referencia externa (FB/OLX):** formulario reducido (ya existe) + etiqueta visible
   **"Referencia externa · datos no verificados"** en feed y detalle (copy no agresivo).

**Consulta por placa en stand-by parcial:** la web solo expone fuentes que entregan datos
sin captcha — ANT y AMT/EPMTSD (worker). SRI y FGE salen de la UI (ni tarjetas
passthrough), desactivables por env var para reactivar sin redeploy. El código backend
queda DORMIDO tal cual (reversible).

**Compuerta M2.5:** wizard operativo end-to-end; publicación nueva aterriza en la ficha;
etiquetas de referencia externa y ficha incompleta visibles; SRI/FGE ausentes de la web;
guión de prueba v2 pasado. (La compuerta M2 —fotos— se cierra junto con esta, con el
mismo guión.)

**Estado (2026-07-19): código implementado, compuerta ABIERTA a la espera de la prueba manual.**
Todo el cambio es de frontend (`consulta-placas-web`); el backend no se tocó.
- Stand-by por env var `NEXT_PUBLIC_FUENTES_INACTIVAS` (default `sri,fge`) →
  `src/lib/fuentes.ts`; documentado en AGENTS.md §8. **EPMTSD se reactiva** (era una lista
  hardcodeada `["FGE","EPMTSD"]`).
- Wizard de 3 pasos en `/marketplace/publicar`; `FichaEditor` acepta `onCompletitud`.
- CTA "Completa tu ficha (N %)" en mis-publicaciones y en el detalle **solo para el dueño**;
  "Ficha incompleta" bajo 30 % en feed y detalle público (`UMBRAL_FICHA_INCOMPLETA`).
- Etiqueta "Referencia externa · datos no verificados" en feed y en mis-referencias.
- Verificado: `tsc --noEmit` limpio, `npm run lint` = 4 errores preexistentes (0 nuevos),
  `npm run build` OK. Revisión `revisor-calidad` con 2 hallazgos MAYORES, **ambos corregidos**.
- **Falta para cerrar:** correr el **guión de prueba v2**
  ([guion_prueba_market.md](guion_prueba_market.md) §3-bis, secciones A–E) contra local.

### M2.6 — Market-first + datos oficiales automáticos (sigue a M2.5)
**Decisión de producto (Marcos, 2026-07-19).**
1. **Reposicionamiento: el producto ES el market de autos.** La consulta por placa pasa a
   ser herramienta secundaria ("adicional") hasta resolver los bloqueos de las páginas
   estatales. Landing/hero, navegación, títulos y copy giran a market: comprar/vender con
   transparencia. El feed gana protagonismo en la home.
2. **Enriquecimiento oficial automático:** al ingresar la placa en el paso 1 del wizard,
   el frontend dispara en segundo plano el `GET /consultar/{placa}` existente (fire &
   forget) → los datos quedan cacheados en `consultas` (regla §10.2 intacta: el CRUD de
   publicaciones jamás invoca scraping). El detalle público del anuncio muestra la sección
   **"Datos oficiales"** (solo fuentes activas: ANT, AMT) — matrícula y multas visibles
   junto a la ficha del vendedor.
**Compuerta M2.6:** home market-first; publicar dispara la consulta sin bloquear el flujo
(fallo de fuente = silencioso para el vendedor); detalle muestra datos oficiales cuando
existen en caché; consulta por placa sigue accesible como sección secundaria.

**Estado (2026-07-19): código implementado, compuerta ABIERTA a la espera de la prueba manual.**
- Home market-first (hero "Compra y vende autos con transparencia", CTAs "Ver autos en
  venta"/"Publica tu auto", destacados del feed, consulta bajada a "Herramientas"),
  navegación reordenada y metadatos/copy girados a market. **Ninguna ruta de consulta se
  eliminó.**
- Fire & forget de `GET /consultar/{placa}` desde el cliente al crear la publicación
  (§10.2 intacta: el CRUD del backend nunca invoca scraping — verificado por el revisor).
- Sección "Datos oficiales" en `/marketplace/{id}`, filtrada por `fuenteInactiva`, con
  "Consultado el …" y degradación a "Datos oficiales en proceso".
- **Backend mínimo**: campo aditivo `consultado_en` en `EstadoFuenteItem` (caché +
  `consultar_con_cache` + consolidador). **Sin migración** (`alembic heads` = `0018`).
- Verificado: `import main` → 61 rutas (sin cambio), `tsc --noEmit` limpio, lint 4
  preexistentes, `build` OK. Revisión `revisor-calidad`: **APTO**, sin bloqueantes; los 2
  hallazgos mayores se resolvieron (uno) y se difirieron (el otro, ver abajo).
- **Falta para cerrar:** guión de prueba v3
  ([guion_prueba_market.md](guion_prueba_market.md) §3-ter, secciones F–H).

**Deuda que entra a M3 (detectada por el revisor en M2.6):** el detalle público llama
`GET /consultar/{placa}/perfil`, que en *cache miss* **dispara scraping** (Playwright ANT +
encolado AMT). Como el anuncio es público e indexable, varias visitas sobre una placa fría
podrían generar scrapes concurrentes contra la misma fuente (choca con el skill
`scraping-respetuoso`). Mitigación propuesta: parámetro `solo_cache=true` en el endpoint de
perfil para este consumo, o no disparar en el primer render sin interacción del usuario.

### M2.7 — Pulido UX del market (feedback de prueba, 2026-07-19)
Hallazgos de Marcos sobre M2.5/M2.6 en local:
1. **Consulta de placa muy extensa** → vista compacta: resumen de un vistazo + secciones
   plegadas. Aplica también a "Datos oficiales" dentro del anuncio.
2. **Presentación de los objetos del marketplace** → rediseño de tarjetas y detalle
   (foto protagonista, precio prominente, jerarquía clara, mobile-first).
3. **Faltan puntos de entrada visibles**: subir fotos (fuera del wizard) y "referenciar
   un anuncio externo" (el flujo existe pero no se descubre).
**Compuerta M2.7:** los 3 hallazgos resueltos y re-probados con el guión v2/v3.

**Estado (2026-07-19): código implementado, compuerta ABIERTA a la espera de la prueba manual.**
Solo frontend — **el backend no se tocó** (verificado por el revisor: sin cambios en `src/`
ni `alembic/`).
- **Consulta compacta**: `ResumenPlaca` (máx. 6 datos, tipografía grande) + todo el detalle
  en `Acordeon` (`<details>` nativo) **cerrado por default**. `PerfilVehiculo` reescrito sin
  perder polling, reintento de AMT, gating de fuentes ni la sección de desbloqueos.
- **Objetos del market**: tarjeta con portada de ratio fijo 4:3 + placeholder, precio grande,
  título de una línea, una fila de chips y toda la tarjeta clickeable. Detalle con jerarquía
  foto → precio → ficha → oficial → extras, galería con swipe en móvil, ficha por bloques
  con íconos. Se eliminó `onEliminar` (código muerto).
- **Entradas**: bloque "¿Viste un auto en Facebook u OLX?" en `/marketplace` + enlace en la
  home; botones visibles **📷 Fotos** y **📋 Ficha técnica** en mis-publicaciones (llegar a
  fotos sin rehacer el wizard).
- Verificado: `tsc --noEmit` limpio, lint 4 preexistentes, `build` OK. Revisión
  `revisor-calidad`: **APTO**, sin bloqueantes; el hallazgo mayor del veredicto con la fuente
  municipal caída se corrigió en la sesión.
- **Falta para cerrar:** guión de prueba v4
  ([guion_prueba_market.md](guion_prueba_market.md) §3-quater, secciones I–L), **en celular**.

**Deuda de M2.6 que M2.7 NO resolvió (sigue abierta para M3):** `DatosOficialesMini` llama a
`GET /consultar/{placa}/perfil` en el primer render de una página pública e indexable, y ese
endpoint **dispara scraping en cache miss**. El rediseño reescribió el componente sin aplicar
ninguna de las dos mitigaciones ya acordadas (`solo_cache=true`, o disparar solo con
interacción del usuario). Resolverlo antes de que el market reciba tráfico real.

### M2.8 — Borrador con umbral, ficha para todos, garage y referencias ricas (feedback 2026-07-19)
1. **BUG:** el plan light no deja llenar la ficha — debe ser idéntico a premium (el
   backend nunca restringió por plan; gate mal puesto en frontend).
2. **Estado `borrador` + umbral de publicación:** el wizard crea la publicación como
   borrador (solo visible al dueño); se puede guardar a medias; **"Publicar" solo se
   habilita con ficha ≥ umbral** (`UMBRAL_FICHA_PUBLICACION`, default 30 %, env var).
   Activar sin umbral → 422. El cobro premium se mueve al momento de ACTIVAR (no se
   cobra por borradores). Publicaciones activas existentes no se retro-validan.
3. **Mi garage:** cada vehículo muestra su estado de venta: con publicación → CTA
   "Completa tu ficha (N %)" / "✓ Ficha completa"; sin publicación → "Publicar este
   auto" (wizard prellenado con placa y vínculo).
4. **Referencias externas ricas:** migración `0019` — `descripcion`, `ciudad`,
   `kilometraje`, `fotos` (JSONB lista, máx 5 vía Cloudinary) en
   `publicaciones_referenciadas`, para copiar los detalles del anuncio de FB. La
   etiqueta "Referencia externa · datos no verificados" se mantiene; editar contenido
   sigue devolviendo la referencia a moderación `pendiente`.
**Compuerta M2.8:** los 4 puntos re-probados (guión v5); borrador nunca visible en feed
ni por URL pública; imposible activar bajo el umbral; light y premium con ficha idéntica.

**Estado (2026-07-19): código implementado, compuerta ABIERTA a la espera de la prueba manual.**
⚠️ **Marcos debe correr `alembic upgrade head`** (migración **0019**) antes de probar.
- **BUG del light:** no existía ningún gate por plan en el frontend. La causa real era que
  los editores de ficha y fotos prellenaban con el endpoint **público**, que solo sirve
  publicaciones `activa`. Se agregó `GET /marketplace/publicaciones/{id}/mia` (dueño,
  cualquier estado) — imprescindible además para que el borrador se pueda completar.
- **Borrador + umbral:** `EstadoPublicacion.BORRADOR`, creación sin cobro,
  `UMBRAL_FICHA_PUBLICACION` (env, default 30) y cobro premium al ACTIVAR, idempotente por
  la columna nueva `premium_cobrado_en`.
- **Mi garage:** CTA por vehículo cruzando por placa con las publicaciones propias.
- **Referencias ricas:** migración `0019` (`descripcion`, `ciudad`, `kilometraje`, `fotos`
  JSONB máx 5) + firma Cloudinary propia + formulario con uploader. Editar el contenido
  sigue devolviendo la referencia a moderación `pendiente`.
- Verificado: `import main` → 63 rutas; `alembic heads` → `0019`; `tsc --noEmit` limpio;
  lint 4 preexistentes; `build` OK.
- Revisión `revisor-calidad`: **2 BLOQUEANTES + 1 MAYOR, los tres corregidos y
  re-verificados con simulación de los caminos exactos** (ver bitácora).
- **Falta para cerrar:** guión v5 ([guion_prueba_market.md](guion_prueba_market.md)
  §3-quinquies, secciones M–P), tras aplicar la migración.

### M3 — Búsqueda y filtros del feed
**Repos:** ambos
- Backend: `GET /marketplace/feed` con query params: `tipo`, `combustible`,
  `transmision`, `precio_min/max`, `anio_min/max`, `q` (marca/modelo/título). Los
  catálogos cerrados de la ficha hacen los filtros triviales (índices GIN sobre JSONB si
  hace falta). Paginación (`limit/offset` o cursor).
- Frontend: barra de filtros + estado en la URL (compartible).
**Compuerta M3:** filtros combinables sin N+1 (revisar SQL emitido); feed pagina; sin
regresión del orden premium → light → referenciadas.

### M4 — Cuentas de patio (multi-vehículo)
**Repos:** ambos · **Decisión de modelo previa con el controller**
- `perfiles_patio` (usuario_id, nombre comercial, RUC opcional validado con
  `validar_ruc`, ciudad, logo, teléfono): un usuario "patio" publica N vehículos con
  página propia (`/patio/[slug]`) y sello "Patio" en el feed.
- Reglas de negocio a definir: precio por volumen de publicaciones premium, límites del
  plan gratis para patios.
**Compuerta M4:** página pública del patio; el feed distingue particular vs patio; PII
del patio es comercial (pública), la del particular sigue protegida.

### M5 — Contacto comprador-vendedor
- Arranque simple: botón de contacto (WhatsApp deep link con placa/título pre-llenados +
  contador de clics como métrica de demanda). Chat interno queda para después — evitar
  construir mensajería antes de validar demanda.
**Compuerta M5:** el vendedor elige exponer o no su canal; nada de PII sin opt-in.

### M6 — Registro asistido por IA (vía 2 de publicación)
- De las fotos del vehículo se extrae el detalle (visión) para **prellenar** los 3 bloques
  de la ficha; el vendedor **valida campo por campo** antes de guardar (la IA propone, el
  humano firma — coherente con "declarado por el vendedor").
- Evaluar costo por análisis en `plan_costos.md` antes de construir (F2+).
**Compuerta M6:** precisión validada sobre ≥20 autos reales; nunca guarda sin validación.

---

## 3. Protocolo por sesión de desarrollo (ritual)

1. **Abrir**: leer `docs/bitacora.md` (última entrada) y este plan; confirmar en qué
   etapa estamos y su compuerta.
2. **Ejecutar**: delegar la tarea al agente que corresponda (dev-backend /
   dev-frontend). Una etapa puede tomar varias sesiones; trocear en tareas con criterio
   de aceptación claro.
3. **Revisar**: correr el agente **revisor-calidad** sobre el diff antes de commitear
   (checklist §5). Lo que falle se corrige en la misma sesión.
4. **Cerrar**: entrada en `docs/bitacora.md` (qué se hizo, verificación, pendientes) +
   commit con mensaje descriptivo. Si la compuerta de la etapa se superó, marcarla aquí.
5. **Control externo**: al cierre de cada **etapa**, sesión con el controller (Cowork)
   para revisión integral y planificación fina de la siguiente.

## 4. Agentes (`.claude/agents/`)

| Agente | Rol | Herramientas |
|---|---|---|
| `dev-backend` | Implementa backend FastAPI según AGENTS.md (módulos DDD, migraciones manuales, contrato de errores) | todas |
| `dev-frontend` | Implementa frontend Next.js 16 / Tailwind 4 (tema "confianza clara", mirror de types) | todas |
| `revisor-calidad` | Revisa diffs contra el checklist del proyecto. **Solo lectura**: no edita, reporta | lectura + bash |

## 5. Checklist del controller (compuerta genérica, aplica a todo diff)

- [ ] Español es-EC en código, rutas, columnas y copy; copy no agresivo.
- [ ] Contrato de errores: 400 formato · 404 "no es tuyo" (indistinto) · 409 conflicto/sin dato · 422 validación · **402 pago con tokens**. Nunca 500.
- [ ] Migración manual, revisada, con `downgrade` y nombre descriptivo; modelo registrado en `src/registry.py`.
- [ ] Privacidad: sin VIN completo ni nombre crudo del dueño en vistas públicas; `Depends(usuario_actual)`/`vehiculo_propio` en todo lo privado.
- [ ] CRUD nunca invoca scraping (§10.2). Listados con `selectinload` (sin N+1).
- [ ] Rutas dinámicas declaradas después de las literales del mismo prefijo.
- [ ] No se cobra por transparencia; solo costo/dificultad/valor real (§10.3).
- [ ] Sin dependencias nuevas sin justificación documentada.
- [ ] Verificación mínima ejecutada: `import main` + conteo de rutas, `alembic heads`, prueba de schemas; frontend: `tsc --noEmit`.
- [ ] Bitácora actualizada.
