$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root 'build\AI Web MCP.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw "Program not found: $exe" }
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'AI Web MCP.lnk'))
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$exe,0"
$shortcut.Description = 'AI Web MCP — 网页大脑与图片桥接服务'
$shortcut.Save()
Write-Output (Join-Path $desktop 'AI Web MCP.lnk')
