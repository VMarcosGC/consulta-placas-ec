# Experiencia del comprador — diseño de la portada del market (carril C)

**Fecha:** 2026-07-20 · **Decisión:** el desarrollo del market se divide en dos carriles:
**V (vendedor)** — publicación, ficha, fotos, referencias (lo trabajado hasta M2.9) — y
**C (comprador)** — navegación, descubrimiento y retención. Este doc diseña el carril C
para la **web**; la idea del feed vertical estilo reels/TikTok queda para la app (§4).

---

## 1. Qué hace que un comprador VUELVA (investigación jul-2026)

De los patrones de los marketplaces líderes (Carvana, AutoScout24, Kavak) y las guías de
merchandising 2026:

1. **Favoritos y búsquedas guardadas son la palanca #1 de retención.** Carvana centró su
   rediseño móvil justamente en saved search + favorites: el comprador de auto no compra
   en la primera visita — vuelve a "sus" autos. *(Nosotros ya tenemos `favoritos` por
   placa en el backend — está subutilizado.)*
2. **Descubrimiento curado, no solo búsqueda.** Los compradores que aún no saben qué
   quieren navegan bloques temáticos; los grids con bloques editoriales intercalados
   generan hasta +25 % páginas por sesión vs. un grid plano infinito.
3. **Velocidad y móvil primero.** Búsqueda con resultados instantáneos y layout que se
   siente app en el celular. Nuestro público (clase media-baja, gama baja) refuerza esto.
4. **La transparencia vende donde hay desconfianza.** Kavak construyó su negocio sobre
   la certificación en un mercado informal — nuestra versión es la **ficha técnica +
   datos oficiales + sello verificado**: hay que EXHIBIRLA como criterio de navegación,
   no solo mostrarla en el detalle.
5. **El detalle debe retener, no expulsar**: similares al pie ("otros como este"),
   favorito con un toque, compartir fácil.

## 2. Diseño de la portada del market (web, `/marketplace`)

Estructura vertical, móvil primero:

| # | Bloque | Contenido | Racional |
|---|---|---|---|
| 1 | **Buscador protagonista** | input grande "¿Qué auto buscas?" + chips rápidos (marca, rango de precio, tipo) | los que ya saben qué quieren no deben scrollear |
| 2 | **Destacados** (carrusel horizontal) | premium activos, portada grande | vitrina que monetiza el plan premium |
| 3 | **✓ Verificados y transparentes** | verificados por la plataforma + fichas ≥ 80 % | nuestro diferenciador; enseña al vendedor que la transparencia da visibilidad |
| 4 | **Explora por marca** | chips/logos de las marcas con stock real (derivadas de los datos, no hardcodeadas) | navegación sin teclado, estilo app |
| 5 | **Recién publicados** | últimos activos, grid 2 col (móvil) / 4 (desktop) | sensación de mercado vivo; recompensa la visita frecuente |
| 6 | **Por presupuesto** | bandas: < $10k · $10-20k · > $20k | el comprador real compra por bolsillo |
| 7 | **Referencias externas** | al pie, tarjetas con su etiqueta "no verificados" | completan oferta sin competir con lo nativo |

Transversal: **♡ favorito con un toque en toda tarjeta** (anónimo → pedir cuenta con copy
amable "Guarda este auto para verlo después"), barra sticky de búsqueda al scrollear, y
bloques que solo se muestran si tienen contenido (sin secciones vacías).

**Retención pasiva v1 (sin construir alertas todavía):** sección "Tus favoritos" arriba
del todo cuando el usuario logueado tiene ≥1, con badge si alguno bajó de precio
(comparación simple contra el precio guardado — barato de implementar, alto impacto).

## 3. Qué NO hacer ahora
- Recomendaciones personalizadas por comportamiento (requiere tracking + volumen).
- Alertas por correo/push de búsquedas guardadas (M-futuro, tras validar demanda).
- Chat/negociación (M5 ya definido: WhatsApp primero).

## 4. Futuro app: feed vertical estilo reels (registrado, no ahora)
Un swipe vertical por anuncio (foto full-screen, precio, ficha resumida, ♡ y "ver más")
es coherente con discovery commerce y con nuestro público. Queda como **MC3** en el plan,
condicionado a: web validada + fotos de buena calidad en volumen (sin buenas fotos, el
formato muere). La web de hoy debe construirse SIN hipotecar ese futuro: los endpoints de
feed paginado por cursor de MC2 servirán tal cual para el swipe de la app.

---
**Fuentes:** [Carvana platform UX (Proximity Lab)](https://www.proximitylab.com/work/carvana-platform-ux-design/) ·
[Lecciones de Carvana (Space Auto)](https://space.auto/blog/building-the-best-dealership-website-lessons-from-carvana-digital-strategies) ·
[Kavak: The Drive to Conquer (The Generalist)](https://www.generalist.com/briefing/kavak) ·
[Product discovery 2026 (CS-Cart)](https://www.cs-cart.com/blog/improve-ecommerce-product-discovery/) ·
[Category pages (ConvertCart)](https://www.convertcart.com/blog/ecommerce-category-pages) ·
[Merchandising 2026 (BigCommerce)](https://www.bigcommerce.com/articles/ecommerce/merchandising/)
