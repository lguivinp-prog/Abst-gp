$ErrorActionPreference = "Stop"

$ProjectName = if ($env:PROJECT_NAME) { $env:PROJECT_NAME } else { "abst_p14_validation" }
$ComposeFile = "verification/docker-compose.test.yml"
$KeepEnv = if ($env:KEEP_ENV) { $env:KEEP_ENV } else { "0" }
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ArtifactsDir = "artifacts/verification/p14/$Timestamp"

New-Item -ItemType Directory -Force -Path $ArtifactsDir | Out-Null
Set-Location -Path "$PSScriptRoot/.."

Write-Host "============================================="
Write-Host "INICIANDO CERTIFICACIÓN CANÓNICA P14 - 14/14 GATES"
Write-Host "============================================="

$Results = [ordered]@{}

function Run-Compose {
    & docker compose -p $ProjectName -f $ComposeFile @args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose execution failed with exit code $LASTEXITCODE"
    }
}

function Get-Candidate-Tree-Sha {
    param(
        [string]$BaseCommit = "caa135c25392330b483167d5d552c51dc398a905",
        [string]$PatchPath = ""
    )
    $TmpIndex = [System.IO.Path]::GetTempFileName()
    $TmpPatch = $null
    $prevIndex = $env:GIT_INDEX_FILE
    try {
        # 1. B3: Deteccion exhaustiva de archivos no rastreados (untracked)
        # Rechaza cualquier omision silenciosa de archivos nuevos en el worktree
        $untracked = git ls-files --others --exclude-standard
        $excludedPatterns = @("artifacts/*", "*.zip", ".git/*", "test_dummy.db")
        $untrackedOffenders = @()
        foreach ($f in $untracked) {
            $normalized = $f.Replace("\", "/")
            $isExcluded = $false
            foreach ($pat in $excludedPatterns) {
                if ($normalized -like $pat) {
                    $isExcluded = $true
                    break
                }
            }
            if (-not $isExcluded) {
                $untrackedOffenders += $normalized
            }
        }
        if ($untrackedOffenders.Count -gt 0) {
            throw "ERROR B3: Archivos no rastreados (untracked) detectados en el worktree que serian omitidos silenciosamente de la certificacion: $($untrackedOffenders -join ', ')"
        }

        # 2. Generar parche binario integro si no fue provisto
        if (-not $PatchPath -or -not (Test-Path $PatchPath)) {
            $TmpPatch = [System.IO.Path]::GetTempFileName()
            git diff $BaseCommit --binary --output=$TmpPatch
            $PatchPath = $TmpPatch
        }

        # 3. Validar inventario del parche contra archivos modificados/anadidos en Git
        $patchStat = git apply --numstat $PatchPath
        if (-not $patchStat) {
            throw "ERROR B3: El parche generado esta vacio o no pudo ser interpretado."
        }

        # 4. Reconstruccion determinista sobre indice temporal aislado
        $env:GIT_INDEX_FILE = $TmpIndex
        git read-tree $BaseCommit
        git apply --cached --binary --whitespace=nowarn $PatchPath
        $computed = (git write-tree).Trim()

        # 5. Comprobacion estricta de correspondencia entre arbol reconstruido y candidato
        & git diff --quiet $computed
        if ($LASTEXITCODE -ne 0) {
            throw "ERROR B3: El arbol reconstruido ($computed) no corresponde de forma exacta al candidato de trabajo."
        }

        # 6. Calculo del hash SHA-256 del parche
        $patchSha256 = (Get-FileHash -Algorithm SHA256 -Path $PatchPath).Hash.ToLower()

        return @{
            TreeSha = $computed
            PatchSha256 = $patchSha256
        }
    } catch {
        Write-Warning "Error calculando Candidate Tree SHA: $_"
        throw $_
    } finally {
        Remove-Item -Force $TmpIndex -ErrorAction SilentlyContinue
        if ($TmpPatch) { Remove-Item -Force $TmpPatch -ErrorAction SilentlyContinue }
        if ($prevIndex) { $env:GIT_INDEX_FILE = $prevIndex } else { Remove-Item env:GIT_INDEX_FILE -ErrorAction SilentlyContinue }
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
    $BaseCommit = if ($env:BASE_COMMIT) { $env:BASE_COMMIT } else { "caa135c25392330b483167d5d552c51dc398a905" }
    $TreeShaBeforeObj = Get-Candidate-Tree-Sha -BaseCommit $BaseCommit
    $TreeShaBefore = $TreeShaBeforeObj.TreeSha
    $PatchShaBefore = $TreeShaBeforeObj.PatchSha256
    Write-Host "Candidate Tree SHA (Pre-Gates): $TreeShaBefore"
    Write-Host "Patch SHA-256 (Pre-Gates):      $PatchShaBefore"
    docker --version | Out-File -FilePath "$ArtifactsDir/versions.txt" -Encoding utf8
    docker compose version | Out-File -FilePath "$ArtifactsDir/versions.txt" -Append -Encoding utf8
    Run-Compose config | Out-File -FilePath "$ArtifactsDir/compose-config.yml" -Encoding utf8

    # A.1 CERTIFICACIÓN GIT AISLADA REAL (B3, B4)
    Write-Host "[A.1] Certificación Git Aislada Real (test_p14_r5_07, test_p14_item4)..."
    try {
        $env:APP_ENV = "test"
        $env:DATABASE_URL = "postgresql://test_user:test_password@localhost:5432/test_db"
        $env:SECRET_KEY = "synthetic_secret_key_for_testing"
        $env:PYTHONPATH = "backend;."
        $certCode = @"
import sys
import os
sys.path.insert(0, '.')
sys.path.insert(0, 'backend')
from tests.security.test_p14_security_hardening import test_p14_r5_07_candidate_tree_sha_isolated_and_stable
from tests.security.test_p14_backup_lan import test_p14_item4_candidate_tree_sha_exact_patch_all_files
print('Executing test_p14_r5_07_candidate_tree_sha_isolated_and_stable on host Git...')
test_p14_r5_07_candidate_tree_sha_isolated_and_stable()
print('test_p14_r5_07 passed.')
print('Executing test_p14_item4_candidate_tree_sha_exact_patch_all_files on host Git...')
test_p14_item4_candidate_tree_sha_exact_patch_all_files()
print('test_p14_item4 passed.')
print('GIT_CERTIFICATION: 2 CRITICAL TESTS PASSED ON REAL GIT (0 SKIPPED)')
"@
        $certTmp = [System.IO.Path]::GetTempFileName() + ".py"
        [System.IO.File]::WriteAllText($certTmp, $certCode)
        try {
            $pInfo = New-Object System.Diagnostics.ProcessStartInfo
            $pInfo.FileName = "python"
            $pInfo.Arguments = "`"$certTmp`""
            $pInfo.RedirectStandardOutput = $true
            $pInfo.RedirectStandardError = $true
            $pInfo.UseShellExecute = $false
            $p = [System.Diagnostics.Process]::Start($pInfo)
            $pOut = $p.StandardOutput.ReadToEnd()
            $pErr = $p.StandardError.ReadToEnd()
            $p.WaitForExit()
            $combined = $pOut + "`n" + $pErr
            [System.IO.File]::WriteAllText("$ArtifactsDir/git_certification.log", $combined)
            if ($p.ExitCode -ne 0) {
                throw "Git certification tests failed with exit code $($p.ExitCode). See $ArtifactsDir/git_certification.log"
            }
        } finally {
            Remove-Item -Force $certTmp -ErrorAction SilentlyContinue
        }
        Write-Host "Pruebas críticas Git B3/B4 completadas en host con éxito (0 skipped)."
    } catch {
        $Results["PREFLIGHT"] = "FAIL"
        throw $_
    }
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
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & docker compose -p $ProjectName -f $ComposeFile run --rm backend-test sh -c "alembic upgrade head && alembic current" 2>&1 | Out-File -FilePath "$ArtifactsDir/alembic.log" -Encoding utf8
        $ErrorActionPreference = $prevEAP
        if ($LASTEXITCODE -ne 0) {
            throw "Alembic failed with exit code $LASTEXITCODE"
        }
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
    Write-Host "Ejecutando suite Playwright Chromium completa..."
    try {
        Run-Compose run --rm browser-test sh -c "npx playwright test --output=/tmp/test-results --reporter=line" | Out-File -FilePath "$ArtifactsDir/browser_e2e.log" -Encoding utf8
        $Results["BROWSER_E2E"] = "PASS"
    } catch {
        $Results["BROWSER_E2E"] = "FAIL"
        throw $_
    }

} finally {
    # L. REPORTE
    Write-Host "--- GENERANDO REPORTE MATRIZ ---"
    $ReportFile = "$ArtifactsDir/gate-summary.md"
    $BaseCommit = if ($env:BASE_COMMIT) { $env:BASE_COMMIT } else { "caa135c25392330b483167d5d552c51dc398a905" }
    $TreeShaAfterObj = Get-Candidate-Tree-Sha -BaseCommit $BaseCommit
    $TreeShaAfter = $TreeShaAfterObj.TreeSha
    $PatchShaAfter = $TreeShaAfterObj.PatchSha256
    Write-Host "Candidate Tree SHA (Post-Gates): $TreeShaAfter"
    Write-Host "Patch SHA-256 (Post-Gates):      $PatchShaAfter"
    $TreeShaStable = ($TreeShaBefore -eq $TreeShaAfter)
    if (-not $TreeShaStable) {
        Write-Error "Fallo critico de trazabilidad Git (B4): Candidate Tree SHA difiere antes y despues de gates ($TreeShaBefore != $TreeShaAfter). Mutacion detectada."
        $Results["GIT_STABILITY_B4"] = "FAIL"
    }
    $HeadSha = try { (git rev-parse HEAD).Trim() } catch { "UNKNOWN" }
    $Branch = try { (git rev-parse --abbrev-ref HEAD).Trim() } catch { "UNKNOWN" }
    "# Resumen de Certificación Canónica P14 (14/14 Release Gates)" | Out-File -FilePath $ReportFile -Encoding utf8
    "" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Run ID:** $Timestamp" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Base Commit:** $BaseCommit" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Candidate Tree SHA (Pre-Gates):** $TreeShaBefore" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Candidate Tree SHA (Post-Gates):** $TreeShaAfter" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Candidate Patch SHA-256:** $PatchShaAfter" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Candidate Tree Stability (B4):** $(if ($TreeShaStable) { 'STABLE (PASS)' } else { 'MUTATED (FAIL)' })" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Worktree HEAD:** $HeadSha" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Worktree Branch:** $Branch" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "**Artifacts Dir:** $ArtifactsDir" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "| Gate | Estado |" | Out-File -FilePath $ReportFile -Append -Encoding utf8
    "|------|--------|" | Out-File -FilePath $ReportFile -Append -Encoding utf8

    $Gates = @("PREFLIGHT", "BUILD", "FRONTEND", "DEPENDENCIAS", "ALEMBIC", "SEED", "SEED_E2E", "SUITE_BACKEND", "CONCURRENCY", "ROLLBACK", "DOCUMENTAL", "LEGACY_V5_INFRASTRUCTURE_PIPELINE", "NATIVE_V6_API_E2E", "BROWSER_E2E")
    $AllPass = $true
    if (-not $TreeShaStable) {
        $AllPass = $false
    }
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
        Write-Host "RELEASE CERTIFICATION P14 PASS (14/14)"
    } else {
        Write-Host "RELEASE CERTIFICATION P14 FAIL"
        exit 1
    }
}
