# Bitácora de trabajo — `consulta_placas_ec`

Registro cronológico de **lo que se hace en cada sesión** (decisiones, cambios, pendientes).
Complementa, no reemplaza:
- [AGENTS.md](../AGENTS.md) — fuente de verdad (reglas, fases, convenciones).
- [proyecto-snapshot.md](../proyecto-snapshot.md) — foto del estado AS-IS completo.

Entradas nuevas arriba (más reciente primero). Formato por entrada:
fecha · rama · qué se hizo · verificación · pendientes.

---

## 2026-07-20 — Market MC1: portada del market para el comprador

**Repos:** ambos (frontend el grueso; backend **una migración mínima**). Primera etapa del
**carril C (comprador)** — hasta aquí todo el market era carril V (vendedor). Diseño en
[producto/experiencia_comprador.md](producto/experiencia_comprador.md) §2. Revisado por
**revisor-calidad** (**APTO**, sin bloqueantes). **Commit sin push.**

**Qué se hizo — `/marketplace` deja de ser un feed plano y pasa a portada curada**
Los 7 bloques del doc §2, móvil primero: buscador protagonista · **Tus favoritos** (arriba
del todo, solo logueado) · Destacados premium en carrusel · **Verificados y transparentes**
(`verificado` o ficha ≥ 80 %) · **Explora por marca** · Recién publicados · **Por
presupuesto** (< $10k · $10-20k · > $20k) · Referencias externas al pie.
**Regla dura respetada: un bloque sin contenido no se renderiza** — nada de encabezados
sobre grillas vacías, incluidas las bandas de presupuesto sin stock.

**♡ favorito con un toque en toda tarjeta.** Reutiliza el módulo `favoritos` existente,
que estaba subutilizado desde la Fase 3. Va sobre la foto, es un `<button>` accesible
(`aria-pressed`) con `preventDefault + stopPropagation` para no disparar el `Link` de la
tarjeta. Optimista con rollback; 409 = éxito idempotente. **Anónimo:** invitación amable
("Guarda este auto para verlo después"), nunca un 401 crudo ni una redirección de golpe.

**Decisiones de diseño**
- **Sin endpoints de agregados.** `GET /marketplace/feed` ya devuelve todas las activas sin
  límite, así que las **marcas con stock** y los conteos se derivan en el cliente. Un
  endpoint habría duplicado la fuente de verdad a cambio de nada. Las marcas **nunca** se
  hardcodean (compuerta MC1): si no hay ningún Kia publicado, no existe el chip "Kia".
- **El buscador filtra en cliente** sobre el feed ya cargado. Los filtros reales con query
  params y paginación por cursor son **MC2**; adelantarlos aquí habría sido trabajo tirado.
- **Favoritos sigue siendo por PLACA, no por `publicacion_id`** (§10.4). El cruce en "Tus
  favoritos" no asume unicidad: si dos publicaciones comparten placa aparecen las dos, y una
  placa favorita sin publicación simplemente no aparece.

**Backend (mínimo, una migración): `0020_favorito_precio`**
`precio_al_guardar` Numeric(12,2) **nullable** en `vehiculos_favoritos`. Es la única pieza
que faltaba para el **badge de baja de precio**: sin persistir el precio al momento de
guardar no hay contra qué comparar. Nullable a propósito y sin backfill — los favoritos
previos y las placas sin publicación no tienen referencia, y un `0` fingido se leería como
"bajó de precio", que es peor que no saber. El badge solo se muestra en **bajada**; una
subida no se anuncia. La comparación la hace el frontend con el precio que ya trae del feed.

**Correcciones aplicadas tras la revisión**
1. **Bug de favoritos:** al recuperar de un 409, si la relectura de `/favoritos` fallaba, el
   `?? []` **vaciaba el mapa entero** — se apagaban todos los ♡ y desaparecía "Tus
   favoritos" aunque en BD siguieran guardados. Ahora ante fallo se conserva el estado.
2. **Rendimiento móvil:** "Recién publicados" y "Verificados" se renderizaban **completos**.
   Con el feed sin límite, un auto premium+verificado+favorito se pintaba 4 veces y con ~300
   activas la portada montaba cientos de tarjetas con sus imágenes — en celulares de gama
   baja, que son nuestro público. Limitados a 12, con aviso de cuántas hay en total.
3. Badge de baja visible en **todos** los bloques, no solo en "Tus favoritos".
4. `haySesion` unificado con `tieneSesion()`: antes confundía "sin sesión" con "backend
   caído" y quedaba divergente del `alternar`.

**Verificación:** `import main` OK · `alembic heads` → **`0020`, cabeza única** ·
`tsc --noEmit` limpio · lint **4 errores preexistentes, 0 nuevos** · `build` OK.
Privacidad confirmada por el revisor: los **borradores son estructuralmente inalcanzables**
desde la portada (el feed filtra `estado == ACTIVA`), y no se agregó ni un campo al feed.

**Pendientes**
- ⚠️ **Marcos debe correr `alembic upgrade head`** (0020) antes de probar: sin ella el ♡
  falla al guardar. Sigue pendiente también la **0019** de M2.8.
- Correr el **guión v6** ([guion_prueba_market.md](guion_prueba_market.md) §3-sexies,
  secciones R–U), **en celular**.
- Deuda anotada para MC2: el corte a 12 se resuelve naturalmente con la paginación por
  cursor; falta la barra sticky de búsqueda al scrollear (transversal del doc §2).
- Deuda transversal (preexistente, no de MC1): los `Decimal` de dinero no tienen cota
  superior (`le=`/`decimal_places`), así que un desbordamiento de `Numeric(12,2)` daría
  `DataError` → 500. Afecta a todos los precios del proyecto, no solo a este campo.
- Sigue abierta la deuda de M2.6: `DatosOficialesMini` dispara scraping en cache miss.

---

## 2026-07-20 — Market M2.9: detalle local de las referencias externas

**Repos:** ambos (frontend el grueso; backend **un endpoint nuevo**, sin migración).
Ajuste de UX pedido por Marcos sobre M2.8. Revisado por **revisor-calidad** (**APTO**, sin
bloqueantes). **Commit sin push**.

**El problema:** la tarjeta de referencia era un `<a>` directo al portal externo. Un clic
te expulsaba del sitio **sin haber visto nada** — ni las fotos ni el detalle que el
aportante se había tomado el trabajo de copiar en M2.8.

**Qué se hizo — dos interacciones separadas**
1. **Clic en la tarjeta → detalle LOCAL** `/marketplace/referencias/{id}`: aviso ámbar con
   el copy exacto "Referencia externa · datos no verificados" **arriba del todo** (antes de
   la galería y del precio: el visitante sabe qué mira antes de leer los datos), galería
   con swipe en móvil, precio, descripción, ciudad, kilometraje y portal de origen. Si la
   referencia trae placa, también "Verificar esta placa".
2. **Botón explícito "Ver anuncio original en {fuente} ↗"** — la única salida al portal
   externo, en pestaña nueva (`rel="noopener noreferrer"`), avisando que abre otro sitio.
   En la tarjeta del feed el texto pasó de "Ver en {fuente} ↗" a "Ver detalle · {fuente}"
   (sin flecha: ese clic ya no sale del sitio).

**Backend (no estaba pedido, pero era necesario):** `GET /marketplace/referencias/{id}`
público. No existía forma de traer UNA referencia, y resolverlo desde el feed no servía
porque está capado a 30 (`LIMITE_REFERENCIADAS_FEED`): una referencia más antigua habría
dado 404. Sirve **solo aprobadas y activas** (mismo filtro que el feed, en el `WHERE`), con
404 indistinto — una `pendiente` o `rechazada` **no se puede ver por URL directa**, que era
el punto crítico de abrir una superficie pública nueva. Declarado **al final** del router
para no capturar las literales `GET /mias` y `GET /pendientes`.

**Verificación**
- Backend: `import main` → **64 rutas**; orden de rutas confirmado sobre las registradas
  (`/mias` y `/pendientes` siguen antes del dinámico); `alembic heads` → `0019` (sin
  migración nueva).
- Frontend: `tsc --noEmit` limpio; lint **4 errores, los 4 preexistentes**; `build` OK con
  la ruta `/marketplace/referencias/[id]` registrada.
- Revisor: sin bloqueantes. Confirmó el filtro aprobada+activa, el orden de rutas, el
  `rel="noopener noreferrer"` y que `PublicacionReferenciadaSalida` no expone `usuario_id`
  ni datos del aportante (no se amplía la superficie de datos, solo el alcance).
- Menores del revisor, **corregidos**: comentario de cabecera de `ListingCard` que seguía
  diciendo "link vivo al portal", y las dos menciones desactualizadas en **AGENTS.md §10.6**
  y `proyecto-snapshot.md`. (`docs/diagramas/modelo_datos.mermaid` dice "enlace vivo" sobre
  la columna `url_externa`, donde **sigue siendo cierto** — no se tocó.)

**Pendientes**
- Guión de prueba: nueva **sección Q** en [guion_prueba_market.md](guion_prueba_market.md)
  (§3-quinquies) y corregido el paso de la sección E que describía el comportamiento viejo.
- Sigue pendiente ⚠️ **`alembic upgrade head` (0019)** de M2.8 y el push de ambos repos.
- Anotado por el revisor (no es deuda nueva, es el patrón del proyecto): la página es
  client-only, así que los detalles de referencia no tienen SEO ni preview al compartirse.

---

## 2026-07-19 — Market M2.8: borrador con umbral, ficha para todos, garage y referencias ricas

**Repos:** ambos. Backend con **migración `0019`** (⚠️ **pendiente de aplicar en Neon: la
corre Marcos con `alembic upgrade head`**). Implementado por el **controller**, revisado por
**revisor-calidad**. **Commit sin push** — Marcos prueba primero.

**Qué se hizo**

1. **BUG "el plan light no deja llenar la ficha" — la causa no era la que parecía.**
   Busqué el gate por plan en el frontend y **no existe**: ni en el wizard, ni en
   mis-publicaciones, ni en el detalle; el `PATCH .../ficha` del backend tampoco restringe.
   La causa real es que `FichaEditor` y `GaleriaFotosEditor` prellenaban con
   `obtenerPublicacionDetalle` = el endpoint **público**, que solo sirve publicaciones
   `activa` (deuda ya anotada en M1). Fix: **`GET /marketplace/publicaciones/{id}/mia`**
   (dueño, cualquier estado) y los dos editores lo usan. Esto era además **requisito** del
   borrador: por definición no es `activa`, así que sin este endpoint el paso 2 del wizard
   no habría cargado nunca.
