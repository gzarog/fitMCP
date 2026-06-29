<#
.SYNOPSIS
  Register (or remove) a Windows Scheduled Task that syncs fitness data on a
  schedule by running scripts\scheduled_sync.py in the project venv.

.EXAMPLE
  .\scripts\register_sync_task.ps1                       # daily at 07:00, all platforms
  .\scripts\register_sync_task.ps1 -Time 06:30 -Platform garmin
  .\scripts\register_sync_task.ps1 -Daily2x              # 07:00 and 19:00
  .\scripts\register_sync_task.ps1 -Unregister          # remove the task

.DESCRIPTION
  The task runs as the current user via S4U (no stored password) so the cached
  Garmin token in your profile is available; it runs whether or not you're
  logged in, and catches up missed runs (-StartWhenAvailable). Output is logged
  to logs\sync.log. Re-running re-registers (idempotent).

  Requires that setup.ps1 has been run (so .venv exists) and that you've logged
  in once with login.py.
#>
[CmdletBinding()]
param(
  [string]$Time = "07:00",
  [string]$Platform = "all",
  [string]$TaskName = "fitnessmcp-sync",
  [switch]$Daily2x,
  [switch]$Unregister
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot          # scripts\ -> repo root
$py = Join-Path $repo ".venv\Scripts\python.exe"
$runner = Join-Path $repo "scripts\scheduled_sync.py"

if ($Unregister) {
  if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
  } else {
    Write-Host "No scheduled task named '$TaskName'."
  }
  return
}

if (-not (Test-Path $py)) {
  Write-Error "venv python not found at $py. Run .\setup.ps1 first."
  exit 1
}

$action = New-ScheduledTaskAction -Execute $py `
  -Argument "`"$runner`" --platform $Platform" -WorkingDirectory $repo

if ($Daily2x) {
  $trigger = @(
    (New-ScheduledTaskTrigger -Daily -At $Time),
    (New-ScheduledTaskTrigger -Daily -At "19:00")
  )
} else {
  $trigger = New-ScheduledTaskTrigger -Daily -At $Time
}

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Principal $principal -Settings $settings -Force | Out-Null

Write-Host "Registered task '$TaskName' (platform=$Platform)."
Write-Host ("Schedule: {0}" -f ($(if ($Daily2x) { "daily $Time and 19:00" } else { "daily $Time" })))
Write-Host "Logs: $repo\logs\sync.log"
Write-Host "Inspect/Run now: Get-ScheduledTask $TaskName | Start-ScheduledTask"
