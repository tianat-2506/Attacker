param(
    [string]$ContainerName = "vietsupply-rls-smoke",
    [int]$Port = 55432,
    [string]$Database = "vietsupply_smoke",
    [string]$User = "vietsupply",
    [string]$Password = "vietsupply-smoke-password",
    [switch]$KeepContainer
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. Install Docker Desktop or provide POSTGRES_TEST_DATABASE_URL to scripts/postgres_rls_smoke.py."
    }
}

Require-Command "docker"

$existing = docker ps -a --filter "name=^/$ContainerName$" --format "{{.Names}}"
if ($existing -eq $ContainerName) {
    docker rm -f $ContainerName | Out-Null
}

docker run `
    --name $ContainerName `
    -e "POSTGRES_DB=$Database" `
    -e "POSTGRES_USER=$User" `
    -e "POSTGRES_PASSWORD=$Password" `
    -p "${Port}:5432" `
    -d `
    postgis/postgis:16-3.4 | Out-Null

try {
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Seconds 2
        $ready = docker exec $ContainerName pg_isready -U $User -d $Database 2>$null
        if ($LASTEXITCODE -eq 0) {
            break
        }
    } while ((Get-Date) -lt $deadline)

    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL container did not become ready within 60 seconds."
    }

    $databaseUrl = "postgresql://$User`:$Password@localhost:$Port/$Database"
    python -B scripts/postgres_rls_smoke.py --database-url $databaseUrl
}
finally {
    if (-not $KeepContainer) {
        docker rm -f $ContainerName | Out-Null
    }
}
