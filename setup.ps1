<#
.SYNOPSIS
  One-command setup for fitness_mcp on Windows (PowerShell).

.EXAMPLE
  .\setup.ps1
  .\setup.ps1 -Dev -Login -Sync -Claude

.DESCRIPTION
  Finds Python 3.11+, creates the .venv, installs dependencies, scaffolds and
  locks down .env, then prints next steps. Optional switches:
    -Dev          install dev deps and run the test suite
    -Login        run interactive Garmin login (password is not stored)
    -Sync         run an initial sync of all platforms
    -FullHistory  with -Sync, pull full history instead of the last 30 days
    -Claude       install the Claude Desktop MCP config

  If you hit an execution-policy error, run:
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
#>
[CmdletBinding()]
param(
  [switch]$Dev,
  [switch]$Login,
  [switch]$Sync,
  [switch]$FullHistory,
  [switch]$Claude
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

function Find-Python {
  $cands = @()
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in "3.13", "3.12", "3.11") { $cands += , @("py", "-$v") }
  }
  foreach ($e in "python", "python3") {
    if (Get-Command $e -ErrorAction SilentlyContinue) { $cands += , @($e) }
  }
  foreach ($c in $cands) {
    $exe = $c[0]
    $rest = if ($c.Length -gt 1) { $c[1..($c.Length - 1)] } else { @() }
    try {
      $ver = & $exe @rest -c "import sys;print('{}.{}'.format(*sys.version_info[:2]))" 2>$null
    } catch { continue }
    if (-not $ver) { continue }
    $p = $ver.Trim().Split(".")
    if ([int]$p[0] -gt 3 -or ([int]$p[0] -eq 3 -and [int]$p[1] -ge 11)) { return , $c }
  }
  return $null
}

# 1. Python 3.11+
Say "Checking Python"
$pyCand = Find-Python
if (-not $pyCand) { Write-Error "Python 3.11+ not found. Install it (python.org) and re-run."; exit 1 }
$pyExe = $pyCand[0]
$pyRest = if ($pyCand.Length -gt 1) { $pyCand[1..($pyCand.Length - 1)] } else { @() }
Write-Host "Using $($pyCand -join ' ')"

# 2. Virtual environment
if (-not (Test-Path .venv)) {
  Say "Creating virtual environment (.venv)"
  & $pyExe @pyRest -m venv .venv
}
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip

# 3. Dependencies
Say "Installing dependencies"
if ($Dev) { & $py -m pip install --quiet -r requirements-dev.txt }
else { & $py -m pip install --quiet -r requirements.txt }

# 4. .env scaffold + lock down to current user
if (-not (Test-Path .env)) {
  Say "Creating .env from template"
  Copy-Item .env.example .env
  Write-Host "Edit .env to add your credentials (Garmin email; OAuth tokens as needed)."
}
try {
  icacls .env /inheritance:r /grant:r "$($env:USERNAME):(F)" | Out-Null
  Write-Host ".env permissions restricted to $($env:USERNAME)."
} catch {
  Write-Warning "Could not restrict .env permissions via icacls: $_"
}

# 5. Dev tests
if ($Dev) {
  Say "Running test suite"
  $env:PYTHONPATH = $PSScriptRoot
  & $py -m pytest
}

# 6. Garmin login
if ($Login) { Say "Garmin login (password is not stored)"; & $py login.py }

# 7. Initial sync
if ($Sync) {
  Say "Initial sync"
  if ($FullHistory) { & $py sync.py --platform all --full-history }
  else { & $py sync.py --platform all }
}

# 8. Claude Desktop config
if ($Claude) { Say "Installing Claude Desktop MCP config"; & $py scripts\claude_config.py --write }

Say "Setup complete"
@"
Next steps:
  1. Edit .env with your credentials (if you haven't).
  2. Garmin login (once):     .\.venv\Scripts\python.exe login.py
  3. Pull data:               .\.venv\Scripts\python.exe sync.py --platform garmin --full-history
  4. Add to Claude Desktop:   .\.venv\Scripts\python.exe scripts\claude_config.py --write
                              (or print it: .\.venv\Scripts\python.exe scripts\claude_config.py)
  5. Restart Claude Desktop and ask away.
"@ | Write-Host
