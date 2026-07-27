[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'OpenZero\TabPilot'),
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$Version = '0.1.0'
$ArchiveName = "OpenZero-Tab-Pilot-Brave-v$Version.zip"
$ArchiveUrl = "https://openzero.talktoai.org/downloads/$ArchiveName"
$ExpectedSha256 = '8ec8f18384f17dc2dc0f64a2609d1ab67e79bee9ff1560b0da191459a58ea1ff'
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
