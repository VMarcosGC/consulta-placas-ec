# Plan de costos por etapas — Revisa tu Carro EC + Market de Autos

**Fecha:** 2026-07-19 · **Decisiones de Marcos:** M2 con **Cloudinary**; presupuesto de
validación **hasta ~$30/mes**.
**Principio:** escalar el gasto **solo cuando la demanda lo dispare** (triggers medibles,
§4). Cada mejora de infraestructura debe estar pagada por una mejora del servicio que
ofrecemos o por ingresos de tokens.

> Precios verificados en julio 2026 (fuentes al pie). Revalidar antes de cada upgrade:
> estos proveedores cambian precios con frecuencia.

---

## 1. Inventario de servicios de los que dependemos

| Servicio | Rol | Free tier (hoy) | Primer escalón pago |
|---|---|---|---|
| **Render** | Backend FastAPI (Docker) | 750 h/mes; **spin-down a los 15 min → cold start 30-60 s** | **Starter $7/mes/servicio** (sin cold start, 512 MB) |
| **Neon** | PostgreSQL 16 | 100 CU-h/mes de cómputo; **0.5 GB/proyecto** | **Launch**: uso puro, sin mínimo — $0.106/CU-h + $0.35/GB-mes |
| **Vercel** | Frontend Next.js | Hobby: 100 GB ancho de banda, 1M invocaciones. **Prohibido uso comercial** | **Pro $20/mes/asiento** (obligatorio al vender tokens) |
| **Cloudinary** (M2) | Fotos: storage + CDN + miniaturas | **25 créditos/mes** (1 crédito = 1 GB storage o 1 GB ancho de banda o 1 000 transformaciones). **Al pasarse SUSPENDE subidas, no cobra overage** | Plus **$89/mes** (225 créditos) — caro: a esa altura conviene migrar a R2 (§5) |
| **UptimeRobot** | Ping a `/health` cada 10 min (mitiga cold start free) | Gratis (50 monitores) | No se prevé pagarlo |
| **Dominio** | Marca propia | — | `.com` ~$12-15/año (~$1.2/mes); `.ec` ~$35-55/año (por confirmar en NIC.ec) |
| **Proveedor vehicular** (`consultas_ec`) | Datos para desbloqueos | — | **Por consulta, ~$0.08 estimado** (medición real pendiente de API key; ver `evaluacion_proveedor_real.md`) |
| **2Captcha / Capsolver** | Solver SRI (DORMIDO) | — | ~$1-3/1000; **no activar** — decisión: passthrough + API oficial |
| **Worker residencial** | AMT/FGE desde tu PC | $0 (tu equipo + Task Scheduler) | Alternativa futura: proxy residencial $50+/mes — **evitar** mientras el worker alcance |

## 2. Fases de gasto según demanda

### F0 — Validación (hoy → primera venta real) · **$8/mes**
- **Render Starter $7**: se activa YA. Justificación: en un market, el comprador que espera
  60 s de cold start no vuelve; es la mejora de servicio más barata por dólar.
- **Dominio `.com` ~$1/mes** (opcional pero recomendado para confianza del feed).
- Todo lo demás en free tier: Neon free (0.5 GB da para miles de publicaciones sin fotos
  — las fotos viven en Cloudinary, la BD solo guarda URLs), Cloudinary free, Vercel Hobby
  (aceptable mientras NO haya ventas), UptimeRobot.
- Presupuesto restante del tope de $30: colchón, no gastarlo por gastar.

### F1 — Lanzamiento comercial (primer paquete de tokens vendido) · **~$28/mes**
- **+ Vercel Pro $20**: la regla de Vercel es explícita — Hobby es solo no-comercial;
  cualquier deployment que genere ingresos exige Pro. Trigger: **el día que se venda el
  primer paquete de tokens** (o antes, si se publica el checkout).
- Cloudinary y Neon siguen free. Con 25 créditos/mes alcanza aprox. para ~12 GB de fotos
  servidas + storage + miniaturas en un mes tranquilo (regla práctica: ~8 fotos/publicación
  optimizadas a ~300 KB ⇒ miles de vistas antes de tocar el techo).

### F2 — Tracción (triggers de §4 disparados) · **~$35-60/mes**
- **+ Neon Launch** (uso puro, sin mínimo): pasar cuando el storage se acerque a 0.5 GB o
  el cómputo a 100 CU-h/mes. Estimado inicial: $5-15/mes.
- **Fotos**: decidir con datos reales de consumo:
  - Si el techo son las **transformaciones/bandwidth** → seguir en Cloudinary pero servir
    variantes cacheadas (el CDN de Vercel absorbe repetidos), o
  - Si el techo es **storage/costo** → migrar originales a **Cloudflare R2** (10 GB gratis,
    egress $0, ~$0.015/GB-mes después) y dejar Cloudinary solo para transformaciones.
  - **No pagar Cloudinary Plus ($89) por reflejo**: es el salto más caro del stack; casi
    siempre R2 + optimización propia sale a <$5/mes.
- **+ Costo variable del proveedor vehicular**: crece con las ventas — y está cubierto por
  diseño (§3). No es gasto fijo.

