@echo off
:: =============================================================================
::  create_setup_wsl.bat - Thin wrapper around create_setup_wsl.ps1
:: =============================================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dpn0.ps1" %*
exit /b %ERRORLEVEL%
