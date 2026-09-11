param([string]$TaskName = 'Petrovaradin-Oglasi-Hourly')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runnerPath = Join-Path $PSScriptRoot 'run-collector.ps1'
if (-not (Test-Path (Join-Path $projectRoot 'venv\Scripts\python.exe'))) { throw 'Nedostaje venv Python.' }
$today = (Get-Date).Date
# Separate daily triggers include both endpoints without repetition-duration ambiguity.
$triggers = @(6..18 | ForEach-Object {
    $at = $today.AddHours($_)
    $daily = New-ScheduledTaskTrigger -Daily -At $at
    # No UTC offset: keep local wall-clock hours across daylight-saving changes.
    $daily.StartBoundary = $at.ToString("yyyy-MM-dd'T'HH:mm:ss")
    $daily
})
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runnerPath + '"') -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 55)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'Oglasi: svakog dana u 06:00, 07:00, ..., 18:00 po lokalnom vremenu; bez nadoknade propustenih termina.' -Force | Out-Null
Get-ScheduledTaskInfo -TaskName $TaskName
