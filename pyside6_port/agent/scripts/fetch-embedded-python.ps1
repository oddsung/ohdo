# Fetch Windows embeddable Python, enable site-packages, install pip,
# and pre-install the core RPA packages ohdo Agent ships with.
#
# Run from agent/ directory:
#   powershell -ExecutionPolicy Bypass -File scripts/fetch-embedded-python.ps1
#
# Produces: agent/vendor/python/ with:
#   - python.exe (3.12.7 embeddable)
#   - python312._pth with `import site` enabled
#   - Lib/site-packages/pip/...
#   - Lib/site-packages/{pywinauto,pyautogui,selenium,mss}/...
# Size: ~70-90 MB extracted (was 22 MB in M2.8 stdlib-only).
#
# agent/vendor/ is gitignored; this script reproduces it at build time.
#
# Idempotent: rerunning skips steps that are already done.

$ErrorActionPreference = "Stop"

$PythonVersion = "3.12.7"
$PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$Packages = @("pywinauto", "pyautogui", "selenium", "mss")

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = Split-Path -Parent $ScriptRoot
$VendorDir = Join-Path $AgentRoot "vendor"
$TargetDir = Join-Path $VendorDir "python"
$ZipPath = Join-Path $VendorDir "python-embed.zip"
$PyExe = Join-Path $TargetDir "python.exe"
$PthFile = Join-Path $TargetDir "python312._pth"
$SitePackages = Join-Path $TargetDir "Lib\site-packages"
$GetPipScript = Join-Path $VendorDir "get-pip.py"

# ── 1) Download + extract embeddable Python ────────────────────────────────

if (-not (Test-Path $PyExe)) {
    if (-not (Test-Path $VendorDir)) {
        New-Item -ItemType Directory -Path $VendorDir | Out-Null
    }
    Write-Host "[1/5] Downloading $PythonUrl"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $ZipPath
    Write-Host "[1/5] Extracting to $TargetDir"
    if (Test-Path $TargetDir) { Remove-Item -Recurse -Force $TargetDir }
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $TargetDir
    Remove-Item $ZipPath
} else {
    Write-Host "[1/5] Embeddable Python already extracted at $TargetDir"
}

if (-not (Test-Path $PyExe)) {
    throw "python.exe not found after extraction: $PyExe"
}

# ── 2) Enable site-packages in python312._pth ──────────────────────────────

if (-not (Test-Path $PthFile)) {
    throw "Expected ._pth file missing: $PthFile"
}

$pthContent = Get-Content $PthFile -Raw
if ($pthContent -match "(?m)^\s*#\s*import site\s*$") {
    Write-Host "[2/5] Enabling 'import site' in python312._pth"
    $pthContent = $pthContent -replace "(?m)^\s*#\s*import site\s*$", "import site"
    # Preserve trailing newline form
    Set-Content -Path $PthFile -Value $pthContent.TrimEnd() -Encoding ASCII
} elseif ($pthContent -match "(?m)^\s*import site\s*$") {
    Write-Host "[2/5] 'import site' already enabled"
} else {
    Write-Host "[2/5] Appending 'import site' to python312._pth"
    Add-Content -Path $PthFile -Value "`nimport site"
}

# ── 3) Install pip via get-pip.py ──────────────────────────────────────────

$PipInstalled = Test-Path (Join-Path $SitePackages "pip")
if (-not $PipInstalled) {
    Write-Host "[3/5] Downloading get-pip.py"
    Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipScript
    Write-Host "[3/5] Installing pip via get-pip.py"
    & $PyExe $GetPipScript --no-warn-script-location
    Remove-Item $GetPipScript
} else {
    Write-Host "[3/5] pip already installed"
}

# ── 4) Install RPA packages ────────────────────────────────────────────────

Write-Host "[4/5] Installing packages: $($Packages -join ', ')"
# pip skips already-satisfied. --no-warn-script-location silences the
# "script installed outside PATH" warning (harmless for an embedded runtime).
& $PyExe -m pip install --no-warn-script-location @Packages

# ── 5) Smoke test ──────────────────────────────────────────────────────────

Write-Host "[5/5] Smoke test: importing all packages"
& $PyExe -c @"
import pywinauto, pyautogui, selenium, mss
print('OK pywinauto', pywinauto.__version__ if hasattr(pywinauto, '__version__') else '(no __version__)')
print('OK pyautogui', pyautogui.__version__ if hasattr(pyautogui, '__version__') else '(no __version__)')
print('OK selenium', selenium.__version__)
print('OK mss', mss.__version__)
"@

Write-Host ""
Write-Host "Done. Embedded Python ready at: $PyExe"
