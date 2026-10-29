param([string]$Python)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Python) {
    $bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundled) { $Python = $bundled }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = (& py -3.12 -c 'import sys; print(sys.executable)') }
    else { throw 'Install Python 3.12, then run setup.ps1 -Python C:\path\to\python.exe' }
}
if (-not (Test-Path '.venv\Scripts\python.exe')) { & $Python -m venv .venv; if ($LASTEXITCODE) { throw 'Unable to create the local Python environment.' } }
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE) { throw 'Python dependency installation failed.' }
$version = '3.3.0'
$toolDir = Join-Path $PSScriptRoot ".tools\inkstitch-$version"
$exe = Join-Path $toolDir 'inkstitch\bin\inkstitch.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    New-Item -ItemType Directory -Force -Path '.tools' | Out-Null
    $archive = Join-Path $PSScriptRoot ".tools\inkstitch-$version.zip"
    if (-not (Test-Path -LiteralPath $archive)) {
        Invoke-WebRequest -Uri "https://github.com/inkstitch/inkstitch/releases/download/v$version/inkstitch-v$version-windows-64bit.zip" -OutFile $archive
    }
    $expected = '992a0aec0cf05ad3af1e68e89acd3a0ec65434f4e1d1a418eb54df106984addb'
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Ink/Stitch checksum mismatch. Remove the downloaded ZIP and retry.' }
    Expand-Archive -LiteralPath $archive -DestinationPath $toolDir -Force
}
Write-Host 'Setup complete. Open start.bat to launch Weave.'
