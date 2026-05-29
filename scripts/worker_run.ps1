<#
.SYNOPSIS
    Envoltorio para correr el worker hibrido (worker.py) como daemon en Windows.

.DESCRIPTION
    - Fija el directorio de trabajo a la raiz del proyecto (para que `src` importe
      y `python-dotenv` halle el .env).
    - Usa el Python del venv del proyecto (.venv\Scripts\python.exe).
    - Corre worker.py en un bucle: si el proceso termina por cualquier razon,
      espera unos segundos y lo reinicia (robustez sin depender de Task Scheduler).
    - Anexa stdout+stderr a logs\worker.log con marca de tiempo.

    No modifica worker.py; solo lo lanza. Pensado para ejecutarse como tarea
    programada en modo "solo con sesion iniciada" (ver worker_install_task.ps1),
    pero tambien sirve para arrancarlo a mano:
        powershell -ExecutionPolicy Bypass -File scripts\worker_run.ps1
#>

$ErrorActionPreference = "Stop"

# Raiz del proyecto = carpeta padre de este script (scripts\..).
$Raiz = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Raiz

$Python = Join-Path $Raiz ".venv\Scripts\python.exe"
$Worker = Join-Path $Raiz "worker.py"
$LogDir = Join-Path $Raiz "logs"
$LogFile = Join-Path $LogDir "worker.log"

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

function Write-Log([string]$Mensaje) {
    $linea = "{0} [worker_run] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Mensaje
    Add-Content -Path $LogFile -Value $linea -Encoding utf8
}

if (-not (Test-Path $Python)) {
    Write-Log "ERROR: no existe el Python del venv en $Python. Crear .venv e instalar requirements.txt."
    exit 1
}

Write-Log "Lanzando worker (bucle de reinicio). Raiz=$Raiz"

# Bucle de supervision: reinicia el worker si se cae. El cierre de sesion mata
# este arbol de procesos (tarea de logon), que es el apagado esperado.
while ($true) {
    Write-Log "Iniciando: $Python $Worker"
    # IMPORTANTE: el worker registra en stderr. En PowerShell 5.1, redirigir el stderr
    # de un .exe (`*>>` / `2>&1`) lo envuelve como error terminante y, con
    # ErrorActionPreference=Stop, abortaria el proceso en la primera linea de log.
    # Por eso delegamos la redireccion a cmd.exe: PowerShell solo espera el exit code.
    & cmd.exe /c "`"$Python`" `"$Worker`" >> `"$LogFile`" 2>&1"
    $code = $LASTEXITCODE
    Write-Log "worker.py termino con codigo $code; reiniciando en 10s..."
    Start-Sleep -Seconds 10
}
