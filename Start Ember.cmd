@echo off
setlocal
cd /d "%~dp0"
title Ember - leave this window open
echo Starting Ember. Leave this window open while using the app.
echo Open the private link printed below in your browser.
echo.
py -3.12 -u -m ember_harness.local_ui
echo.
echo Ember has stopped. Your saved sessions remain on disk.
pause
