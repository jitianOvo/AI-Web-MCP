@echo off
rem GPT Web MCP Bridge 托盘启动器（双击运行，之后在右下角托盘操作）
cd /d "%~dp0.."
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0bridge_tray.ps1"
