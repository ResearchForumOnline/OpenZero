[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'OpenZero\TabPilot'),
    [string]$OpenZeroSshHost = '',
    [switch]$ConfigureTunnel,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Version = '0.2.0'
$ArchiveName = "OpenZero-Tab-Pilot-Brave-v$Version.zip"
$ArchiveUrl = "https://openzero.talktoai.org/downloads/$ArchiveName"
$ExpectedSha256 = '732fa09c2cc13fcd285675a1500dc690968f03286e0962b01ff85744670c21d9'
$Target = Join-Path $InstallRoot $Version

function Find-Brave {
    $candidates = @(
        (Join-Path $env:ProgramFiles 'BraveSoftware\Brave-Browser\Application\brave.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'BraveSoftware\Brave-Browser\Application\brave.exe'),
        (Join-Path $env:LOCALAPPDATA 'BraveSoftware\Brave-Browser\Application\brave.exe')
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}

function Install-OpenZeroTunnel {
    param([Parameter(Mandatory)][string]$SshHost)

    if ($SshHost -notmatch '^(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9._-]+$') {
        throw 'OpenZeroSshHost must be a hostname or user@hostname containing only letters, numbers, dots, underscores, and hyphens.'
    }

    $Ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue
    if (-not $Ssh) {
        throw 'Windows OpenSSH client was not found. Install it or configure the tunnel manually.'
    }

    $TunnelRoot = Join-Path $env:LOCALAPPDATA 'OpenZero\TabPilot'
    $TunnelScript = Join-Path $TunnelRoot 'start-openzero-tunnel.ps1'
    $StartupRoot = [Environment]::GetFolderPath('Startup')
    $ShortcutPath = Join-Path $StartupRoot 'OpenZero Tab Pilot Tunnel.lnk'
    $PowerShell = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $PowerShell -PathType Leaf)) {
        $PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
    }

    New-Item -ItemType Directory -Path $TunnelRoot -Force | Out-Null
    $TunnelBody = @"
`$ErrorActionPreference = 'Continue'
while (`$true) {
    & '$($Ssh.Source)' -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=4 -L '1024:127.0.0.1:1024' '$SshHost'
    Start-Sleep -Seconds 5
}
"@
    Set-Content -LiteralPath $TunnelScript -Value $TunnelBody -Encoding UTF8

    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $PowerShell
    $Shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$TunnelScript`""
    $Shortcut.WorkingDirectory = $TunnelRoot
    $Shortcut.Description = 'Keep the OpenZero Tab Pilot loopback SSH tunnel connected'
    $Shortcut.Save()

    Write-Host "Automatic loopback tunnel configured for Windows sign-in: $SshHost" -ForegroundColor Green
    Write-Host "Startup shortcut: $ShortcutPath"
    Start-Process -FilePath $PowerShell -ArgumentList @(
        '-NoProfile',
        '-WindowStyle', 'Hidden',
        '-ExecutionPolicy', 'Bypass',
        '-File', $TunnelScript
    )
}

Write-Host "OpenZero Tab Pilot $Version setup" -ForegroundColor Cyan
Write-Host 'This downloads and verifies the extension, then opens Brave extension settings.'
Write-Host 'Brave intentionally requires you to approve Load unpacked yourself.' -ForegroundColor Yellow

if (Test-Path -LiteralPath (Join-Path $Target 'manifest.json') -PathType Leaf) {
    Write-Host "Already prepared at $Target" -ForegroundColor Green
} else {
    if (Test-Path -LiteralPath $Target) {
        throw "Target exists but has no manifest.json: $Target. Move it aside and rerun."
    }

    $TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("openzero-tab-pilot-" + [guid]::NewGuid().ToString('N'))
    $ArchivePath = Join-Path $TempRoot $ArchiveName
    $Stage = Join-Path $TempRoot 'extension'

    try {
        New-Item -ItemType Directory -Path $TempRoot, $Stage -Force | Out-Null
        Write-Host "Downloading $ArchiveUrl"
        Invoke-WebRequest -Uri $ArchiveUrl -OutFile $ArchivePath -UseBasicParsing

        $ActualSha256 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualSha256 -ne $ExpectedSha256) {
            throw "Checksum mismatch. Expected $ExpectedSha256 but received $ActualSha256."
        }

        Expand-Archive -LiteralPath $ArchivePath -DestinationPath $Stage
        if (-not (Test-Path -LiteralPath (Join-Path $Stage 'manifest.json') -PathType Leaf)) {
            throw 'The verified archive did not contain manifest.json at its root.'
        }

        New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
        Move-Item -LiteralPath $Stage -Destination $Target
        Write-Host "Verified and extracted to $Target" -ForegroundColor Green
    } finally {
        if ($TempRoot -and (Test-Path -LiteralPath $TempRoot)) {
            Remove-Item -LiteralPath $TempRoot -Recurse -Force
        }
    }
}

if ($ConfigureTunnel) {
    if ([string]::IsNullOrWhiteSpace($OpenZeroSshHost)) {
        throw 'Use -OpenZeroSshHost with -ConfigureTunnel, for example: -OpenZeroSshHost user@server -ConfigureTunnel'
    }
    Install-OpenZeroTunnel -SshHost $OpenZeroSshHost
}

if (-not $NoLaunch) {
    $Brave = Find-Brave
    if ($Brave) {
        Start-Process -FilePath $Brave -ArgumentList 'brave://extensions'
    } else {
        Write-Warning 'Brave was not found automatically. Open brave://extensions manually.'
    }

    Start-Process explorer.exe -ArgumentList "/select,`"$(Join-Path $Target 'manifest.json')`""

    Write-Host ''
    Write-Host 'Finish in Brave:' -ForegroundColor Cyan
    Write-Host '1. Enable Developer mode.'
    Write-Host '2. Choose Load unpacked.'
    Write-Host "3. Select: $Target"
    Write-Host '4. Open extension Options and connect to http://127.0.0.1:1024.'
    Write-Host ''
    Write-Host 'For a remote OpenZero node, use an SSH tunnel. Never expose the bearer API over plain remote HTTP.' -ForegroundColor Yellow
}
