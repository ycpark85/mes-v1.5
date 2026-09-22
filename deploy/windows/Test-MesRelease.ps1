[CmdletBinding()]
param(
    [string]$RepositoryRoot,
    [string]$ReportRoot,
    [switch]$RequireCleanWorktree,
    [switch]$SkipDotnetRestore
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'MesDeployment.Common.ps1')

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $RepositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
}
else {
    $RepositoryRoot = (Resolve-Path -LiteralPath $RepositoryRoot -ErrorAction Stop).Path
}
if ([string]::IsNullOrWhiteSpace($ReportRoot)) {
    $ReportRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'mes-release-validation'
}
$ReportRoot = [System.IO.Path]::GetFullPath($ReportRoot)
if (Test-MesPathOverlap -First $RepositoryRoot -Second $ReportRoot) {
    throw 'Release validation reports must be stored outside the Git repository.'
}

$backendRoot = Join-Path $RepositoryRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$solution = Join-Path $RepositoryRoot 'frontend-wpf\Mes.WpfClean\Mes.Wpf\Mes.Wpf.sln'
$requiredFiles = @(
    $python,
    $solution,
    (Join-Path $backendRoot 'alembic.ini'),
    (Join-Path $backendRoot 'scripts\validate_release_sources.py')
)
foreach ($path in $requiredFiles) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required release validation file is missing: $path"
    }
}

$timestamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$commit = (& git -C $RepositoryRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read the release Git commit.'
}
$branch = (& git -C $RepositoryRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read the release Git branch.'
}
$shortCommit = $commit.Substring(0, 8)
$runRoot = Join-Path $ReportRoot ("{0}-{1}-{2}" -f $timestamp, $shortCommit, $PID)
New-Item -ItemType Directory -Path $runRoot -Force | Out-Null

$initialGitStatus = (& git -C $RepositoryRoot status --porcelain) -join "`n"
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read the initial Git worktree state.'
}

$results = New-Object System.Collections.Generic.List[object]

function Add-MesReleaseResult {
    param(
        [string]$Name,
        [string]$Status,
        [double]$DurationSeconds,
        [string]$Summary,
        [string]$LogPath
    )
    $script:results.Add([ordered]@{
        name = $Name
        status = $Status
        duration_seconds = [Math]::Round($DurationSeconds, 3)
        summary = $Summary
        log_path = $LogPath
    })
}

function Invoke-MesReleaseCommandStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [int[]]$AllowedExitCodes = @(0),
        [int[]]$WarningExitCodes = @()
    )

    $logPath = Join-Path $runRoot ("{0}.log" -f $Name)
    $watch = [Diagnostics.Stopwatch]::StartNew()
    Write-Host "`n== $Name ==" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        $exitCode = Invoke-MesNativeCommand `
            -Executable $Executable `
            -Arguments $Arguments `
            -AllowedExitCodes $AllowedExitCodes `
            -OutputLog $logPath
        $status = if ($WarningExitCodes -contains $exitCode) { 'WARNING' } else { 'OK' }
        $summary = "Command completed with exit code $exitCode"
        Add-MesReleaseResult $Name $status $watch.Elapsed.TotalSeconds $summary $logPath
    }
    catch {
        $_.Exception.Message | Out-File -LiteralPath $logPath -Encoding UTF8 -Append
        Add-MesReleaseResult $Name 'CRITICAL' $watch.Elapsed.TotalSeconds $_.Exception.Message $logPath
    }
    finally {
        $watch.Stop()
        Pop-Location
    }
}

$oldBytecode = $env:PYTHONDONTWRITEBYTECODE
$oldTelemetry = $env:DOTNET_CLI_TELEMETRY_OPTOUT
$oldNoLogo = $env:DOTNET_NOLOGO
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'

