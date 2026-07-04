@echo off
cd /d "%~dp0..\.."
echo Installing dependencies...
python -m pip install -e .[build]
echo Building standalone executable...
pyinstaller scripts/installer/openmapfileanalyzer.spec --distpath out\windows\pyinstaller\dist --workpath out\windows\pyinstaller\build
echo Done.
