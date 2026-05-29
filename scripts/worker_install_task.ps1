<#
.SYNOPSIS
    Registra la tarea programada que autoarranca el worker hibrido.

.DESCRIPTION
    Modo "solo con sesion iniciada":
      - Disparador: al iniciar sesion el usuario actual (AtLogOn).
      - Cuenta: usuario actual, RunLevel Limited (SIN admin), LogonType Interactive
        => NO se guarda contrasena.
      - Sin limite de tiempo (daemon), no arranca otra instancia si ya corre,
        corre con bateria, se inicia cuando este disponible, reinicia ante fallo.

    No requiere permisos de administrador. Lo unico que crea en el sistema es esta
    tarea (nombre 'ConsultaPlacasWorker'); revertir con worker_uninstall_task.ps1.

    Uso:
        powershell -ExecutionPolicy Bypass -File scripts\worker_install_task.ps1
#>

$ErrorActionPreference = "Stop"

$NombreTarea = "ConsultaPlacasWorker"
$Raiz = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Envoltorio = Join-Path $Raiz "scripts\worker_run.ps1"

if (-not (Test-Path $Envoltorio)) {
    throw "No se encontro el envoltorio en $Envoltorio"
}

# Accion: powershell oculto corriendo el envoltorio.
$accion = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"{0}`"" -f $Envoltorio)

# Disparador: al iniciar sesion del usuario actual.
$usuario = "$env:USERDOMAIN\$env:USERNAME"
$disparador = New-ScheduledTaskTrigger -AtLogOn -User $usuario

# Principal: usuario actual, sin admin (Limited), tipo interactivo (no guarda clave).
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited

# Ajustes: daemon (sin limite de tiempo), una sola instancia, robusto a energia/reinicio.
$ajustes = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$ajustes.ExecutionTimeLimit = "PT0S"   # 0 = sin limite (daemon)

# (Re)registrar la tarea.
if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
    Write-Host "La tarea '$NombreTarea' ya existe; se reemplaza." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
}

Register-ScheduledTask -TaskName $NombreTarea `
    -Action $accion -Trigger $disparador -Principal $principal -Settings $ajustes `
    -Description "Worker hibrido de consulta_placas_ec: procesa cola_scraping (AMT/FGE) desde IP residencial." | Out-Null

Write-Host ""
Write-Host "Tarea '$NombreTarea' registrada (modo: solo con sesion iniciada, sin admin)." -ForegroundColor Green
Write-Host "Arrancara sola al iniciar sesion. Comandos utiles:"
Write-Host "  Arrancar ahora:   Start-ScheduledTask -TaskName $NombreTarea"
Write-Host "  Ver estado:       Get-ScheduledTask -TaskName $NombreTarea | Get-ScheduledTaskInfo"
Write-Host "  Detener:          Stop-ScheduledTask -TaskName $NombreTarea"
Write-Host "  Logs:             Get-Content `"$Raiz\logs\worker.log`" -Tail 30 -Wait"
Write-Host "  Desinstalar:      powershell -ExecutionPolicy Bypass -File scripts\worker_uninstall_task.ps1"
