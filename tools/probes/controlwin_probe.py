"""Проба M0 в CODESYS Control Win: поведение, от которого зависят правила C2S7-SEM/-ADDR.

    python tools/probes/controlwin_probe.py      # нужен CODESYS 3.5.17.30 и рантайм (под блокировкой)

Программа PRG_M0 за один цикл вычисляет всё нужное и ставит xDone; хост читает значения.
Результат — build/probes/controlwin.json; выводы — в docs/PROBES.md.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "tools" / "codesys"), str(HERE)]

import cdsrun  # noqa: E402

import online  # noqa: E402

F_OUT_DECL = """FUNCTION F_M0Out : INT
VAR_INPUT
    xSet : BOOL;
END_VAR
VAR_OUTPUT
    iOut : INT := 7;
END_VAR
VAR
    iLocal : INT := 5;
END_VAR
"""
F_OUT_IMPL = """IF xSet THEN
    iOut := 99;
    iLocal := 42;
END_IF
F_M0Out := iLocal;
"""

GVL_DECL = """VAR_GLOBAL
    wOver AT %MW0 : WORD;
    xBit10 AT %MX1.0 : BOOL;
    xBit03 AT %MX0.3 : BOOL;
    bByte1 AT %MB1 : BYTE;
    dOver AT %MD1 : DWORD;
    wWord2 AT %MW2 : WORD;
END_VAR
"""

PRG_DECL = """PROGRAM PRG_M0
VAR
    xDone : BOOL;
    iR25, iR35, iRm25, iRm35, iR05, iR15 : INT;
    diR25 : DINT;
    fbSr : SR;
    fbRs : RS;
    xSrQ, xRsQ : BOOL;
    fbCtu : CTU;
    fbCtd : CTD;
    wCtuCv, wCtdCv : WORD;
    xCtuQ, xCtdQ : BOOL;
    i : UDINT;
    iLim : INT;
    iLimLo : INT;
    iF1, iF2, iO1, iO2 : INT;
    fbFt : F_TRIG;
    xFtFirst : BOOL;
    iOvf : INT := 32767;
    iA : INT := 300;
    iB : INT := 300;
    diMul : DINT;
    tWrap : TIME;
    tBig : TIME := T#30D;
    aBuf : ARRAY[0..199] OF INT;
    k : INT;
END_VAR
"""

PRG_IMPL = """IF NOT xDone THEN
    iR25 := REAL_TO_INT(2.5);
    iR35 := REAL_TO_INT(3.5);
    iRm25 := REAL_TO_INT(-2.5);
    iRm35 := REAL_TO_INT(-3.5);
    iR05 := REAL_TO_INT(0.5);
    iR15 := REAL_TO_INT(1.5);
    diR25 := REAL_TO_DINT(2.5);
    fbSr(SET1 := TRUE, RESET := TRUE);
    xSrQ := fbSr.Q1;
    fbRs(SET := TRUE, RESET1 := TRUE);
    xRsQ := fbRs.Q1;
    FOR i := 1 TO 70000 DO
        fbCtu(CU := TRUE, RESET := FALSE, PV := 1);
        fbCtu(CU := FALSE, RESET := FALSE, PV := 1);
    END_FOR
    wCtuCv := fbCtu.CV;
    xCtuQ := fbCtu.Q;
    fbCtd(CD := FALSE, LOAD := TRUE, PV := 2);
    fbCtd(CD := FALSE, LOAD := FALSE, PV := 2);
    FOR i := 1 TO 5 DO
        fbCtd(CD := TRUE, LOAD := FALSE, PV := 2);
        fbCtd(CD := FALSE, LOAD := FALSE, PV := 2);
    END_FOR
    wCtdCv := fbCtd.CV;
    xCtdQ := fbCtd.Q;
    iLim := LIMIT(10, 5, 0);
    iLimLo := LIMIT(10, 20, 0);
    iF1 := F_M0Out(xSet := TRUE, iOut => iO1);
    iF2 := F_M0Out(xSet := FALSE, iOut => iO2);
    fbFt(CLK := FALSE);
    xFtFirst := fbFt.Q;
    iOvf := iOvf + 1;
    diMul := iA * iB;
    tWrap := T#0MS - T#1MS;
    GVL_M0.wOver := 16#0108;
    GVL_M0.wWord2 := 16#ABCD;
    FOR k := 0 TO 199 DO
        aBuf[k] := k;
    END_FOR
    xDone := TRUE;