2. **Borrador + umbral de publicación.** `EstadoPublicacion.BORRADOR` (String en BD, sin
   migración de tipo). `POST /publicaciones` crea en borrador y **ya no cobra**. Publicar es
   `PATCH {estado: activa}`: valida `UMBRAL_FICHA_PUBLICACION` (env, default 30) → **422**
   *"Completa al menos el 30% de la ficha para publicar. Vas en N%."*, y **ahí** se debita
   el premium. Verificado que `borrador` no se expone: feed y detalle público ya filtraban
   por `activa` (el revisor auditó todos los consumidores). Las activas existentes **no se
   retro-validan**.
3. **Mi garage.** Cada vehículo cruza con las publicaciones propias **por placa** — no por
   `vehiculo_id`, porque exponerlo obligaría a sacar un id interno del garage en
   `PublicacionInternaSalida`, que también sirve el feed anónimo (el revisor validó la
   decisión). CTA "Publicar este auto" (wizard prellenado por query params, con `Suspense`
   por `useSearchParams`), "Completa tu ficha (N %)", "Borrador sin publicar" o
   "✓ Ficha completa".
4. **Referencias ricas.** Migración `0019`: `descripcion` (2000), `ciudad` (80),
   `kilometraje` (BigInteger) y `fotos` (JSONB NOT NULL default `'[]'`, **máx 5** validado
   en Pydantic con dedup). Endpoint `POST /marketplace/referencias/firma-foto` con carpeta
   propia. Formulario con los campos nuevos + uploader. Los campos ricos entran a
   `_CAMPOS_CONTENIDO`: editarlos devuelve la referencia a moderación `pendiente`.

**Verificación**
- Backend: `import main` → **63 rutas**; `alembic heads` → **`0019`** único; validación de
  fotos (dedup + rechazo de 6) y del umbral (0 % → 422 con el copy exacto; 35 % → pasa).
- Frontend: `tsc --noEmit` limpio; lint **4 errores, los 4 preexistentes**; `build` OK.

**Hallazgos del revisor — 2 BLOQUEANTES y 1 mayor, los tres corregidos**
- **Doble cobro del premium.** Mi idempotencia "por construcción" (prohibir volver a
  borrador) **no se sostenía**: `light → PATCH plan=premium (en borrador) → PATCH
  estado=activa` cobraba **6 tokens** en vez de 3, porque `asciende_a_premium` y
  `publica_borrador` eran flags independientes.
- **Activación saltándose el umbral Y sin pagar.** `borrador → pausada → activa` dejaba el
  anuncio **activo, premium, destacado, con ficha al 0 % y costo 0 tokens**.
