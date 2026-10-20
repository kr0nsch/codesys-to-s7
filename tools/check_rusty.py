"""RuSTy v1.0.6 `plc --check` (job rusty): ST′ кольца не хуже источника.

RuSTy понимает не все расширения CODESYS (например, `qualified_only` у GVL), поэтому ошибки есть и у
исходного ST s7-to-codesys. Критерий: множество ошибок (код + текст) у ST′ — подмножество ошибок
источника. Запускается `tools/check/run_rusty.py` клона s7-to-codesys @ 2285760c.

    RUSTY_PLC=… RUSTY_STDLIB_INCLUDE=… python tools/check_rusty.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from c2s7.api import run_migrate  # noqa: E402
from c2s7.convert.core import Options  # noqa: E402
from c2s7.verify import s7conv_clone as SC  # noqa: E402
from c2s7.verify.roundtrip import run_s7conv  # noqa: E402


def rusty(clone: Path, root: Path, work: Path, label: str) -> set[tuple[str, str]]:
    empty = work / "no_exclude.txt"
    empty.write_text("", encoding="utf-8")
    js = work / f"rusty-{label}.json"
    cmd = [
        sys.executable,
        str(clone / "tools" / "check" / "run_rusty.py"),
        "--root",
        str(root),
        "--no-tests",
        "--exclude-file",
        str(empty),
        "--log",
        str(work / f"rusty-{label}.log"),
        "--json",
        str(js),
    ]
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, check=False)
    print(proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr[-500:])
    data = json.loads(js.read_text(encoding="utf-8"))
    return {(d["code"], d["message"]) for d in data.get("diagnostics", []) if d.get("severity") == "error"}


def main() -> int:
    clone = SC.check(SC.default_dir(REPO))
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        out = work / "ring"
        run_migrate(REPO / "tests" / "fixtures" / "s7-to-codesys", out, Options())
        rt = run_s7conv(out, clone)
        src = rusty(clone, REPO / "tests" / "fixtures" / "s7-to-codesys", work, "source")
        prime = rusty(clone, rt.st_prime, work, "st_prime")
    extra = sorted(prime - src)
    print(f"ошибок RuSTy: источник {len(src)}, ST′ {len(prime)}, новых в ST′ {len(extra)}")
    for code, msg in extra:
        print(f"  {code} {msg}")
    return 0 if not extra else 1


if __name__ == "__main__":
    sys.exit(main())
