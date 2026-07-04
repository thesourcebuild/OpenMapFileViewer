@echo off
cd /d "%~dp0.." 2>nul
if "%~1"=="" goto :usage
goto :run

:usage
echo.
echo Usage: %~n0 ^<map_file^> [options...]
echo.
echo Example: %~n0 samples\keil\openlibcli_stm32f103rbtx.map
echo.
exit /b 0

:run
python src/openmapfileanalyzer.py %*