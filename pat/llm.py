"""LLM integration — planned for annual-report narrative generation.

This module is intentionally empty. It marks the architectural slot for
LLM-assisted writing (e.g., turning a filtered Report into a narrative
paragraph suitable for annual or self-study reports).

When implementing, accept a Report object plus a prompt template,
return a NarrativeBlock (defined in pat/render/model.py). Read any API
key from an environment variable; never commit keys. Keep this module
free of Streamlit imports.
"""
