param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$alreadyStaged = @(git diff --cached --name-only)

if ($alreadyStaged.Count -gt 0) {
    Write-Host "Files are already staged:"
    $alreadyStaged
    throw "Commit or unstage the existing staged files before continuing."
}

$candidates = @(
    "Dockerfile",
    "alembic.ini",
    "tests/final_validation/generate_final_validation_matrix.py",
    "tests/recovery/finalize_disaster_recovery.ps1",
    "tests/recovery/validate_postgres_backup_restore.ps1",
    "tests/security/run_production_security_validation.ps1",
    "tests/storage/finalize_diagnostic_report_e2e.ps1",
    "tests/storage/inspect_diagnostic_report_module.ps1",
    "tests/storage/validate_minio_storage.py"
)

$existing = @(
    $candidates |
        Where-Object { Test-Path $_ -PathType Leaf }
)

if ($existing.Count -eq 0) {
    throw "No reusable project files were found."
}

Write-Host "=== FILES SELECTED ==="
$existing

$pythonFiles = @(
    $existing |
        Where-Object { $_.EndsWith(".py") }
)

foreach ($file in $pythonFiles) {
    python -m py_compile $file

    if ($LASTEXITCODE -ne 0) {
        throw "Python syntax validation failed: $file"
    }
}

$powershellFiles = @(
    $existing |
        Where-Object { $_.EndsWith(".ps1") }
)

foreach ($file in $powershellFiles) {
    $content = Get-Content $file -Raw
    [void][scriptblock]::Create($content)
}

foreach ($file in @("Dockerfile", "alembic.ini")) {
    if ($existing -contains $file) {
        if ((Get-Item $file).Length -eq 0) {
            throw "The file is empty: $file"
        }
    }
}

git add -- $existing

git diff --cached --check

if ($LASTEXITCODE -ne 0) {
    throw "Git validation failed."
}

$staged = @(git diff --cached --name-only)

Write-Host "`n=== STAGED FILES ==="
$staged

if ($staged.Count -eq 0) {
    Write-Host "No new changes to commit."
    exit 0
}

git commit -m "Add deployment configuration and reusable validation scripts"

if ($LASTEXITCODE -ne 0) {
    throw "Git commit failed."
}

Write-Host "`n=== RECENT COMMITS ==="
git log -5 --oneline

Write-Host "`n=== REMAINING STATUS COUNTS ==="
Write-Host "Tracked changes :" @(git diff --name-only).Count
Write-Host "Untracked files :" @(git ls-files --others --exclude-standard).Count
