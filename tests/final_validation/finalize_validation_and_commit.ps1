param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$outDir = ".\tests\final_validation"
New-Item -ItemType Directory -Force $outDir | Out-Null

function Get-BooleanSummary {
    param(
        [string[]]$Candidates,
        [int]$ExpectedTotal
    )

    $path = $Candidates |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1

    if (-not $path) {
        return [pscustomobject]@{
            Status = "PENDING"
            Passed = $null
            Total = $ExpectedTotal
            Evidence = ""
            Note = "Evidence file not found."
        }
    }

    $rows = @(Import-Csv $path)

    if ($rows.Count -eq 0) {
        return [pscustomobject]@{
            Status = "REVIEW"
            Passed = $null
            Total = $ExpectedTotal
            Evidence = $path
            Note = "Evidence file is empty."
        }
    }

    $columns = @("Passed", "passed", "PASS", "Success", "success", "Valid", "valid")
    $column = $columns |
        Where-Object { $rows[0].PSObject.Properties.Name -contains $_ } |
        Select-Object -First 1

    if (-not $column) {
        return [pscustomobject]@{
            Status = "REVIEW"
            Passed = $null
            Total = $ExpectedTotal
            Evidence = $path
            Note = "Pass/fail column could not be identified."
        }
    }

    $parsed = @(
        foreach ($row in $rows) {
            $value = "$($row.$column)".Trim().ToLowerInvariant()

            if ($value -in @("true", "1", "yes", "pass", "passed")) {
                $true
            }
            elseif ($value -in @("false", "0", "no", "fail", "failed")) {
                $false
            }
        }
    )

    if ($parsed.Count -eq 0) {
        return [pscustomobject]@{
            Status = "REVIEW"
            Passed = $null
            Total = $ExpectedTotal
            Evidence = $path
            Note = "Pass/fail values could not be parsed."
        }
    }

    $passed = @($parsed | Where-Object { $_ }).Count
    $status = if ($passed -eq $parsed.Count -and $parsed.Count -eq $ExpectedTotal) {
        "PASS"
    }
    elseif ($passed -eq $parsed.Count) {
        "REVIEW"
    }
    else {
        "FAIL"
    }

    return [pscustomobject]@{
        Status = $status
        Passed = $passed
        Total = $parsed.Count
        Evidence = $path
        Note = if ($parsed.Count -ne $ExpectedTotal) {
            "Expected $ExpectedTotal checks, found $($parsed.Count)."
        }
        else {
            ""
        }
    }
}

$matrix = @()

function Add-ValidationRow {
    param(
        [string]$Domain,
        [string]$Validation,
        [pscustomobject]$Summary
    )

    $script:matrix += [pscustomobject]@{
        domain = $Domain
        validation = $Validation
        status = $Summary.Status
        passed_checks = $Summary.Passed
        total_checks = $Summary.Total
        evidence = $Summary.Evidence
        note = $Summary.Note
    }
}

Add-ValidationRow "Security" "Production HTTP security" (
    Get-BooleanSummary @(
        ".\tests\security\production_security_results.csv"
    ) 17
)

Add-ValidationRow "Security" "Diagnostic report strict audit" (
    Get-BooleanSummary @(
        ".\tests\security\diagnostic_report_audit_strict_results.csv",
        ".\tests\security\diagnostic_report_audit_results.csv"
    ) 9
)

Add-ValidationRow "Storage" "Diagnostic report end-to-end storage" (
    Get-BooleanSummary @(
        ".\tests\storage\diagnostic_report_e2e_results.csv",
        ".\tests\storage\diagnostic_report_storage_results.csv"
    ) 10
)

Add-ValidationRow "Storage" "MinIO service lifecycle" (
    Get-BooleanSummary @(
        ".\tests\storage\storage_service_validation_results.csv",
        ".\tests\storage\minio_storage_results.csv"
    ) 4
)

Add-ValidationRow "Disaster recovery" "PostgreSQL backup and restore" (
    Get-BooleanSummary @(
        ".\tests\recovery\postgres_backup_restore_results.csv"
    ) 19
)

Add-ValidationRow "Disaster recovery" "MinIO backup and restore" (
    Get-BooleanSummary @(
        ".\tests\recovery\minio_backup_restore_results.csv"
    ) 23
)

