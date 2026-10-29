# ABAST GP V6 — P20 Daily Backup Task Runner for Windows Task Scheduler
# Ejecuta el respaldo diario a las 02:00 (hora local de Perú)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$worktreeDir = Split-Path -Parent $scriptDir
$logDir = if ($env:MONITOR_LOG_PRIMARY) { $env:MONITOR_LOG_PRIMARY } else { "D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\logs" }

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$logFile = Join-Path $logDir "scheduled_task_runner.log"
$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
"[$timestamp] Iniciando tarea programada de respaldo diario..." | Out-File -FilePath $logFile -Append -Encoding utf8

Set-Location -Path $worktreeDir

try {
    # Ejecutar runner de Python
    $proc = Start-Process -FilePath "python.exe" -ArgumentList "scripts/p20_daily_backup.py" -Wait -PassThru -NoNewWindow
    $exitCode = $proc.ExitCode

    $finishTs = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    if ($exitCode -eq 0) {
        "[$finishTs] Tarea de respaldo finalizada con EXITO (ExitCode: $exitCode)." | Out-File -FilePath $logFile -Append -Encoding utf8
    } else {
        "[$finishTs] ERROR: Tarea de respaldo finalizo con fallo (ExitCode: $exitCode)." | Out-File -FilePath $logFile -Append -Encoding utf8
    }
    exit $exitCode
} catch {
    $errTs = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "[$errTs] EXCEPCION durante la ejecucion de la tarea programada: $_" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}
