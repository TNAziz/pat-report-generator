#!/usr/bin/env bash
# Launcher for the PAT Report Generator on macOS / Linux.
#
# First run installs the dependencies; later runs go straight to the app.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found. Install Python 3.10 or newer, then run this again." >&2
  exit 1
fi

if ! python3 -c "import streamlit" >/dev/null 2>&1; then
  echo
  echo "First run: installing the packages this app needs."
  echo "This takes a few minutes and only happens once."
  echo
  python3 -m pip install --upgrade pip
  if ! python3 -m pip install -r requirements.txt; then
    echo
    echo "The full install failed -- retrying without the optional PDF library." >&2
    python3 -m pip install streamlit pandas openpyxl python-docx markdown platformdirs
  fi
  echo
  echo "Done. Starting the app."
  echo
fi

python3 -m streamlit run Home.py
