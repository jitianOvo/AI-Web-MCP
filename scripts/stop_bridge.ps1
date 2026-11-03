$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"
$pythonPath = Join-Path $projectRoot "runtime\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = (Get-Command python).Source }
& $pythonPath -c "from ai_web_mcp.client import BridgeClient, BridgeError; c=BridgeClient(); print(c.shutdown())"
