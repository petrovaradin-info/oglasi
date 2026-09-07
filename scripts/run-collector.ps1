param([string]$Source = '', [int]$MaxDetails = 0)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot 'venv\Scripts\python.exe'
$logDirectory = Join-Path $projectRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$env:PYTHONIOENCODING = 'utf-8'
$logFile = Join-Path $logDirectory ((Get-Date -Format 'yyyy-MM-dd') + '.log')
$ErrorActionPreference = 'Continue'
$collectorArguments = @((Join-Path $projectRoot 'main.py'), 'collect')
if ($Source) { $collectorArguments += @('--source', $Source) }
if ($MaxDetails -gt 0) { $collectorArguments += @('--max-details', $MaxDetails) }
& $pythonPath @collectorArguments >> $logFile 2>&1
$collectorExit = $LASTEXITCODE
& $pythonPath (Join-Path $projectRoot 'main.py') export >> $logFile 2>&1
if ($collectorExit -eq 0) { $collectorExit = $LASTEXITCODE }
exit $collectorExit