### F3 — Escala (patios activos, cientos de publicaciones) · **~$100-250/mes**
- Render: instancia mayor o segundo servicio (worker dedicado en la nube con proxy
  residencial solo si el worker de tu PC deja de alcanzar).
- Neon Launch crece con uso; evaluar Scale si hacen falta más branches/entornos.
- CDN/imágenes: contrato Cloudinary o pipeline propio en R2 + Workers.
- **Gestión oficial**: API del SRI (convenio, $0/consulta) y acuerdos con patios — a esta
  altura los trámites valen más que cualquier optimización técnica.

## 3. El otro lado: costos de lo que OFRECEMOS (unit economics)

Regla vigente (AGENTS.md §10.3): **1 token ≈ USD 0.04** y solo se cobra por costo real,
dificultad o valor comercial.

| Producto | Precio (tokens → USD) | Costo variable | Margen |
|---|---|---|---|
| Ficha pública + ficha técnica | 0 (gratis) | ~$0 (BD propia) | — (motor de tráfico) |
| Identificadores técnicos | 3 → $0.12 | ~$0.08 (proveedor, 1 llamada cacheada) | ~$0.04 |
| Titular validado | 5 → $0.20 | misma llamada cacheada | ~$0.20 |
| Multas con montos | 10 → $0.40 | scraping propio (worker $0) | ~$0.40 |
| Reporte compra segura | 40 → $1.60 | ~$0.08 | ~$1.52 |
| Publicación premium | 3 → $0.12 | $0 | $0.12 |
| Verificación marketplace | 100 → $4.00 | tu tiempo de revisión | según tu hora |

Lecturas clave:
- El **caché** es el multiplicador del margen: una llamada de $0.08 al proveedor sirve
  varios productos y varios compradores del mismo vehículo (TTL 90 d para lo estático).
- El punto de equilibrio de la infra F1 (~$28/mes) son **~18 reportes de compra segura al
  mes** o su equivalente en mezcla de productos. Métrica simple para decidir upgrades.
- Las **mejoras del servicio ofrecido** se escalonan igual que la infra: más fotos por
  publicación (F2), verificación con visita física (F3, cobrarla acorde), destacados de
  patio (F3) — cada una entra cuando su fase de infra la soporte sin degradar lo gratis.

## 4. Triggers de upgrade (medibles, no por intuición)

| Métrica (revisar 1×/semana) | Umbral | Acción |
|---|---|---|
| Ventas de tokens | primer paquete vendido | Vercel Pro $20 (F1) |
| Storage Neon | > 0.4 GB (80 %) | Neon Launch (F2) |
| Créditos Cloudinary | > 20/25 (80 %) dos meses seguidos | Decisión R2 vs seguir (F2) |
| Consultas al backend | cold starts reportados / feed lento | Ya cubierto por Starter; si sigue → instancia mayor (F3) |
| Cola del worker (AMT/FGE) | > 1 h de retraso sostenido | Segundo worker o proxy (F3) |
| Llamadas al proveedor | > 100/mes | Renegociar precio por volumen |

## 5. Riesgos de costo conocidos
1. **Cloudinary no avisa cobrando: suspende.** Configurar alerta al 80 % de créditos desde
   el día 1 de M2; si se suspende, el market se queda sin fotos nuevas.
2. **Vercel Hobby comercial**: monetizar sobre Hobby es violación de términos — riesgo de
   pausa del deployment justo cuando empieza a vender. Por eso el trigger de F1 es duro.
3. **Neon free tiene tope agregado** (5 GB entre proyectos): no crear proyectos paralelos
   de prueba sobre la misma cuenta sin control.
4. **El proveedor vehicular es costo variable sin techo**: mantener la regla "solo se
   llama al desbloquear + caché"; jamás llamarlo en el preview gratis (ya es regla §10.3).
5. **Render Starter es por servicio**: si algún día el worker va a la nube, son $7 más —
   mantenerlo en tu PC mientras se pueda.

## 6. Resumen ejecutivo

| Fase | Gasto/mes | Se activa cuando |
|---|---|---|
| F0 Validación | **~$8** (Render Starter + dominio) | ahora (decisión 2026-07-19) |
| F1 Comercial | **~$28** (+ Vercel Pro) | primera venta de tokens |
| F2 Tracción | **~$35-60** (+ Neon Launch, decisión fotos) | triggers de storage/créditos |
| F3 Escala | **~$100-250** | patios activos y volumen sostenido |

---

**Fuentes de precios (julio 2026):**
[Cloudinary Pricing](https://cloudinary.com/pricing) · [Cloudinary credits FAQ](https://cloudinary.com/documentation/developer_onboarding_faq_credits) ·
[Neon Pricing](https://neon.com/pricing) · [Neon plans (docs)](https://neon.com/docs/introduction/plans) ·
[Render — free tier 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026) ·
[Vercel Pricing](https://vercel.com/pricing) · [Vercel Hobby (docs)](https://vercel.com/docs/plans/hobby) · [Vercel Fair Use](https://vercel.com/docs/limits/fair-use-guidelines)