- **Corrección de ambos:** máquina de estados explícita (`_aplicar_transicion_estado`: desde
  `borrador` **solo** se sale a `activa`, validando umbral; a `borrador` no se vuelve) +
  cobro derivado de **un solo predicado sobre el estado resultante** ("queda premium Y
  activa Y `premium_cobrado_en is None`"), con la marca persistida nueva
  **`premium_cobrado_en`** (agregada a la misma migración `0019`, que aún no se aplicó).
  Re-verificado simulando los caminos exactos del revisor: 1 cobro en vez de 2, y 422 en el
  atajo por `pausada`.
- **Mayor:** `PATCH /referencias/{id}` con `{"fotos": null}` reventaba en 500 (columna NOT
  NULL). Ahora un `null` explícito se normaliza a lista vacía ("quitar todas").
- Menores corregidos: docstrings que citaban un endpoint `activar` inexistente, `descripcion`
  de referencias ahora sí se renderiza en la tarjeta, `carpeta_referencia` muerta eliminada,
  el garage distingue borrador/vendida, y el wizard avisa del cobro premium **antes** de
  pulsar publicar (antes se enteraba con un 402).

**Pendientes**
- ⚠️ **`alembic upgrade head` (0019) en Neon** — sin eso, las referencias y el cobro
  idempotente no funcionan.
- **Correr el guión v5** ([guion_prueba_market.md](guion_prueba_market.md) §3-quinquies,
  secciones M–P), incluidos los dos casos de abuso que encontró el revisor.
- **Push pendiente** de ambos repos.
- Sigue abierta la deuda de M2.6/M2.7: `DatosOficialesMini` dispara scraping en cache miss
  desde una página pública e indexable (resolver en M3 con `solo_cache=true`).

---

## 2026-07-19 — Market M2.7: pulido UX (consulta compacta, tarjetas, entradas)

**Repo:** `consulta-placas-web` (**el backend no se tocó** — verificado por el revisor: sin
cambios en `src/` ni `alembic/`). Responde a los 3 hallazgos de la prueba de Marcos sobre
M2.5/M2.6. Implementado por el **controller**, revisado por **revisor-calidad** (**APTO**,
sin bloqueantes). **Commit sin push** — Marcos prueba primero.

**Qué se hizo**

1. **Consulta de placa compacta** (hallazgo 1: "muy extensa").
   - Nuevo `ResumenPlaca.tsx`: tarjeta "de un vistazo" con **máximo 6 datos** en tipografía
     grande (marca/modelo, año/color, matrícula, multas, total, fecha de consulta) y el
     veredicto. Exporta `derivarResumen`/`fechaLegible`, que reusa el anuncio (sin duplicar).
   - Nuevo `Acordeon.tsx` sobre **`<details>/<summary>` nativo**: sin estado, sin JS,
     accesible por teclado y sin sumar efectos de React (ni errores de lint).
   - `PerfilVehiculo.tsx` **reescrito**: todo el detalle (desglose por fuente, matriculación,
     identificación/titular, portales oficiales, tablero de fuentes) pasó a acordeones
     **cerrados por default**. La sección de desbloqueos con tokens queda **visible**: es
     acción, no detalle. El revisor confirmó que no hubo regresiones (polling, re-consulta
     con sesión, reintento de AMT, gating por `fuenteInactiva`, enlaces oficiales).
2. **Objetos del marketplace** (hallazgo 2: "presentación").
   - `ListingCard.tsx` reescrito, mobile-first: portada con **ratio fijo 4:3** (+ placeholder
     🚗 del mismo tamaño, para que la grilla no baile), **precio grande primero**, título en
     una línea truncada, **una sola fila de chips**, y **toda la tarjeta clickeable**. Se
     eliminaron la descripción y el bloque de mantenimientos que la estiraban, y la prop
     `onEliminar` (código muerto: ningún caller la pasaba).
   - Detalle reescrito con jerarquía **foto → precio/título/CTA → ficha → oficial → extras**.
     Galería con **swipe** en móvil (scroll-snap nativo, sin librerías) y miniaturas en
     escritorio. Ficha en tarjetas por bloque con íconos (⚙️ 🚙 🪑 ✨).
   - Nuevo `DatosOficialesMini.tsx`: la sección oficial en el anuncio baja a **3-4 líneas**
     con "Ver detalle completo →" hacia `/consultar/{placa}`.
3. **Puntos de entrada que faltaban** (hallazgo 3: "no se descubren").
   - `/marketplace`: bloque visible **"🔗 ¿Viste un auto en Facebook u OLX?"** con
     "Referenciar anuncio externo" (el flujo ya existía, pero estaba escondido entre botones
     iguales) + "Mis referencias". Enlace equivalente en la home.
   - `mis-publicaciones`: las acciones pasaron de enlaces de texto a **botones visibles
     📷 Fotos y 📋 Ficha técnica**, con estado activo. El vendedor llega a subir fotos **sin
     rehacer el wizard**.

**Verificación**
- `tsc --noEmit` limpio; `npm run lint` → **4 errores, los 4 preexistentes**; `build` OK.
- **Hallazgo mayor del revisor, corregido en la sesión:** con AMT en **`error_fuente`** el
  resumen decía **"Al día"** en verde y el botón de reintentar quedaba enterrado en un
  acordeón cerrado. Es la misma familia del bug que M2.6 arregló para `en_proceso`, ahora
  expuesta para la fuente caída. Ahora `derivarResumen` expone `municipalesCaidas`, el
  veredicto muestra **"Sin dato municipal"**, el chip del acordeón dice lo mismo y ese
  acordeón **se abre solo** cuando hay que reintentar.
- Menores corregidos: guarda explícita de `detalleBloqueado` antes de pintar cualquier monto
  (antes la privacidad dependía de que el consolidador vaciara `multas_detalle`), y
  `tabIndex`/`aria-label` en el carrusel móvil.

**Pendientes**
- **Correr el guión v4** ([guion_prueba_market.md](guion_prueba_market.md) §3-quater,
  secciones I–L) — **en celular**, que es donde se nota el rediseño.
- **Push pendiente** de ambos repos.
- **Deuda de M2.6 que M2.7 NO resolvió** (el revisor insistió en registrarla):
  `DatosOficialesMini` llama al perfil en el primer render de una página pública e indexable,
  y ese endpoint dispara scraping en cache miss. Las dos mitigaciones ya acordadas
  (`solo_cache=true` o disparo bajo interacción) siguen sin aplicarse. Resolver en M3, antes
  de que el market reciba tráfico real.

---

## 2026-07-19 — Market M2.6: market-first + datos oficiales automáticos en el anuncio

**Repos:** ambos (frontend el grueso; backend un cambio mínimo aditivo, **sin migración**).
Decisión de producto de Marcos (plan_market_autos.md §M2.6). Implementado por el
**controller**, revisado por **revisor-calidad** (**APTO**, sin bloqueantes).
**Commit sin push** — Marcos prueba primero.

**Qué se hizo**

1. **Reposicionamiento market-first.** El producto ES el market de autos; la consulta por
   placa pasa a herramienta de apoyo mientras las fuentes estatales sigan bloqueadas.
   - Home: hero **"Compra y vende autos con transparencia"** con CTA primario "Ver autos en
     venta" y secundario "Publica tu auto" (antes el hero era el buscador de placa). Nueva
     sección de destacados del feed (`DestacadosMarket.tsx`, premium primero, degrada a CTA
     si el feed está vacío). La consulta baja a una sección **"Herramientas"**.
   - Navegación: **Marketplace · Publicar · Consulta de placa · Precios** ("Consultar" se
     renombró). Pie, títulos, metadescripciones y copy de `/marketplace` girados a market.
   - **Ninguna ruta de consulta se eliminó** (verificado por el revisor): `/consultar` y
     `/consultar/{placa}` siguen intactas, solo pierden protagonismo.
2. **Enriquecimiento oficial automático (fire & forget).** Al crear la publicación en el
   paso 1 del wizard, el **cliente** dispara `GET /consultar/{placa}` sin `await`, sin
   spinner y tragando errores: el pipeline deja los datos cacheados en `consultas` y el
   vendedor no espera ni se entera si una fuente está caída. Usa `pub.placa` (la que
   normalizó el backend) para que la caché quede bajo la misma clave que lee el anuncio.
   **§10.2 intacta**: el CRUD del backend nunca invoca scraping — el revisor lo verificó con
   grep sobre `src/modules/marketplace/` y `src/modules/vehiculos/` (0 resultados).
3. **Sección "Datos oficiales" en `/marketplace/{id}`.** Consume el perfil consolidado de la
   placa, filtra por `fuenteInactiva` (SRI/FGE fuera) y muestra matrícula (ANT) e
   infracciones con **"Consultado el {fecha}"** en es-EC. Si no hay nada cacheado, degrada a
   **"Datos oficiales en proceso"** sin romper la página. **No filtra lo que se cobra**: con
   `multas_bloqueado` (el caso anónimo) solo se muestra el veredicto gratis, nunca los
   montos; el enlace lleva a `/consultar` para el detalle pagado.
4. **Backend (mínimo, aditivo, sin migración).** Campo `consultado_en: str | None` en
   `EstadoFuenteItem`. Lo inyecta la caché al leer (desde `creado_en`, **sobre una copia**
   para no ensuciar el objeto ORM) y `consultar_con_cache` para el dato recién scrapeado.
   Solo se sella lo que trajo datos (`ESTADOS_CACHEABLES`): sellar un error afirmaría una
   consulta exitosa que no ocurrió.

**Verificación**
- Backend: `import main` → **61 rutas (sin cambio)**; `alembic heads` → único `0018`;
  prueba directa de `consolidar_placa` → ANT cacheada propaga `consultado_en`, AMT
  `en_proceso` lo deja en `None`.
- Frontend: `tsc --noEmit` limpio; `npm run lint` → **4 errores, los 4 preexistentes**;
  `npm run build` OK.
- **Hallazgo mayor del revisor, corregido en la sesión:** la tarjeta de multas afirmaba
  **"Al día"** cuando AMT seguía `en_proceso` — el veredicto estaba incompleto y en un
  anuncio de venta ese falso negativo favorece al vendedor. Ahora, con el municipio en
  camino, muestra un estado neutro **"Consultando…"** y **no estampa fecha** (sellar con la
  hora de la ANT daba una sensación de completitud inexistente). Reproducido y verificado
  con `consolidar_placa` (ANT completada + AMT en_proceso → `tiene_pendientes: False`).
- Menores corregidos: docstring/sellado de `consultado_en` por estado cacheable, copy
  "(ANT y AMT)" → incluye municipios (podía listar EPMTSD), condición de "en proceso" ya no
  se queda pegada, y el fire & forget usa `pub.placa`.

**Pendientes**
- **Correr el guión de prueba v3** ([guion_prueba_market.md](guion_prueba_market.md) §3-ter,
  secciones F–H). Con eso se cierra M2.6.
- **Push pendiente** de ambos repos (Marcos prueba antes).
- **Deuda que entra a M3** (hallazgo mayor diferido): el detalle público llama al perfil, que
  en *cache miss* **dispara scraping**. Como el anuncio es público e indexable, varias
  visitas sobre una placa fría podrían generar scrapes concurrentes contra la misma fuente
  (choca con `scraping-respetuoso`). Propuesta: `solo_cache=true` en el endpoint de perfil.

---

## 2026-07-19 — Market M2.5: stand-by de fuentes + wizard de publicación + referencias

**Repos:** el grueso en `consulta-placas-web` (frontend); en este repo **solo documentación**.
Decisión de producto de Marcos (plan_market_autos.md §M2.5). Implementado por el
**controller**; revisado por **revisor-calidad**. **Commit sin push** — Marcos prueba primero.

**El backend NO se tocó.** Verificado: sin cambios en `src/` ni en `alembic/`. Los servicios
de SRI y FGE quedan vivos y **dormidos**; el ocultamiento es de presentación y reversible.

**Qué se hizo**

1. **Stand-by de fuentes.** Nuevo `src/lib/fuentes.ts` con `fuenteInactiva(clave)`, manejado
   por la env var **`NEXT_PUBLIC_FUENTES_INACTIVAS`** (default `sri,fge`; `""` reactiva todo).
   SRI y FGE salen de **toda** la UI: tarjeta "Valores SRI", enlace passthrough al portal del
   SRI, chips del tablero "Fuentes consultadas", lista del pie de página, filas de `/precios`
   (SRI y alertas legales) y metadatos SEO. El total "A pagar" del encabezado ya no suma
   valores del SRI (mostrar un monto sin su fuente era inexplicable). Documentado en
   **AGENTS.md §8**. ⚠️ **EPMTSD vuelve a mostrarse**: la lista vieja estaba hardcodeada como
   `["FGE","EPMTSD"]` y EPMTSD sí es una fuente activa vía worker residencial. Su enlace
   oficial pasó a `destacado` al quedar como acción principal de la sección.
2. **Wizard de publicación (3 pasos).** `/marketplace/publicar` pasó de formulario suelto a
   **datos básicos → ficha técnica → fotos**, con barra de pasos. Al crear la publicación
   **navega automático al paso 2** (antes el usuario caía en el feed y la ficha nacía vacía —
   ese era el problema que motivó la etapa). "Completar después" siempre disponible. Se
   conservan vinculación con el garage, selector de plan y manejo de 401/402.
   `FichaEditor` acepta un `onCompletitud` opcional (patrón latest-ref) para que el
   contenedor refresque el % en vivo.
3. **Transparencia de la ficha.** Umbrales en `src/lib/ficha.ts`
   (`UMBRAL_FICHA_INCOMPLETA = 30`, `FICHA_COMPLETA = 100`). CTA persistente
   **"Completa tu ficha (N %)"** en mis-publicaciones (abre el editor, el % baja en vivo) y
   en `/marketplace/{id}` **solo si el visitante es el dueño**. Bajo 30 %, feed y detalle
   público muestran **"Ficha incompleta"** en lugar del chip de porcentaje (`null` cuenta
   como incompleta).
4. **Referencias externas.** Copy exacto **"Referencia externa · datos no verificados"** en
   el feed (`ListingCard`) y en `mis-referencias`. El formulario de referenciar no se tocó.
   De paso, corregido un voseo preexistente ("Podés" → "Puedes") en mis-referencias.

**Verificación**
- `npx tsc --noEmit` limpio; `npm run lint` → **4 errores, los 4 preexistentes** (ninguno
  nuevo); `npm run build` OK (16 rutas).
- Sobre el **HTML renderizado** del build: el pie lista solo ANT y AMT; `/precios` ya no
  muestra las filas de SRI ni de alertas legales.
- **revisor-calidad**: 2 hallazgos MAYORES, **ambos corregidos en la sesión** —
  (a) `.env.example` quedaba fuera del repo por el patrón `.env*` del `.gitignore`
  (se agregó `!.env.example`, si no la variable nueva quedaba sin documentar);
  (b) `hayFuentesEnProceso` no filtraba fuentes ocultas, así que una FGE `en_proceso` dejaba
  el perfil repollando cada 4 s con el encabezado en "Consultando…" para siempre.
  Sin hallazgos de privacidad: el CTA del dueño no dispara nada sin sesión y falla en silencio.

**Pendientes**
- **Correr el guión de prueba v2** ([guion_prueba_market.md](guion_prueba_market.md) §3-bis,
  secciones A–E) en local. Con eso se cierran **M2.5 y M2** juntas.
- **Push pendiente** de ambos repos (Marcos prueba antes).
- Menor (anotado por el revisor, diferido a M3): el detalle público descarga
  `listarMisPublicaciones()` completo solo para saber si el anuncio es propio; un campo
  `es_mia` en el detalle lo resolvería.
- Menor: el botón del paso 1 ya no dice "Publicar Premium/gratis"; el aviso de que Premium
  cobra tokens vive solo en el selector de plan.

---

## 2026-07-19 — Market M2 (frontend): uploader + galería de fotos

**Repo:** `consulta-placas-web`. Implementado por el **controller** (el subagente dev-frontend se
cortó por límite de sesión a mitad); revisado por **revisor-calidad** (APTO, sin bloqueantes).

**Qué se hizo**
- **`types/api.ts` + `lib/api.ts`**: tipos `BloqueFoto`/`FirmaSubida`/`FotoRegistrar`/`FotoSalida`,
  `fotos` en `PublicacionDetalle`, `foto_portada` en `PublicacionInterna`. Funciones
  `firmarSubidaFoto`, `subirACloudinary` (fetch **directo** a Cloudinary, no al backend),
  `registrarFoto`, `reordenarFotos`, `eliminarFoto`. Nueva clase `CloudinaryError` para no
  confundir los códigos HTTP de Cloudinary con los del backend propio.
- **Galería pública** en `marketplace/[id]/page.tsx`: portada grande + miniaturas (solo lectura).
- **`GaleriaFotosEditor.tsx`** (dueño, en `mis-publicaciones`): subir (flujo firma→Cloudinary→
  registrar), borrar y reordenar (optimista con reversión). **Límite 12** (botón deshabilitado +
  corte del bucle + 409). Degrada con gracia ante **503** (Cloudinary no configurado). Carga con
  el patrón IIFE-async-en-useEffect (como FichaEditor) → sin error de lint nuevo.
- **`ListingCard.tsx`**: usa `foto_portada` como portada del feed (publicaciones internas).

**Verificación:** `tsc --noEmit` limpio; `npm run lint` → **4 errores (los preexistentes**;
`GaleriaFotosEditor` no agrega ninguno). Revisor: contrato fiel al backend, flujo de subida
correcto, manejo 503/409, privacidad (galería pública solo lectura, mutaciones con Bearer),
sin deps nuevas. Menor detectado y **corregido en la sesión**: errores de Cloudinary ahora se
distinguen de los del backend (`CloudinaryError`).

**Pendientes**
- **E2E real de fotos** requiere cargar `CLOUDINARY_*` en el backend (dev responde 503) y la
  **migración `0018` aplicada en Neon** (la corre Marcos). Sin eso, subir/registrar no opera.
- Compuerta M2: código listo en ambos repos; falta la verificación E2E con Cloudinary configurado
  (subir/borrar/reordenar + portada en el feed).

---

## 2026-07-19 — Market M2 (backend): fotos de la publicación (Cloudinary firmado)

**Rama:** `main`. Ejecutado por **dev-backend**, revisado por **revisor-calidad** (APTO).
Decisión de infra (Marcos, plan_costos.md): **Cloudinary free tier**, el navegador sube directo
con firma del backend; la BD solo guarda URLs. **Migración 0018 aún NO aplicada en Neon** (la
corre Marcos).

**Qué se hizo**
- **`fotos_publicacion`** (migración `0018`): `publicacion_id` FK→`publicaciones_internas`
  (CASCADE, index), `url` String(**2048**), `bloque` String(20) nullable
  (`motor_suspension|carroceria|interiores|general`, validado en Pydantic), `orden` Integer,
  `creado_en`. Modelo `FotoPublicacion` + relación `PublicacionInterna.fotos`
  (`delete-orphan`, `order_by orden`). Registrado en `registry.py`.
- **Firma Cloudinary** (`marketplace/services/cloudinary.py`): SHA-1 **manual** (sin SDK →
  cero deps nuevas); credenciales solo por env (`CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET/
  UPLOAD_FOLDER`). El `api_secret` **nunca** sale al cliente. Sin config → **503** (patrón vision.py).
- **Endpoints del dueño** (orden de rutas: literales antes que dinámicas): `POST .../fotos/firma`
  (503 si no hay config), `POST .../fotos` (valida URL de nuestro cloud → 400; **límite 12 → 409**;
  `orden` al final), `PATCH .../fotos/orden` (reorden; **422** si la lista no calza), `DELETE
  .../fotos/{foto_id}` (204; borra registro, no el binario). 404 indistinto de propiedad.
- **Salida**: `PublicacionDetalleSalida.fotos` (ordenadas) y `PublicacionInternaSalida.foto_portada`
  (primera por orden) en el feed. `selectinload(fotos)` en feed/mias/detalle/helpers → sin N+1.
- `.env.example` con las 4 vars (aviso de no commitear valores; 503 sin credenciales).

**Verificación:** `import main` → 61 rutas (las 4 `/fotos*` presentes; literales siguen
resolviendo); `Base.metadata` → 17 tablas con `fotos_publicacion`; `alembic heads` → único `0018`;
`alembic upgrade 0017:0018 --sql` (offline) genera tabla+índice y `downgrade` simétrico; firma
determinista y api_secret no expuesto; validación de URL rechaza http/host ajeno/spoofing de
subdominio. **Sin SDK cloudinary en requirements.**

**Pendientes / deuda menor (del revisor)**
- **`alembic upgrade head` contra Neon** (0018) — lo corre Marcos; cierra la parte backend de M2.
- `registrar_foto` con `orden` explícito no deduplica contra órdenes existentes (empate resoluble;
  `reordenar` lo normaliza). `FotoReordenar.orden` es lista de `foto_id` (nombre podría confundir).
- **DELETE no destruye el binario en Cloudinary** (barrido posterior, decisión acordada).
- **Frontend M2** (uploader por bloque + galería en el detalle): segunda sesión con dev-frontend.

---

## 2026-07-18 — Market M1: ficha técnica en el frontend (detalle + editor)

**Repo:** `consulta-placas-web` (commit `1c0bd95`). **Backend M0** cerrado antes: migración
`0017` aplicada en Neon (`alembic current` = `0017`), commits `45c7da9` (ficha) + `5855abb`
(agentes + plan). Ejecutado por el agente **dev-frontend**, revisado por **revisor-calidad**.

**Qué se hizo**
- **Detalle público** `app/marketplace/[id]/page.tsx`: consume `GET /marketplace/publicaciones/{id}`;
  pinta el anuncio + la ficha en 4 tarjetas (Motor y suspensión / Carrocería / Interiores /
  Extras), **barra de completitud** y etiqueta **"declarado por el vendedor"** en los campos de
  condición. Maneja 404 y ficha vacía.
- **Editor del vendedor** `components/FichaEditor.tsx` (inline en `mis-publicaciones`): 3 pestañas
  + extras, **guardado parcial por bloque** (un `PATCH .../ficha` que envía solo el bloque
  editado; los demás quedan intactos), nada obligatorio, selects con labels es-EC.
- `lib/api.ts` (`obtenerPublicacionDetalle`, `actualizarFichaPublicacion`), `lib/ficha.ts`
  (etiquetas de catálogos), `types/api.ts` (mirror de bloques/catálogos/`FichaSalida`/
  `FichaActualizar`/`PublicacionDetalle` + `completitud_ficha`), `ListingCard` (chip
  "Ficha N% completa").

**Verificación:** `tsc --noEmit` limpio; `eslint` sin errores nuevos (los 4 preexistentes de
`Header`/`admin/*`/`mis-publicaciones` siguen). Revisor: contrato fiel al backend, guardado
parcial correcto, sin PII, copy no agresivo, sin deps nuevas → **APTO**. **Compuerta M1 cerrada.**

**Pendientes / deuda menor**
- Mapear el 422 de rango (p. ej. cilindraje > 10000) a copy es-EC en `FichaEditor`.
- Editar la ficha de una publicación **pausada**: el prellenado usa el `GET` público (solo
  `activa`); haría falta un GET de ficha con scope de dueño. No bloquea M1 (nacen `activa`).
- Siguiente: **M2 — fotos de la publicación** (decisión previa de storage con Marcos).

---

## 2026-07-18 — Market de autos (paso 2): ficha técnica de la publicación

**Rama:** `main`. Decisión de rumbo: el pilar de consulta queda en su techo razonable
(SRI/FGE passthrough, AMT/EPMTSD vía worker residencial, proveedor real pendiente solo de
API key). Arranca el **market de autos** para uso particular y patios: primero, ver
vehículos y su detalle con transparencia para el comprador y registro simple del vendedor.

**Qué se hizo**
- **`fichas_publicacion`** (migración `0017`): 1:1 con `publicaciones_internas` (UK +
  CASCADE). **3 bloques** JSONB nullable — `motor_suspension`, `carroceria`, `interiores` —
  + `extras` (lista JSONB, default `[]`; ej. láminas de seguridad, llantas recién cambiadas).
  El shape lo valida Pydantic (`extra="forbid"`), no la BD → la ficha evoluciona sin migración.
- **Schemas** (`marketplace/schemas.py`): `BloqueMotorSuspension` / `BloqueCarroceria` /
  `BloqueInteriores` (todo opcional; catálogos `Literal` es-EC: combustible, transmisión,
  tracción, estado de componentes, tipo de carrocería, pintura, material de asientos +
  `observaciones` libre por bloque), `ExtraVehiculo` (nombre+detalle, máx. 20),
  `FichaActualizar` (parcial por `model_fields_set`: enviar bloque = reemplaza, `null` =
  borra, omitir = intacto), `FichaSalida` con **`completitud`** (% de campos llenos de los
  3 bloques), `PublicacionDetalleSalida` (feed + ficha). El feed agrega `completitud_ficha`.
- **Endpoints** (`routers/publicaciones.py`): `PATCH /marketplace/publicaciones/{id}/ficha`
  (dueño, upsert, gratis — la transparencia no se cobra) y
  `GET /marketplace/publicaciones/{id}` (público anónimo, solo `activa`, 404 indistinto).
  La ruta dinámica va AL FINAL del router para no capturar `mias` /
  `pendientes-verificacion` (nota en el código). `selectinload(ficha)` en feed/listados.
- Registro en `src/registry.py`.

**Verificación:** `import main` → 42 rutas OpenAPI (PATCH ficha y GET detalle presentes;
rutas literales siguen resolviendo); `Base.metadata` → 16 tablas con `fichas_publicacion`;
`alembic heads` → `0017`; pruebas de schema: payload típico OK, catálogo inválido → 422,
campo con typo → 422 (`extra="forbid"`), completitud parcial calcula bien.

**Revisión de calidad (compuerta M0, agente revisor-calidad):** APTO PARA COMMIT. Sin
bloqueantes. Confirmado: contrato de errores (404 indistinto, ficha gratis sin 402, sin 500),
orden de rutas dinámicas al final, `selectinload(ficha)` sin N+1, migración manual con
`downgrade` + modelo en `registry.py`, privacidad (sin VIN/dueño en el detalle), es-EC no
agresivo, sin deps nuevas. Verificación mínima verde (`import main`, `alembic heads` único
`0017`, schemas rechazan typo/catálogo inválido). Head del código `0017`; **BD Neon aún en
`0016`** (0017 sin aplicar).

**Pendientes**
- **`alembic upgrade head` contra Neon** (verificado: la BD está en `0016`, la migración `0017`
  NO se ha aplicado). Es el paso que cierra la compuerta M0; lo corre Marcos.
- Hallazgos menores del revisor (cosméticos, no bloquean): índice `ix_fichas_publicacion_publicacion_id`
  redundante con la UK (limpiar en futura migración); `PATCH .../ficha` con cuerpo `{}` crea ficha
  vacía → `completitud_ficha` pasa de `null` a `0` (definir en frontend si se pintan distinto).
- Frontend (`consulta-placas-web`): página de detalle de publicación + formulario por
  bloques con barra de completitud; feed muestra `completitud_ficha`.
- Siguientes del market: fotos de la publicación, búsqueda/filtros del feed, cuentas de
  patio (multi-vehículo), contacto comprador-vendedor.

---

## 2026-06-01 — POC proveedor real (`consultas_ec`) + fix de precios en la home

**Rama:** `main`. Integración HTTP real de **un** proveedor para medir costo/cobertura/latencia/
margen, sin activar nada en prod todavía.

- **`providers/consultas_ec.py`**: llamada HTTP real (httpx async, timeout configurable) + mapeo
  **defensivo** al contrato (`_mapear`, nombres es/en, datos anidados). Tolerante a fallos
  (red/HTTP≠200/no-JSON → `estado=error`, nunca lanza). Sin `CONSULTAS_EC_API_KEY`+`BASE_URL` →
  `sin_credenciales`, capacidades vacío (no ofrece ni cobra). Verificado.
- **Costo en `costos_proveedor_consulta`**: `services/proveedor.registrar_costos_proveedor`
  (upsert por producto+proveedor) se llama al cachear un resultado OK con costo.
- **Harness `scripts/evaluar_proveedor.py`**: corre 50–100 placas contra el proveedor activo y
  mide % éxito, latencia (prom/min/max/p95), cobertura de campos, costo y errores. Secuencial
  (`--delay`), `--placas archivo`, `--json`. **Dry-run con mock (60 placas): 100% éxito, cobertura
  total salvo `valores_pendientes`** → valida el harness y el flujo end-to-end.
- **Doc `docs/producto/evaluacion_proveedor_real.md`**: metodología, config, resultados (mock +
  plantilla real PENDIENTE), margen (1 llamada ≈ $0.08 alimenta identificadores+titular; bundle
  margen ~$1.52) y criterio de activación (≥70% éxito, p95 ≤3s, cobertura ≥60%, margen positivo).
- **`.env.example`**: `CONSULTAS_EC_BASE_URL`, `CONSULTAS_EC_COSTO_USD`.
- **Frontend home (`page.tsx`)**: la sección "Planes simples" mostraba el modelo viejo de
  suscripción (Gratis 5 consultas/mes, **Pro $4.99/mes**) que contradecía el modelo por tokens.
  Reescrita a "Precios claros": **Gratis** (datos públicos) + **Datos por tokens** ($0.04,
  desde $1=25), alineada con `/precios`.

**Verificación:** `scripts/validar_desbloqueos` OK; `consultas_ec` sin credenciales degrada limpio;
imports `main`/proveedor OK; harness dry-run mock OK; frontend `tsc --noEmit` OK.

**Pendiente (criterio de salida del POC):** cargar `CONSULTAS_EC_API_KEY` + `BASE_URL`, confirmar
el contrato real (ajustar `_mapear` si difiere), correr el harness con placas reales y decidir
activar o no según §8 del doc. No se agregó migración.

---

## 2026-06-01 — Fase 3: experiencia progresiva de desbloqueo + capa de proveedores

**Rama:** `main`. Preview gratis → desbloqueo de bloques por tokens, con una capa de proveedores
externos lista (sin credenciales reales todavía) y el frontend con tarjetas de desbloqueo.

### Backend — capa de proveedores (`src/modules/consulta/providers/`)
- **Contrato normalizado** `base.ResultadoVehicular` (placa, marca, modelo, anio, color, tipo,
  clase, servicio, chasis, motor, vin, titular, multas, valores_pendientes, proveedor,
  costo_estimado_usd, estado, raw_response) + interfaz `ProveedorVehicular` (capacidades + `consultar`).
- **`mock_provider.py`** funcional: datos deterministas por placa (VIN 17 chars, titular, etc.);
  capacidades `{identificadores_tecnicos, titular_validado}`. Default `PROVEEDOR_VEHICULAR_ACTIVO=mock`.
- **Stubs reales** `consultas_ec.py` / `placaapi_ec.py` / `webservices_ec.py`: leen su API key;
  sin credencial → `capacidades` vacío y `sin_credenciales` (no ofrecen ni cobran). Llamada HTTP = TODO.
- **`selector.py`**: proveedor activo por env var (memoizado). NO scraping, NO captcha.
- **Puente `services/proveedor.py`**: `capacidades_proveedor()` (sin llamar), `leer_proveedor_cacheado()`
  y `asegurar_datos_proveedor()` (llama SOLO si no hay caché; cachea en `consultas` fuente `PROVEEDOR`).
  Cumple "no llamar al proveedor en la consulta gratis" y "no re-llamar si está en caché".

### Backend — perfil adaptado (consolidador + schemas)
- Nuevo schema `Titular` (bloqueado/disponible/validado/nombre_ofuscado/mensaje) + `ofuscar_nombre`
  en `core/ofuscacion.py`. **Nunca** se expone el nombre crudo: solo validación + iniciales.
- `consolidar_placa` recibe `proveedor_datos` (cacheado) y `proveedor_capacidades`: llena VIN/motor/
  chasis y el titular desde el proveedor; `disponible` se calcula por capacidad (sin llamar).
  VIN/motor/chasis/titular siguen ofuscados si el bloque no está desbloqueado (regla #6).
- `routers/consulta.py` (perfil) y `routers/desbloqueos.py` pasan proveedor (solo caché en el preview).
  Al desbloquear un producto-proveedor (`identificadores_tecnicos`/`titular_validado` o el bundle),
  se invoca al proveedor, se cobra **solo si entrega el dato** (409 si no), y se audita proveedor+costo.
- `.env.example`: `PROVEEDOR_VEHICULAR_ACTIVO=mock`, `CONSULTAS_EC_API_KEY`, `PLACAAPI_EC_API_KEY`,
  `WEBSERVICES_EC_API_KEY`.

### Frontend (`consulta-placas-web`)
- Componentes nuevos: `TokenBadge` (costo en tokens + USD ref.), `UnlockCard` (flujo completo:
  login / 402→CTA recargar / 409 / éxito sin recargar / idempotente), `ProductoConsultaCard`
  (preview seguro por código), `ReporteCompraSeguraCard` (bundle).
- `PerfilVehiculo`: sección **"Completa tu revisión del vehículo"** con las tarjetas bloqueadas;
  los datos revelados van a sus tarjetas dedicadas (Identificación, **Titular**, Multas). Se quitó
  el botón inline anterior. Copy es-EC, sin lenguaje agresivo ("Desbloquea solo lo que necesitas").
- `types/api.ts` (+`Titular`, `titular`), `consultar/[placa]` sin cambios de fetch.

**Verificación:** `python -m scripts.validar_desbloqueos` OK (catálogo + gateo + capa mock:
identificadores/titular disponibles por capacidad; titular SIEMPRE ofuscado, nunca crudo);
imports de `main`/routers/proveedor OK; **frontend `tsc --noEmit` OK** (lint: 4 errores
pre-existentes en Header/mis-publicaciones, no en archivos nuevos).

**Pendiente:** integrar un proveedor real (implementar la llamada HTTP en su stub + cargar API key);
SRI/Fiscalía siguen como enlace oficial (sin proveedor confiable / PII). No se agregó migración.

---

## 2026-05-31 — Reajuste comercial del catálogo (Fase 2.5): solo se cobra por valor real

**Rama:** `main`. No se debe cobrar con tokens **datos públicos simples** (clase, servicio,
marca, modelo, año, color, estado de matrícula) que ya vienen de fuentes públicas. Solo se
cobra por datos con **costo de proveedor externo, dificultad real o valor comercial relevante**.

- **Valor del token:** USD 0.05 → **USD 0.04**. `precio_referencial_usd = tokens × 0.04`.
- **Migración 0016** (manual): desactiva `vehiculo_basico`/`vehiculo_tecnico` (`activo=false`);
  renombra `vehiculo_identificadores`→`identificadores_tecnicos` (3t),
  `vehiculo_titular_validado`→`titular_validado` (5t), `vehiculo_multas`→`multas_con_montos`
  (10t); reprecia `reporte_compra_segura` 30→40t y `verificacion_marketplace` 80→100t; siembra
  `consulta_publica_base` (0t), `valores_matricula_sri` (12t) y `alertas_legales` (8t); migra los
  `desbloqueos_consulta` existentes al nuevo código (datos de prueba). Reversible.
- **Seed** (`catalogo_productos.py`): nuevo catálogo de 8 productos + `BUNDLE_INCLUYE` ampliado.
- **Consolidador**: ya **no gatea** `datos_basicos` (ficha pública gratis); identificadores →
  `identificadores_tecnicos`, multas → `multas_con_montos`. `titular_validado`,
  `valores_matricula_sri` y `alertas_legales` salen `disponible=false` (enlace oficial / sin
  proveedor confiable). Alias `POST .../desbloquear` → `identificadores_tecnicos`.
- **Marketplace**: `TOKENS_VERIFICACION_MARKETPLACE` default 80 → 100 (alineado al catálogo).
- **Copy es-EC (tuteo)**: "Validar titular registrado", "Ver identificadores técnicos", "Ver
  multas con valores", "Ver valores de matrícula (SRI)", "Ver alertas legales", "Generar reporte
  compra segura". Sin "paga para ver el dueño".
- **Regla técnica documentada**: la consulta gratuita no llama a proveedores externos; el
  proveedor se invoca solo al desbloquear un producto pagado y su respuesta se cachea; si otro
  producto usa un dato ya cacheado, no se vuelve a llamar.
- **Docs**: `catalogo_productos_consulta.md`, `reglas_monetizacion_tokens.md` (+ paquetes de
  recarga: $1→25t, $2.50→65t, $5→135t, $10→280t), `modelo_tokens_microdesbloqueos.md` (§9),
  `politica_datos_sensibles.md`, AGENTS.md §10.3.

**Verificación:** `python -m scripts.validar_desbloqueos` OK (8 productos, 1 token=USD0.04,
ficha pública gratis, multas gateadas); imports de routers/consolidador/marketplace/registry OK;
`alembic history` encadena `0015 → 0016 (head)`.

**Frontend alineado** (repo `consulta-placas-web`, commit `ac418ed`): página de precios reescrita
al modelo por tokens (1 token = USD 0.04; paquetes $1=25/$2.50=65/$5=135/$10=280); la ficha
pública ya no se pinta con candado (gratis); `PerfilVehiculo` usa los códigos nuevos
(`multas_con_montos`, `identificadores_tecnicos`) y el botón muestra el nombre-acción del
producto; copy corregido ("Conoce"; no se promete SRI/Fiscalía automáticos, frase de enlaces
oficiales). No se rediseñó el marketplace.

**Pendiente:** integrar proveedores reales para activar `titular_validado`/
`valores_matricula_sri`/`alertas_legales` (hoy enlace oficial). Iniciar **Fase 3** sin
inconsistencias comerciales/visuales.

---

## 2026-05-31 — Microdesbloqueos v2: catálogo en BD + auditoría comercial (backend)

**Rama:** `main`. Evolución del v1 (catálogo en código + tabla `desbloqueos`) al v2 pedido.

- **Migración 0015** (manual): crea `productos_consulta` (catálogo: codigo, nombre, tokens,
  `precio_referencial_usd`, sensibilidad, activo, orden), `desbloqueos_consulta` (auditoría:
  tokens_cobrados, precio_referencial_usd, proveedor_usado, costo_estimado_usd,
  resultado_cache_id; UK usuario+placa+producto) y `costos_proveedor_consulta`. **Dropea**
  `desbloqueos` (v1, solo prueba). **Siembra** el catálogo idempotente (ON CONFLICT DO NOTHING).
- **Modelos** `ProductoConsulta` / `DesbloqueoConsulta` / `CostoProveedorConsulta` (reemplazan
  `Desbloqueo`); registrados en `registry.py`.
- **Catálogo en BD** como fuente de verdad; `catalogo_productos.py` queda como definición-semilla
  (`SEED_PRODUCTOS` + `BUNDLE_INCLUYE`). `services/desbloqueos.inicializar_catalogo` siembra
  idempotente; `catalogo_activo`, `obtener_producto`, `productos_desbloqueados`,
  `listar_desbloqueos`, `desbloquear` (débito atómico, idempotente, expande bundle).
- **Consolidador** ahora recibe `catalogo` (filas BD) para armar `productos`; el gateo de
  secciones no cambia.
- **Router dedicado** `routers/desbloqueos.py`: `GET /consultar/{placa}/productos`,
  `POST /consultar/{placa}/desbloquear/{producto_codigo}` (400/422-inactivo/409/402, idempotente),
  alias `POST .../desbloquear`, `GET /consultar/{placa}/desbloqueos`. Montado en `main.py`. Los
  endpoints de desbloqueo salieron de `consulta.py` (el perfil sigue ahí, ahora pasa el catálogo).
- **Schemas**: `ProductoConsultaCreate/Response`, `DesbloqueoConsultaRequest/Response`,
  `EstadoProductosPlacaResponse` (+ `precio_referencial_usd` en `ProductoEstado`).
- **Script de validación** `scripts/validar_desbloqueos.py` (sin BD): catálogo (7 productos,
  1 token=USD0.05) + gateo teaser/unlock.

**Compat:** el frontend desplegado NO cambia — mismos paths (`/desbloquear/{codigo}` y alias),
el perfil mantiene `productos`; los GET nuevos son aditivos.

**Verificación:** `configure_mappers` + carga app OK; 4 rutas presentes; migración 0015 renderiza
(3 tablas + drop + seed ON CONFLICT); `scripts/validar_desbloqueos` pasa.

**Pendientes:** proveedor externo para `titular_validado`/`tecnico` (siguen `disponible=false`);
poblar `costos_proveedor_consulta` cuando exista proveedor; UI para `GET /desbloqueos` (historial).

---

## 2026-05-31 — Cierre de pendientes: verificación 80 tokens + saldo en header + seam proveedor

**Rama:** `main`.

- **Verificación marketplace reconciliada (decisión #2):** se separó *destacar* de *verificar*.
  Publicar premium = 3 tokens (solo destaca, nace `no_verificado`). Nuevo endpoint
  `POST /marketplace/publicaciones/{id}/solicitar-verificacion` (dueño): cobra
  `TOKENS_VERIFICACION_MARKETPLACE`=**80** (402 si falta), deja `pendiente` → cola admin.
  422 si la publicación es light; idempotente si ya está pendiente/verificada. `crear_publicacion`
  y `actualizar_publicacion` ya NO ponen `pendiente` automáticamente.
- **Frontend:** `solicitarVerificacion(id)` + nueva pantalla `/marketplace/mis-publicaciones`
  (lista del dueño con estado de verificación y botón "Solicitar verificación · 80 tokens",
  maneja 402/422) + enlace desde el marketplace. **Saldo de tokens** (🪙 N) visible en el Header.
- **Proveedor titular/técnico (decisión #3):** BLOQUEADO por dependencia externa (no hay proveedor
  autorizado). `vehiculo_titular_validado` y `vehiculo_tecnico` siguen `disponible=false` (no
  cobran). Documentado el punto de integración (`services/proveedor_<x>.py` → poblar en el
  consolidador) para activarlos sin tocar el cobro. NO se hace scraping de padrones.
- **Snapshot** regenerado.

**Verificación:** rutas backend cargan (incluye solicitar-verificacion); `tsc`+`next build` ok.
Sin migración nueva (usa `estado_verificacion`/`verificado_en` existentes).

---

## 2026-05-31 — Microdesbloqueos por tokens (implementación backend + frontend)

**Rama:** `main`.

**Backend**
- Modelo `Desbloqueo` (`src/modules/consulta/models/desbloqueo.py`) + migración **0014**
  (tabla `desbloqueos`, UK usuario+placa+producto; guarda qué se compró, no el dato).
- `services/catalogo_productos.py`: catálogo en código (precios/descripciones/bundle).
- `services/desbloqueos.py`: `productos_desbloqueados`, `desbloquear_producto` (débito atómico
  idempotente, expande bundle), `estado_catalogo`.
- `consolidador.consolidar_placa(placa, resultados, productos_desbloqueados)`: gatea secciones;
  teaser gratis = marca/modelo/año/color + matrícula vigente + veredicto `tiene_pendientes`.
- `auth.dependencies.usuario_actual_opcional` (auth opcional, no 401).
- Endpoints: `GET /consultar/{placa}/perfil` (auth opcional, gateado), `POST
  /consultar/{placa}/desbloquear/{producto}` (400/409/402), y el viejo `/desbloquear` queda
  como **alias** de `vehiculo_identificadores`.

**Frontend**
- Tipos `ProductoEstado`, `DatosBasicos.{matricula_vigente,bloqueado}`, `VehiculoConsolidado.
  {multas_bloqueado,productos,tiene_pendientes}`.
- `consultarPerfil` envía el token si hay sesión (auth opcional) → revela lo ya pagado;
  `desbloquearProducto(placa,codigo)`.
- `PerfilVehiculo`: veredicto desde el backend; `BotonDesbloqueo` (🔓 N tokens, maneja 401/402/409)
  en Datos/ Multas/ Identificación; re-fetch con token al montar.

**Decisiones aplicadas (defaults del plan):** teaser mínimo; `verificacion_marketplace` no se
cablea a la consulta; `tecnico`/`titular_validado` sin fuente → `disponible=false`; bundle no
descuenta lo ya pagado; **402** si falta saldo; **no cobrar** si el dato no está disponible.

**Verificación:** `configure_mappers` + carga de app OK; gateo probado con datos simulados
(teaser oculta clase/multas/VIN, unlock revela); migración 0014 renderiza; `tsc`+`next build` ok.

**Pendientes:** proveedor para `titular_validado`/`tecnico`; reconciliar precio de
`verificacion_marketplace` (80) con el premium=3 actual; mostrar saldo de tokens en el header;
regenerar `proyecto-snapshot.md`.

---

## 2026-05-31 — PLAN: modelo de microdesbloqueos por tokens (solo documentación)

**Rama:** `main` (commit local, **sin push** — no se toca producción todavía).

**Qué se hizo:** planificación y documentación de producto para pasar del desbloqueo
**monolítico** actual (`POST /consultar/{placa}/desbloquear`, revela todos los identificadores
por 1 token) a **microdesbloqueos progresivos**: consulta inicial gratuita (teaser) + productos
pequeños desbloqueables con tokens. Se crearon 4 docs en `docs/producto/`:
`modelo_tokens_microdesbloqueos.md`, `catalogo_productos_consulta.md`,
`reglas_monetizacion_tokens.md`, `politica_datos_sensibles.md`.

**Decisiones tomadas:**
- **1 token = USD 0.05** (referencial). Saldo inicial de cortesía sigue en 5 tokens.
- **Catálogo inicial** (códigos en español, estables como clave de `desbloqueos`):
  `vehiculo_basico` 3 · `vehiculo_tecnico` 2 · `vehiculo_identificadores` 3 ·
  `vehiculo_titular_validado` 5 · `vehiculo_multas` 8 · `reporte_compra_segura` 30 (bundle) ·
  `verificacion_marketplace` 80.
- **Titular = dato sensible (PII):** se maneja **ofuscado o validado** (coincide/no coincide),
  nunca crudo a terceros; valor completo solo al dueño autenticado. Fuente: proveedor autorizado.
- **No cobrar si no hay dato** entregado; **402** si falta saldo; **idempotencia** vía tabla
  `desbloqueos` (UK usuario+placa+producto): no se recobra lo ya comprado.
- **Sin evasión de captcha / anti-bot**: datos vía fuentes ya obtenidas + caché + proveedores
  autorizados + enlaces oficiales asistidos (SRI). El token cobra el acceso, no el bypass.
- El catálogo de productos vive en **código** (`services/catalogo_productos.py`), no en BD
  (precios versionados sin migración); solo `desbloqueos` es tabla nueva (migración 0014, manual).

**Decisiones abiertas (a confirmar antes de implementar):** alcance exacto del teaser gratis;
reconciliar `verificacion_marketplace` (80) con el flujo admin ya construido (premium=3 hoy);
proveedor del titular validado; si el bundle descuenta lo ya pagado.

**Verificación:** sin cambios de código ejecutable; solo documentación. `proyecto-snapshot.md`
sigue vigente (regenerado el 2026-05-31).

**Pendientes / siguiente etapa:** ver "Plan de archivos" en `modelo_tokens_microdesbloqueos.md`
(modelo `Desbloqueo` + migración 0014, `catalogo_productos.py`, `desbloqueos.py`, endpoints
`/productos` y `/desbloquear/{producto}`, gating del consolidador, UI con `BotonDesbloqueo`).

---

## 2026-05-31 — Verificación premium del marketplace (flujo admin completo)

**Rama:** `main`.

**Backend**
- `models.py`: `EstadoVerificacion` suma el valor terminal **`rechazado`** (columna String, sin migración). Nueva columna **`verificado_en`** (timestamp, nullable) en `publicaciones_internas` para auditar cuándo se selló → **migración 0013** (manual, revisada a mano).
- `schemas.py`: `PublicacionInternaSalida` expone `verificado_en`; nuevo `VerificacionPublicacion` (body `decision`, solo `verificado`/`rechazado`, validación de estado terminal).
- `routers/publicaciones.py` (espeja la moderación de referencias):
  - `GET /marketplace/publicaciones/pendientes-verificacion` — cola de premium `pendiente`, más antiguas primero (solo `admin_actual`).
  - `POST /marketplace/publicaciones/{id}/verificar` — marca `verificado` (sella + `verificado_en=now`) o `rechazado` (quita sello). 404 si no existe; **422 si no es premium**.

**Frontend**
- `types/api.ts`: `EstadoVerificacion` suma `rechazado`; `PublicacionInterna` suma `verificado_en`.
- `lib/api.ts`: `listarPublicacionesPendientesVerificacion()` y `verificarPublicacion(id, decision)`.
- Nueva pantalla **`/admin/verificaciones`** (mismo molde que `/admin/moderacion`): cola de premium pendientes con su argumento (mantenimientos) + botones Verificar/Rechazar. Acceso admin en el Header ("Verificar").
- El sello "Verificado por la plataforma" ya vivía en `ListingCard` (se muestra solo con `verificado`).

**Verificación:** `configure_mappers` + carga de `app` OK; rutas nuevas presentes; migración 0013 renderiza el `ADD COLUMN verificado_en`; `tsc` + `next build` del frontend en verde.

**Pendientes:** definir si el sello debe condicionar el orden/box del feed premium; notificar al dueño cuando su premium queda verificada/rechazada (hoy no hay notificaciones).

---

## 2026-05-29 — Integración de las 3 fuentes restantes + rebranding "Revisa tu Carro EC" + rediseño claro

**Rama:** `main`. Continuación del pivote a Perfil Consolidado.

**Backend — `estado_fuentes` catálogo-driven + 3 fuentes nuevas (una por una, con descubrimiento §14)**
- `consolidador.py`: `consolidar_placa(placa, resultados: dict[str,dict])` arma `estado_fuentes`
  recorriendo `CATALOGO_FUENTES` (implementadas = estado vivo; resto = `no_integrada`). Sumar
  fuente = catálogo + scraper + ruteo, sin tocar el consolidador. `_obtener_fuentes_placa` ahora
  devuelve dict keyed por clave.
- **EPMTSD** (oficial, multas): descubrimiento reveló que su portal corre sobre la **misma
  plataforma AxisCloud que AMT** (`ps_empresa=06` vs `03`). Se extrajo el adaptador compartido
  `services/_axiscloud.py` (flujo Playwright + parser de infracciones); `amt.py` y `epmtsd.py`
  quedaron como wrappers delgados. Vía worker híbrido (mismo gotcha de IP datacenter que AMT).
  Verificado en vivo (`consulta_realizada`); AMT re-verificado sin regresión.
- **ConsultasEcuador** (no oficial, chasis/motor): descubrimiento mostró que es página de
  afiliado (widget Bumper) tras **reCAPTCHA** — no scrapeable. Se integró como `consulta_externa`
  (enlace + disclaimer no oficial), sin scraping. Mismo criterio que SRI.
- **EcuadorLegalOnline** (no oficial): sitio de guías con ad-gate/reCAPTCHA y dato de propietario
  de pago (PII). También `consulta_externa` (enlace + disclaimer). Las 7 fuentes quedan
  `implementada=True`.
- Reintento (`FUENTES_WORKER`) ahora incluye EPMTSD; `worker.py CONSULTORES` también.

**Frontend (repo consulta-placas-web)**
- `PerfilVehiculo.tsx`: sección **Identificación** (chasis/motor ofuscados + enlace externo de
  ConsultasEcuador), marcadores **ⓘ no oficial** + disclaimer por ítem, chips del tablero
  clicables cuando son `consulta_externa`.
- **Rebranding** a **"Revisa tu Carro EC"** (antes ConsultaPlacas): nombre evita la ambigüedad de
  "seguro" (póliza); monograma RC. Aplicado en layout/Header/Footer/metadata y páginas.
- **Rediseño visual "Confianza clara"**: de tema oscuro neón (violeta-rosa-ámbar) a **tema claro**
  (fondo #f6f8fc), gradiente de marca **azul→cian**, estados verde/ámbar/rojo, sombras suaves.
  Decidido con el usuario: base clara + azul confianza, prioridad "atracción/que enganche".
  Convertidas TODAS las pantallas (landing, consulta, resultado, login, registro, precios,
  mi-garage, header, footer, inputs). `tsc` + `eslint` limpios; sin tokens `zinc-` restantes.

**Pendiente**
- **Imágenes referenciales del vehículo**: discutido (no hay foto del auto real por placa; opción
  recomendada: híbrido render-por-modelo + ilustración por clase, con sello "referencial").
  Pospuesto por decisión del usuario.
- Licencia de CDN de imágenes si se va por render (imagin.studio u otro).
- Deploy: el frontend en Vercel apunta a prod (Render), que necesita el deploy con los nuevos
  endpoints (`/perfil`, fuentes) antes de que el front los consuma.

---

## 2026-05-29 — Pivote a "Perfil Consolidado de Vehículo" (catálogo + schema + endpoint + frontend)

**Rama:** `main`. Plan de 3 pasos (catálogo → schema consolidado → frontend) + avance del
endpoint consolidado.

**Qué se hizo**
- **Paso 1 — Catálogo de fuentes:** nuevo `src/modules/consulta/services/catalogo_fuentes.py`,
  capa **estática** (no toca scraping). Enums `Prioridad`/`Origen`/`CategoriaDato`, dataclass
  `FuenteCatalogo` y `CATALOGO_FUENTES` con 7 fuentes (ANT, SRI, AMT, FGE oficiales/implementadas;
  EPMTSD, ConsultasEcuador, EcuadorLegalOnline pendientes). Helpers `fuentes_por_categoria`,
  `fuentes_implementadas`.
- **Paso 2 — Schema consolidado:** nuevo `src/modules/consulta/schemas.py` con
  `VehiculoConsolidadoResponse` (secciones `datos_basicos`, `identificacion` ofuscada,
  `valores_tributarios`, `multas_pendientes`, `novedades_legales`) + bloque `estado_fuentes`
  (enum `EstadoFuente` + `desde_estado_servicio`). Listas con `default_factory` para no romper
  con fuentes `en_proceso`.
- **Avance — agregación server-side:** nuevo `services/consolidador.py` (`consolidar_placa`) que
  mapea los dicts crudos por-fuente → `VehiculoConsolidadoResponse`. Router refactorizado: helper
  compartido `_obtener_fuentes_placa` y nuevo endpoint **`GET /consultar/{placa}/perfil`**
  (`response_model=VehiculoConsolidadoResponse`). El endpoint legacy `/consultar/{placa}` (vista
  por fuente) se conserva.
- **Paso 3 — Frontend (repo consulta-placas-web):** nuevo `PerfilVehiculo.tsx` orientado a la
  entidad (tarjeta del auto + secciones Valores/Multas/Legal, skeletons mientras AMT/FGE cargan,
  tablero de chips de fuentes con ⓘ para no oficiales). Migrado a consumir `/perfil` directo:
  `consultarPerfil` en `api.ts`, `page.tsx` fetchea el endpoint consolidado, `consolidar.ts`
  reducido a helpers de lectura (`hayFuentesEnProceso`, `estadoDeFuente`, `marcarFuenteEnProceso`).
  Eliminado `ResultadoConsulta.tsx` (huérfano).

**code-review (high) — 2 bugs corregidos**
- Infracciones AMT **pagadas/anuladas** se contaban como pendientes (se volcaba todo `categorias`);
  corregido a un ítem basado en `infracciones.pendientes` + `total_a_pagar`.
- Tarjeta principal daba veredicto "Sin pendientes" prematuro mientras AMT/FGE cargaban; ahora
  muestra estado neutral "Consultando…" si hay fuentes `en_proceso`.

**Verificación**
- Backend: `import main` registra `/consultar/{placa}/perfil`; `consolidar_placa` produce el JSON
  esperado con fuentes mixtas (completada/consulta_externa/en_proceso/error_fuente).
- Frontend: `tsc --noEmit` y `eslint` en verde.

**Pendientes**
- `identificacion` (chasis/motor) queda preparada pero vacía hasta integrar fuentes no oficiales
  (ConsultasEcuador) — recién ahí se cablea ofuscación en la vista.
- El gateo de secciones por scope del token de compra-venta sigue pendiente (heredado Fase 4).

---

## 2026-05-29 — Resiliencia worker (`error_fuente`) + caché de doble velocidad

**Rama:** `main`. Instrucciones del round-trip a Gemini (Instrucción 1 y 2; la 3 es del
frontend, fuera de este repo).

**Instrucción 1 — límite de reintentos + estado `error_fuente` (✅).** Hallazgo: la cola
**ya** cortaba en `fallido` tras `max_intentos`; el bucle real era **del cliente** (al fallar,
cache miss → re-encola en cada poll → reintento infinito). Solución en dos piezas:
- *Worker/cola*: estado terminal renombrado `fallido` → **`error_fuente`** (más claro para el
  frontend); tope subido a **4** intentos (`MAX_INTENTOS_DEFAULT`, fijado en `encolar_scraping`).
  Sin migración (ni `cola_scraping.estado` ni `consultas.estado` tienen CHECK).
- *API*: `consultar_via_worker` lee la cola (`fuente_en_error_reciente`) en cache miss; si el
  último trabajo quedó `error_fuente` dentro de una **ventana de enfriamiento (12h)**, devuelve
  `estado: error_fuente` (+`error`) **sin re-encolar**. El cliente deja de pollear.
- *Reintento manual*: `POST /consultar/{identificador}/reintentar/{fuente}` (AMT/FGE) reencola
  saltándose el enfriamiento. Resumen de `/consultar` y `/consultar-judicial` agregan
  `amt_error_fuente` / `fge_error_fuente`.

**Instrucción 2 — caché de doble velocidad (✅, ajustada al AS-IS).** `cache.py` define TTL por
naturaleza: transaccional **12h** (`CACHE_TTL_TRANSACCIONAL_MINUTOS`) y estático **90 días**
(`CACHE_TTL_ESTATICO_MINUTOS`). Decisión del usuario: *"la que mejor se ajuste al AS-IS y dé
espacio para el TO-BE"* → **TTL por fuente** (`ttl_para_fuente`): ANT/AMT/FGE = 12h. Como hoy
cada fuente es un solo blob y **ANT mezcla** características (estático) + citaciones
(transaccional), gana la frescura (12h). El TTL de 90 días queda **cableado y reservado** para
cuando, con clientes reales (TO-BE), el perfil del vehículo se cachee como entrada propia.
`obtener_consulta_reciente` ahora deriva el TTL de la fuente; el router dejó de pasar
`CACHE_TTL_MINUTOS` fijo.

**Doc:** AGENTS.md §6 (+estado `error_fuente`) y §8 (TTL doble); skill respuesta-api-estandar;
docs/arquitectura_hibrida.md (`fallido`→`error_fuente`, max 4); `.env.example` (+2 TTL).

**Pendiente (frontend, repo consulta-placas-web · Instrucción 3):** Skeleton + polling cada 4s
mientras `*_en_proceso`; al ver `*_error_fuente` detener polling y mostrar botón "Reintentar
conexión" → `POST /consultar/{identificador}/reintentar/{fuente}`. Tarjeta SRI con botón a
`url_consulta_sri`.

---

## 2026-05-29 — Rotación BD + gateo por scope + anti-captcha SRI (2Captcha)

**Rama:** `main` (Fase 0 ya mergeada). Cambios de esta sesión **sin commitear** al cierre.

**Paso 1 — Validar BD tras rotación de credenciales Neon (✅).** `alembic current` → `0009 (head)`
conectando con las credenciales nuevas del `.env`. Verificado solo en local; pendiente
actualizar la var en Render.

**Paso 2 — Gateo de visualización por `scope` en el enlace compartido (✅).**
- `src/modules/marketplace/schemas.py`: nuevas secciones `KilometrajeCompartido`,
  `MantenimientoCompartido`, `DuenoCompartido` y `VehiculoCompartidoSalida` (hereda de
  `VehiculoSalidaCompartida` → respuesta **retrocompatible**, agrega 3 claves opcionales).
  `desde_enlace(enlace)` lee `enlace.scope` e incluye cada sección solo si su flag es `True`;
  ordena cronológicamente. **Privacidad:** la cédula de dueños previos se ofusca aunque el
  scope habilite la sección (`171*******`).
- `src/modules/marketplace/routers/compartidos.py`: `GET /compartido/{token}` ahora responde
  `VehiculoCompartidoSalida`. No se tocó la migración `0008` ni el modelo.
- Verificado con 3 casos (scope vacío / solo kilometraje / completo).

**Paso 3 — Integración anti-captcha en SRI (proveedor 2Captcha) (⚠️ código listo, falta key + verificación live).**
- Nuevo `src/modules/consulta/services/captcha.py`: cliente 2Captcha con `httpx.AsyncClient`
  (in.php/res.php), key por `TWOCAPTCHA_API_KEY`, polling con timeout, excepciones
  `CaptchaNoConfigurado/SinSaldo/Timeout/Error`.
- `src/modules/consulta/services/sri.py`: si `hay_api_key()`, extrae el `sitekey` del DOM
  (no hardcodeado), resuelve e inyecta el token en `g-recaptcha-response` antes de enviar.
  **Gateado por la env key**: sin `TWOCAPTCHA_API_KEY` el flujo queda idéntico al previo
  (cero riesgo en prod). `.env.example` documenta la nueva var.
- **Verificación live (con key real, saldo $3):** la consulta a SRI devolvió
  `ERROR_CAPTCHA_UNSOLVABLE`. **Discovery del DOM de SRI confirmó: reCAPTCHA Enterprise v3**
  (`enterprise.js?render=...`, `grecaptcha.enterprise`, sin `data-sitekey` ni textarea),
  **sitekey `6LdukTQsAAAAAIcciM4GZq4ibeyplUhmWvlScuQE`**.
- **Implicación:** el scaffold actual (v2 + inyección de `g-recaptcha-response`) es el mecanismo
  equivocado. El rework pendiente para v3: (1) resolver con `version=v3` + `action` + `min_score`
  (el cliente `captcha.py` ya lo soporta); (2) **override de `grecaptcha.enterprise.execute`**
  vía init-script para que SRI tome el token; (3) descubrir el `action` real (se genera en JS al
  click, no está en el HTML estático). v3 enterprise es el caso más difícil; éxito no garantizado.
  La key quedó en `.env` local (gitignored), **no** en Render.

**Decisiones tomadas:** anti-captcha = **2Captcha**; worker correrá en **PC Windows + Task
Scheduler**; tarifario de tokens **se mantiene en 0** por ahora.

**Pendientes:** commitear esta sesión; fondear 2Captcha y verificar SRI live; script de
autoarranque del worker (Task Scheduler) cuando se decida desplegarlo.

### Actualización (misma sesión) — Worker desplegado + SRI: pivote a passthrough

- **Worker autoarranque (Task Scheduler):** hecho y verificado; commit `ab2b5df`. La tarea
  `ConsultaPlacasWorker` autoarranca al iniciar sesión. En la prueba el worker procesó
  **AMT/TBA3373 y FGE/TBA3373 → consulta_realizada** desde IP residencial.

- **SRI — investigación de la vía A (solver) y pivote:**
  - 2Captcha entrega token pero SRI (reCAPTCHA **Enterprise v3**, sitekey
    `6LdukTQsAAAAAIcciM4GZq4ibeyplUhmWvlScuQE`, action `matriculacion_vehicular_valores_pagar`)
    **rechaza el token** (score server-side). Probado e2e con el override de
    `grecaptcha.enterprise.execute`: token inyectado pero sin datos.
  - Comparativa de opciones con costos: A) Capsolver (~$3/1000, ~90% enterprise) + proxy
    residencial (~$1–7/GB) → barato/consulta pero **frágil**, sin garantía; B) **API oficial
    SRI** (convenio) → definitiva, $0, pero trámite; C) aceptar el vacío.
  - **Decisión:** **passthrough** (idea del usuario). SRI deja de scrapearse; `consultar_sri`
    devuelve `estado: consulta_externa` + `url_consulta` (instantáneo, sin Playwright/costo).
    El frontend mostrará un botón al portal del SRI (no se puede iframe:
    `X-Frame-Options: SAMEORIGIN`; tampoco se prefija la placa, SPA Angular).
  - El solver (vía A) queda **DORMIDO** en `_consultar_sri_scraping` + `captcha.py`
    (Capsolver + 2Captcha), reactivable. La vía **B (API oficial)** queda para después.
  - Nuevo estado de contrato **`consulta_externa`** (+ campo `url_consulta`) documentado en
    AGENTS.md §6 y el skill respuesta-api-estandar. Resumen de `/consultar` agrega
    `sri_consulta_externa` y `url_consulta_sri`.

**Pendiente frontend (repo consulta-placas-web):** tarjeta de SRI con botón que abre
`url_consulta` en pestaña nueva + placa visible para copiar.

---

## 2026-05-29 — Fase 0: mudanza a monolito modular (DDD)

**Rama:** `refactor/modulos` (no mergeada a `main` al cierre de la sesión).

**Qué se hizo**
- Reorganización del backend de "por tipo de archivo" (`routers/`, `models/`, `schemas/`,
  `services/`, `auth/`, `utils/` sueltos) a "por dominio de negocio" en `src/`:
  - `src/core/` ← `database.py`, `validators.py`, `ofuscacion.py`.
  - 5 módulos en `src/modules/`: `auth`, `tokens`, `consulta`, `vehiculos`, `marketplace`.
  - `src/registry.py` ← registro único de modelos para `Base.metadata` (lo importa Alembic).
- Endpoints públicos extraídos de `main.py` → `src/modules/consulta/routers/consulta.py`.
  `main.py` quedó limpio (solo `app` + CORS + `include_router`).
- Entrypoints (`main.py`, `run.py`, `worker.py`, `scripts/discover.py`) se mantienen en la raíz.
- Toda la mudanza con `git mv` (historial preservado). **Cero cambios de lógica**; solo imports
  y la extracción literal de endpoints. `alembic/versions/*` intactas; `env.py` solo cambió 2
  imports. BD de Neon no se tocó.
- Documentación: `CLAUDE.md` → `AGENTS.md` (+ shim `CLAUDE.md` con `@AGENTS.md` para auto-load);
  rutas viejas actualizadas en AGENTS.md y los 6 skills; nueva §1.1 (arquitectura modular +
  mapa skill→módulo); snapshot regenerado; se crea esta bitácora.

**Verificación (compuerta superada)**
- `import main` → 35 rutas; `src.registry` → 10 tablas en `Base.metadata`; `import worker` OK.
- `alembic heads` → `0009` (env.py resuelve, sin tocar la BD).
- Server arriba: `GET /health` `{"status":"ok"}`, `/consultar/!!!`→400, `/auth/me` sin token→401,
  `/marketplace`→200 (consultó Neon real).

**Pendientes**
- Commitear y decidir el merge de `refactor/modulos` → `main`.
- Limpieza de cohesión opcional (no hecha, tocaría lógica): separar `TransaccionToken` y los
  schemas de token de `auth` hacia `tokens`.
- Continuar el roadmap: Fase 1 (sellar `auth`+`vehiculos`), 2 (worker scraping), 3 (débito real
  de tokens + ofuscación en vista compartida), 4/5 (OCR end-to-end).
- Operativo heredado: desplegar `worker.py` en IP residencial EC; verificar OCR end-to-end;
  confirmar rotación de credencial de Neon.
