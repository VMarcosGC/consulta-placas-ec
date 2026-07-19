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
