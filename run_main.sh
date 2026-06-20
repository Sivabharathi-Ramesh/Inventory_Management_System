#!/bin/bash
# Launcher script to start main.py with the project's virtualenv (if present).
# Logs stdout/stderr to startup.log in the project folder.

BASE_DIR="/home/sama/Documents/inventory_management_stemland"
cd "$BASE_DIR" || exit 1

# Prefer using the project's virtual environment if it exists
if [ -f "$BASE_DIR/.venv/bin/activate" ]; then
  # shellcheck source=/dev/null
  source "$BASE_DIR/.venv/bin/activate"
  exec "$BASE_DIR/.venv/bin/python" "$BASE_DIR/main.py" >> "$BASE_DIR/startup.log" 2>&1
else
  exec python3 "$BASE_DIR/main.py" >> "$BASE_DIR/startup.log" 2>&1
fi
