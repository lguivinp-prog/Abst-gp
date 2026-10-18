$ErrorActionPreference = "Stop"

$ProjectName = "abst_gp_v52_validation"
$ComposeFile = "verification/docker-compose.test.yml"
$KeepEnv = if ($env:KEEP_ENV) { $env:KEEP_ENV } else { "0" }
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ArtifactsDir = "artifacts/verification/v5.3/$Timestamp"

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null
Set-Location -Path "$PSScriptRoot/.."

Write-Host "============================================="
Write-Host "INICIANDO RELEASE CERTIFICATION V5.3 - 11/11 GATES"
Write-Host "============================================="

$Results = [ordered]@{}

function Run-Compose {
    & docker compose -p $ProjectName -f $ComposeFile @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose execution failed with exit code $LASTEXITCODE"
    }
}

function Cleanup {
    Write-Host "--- Ejecutando Cleanup ---"
    docker compose -p $ProjectName -f $ComposeFile logs | Out-File -FilePath "$ArtifactsDir/docker-compose.log" -Encoding utf8
    if ($KeepEnv -eq "1") {
        Write-Host "KEEP_ENV=1: Omitiendo cleanup de contenedores."
    } else {
        docker compose -p $ProjectName -f $ComposeFile down -v --remove-orphans
    }
}

