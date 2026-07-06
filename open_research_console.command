#!/bin/zsh
set -e
cd "/Users/aidianchi/Desktop/ndx_mac"

PYTHON="$PWD/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

"$PYTHON" src/open_research_console.py
