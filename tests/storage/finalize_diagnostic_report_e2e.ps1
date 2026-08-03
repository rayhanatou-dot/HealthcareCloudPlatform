param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$testFile = ".\tests\storage\test_diagnostic_report_e2e.py"
$resultFile = ".\tests\storage\diagnostic_report_e2e_results.csv"
$logFile = ".\tests\storage\diagnostic_report_e2e_output.txt"

if (-not (Test-Path $testFile)) {
    throw "Missing test file: $testFile"
}

function Get-DiagnosticReportCount {
    $value = docker compose exec -T postgres psql `
        -U healthcare_user `
        -d healthcare_cloud_db `
        -tA `
        -c "SELECT COUNT(*) FROM diagnostic_reports;"

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read diagnostic_reports count."
    }

    return [int]($value.Trim())
}

Write-Host "=== BACKEND HEALTH ==="

$health = Invoke-RestMethod `
    -Uri "http://localhost:8000/health" `
    -TimeoutSec 15 `
    -ErrorAction Stop

if ($health.status -ne "healthy") {
    throw "Backend health check failed."
}

Write-Host "Backend status: healthy"

Write-Host "`n=== TEST SYNTAX ==="

python -m py_compile $testFile

if ($LASTEXITCODE -ne 0) {
    throw "E2E test syntax validation failed."
}

Write-Host "Python syntax: PASS"

$beforeCount = Get-DiagnosticReportCount

Remove-Item $resultFile -ErrorAction SilentlyContinue
Remove-Item $logFile -ErrorAction SilentlyContinue

Write-Host "`n=== DIAGNOSTIC REPORT E2E TEST ==="

python $testFile 2>&1 |
    Tee-Object -FilePath $logFile

$testExitCode = $LASTEXITCODE

if ($testExitCode -ne 0) {
    Write-Host "`n=== BACKEND LOGS ==="
    docker compose logs backend --tail 80
    throw "Diagnostic report E2E validation failed. Review $logFile"
}

if (-not (Test-Path $resultFile)) {
    throw "The E2E result CSV was not created."
}

$results = Import-Csv $resultFile
$failedResults = @(
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

$afterCount = Get-DiagnosticReportCount

Write-Host "`n=== RESULT TABLE ==="

$results |
    Format-Table `
        Test,
        Expected,
        Actual,
        Passed `
        -AutoSize `
        -Wrap

Write-Host "`n=== CLEANUP CHECK ==="
Write-Host "Rows before test: $beforeCount"
Write-Host "Rows after test : $afterCount"

if ($failedResults.Count -gt 0) {
    throw "$($failedResults.Count) E2E checks failed."
}

if ($beforeCount -ne $afterCount) {
    throw "Cleanup failed: diagnostic_reports row count changed."
}

Write-Host "`n=== GIT VALIDATION ==="

git diff --check

if ($LASTEXITCODE -ne 0) {
    throw "Git whitespace validation failed."
}

$filesToStage = @(
    ".\backend\app\services\storage_service.py",
    ".\tests\storage\test_diagnostic_report_e2e.py",
    ".\tests\storage\diagnostic_report_e2e_results.csv"
) | Where-Object { Test-Path $_ }

git add -- $filesToStage

$stagedChanges = git diff --cached --name-only

if ($stagedChanges) {
    git commit -m "Add diagnostic report end-to-end storage validation"

    if ($LASTEXITCODE -ne 0) {
        throw "Git commit failed."
    }
}
else {
    Write-Host "No new staged changes to commit."
}

Write-Host "`n=== FINAL STATUS ==="
Write-Host "E2E checks : $($results.Count)"
Write-Host "Failed     : $($failedResults.Count)"
Write-Host "Cleanup    : PASS"
git log -1 --oneline
