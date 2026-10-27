@echo off
rem Run the bot with the virtual environment's own Python, from anywhere.
rem
rem   soundbot task-restart
rem   soundbot run-once --dry-run --country CY
rem   soundbot serve --open
rem
rem Typing "main.py ..." instead leaves it to the .py file association, which on a machine that has
rem none makes Windows ask which program to open it with - and where there is one, it runs the system
rem Python rather than this folder's, which has none of the dependencies installed.
setlocal
set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo No virtual environment in %HERE%
  echo Create it with:
  echo     py -3.13 -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)
"%PY%" "%HERE%main.py" %*
