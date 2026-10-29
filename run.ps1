param([string]$Image)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup.ps1 first.' }
}
if (-not $env:WEAVE_INKSTITCH -and -not (Test-Path '.tools\inkstitch-3.3.0\inkstitch\bin\inkstitch.exe')) { throw 'Run setup.ps1 to install Ink/Stitch.' }
Write-Host 'Open http://127.0.0.1:8765 in your browser. Keep this window open while using Weave.'
if ($Image) { & $python app.py --image $Image } else { & $python app.py }
