#!/usr/bin/env bash
# Launch the robot control panel. Uses ./.venv if present, else system python3.
cd "$(dirname "$0")"
PY="python3"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"
exec "$PY" web_control.py
