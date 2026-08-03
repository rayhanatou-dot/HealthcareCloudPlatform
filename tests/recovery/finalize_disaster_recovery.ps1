param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$postgresResults = ".\tests\recovery\postgres_backup_restore_results.csv"
$minioResults = ".\tests\recovery\minio_backup_restore_results.csv"

$requiredFiles = @(
    ".\tests\recovery\validate_postgres_backup_restore.py",
    ".\tests\recovery\validate_minio_backup_restore.py",
    ".\tests\recovery\run_minio_recovery_validation.ps1",
    ".\tests\recovery\postgres_backup_restore_results.csv",
    ".\tests\recovery\postgres_backup_manifest.json",
    ".\tests\recovery\postgres_backup_restore_summary.txt",
    ".\tests\recovery\minio_backup_restore_results.csv",
    ".\tests\recovery\minio_backup_restore_summary.txt"
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path $file)) {
        throw "Required recovery artifact is missing: $file"
    }
}

$postgresRows = Import-Csv $postgresResults
$minioRows = Import-Csv $minioResults

$postgresFailed = @(
    $postgresRows |
        Where-Object {
            $_.Passed -notin @(
                "True",
                "true",
                "PASS",
                "Pass"
            )
        }
)

$minioFailed = @(
    $minioRows |
        Where-Object {
            $_.Passed -notin @(
                "True",
                "true",
                "PASS",
                "Pass"
            )
        }
)

if ($postgresFailed.Count -gt 0) {
    throw "PostgreSQL recovery validation contains $($postgresFailed.Count) failed checks."
}

if ($minioFailed.Count -gt 0) {
    throw "MinIO recovery validation contains $($minioFailed.Count) failed checks."
}

Write-Host "=== RECOVERY VALIDATION ==="
Write-Host "PostgreSQL checks: $($postgresRows.Count)"
Write-Host "PostgreSQL failed: $($postgresFailed.Count)"
Write-Host "MinIO checks     : $($minioRows.Count)"
Write-Host "MinIO failed     : $($minioFailed.Count)"

$gitignorePath = ".\.gitignore"

if (-not (Test-Path $gitignorePath)) {
    New-Item -ItemType File -Path $gitignorePath | Out-Null
}

$ignoreRules = @(
    "tests/recovery/*.dump",
    "tests/recovery/minio_backup_*/"
)

$currentIgnoreLines = @(
    Get-Content $gitignorePath -ErrorAction SilentlyContinue
)

foreach ($rule in $ignoreRules) {
    if ($currentIgnoreLines -notcontains $rule) {
        Add-Content -Path $gitignorePath -Value $rule -Encoding UTF8
        $currentIgnoreLines += $rule
    }
}

python -m py_compile `
    ".\tests\recovery\validate_postgres_backup_restore.py" `
    ".\tests\recovery\validate_minio_backup_restore.py"

if ($LASTEXITCODE -ne 0) {
    throw "Recovery Python syntax validation failed."
}

$filesToCommit = @(
    ".gitignore",
    "tests/recovery/validate_postgres_backup_restore.py",
    "tests/recovery/validate_minio_backup_restore.py",
    "tests/recovery/run_minio_recovery_validation.ps1",
    "tests/recovery/postgres_backup_restore_results.csv",
    "tests/recovery/postgres_backup_manifest.json",
    "tests/recovery/postgres_backup_restore_summary.txt",
    "tests/recovery/minio_backup_restore_results.csv",
    "tests/recovery/minio_backup_restore_summary.txt"
)

git diff --check -- $filesToCommit

if ($LASTEXITCODE -ne 0) {
    throw "Git whitespace validation failed."
}

git add -- $filesToCommit

git diff --cached --check

if ($LASTEXITCODE -ne 0) {
    throw "Staged recovery artifacts failed validation."
}

Write-Host "`n=== STAGED FILES ==="
git diff --cached --name-status

$stagedFiles = @(git diff --cached --name-only)

if ($stagedFiles.Count -eq 0) {
    Write-Host "No new recovery changes to commit."
}
else {
    git commit -m "Add disaster recovery validation"

    if ($LASTEXITCODE -ne 0) {
        throw "Recovery validation commit failed."
    }
}

Write-Host "`n=== FINAL STATUS ==="
Write-Host "PostgreSQL recovery: PASS"
Write-Host "MinIO recovery     : PASS"
Write-Host "Backup archives    : ignored by Git"
git log -3 --oneline
git status --short
