"""Трассы CODESYS Control Win, режим R2 «фиксированный цикл» (ТЗ M10, 00-INDEX §4.5).

Стенд: копия корпуса без его задач и одна задача TraceTask (10 мс) с программой PRG_Trace, которую этот
скрипт строит из сценариев CSV: на цикле k она берёт входы строки k из массивов (строка сценария
держится до момента следующей строки — t_ms / период циклов), один раз вызывает POU, пишет выходы и
TIME() начала цикла в массивы; после N циклов ставит xDone. Хост ждёт xDone и читает массивы
`read_values` пакетами. Рантайм общий — под блокировкой (tools/codesys/online.py).

    python tools/codesys/trace.py corpus      # 11 POU корпуса → corpus/<язык>/<кейс>/oracle-codesys.{csv,json}

Сравнение c2s7.sim с трассой (по записанным t_ms) — tests/codesys/test_corpus_codesys.py и
tools/codesys/trace.py compare.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (HERE, REPO / "tools" / "probes", REPO / "tools" / "corpus", REPO / "src", REPO):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

PERIOD_MS = 10
MAX_CYCLES = 1500


@dataclass
class Stream:
    """Последовательность циклов одного POU: входы по циклам и список выходов."""

    block: str
    kind: str  # FB | PRG | FC
    inputs: list[tuple[str, str]]  # (имя, тип)
    outputs: list[tuple[str, str]]
    cycles: list[dict[str, Any]] = field(default_factory=list)
    scen: list[str] = field(default_factory=list)


def _header_types(csv_path: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    head = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    ins = [tuple(h[3:].split(":")) for h in head if h.startswith("in.")]
    outs = [tuple(h[4:].split(":")) for h in head if h.startswith("out.")]
    return [(a, b) for a, b in ins], [(a, b) for a, b in outs]  # type: ignore[misc]


def build_stream(block: str, kind: str, csv_path: Path, period: int = PERIOD_MS) -> Stream:
    from c2s7.sim.scenarios import read_csv

    ins, outs = _header_types(csv_path)
    st = Stream(block, kind, ins, outs)
    rows = read_csv(csv_path)
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) and rows[i + 1].scenario == r.scenario else None
        n = max(1, round((nxt.t_ms - r.t_ms) / period)) if nxt is not None else 1
        vals = {p: v for p, (_t, v) in r.inputs.items()}
        for _ in range(n):
            st.cycles.append(dict(vals))
            st.scen.append(r.scenario)
    if len(st.cycles) > MAX_CYCLES:
        raise ValueError(f"{block}: {len(st.cycles)} циклов > {MAX_CYCLES}")
    return st


def _lit(v: Any, typ: str) -> str:
    t = typ.upper()
    if t == "BOOL":
        return "TRUE" if v else "FALSE"
    if t == "TIME":
        return f"T#{int(v)}MS"
    if t in ("REAL", "LREAL"):
        r = repr(float(v))
        return r if ("." in r or "e" in r) else r + ".0"
    return str(int(v))


def _array_init(values: list[str]) -> str:
    """[v1, 3(v2), …] — подряд идущие повторы сжимаются."""
    out: list[str] = []
    i = 0
    while i < len(values):
        j = i
        while j < len(values) and values[j] == values[i]:
            j += 1
        n = j - i
        out.append(f"{n}({values[i]})" if n > 1 else values[i])
        i = j
    return "[" + ", ".join(out) + "]"


def _st_type(typ: str) -> str:
    return "STRING(80)" if typ.upper() == "STRING" else typ.upper()


def trace_program(streams: list[Stream]) -> tuple[str, str, int]:
    nmax = max(len(s.cycles) for s in streams)
    decl = ["PROGRAM PRG_Trace", "VAR", "    k : DINT;", "    xDone : BOOL;", f"    aTime : ARRAY[1..{nmax}] OF TIME;"]
    body = ["IF NOT xDone THEN", "    k := k + 1;", "    aTime[k] := TIME();"]
    for s in streams:
        n = len(s.cycles)
        b = s.block
        if s.kind == "FB":
            decl.append(f"    inst_{b} : {b};")
        for name, typ in s.inputs:
            vals = [_lit(c[name], typ) for c in s.cycles]
            decl.append(f"    aIn_{b}_{name} : ARRAY[1..{n}] OF {_st_type(typ)} := {_array_init(vals)};")
        for name, typ in s.outputs:
            decl.append(f"    aOut_{b}_{name} : ARRAY[1..{n}] OF {_st_type(typ)};")
        args = ", ".join(f"{name} := aIn_{b}_{name}[k]" for name, _ in s.inputs)
        body.append(f"    IF k <= {n} THEN")
        if s.kind == "FC":
            outs = [o for o, _ in s.outputs if o != b]
            oargs = "".join(f", {o} => aOut_{b}_{o}[k]" for o in outs)
            target = f"aOut_{b}_{b}[k]" if any(o == b for o, _ in s.outputs) else None
            call = f"{b}({args}{oargs})"
            body.append(f"        {target} := {call};" if target else f"        {call};")
        else:
            callee = f"inst_{b}" if s.kind == "FB" else b
            body.append(f"        {callee}({args});")
            for o, _ in s.outputs:
                body.append(f"        aOut_{b}_{o}[k] := {callee}.{o};")
        body.append("    END_IF")
    body += [f"    IF k >= {nmax} THEN", "        xDone := TRUE;", "    END_IF", "END_IF"]
    decl.append("END_VAR")
    return "\n".join(decl) + "\n", "\n".join(body) + "\n", nmax


_RAW = re.compile(r"^[A-Z_]+#")


def parse_raw(raw: str | None, typ: str) -> Any:
    from c2s7.st import literals as L

    if raw is None:
        return None
    s = raw.strip()
    t = typ.upper()
    if t == "BOOL":
        return s.upper() == "TRUE"
    if t == "TIME":
        body = s.split("#", 1)[1] if "#" in s else s
        return L.parse_duration_ns(body) // 1_000_000
    s = _RAW.sub("", s)
    if t in ("REAL", "LREAL"):
        return float(s)
    return int(s, 0) if s.lower().startswith("0x") else int(s)


def corpus_streams() -> tuple[list[Stream], dict[str, Any]]:
    from corpus.common import load_specs

    specs = load_specs()
    streams = []
    for name, cs in specs.items():
        if not cs.in_codesys:
            continue
        kind = {"function": "FC", "program": "PRG"}.get(cs.pou.kind, "FB")
        streams.append(build_stream(name, kind, REPO / "scenarios" / f"{name}.csv"))
    return streams, specs


def run_corpus(timeout_s: float = 1500) -> int:
    import builder as B
    import cdsrun
    import online
    from corpus.common import case

    streams, specs = corpus_streams()
    decl, impl, nmax = trace_program(streams)
    work = REPO / "build" / "trace"
    work.mkdir(parents=True, exist_ok=True)
    c = case(include_il=False)
    duts = c.duts
    c.duts = []
    c.pous = [p for p in c.pous if p.name != "PRG_Corpus"]
    xml = work / "corpus-trace.xml"
    xml.write_text(B.pretty(B.project_xml(c, "ZarechnayaTrace")), encoding="utf-8")
    (work / "PRG_Trace.st").write_text(decl + impl, encoding="utf-8")
    batches = [{"name": "time", "exprs": [f"PRG_Trace.aTime[{k}]" for k in range(1, nmax + 1)]}]
    for s in streams:
        for o, _ in s.outputs:
            batches.append(
                {"name": f"{s.block}.{o}", "exprs": [f"PRG_Trace.aOut_{s.block}_{o}[{k}]" for k in range(1, len(s.cycles) + 1)]}
            )
    job = {
        "project": str(work / "trace.project"),
        "device": cdsrun.CONTROL_WIN,
        "libraries": [["Standard", "Standard, * (System)"]],
        "imports": [str(xml)],
        "objects": [{"kind": "dut", "name": d.name, "decl": d.text} for d in duts]
        + [{"kind": "pou", "name": "PRG_Trace", "pou_type": "program", "decl": decl, "impl": impl}],
        "tasks": [{"name": "TraceTask", "interval_ms": PERIOD_MS, "priority": 1, "pous": ["PRG_Trace"]}],
        "build": True,
        "online": {
            "wait": {"expr": "PRG_Trace.xDone", "timeout_s": nmax * PERIOD_MS / 1000 * 3 + 60, "poll_ms": 500},
            "read": ["PRG_Trace.k"],
            "read_values": batches,
        },
    }
    try:
        res = online.run_script("c2s7_online.py", job, "trace-corpus", timeout_s=timeout_s, online=True)
    except online.RuntimeBusy as exc:
        print(f"runtime busy: {exc}")
        return 3
    (work / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    b = res.get("build", {})
    print(f"CODESYS ok={res.get('ok')} сборка: ошибок {b.get('errors')}, ожидание xDone: {res.get('wait_ok')}")
    for m in b.get("messages", [])[:30]:
        print(f"  {m['severity']} {m['object']}: {m['text']}")
    if res.get("error") or not res.get("wait_ok"):
        print(res.get("error") or "\n".join(res.get("log", [])[-20:]))
        return 1
    got = res["batches"]
    times = [parse_raw(v, "TIME") for v in got["time"]["values"]]
    t0 = times[0]
    date = dt.date.today().isoformat()
    for s in streams:
        cs = specs[s.block]
        outs = {o: [parse_raw(v, t) for v in got[f"{s.block}.{o}"]["values"]] for o, t in s.outputs}
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["scenario", "cycle", "t_ms", *[f"in.{n}:{t}" for n, t in s.inputs], *[f"out.{n}:{t}" for n, t in s.outputs]])
        for k, cyc in enumerate(s.cycles):
            row = [s.scen[k], k + 1, (times[k] - t0) & 0xFFFFFFFF]
            row += [_fmt(cyc[n], t) for n, t in s.inputs]
            row += [_fmt(outs[n][k], t) for n, t in s.outputs]
            w.writerow(row)
        (cs.path / "oracle-codesys.csv").write_text(buf.getvalue(), encoding="utf-8", newline="\n")
        src = cs.path / "source.cds.xml"
        meta = {
            "format": "oracle-codesys/1",
            "tool": "c2s7 0.1.0 tools/codesys/trace.py",
            "codesys": "3.5.17.30",
            "device": "CODESYS Control Win V3 (4096, 0000 0001, 3.5.17.30)",
            "date": date,
            "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest() if src.exists() else None,
            "task": "TraceTask",
            "period_ms": PERIOD_MS,
            "cycles": len(s.cycles),
            "scenarios": sorted(set(s.scen), key=s.scen.index),
            "regime": "R2",
            "inputs_from": f"scenarios/{s.block}.csv (строка держится до t_ms следующей)",
        }
        (cs.path / "oracle-codesys.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"  {s.block}: {len(s.cycles)} циклов")
    return 0


def _fmt(v: Any, t: str) -> str:
    from refcommon import fmt

    return fmt(v, t)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["corpus", "program"])
    args = ap.parse_args(argv)
    sys.path.insert(0, str(REPO / "scenarios" / "reference"))
    if args.what == "program":
        streams, _ = corpus_streams()
        d, i, _n = trace_program(streams)
        print(d + i)
        return 0
    return run_corpus()


if __name__ == "__main__":
    sys.exit(main())
