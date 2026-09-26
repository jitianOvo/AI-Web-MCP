@echo off
rem Build GPT Web MCP.exe launcher with MinGW-w64 g++
setlocal
set ROOT=%~dp0..
set OUT="%ROOT%\build\GPT Web MCP.exe"
if not exist "%ROOT%\build" mkdir "%ROOT%\build"
g++ -O2 -static -municode -mconsole "%ROOT%\launcher\main.cpp" ^
  -o %OUT% -lshell32 -luser32 -lwininet -ladvapi32 -static-libgcc -static-libstdc++
if errorlevel 1 ( echo build=FAILED & exit /b 1 )
echo build=OK
dir %OUT%