try {
    # A. PREFLIGHT
    Write-Host "[A] Preflight..."
    docker --version | Out-File -FilePath "$ArtifactsDir/versions.txt" -Encoding utf8
    docker compose version | Out-File -FilePath "$ArtifactsDir/versions.txt" -Append -Encoding utf8
    Run-Compose config | Out-File -FilePath "$ArtifactsDir/compose-config.yml" -Encoding utf8
    $Results["PREFLIGHT"] = "PASS"

    # B. BUILD IMÁGENES
    Write-Host "[B] Build Imágenes..."
    try {
        Run-Compose build | Out-File -FilePath "$ArtifactsDir/compose-build.log" -Encoding utf8
        $Results["BUILD"] = "PASS"
    } catch {
        $Results["BUILD"] = "FAIL"
        throw $_
    }

    # C. FRONTEND
    Write-Host "[C] Frontend Build & Check..."
    try {
        Run-Compose run --rm frontend-test sh -c "npm ci --legacy-peer-deps && npm run build" | Out-File -FilePath "$ArtifactsDir/npm-ci.log" -Encoding utf8
        $Results["FRONTEND"] = "PASS"
    } catch {
        $Results["FRONTEND"] = "FAIL"
        throw $_
    }

    # D. DEPENDENCIAS
    Write-Host "[D] Dependencias (PostgreSQL, Redis)..."
    Run-Compose up -d db-test redis-test
    Write-Host "Esperando healthchecks..."
    Start-Sleep -Seconds 10
    $Results["DEPENDENCIAS"] = "PASS"

    # E. ALEMBIC
    Write-Host "[E] Alembic Migrations..."
    try {
        Run-Compose run --rm backend-test alembic upgrade head | Out-File -FilePath "$ArtifactsDir/alembic.log" -Encoding utf8
        $Results["ALEMBIC"] = "PASS"
    } catch {
        $Results["ALEMBIC"] = "FAIL"
        throw $_
    }

    # E.2 BOOTSTRAP SEED
    Write-Host "[E.2] Bootstrap Base Data..."
    try {
        Run-Compose run --rm backend-test python scripts/seed_base.py | Out-File -FilePath "$ArtifactsDir/seed.log" -Encoding utf8
        $Results["SEED"] = "PASS"
    } catch {
        $Results["SEED"] = "FAIL"
        throw $_
    }

    # F. BACKEND SUITE
    Write-Host "[F] Backend Suite Completa..."
    try {
        & docker compose -p $ProjectName -f $ComposeFile stop worker-test backend-app 2>&1 | Out-Null
    } catch {}
    $global:LASTEXITCODE = 0
    try {
        Run-Compose run --rm backend-test python -m pytest tests/ -v --ignore=tests/e2e | Out-File -FilePath "$ArtifactsDir/pytest-full.log" -Encoding utf8
        $Results["SUITE_BACKEND"] = "PASS"
    } catch {
        Write-Host "=== ERROR EXCEPTION IN SUITE_BACKEND ==="
        Write-Host "Message: $_"
        Write-Host "Exception: $($_.Exception)"
        Write-Host "ScriptStackTrace: $($_.ScriptStackTrace)"
        $Results["SUITE_BACKEND"] = "FAIL"
        throw $_
    }

    # G. CONCURRENCIA
    Write-Host "[G] Prueba Real de Concurrencia (Legacy + P13)..."
    try {
        Run-Compose run --rm backend-test python -m pytest tests/api/integration/test_comparison_concurrency.py tests/api/v6/test_p13_concurrency_idempotency.py -v | Out-File -FilePath "$ArtifactsDir/concurrency.log" -Encoding utf8
        $Results["CONCURRENCY"] = "PASS"
    } catch {
        $Results["CONCURRENCY"] = "FAIL"
        throw $_
    }

    # H. ROLLBACK
    Write-Host "[H] Prueba Real de Rollback..."
    try {
        Run-Compose run --rm backend-test python -m pytest tests/api/integration/test_comparison_rollback.py -v | Out-File -FilePath "$ArtifactsDir/rollback.log" -Encoding utf8
        $Results["ROLLBACK"] = "PASS"
    } catch {
        $Results["ROLLBACK"] = "FAIL"
        throw $_
    }

    # I. DOCUMENTAL SECURITY
    Write-Host "[I] Gate Documental (Seguridad)..."
    try {
        Run-Compose run --rm backend-test python -m pytest tests/e2e/test_documental_security.py -v | Out-File -FilePath "$ArtifactsDir/documental.log" -Encoding utf8
        $Results["DOCUMENTAL"] = "PASS"
    } catch {
        $Results["DOCUMENTAL"] = "FAIL"
        throw $_
    }

    # J. LEGACY V5 INFRASTRUCTURE PIPELINE
    Write-Host "[J] LEGACY_V5_INFRASTRUCTURE_PIPELINE..."
    Run-Compose up -d backend-app worker-test
    Write-Host "Esperando a backend y worker..."
    Start-Sleep -Seconds 15
    try {
        Run-Compose run --rm backend-test python -m pytest tests/e2e/test_full_document_pipeline.py -v | Out-File -FilePath "$ArtifactsDir/legacy_e2e.log" -Encoding utf8
        $Results["LEGACY_V5_INFRASTRUCTURE_PIPELINE"] = "PASS"
    } catch {
        $Results["LEGACY_V5_INFRASTRUCTURE_PIPELINE"] = "FAIL"
        throw $_
    }

    # J.1 ISOLATION BOUNDARY
    Write-Host "[J.1] ISOLATION BOUNDARY: Reiniciando worker y backend ordenadamente..."
    Run-Compose stop worker-test backend-app
    Run-Compose start backend-app worker-test
    Start-Sleep -Seconds 5

    # J.2 NATIVE V6 API E2E
    Write-Host "[J.2] NATIVE_V6_API_E2E..."
    try {
        Run-Compose run --rm backend-test python -m pytest tests/e2e/test_v6_full_document_pipeline.py -v | Out-File -FilePath "$ArtifactsDir/native_v6_e2e.log" -Encoding utf8
        $Results["NATIVE_V6_API_E2E"] = "PASS"
    } catch {
        $Results["NATIVE_V6_API_E2E"] = "FAIL"
        throw $_
    }

    # K. BROWSER E2E
    Write-Host "[K] Browser E2E..."
    Write-Host "[K.1] Bootstrap E2E Data para Browser..."
    try {
        Run-Compose run --rm -e ALLOW_E2E_SEED=true backend-test python scripts/seed_e2e.py | Out-File -FilePath "$ArtifactsDir/seed_e2e.log" -Encoding utf8
        $Results["SEED_E2E"] = "PASS"
    } catch {
        $Results["SEED_E2E"] = "FAIL"
        throw $_
    }

    Run-Compose up -d frontend-test
    Write-Host "Instalando Playwright dependencias en test container y ejecutando pruebas..."
    try {
        Run-Compose run --rm browser-test sh -c "npm install && npx playwright install --with-deps chromium && npm run test" | Out-File -FilePath "$ArtifactsDir/browser_e2e.log" -Encoding utf8
        $Results["BROWSER_E2E"] = "PASS"
    } catch {
        $Results["BROWSER_E2E"] = "FAIL"
        throw $_
    }

} finally {
    # L. REPORTE
    Write-Host "--- GENERANDO REPORTE MATRIZ ---"
    $ReportFile = "$ArtifactsDir/gate-summary.md"
    "# Resumen de Certificación V5.3 (14/14 Release Gates)" | Out-File -FilePath $ReportFile -Encoding utf8
    "" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Run ID:** $Timestamp" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Base Commit:** 063814e1ef6ded289d60dd4e9a906068bdd3752b" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Artifacts Dir:** $ArtifactsDir" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "| Gate | Estado |" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "|------|--------|" | Out-File -FilePath $ReportFile -Append -Encoding utf8

    $Gates = @("PREFLIGHT", "BUILD", "FRONTEND", "DEPENDENCIAS", "ALEMBIC", "SEED", "SEED_E2E", "SUITE_BACKEND", "CONCURRENCY", "ROLLBACK", "DOCUMENTAL", "LEGACY_V5_INFRASTRUCTURE_PIPELINE", "NATIVE_V6_API_E2E", "BROWSER_E2E")
    $AllPass = $true
    foreach ($g in $Gates) {
        $state = if ($Results.Contains($g)) { $Results[$g] } else { "FAIL" }
        "| $g | $state |" | Out-File -FilePath $ReportFile -Append -Encoding utf8
        Write-Host "$($g): $state"
        if ($state -ne "PASS") {
            $AllPass = $false
        }
    }

    Cleanup

    if ($AllPass) {
        Write-Host "RELEASE CERTIFICATION V5.3 PASS (14/14)"
    } else {
        Write-Host "RELEASE CERTIFICATION V5.3 FAIL"
        exit 1
    }
}
