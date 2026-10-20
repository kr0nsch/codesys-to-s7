"""Пробник TIA `probe/` (ТЗ M8, 00-INDEX §4.9): на конструкцию verify — минимальный блок SCL с ожидаемыми
значениями по CODESYS и строка RESULTS.csv для человека с TIA Portal и PLCSIM.

Ожидания взяты только из проверенного: проба M0 в CODESYS Control Win 3.5.17.30 (docs/PROBES.md) и
трассы корпуса (oracle-codesys.csv). Это поставляемый артефакт, а не доказательство готовности:
`observed` = `not-run`, пока его не заполнит человек (`ok`, `error:<текст>`, `value:<значение>`).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from c2s7 import TOOL

COLUMNS = ["probe_id", "construct", "file", "expected", "observed", "ide", "ide_version", "date", "notes"]


@dataclass(frozen=True)
class Probe:
    id: str
    rule: str
    construct: str
    block: str
    scl: str
    expected: str
    minutes: int
    source: str


def _fb(name: str, outputs: list[tuple[str, str]], body: str, statics: list[tuple[str, str]] | None = None) -> str:
    outs = "\n".join(f"      {n} : {t};" for n, t in outputs)
    stat = ""
    if statics:
        stat = "   VAR\n" + "\n".join(f"      {n} : {t};" for n, t in statics) + "\n   END_VAR\n\n"
    return (
        f"FUNCTION_BLOCK \"{name}\"\n{{ S7_Optimized_Access := 'TRUE' }}\nVERSION : 0.1\n"
        f"   VAR_OUTPUT\n{outs}\n   END_VAR\n\n{stat}BEGIN\n{body}END_FUNCTION_BLOCK\n"
    )


PROBES: list[Probe] = [
    Probe(
        "P01",
        "C2S7-SEM-ROUND",
        "REAL_TO_INT на половине",
        "PRB_Round",
        _fb(
            "PRB_Round",
            [("iR25", "Int"), ("iRm25", "Int"), ("iR35", "Int"), ("iR05", "Int")],
            "\t#iR25 := REAL_TO_INT(2.5);\n\t#iRm25 := REAL_TO_INT(-2.5);\n\t#iR35 := REAL_TO_INT(3.5);\n"
            "\t#iR05 := REAL_TO_INT(0.5);\n",
        ),
        "iR25=3; iRm25=-3; iR35=4; iR05=1",
        10,
        "проба M0, Control Win 3.5.17.30 (docs/PROBES.md)",
    ),
    Probe(
        "P02",
        "C2S7-SEM-LIMIT",
        "LIMIT при MN > MX",
        "PRB_Limit",
        _fb(
            "PRB_Limit",
            [("iLim", "Int"), ("iLimHi", "Int")],
            "\t#iLim := LIMIT(MN := 10, IN := 5, MX := 0);\n\t#iLimHi := LIMIT(MN := 10, IN := 20, MX := 0);\n",
        ),
        "iLim=0; iLimHi=0 (результат — MX)",
        10,
        "проба M0 (LIMIT(10, 5, 0) = 0, LIMIT(10, 20, 0) = 0)",
    ),
    Probe(
        "P03",
        "C2S7-SEM-OVERFLOW",
        "разрядность промежуточного результата и перенос INT",
        "PRB_Overflow",
        _fb(
            "PRB_Overflow",
            [("diMul", "DInt"), ("iWrap", "Int")],
            "\t#a := 300;\n\t#b := 300;\n\t#diMul := #a * #b;\n\t#c := 32767;\n\t#iWrap := #c + 1;\n",
            [("a", "Int"), ("b", "Int"), ("c", "Int")],
        ),
        "diMul=90000; iWrap=-32768",
        10,
        "проба M0 (DINT := INT * INT = 90000; 32767 + 1 = -32768)",
    ),
    Probe(
        "P04",
        "C2S7-SEM-SRRS",
        "SR/RS при SET = RESET = 1 (CDS_SR/CDS_RS c2s7)",
        "PRB_SrRs",
        _fb(
            "PRB_SrRs",
            [("xSr", "Bool"), ("xRs", "Bool")],
            "\t#fbSr(SET1 := TRUE, RESET := TRUE);\n\t#xSr := #fbSr.Q1;\n"
            "\t#fbRs(SET := TRUE, RESET1 := TRUE);\n\t#xRs := #fbRs.Q1;\n",
            [("fbSr", '"CDS_SR"'), ("fbRs", '"CDS_RS"')],
        ),
        "xSr=TRUE; xRs=FALSE (как Standard.SR/RS CODESYS)",
        15,
        "проба M0 (SR → TRUE, RS → FALSE); блоки — tia/compat",
    ),
    Probe(
        "P05",
        "C2S7-SEM-TIMER-Q",
        "самосбрасывающийся таймер: импульс на один вызов",
        "PRB_SelfReset",
        _fb(
            "PRB_SelfReset",
            [("diPulses", "DInt"), ("diCalls", "DInt")],
            "\t#fbT(IN := NOT #xQ, PT := T#500MS, Q => #xQ);\n\t#diCalls := #diCalls + 1;\n"
            "\tIF #xQ THEN\n\t\t#diPulses := #diPulses + 1;\n\tEND_IF;\n",
            [("fbT", "TON_TIME"), ("xQ", "Bool")],
        ),
        "Q = TRUE ровно на один вызов подряд; между импульсами ≥ 500 мс (diPulses растёт на 1 за импульс)",
        20,
        "трасса Control Win corpus/st/FB_TimeIdioms (R2): Q = TRUE ровно на один вызов",
    ),
    Probe(
        "P06",
        "C2S7-GFX-DOUBLECOIL",
        "двойная катушка: побеждает последняя сеть",
        "PRB_DoubleCoil",
        _fb(
            "PRB_DoubleCoil",
            [("xOut", "Bool")],
            "\t#xOut := TRUE;   // сеть 1\n\t#xOut := FALSE;  // сеть 2 — последняя\n",
        ),
        "xOut=FALSE",
        5,
        "трасса Control Win corpus/ld/PRG_PumpInterlock (R2)",
    ),
]


def probes_for(rules: set[str] | None) -> list[Probe]:
    return [p for p in PROBES if rules is None or p.rule in rules]


def readme(probes: list[Probe]) -> str:
    total = sum(p.minutes for p in probes)
    lines = [
        "# Пробник TIA Portal",
        "",
        f"Создано {TOOL}. На каждую конструкцию с исходом verify — минимальный блок SCL и ожидаемые",
        "значения по CODESYS (проба M0 в Control Win 3.5.17.30 и трассы корпуса). Автор c2s7 TIA не имеет:",
        "это процедура для человека с TIA V19/V21 и PLCSIM, а не доказательство готовности.",
        "",
        "Порядок: External source files → Add new external file → `P*.scl` → Generate blocks from source →",
        "OB1 вызывает экземпляры → PLCSIM → значения выходов в `RESULTS.csv` (`observed`: `ok`,",
        "`error:<текст дословно>`, `value:<значение>`). Для P04 сначала импортируйте `tia/compat/`.",
        "",
        "| Проба | Правило | Конструкция | Ожидание (CODESYS) | Минут |",
        "|---|---|---|---|---|",
    ]
    for p in probes:
        lines.append(f"| {p.id} | {p.rule} | {p.construct} | {p.expected} | {p.minutes} |")
    lines += ["", f"Итого ≈ {total} мин.", ""]
    return "\n".join(lines)


def results_csv(probes: list[Probe]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for p in probes:
        w.writerow([p.id, p.construct, f"{p.id}_{p.block}.scl", p.expected, "not-run", "", "", "", p.source])
    return buf.getvalue()


def probe_files(rules: set[str] | None = None) -> dict[str, tuple[str, bool]]:
    """Файлы probe/: путь → (текст, формат TIA с BOM/CRLF)."""
    probes = probes_for(rules)
    files: dict[str, tuple[str, bool]] = {
        "probe/README.md": (readme(probes), False),
        "probe/RESULTS.csv": (results_csv(probes), False),
    }
    for p in probes:
        files[f"probe/{p.id}_{p.block}.scl"] = (f"// создано {TOOL} · пробник {p.id} · {p.rule}\n" + p.scl, True)
    return files


def write_probe(out: Path) -> int:
    """`c2s7 probe <out>`: пробы для правил verify из out/MIGRATION_REPORT.json (без отчёта — все)."""
    from c2s7.emit.files import write_tia

    rules: set[str] | None = None
    rep = out / "MIGRATION_REPORT.json"
    if rep.exists():
        data = json.loads(rep.read_text(encoding="utf-8"))
        rules = {f["rule"] for f in data.get("findings", [])} | {
            r for f in data.get("findings", []) for r in f.get("related", [])
        }
    files = probe_files(rules)
    for rel, (text, tia) in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if tia:
            write_tia(path, text)
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
    return len(files) - 2
