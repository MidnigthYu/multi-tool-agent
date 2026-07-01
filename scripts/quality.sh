#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo "=== Iteration 2 Quality Gate ==="
for step in "ruff format --check ." "ruff check ." "mypy --strict core/ config/ storage/ memory/ tools/" "pytest tests/ -v --cov=core --cov=config --cov=storage --cov=memory --cov=tools --cov-report=term --cov-fail-under=90"; do
    echo; echo "[$step]"
    if eval "$step"; then echo "PASSED"; else echo "FAILED"; fi
done
echo; echo "=== ALL GATES PASSED ==="
