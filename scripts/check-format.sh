#!/bin/bash
# Check formatting and provide helpful message on failure

# Use ruff from venv if available, otherwise system ruff
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if [ -x "$REPO_ROOT/.venv/bin/ruff" ]; then
    RUFF="$REPO_ROOT/.venv/bin/ruff"
else
    RUFF="ruff"
fi

if $RUFF format --check "$@"; then
    exit 0
else
    echo ""
    echo "To fix formatting, run: ruff format ."
    echo ""
    exit 1
fi
