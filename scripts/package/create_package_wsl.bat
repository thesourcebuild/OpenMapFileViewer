@echo off
:: =============================================================================
::  create_package_wsl.bat - Thin wrapper around create_package_wsl.ps1
:: =============================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1" %*
exit /b %ERRORLEVEL%
