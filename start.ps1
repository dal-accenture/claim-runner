# Starts all claim-runner services in dependency order.
# Data Service must be healthy before adjudication services are started.
# Run from repository root.

param()

$DataPort     = if ($env:DATA_PORT)     { $env:DATA_PORT }     else { "8083" }
$BenefitsPort = if ($env:BENEFITS_PORT) { $env:BENEFITS_PORT } else { "8081" }
$PricerPort   = if ($env:PRICER_PORT)   { $env:PRICER_PORT }   else { "8082" }
$ClaimsPort   = if ($env:CLAIMS_PORT)   { $env:CLAIMS_PORT }   else { "8080" }

function Wait-ForHealth {
    param([string]$Url, [string]$ServiceName, [int]$MaxSeconds = 30)
    Write-Host "Waiting for $ServiceName at $Url ..."
    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        try {
            Invoke-RestMethod -Uri $Url -Method Get -ErrorAction Stop | Out-Null
            Write-Host "$ServiceName is UP."
            return
        } catch { }
        Start-Sleep -Seconds 1
    }
    Write-Error "ERROR: $ServiceName did not become healthy within $MaxSeconds seconds."
    exit 1
}

# --- 1. Data Service (no upstream dependencies) ---
Write-Host "Starting Data Service on port $DataPort ..."
$env:PORT = $DataPort
$dataJob = Start-Job -ScriptBlock {
    param($port, $repoRoot)
    Set-Location (Join-Path $repoRoot "data_service")
    $env:PORT = $port
    python -m uvicorn main:app --host 0.0.0.0 --port $port
} -ArgumentList $DataPort, $PSScriptRoot

Wait-ForHealth "http://localhost:$DataPort/health" "Data Service"

# --- 2. Benefits Determiner (depends on Data Service) ---
Write-Host "Starting Benefits Determiner on port $BenefitsPort ..."
$benefitsJob = Start-Job -ScriptBlock {
    param($port, $repoRoot)
    Set-Location $repoRoot
    $env:PORT = $port
    python -m uvicorn benefits_determiner.main:app --host 0.0.0.0 --port $port
} -ArgumentList $BenefitsPort, $PSScriptRoot

Wait-ForHealth "http://localhost:$BenefitsPort/health" "Benefits Determiner"

# --- 3. Pricer (depends on Data Service) ---
Write-Host "Starting Pricer on port $PricerPort ..."
$pricerJob = Start-Job -ScriptBlock {
    param($port, $repoRoot)
    Set-Location $repoRoot
    $env:PORT = $port
    python -m uvicorn pricer.main:app --host 0.0.0.0 --port $port
} -ArgumentList $PricerPort, $PSScriptRoot

Wait-ForHealth "http://localhost:$PricerPort/health" "Pricer"

# --- 4. Claims Manager (depends on Benefits Determiner + Pricer) ---
Write-Host "Starting Claims Manager on port $ClaimsPort ..."
$claimsJob = Start-Job -ScriptBlock {
    param($port, $repoRoot)
    Set-Location $repoRoot
    $env:PORT = $port
    python -m uvicorn claims_manager.main:app --host 0.0.0.0 --port $port
} -ArgumentList $ClaimsPort, $PSScriptRoot

Wait-ForHealth "http://localhost:$ClaimsPort/health" "Claims Manager"

Write-Host "All services started. Press Ctrl+C to stop."
try {
    Wait-Job $dataJob, $benefitsJob, $pricerJob, $claimsJob | Out-Null
} finally {
    Get-Job | Stop-Job
    Get-Job | Remove-Job
}
