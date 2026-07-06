param(
    [string]$NetworkName = "vietsupply-evidence-smoke-net",
    [string]$MinioContainerName = "vietsupply-minio-smoke",
    [string]$ClamAvContainerName = "vietsupply-clamav-smoke",
    [int]$MinioPort = 59000,
    [int]$MinioConsolePort = 59001,
    [int]$ClamAvPort = 53310,
    [string]$Bucket = "vietsupply-evidence-smoke",
    [string]$AccessKey = "vietsupply-smoke-access",
    [string]$SecretKey = "vietsupply-smoke-secret-12345",
    [int]$MinioStartupSeconds = 60,
    [int]$ClamAvStartupSeconds = 240,
    [switch]$RunReadinessGate,
    [switch]$KeepContainers
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. Install Docker Desktop or configure external S3/MinIO and ClamAV, then run scripts/run_evidence_object_storage_smoke.py and scripts/run_clamav_smoke.py directly."
    }
}

function Remove-ContainerIfExists($Name) {
    $existing = docker ps -a --filter "name=^/$Name$" --format "{{.Names}}"
    if ($existing -eq $Name) {
        docker rm -f $Name | Out-Null
    }
}

function Remove-NetworkIfExists($Name) {
    $existing = docker network ls --filter "name=^$Name$" --format "{{.Name}}"
    if ($existing -eq $Name) {
        docker network rm $Name | Out-Null
    }
}

function Wait-ForHttp($Url, $TimeoutSeconds, $Name) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become ready within $TimeoutSeconds seconds."
}

function Wait-ForClamAv($TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        python -B scripts/run_clamav_smoke.py --json *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)
    throw "ClamAV did not pass clean/EICAR smoke within $TimeoutSeconds seconds."
}

Require-Command "docker"

Remove-ContainerIfExists $MinioContainerName
Remove-ContainerIfExists $ClamAvContainerName
Remove-NetworkIfExists $NetworkName

docker network create $NetworkName | Out-Null

docker run `
    --name $MinioContainerName `
    --network $NetworkName `
    -e "MINIO_ROOT_USER=$AccessKey" `
    -e "MINIO_ROOT_PASSWORD=$SecretKey" `
    -p "${MinioPort}:9000" `
    -p "${MinioConsolePort}:9001" `
    -d `
    minio/minio:latest server /data --console-address ":9001" | Out-Null

docker run `
    --name $ClamAvContainerName `
    --network $NetworkName `
    -p "${ClamAvPort}:3310" `
    -d `
    clamav/clamav:stable | Out-Null

try {
    Wait-ForHttp "http://127.0.0.1:$MinioPort/minio/health/ready" $MinioStartupSeconds "MinIO"

    docker run --rm --network $NetworkName minio/mc:latest `
        sh -c "mc alias set local http://$MinioContainerName`:9000 $AccessKey $SecretKey >/dev/null && mc mb -p local/$Bucket >/dev/null || true" | Out-Null

    $env:EVIDENCE_OBJECT_STORE_ENDPOINT = "http://127.0.0.1:$MinioPort"
    $env:EVIDENCE_OBJECT_STORE_BUCKET = $Bucket
    $env:EVIDENCE_OBJECT_STORE_ACCESS_KEY_ID = $AccessKey
    $env:EVIDENCE_OBJECT_STORE_SECRET_ACCESS_KEY = $SecretKey
    $env:EVIDENCE_OBJECT_STORE_REGION = "us-east-1"
    $env:EVIDENCE_MALWARE_SCANNER = "clamav"
    $env:CLAMAV_HOST = "127.0.0.1"
    $env:CLAMAV_PORT = "$ClamAvPort"

    python -B scripts/run_evidence_object_storage_smoke.py --json
    if ($LASTEXITCODE -ne 0) {
        throw "Evidence object storage smoke failed."
    }

    Wait-ForClamAv $ClamAvStartupSeconds
    python -B scripts/run_clamav_smoke.py --json
    if ($LASTEXITCODE -ne 0) {
        throw "ClamAV smoke failed."
    }

    if ($RunReadinessGate) {
        $env:EVIDENCE_OBJECT_STORAGE_LIVE_SMOKE = "1"
        $env:EVIDENCE_MALWARE_SCANNER_LIVE_SMOKE = "1"
        python -B scripts/run_trust_readiness_gate.py --allow-missing-live --json
    }
}
finally {
    if (-not $KeepContainers) {
        docker rm -f $MinioContainerName $ClamAvContainerName 2>$null | Out-Null
        docker network rm $NetworkName 2>$null | Out-Null
    }
}
