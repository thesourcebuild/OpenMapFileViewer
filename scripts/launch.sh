#!/bin/bash
set -e
cd "$(dirname "$0")/.."
if [ -z "$1" ]; then
    echo ""
    echo "Usage: $(basename "$0") <map_file> [options...]"
    echo ""
    echo "Example: $(basename "$0") samples/keil/openlibcli_stm32f103rbtx.map"
    echo ""
    exit 0
fi
cmd=$(command -v python3 || command -v python)
exec "$cmd" src/openmapfileanalyzer.py "$@"