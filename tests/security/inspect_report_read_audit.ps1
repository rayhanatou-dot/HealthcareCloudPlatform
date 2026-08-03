param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$outputDir = Join-Path $ProjectRoot "tests\security"
$outputFile = Join-Path $outputDir "report_read_audit_inspection.txt"

New-Item -ItemType Directory -Force $outputDir | Out-Null
Remove-Item $outputFile -ErrorAction SilentlyContinue

function Write-Section {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    $header = "`n=== $Title ==="
    Write-Host $header
    $header | Add-Content -Path $outputFile -Encoding UTF8
}

function Write-Line {
    param(
        [AllowEmptyString()]
        [string]$Text
    )

    Write-Host $Text
    $Text | Add-Content -Path $outputFile -Encoding UTF8
}

$endpointFile = ".\backend\app\api\v1\endpoints\diagnostic_reports.py"

if (-not (Test-Path $endpointFile)) {
    throw "Diagnostic report endpoint file was not found."
}

Write-Section "CURRENT GIT HEAD"

foreach ($line in (git log -1 --oneline)) {
    Write-Line $line
}

Write-Section "DIAGNOSTIC REPORT GET ROUTES"

$routeMatches = Select-String `
    -Path $endpointFile `
    -Pattern '@router\.get\(' `
    -Context 0,45

foreach ($match in $routeMatches) {
    Write-Line ""
    Write-Line "LINE: $($match.LineNumber)"
    Write-Line $match.Line

    foreach ($line in $match.Context.PostContext) {
        Write-Line $line
    }
}

Write-Section "DIAGNOSTIC REPORT AUDIT USAGE"

$auditMatches = Select-String `
    -Path $endpointFile `
    -Pattern 'audit|REPORT_|ACCESS_DENIED|LOGIN_' `
    -CaseSensitive:$false `
    -Context 3,8

foreach ($match in $auditMatches) {
    Write-Line ""
    Write-Line "LINE: $($match.LineNumber)"

    foreach ($line in $match.Context.PreContext) {
        Write-Line $line
    }

    Write-Line $match.Line

    foreach ($line in $match.Context.PostContext) {
        Write-Line $line
    }
}

Write-Section "AUDIT IMPLEMENTATION FILES"

$auditFiles = Get-ChildItem ".\backend\app" `
    -Recurse `
    -File `
    -Filter "*.py" |
    Where-Object {
        $_.Name -match "audit" -or
        (
            Select-String `
                -Path $_.FullName `
                -Pattern "REPORT_UPLOAD|REPORT_DOWNLOAD|ACCESS_DENIED" `
                -Quiet
        )
    } |
    Sort-Object FullName -Unique

foreach ($file in $auditFiles) {
    Write-Line $file.FullName
}

Write-Section "AUDIT ACTION DEFINITIONS"

$definitionMatches = Get-ChildItem ".\backend\app" `
    -Recurse `
    -File `
    -Filter "*.py" |
    Select-String `
        -Pattern 'REPORT_UPLOAD|REPORT_DOWNLOAD|REPORT_READ|class\s+.*Audit|Enum' `
        -CaseSensitive:$false `
        -Context 2,8

foreach ($match in $definitionMatches) {
    Write-Line ""
    Write-Line "FILE: $($match.Path)"
    Write-Line "LINE: $($match.LineNumber)"

    foreach ($line in $match.Context.PreContext) {
        Write-Line $line
    }

    Write-Line $match.Line

    foreach ($line in $match.Context.PostContext) {
        Write-Line $line
    }
}

Write-Section "AUDIT SERVICE PUBLIC METHODS"

$serviceCandidates = $auditFiles |
    Where-Object {
        $_.Name -match "service"
    }

foreach ($file in $serviceCandidates) {
    Write-Line ""
    Write-Line "FILE: $($file.FullName)"

    $methodMatches = Select-String `
        -Path $file.FullName `
        -Pattern '^\s*(async\s+)?def\s+' `
        -Context 0,12

    foreach ($match in $methodMatches) {
        Write-Line ""
        Write-Line "LINE: $($match.LineNumber)"
        Write-Line $match.Line

        foreach ($line in $match.Context.PostContext) {
            Write-Line $line
        }
    }
}

Write-Section "TARGETED STATUS"

$statusLines = git status --short -- `
    "backend/app/api/v1/endpoints/diagnostic_reports.py" `
    "backend/app/services" `
    "backend/app/models" `
    "tests/security/test_diagnostic_report_audit_e2e.py" `
    "tests/security/diagnostic_report_audit_results.csv"

foreach ($line in $statusLines) {
    Write-Line $line
}

Write-Host "`nInspection file created:"
Write-Host $outputFile
