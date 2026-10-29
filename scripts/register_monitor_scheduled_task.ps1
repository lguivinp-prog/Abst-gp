# ABAST GP V6 — P20 Registro de Tarea Programada de Monitoreo Periodico
# Registra la tarea para ejecutarse cada 15 minutos de forma indefinida
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$taskName = if ($env:MONITOR_TASK_NAME) { $env:MONITOR_TASK_NAME } else { "ABAST_GP_V6_Health_Monitor" }
$scriptPath = Join-Path $scriptDir "p20_monitor_runner.ps1"

Write-Host "Registrando tarea programada '$taskName' para ejecutarse cada 15 minutos..."

# 1. Definir accion
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

# 2. Definir disparador recurrente cada 15 minutos indefinidamente
# Iniciando inmediatamente con repeticion continua
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15)

# 3. Definir configuracion
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# 4. Registrar tarea
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Supervisión autónoma periódica cada 15 minutos de infraestructura ABAST GP V6 (PostgreSQL, Redis, Workers, API, Caddy, Storage)." `
    -Force | Out-Null

Write-Host "Tarea '$taskName' registrada exitosamente."

# 5. Consultar y verificar la tarea registrada
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State, @{Name="NextRunTime";Expression={($_ | Get-ScheduledTaskInfo).NextRunTime}} | Format-List
