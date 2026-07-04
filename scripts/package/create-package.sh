#!/bin/bash
set -e
cd "$(dirname "$0")/../.."

# Ensure python3-venv is available (needed on fresh WSL/Ubuntu)
if ! python3 -c "import ensurepip" 2>/dev/null; then
    echo "=== Installing python3-venv ==="
    sudo apt-get update -qq
    sudo apt-get install -y -qq python3-venv
fi

echo "=== Creating virtual environment ==="
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python3 -m pip install --upgrade pip

echo "=== Installing build dependencies ==="
python3 -m pip install build

echo "=== Building package distribution ==="
pyproject-build --outdir out/package/dist

echo "=== Done ==="
echo "Package output: $(pwd)/out/package/dist/"