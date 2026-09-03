# Consulta de datos del vehículo — fuentes, fases y sección aislada

**Fecha:** 2026-09-03 · **Estado:** análisis + plan para reactivar la consulta como
sección propia.
**Qué pide este documento:** verificar las opciones de consulta que ya teníamos, sumar un
análisis de nuevas webs para consultas **por fases** (de lo más simple a lo más completo:
n.º de dueños, temas judiciales, etc.), agruparlas y evaluarlas; y definir cómo se
presenta: una **pantalla aislada** del resto de la web, con solo un campo para la placa
que devuelve el detalle **en bloques**, gratis para lo básico y con login para lo
ampliado, más una **landing** que lleve a este servicio y otra que reparta entre
**Consultas** y **Marketplace + Servicios**.

> Relacionado: [`catalogo_fuentes.py`](../../src/modules/consulta/services/catalogo_fuentes.py)
> (catálogo maestro), [`modelo_tokens_microdesbloqueos.md`](modelo_tokens_microdesbloqueos.md),
> [`catalogo_productos_consulta.md`](catalogo_productos_consulta.md), AGENTS.md §6 y §8.

---

## 1. Lo que ya teníamos levantado

### 1.1 Pipeline

`GET /consultar/{placa}/perfil` → `VehiculoConsolidadoResponse`: agrega varias fuentes en
**secciones temáticas** (`datos_basicos`, `identificacion`, `valores_tributarios`,
`multas_pendientes` + `multas_detalle`, `novedades_legales`) + un `veredicto` **gratis**
(sí/no hay multas/valores/novedades) + `estado_fuentes` para pollear mientras AMT carga.
El frontend (`PerfilVehiculo.tsx`) solo lee y pinta: tarjeta-resumen arriba + acordeones.

- **Auth opcional** (`usuario_actual_opcional`): sin sesión, todo va en *teaser*; con
  sesión, se revelan los microdesbloqueos que el usuario ya tenía.
- **Nunca dispara scraping desde el marketplace** (§1.0.1). La consulta sí scrapea, porque
  **la pide el usuario explícitamente**.

### 1.2 Fuentes registradas (catálogo maestro)

| Clave | Institución / portal | Oficial | Aporta | Estado hoy |
|---|---|---|---|---|
| **ANT** | Agencia Nacional de Tránsito | ✅ | datos básicos (marca, modelo, año, color, clase), citaciones nacionales | **Funciona** (Playwright, local y cloud) |
| **AMT** | Ag. Metropolitana de Tránsito (Quito) | ✅ | infracciones municipales de Quito | **Funciona vía worker residencial**; bloqueada desde IP datacenter |
| **EPMTSD** | EP Tránsito Santo Domingo | ✅ | infracciones municipales STO. DGO. | **Funciona vía worker** (mismo portal AxisCloud que AMT) |
| **SRI** | Servicio de Rentas Internas | ✅ | valores de matrícula, impuestos | **Bloqueada** (reCAPTCHA Enterprise invisible). Passthrough al portal; oculta en la UI (`NEXT_PUBLIC_FUENTES_INACTIVAS`) |
| **FGE** | Fiscalía General del Estado | ✅ | noticias del delito (SIAF) | **Bloqueada** (hCaptcha desde may-2026). Passthrough; oculta en la UI |
| **ConsultasEcuador** | portal de terceros | ❌ | chasis / motor | Solo enlace + disclaimer; reCAPTCHA, es afiliado |
| **EcuadorLegalOnline** | portal de terceros | ❌ | propietario por placa (PII, de pago) | Solo enlace + disclaimer |

### 1.3 Capa de proveedores comerciales (API, sin captcha)

Abstracción `ProveedorVehicular` → `ResultadoVehicular` normalizado. Registro en
`providers/selector.py` (`PROVEEDOR_VEHICULAR_ACTIVO`):

| Proveedor | Estado | Capacidades declaradas |
|---|---|---|
| `consultas_ec` | **Integración HTTP real (POC)**, sin API key confirmada; mapeo defensivo. Es el valor correcto de `PROVEEDOR_VEHICULAR_ACTIVO` en prod (§1.0.3). | según credencial |
| `placaapi_ec` | stub con *seam*; sin contrato | `identificadores_tecnicos` |
| `webservices_ec` | stub con *seam*; sin contrato | `identificadores_tecnicos`, `titular_validado` |
| `mock` | **solo desarrollo** — nunca en prod (§1.0.3): fabrica datos y choca con la propuesta de transparencia | todas |

