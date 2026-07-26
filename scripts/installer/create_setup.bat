@echo off
cd /d "%~dp0..\.."
set "VENV=.venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv "%VENV%"
    if errorlevel 1 exit /b 1
)

echo Installing dependencies...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV%\Scripts\python.exe" -m pip install -e .[build]
if errorlevel 1 exit /b 1

echo Building standalone executable...
"%VENV%\Scripts\python.exe" -m PyInstaller scripts/installer/openmapfileviewer.spec --distpath out\windows\pyinstaller\dist --workpath out\windows\pyinstaller\build
if errorlevel 1 exit /b 1

echo Done.

