#!/usr/bin/env bash
# Launcher for the PAT Report Generator on macOS / Linux.
set -e
cd "$(dirname "$0")"
python3 -m streamlit run Home.py
