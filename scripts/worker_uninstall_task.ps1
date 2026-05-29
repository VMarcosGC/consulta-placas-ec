<#
.SYNOPSIS
    Elimina la tarea programada del worker hibrido (revierte el autoarranque).

.DESCRIPTION
    Quita la tarea 'ConsultaPlacasWorker'. No borra codigo, logs ni datos; solo
    deja de autoarrancar el worker al iniciar sesion.

    Uso:
        powershell -ExecutionPolicy Bypass -File scripts\worker_uninstall_task.ps1
#>

$ErrorActionPreference = "Stop"
$NombreTarea = "ConsultaPlacasWorker"

if (Get-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $NombreTarea -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $NombreTarea -Confirm:$false
    Write-Host "Tarea '$NombreTarea' eliminada. El worker ya no autoarranca." -ForegroundColor Green
}
else {
    Write-Host "La tarea '$NombreTarea' no existe; nada que hacer." -ForegroundColor Yellow
}
