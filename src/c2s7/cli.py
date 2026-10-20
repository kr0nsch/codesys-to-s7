"""Командная строка c2s7."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from c2s7 import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="c2s7",
        description="Перенос проектов CODESYS 3.5 в Siemens S7-1200/1500 (TIA Portal).",
    )
    parser.add_argument("--version", action="version", version=f"c2s7 {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
