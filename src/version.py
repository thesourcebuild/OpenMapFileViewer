import sys
from pathlib import Path


def _get_version() -> str:
    if getattr(sys, "frozen", False):
        version_file = Path(sys.executable).resolve().parent / "version"
    else:
        version_file = Path(__file__).resolve().parent.parent / "version"
    return version_file.read_text(encoding="utf-8").strip()


__version__ = _get_version()
