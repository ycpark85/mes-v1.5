[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$HostAddress = '127.0.0.1',

    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [switch]$NoReload
)

$ErrorActionPreference = 'Stop'

$backendRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$envPath = Join-Path $backendRoot '.env'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Python virtual environment was not found: $pythonPath"
}
if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "Backend environment file was not found: $envPath"
}

$arguments = @(
    '-m', 'uvicorn', 'app.main:app',
    '--host', $HostAddress,
    '--port', $Port.ToString()
)
if (-not $NoReload) {
    $arguments += '--reload'
}

Push-Location $backendRoot
try {
    & $pythonPath @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Development backend exited with code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
