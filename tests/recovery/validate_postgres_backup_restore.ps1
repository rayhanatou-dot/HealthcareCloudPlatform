param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$recoveryDir = Join-Path $ProjectRoot "tests\recovery"
New-Item -ItemType Directory -Force $recoveryDir | Out-Null

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$DefaultValue
    )

    $envPath = Join-Path $ProjectRoot ".env"

    if (Test-Path $envPath) {
        $match = Get-Content $envPath |
            Where-Object {
                $_ -match "^\s*$([regex]::Escape($Name))="
            } |
            Select-Object -First 1

        if ($match) {
            return (($match -split "=", 2)[1]).Trim().Trim('"').Trim("'")
        }
    }

    return $DefaultValue
}

$postgresUser = Get-EnvValue `
    -Name "POSTGRES_USER" `
    -DefaultValue "healthcare_user"

$sourceDatabase = Get-EnvValue `
    -Name "POSTGRES_DB" `
    -DefaultValue "healthcare_cloud_db"

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$restoreDatabase = "${sourceDatabase}_restore_test"

$containerDump = "/tmp/${sourceDatabase}_${timestamp}.dump"
$hostDump = Join-Path `
    $recoveryDir `
    "${sourceDatabase}_${timestamp}.dump"

$resultCsv = Join-Path `
    $recoveryDir `
    "postgres_backup_restore_results.csv"

$manifestFile = Join-Path `
    $recoveryDir `
    "postgres_backup_manifest.json"

$summaryFile = Join-Path `
    $recoveryDir `
    "postgres_backup_restore_summary.txt"

$results = New-Object System.Collections.Generic.List[object]
$backendWasRunning = $false
$restoreCreated = $false

function Add-Result {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Test,
        [Parameter(Mandatory = $true)]
        [string]$Expected,
        [Parameter(Mandatory = $true)]
        [string]$Actual,
        [Parameter(Mandatory = $true)]
        [bool]$Passed
    )

    $results.Add(
        [pscustomobject]@{
            Test = $Test
            Expected = $Expected
            Actual = $Actual
            Passed = $Passed
        }
    )

    $state = if ($Passed) { "PASS" } else { "FAIL" }

    Write-Host (
        "{0,-38} {1} (expected {2}, got {3})" -f `
            $Test,
            $state,
            $Expected,
            $Actual
    )
}

function Invoke-PsqlScalar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Database,
        [Parameter(Mandatory = $true)]
        [string]$Sql
    )

    $output = docker compose exec -T postgres psql `
        -U $postgresUser `
        -d $Database `
        -tA `
        -P pager=off `
        -c $Sql

    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL query failed for database: $Database"
    }

    return ($output | Out-String).Trim()
}

