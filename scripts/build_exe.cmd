@echo off
rem Build GPT Web MCP.exe launcher with MinGW-w64 g++
setlocal
set ROOT=%~dp0..
set OUT="%ROOT%\build\GPT Web MCP.exe"
if not exist "%ROOT%\build" mkdir "%ROOT%\build"
rem Build through an ASCII temp dir because ld cannot handle non-ASCII paths.
set TMPD=%TEMP%\gpt-web-mcp-build
if not exist "%TMPD%" mkdir "%TMPD%"
copy /Y "%ROOT%\launcher\main.cpp" "%TMPD%\main.cpp" >nul
g++ -O2 -static -municode -mwindows "%TMPD%\main.cpp" ^
  -o "%TMPD%\GPT-Web-MCP.exe" -lshell32 -luser32 -lwininet -ladvapi32 -static-libgcc -static-libstdc++
if errorlevel 1 ( echo build=FAILED & exit /b 1 )
copy /Y "%TMPD%\GPT-Web-MCP.exe" %OUT% >nul
echo build=OK
dir %OUT%
