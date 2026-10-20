"""Печать docs/MAPPING.md и docs/RULES.md из YAML пакета (тесты сверяют файлы с этим выводом).

python tools/gen_docs.py          # записать
python tools/gen_docs.py --check  # код 1, если файлы устарели
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from c2s7 import mapping, rules  # noqa: E402

DOCS = {"docs/MAPPING.md": mapping.render_md, "docs/RULES.md": rules.render_md}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for rel, fn in DOCS.items():
        text = fn()
        path = REPO / rel
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    for s in stale:
        print(f"устарел: {s} (python tools/gen_docs.py)", file=sys.stderr)
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
