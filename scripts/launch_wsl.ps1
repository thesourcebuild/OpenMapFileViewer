param(
    [Parameter(ValueFromRemainingArguments)]
    [string[]]$Args
)

$WslDist = ""

# Manual argument parsing (PowerShell misbinds --help to -WslDist)
$forward = @()
$i = 0
while ($i -lt $Args.Count) {
    switch -wildcard ($Args[$i]) {
        '-WslDist' {
            $i++
            if ($i -lt $Args.Count) { $WslDist = $Args[$i] }
        }
        '-WslDist:*' {
            $WslDist = ($Args[$i] -split ':', 2)[1]
        }
        default {
            # Convert Windows paths to WSL paths
            $arg = $Args[$i]
            if ($arg -match '^([a-zA-Z]):\\(.*)') {
                # Absolute Windows path: I:\path\to\file → /mnt/i/path/to/file
                $arg = "/mnt/$($Matches[1].ToLower())/$($Matches[2] -replace '\\', '/')"
            } else {
                $arg = $arg -replace '\\', '/'
            }
            $forward += $arg
        }
    }
    $i++
}

if ($Args.Count -eq 0) {
    Write-Host @"
launch_wsl.ps1 — Run the map file analyzer via WSL

Forwards all arguments to scripts/launch.sh inside WSL Ubuntu.

Usage:
    scripts\launch_wsl <map_file> [options...]
    scripts\launch_wsl --help
    scripts\launch_wsl -WslDist Ubuntu-22.04 <map_file> [options...]
"@
    exit 0
}

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\.."

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

Write-Host "[launch_wsl] Distro    : $WslDist"
Write-Host "[launch_wsl] Project   : $WslPath"

# Forward arguments to launch.sh
if ($forward.Count -gt 0) {
    $quoted = $forward | ForEach-Object {
        if ($_ -match '[\s"]') { "'$_'" } else { $_ }
    }
    $cmd = "bash $WslPath/scripts/launch.sh $($quoted -join ' ')"
} else {
    $cmd = "bash $WslPath/scripts/launch.sh"
}

Write-Host "[launch_wsl] Command   : $cmd"
Write-Host ""

wsl -d $WslDist -- bash -c $cmd
exit $LASTEXITCODE