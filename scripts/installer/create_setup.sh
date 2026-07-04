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

echo "=== Installing dependencies ==="
python3 -m pip install -e .[build]

echo "=== Building standalone executable ==="
pyinstaller scripts/installer/openmapfileanalyzer.spec --distpath out/linux/pyinstaller/dist --workpath out/linux/pyinstaller/build --clean

echo "=== Done ==="
echo "Linux binary: $(pwd)/out/linux/pyinstaller/dist/openmapfileanalyzer"