try {
    $sourceReport = Join-Path $runRoot 'source-policy.json'
    $sourceArguments = @(
        '-m', 'scripts.validate_release_sources',
        '--repository-root', $RepositoryRoot,
        '--mode', 'source',
        '--output-json', $sourceReport,
        '--format', 'text'
    )
    if ($RequireCleanWorktree) {
        $sourceArguments += '--require-clean-worktree'
    }
    Invoke-MesReleaseCommandStep `
        -Name 'source_policy' `
        -WorkingDirectory $backendRoot `
        -Executable $python `
        -Arguments $sourceArguments `
        -AllowedExitCodes @(0, 1) `
        -WarningExitCodes @(1)

    Invoke-MesReleaseCommandStep `
        -Name 'backend_tests' `
        -WorkingDirectory $backendRoot `
        -Executable $python `
        -Arguments @('-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--junitxml', (Join-Path $runRoot 'backend-tests.xml'))

    Invoke-MesReleaseCommandStep `
        -Name 'inspection_postgres_regressions' `
        -WorkingDirectory $backendRoot `
        -Executable $python `
        -Arguments @('-m', 'scripts.inspection_regression_gate', '--report', (Join-Path $runRoot 'backend-tests.xml'))

    Invoke-MesReleaseCommandStep `
        -Name 'alembic_head' `
        -WorkingDirectory $backendRoot `
        -Executable $python `
        -Arguments @('-m', 'alembic', 'current', '--check-heads')

    Invoke-MesReleaseCommandStep `
        -Name 'alembic_metadata' `
        -WorkingDirectory $backendRoot `
        -Executable $python `
        -Arguments @('-m', 'alembic', 'check')

    if ($SkipDotnetRestore) {
        Add-MesReleaseResult `
            'dotnet_restore' `
            'WARNING' `
            0 `
            'NuGet restore was explicitly skipped' `
            ''
    }
    else {
        Invoke-MesReleaseCommandStep `
            -Name 'dotnet_restore' `
            -WorkingDirectory $RepositoryRoot `
            -Executable 'dotnet' `
            -Arguments @('restore', $solution, '--nologo')
    }

    Invoke-MesReleaseCommandStep `
        -Name 'wpf_release_build' `
        -WorkingDirectory $RepositoryRoot `
        -Executable 'dotnet' `
        -Arguments @('build', $solution, '-c', 'Release', '--no-restore', '--nologo')

    foreach ($regression in @('InspectionRegression', 'ApiRegression')) {
        $project = Join-Path $RepositoryRoot "frontend-wpf\tests\$regression\$regression.csproj"
        $arguments = @('run', '--project', $project, '-c', 'Release', '--no-launch-profile', '--verbosity', 'quiet')
        if ($SkipDotnetRestore) { $arguments += '--no-restore' }
        Invoke-MesReleaseCommandStep `
            -Name "wpf_$regression" `
            -WorkingDirectory $RepositoryRoot `
            -Executable 'dotnet' `
            -Arguments $arguments
    }

    Invoke-MesReleaseCommandStep `
        -Name 'wpf_release_output' `
        -WorkingDirectory $backendRoot `
        -Executable $python `
        -Arguments @(
            '-m', 'scripts.validate_release_sources',
            '--repository-root', $RepositoryRoot,
            '--mode', 'built-output',
            '--output-json', (Join-Path $runRoot 'wpf-output.json'),
            '--format', 'text'
        )
}
finally {
    $env:PYTHONDONTWRITEBYTECODE = $oldBytecode
    $env:DOTNET_CLI_TELEMETRY_OPTOUT = $oldTelemetry
    $env:DOTNET_NOLOGO = $oldNoLogo
}

$finalGitStatus = (& git -C $RepositoryRoot status --porcelain) -join "`n"
$gitWatch = [Diagnostics.Stopwatch]::StartNew()
if ($LASTEXITCODE -ne 0) {
    Add-MesReleaseResult 'validation_worktree_integrity' 'CRITICAL' 0 'Unable to read final Git status' ''
}
elseif ($initialGitStatus -ceq $finalGitStatus) {
    Add-MesReleaseResult 'validation_worktree_integrity' 'OK' $gitWatch.Elapsed.TotalSeconds 'Validation did not change tracked source state' ''
}
else {
    Add-MesReleaseResult 'validation_worktree_integrity' 'CRITICAL' $gitWatch.Elapsed.TotalSeconds 'Validation changed the Git worktree state' ''
}
$gitWatch.Stop()

$overallCode = 0
foreach ($result in $results) {
    if ($result.status -eq 'CRITICAL') {
        $overallCode = 2
        break
    }
    if ($result.status -eq 'WARNING') {
        $overallCode = [Math]::Max($overallCode, 1)
    }
}
$overallStatus = if ($overallCode -eq 2) { 'CRITICAL' } elseif ($overallCode -eq 1) { 'WARNING' } else { 'OK' }
$report = [ordered]@{
    format_version = 1
    generated_at_utc = [DateTime]::UtcNow.ToString('o')
    overall_status = $overallStatus
    exit_code = $overallCode
    repository_root = $RepositoryRoot
    branch = $branch
    commit = $commit
    clean_worktree_required = [bool]$RequireCleanWorktree
    dotnet_restore_skipped = [bool]$SkipDotnetRestore
    results = $results
}
$reportPath = Join-Path $runRoot 'release-validation.json'
$temporaryReport = "$reportPath.tmp"
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryReport -Encoding UTF8
Move-Item -LiteralPath $temporaryReport -Destination $reportPath -Force

Write-Host "`nMES release validation: $overallStatus" -ForegroundColor $(if ($overallCode -eq 2) { 'Red' } elseif ($overallCode -eq 1) { 'Yellow' } else { 'Green' })
foreach ($result in $results) {
    Write-Host ("[{0}] {1}: {2}" -f $result.status, $result.name, $result.summary)
}
Write-Host "release_validation_report=$reportPath"
exit $overallCode
