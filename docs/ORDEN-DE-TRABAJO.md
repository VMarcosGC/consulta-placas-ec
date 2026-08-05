# Orden de trabajo — ciclo marketplace (2026-08-04)

## Antes de TASK-001

Tres cosas que no son desarrollo y que bloquean o distorsionan todo lo demás.

### P0 — Cortar el proveedor `mock` en producción

**Hoy, sin código.** Producción cobra 3 y 5 tokens por `identificadores_tecnicos`
y `titular_validado` que el mock **fabrica**. Un usuario paga por la validación de
un titular que salió de una lista hardcodeada, en un producto cuya propuesta es la
transparencia.

Dashboard de Render → `PROVEEDOR_VEHICULAR_ACTIVO` a un proveedor sin credenciales.
Verificar después que el endpoint público devuelva `disponible: false` en ambos
productos.

El arreglo estructural (default nulo en vez de `mock`) va en tarea aparte; esto es
el corte inmediato.

### P1 — Pushear el frontend

Tres commits locales: M2.10, MC2 y el fix de `solo_cache`. La bitácora del
2026-07-25 declara **cerrada** la deuda de M2.6/M2.7, pero en la web que ven los
usuarios `DatosOficialesMini` sigue llamando al perfil sin `solo_cache`, o sea
sigue disparando scraping en cache miss. El trabajo está hecho y documentado como
resuelto; el problema sigue exactamente donde estaba.

### P2 — Reemplazar `AGENTS.md` §1

Ver `AGENTS-seccion-1-reemplazo.md`. Los tres agentes leen ese archivo como fuente
de verdad y hoy dice "consulta por placa con cuatro pilares". Sin esto,
`dev-backend` implementa TASK-001 con la definición de producto anterior.

Commit: `docs(agents): reorienta el proposito al marketplace y fija el alcance del ciclo`

---

## TASK-001 — Contacto comprador-vendedor

Ver `TASK-001-contacto-vendedor.md`. Ruteo `claude-code` por §16: migración
Alembic más cambio de modelo que cruza el marketplace.

Es el bloqueante real de "market completo": sin contacto, un comprador ve el
anuncio y no tiene cómo llegar al vendedor.

---

## Después de TASK-001

En orden, sin fechas — el orden importa más que el calendario.

**TASK-002 — Frontend del contacto.** Botón "Ver teléfono" en el detalle, enlace
a WhatsApp, formulario de perfil de vendedor. Repo hermano. Ruteo `claude-code`
(`dev-frontend`), porque toca el mirror de types y el contrato de errores.

**TASK-003 — Precios a 0 y `/precios` honesto.** Hoy muestra cuatro paquetes con
un pie que promete un gateway que no llega en este ciclo. Con el alcance §1.0.2
eso es publicidad de algo inexistente. Ruteo `codex`: cercado y mecánico.

**TASK-004 — Proveedor nulo por defecto.** El arreglo estructural de P0: que el
default sea un proveedor que declara capacidades vacías y `mock` requiera
habilitación explícita en desarrollo. Ruteo `claude-code`.

**TASK-005 — `compartidos.py:58` devuelve 402, no 422.** Latente mientras el costo
sea 0, se activa el día que se cobre. Ruteo `codex`: una línea con criterio obvio.

**TASK-006 — Auditoría de créditos en el ledger.** 51 tokens sin explicar entre
tres usuarios, entrados por SQL manual. Sin consecuencia económica hoy; imposible
de cerrar cuando existan saldos reales. Ruteo `claude-code`.

**TASK-007 — `scripts/estado.py`.** Imprime: head de alembic local vs Neon,
commits sin pushear en ambos repos, proveedor activo en producción, fuentes con
consultas en los últimos 7 días. Su salida es **precondición de cada entrada de
bitácora**.

Esta es la que evita que el diagnóstico vuelva a hacer falta. Las cinco
discrepancias encontradas comparten causa: la documentación registra intención, no
estado verificado. "Correr alembic" arrastrado cinco entradas cuando ya estaba
hecho; FGE descrita como funcional en tres lugares desde que murió el 30 de mayo;
"commit sin push" falso para backend y verdadero para frontend. Un comando que
mira el sistema real las cierra todas.

Ruteo `codex`: script aislado, criterio de aceptación obvio.

---

## Compuertas abiertas

Hay siete a la vez (M2, M2.5, M2.6, M2.7, M2.8, M2.10, MC1, MC2), todas con la
misma frase: "código implementado, compuerta ABIERTA a la espera de la prueba
manual". Los guiones v2 a v6 nunca se corrieron.

**Recomendación: no cerrarlas una por una.** El código cambió seis veces encima;
correr seis guiones verifica un estado que ya no existe. Después de TASK-002,
correr **solo el guión de MC2** más el flujo de contacto de punta a punta, y
declarar las anteriores cerradas por inclusión donde el flujo las atraviese.

Documentar esa decisión en la bitácora, con el motivo. Es una desviación
deliberada del ritual de §3, no un olvido más.

---

## Fuera de este ciclo

Patios e ingesta masiva (etapa 2). Pasarela de pago. SRI y FGE. Feed tipo reels y
app móvil. Mensajería interna. Verificación de teléfono por OTP.

Reactivación de cada uno: ver la tabla de `AGENTS.md` §1.0.2.
