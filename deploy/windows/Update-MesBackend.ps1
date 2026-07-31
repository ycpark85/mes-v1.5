[CmdletBinding()]
param(
    [ValidateNotNullOrEmpty()]
    [string]$RepositoryRoot = 'C:\mes',

    [ValidateNotNullOrEmpty()]
    [string]$Branch = 'main',

    [ValidateNotNullOrEmpty()]
    [string]$ExpectedRemoteUrl = 'https://github.com/ycpark85/mes-v1.5.git',

    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8000,

    [string]$BackupCommandPath = '',

    [switch]$Apply,

    [switch]$ApplyMigration,

    [switch]$SkipBackup
)

$ErrorActionPreference = 'Stop'

if ($ApplyMigration -and -not $Apply) {
    throw '-ApplyMigration requires -Apply.'
}

$repository = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$backendRoot = Join-Path $repository 'backend'
$pythonPath = Join-Path $backendRoot '.venv\Scripts\python.exe'
$envPath = Join-Path $backendRoot '.env'
$requirementsPath = Join-Path $backendRoot 'requirements.txt'

foreach ($requiredPath in @($backendRoot, $pythonPath, $envPath, $requirementsPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required path was not found: $requiredPath"
    }
}

function Invoke-Git {
    param([Parameter(Mandatory)][string[]]$Arguments)

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& git -C $repository @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    if ($exitCode -ne 0) {
        $details = $output -join [Environment]::NewLine
        throw "git $($Arguments -join ' ') failed:$([Environment]::NewLine)$details"
    }
    return $output
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments
    )

    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output = $output
    }
}

function Normalize-GitUrl {
    param([Parameter(Mandatory)][string]$Url)

    return $Url.Trim().TrimEnd('/').ToLowerInvariant() -replace '\.git$', ''
}

$remoteUrl = (Invoke-Git -Arguments @('remote', 'get-url', 'origin') | Select-Object -First 1).Trim()
if ((Normalize-GitUrl $remoteUrl) -ne (Normalize-GitUrl $ExpectedRemoteUrl)) {
    throw "origin is not the mes-v1.5 repository: $remoteUrl"
}

$currentBranch = (Invoke-Git -Arguments @('branch', '--show-current') | Select-Object -First 1).Trim()
if ($currentBranch -ne $Branch) {
    throw "Current branch must be '$Branch': $currentBranch"
}

$trackedChanges = @(Invoke-Git -Arguments @('status', '--porcelain', '--untracked-files=no'))
if ($trackedChanges.Count -gt 0) {
    $details = $trackedChanges -join [Environment]::NewLine
    throw "Tracked local changes block deployment:$([Environment]::NewLine)$details"
}

Invoke-Git -Arguments @('fetch', '--prune', 'origin', $Branch) | Out-Null

$currentCommit = (Invoke-Git -Arguments @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
$targetCommit = (Invoke-Git -Arguments @('rev-parse', "origin/$Branch") | Select-Object -First 1).Trim()

$ancestorCheck = Invoke-NativeCommand -FilePath 'git' -Arguments @(
    '-C', $repository, 'merge-base', '--is-ancestor', $currentCommit, $targetCommit
)
if ($ancestorCheck.ExitCode -ne 0) {
    throw 'origin/main is not a fast-forward continuation of the deployed commit.'
}

$listeners = @(Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue)
$apiRunning = $listeners.Count -gt 0

Write-Output "Repository=$repository"
Write-Output "Branch=$Branch"
Write-Output "CurrentCommit=$currentCommit"
Write-Output "TargetCommit=$targetCommit"
Write-Output "ApiPortInUse=$apiRunning"
Write-Output "Apply=$Apply"

if (-not $Apply) {
    Write-Output 'PLAN_ONLY=TRUE'
    return
}

if ($apiRunning) {
    throw "API port $ApiPort is still in use. Stop the backend before deployment."
}

if ($currentCommit -eq $targetCommit) {
    Write-Output 'NO_CHANGES=TRUE'
    return
}

if (-not $SkipBackup) {
    if ([string]::IsNullOrWhiteSpace($BackupCommandPath)) {
        $BackupCommandPath = Join-Path $repository 'backup_mes_db.cmd'
    }
    if (-not (Test-Path -LiteralPath $BackupCommandPath -PathType Leaf)) {
        throw "Database backup command was not found: $BackupCommandPath"
    }

    & $BackupCommandPath
    if ($LASTEXITCODE -ne 0) {
        throw "Database backup failed: $BackupCommandPath"
    }
}

Invoke-Git -Arguments @('pull', '--ff-only', 'origin', $Branch) | Out-Null

Push-Location $backendRoot
try {
    $pipResult = Invoke-NativeCommand -FilePath $pythonPath -Arguments @(
        '-m', 'pip', 'install', '--disable-pip-version-check', '-r', $requirementsPath
    )
    $pipResult.Output | Write-Output
    if ($pipResult.ExitCode -ne 0) {
        throw 'Backend dependency installation failed.'
    }

    $headsResult = Invoke-NativeCommand -FilePath $pythonPath -Arguments @('-m', 'alembic', 'heads')
    if ($headsResult.ExitCode -ne 0) {
        $details = $headsResult.Output -join [Environment]::NewLine
        throw "Alembic heads failed:$([Environment]::NewLine)$details"
    }
    $headMatches = @($headsResult.Output | Select-String -Pattern '^\s*([0-9a-f]+)\s+\(head\)')
    if ($headMatches.Count -ne 1) {
        $details = $headsResult.Output -join [Environment]::NewLine
        throw "Exactly one Alembic head is required:$([Environment]::NewLine)$details"
    }
    $headRevision = $headMatches[0].Matches[0].Groups[1].Value

    $currentResult = Invoke-NativeCommand -FilePath $pythonPath -Arguments @('-m', 'alembic', 'current')
    if ($currentResult.ExitCode -ne 0) {
        $details = $currentResult.Output -join [Environment]::NewLine
        throw "Alembic current failed:$([Environment]::NewLine)$details"
    }
    $currentMatch = $currentResult.Output | Select-String -Pattern '^\s*([0-9a-f]+)' | Select-Object -First 1
    $currentRevision = if ($currentMatch) { $currentMatch.Matches[0].Groups[1].Value } else { '' }

    if ($currentRevision -ne $headRevision) {
        if (-not $ApplyMigration) {
            throw "Database revision '$currentRevision' differs from code head '$headRevision'. Re-run only after review with -ApplyMigration."
        }

        $migrationResult = Invoke-NativeCommand -FilePath $pythonPath -Arguments @(
            '-m', 'alembic', 'upgrade', 'head'
        )
        $migrationResult.Output | Write-Output
        if ($migrationResult.ExitCode -ne 0) {
            throw 'Alembic migration failed. Do not run an automatic downgrade.'
        }
    }

    $importResult = Invoke-NativeCommand -FilePath $pythonPath -Arguments @(
        '-B', '-c', 'from app.main import app; print(app.title)'
    )
    $importResult.Output | Write-Output
    if ($importResult.ExitCode -ne 0) {
        throw 'Backend import smoke check failed.'
    }
}
finally {
    Pop-Location
}

$deployedCommit = (Invoke-Git -Arguments @('rev-parse', 'HEAD') | Select-Object -First 1).Trim()
Write-Output "DEPLOYED_COMMIT=$deployedCommit"
Write-Output "START_COMMAND=$(Join-Path $repository 'run_mes_api.cmd')"
Write-Output "HEALTH_URL=http://127.0.0.1:$ApiPort/api/v1/health"
