@echo off
cd /d "%~dp0..\.."
echo Installing build dependencies...
python -m pip install build
echo Building package distribution...
pyproject-build --outdir out/package/dist
echo Done.
