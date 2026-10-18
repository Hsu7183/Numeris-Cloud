"""Compatibility entry point; keep all Lotto modes on the same dataset."""
import sys
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.build_lotto649_pages import build  # noqa: E402

if __name__ == "__main__":
    build()