### 1.4 Catálogo de "microdesbloqueos" (`productos_consulta`)

| Código | Qué muestra | Tokens (BD hoy) | Sensibilidad |
|---|---|---|---|
| `consulta_publica_base` | clase, servicio, marca, modelo, año, color, estado de matrícula | **0** (gratis) | pública |
| `identificadores_tecnicos` | chasis, motor, VIN (ofuscados→claros) | 3 | media |
| `titular_validado` | ¿hay titular registrado validado? | 5 | alta |
| `alertas_legales` | alertas legales / gravámenes | 8 | alta |
| `multas_con_montos` | multas con valores | 10 | media |
| `valores_matricula_sri` | valores de matrícula (SRI) | 12 | media |
| `reporte_compra_segura` | bundle de todo lo anterior | 40 | — |
| `verificacion_marketplace` | sello de verificación de la plataforma | 100 | — |

> **Deuda que este trabajo salda (AGENTS.md §1.0.3):** los valores de token > 0 de
> `productos_consulta` quedaban dormidos "hasta que se retome el tema de la consulta por
> placa". Se retoma ahora → **migración que los pone en 0** (§5.1). Mientras dure la
> monetización suspendida, el gate real es **login**, no tokens.

---

## 2. Nuevas webs / fuentes candidatas — evaluación

Criterios: **(V)** valor del dato · **(A)** accesibilidad técnica (sin captcha, HTML/JSON
estable, IP-tolerante) · **(L)** legalidad / PII · **(C)** costo. Nota de 1–5.

| Fuente | Dato que aportaría | V | A | L | C | Veredicto |
|---|---|---|---|---|---|---|
| **ANT — Consulta de Valores a Pagar de Matrícula** (portal ANT, distinto del de citaciones) | valor de matrícula y rubros a pagar (alternativa al SRI) | 4 | 3 | 5 | 5 (gratis) | **Probar.** Si responde sin captcha desde IP residencial, cubre el hueco que dejó el SRI. Fase 2. |
| **ANT — Récord / puntos del conductor** (por cédula) | infracciones y puntos de una **persona**, no del auto | 3 | 3 | 3 (PII, requiere consentimiento del titular) | 5 | **Fase 3, con login y consentimiento explícito.** No para la vista básica. |
| **SRI — API de consultas** (convenio / clave de servicios en línea) | matrícula, impuestos, RUC del propietario | 5 | 5 (si hay convenio) | 4 | 3 (trámite administrativo, posible costo) | **Camino B del SRI (AGENTS.md §6).** Es la vía definitiva; requiere gestión institucional. Fase 3+. |
| **Registro Civil / DINARDAP** (validación de identidad del titular) | nombre del titular a partir de cédula/placa | 5 | 2 (acceso restringido, es DINARDAP) | 2 (PII fuerte, marco legal estricto) | 2 | **No sin convenio.** Alto valor pero es justamente lo que un particular no puede tocar sin base legal. Documentar como aspiracional. |
| **Función Judicial — eSATJE / SATJE** (procesos judiciales por cédula/RUC) | juicios en los que aparece una persona/empresa | 4 | 3 (hay endpoint JSON público; cambia seguido) | 3 (dato público pero es PII sensible) | 5 | **Fase 3, con login.** Es el "temas judiciales" del pedido. Útil para "compra segura". Mostrar con disclaimer y sin exponer detalles de terceros. |
| **Fiscalía — SIAF (FGE)** | noticias del delito por placa (robo, uso en delito) | 5 | 1 (hCaptcha desde may-2026) | 4 | 4 (solver ~USD 1–3/1000) | **Passthrough + botón al portal** (ya está). Reactivar scraping solo si se paga solver o hay API. |
| **Policía Nacional — vehículos reportados/robados** | ¿el auto está reportado como robado? | 5 | 2 (no hay consulta pública estable; a veces vía ANT) | 4 | 4 | **Investigar** si la ANT ya expone "señalado por robo" en su ficha (a veces sí). Si no, aspiracional. |
| **SRI — Deudas firmes / estado tributario del RUC del titular** | ¿el vendedor (si es empresa/patio) tiene deudas? | 3 | 4 (consulta pública por RUC, con captcha suave) | 4 | 5 | **Fase 3**, útil para patios (etapa 2). |
| **GADs municipales adicionales** (Cuenca EMOV, Ambato, Manta, Guayaquil ATM) | infracciones municipales de otras ciudades | 4 | 3 (varios usan AxisCloud como AMT/EPMTSD; otros portales propios) | 5 | 5 | **Fase 2, incremental.** EMOV Cuenca y ATM Guayaquil son los siguientes por volumen. Reusan el patrón del worker. |
| **Aseguradoras / peritajes (histórico de siniestros)** | ¿el auto tuvo pérdida total / siniestros? | 5 | 1 (no hay fuente pública; sería convenio con aseguradoras) | 3 | 1 | **Aspiracional.** Es el santo grial del "CARFAX ecuatoriano"; no existe fuente abierta. |
| **Portales de terceros** (Patente.ec, ConsultasEcuador, EcuadorLegalOnline, etc.) | agregadores de lo anterior | 2 | 2 (captcha, afiliados, datos revendidos) | 2 | 3 | **No scrapear.** Solo enlace + disclaimer "no oficial", como ya se hace. |

