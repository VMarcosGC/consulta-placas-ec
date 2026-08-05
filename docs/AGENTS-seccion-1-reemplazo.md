# Reemplazo de `AGENTS.md` §1

> Reemplaza **solo** el contenido de `## 1. Propósito del proyecto`.
> No toca §1.1 ni ninguna otra sección. No renumera nada.
> Motivo: la decisión M2.6 del 2026-07-19 giró el producto a marketplace y §1
> quedó describiendo el producto anterior. Los tres agentes leen este archivo
> como fuente de verdad, así que toman decisiones con una definición obsoleta.

---

## 1. Propósito del proyecto

`consulta_placas_ec` (Revisa tu Carro EC) es un **marketplace de autos usados
para Ecuador** cuya propuesta de valor es la transparencia: el comprador ve la
ficha declarada por el vendedor junto a datos oficiales de fuentes públicas.

Público objetivo: compradores y vendedores particulares de clase media-baja,
navegando desde celulares de gama baja.

### 1.0.1 Jerarquía del producto

**El marketplace es el producto.** La consulta por placa es un **complemento**
que enriquece los anuncios, no un producto en sí.

Consecuencia operativa, y es una regla dura: **si una consulta falla, el flujo
del marketplace continúa.** Publicar, buscar, ver un anuncio y contactar a un
vendedor nunca dependen de que una fuente externa responda. Un dato oficial
ausente se muestra como no disponible; jamás bloquea una publicación ni degrada
la portada.

### 1.0.2 Alcance del ciclo vigente

Definido el 2026-08-04. Todo lo que no esté aquí está fuera de alcance.

**Dentro:**

- Marketplace completo para **personas naturales**: publicar con ficha declarada,
  fotos y precio; aportar referencias externas (Facebook, OLX); portada curada,
  búsqueda, favoritos; y **contacto comprador-vendedor**.
- Consultas como complemento, **solo fuentes públicas sin captcha**:
  ANT, AMT, EPMTSD.
- Contacto por **teléfono público del vendedor**, sin intermediación de tokens.

**Fuera, por decisión explícita — no es deuda, es alcance pospuesto:**

| Tema | Estado | Criterio de reactivación |
|---|---|---|
| Cobro y pasarela de pago | fuera | tener una versión estable y usuarios reales |
| Fuentes con captcha (SRI, FGE) | fuera | que se justifique el costo de resolver captcha o exista convenio de API oficial |
| Cuentas de patio e ingesta masiva | etapa 2 | que el flujo de particulares funcione con usuarios reales |
| Feed tipo reels, app móvil | fuera | — |

### 1.0.3 Monetización: suspendida, no eliminada

El mecanismo de tokens permanece implementado y funcional (`debitar_tokens`,
catálogo versionado, idempotencia por UK) pero **todos los precios están en 0**.

Reglas mientras dure el ciclo:

- Ningún flujo cobra. Ningún proveedor de pago está activo.
- **El proveedor `mock` no se usa en producción bajo ninguna circunstancia.** Un
  proveedor que fabrica datos no puede alimentar un producto cuya propuesta es la
  transparencia. El default de `PROVEEDOR_VEHICULAR_ACTIVO` es un proveedor nulo
  que declara capacidades vacías; `mock` se habilita explícitamente y solo en
  desarrollo.
- El contacto con el vendedor es libre y no se cobra.
- La auditoría del ledger (§10.3) sigue siendo obligatoria aunque los precios
  sean 0: los créditos deben quedar registrados igual, o el hueco se vuelve
  imposible de cerrar cuando existan saldos reales.

Qué se monetiza y qué no se decide **después** de tener una versión estable, con
datos de uso reales en la mano.

### 1.0.4 Etapas

**Etapa 1 — particulares (ciclo vigente).** Un vendedor es una persona natural.

**Etapa 2 — patios.** Cuentas de patio con página propia, ingesta masiva de
inventario, varios usuarios por vendedor. Las reglas de negocio están sin definir
y se definen al abrir la etapa, no antes.

Para no pagar una migración de datos cara después, el modelo incorpora desde la
etapa 1 una capa **`Vendedor`** entre el usuario y sus publicaciones. En etapa 1
la relación es 1:1 con la cuenta y el tipo es siempre `particular`. La etapa 2
agrega el tipo `patio` y la relación N:1 — un cambio aditivo, sin reescribir el
modelo.
