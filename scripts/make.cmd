@echo off
REM T16 shim: forward all args to the canonical Windows runner (make.ps1).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make.ps1" %*
exit /b %ERRORLEVEL%