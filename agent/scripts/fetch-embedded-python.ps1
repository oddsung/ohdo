# Fetch Windows embeddable Python and extract to agent/vendor/python/.
# Run from agent/ directory:
#   powershell -ExecutionPolicy Bypass -File scripts/fetch-embedded-python.ps1
#
# Produces: agent/vendor/python/python.exe (plus stdlib zip, DLLs)
# Size: ~11 MB extracted.
#
# Intentionally does NOT include pip — M2.8 ships stdlib-only sandbox.
# agent/vendor/ is gitignored; this script reproduces it at build time.

$ErrorActionPreference = "Stop"

$Version = "3.12.7"
$Url = "https://www.python.org/ftp/python/$Version/python-$Version-embed-amd64.zip"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = Split-Path -Parent $ScriptRoot
$VendorDir = Join-Path $AgentRoot "vendor"
$TargetDir = Join-Path $VendorDir "python"
$ZipPath = Join-Path $VendorDir "python-embed.zip"

if (Test-Path (Join-Path $TargetDir "python.exe")) {
    Write-Host "Embedded Python already present: $TargetDir"
    exit 0
}

if (-not (Test-Path $VendorDir)) {
    New-Item -ItemType Directory -Path $VendorDir | Out-Null
}

Write-Host "Downloading $Url"
Invoke-WebRequest -Uri $Url -OutFile $ZipPath

Write-Host "Extracting to $TargetDir"
if (Test-Path $TargetDir) { Remove-Item -Recurse -Force $TargetDir }
Expand-Archive -LiteralPath $ZipPath -DestinationPath $TargetDir

Remove-Item $ZipPath

$PyExe = Join-Path $TargetDir "python.exe"
if (-not (Test-Path $PyExe)) {
    throw "Extraction succeeded but python.exe not found at: $PyExe"
}

Write-Host "OK. python.exe: $PyExe"
& $PyExe --version