### 2.1 Lo que sí mueve la aguja a corto plazo

1. **ANT "valores de matrícula"** — si funciona, tapa el hueco del SRI en la vista básica.
2. **Más GADs municipales** (EMOV Cuenca, ATM Guayaquil) — mismo patrón de worker, más
   cobertura de multas.
3. **Función Judicial (eSATJE)** — habilita el bloque "temas judiciales" con login.

Lo demás (Registro Civil, aseguradoras, Policía) necesita **convenio institucional** y es
de etapa 2+.

---

## 3. Agrupación en fases (de lo simple a lo completo)

La consulta se presenta en **bloques**, y cada bloque tiene un **nivel de acceso**:

### Fase 1 — Básico · GRATIS · sin cuenta

*"¿Qué es este auto y está al día?"*

| Bloque | Dato | Fuente |
|---|---|---|
| **Identificación** | marca, modelo, año, color, clase, tipo de servicio | ANT |
| **Matrícula** | estado de matriculación, ciudad de matrícula, fecha de caducidad | ANT (+ ANT valores si se habilita) |
| **Veredicto rápido** | "tiene multas: sí/no", "tiene valores por pagar: sí/no", "novedades legales: sí/no" — **sin montos ni detalle** | ANT + AMT/EPMTSD (caché) |

Esto se responde solo con la placa. Es lo que ve cualquiera.

### Fase 2 — Ampliado · GRATIS con cuenta (login)

*"Muéstrame el detalle."*

| Bloque | Dato | Fuente |
|---|---|---|
| **Multas con detalle** | cada citación/infracción con fecha, artículo, monto, estado | ANT + AMT + EPMTSD (+ más GADs, incremental) |
| **Valores de matrícula** | rubros a pagar, total | ANT valores / SRI (cuando haya vía) |
| **Identificadores técnicos** | chasis, motor, VIN — **ofuscados salvo al dueño** (§7 AGENTS) | proveedor API (`consultas_ec`) |
| **Historial de propietarios (n.º de dueños)** | cuántas transferencias registra el vehículo | proveedor API / ANT (según disponibilidad) |

El login es la barrera: sirve para atribuir uso, aplicar límites y —cuando vuelva la
monetización— reactivar el cobro sin rediseñar. **Hoy no cuesta tokens** (§5.1).

### Fase 3 — Compra segura · con cuenta + consentimiento

*"Voy a comprarlo, dame todo."*

| Bloque | Dato | Fuente | Nota |
|---|---|---|---|
| **Titular registrado** | ¿hay un titular validado? (sí/no, sin exponer el nombre a terceros) | proveedor / DINARDAP (aspiracional) | PII |
| **Temas judiciales** | procesos en los que aparece el titular (cédula/RUC) | Función Judicial eSATJE | PII sensible; disclaimer; sin datos de terceros |
| **Alertas legales / gravámenes** | prendas, limitaciones de dominio | proveedor / registro mercantil | PII |
| **Reporte "compra segura"** | PDF con todo lo anterior consolidado + fecha y fuentes | bundle | descargable |

Requiere que el usuario **declare que va a comprar el auto** (consentimiento del uso del
dato) y, para lo que sea PII de un tercero, mostrar solo agregados / sí-no.

---

## 4. La sección aislada — cómo se presenta

### 4.1 Aislamiento

La consulta vive en **`/verificar`**, una superficie **sin el chrome del marketplace**:
sin `Header`, sin `Footer`, sin `BarraNavegacionMovil`, sin `ChatWidget`. Solo una barra
mínima (wordmark **CarStore Ec** + enlace "Volver"). Motivo: es un **servicio distinto**
al de comprar/vender; mezclarlo con el feed diluye ambos.

