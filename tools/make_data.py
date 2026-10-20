"""Данные прогонов для сайта и документов (без CODESYS): docs/data/ring-verify.json, docs/data/corpus.json,
corpus/zarechnaya.xml (весь корпус, вход демо). Нужен клон s7-to-codesys @ 2285760c.

    python tools/make_data.py           # записать
    python tools/make_data.py --check   # код 1, если файлы устарели
"""

from __future__ import annotations

import argparse
import argparse as _ap
import dataclasses
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
for p in (REPO / "src", REPO / "tools" / "corpus", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

DATA = REPO / "docs" / "data"


def ring_verify() -> dict[str, object]:
    from c2s7.api import run_migrate
    from c2s7.convert.core import Options
    from c2s7.verify import s7conv_clone as SC
    from c2s7.verify.run import verify

    clone = SC.check(SC.default_dir(REPO))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "ring"
        run_migrate(Path("tests/fixtures/s7-to-codesys"), out, Options())
        args = _ap.Namespace(s7conv=str(clone), oracle="stsim", regime="r1", scenarios=None)
        verify(out, args)
        data = json.loads((out / "EQUIVALENCE.json").read_text(encoding="utf-8"))
    for b in data.get("ring", {}).get("blocks", []):
        for d in b.get("divergences", []):
            d.pop("original", None)
            d.pop("ours", None)
    data.get("stsim", {}).pop("gen_tests", None)
    return data


def corpus() -> dict[str, object]:
    from corpus_check import check

    out: dict[str, object] = {}
    for cpu, tia in (("s7-1500", "V21"), ("s7-1200", "V19")):
        with tempfile.TemporaryDirectory() as tmp:
            rs = check(cpu, tia, "export", Path(tmp))
        out[cpu] = [dataclasses.asdict(r) for r in rs]
    return out


def corpus_xml() -> str:
    import builder as B
    from corpus.common import case

    return B.pretty(B.project_xml(case(include_il=True), "Zarechnaya"))


def render_all() -> dict[Path, str]:
    import os

    os.chdir(REPO)
    return {
        DATA / "ring-verify.json": json.dumps(ring_verify(), indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        DATA / "corpus.json": json.dumps(corpus(), indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        REPO / "corpus" / "zarechnaya.xml": corpus_xml(),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    stale = []
    for path, text in render_all().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(str(path.relative_to(REPO)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
            print(path.relative_to(REPO))
    if stale:
        print("устарели: " + ", ".join(stale))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
