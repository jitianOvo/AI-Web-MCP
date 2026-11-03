@echo off
rem Build AI Web MCP.exe launcher with MinGW-w64 g++
setlocal
set ROOT=%~dp0..
set OUT="%ROOT%\build\AI Web MCP.exe"
if /I "%~1"=="--stage" set OUT="%ROOT%\build\AI Web MCP.next.exe"
if not exist "%ROOT%\build" mkdir "%ROOT%\build"
rem Keep build intermediates in the project. SUBST provides an ASCII path for ld.
set TMPD=%ROOT%\tmp\launcher-build
if not exist "%TMPD%" mkdir "%TMPD%"
copy /Y "%ROOT%\launcher\main.cpp" "%TMPD%\main.cpp" >nul
copy /Y "%ROOT%\launcher\json_fields.h" "%TMPD%\json_fields.h" >nul
copy /Y "%ROOT%\res\app.rc" "%TMPD%\app.rc" >nul
copy /Y "%ROOT%\res\AI_Web_MCP_iconic.ico" "%TMPD%\AI_Web_MCP_iconic.ico" >nul
set BUILDDRIVE=
for %%D in (Z Y X W V U T S R Q P) do if not defined BUILDDRIVE if not exist %%D:\ set BUILDDRIVE=%%D:
if not defined BUILDDRIVE ( echo build=FAILED-no-free-drive & exit /b 1 )
subst %BUILDDRIVE% "%TMPD%"
if errorlevel 1 ( echo build=FAILED-subst & exit /b 1 )
pushd %BUILDDRIVE%\
windres app.rc -O coff -o app.res
if errorlevel 1 goto failed
g++ -O2 -static -municode -mwindows main.cpp app.res ^
  -o AI-Web-MCP.exe -lshell32 -luser32 -lwininet -ladvapi32 -lgdi32 -static-libgcc -static-libstdc++
if errorlevel 1 goto failed
popd
subst %BUILDDRIVE% /D
copy /Y "%TMPD%\AI-Web-MCP.exe" %OUT% >nul
if errorlevel 1 ( echo build=FAILED-copy & exit /b 1 )
echo build=OK
dir %OUT%
exit /b 0
:failed
popd
subst %BUILDDRIVE% /D
echo build=FAILED
exit /b 1
