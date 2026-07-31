[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputRoot,

    [ValidateNotNullOrEmpty()]
    [string]$ExpectedApiBaseUrl = 'https://vendor-mes.semiindustry.com/',

    [switch]$AllowNonMain
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repository = (Resolve-Path -LiteralPath (Join-Path $scriptRoot '..\..')).Path
$projectPath = Join-Path $repository 'frontend-wpf\Mes.WpfClean\Mes.Wpf\Mes.Vendor.Wpf\Mes.Vendor.Wpf.csproj'
$productionSettingsPath = Join-Path $repository 'frontend-wpf\Mes.WpfClean\Mes.Wpf\Mes.Vendor.Wpf\appsettings.Production.json'
$output = [IO.Path]::GetFullPath($OutputRoot)

if ($output.StartsWith($repository + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Vendor WPF publish output must be outside the Git repository.'
}
if (Test-Path -LiteralPath $output) {
    throw "Output path already exists. Use a new versioned path: $output"
}

$gitStatus = @(& git -C $repository status --porcelain 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read Git status:$([Environment]::NewLine)$($gitStatus -join [Environment]::NewLine)"
}
if ($gitStatus.Count -gt 0) {
    throw "A clean worktree is required:$([Environment]::NewLine)$($gitStatus -join [Environment]::NewLine)"
}

$branch = (& git -C $repository branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read the current Git branch.'
}
if (-not $AllowNonMain -and $branch -ne 'main') {
    throw "Production vendor WPF publishing is allowed only from main. Current branch: $branch"
}

$settings = Get-Content -LiteralPath $productionSettingsPath -Raw | ConvertFrom-Json
if ($settings.Api.BaseUrl -ne $ExpectedApiBaseUrl) {
    throw "Vendor production API URL differs from the approved value: $($settings.Api.BaseUrl)"
}

$staging = Join-Path ([IO.Path]::GetTempPath()) ("mes-v1.5-vendor-wpf-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging -Force | Out-Null

try {
    dotnet publish $projectPath `
        --configuration Release `
        --runtime win-x64 `
        --self-contained true `
        --property:PublishSingleFile=true `
        --property:PublishDir="$staging\"
    if ($LASTEXITCODE -ne 0) {
        throw 'Vendor WPF publish failed.'
    }

    foreach ($requiredPath in @(
        (Join-Path $staging 'Mes.Vendor.Wpf.exe'),
        (Join-Path $staging 'appsettings.Production.json')
    )) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Required vendor WPF output was not created: $requiredPath"
        }
    }

    New-Item -ItemType Directory -Path $output -Force | Out-Null
    Copy-Item -Path (Join-Path $staging '*') -Destination $output -Recurse

    $outputFiles = @(Get-ChildItem -LiteralPath $output -Recurse -File)
    foreach ($file in $outputFiles) {
        [void](Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256)
    }

    $commit = (& git -C $repository rev-parse HEAD).Trim()
    Write-Output "SOURCE_COMMIT=$commit"
    Write-Output "OUTPUT=$output"
    Write-Output "FILE_COUNT=$($outputFiles.Count)"
    Write-Output "TOTAL_BYTES=$(($outputFiles | Measure-Object Length -Sum).Sum)"
}
finally {
    $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedStaging = [IO.Path]::GetFullPath($staging)
    if ((Test-Path -LiteralPath $resolvedStaging) -and $resolvedStaging.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
