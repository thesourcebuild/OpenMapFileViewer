@echo off
:: =============================================================================
::  launch_wsl.bat - Thin wrapper around launch_wsl.ps1
:: =============================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1" %*
exit /b %ERRORLEVEL%
