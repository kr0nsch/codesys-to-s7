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
    sample: list[int] = field(default_factory=list)  # номера циклов (с 1), где пишутся выходы


def _header_types(csv_path: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    head = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    ins = [tuple(h[3:].split(":")) for h in head if h.startswith("in.")]
    outs = [tuple(h[4:].split(":")) for h in head if h.startswith("out.")]
    return [(a, b) for a, b in ins], [(a, b) for a, b in outs]  # type: ignore[misc]


def build_stream(
    block: str, kind: str, csv_path: Path, period: int = PERIOD_MS, sample: str = "all", max_cycles: int = MAX_CYCLES
) -> Stream:
    """Циклы стенда из CSV: строка держится до t_ms следующей; sample="rows" — выходы только на первом и
    последнем цикле каждой строки (долгие сценарии), "all" — на каждом цикле."""
    from c2s7.sim.scenarios import read_csv

    ins, outs = _header_types(csv_path)
    st = Stream(block, kind, ins, outs)
    rows = read_csv(csv_path)
    cur: dict[str, Any] = {}
    for i, r in enumerate(rows):
        nxt = rows[i + 1] if i + 1 < len(rows) and rows[i + 1].scenario == r.scenario else None
        n = max(1, round((nxt.t_ms - r.t_ms) / period)) if nxt is not None else 1
        cur.update({p: v for p, (_t, v) in r.inputs.items()})
        first = len(st.cycles) + 1
        for _ in range(n):
            st.cycles.append(dict(cur))
            st.scen.append(r.scenario)
        if sample == "rows":
            st.sample += sorted({first, len(st.cycles)})
    if sample == "all":
        st.sample = list(range(1, len(st.cycles) + 1))
    if len(st.cycles) > max_cycles:
        raise ValueError(f"{block}: {len(st.cycles)} циклов > {max_cycles}")
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
    if t.startswith("STRING"):
        return "'" + str(v).replace("'", "$'") + "'"
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


def _id(path: str) -> str:
    """Путь сценария (status.faultCode, a[3]) → часть идентификатора массива."""
    return re.sub(r"[^A-Za-z0-9_]", "_", path)


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
            decl.append(f"    aIn_{b}_{_id(name)} : ARRAY[1..{n}] OF {_st_type(typ)} := {_array_init(vals)};")
        m = len(s.sample)
        for name, typ in s.outputs:
            decl.append(f"    aOut_{b}_{_id(name)} : ARRAY[1..{m}] OF {_st_type(typ)};")
        all_cycles = s.sample == list(range(1, n + 1))
        if not all_cycles:
            decl.append(f"    aSmp_{b} : ARRAY[1..{m}] OF DINT := [{', '.join(map(str, s.sample))}];")
            decl.append(f"    j_{b} : DINT := 1;")
        idx = "k" if all_cycles else f"j_{b}"
        body.append(f"    IF k <= {n} THEN")
        if s.kind == "FC":
            args = ", ".join(f"{name} := aIn_{b}_{_id(name)}[k]" for name, _ in s.inputs)
            outs = [o for o, _ in s.outputs if o != b]
            oargs = "".join(f", {o} => aOut_{b}_{_id(o)}[{idx}]" for o in outs)
            target = f"aOut_{b}_{b}[{idx}]" if any(o == b for o, _ in s.outputs) else None
            call = f"{b}({args}{oargs})"
            body.append(f"        {target} := {call};" if target else f"        {call};")
        else:
            callee = f"inst_{b}" if s.kind == "FB" else b
            for name, _ in s.inputs:  # входы (и вложенные пути) — присваиванием до вызова
                body.append(f"        {callee}.{name} := aIn_{b}_{_id(name)}[k];")
            body.append(f"        {callee}();")
            if all_cycles:
                for o, _ in s.outputs:
                    body.append(f"        aOut_{b}_{_id(o)}[k] := {callee}.{o};")
            else:
                body.append(f"        IF j_{b} <= {m} THEN")
                body.append(f"            IF k = aSmp_{b}[j_{b}] THEN")
                for o, _ in s.outputs:
                    body.append(f"                aOut_{b}_{_id(o)}[j_{b}] := {callee}.{o};")
                body.append(f"                j_{b} := j_{b} + 1;")
                body.append("            END_IF")
                body.append("        END_IF")
        body.append("    END_IF")
    body += [f"    IF k >= {nmax} THEN", "        xDone := TRUE;", "    END_IF", "END_IF"]
    decl.append("END_VAR")
    return "\n".join(decl) + "\n", "\n".join(body) + "\n", nmax


def read_batches(streams: list[Stream], nmax: int) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = [{"name": "time", "exprs": [f"PRG_Trace.aTime[{k}]" for k in range(1, nmax + 1)]}]
    for s in streams:
        for o, _ in s.outputs:
            exprs = [f"PRG_Trace.aOut_{s.block}_{_id(o)}[{k}]" for k in range(1, len(s.sample) + 1)]
            batches.append({"name": f"{s.block}.{o}", "exprs": exprs})
    chunked: list[dict[str, Any]] = []  # пакеты по 2000 выражений (одно чтение read_values)
    for b in batches:
        for i in range(0, len(b["exprs"]), 2000):
            chunked.append({"name": f"{b['name']}#{i // 2000}", "exprs": b["exprs"][i : i + 2000]})
    return chunked


def merge_batches(got: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name in sorted(got, key=lambda n: (n.rsplit("#", 1)[0], int(n.rsplit("#", 1)[1]))):
        base = name.rsplit("#", 1)[0]
        merged.setdefault(base, {"values": []})["values"].extend(got[name]["values"])
    return merged


def write_trace(s: Stream, got: dict[str, Any], times: list[int], dest: Path, meta: dict[str, Any]) -> None:
    t0 = times[0]
    vals = {o: [parse_raw(v, t) for v in got[f"{s.block}.{o}"]["values"]] for o, t in s.outputs}
    pos = {c: i for i, c in enumerate(s.sample)}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["scenario", "cycle", "t_ms", *[f"in.{n}:{t}" for n, t in s.inputs], *[f"out.{n}:{t}" for n, t in s.outputs]])
    for k, cyc in enumerate(s.cycles):
        row = [s.scen[k], k + 1, (times[k] - t0) & 0xFFFFFFFF]
        row += [_fmt(cyc[n], t) for n, t in s.inputs]
        i = pos.get(k + 1)
        row += [_fmt(vals[n][i], t) if i is not None else "" for n, t in s.outputs]
        w.writerow(row)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "oracle-codesys.csv").write_text(buf.getvalue(), encoding="utf-8", newline="\n")
    full = {
        "format": "oracle-codesys/1",
        "tool": "c2s7 0.1.0 tools/codesys/trace.py",
        "codesys": "3.5.17.30",
        "device": "CODESYS Control Win V3 (4096, 0000 0001, 3.5.17.30)",
        "date": dt.date.today().isoformat(),
        "task": "TraceTask",
        "period_ms": PERIOD_MS,
        "cycles": len(s.cycles),
        "sampled_cycles": len(s.sample),
        "scenarios": sorted(set(s.scen), key=s.scen.index),
        "regime": "R2",
        **meta,
    }
    (dest / "oracle-codesys.json").write_text(json.dumps(full, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


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
    if t.startswith("STRING"):
        if len(s) >= 2 and s[0] == s[-1] == "'":
            s = s[1:-1]
        return s.replace("$'", "'").replace("$$", "$")
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


def run_job(label: str, streams: list[Stream], imports: list[str], objects: list[dict[str, Any]], timeout_s: float = 1500) -> tuple[dict[str, Any], list[int]] | int:
    """Стенд в Control Win: импорт/объекты + PRG_Trace в TraceTask; результат — (пакеты значений, TIME() циклов)."""
    import cdsrun

    import online

    decl, impl, nmax = trace_program(streams)
    work = REPO / "build" / "trace" / label
    work.mkdir(parents=True, exist_ok=True)
    (work / "PRG_Trace.st").write_text(decl + impl, encoding="utf-8")
    job = {
        "project": str(work / "trace.project"),
        "device": cdsrun.CONTROL_WIN,
        "libraries": [["Standard", "Standard, * (System)"]],
        "imports": imports,
        "objects": [*objects, {"kind": "pou", "name": "PRG_Trace", "pou_type": "program", "decl": decl, "impl": impl}],
        "tasks": [{"name": "TraceTask", "interval_ms": PERIOD_MS, "priority": 1, "pous": ["PRG_Trace"]}],
        "build": True,
        "online": {
            "wait": {"expr": "PRG_Trace.xDone", "timeout_s": nmax * PERIOD_MS / 1000 * 3 + 60, "poll_ms": 500},
            "read": ["PRG_Trace.k"],
            "read_values": read_batches(streams, nmax),
        },
    }
    try:
        res = online.run_script("c2s7_online.py", job, f"trace-{label}", timeout_s=timeout_s, online=True)
    except online.RuntimeBusy as exc:
        print(f"runtime busy: {exc}")
        return 3
    (work / "result.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    b = res.get("build", {})
    print(f"CODESYS {label}: ok={res.get('ok')} сборка: ошибок {b.get('errors')}, ожидание xDone: {res.get('wait_ok')}")
    for m in b.get("messages", [])[:30]:
        if m["severity"] in ("Error", "FatalError"):
            print(f"  {m['severity']} {m['object']}: {m['text']}")
    if res.get("error") or not res.get("wait_ok"):
        print(res.get("error") or "\n".join(res.get("log", [])[-20:]))
        return 1
    got = merge_batches(res["batches"])
    times = [parse_raw(v, "TIME") for v in got["time"]["values"]]
    return got, times


def run_corpus(timeout_s: float = 1500) -> int:
    import builder as B
    from corpus.common import case

    streams, specs = corpus_streams()
    work = REPO / "build" / "trace" / "corpus"
    work.mkdir(parents=True, exist_ok=True)
    c = case(include_il=False)
    duts = c.duts
    c.duts = []
    c.pous = [p for p in c.pous if p.name != "PRG_Corpus"]
    xml = work / "corpus-trace.xml"
    xml.write_text(B.pretty(B.project_xml(c, "ZarechnayaTrace")), encoding="utf-8")
    objs = [{"kind": "dut", "name": d.name, "decl": d.text} for d in duts]
    r = run_job("corpus", streams, [str(xml)], objs, timeout_s)
    if isinstance(r, int):
        return r
    got, times = r
    for s in streams:
        cs = specs[s.block]
        src = cs.path / "source.cds.xml"
        meta = {
            "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest() if src.exists() else None,
            "inputs_from": f"scenarios/{s.block}.csv (строка держится до t_ms следующей)",
        }
        write_trace(s, got, times, cs.path, meta)
        print(f"  {s.block}: {len(s.cycles)} циклов")
    return 0


def layout_objects(root: Path) -> list[dict[str, Any]]:
    """Объекты CODESYS из ST-раскладки: DUT, GVL (кроме списков Persistent), POU с декларацией и телом."""
    src = root / "src"
    objs: list[dict[str, Any]] = []
    for f in sorted(src.rglob("*.dut.st")):
        objs.append({"kind": "dut", "name": f.name.split(".")[0], "decl": f.read_text(encoding="utf-8")})
    for f in sorted(src.rglob("*.gvl.st")):
        objs.append({"kind": "gvl", "name": f.name.split(".")[0], "decl": f.read_text(encoding="utf-8")})
    for decl in sorted(src.rglob("*.decl.st")):
        stem = decl.name[: -len(".decl.st")]
        if "." in stem or decl.parent.name != stem:
            continue
        text = decl.read_text(encoding="utf-8")
        m = re.search(r"^\s*(PROGRAM|FUNCTION_BLOCK|FUNCTION)\s+(\w+)(?:\s*:\s*(\w+))?", text, re.MULTILINE | re.IGNORECASE)
        if m is None:
            continue
        kind = {"PROGRAM": "program", "FUNCTION_BLOCK": "functionBlock", "FUNCTION": "function"}[m.group(1).upper()]
        impl = decl.with_name(f"{stem}.impl.st")
        objs.append(
            {
                "kind": "pou",
                "name": stem,
                "pou_type": kind,
                "return_type": m.group(3),
                "decl": text,
                "impl": impl.read_text(encoding="utf-8") if impl.exists() else "",
            }
        )
    return objs


def load_result(label: str) -> tuple[dict[str, Any], list[int]] | None:
    """Результат прошлого прогона стенда (build/trace/<label>/result.json), чтобы не гонять рантайм повторно."""
    path = REPO / "build" / "trace" / label / "result.json"
    if not path.exists():
        return None
    res = json.loads(path.read_text(encoding="utf-8"))
    if not res.get("wait_ok") or "batches" not in res:
        return None
    got = merge_batches(res["batches"])
    return got, [parse_raw(v, "TIME") for v in got["time"]["values"]]


def run_ring(timeout_s: float = 1500, reuse: bool = False) -> int:
    """Кейс 1, R2: трассы источника (ST s7-to-codesys) и ST′ (s7conv --timers standard из SCL c2s7)."""
    from c2s7.api import run_migrate
    from c2s7.convert.core import Options
    from c2s7.verify import s7conv_clone as SC
    from c2s7.verify.roundtrip import run_s7conv

    fixture = REPO / "tests" / "fixtures" / "s7-to-codesys"
    streams = [
        build_stream(f.stem, "FB", f, sample="rows", max_cycles=40000) for f in sorted((fixture / "scenarios").glob("*.csv"))
    ]
    clone = SC.check(SC.default_dir(REPO))
    out = REPO / "build" / "trace" / "ring-out"
    run_migrate(fixture, out, Options())
    rt = run_s7conv(out, clone, timers="standard")
    dest_root = REPO / "tests" / "oracle" / "ring"
    for label, root in (("source", fixture), ("st_prime", rt.st_prime)):
        prev = load_result(f"ring-{label}") if reuse else None
        r = prev if prev is not None else run_job(f"ring-{label}", streams, [], layout_objects(root), timeout_s)
        if isinstance(r, int):
            return r
        got, times = r
        for s in streams:
            meta = {
                "inputs_from": f"tests/fixtures/s7-to-codesys/scenarios/{s.block}.csv (строка держится до t_ms следующей)",
                "code": "ST s7-to-codesys @ 2285760c (фикстура)" if label == "source" else "ST′: s7conv --timers standard из tia/sources c2s7",
            }
            write_trace(s, got, times, dest_root / label / s.block, meta)
            print(f"  {label} {s.block}: {len(s.cycles)} циклов")
    return 0


def _fmt(v: Any, t: str) -> str:
    from refcommon import fmt

    return fmt(v, t)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["corpus", "ring", "program"])
    ap.add_argument("--reuse", action="store_true", help="взять готовый build/trace/*/result.json, если есть")
    args = ap.parse_args(argv)
    sys.path.insert(0, str(REPO / "scenarios" / "reference"))
    if args.what == "program":
        streams, _ = corpus_streams()
        d, i, _n = trace_program(streams)
        print(d + i)
        return 0
    if args.what == "ring":
        return run_ring(reuse=args.reuse)
    return run_corpus()


if __name__ == "__main__":
    sys.exit(main())
