@echo off
REM Launcher for the PAT Report Generator on Windows.
REM
REM First run installs the dependencies; later runs go straight to the
REM app. Streamlit is invoked via `python -m`, which works whether or
REM not the pip Scripts folder is on PATH.
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python was not found on this computer.
  echo.
  echo Install Python 3.10 or newer from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" in the installer, then run this
  echo file again.
  echo.
  pause
  exit /b 1
)

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
  echo.
  echo First run: installing the packages this app needs.
  echo This takes a few minutes and only happens once.
  echo.
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  if errorlevel 1 (
    echo.
    echo The full install failed -- retrying without the optional PDF
    echo library. PDF export will fall back to headless Edge or Chrome,
    echo which is how it works on most Windows machines anyway.
    echo.
    python -m pip install streamlit pandas openpyxl python-docx markdown platformdirs
    if errorlevel 1 (
      echo.
      echo Installation failed. Read the messages above -- the usual cause
      echo is no internet connection or a proxy blocking pip.
      echo.
      pause
      exit /b 1
    )
  )
  echo.
  echo Done. Starting the app.
  echo.
)

python -m streamlit run Home.py