function Remove-RestoreDatabase {
    if (-not $restoreCreated) {
        return
    }

    docker compose exec -T postgres psql `
        -U $postgresUser `
        -d postgres `
        -v ON_ERROR_STOP=1 `
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$restoreDatabase' AND pid <> pg_backend_pid();" |
        Out-Null

    docker compose exec -T postgres dropdb `
        -U $postgresUser `
        --if-exists `
        $restoreDatabase

    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Unable to drop temporary restore database: $restoreDatabase"
    }
    else {
        $script:restoreCreated = $false
    }
}

try {
    Write-Host "=== PRE-FLIGHT ==="

    $postgresContainer = (
        docker compose ps -q postgres
    ).Trim()

    if (-not $postgresContainer) {
        throw "PostgreSQL container is not running."
    }

    $backendContainer = (
        docker compose ps -q backend
    ).Trim()

    $backendWasRunning = [bool]$backendContainer

    Add-Result `
        -Test "PostgreSQL container" `
        -Expected "running" `
        -Actual "running" `
        -Passed $true

    if ($backendWasRunning) {
        Write-Host "Stopping backend to create a consistent backup..."
        docker compose stop backend

        if ($LASTEXITCODE -ne 0) {
            throw "Unable to stop backend."
        }
    }

    $sourceTableCount = [int](
        Invoke-PsqlScalar `
            -Database $sourceDatabase `
            -Sql "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public';"
    )

    $sourceConstraintCount = [int](
        Invoke-PsqlScalar `
            -Database $sourceDatabase `
            -Sql "SELECT COUNT(*) FROM pg_constraint WHERE connamespace = 'public'::regnamespace;"
    )

    $sourceIndexCount = [int](
        Invoke-PsqlScalar `
            -Database $sourceDatabase `
            -Sql "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';"
    )

    Write-Host "`n=== BACKUP ==="

    docker compose exec -T postgres pg_dump `
        -U $postgresUser `
        -d $sourceDatabase `
        --format=custom `
        --compress=6 `
        --no-owner `
        --no-privileges `
        --file=$containerDump

    if ($LASTEXITCODE -ne 0) {
        throw "pg_dump failed."
    }

    docker cp `
        "${postgresContainer}:$containerDump" `
        $hostDump

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to copy backup from the PostgreSQL container."
    }

    docker compose exec -T postgres rm -f $containerDump |
        Out-Null

    $dumpExists = Test-Path $hostDump
    $dumpSize = if ($dumpExists) {
        (Get-Item $hostDump).Length
    }
    else {
        0
    }

    Add-Result `
        -Test "Backup file created" `
        -Expected "non-empty file" `
        -Actual "$dumpSize bytes" `
        -Passed ($dumpExists -and $dumpSize -gt 0)

    if (-not $dumpExists -or $dumpSize -le 0) {
        throw "Backup file is missing or empty."
    }

    $dumpHash = (
        Get-FileHash `
            -Path $hostDump `
            -Algorithm SHA256
    ).Hash.ToLowerInvariant()

    Add-Result `
        -Test "Backup SHA-256" `
        -Expected "64 hexadecimal characters" `
        -Actual $dumpHash `
        -Passed ($dumpHash -match "^[a-f0-9]{64}$")

    docker compose exec -T postgres pg_restore `
        --list `
        $containerDump 2>$null |
        Out-Null

    # The archive was already removed from the container, so validate
    # the host archive by copying it back temporarily.
    docker cp `
        $hostDump `
        "${postgresContainer}:$containerDump"

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to copy the backup archive back into the container."
    }

    docker compose exec -T postgres pg_restore `
        --list `
        $containerDump |
        Out-Null

    Add-Result `
        -Test "Archive readability" `
        -Expected "readable pg_restore archive" `
        -Actual (
            if ($LASTEXITCODE -eq 0) {
                "readable"
            }
            else {
                "unreadable"
            }
        ) `
        -Passed ($LASTEXITCODE -eq 0)

    if ($LASTEXITCODE -ne 0) {
        throw "The backup archive is not readable."
    }

    Write-Host "`n=== TEMPORARY RESTORE ==="

    docker compose exec -T postgres psql `
        -U $postgresUser `
        -d postgres `
        -v ON_ERROR_STOP=1 `
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$restoreDatabase' AND pid <> pg_backend_pid();" |
        Out-Null

    docker compose exec -T postgres dropdb `
        -U $postgresUser `
        --if-exists `
        $restoreDatabase |
        Out-Null

    docker compose exec -T postgres createdb `
        -U $postgresUser `
        $restoreDatabase

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create temporary restore database."
    }

    $restoreCreated = $true

    docker compose exec -T postgres pg_restore `
        -U $postgresUser `
        -d $restoreDatabase `
        --no-owner `
        --no-privileges `
        --exit-on-error `
        $containerDump

    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed."
    }

    Add-Result `
        -Test "Temporary restore" `
        -Expected "successful" `
        -Actual "successful" `
        -Passed $true

    $restoredTableCount = [int](
        Invoke-PsqlScalar `
            -Database $restoreDatabase `
            -Sql "SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'public';"
    )

    Add-Result `
        -Test "Public table count" `
        -Expected "$sourceTableCount" `
        -Actual "$restoredTableCount" `
        -Passed ($sourceTableCount -eq $restoredTableCount)

    $restoredConstraintCount = [int](
        Invoke-PsqlScalar `
            -Database $restoreDatabase `
            -Sql "SELECT COUNT(*) FROM pg_constraint WHERE connamespace = 'public'::regnamespace;"
    )

    Add-Result `
        -Test "Constraint count" `
        -Expected "$sourceConstraintCount" `
        -Actual "$restoredConstraintCount" `
        -Passed ($sourceConstraintCount -eq $restoredConstraintCount)

    $restoredIndexCount = [int](
        Invoke-PsqlScalar `
            -Database $restoreDatabase `
            -Sql "SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';"
    )

    Add-Result `
        -Test "Index count" `
        -Expected "$sourceIndexCount" `
        -Actual "$restoredIndexCount" `
        -Passed ($sourceIndexCount -eq $restoredIndexCount)

    Write-Host "`n=== TABLE ROW COUNTS ==="

    $tableNamesText = Invoke-PsqlScalar `
        -Database $sourceDatabase `
        -Sql "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"

    $tableNames = @(
        $tableNamesText -split "\r?\n" |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_)
            }
    )

    $matchedTables = 0
    $mismatchedTables = New-Object System.Collections.Generic.List[string]

    foreach ($tableName in $tableNames) {
        $safeTableName = $tableName.Replace('"', '""')

        $sourceCount = [long](
            Invoke-PsqlScalar `
                -Database $sourceDatabase `
                -Sql "SELECT COUNT(*) FROM public.`"$safeTableName`";"
        )

        $restoredCount = [long](
            Invoke-PsqlScalar `
                -Database $restoreDatabase `
                -Sql "SELECT COUNT(*) FROM public.`"$safeTableName`";"
        )

        $passed = $sourceCount -eq $restoredCount

        if ($passed) {
            $matchedTables++
        }
        else {
            $mismatchedTables.Add(
                "$tableName ($sourceCount != $restoredCount)"
            )
        }

        Add-Result `
            -Test "Rows: $tableName" `
            -Expected "$sourceCount" `
            -Actual "$restoredCount" `
            -Passed $passed
    }

    $manifest = [ordered]@{
        created_at_utc = (
            Get-Date
        ).ToUniversalTime().ToString("o")
        source_database = $sourceDatabase
        restore_database = $restoreDatabase
        postgres_user = $postgresUser
        backup_file = $hostDump
        backup_size_bytes = $dumpSize
        backup_sha256 = $dumpHash
        public_table_count = $sourceTableCount
        constraint_count = $sourceConstraintCount
        index_count = $sourceIndexCount
        tables_verified = $tableNames.Count
        tables_matched = $matchedTables
        mismatched_tables = @($mismatchedTables)
    }

    $manifest |
        ConvertTo-Json -Depth 5 |
        Set-Content `
            -Path $manifestFile `
            -Encoding UTF8

    $results |
        Export-Csv `
            -Path $resultCsv `
            -NoTypeInformation `
            -Encoding UTF8

    $failed = @(
        $results |
            Where-Object {
                -not $_.Passed
            }
    )

    $summaryLines = @(
        "PostgreSQL Backup and Restore Validation"
        "========================================"
        "Source database: $sourceDatabase"
        "Backup file: $hostDump"
        "Backup size: $dumpSize bytes"
        "SHA-256: $dumpHash"
        "Tables verified: $($tableNames.Count)"
        "Tables matched: $matchedTables"
        "Failed checks: $($failed.Count)"
        "Temporary restore database removed: pending cleanup"
    )

    $summaryLines |
        Set-Content `
            -Path $summaryFile `
            -Encoding UTF8

    Write-Host "`n=== POSTGRESQL RECOVERY SUMMARY ==="
    Write-Host "Total checks : $($results.Count)"
    Write-Host "Passed       : $($results.Count - $failed.Count)"
    Write-Host "Failed       : $($failed.Count)"
    Write-Host "Tables       : $matchedTables/$($tableNames.Count)"
    Write-Host "Backup       : $hostDump"
    Write-Host "SHA-256      : $dumpHash"
    Write-Host "Results CSV  : $resultCsv"
    Write-Host "Manifest     : $manifestFile"

    if ($failed.Count -gt 0) {
        throw "PostgreSQL backup and restore validation failed."
    }
}
finally {
    try {
        Remove-RestoreDatabase
    }
    catch {
        Write-Warning $_
    }

    try {
        $postgresContainer = (
            docker compose ps -q postgres
        ).Trim()

        if ($postgresContainer) {
            docker compose exec -T postgres rm -f $containerDump |
                Out-Null
        }
    }
    catch {
        Write-Warning "Unable to remove temporary container archive."
    }

    if ($backendWasRunning) {
        Write-Host "Restarting backend..."
        docker compose start backend |
            Out-Null

        Start-Sleep -Seconds 10

        try {
            $health = Invoke-RestMethod `
                -Uri "http://localhost:8000/health" `
                -TimeoutSec 15 `
                -ErrorAction Stop

            Write-Host "Backend health: $($health.status)"
        }
        catch {
            Write-Warning "Backend restarted, but the health endpoint was not reachable yet."
        }
    }
}
