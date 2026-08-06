[CmdletBinding()]
param(
    [string]$BackendRoot = 'C:\mes\backend',
    [string]$BackupRoot = 'C:\mes\deploy-backups\inspection-cleanup',
    [switch]$DryRunOnly,
    [Nullable[int]]$ExpectedCount
)

$ErrorActionPreference = 'Stop'

$pythonPath = Join-Path $BackendRoot '.venv\Scripts\python.exe'
$cleanupScript = Join-Path $BackendRoot 'scripts\cleanup_legacy_canceled_inspection_schedules.py'

foreach ($requiredPath in @($BackendRoot, $pythonPath, $cleanupScript)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required cleanup path was not found: $requiredPath"
    }
}

function Invoke-CleanupScript {
    param([string[]]$Arguments)

    Push-Location $BackendRoot
    try {
        $output = @(& $pythonPath $cleanupScript @Arguments)
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($exitCode -notin @(0, 2)) {
        throw "Inspection-schedule cleanup script failed with exit code $exitCode."
    }

    $jsonText = $output -join [Environment]::NewLine
    if ([string]::IsNullOrWhiteSpace($jsonText)) {
        throw 'Inspection-schedule cleanup script returned no report.'
    }

    try {
        return $jsonText | ConvertFrom-Json
    }
    catch {
        throw "Unable to parse cleanup report: $jsonText"
    }
}

Write-Host 'Inspecting legacy canceled outsource inspection schedules...'
$dryRun = Invoke-CleanupScript -Arguments @('--preview-limit', '10000')

Write-Host "APP_ENV: $($dryRun.app_env)"
Write-Host "Database: $($dryRun.database)"
Write-Host "Candidates: $($dryRun.candidate_count)"
Write-Host "Safe: $($dryRun.safe_count)"
Write-Host "Blocked: $($dryRun.blocked_count)"

if ($dryRun.rows.Count -gt 0) {
    $dryRun.rows |
        Select-Object `
            inspection_schedule_id,
            lot_no,
            inspection_date,
            outsource_work_group_id,
            blocked_reasons |
        Format-Table -AutoSize
}

if ([int]$dryRun.blocked_count -gt 0) {
    throw 'Referenced schedules exist. No rows were deleted.'
}

if ([int]$dryRun.safe_count -eq 0) {
    Write-Host 'No cleanup target exists. No rows were deleted.'
    exit 0
}

if ($DryRunOnly) {
    Write-Host 'Dry-run completed. No rows were deleted.'
    exit 0
}

$safeCount = [int]$dryRun.safe_count
if ($null -eq $ExpectedCount) {
    $confirmation = Read-Host "To delete these rows, enter the exact safe count ($safeCount)"
    if ($confirmation -notmatch '^\d+$' -or [int]$confirmation -ne $safeCount) {
        throw 'Confirmation count did not match. No rows were deleted.'
    }
}
elseif ($ExpectedCount.Value -ne $safeCount) {
    throw (
        "ExpectedCount did not match the dry-run result: " +
        "expected=$($ExpectedCount.Value), actual=$safeCount"
    )
}

Write-Host 'Creating a recovery snapshot and applying cleanup...'
$applyReport = Invoke-CleanupScript -Arguments @(
    '--apply',
    '--expected-count', [string]$safeCount,
    '--expected-app-env', [string]$dryRun.app_env,
    '--expected-database', [string]$dryRun.database,
    '--backup-root', $BackupRoot,
    '--preview-limit', '10000'
)

if (-not $applyReport.applied -or [int]$applyReport.deleted_count -ne $safeCount) {
    throw 'Cleanup apply report did not match the approved target count.'
}
if (-not (Test-Path -LiteralPath $applyReport.backup_path)) {
    throw "Cleanup backup file was not found: $($applyReport.backup_path)"
}

$postCheck = Invoke-CleanupScript -Arguments @('--preview-limit', '10000')
if (
    [int]$postCheck.candidate_count -ne 0 -or
    [int]$postCheck.safe_count -ne 0 -or
    [int]$postCheck.blocked_count -ne 0
) {
    throw 'Post-cleanup verification failed because legacy candidates remain.'
}

Write-Host 'Legacy canceled inspection-schedule cleanup completed successfully.'
Write-Host "Deleted rows: $($applyReport.deleted_count)"
Write-Host "Recovery snapshot: $($applyReport.backup_path)"
