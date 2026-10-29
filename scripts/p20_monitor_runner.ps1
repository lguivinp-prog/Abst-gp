# ABAST GP V6 — P20 Health Monitor Task Runner for Windows Task Scheduler
# Ejecuta la comprobacion real de infraestructura cada 15 minutos
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$worktreeDir = Split-Path -Parent $scriptDir
$logDir = if ($env:MONITOR_LOG_PRIMARY) { $env:MONITOR_LOG_PRIMARY } else { "D:\BACKUPS_PROYECTOS\ABAST_GP_P19_MIGRATION\logs" }

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

$logFile = Join-Path $logDir "monitor_task_runner.log"
$timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

Set-Location -Path $worktreeDir

try {
    # Ejecutar monitor real
    $proc = Start-Process -FilePath "python.exe" -ArgumentList "monitoring/p20_real_health_monitor.py" -Wait -PassThru -NoNewWindow
    $exitCode = $proc.ExitCode

    $finishTs = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "[$finishTs] Monitoreo de infraestructura finalizado (ExitCode: $exitCode)." | Out-File -FilePath $logFile -Append -Encoding utf8
    exit $exitCode
} catch {
    $errTs = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    "[$errTs] EXCEPCION durante la ejecucion del monitor: $_" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}