$performancePath = ".\tests\performance\results\performance_consolidated_summary.csv"

if (Test-Path $performancePath) {
    $performanceRows = @(Import-Csv $performancePath)
    $optimized = $performanceRows |
        Where-Object { $_.scenario -eq "200 users optimized" } |
        Select-Object -First 1

    if ($optimized) {
        $failures = [int][double]$optimized.failure_count
        $performanceSummary = [pscustomobject]@{
            Status = if ($failures -eq 0) { "PASS" } else { "FAIL" }
            Passed = if ($failures -eq 0) { 1 } else { 0 }
            Total = 1
            Evidence = $performancePath
            Note = "Failures=$failures; RPS=$($optimized.requests_per_second); P95=$($optimized.p95_response_ms) ms."
        }
    }
    else {
        $performanceSummary = [pscustomobject]@{
            Status = "REVIEW"
            Passed = $null
            Total = 1
            Evidence = $performancePath
            Note = "Optimized 200-user scenario not found."
        }
    }
}
else {
    $performanceSummary = [pscustomobject]@{
        Status = "PENDING"
        Passed = $null
        Total = 1
        Evidence = ""
        Note = "Consolidated performance summary not found."
    }
}

Add-ValidationRow "Performance" "Optimized 200-user load" $performanceSummary

$csvPath = Join-Path $outDir "final_validation_matrix.csv"
$mdPath = Join-Path $outDir "final_validation_matrix.md"
$txtPath = Join-Path $outDir "final_project_status.txt"

$matrix | Export-Csv $csvPath -NoTypeInformation -Encoding UTF8

$pass = @($matrix | Where-Object status -eq "PASS").Count
$fail = @($matrix | Where-Object status -eq "FAIL").Count
$pending = @($matrix | Where-Object status -eq "PENDING").Count
$review = @($matrix | Where-Object status -eq "REVIEW").Count
$overall = if ($fail -eq 0 -and $pending -eq 0 -and $review -eq 0) {
    "PASS"
}
else {
    "INCOMPLETE"
}

$markdown = @(
    "# Final Validation Matrix",
    "",
    "| Domain | Validation | Status | Checks | Evidence | Note |",
    "|---|---|---:|---:|---|---|"
)

foreach ($row in $matrix) {
    $checks = if ($null -ne $row.passed_checks) {
        "$($row.passed_checks)/$($row.total_checks)"
    }
    else {
        "?/$($row.total_checks)"
    }

    $markdown += "| $($row.domain) | $($row.validation) | $($row.status) | $checks | $($row.evidence) | $($row.note) |"
}

$markdown += @(
    "",
    "## Status summary",
    "",
    "- Overall: $overall",
    "- PASS: $pass",
    "- FAIL: $fail",
    "- PENDING: $pending",
    "- REVIEW: $review",
    ""
)

$markdown | Set-Content $mdPath -Encoding UTF8

@(
    "FINAL PROJECT VALIDATION STATUS",
    "Overall status: $overall",
    "PASS: $pass",
    "FAIL: $fail",
    "PENDING: $pending",
    "REVIEW: $review",
    "",
    "CSV: $csvPath",
    "Markdown: $mdPath"
) | Set-Content $txtPath -Encoding UTF8

Write-Host "=== FINAL VALIDATION MATRIX ==="
$matrix |
    Format-Table domain, validation, status, passed_checks, total_checks -AutoSize -Wrap

Write-Host "`n=== FINAL STATUS ==="
Get-Content $txtPath

git add -- `
    ".\tests\security\validate_production_http_security.py" `
    ".\tests\security\production_security_results.csv" `
    ".\tests\security\production_security_summary.txt" `
    $csvPath `
    $mdPath `
    $txtPath `
    ".\tests\final_validation\finalize_validation_and_commit.ps1"

git diff --cached --check

if ($LASTEXITCODE -ne 0) {
    throw "Git validation failed."
}

git diff --cached --quiet

if ($LASTEXITCODE -ne 0) {
    git commit -m "Add final production validation matrix"

    if ($LASTEXITCODE -ne 0) {
        throw "Git commit failed."
    }
}

Write-Host "`n=== RECENT COMMITS ==="
git log -3 --oneline
