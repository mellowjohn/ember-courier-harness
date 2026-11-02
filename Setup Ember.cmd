@echo off
setlocal
cd /d "%~dp0"
title Ember setup
echo Preparing Ember in this folder. No administrator access is needed.
echo.
py -3.12 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 goto python312
py -3 -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 goto python3
python -c "import sys; sys.exit(sys.version_info < (3, 12))" >nul 2>&1
if not errorlevel 1 goto pythonpath
echo Python 3.12 or newer was not found.
echo Install Python from https://www.python.org/downloads/ then run this file again.
echo With the Python install manager, run: py install 3.12
set "ember_exit=1"
goto done
:python312
py -3.12 -u tools\setup_ember.py %*
goto result
:python3
py -3 -u tools\setup_ember.py %*
goto result
:pythonpath
python -u tools\setup_ember.py %*
:result
set "ember_exit=%errorlevel%"
:done
echo.
if not "%EMBER_NO_PAUSE%"=="1" pause
exit /b %ember_exit%
