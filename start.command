#!/bin/zsh
set -e

cd "$(dirname "$0")"

PYTHON="$PWD/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi

"$PYTHON" src/open_research_console.py
