"""CDS_SR/CDS_RS против Standard.SR/RS в CODESYS Control Win (ТЗ M7, КТ-B).

Блоки CodesysCompat написаны на SCL; в CODESYS исполняется их обратный перевод s7conv (ST′ из
корпуса, build/corpus/<cpu>/out/roundtrip/st_prime). Программа PRG_SrCheck за один цикл прогоняет
обе пары по одной последовательности (SET, RESET), включая SET = RESET = 1 из обоих состояний,
и пишет выходы в массивы; хост сравнивает поэлементно.

    python tools/codesys/check_compat.py    → docs/data/compat-controlwin.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO / "tools" / "probes", REPO / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cdsrun  # noqa: E402
import online  # noqa: E402

SEQ = [(0, 0), (1, 0), (0, 0), (1, 1), (0, 1), (0, 0), (1, 1), (1, 0), (1, 1), (0, 1), (1, 1), (0, 0)]
OUT = REPO / "docs" / "data" / "compat-controlwin.json"


def st_prime_dir() -> Path:
    d = REPO / "build" / "corpus" / "s7-1500" / "out" / "roundtrip" / "st_prime" / "src" / "POUs"
    if not (d / "CDS_SR").exists():
        raise SystemExit("нет ST′ CDS_SR: сначала python tools/corpus/corpus_check.py")
    return d


def program() -> tuple[str, str]:
    n = len(SEQ)
    s = ", ".join("TRUE" if a else "FALSE" for a, _ in SEQ)
    r = ", ".join("TRUE" if b else "FALSE" for _, b in SEQ)
    decl = f"""PROGRAM PRG_SrCheck
VAR
    xDone : BOOL;
    i : INT;
    aS : ARRAY[1..{n}] OF BOOL := [{s}];
    aR : ARRAY[1..{n}] OF BOOL := [{r}];
    aSrStd, aSrCds, aRsStd, aRsCds : ARRAY[1..{n}] OF BOOL;
    fbSrStd : SR;
    fbRsStd : RS;
    fbSrCds : CDS_SR;
    fbRsCds : CDS_RS;
END_VAR
"""
    impl = f"""IF NOT xDone THEN
    FOR i := 1 TO {n} DO
        fbSrStd(SET1 := aS[i], RESET := aR[i]);
        aSrStd[i] := fbSrStd.Q1;
        fbSrCds(SET1 := aS[i], RESET := aR[i]);
        aSrCds[i] := fbSrCds.Q1;
        fbRsStd(SET := aS[i], RESET1 := aR[i]);
        aRsStd[i] := fbRsStd.Q1;
        fbRsCds(SET := aS[i], RESET1 := aR[i]);
        aRsCds[i] := fbRsCds.Q1;
    END_FOR
    xDone := TRUE;
END_IF
"""
    return decl, impl


def main() -> int:
    d = st_prime_dir()
    objs = []
    for name in ("CDS_SR", "CDS_RS"):
        objs.append(
            {
                "kind": "pou",
                "name": name,
                "pou_type": "functionBlock",
                "decl": (d / name / f"{name}.decl.st").read_text(encoding="utf-8"),
                "impl": (d / name / f"{name}.impl.st").read_text(encoding="utf-8"),
            }
        )
    decl, impl = program()
    objs.append({"kind": "pou", "name": "PRG_SrCheck", "pou_type": "program", "decl": decl, "impl": impl})
    n = len(SEQ)
    batches = [{"name": a, "exprs": [f"PRG_SrCheck.{a}[{k}]" for k in range(1, n + 1)]} for a in ("aSrStd", "aSrCds", "aRsStd", "aRsCds")]
    job = {
        "project": str(REPO / "build" / "cds" / "compat-check.project"),
        "device": cdsrun.CONTROL_WIN,
        "objects": objs,
        "tasks": [{"name": "Task_Check", "interval_ms": 20, "priority": 1, "pous": ["PRG_SrCheck"]}],
        "build": True,
        "online": {"wait": {"expr": "PRG_SrCheck.xDone", "timeout_s": 30, "poll_ms": 200}, "read_values": batches},
    }
    try:
        res = online.run_script("c2s7_online.py", job, "compat-check", timeout_s=600, online=True)
    except online.RuntimeBusy as exc:
        print(f"runtime busy: {exc}")
        return 3
    if not res.get("ok") or res.get("build", {}).get("errors"):
        print(json.dumps({k: res.get(k) for k in ("error", "build", "log")}, ensure_ascii=False, indent=1)[:4000])
        return 1
    vals = {k: [v.strip().upper() == "TRUE" for v in b["values"]] for k, b in res["batches"].items()}
    summary = {
        "what": "CDS_SR/CDS_RS (ST′ от s7conv) против Standard.SR/RS в CODESYS Control Win 3.5.17.30",
        "sequence": [{"set": bool(a), "reset": bool(b)} for a, b in SEQ],
        "sr_standard": vals["aSrStd"],
        "sr_cds": vals["aSrCds"],
        "rs_standard": vals["aRsStd"],
        "rs_cds": vals["aRsCds"],
        "sr_equal": vals["aSrStd"] == vals["aSrCds"],
        "rs_equal": vals["aRsStd"] == vals["aRsCds"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: summary[k] for k in ("sr_equal", "rs_equal")}))
    return 0 if summary["sr_equal"] and summary["rs_equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
