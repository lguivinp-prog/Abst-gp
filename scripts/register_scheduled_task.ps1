# ABAST GP V6 — P20 Registro de Tarea Programada de Respaldo Diario
# Registra la tarea para ejecutarse diariamente a las 02:00 (hora local de Perú, UTC-5)
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$taskName = if ($env:BACKUP_TASK_NAME) { $env:BACKUP_TASK_NAME } else { "ABAST_GP_V6_Daily_Backup" }
$scriptPath = Join-Path $scriptDir "p20_backup_runner.ps1"

Write-Host "Registrando tarea programada '$taskName' para las 02:00 AM..."

# 1. Definir accion
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

# 2. Definir disparador diario a las 02:00
$trigger = New-ScheduledTaskTrigger -Daily -At "02:00:00"

# 3. Definir configuracion de ejecucion
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable

# 4. Registrar tarea para el usuario actual
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Respaldo diario automatico consistente, cifrado y firmado de ABAST GP V6 (PostgreSQL y documentos) a las 02:00 AM." `
    -Force | Out-Null

Write-Host "Tarea '$taskName' registrada exitosamente."

# 5. Consultar y verificar la tarea registrada
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State, @{Name="NextRunTime";Expression={($_ | Get-ScheduledTaskInfo).NextRunTime}} | Format-List
