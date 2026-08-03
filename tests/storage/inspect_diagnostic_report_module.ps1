param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$resultsDir = Join-Path $ProjectRoot "tests\storage"
$reportFile = Join-Path $resultsDir "diagnostic_report_interface_inspection.txt"

New-Item -ItemType Directory -Force $resultsDir | Out-Null
Remove-Item $reportFile -ErrorAction SilentlyContinue

function Write-Section {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    $line = "`n=== $Title ==="
    Write-Host $line
    $line | Add-Content -Path $reportFile -Encoding UTF8
}

function Write-Text {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Text
    )

    Write-Host $Text
    $Text | Add-Content -Path $reportFile -Encoding UTF8
}

$endpointFile = ".\backend\app\api\v1\endpoints\diagnostic_reports.py"
$schemaFile = ".\backend\app\schemas\diagnostic_report.py"
$modelFile = ".\backend\app\models\diagnostic_report.py"
$serviceFile = ".\backend\app\services\diagnostic_report_service.py"

foreach ($requiredFile in @(
    $endpointFile,
    $schemaFile,
    $modelFile,
    $serviceFile
)) {
    if (-not (Test-Path $requiredFile)) {
        throw "Required file not found: $requiredFile"
    }
}

Write-Section "DIAGNOSTIC REPORT ROUTES"

$routeMatches = Select-String `
    -Path $endpointFile `
    -Pattern "@router\.(get|post|put|patch|delete)" `
    -Context 0,22

foreach ($match in $routeMatches) {
    Write-Text ""
    Write-Text "FILE: $($match.Path)"
    Write-Text "LINE: $($match.LineNumber)"
    Write-Text $match.Line

    foreach ($contextLine in $match.Context.PostContext) {
        Write-Text $contextLine
    }
}

Write-Section "RBAC BLOCKS"

$rbacMatches = Select-String `
    -Path $endpointFile `
    -Pattern "require_roles\(" `
    -Context 0,8

foreach ($match in $rbacMatches) {
    Write-Text ""
    Write-Text "LINE: $($match.LineNumber)"
    Write-Text $match.Line

    foreach ($contextLine in $match.Context.PostContext) {
        Write-Text $contextLine
    }
}

Write-Section "PYDANTIC SCHEMAS"

$schemaLines = Get-Content $schemaFile

for ($index = 0; $index -lt $schemaLines.Count; $index++) {
    Write-Text ("{0,4}: {1}" -f ($index + 1), $schemaLines[$index])
}

Write-Section "SQLALCHEMY MODEL"

$modelLines = Get-Content $modelFile

for ($index = 0; $index -lt $modelLines.Count; $index++) {
    Write-Text ("{0,4}: {1}" -f ($index + 1), $modelLines[$index])
}

Write-Section "SERVICE PUBLIC METHODS"

$serviceMatches = Select-String `
    -Path $serviceFile `
    -Pattern "^\s*(async\s+)?def\s+" `
    -Context 0,10

foreach ($match in $serviceMatches) {
    Write-Text ""
    Write-Text "LINE: $($match.LineNumber)"
    Write-Text $match.Line

    foreach ($contextLine in $match.Context.PostContext) {
        Write-Text $contextLine
    }
}

Write-Section "DATABASE COLUMNS"

$columnsSql = @"
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'diagnostic_reports'
ORDER BY ordinal_position;
"@

$columnsOutput = docker compose exec -T postgres psql `
    -U healthcare_user `
    -d healthcare_cloud_db `
    -P pager=off `
    -c $columnsSql

if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect diagnostic_reports columns."
}

foreach ($line in $columnsOutput) {
    Write-Text $line
}

Write-Section "DATABASE CONSTRAINTS"

$constraintsSql = @"
SELECT
    conname AS constraint_name,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.diagnostic_reports'::regclass
ORDER BY conname;
"@

$constraintsOutput = docker compose exec -T postgres psql `
    -U healthcare_user `
    -d healthcare_cloud_db `
    -P pager=off `
    -c $constraintsSql

if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect diagnostic_reports constraints."
}

foreach ($line in $constraintsOutput) {
    Write-Text $line
}

Write-Section "DATABASE INDEXES"

$indexesSql = @"
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'diagnostic_reports'
ORDER BY indexname;
"@

$indexesOutput = docker compose exec -T postgres psql `
    -U healthcare_user `
    -d healthcare_cloud_db `
    -P pager=off `
    -c $indexesSql

if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect diagnostic_reports indexes."
}

foreach ($line in $indexesOutput) {
    Write-Text $line
}

Write-Section "ROW COUNT"

$countOutput = docker compose exec -T postgres psql `
    -U healthcare_user `
    -d healthcare_cloud_db `
    -P pager=off `
    -c "SELECT COUNT(*) AS diagnostic_report_count FROM diagnostic_reports;"

if ($LASTEXITCODE -ne 0) {
    throw "Unable to count diagnostic reports."
}

foreach ($line in $countOutput) {
    Write-Text $line
}

Write-Host "`nInspection report created:"
Write-Host $reportFile
