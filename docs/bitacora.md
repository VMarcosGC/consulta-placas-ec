# Bitácora de trabajo — `consulta_placas_ec`

Registro cronológico de **lo que se hace en cada sesión** (decisiones, cambios, pendientes).
Complementa, no reemplaza:
- [AGENTS.md](../AGENTS.md) — fuente de verdad (reglas, fases, convenciones).
- [proyecto-snapshot.md](../proyecto-snapshot.md) — foto del estado AS-IS completo.

Entradas nuevas arriba (más reciente primero). Formato por entrada:
fecha · rama · qué se hizo · verificación · pendientes.

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
