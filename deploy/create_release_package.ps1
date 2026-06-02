param(
    [string]$OutputDir = "_publish_clean",
    [string]$PackageName = "fdsmarticles-cloud-release"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputRoot = Join-Path $Root $OutputDir
$Stage = Join-Path $OutputRoot $PackageName
$ZipPath = Join-Path $OutputRoot "$PackageName.zip"

function Assert-InRoot([string]$Path) {
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to operate outside repository root: $full"
    }
    return $full
}

function Get-RepoRelativePath([string]$BasePath, [string]$TargetPath) {
    $baseFull = [System.IO.Path]::GetFullPath($BasePath)
    if (-not $baseFull.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
        $baseFull = $baseFull + [System.IO.Path]::DirectorySeparatorChar
    }
    $targetFull = [System.IO.Path]::GetFullPath($TargetPath)
    $relativeUri = ([Uri]$baseFull).MakeRelativeUri([Uri]$targetFull)
    return [Uri]::UnescapeDataString($relativeUri.ToString()).Replace('/', [System.IO.Path]::DirectorySeparatorChar)
}

$OutputRoot = Assert-InRoot $OutputRoot
$Stage = Assert-InRoot $Stage
$ZipPath = Assert-InRoot $ZipPath

if (Test-Path -LiteralPath $Stage) {
    Remove-Item -LiteralPath $Stage -Recurse -Force
}
New-Item -ItemType Directory -Path $Stage -Force | Out-Null

$ExcludedDirs = @(
    ".git", ".claude", ".vscode", ".idea", "__pycache__", ".pytest_cache", ".venv", "venv", "ENV",
    "node_modules", "dist", "data", "backups", "qa", "reports", "_publish_clean", "unused_project_assets",
    "audio", "uploads", "archive", "faiss_index", "faiss_index_business", "Fudan_Business_Knowledge_Data",
    "Fudan_News_Data", "Fudan_Wechat_Data", "project_materials", "pretext", "pretext-main"
)
$AllowedEnvExamples = @(".env.docker.example", ".env.production.example")

Get-ChildItem -LiteralPath $Root -Recurse -Force -File | ForEach-Object {
    $relative = Get-RepoRelativePath $Root $_.FullName
    $segments = $relative -split "[\\/]"
    if ($segments | Where-Object { $ExcludedDirs -contains $_ }) {
        return
    }
    if ($_.Name -like ".env*" -and -not ($AllowedEnvExamples -contains $_.Name)) {
        return
    }
    if ($_.Name -like "*.db" -or $_.Name -like "*.db-*" -or $_.Name -like "*.log") {
        return
    }

    $target = Join-Path $Stage $relative
    $targetDir = Split-Path -Parent $target
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target -Force
}

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $ZipPath -Force

$manifest = Get-ChildItem -LiteralPath $Stage -Recurse -File | ForEach-Object {
    Get-RepoRelativePath $Stage $_.FullName
}
$manifest | Set-Content -LiteralPath (Join-Path $OutputRoot "$PackageName.manifest.txt") -Encoding UTF8

Write-Output "release_stage=$Stage"
Write-Output "release_zip=$ZipPath"
Write-Output "manifest=$(Join-Path $OutputRoot "$PackageName.manifest.txt")"