- `/verificar` → **landing del servicio**: una frase de qué hace + el campo de placa +
  "qué incluye gratis / con cuenta". Un botón grande.
- `/verificar/{placa}` → **resultado en bloques** (misma superficie aislada). Reusa
  `PerfilVehiculo` (tarjeta-resumen + acordeones por bloque) con el estado de acceso por
  bloque.
- `/consultar` y `/consultar/{placa}` → **redirigen** a `/verificar` (no romper enlaces
  ni SEO).

### 4.2 Free vs. login en la pantalla

- Sin sesión: se pintan los bloques de **Fase 1** con datos; los de Fase 2/3 aparecen como
  **teaser con candado** y un botón "Inicia sesión para ver el detalle" (`/login?next=…`).
- Con sesión: se revelan los bloques de Fase 2 (y Fase 3 tras el consentimiento de
  "compra segura"). **Sin tokens, sin precios** en la UI (§1.0.3).

### 4.3 Las dos landings

1. **Hub / puerta de entrada** (`/`): dos accesos grandes —
   **"Consultar un vehículo"** → `/verificar` · **"Comprar, vender y servicios"** →
   `/marketplace`. Debajo, lo que ya vive en el inicio (accesos rápidos + mapa de stock).
2. **Landing del servicio de consulta** (`/verificar`, ver 4.1): su propia página de
   entrada con el campo de placa.

---

## 5. Cambios necesarios

### 5.1 Backend (mínimo)

- **Migración `0036`:** `UPDATE productos_consulta SET tokens = 0, precio_referencial_usd = 0`
  para todos los códigos. Es la que AGENTS.md §1.0.3 dejó anotada como pendiente para
  "cuando se retome el tema de la consulta por placa". Deja las ramas de cobro cableadas
  pero inalcanzables (`debitar_tokens(0)` es no-op).
- **`consultar_perfil`:** con sesión, revelar todos los productos activos (ya son gratis)
  sin exigir un `POST /desbloquear` por bloque. Cambio acotado: `desbloqueados = {todos los
  códigos activos} if usuario else set()`. Reversible cuando vuelva la monetización.
- **No** se toca el pipeline de fuentes ni el catálogo. SRI/FGE siguen dormidos.

### 5.2 Frontend

- `src/lib/rutas.ts` — lista de rutas aisladas + helper.
- `ChromeSlot` (o *early-return* en `Header`/`BarraNavegacionMovil`/`ChatWidget` + gate del
  `Footer`) para ocultar el chrome en `/verificar*`.
- `src/app/verificar/layout.tsx` — barra mínima propia.
- `src/app/verificar/page.tsx` — landing del servicio (campo de placa).
- `src/app/verificar/[placa]/page.tsx` — resultado en bloques (reusa `PerfilVehiculo`).
- `src/app/consultar/**` — `redirect()` a `/verificar`.
- `src/app/page.tsx` — hub con las dos puertas arriba; el resto del inicio se conserva.

### 5.3 Fuera de este cambio (siguiente iteración)

- Probar **ANT "valores de matrícula"** desde el worker.
- Sumar **EMOV Cuenca** y **ATM Guayaquil** al worker (patrón AxisCloud/propio).
- Integrar **Función Judicial eSATJE** como bloque "temas judiciales" (Fase 3).
- Bloque **n.º de dueños** cuando el proveedor API confirme el contrato.
- Consentimiento explícito de "voy a comprar este auto" para Fase 3.

---

## 6. Riesgos y notas

- **PII de terceros:** los bloques judiciales / de titular muestran **agregados o sí/no**,
  nunca el nombre ni el detalle del proceso de otra persona a un extraño. El dueño
  autenticado ve lo suyo completo (§7, §9 AGENTS).
- **`mock` jamás en producción** (§1.0.3): la vista aislada hereda esa regla — un dato
  fabricado en una pantalla cuya promesa es la transparencia es peor que no tener el dato.
- **Una fuente caída no rompe la pantalla** (§8): el bloque sale como "no disponible" y el
  resto se pinta igual.
- **SEO:** `/consultar/{placa}` ya está indexado; los `redirect()` a `/verificar/{placa}`
  deben ser permanentes para trasladar el ranking.
- **Reversibilidad de la monetización:** al poner los tokens en 0 no se borra la lógica de
  cobro; cuando se retome, se suben los precios y se vuelve a exigir `desbloquear` por
  bloque. El `login` como barrera ya deja el punto de control puesto.
