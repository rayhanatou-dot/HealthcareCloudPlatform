param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$recoveryDir = Join-Path $ProjectRoot "tests\recovery"
$targetScript = Join-Path $recoveryDir "validate_minio_backup_restore.py"
$resultCsv = Join-Path $recoveryDir "minio_backup_restore_results.csv"
$summaryFile = Join-Path $recoveryDir "minio_backup_restore_summary.txt"

New-Item -ItemType Directory -Force $recoveryDir | Out-Null

$downloadedFile = Get-ChildItem `
    "$HOME\Downloads" `
    -Filter "validate_minio_backup_restore*.py" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $downloadedFile) {
    throw "Le script validate_minio_backup_restore.py est introuvable dans Downloads."
}

Copy-Item `
    -Path $downloadedFile.FullName `
    -Destination $targetScript `
    -Force

Write-Host "=== PYTHON SYNTAX ==="

python -m py_compile $targetScript

if ($LASTEXITCODE -ne 0) {
    throw "La validation syntaxique du script MinIO a échoué."
}

Write-Host "Python syntax: PASS"

Remove-Item $resultCsv -ErrorAction SilentlyContinue
Remove-Item $summaryFile -ErrorAction SilentlyContinue

Write-Host "`n=== MINIO BACKUP AND RESTORE ==="

python $targetScript

$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    throw "La validation de sauvegarde et restauration MinIO a échoué."
}

if (-not (Test-Path $resultCsv)) {
    throw "Le fichier de résultats MinIO n'a pas été créé."
}

$results = Import-Csv $resultCsv
$failed = @(
    $results |
        Where-Object {
            $_.Passed -notin @(
                "True",
                "true",
                "PASS",
                "Pass"
            )
        }
)

Write-Host "`n=== RESULT TABLE ==="

$results |
    Format-Table `
        Test,
        Expected,
        Actual,
        Passed `
        -AutoSize `
        -Wrap

if ($failed.Count -gt 0) {
    throw "$($failed.Count) contrôle(s) MinIO ont échoué."
}

Write-Host "`n=== FINAL STATUS ==="
Write-Host "Checks : $($results.Count)"
Write-Host "Failed : $($failed.Count)"
Write-Host "Result : PASS"
Write-Host "CSV    : $resultCsv"
Write-Host "Summary: $summaryFile"