END_IF
"""

READ = [
    "PRG_M0.iR25",
    "PRG_M0.iR35",
    "PRG_M0.iRm25",
    "PRG_M0.iRm35",
    "PRG_M0.iR05",
    "PRG_M0.iR15",
    "PRG_M0.diR25",
    "PRG_M0.xSrQ",
    "PRG_M0.xRsQ",
    "PRG_M0.wCtuCv",
    "PRG_M0.xCtuQ",
    "PRG_M0.wCtdCv",
    "PRG_M0.xCtdQ",
    "PRG_M0.iLim",
    "PRG_M0.iLimLo",
    "PRG_M0.iF1",
    "PRG_M0.iF2",
    "PRG_M0.iO1",
    "PRG_M0.iO2",
    "PRG_M0.xFtFirst",
    "PRG_M0.iOvf",
    "PRG_M0.diMul",
    "PRG_M0.tWrap",
    "PRG_M0.tBig",
    "GVL_M0.xBit10",
    "GVL_M0.xBit03",
    "GVL_M0.bByte1",
    "GVL_M0.dOver",
]


def main() -> int:
    work = REPO / "build" / "cds"
    job = {
        "project": str(work / "m0-controlwin.project"),
        "device": cdsrun.CONTROL_WIN,
        "objects": [
            {"kind": "gvl", "name": "GVL_M0", "decl": GVL_DECL},
            {
                "kind": "pou",
                "name": "F_M0Out",
                "pou_type": "function",
                "return_type": "INT",
                "decl": F_OUT_DECL,
                "impl": F_OUT_IMPL,
            },
            {"kind": "pou", "name": "PRG_M0", "pou_type": "program", "decl": PRG_DECL, "impl": PRG_IMPL},
        ],
        "tasks": [{"name": "Task_M0", "interval_ms": 20, "priority": 1, "pous": ["PRG_M0"]}],
        "build": True,
        "online": {
            "wait": {"expr": "PRG_M0.xDone", "timeout_s": 30, "poll_ms": 200},
            "read": READ,
            "read_values": [{"name": "throughput200", "exprs": [f"PRG_M0.aBuf[{k}]" for k in range(200)]}],
        },
    }
    started = time.time()
    try:
        res = online.run_script("c2s7_online.py", job, "m0-controlwin", timeout_s=600, online=True)
    except online.RuntimeBusy as exc:
        print(f"runtime busy: {exc}")
        return 3
    res["host_seconds"] = round(time.time() - started, 1)
    out = REPO / "build" / "probes" / "controlwin.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    vals = res.get("values", {})
    with open(REPO / "build" / "probes" / "controlwin.txt", "w", encoding="utf-8") as fh:
        build = res.get("build", {})
        fh.write(f"ok={res.get('ok')} error={res.get('error')}\n")
        fh.write(f"build={build.get('errors')}/{build.get('warnings')}\n")
        for m in res.get("build", {}).get("messages", []):
            fh.write(f"  {m['severity']} {m['object']}: {m['text']}\n")
        for k in READ:
            fh.write(f"{k} = {vals.get(k)}\n")
        b = res.get("batches", {}).get("throughput200", {})
        fh.write(f"read_values 200: {b.get('seconds')} s via {b.get('how')}\n")
        fh.write("\n".join(res.get("log", [])) + "\n")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
