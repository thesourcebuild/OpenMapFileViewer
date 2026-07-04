param(
    [switch]$Help,
    [string]$WslDist = "",
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$args
)

if ($Help -or $args -contains '--help' -or $args -contains '-h') {
    Write-Host @"
create_setup_wsl.ps1 — Build Linux standalone executable via WSL

Delegates to create_setup.sh inside WSL Ubuntu.

Usage:
    scripts\installer\create_setup_wsl                         (default Ubuntu distro)
    scripts\installer\create_setup_wsl -WslDist Ubuntu-22.04   (specific distro)
"@
    exit 0
}

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."

# Find WSL distro
if (-not $WslDist) {
    $enc = [Console]::OutputEncoding
    [Console]::OutputEncoding = [System.Text.Encoding]::Unicode
    $distros = @(wsl --list --quiet 2>&1 | ForEach-Object { $_.Trim() })
    [Console]::OutputEncoding = $enc
    $WslDist = $distros | Where-Object { $_ -match '^Ubuntu' } | Select-Object -First 1
    if (-not $WslDist) { $WslDist = "Ubuntu" }
}

# Convert Windows path to WSL path
$Drive = $ProjectRoot.Drive.Name.ToLower()
$RelPath = $ProjectRoot.Path.Substring(3) -replace '\\', '/'
$WslPath = "/mnt/$Drive/$RelPath"

Write-Host "[create_setup_wsl] Distro    : $WslDist"
Write-Host "[create_setup_wsl] Project   : $WslPath"
Write-Host ""

# Write a tiny runner script and execute via WSL
$tmpRel = ".wsl_build_$(Get-Random).sh"
$tmpFile = Join-Path $ProjectRoot.Path $tmpRel
$tmpDrive = (Split-Path -Qualifier $tmpFile).TrimEnd(':').ToLower()
$tmpPath = (Split-Path -NoQualifier $tmpFile) -replace '\\', '/'
$tmpWsl = "/mnt/$tmpDrive$tmpPath"
try {
    "cd '$WslPath' && bash scripts/installer/create_setup.sh" | Out-File -FilePath $tmpFile -Encoding ASCII -NoNewline
    Write-Host "Starting WSL build..."
    wsl -d $WslDist -- bash $tmpWsl
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[create_setup_wsl] FAILED (exit $LASTEXITCODE)"
    }
    exit $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $tmpFile -ErrorAction SilentlyContinue
}