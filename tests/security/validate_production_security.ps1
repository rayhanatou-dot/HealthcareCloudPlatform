param(
    [string]$ProjectRoot = "C:\Users\ASUS\healthcare-cloud-platform"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$envFile = Join-Path $ProjectRoot ".env"
$backupFile = Join-Path $ProjectRoot ".env.production-test-backup"
$resultsDir = Join-Path $ProjectRoot "tests\security"
$headersFile = Join-Path $resultsDir "production_health_headers.txt"
$summaryFile = Join-Path $resultsDir "production_security_results.csv"

New-Item -ItemType Directory -Force $resultsDir | Out-Null

if (-not (Test-Path $envFile)) {
    throw "Missing .env file: $envFile"
}

function Set-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    $lines = Get-Content $Path
    $pattern = "^\s*" + [regex]::Escape($Name) + "="
    $updated = $false

    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -match $pattern) {
            $lines[$index] = "$Name=$Value"
            $updated = $true
            break
        }
    }

    if (-not $updated) {
        $lines += "$Name=$Value"
    }

    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)

    [System.IO.File]::WriteAllLines(
        $Path,
        $lines,
        $utf8NoBom
    )
}

function Wait-ForHealth {
    param(
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do {
        try {
            $response = Invoke-RestMethod `
                -Uri "http://localhost:8000/health" `
                -TimeoutSec 5 `
                -ErrorAction Stop

            if ($response.status -eq "healthy") {
                return
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    throw "Backend did not become healthy within $TimeoutSeconds seconds."
}

function Add-Result {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Test,
        [string]$Expected,
        [string]$Actual,
        [bool]$Passed
    )

    $Results.Add(
        [PSCustomObject]@{
            Test = $Test
            Expected = $Expected
            Actual = $Actual
            Passed = $Passed
        }
    )
}

$results = [System.Collections.Generic.List[object]]::new()
$restored = $false

Copy-Item $envFile $backupFile -Force

try {
    Set-DotEnvValue -Path $envFile -Name "APP_ENV" -Value "production"
    Set-DotEnvValue -Path $envFile -Name "DOCS_ENABLED" -Value "false"

    docker compose up -d --force-recreate backend

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to recreate backend in production mode."
    }

    Wait-ForHealth

    curl.exe `
        -s `
        -D $headersFile `
        -o NUL `
        "http://localhost:8000/health"

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to retrieve production response headers."
    }

    $headers = Get-Content $headersFile -Raw

    Add-Result `
        -Results $results `
        -Test "X-Content-Type-Options" `
        -Expected "nosniff" `
        -Actual $(if ($headers -match "(?im)^x-content-type-options:\s*nosniff\s*$") { "nosniff" } else { "missing" }) `
        -Passed ($headers -match "(?im)^x-content-type-options:\s*nosniff\s*$")

    Add-Result `
        -Results $results `
        -Test "X-Frame-Options" `
        -Expected "DENY" `
        -Actual $(if ($headers -match "(?im)^x-frame-options:\s*DENY\s*$") { "DENY" } else { "missing" }) `
        -Passed ($headers -match "(?im)^x-frame-options:\s*DENY\s*$")

    Add-Result `
        -Results $results `
        -Test "Content-Security-Policy" `
        -Expected "present" `
        -Actual $(if ($headers -match "(?im)^content-security-policy:") { "present" } else { "missing" }) `
        -Passed ($headers -match "(?im)^content-security-policy:")

    Add-Result `
        -Results $results `
        -Test "Strict-Transport-Security" `
        -Expected "present" `
        -Actual $(if ($headers -match "(?im)^strict-transport-security:") { "present" } else { "missing" }) `
        -Passed ($headers -match "(?im)^strict-transport-security:")

    Add-Result `
        -Results $results `
        -Test "Uvicorn server header" `
        -Expected "absent" `
        -Actual $(if ($headers -match "(?im)^server:\s*uvicorn\s*$") { "present" } else { "absent" }) `
        -Passed (-not ($headers -match "(?im)^server:\s*uvicorn\s*$"))

    $swaggerStatus = (
        & curl.exe -s -o NUL -w "%{http_code}" "http://localhost:8000/docs"
    ).Trim()

    $openApiStatus = (
        & curl.exe -s -o NUL -w "%{http_code}" "http://localhost:8000/openapi.json"
    ).Trim()

    $redocStatus = (
        & curl.exe -s -o NUL -w "%{http_code}" "http://localhost:8000/redoc"
    ).Trim()

    Add-Result `
        -Results $results `
        -Test "Swagger disabled" `
        -Expected "404" `
        -Actual $swaggerStatus `
        -Passed ($swaggerStatus -eq "404")

    Add-Result `
        -Results $results `
        -Test "OpenAPI schema disabled" `
        -Expected "404" `
        -Actual $openApiStatus `
        -Passed ($openApiStatus -eq "404")

    Add-Result `
        -Results $results `
        -Test "ReDoc disabled" `
        -Expected "404" `
        -Actual $redocStatus `
        -Passed ($redocStatus -eq "404")

    $untrustedHostStatus = (
        & curl.exe `
            -s `
            -o NUL `
            -w "%{http_code}" `
            -H "Host: malicious.example" `
            "http://127.0.0.1:8000/health"
    ).Trim()

    Add-Result `
        -Results $results `
        -Test "Untrusted Host rejected" `
        -Expected "400" `
        -Actual $untrustedHostStatus `
        -Passed ($untrustedHostStatus -eq "400")

    $results |
        Export-Csv `
            -Path $summaryFile `
            -NoTypeInformation `
            -Encoding UTF8
}
finally {
    if (Test-Path $backupFile) {
        Copy-Item $backupFile $envFile -Force
        Remove-Item $backupFile -Force
        $restored = $true

        docker compose up -d --force-recreate backend | Out-Null
        Wait-ForHealth
    }
}

Write-Host "`n=== PRODUCTION SECURITY TEST SUMMARY ==="

$results |
    Format-Table `
        Test,
        Expected,
        Actual,
        Passed `
        -AutoSize

$failedCount = @(
    $results | Where-Object { -not $_.Passed }
).Count

Write-Host "`nTotal checks :" $results.Count
Write-Host "Passed       :" ($results.Count - $failedCount)
Write-Host "Failed       :" $failedCount
Write-Host "Environment restored:" $restored
Write-Host "Results file :" $summaryFile

if ($failedCount -gt 0) {
    exit 1
}
