[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateRange(1, 65535)]
    [int]$ApplicationRevision,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$OutputRoot,

    [ValidateNotNullOrEmpty()]
    [string]$ExpectedApiBaseUrl = 'http://172.30.1.240:8000/',

    [ValidateNotNullOrEmpty()]
    [string]$ExpectedInstallUrl = '\\172.30.1.240\mes_wpf\',

    [switch]$AllowNonMain
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repository = (Resolve-Path -LiteralPath (Join-Path $scriptRoot '..\..')).Path
$projectPath = Join-Path $repository 'frontend-wpf\Mes.WpfClean\Mes.Wpf\Mes.Wpf\Mes.Wpf.csproj'
$profilePath = Join-Path $repository 'frontend-wpf\Mes.WpfClean\Mes.Wpf\Mes.Wpf\Properties\PublishProfiles\ClickOnceProfile.pubxml'
$productionSettingsPath = Join-Path $repository 'frontend-wpf\Mes.WpfClean\Mes.Wpf\Mes.Wpf\appsettings.Production.json'
$output = [IO.Path]::GetFullPath($OutputRoot)

if ($output.StartsWith($repository + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'WPF publish output must be outside the Git repository.'
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
    throw "Production WPF publishing is allowed only from main. Current branch: $branch"
}

$settings = Get-Content -LiteralPath $productionSettingsPath -Raw | ConvertFrom-Json
if ($settings.Api.BaseUrl -ne $ExpectedApiBaseUrl) {
    throw "Production API URL differs from the approved value: $($settings.Api.BaseUrl)"
}

[xml]$profile = Get-Content -LiteralPath $profilePath -Raw
$installUrl = [string]$profile.Project.PropertyGroup.InstallUrl
$updateUrl = [string]$profile.Project.PropertyGroup.UpdateUrl
if ($installUrl -ne $ExpectedInstallUrl -or $updateUrl -ne $ExpectedInstallUrl) {
    throw "ClickOnce InstallUrl/UpdateUrl differ from the approved value: $installUrl / $updateUrl"
}

$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) {
    throw "Visual Studio Installer's vswhere.exe was not found."
}
$msbuildPath = @(& $vswhere -latest -products * -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\MSBuild.exe') | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($msbuildPath) -or -not (Test-Path -LiteralPath $msbuildPath -PathType Leaf)) {
    throw 'A Visual Studio MSBuild installation capable of ClickOnce publish was not found.'
}

$staging = Join-Path ([IO.Path]::GetTempPath()) ("mes-v1.5-wpf-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging -Force | Out-Null

try {
    $msbuildArguments = @(
        $projectPath,
        '/restore',
        '/target:Publish',
        '/property:Configuration=Release',
        '/property:PublishProfile=ClickOnceProfile',
        "/property:ApplicationRevision=$ApplicationRevision",
        "/property:PublishDir=$staging\",
        "/property:PublishUrl=$staging\",
        '/verbosity:minimal',
        '/nologo'
    )

    & $msbuildPath @msbuildArguments
    if ($LASTEXITCODE -ne 0) {
        throw 'WPF ClickOnce publish failed.'
    }

    $versionFolder = Join-Path $staging "Application Files\Mes.Wpf_1_0_0_$ApplicationRevision"
    foreach ($requiredPath in @(
        (Join-Path $staging 'setup.exe'),
        (Join-Path $staging 'Mes.Wpf.application'),
        $versionFolder
    )) {
        if (-not (Test-Path -LiteralPath $requiredPath)) {
            throw "Required ClickOnce output was not created: $requiredPath"
        }
    }

    New-Item -ItemType Directory -Path $output -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $staging 'setup.exe') -Destination $output
    Copy-Item -LiteralPath (Join-Path $staging 'Mes.Wpf.application') -Destination $output
    Copy-Item -LiteralPath (Join-Path $staging 'Application Files') -Destination $output -Recurse

    $outputFiles = @(Get-ChildItem -LiteralPath $output -Recurse -File)
    foreach ($file in $outputFiles) {
        [void](Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256)
    }

    $commit = (& git -C $repository rev-parse HEAD).Trim()
    Write-Output "WPF_VERSION=1.0.0.$ApplicationRevision"
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
