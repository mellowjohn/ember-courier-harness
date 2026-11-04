@echo off
setlocal
cd /d "%~dp0"
title Ember - leave this window open
echo Starting Ember. Leave this window open while using the app.
echo Open the private link printed below in your browser.
echo.
set "ember_browser=--open-browser"
if "%EMBER_NO_BROWSER%"=="1" set "ember_browser="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "ember_python=%~dp0.venv\Scripts\python.exe"
    goto check_python
)
if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
    set "ember_python=%VIRTUAL_ENV%\Scripts\python.exe"
    goto check_python
)
if exist "%~dp0Setup Ember.cmd" goto setup
py -3.12 -c "import sys; from importlib.util import find_spec; from importlib.metadata import version; sys.exit(0 if sys.version_info >= (3,12) and all(find_spec(n) for n in ('ember_harness','jsonschema','PIL')) and int(version('Pillow').split('.')[0]) == 13 else 1)" >nul 2>&1
if errorlevel 1 goto setup
py -3.12 -u -m ember_harness.local_ui %ember_browser% %*
goto stopped
:project_python
set "ember_python=%~dp0.venv\Scripts\python.exe"
:check_python
"%ember_python%" -c "import sys; from importlib.util import find_spec; from importlib.metadata import version; sys.exit(0 if sys.version_info >= (3,12) and all(find_spec(n) for n in ('ember_harness','jsonschema','PIL')) and int(version('Pillow').split('.')[0]) == 13 else 1)" >nul 2>&1
if errorlevel 1 goto setup
"%ember_python%" -u -m ember_harness.local_ui %ember_browser% %*
goto stopped
:setup
echo Ember needs first-time setup or a dependency repair.
if not exist "%~dp0Setup Ember.cmd" (
    echo Setup Ember.cmd is missing. Extract the complete repository and try again.
    cmd /c exit 1
    goto stopped
)
set "ember_saved_pause=%EMBER_NO_PAUSE%"
set "EMBER_NO_PAUSE=1"
call "%~dp0Setup Ember.cmd"
set "ember_exit=%errorlevel%"
set "EMBER_NO_PAUSE=%ember_saved_pause%"
if not "%ember_exit%"=="0" goto setup_failed
goto project_python
:setup_failed
cmd /c exit %ember_exit%
:stopped
set "ember_exit=%errorlevel%"
echo.
if not "%ember_exit%"=="0" echo Launch failed. Run Setup Ember.cmd or see docs\INSTALL.md for help.
echo Ember has stopped. Your saved sessions remain on disk.
if not "%EMBER_NO_PAUSE%"=="1" pause
exit /b %ember_exit%
