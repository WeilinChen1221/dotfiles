@echo off
setlocal
where pwsh >nul 2>nul
if %errorlevel% equ 0 (
    pwsh -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0open.ps1" %*
) else (
    powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0open.ps1" %*
)
