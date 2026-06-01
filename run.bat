@echo off
REM Launcher for the PAT Report Generator on Windows.
REM Always invokes Streamlit via `python -m`, which works whether or
REM not the user has the pip Scripts folder on PATH.
cd /d "%~dp0"
python -m streamlit run Home.py
