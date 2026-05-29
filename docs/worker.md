# Worker híbrido — autoarranque en Windows (Task Scheduler)

El worker ([worker.py](../worker.py)) procesa la cola `cola_scraping` desde una IP
**residencial ecuatoriana** y llena la caché `consultas` que lee la API en Render.
AMT y FGE bloquean IPs de datacenter, por eso se procesan acá y no en el cloud
(ver [arquitectura_hibrida.md](arquitectura_hibrida.md)).

Esta guía cubre correrlo como **tarea programada en modo "solo con sesión iniciada"**:
arranca al iniciar sesión, sin guardar contraseña ni permisos de administrador.

## Prerrequisitos
- `.venv` creado con las dependencias: `pip install -r requirements.txt`.
- Chromium de Playwright instalado: `playwright install chromium`.
- `.env` con `DATABASE_URL` apuntando a Neon (lo carga `python-dotenv` al importar
  `src/core/database.py`).

## Instalar el autoarranque
```powershell
powershell -ExecutionPolicy Bypass -File scripts\worker_install_task.ps1
```
Registra la tarea `ConsultaPlacasWorker`. **No pide admin ni contraseña.**

| Parámetro | Valor |
|---|---|
| Disparador | Al iniciar sesión del usuario actual |
| Cuenta | usuario actual, sin elevación (RunLevel Limited), LogonType Interactive |
| Tiempo límite | sin límite (es un daemon) |
| Instancias | una sola (IgnoreNew) |
| Energía | corre con batería, no se detiene al pasar a batería |
| Reinicio ante fallo | 3 veces, cada 1 min (además del bucle del envoltorio) |

El envoltorio [scripts/worker_run.ps1](../scripts/worker_run.ps1) corre `worker.py`
en un **bucle de reinicio** y vuelca todo a `logs/worker.log`.

## Operación
```powershell
# Arrancar ya (sin esperar al próximo logon)
Start-ScheduledTask -TaskName ConsultaPlacasWorker

# Estado / última ejecución
Get-ScheduledTask -TaskName ConsultaPlacasWorker | Get-ScheduledTaskInfo

# Detener
Stop-ScheduledTask -TaskName ConsultaPlacasWorker

# Ver logs en vivo
Get-Content .\logs\worker.log -Tail 30 -Wait
```

### Correr a mano (sin tarea, para depurar)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\worker_run.ps1
# o directamente:
.\.venv\Scripts\python.exe worker.py
```

## Desinstalar
```powershell
powershell -ExecutionPolicy Bypass -File scripts\worker_uninstall_task.ps1
```

## Comportamiento y límites
- **Solo con sesión iniciada:** si cierras sesión o apagas la PC, el worker se detiene
  y los trabajos quedan en la cola (`pendiente` / `en_proceso`); se procesan cuando vuelve.
  No se pierde nada.
- **Cierre abrupto:** Windows mata el proceso al cerrar sesión. El worker tiene **rescate
  de zombis**: los trabajos `en_proceso` huérfanos (> `WORKER_TIMEOUT_ZOMBI_SEGUNDOS`, default
  300s) vuelven a `pendiente` automáticamente. No requiere apagado limpio.
- **OneDrive:** el proyecto vive bajo `OneDrive`; correr como el usuario logueado evita
  problemas de acceso a esa ruta (otra razón del modo "con sesión").
- **Variables opcionales** (en `.env` o entorno): `WORKER_POLL_SEGUNDOS` (5),
  `WORKER_BACKOFF_BASE_SEGUNDOS` (30), `WORKER_TIMEOUT_ZOMBI_SEGUNDOS` (300).
- **24/7 sin sesión:** si en el futuro se necesita, se cambia a "ejecutar aunque el usuario
  no haya iniciado sesión" (requiere almacenar la contraseña de Windows en la tarea).
