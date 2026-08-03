param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$target = ".\tests\security\validate_production_http_security.py"

if (-not (Test-Path $target)) {
    $downloaded = Get-ChildItem "$HOME\Downloads" `
        -Filter "validate_production_http_security*.py" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if (-not $downloaded) {
        throw "validate_production_http_security.py was not found."
    }

    New-Item -ItemType Directory -Force ".\tests\security" | Out-Null
    Copy-Item $downloaded.FullName $target -Force
}

python -m py_compile $target

if ($LASTEXITCODE -ne 0) {
    throw "Production security test syntax validation failed."
}

python $target
$exitCode = $LASTEXITCODE

if (Test-Path ".\tests\security\production_security_summary.txt") {
    Write-Host "`n=== PRODUCTION SECURITY SUMMARY ==="
    Get-Content ".\tests\security\production_security_summary.txt"
}

if (Test-Path ".\tests\security\production_security_results.csv") {
    Write-Host "`n=== PRODUCTION SECURITY RESULTS ==="

    Import-Csv ".\tests\security\production_security_results.csv" |
        Format-Table Test, Expected, Actual, Passed -AutoSize -Wrap
}

if ($exitCode -ne 0) {
    throw "Production HTTP security validation failed."
}

Write-Host "`nProduction HTTP security validation: PASS"
