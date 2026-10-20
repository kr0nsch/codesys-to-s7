"""Сценарии корпуса из эталонных моделей: scenarios/reference/model_*.py → scenarios/<блок>.csv.

python tools/corpus/gen_scenarios.py           # записать
python tools/corpus/gen_scenarios.py --check   # код 1, если CSV устарели
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REF = REPO / "scenarios" / "reference"
OUT = REPO / "scenarios"


def models() -> dict[str, object]:
    if str(REF) not in sys.path:
        sys.path.insert(0, str(REF))
    out: dict[str, object] = {}
    for f in sorted(REF.glob("model_*.py"), key=lambda p: (p.name.lower(), p.name)):
        mod = importlib.import_module(f.stem)
        spec = mod.SPEC
        out[spec.block] = spec
    return out


def render_all() -> dict[Path, str]:
    ms = models()
    from refcommon import render_csv

    return {OUT / f"{name}.csv": render_csv(spec) for name, spec in ms.items()}  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    stale = []
    for path, text in render_all().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(path.name)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        print("устарели: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
