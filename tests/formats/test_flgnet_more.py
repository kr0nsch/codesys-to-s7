"""FlgNet: боксы арифметики, MOVE, сравнения, XOR, TON, прыжок LD; выход вне подмножества → SCL."""

from __future__ import annotations

import copy
import random
import sys
from pathlib import Path

import pytest
from c2s7.api import migrate
from c2s7.convert.core import Options
from c2s7.emit.simaticml.validate import validate
from c2s7.emit.simaticml.xsd import validate_xsd, xsd_dir
from c2s7.ingest.plcopen import load_plcopen
from c2s7.model import Project
from c2s7.sim.interp import Clock, Sim
from c2s7.st import nodes as A
from c2s7.verify.s7xml_reader import read_flgnet

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools" / "corpus")]
import builder as B  # noqa: E402

VARS = [
    B.V("i1", "INT", "VAR_INPUT"),
    B.V("i2", "INT", "VAR_INPUT"),
    B.V("a", "BOOL", "VAR_INPUT"),
    B.V("b", "BOOL", "VAR_INPUT"),
    B.V("iSum", "INT", "VAR_OUTPUT"),
    B.V("iMul", "INT", "VAR_OUTPUT"),
    B.V("iDiff", "INT", "VAR_OUTPUT"),
    B.V("iCopy", "INT", "VAR_OUTPUT"),
    B.V("xGe", "BOOL", "VAR_OUTPUT"),
    B.V("xX", "BOOL", "VAR_OUTPUT"),
    B.V("xQ", "BOOL", "VAR_OUTPUT"),
    B.V("fbT", "TON"),
]

FBD = B.Pou(
    "FB_Boxes",
    "functionBlock",
    B.Fbd(
        [
            B.Network([B.Out("iSum", B.Box("ADD", inputs={"In1": B.In("i1"), "In2": B.In("i2")}))]),
            B.Network([B.Out("iMul", B.Box("MUL", inputs={"In1": B.In("i1"), "In2": B.In("i2"), "In3": B.In("2")}))]),
            B.Network([B.Out("iDiff", B.Box("SUB", inputs={"In1": B.In("i1"), "In2": B.In("i2")}))]),
            B.Network([B.Out("iCopy", B.Box("MOVE", inputs={"In1": B.In("i2")}))]),
            B.Network([B.Out("xGe", B.Box("GE", inputs={"In1": B.In("i1"), "In2": B.In("i2")}))]),
            B.Network([B.Out("xX", B.Box("XOR", inputs={"In1": B.In("a"), "In2": B.In("b")}, negated=("In2",)))]),
            B.Network(
                [B.Out("xQ", B.Box("TON", inst="fbT", inputs={"IN": B.In("a"), "PT": B.In("T#300MS")}, out_pin="Q"))]
            ),
        ]
    ),
    VARS,
)

LDJ = B.Pou(
    "FB_LdJump",
    "functionBlock",
    B.Ld(
        [
            B.LdJump("lblSkip", cond=B.Contact("a")),
            B.Rung(B.Series(B.Contact("b"), B.Coil("xX"))),
            B.Rung(B.Series(B.Contact("b", neg=True), B.Coil("xGe")), label="lblSkip"),
        ]
    ),
    VARS,
)


def _emit(tmp_path: Path, pou: B.Pou, tia: str = "V21") -> tuple[object, Project, str | None]:
    f = tmp_path / f"{pou.name}.xml"
    f.write_text(B.pretty(B.project_xml(B.Case("x", pous=[pou]))), encoding="utf-8")
    proj = load_plcopen(f)
    res = migrate(proj, Options(tia=tia))
    xml = next(iter(res.simaticml.values()), None)
    return res, proj, xml


@pytest.mark.parametrize("pou", [FBD, LDJ], ids=["fbd-boxes", "ld-jump"])
def test_boxes_and_jump_roundtrip(tmp_path: Path, pou: B.Pou) -> None:
    res, proj, xml = _emit(tmp_path, pou)
    assert xml is not None, [(f.rule, f.detail) for f in res.collector.findings]  # type: ignore[attr-defined]
    assert validate(xml, "V21") == []
    if xsd_dir("V21", REPO) is not None:
        assert validate_xsd(xml, "V21", REPO) == []
    src = proj.pous[0]
    rb = read_flgnet(xml)
    p2 = copy.deepcopy(src)
    p2.text.body = rb.body
    p2.text.var_blocks.append(A.VarBlock("VAR_TEMP", [], [A.VarDecl(t, A.NamedType("BOOL")) for t in rb.temps]))
    c1, c2 = Clock(), Clock()
    s1, s2 = Sim(Project("a", "st", "a", "-", pous=[src]), c1), Sim(Project("b", "st", "b", "-", pous=[p2]), c2)
    i1, i2 = s1.new_instance(s1.pous[src.name.upper()]), s2.new_instance(s2.pous[src.name.upper()])
    rnd = random.Random(7)
    outs = [d.name.upper() for b, d in src.decls() if b.kind == "VAR_OUTPUT"]
    for k in range(60):
        c1.now_ms = c2.now_ms = 100 * k
        vals = {
            "i1": rnd.randint(-50, 50),
            "i2": rnd.randint(-50, 50),
            "a": rnd.random() < 0.6,
            "b": rnd.random() < 0.5,
        }
        s1.call_fb(i1, dict(vals))
        s2.call_fb(i2, dict(vals))
        assert {o: i1.vars[o] for o in outs} == {o: i2.vars[o] for o in outs}


def test_outside_subset_goes_to_scl(tmp_path: Path) -> None:
    ctu = B.Pou(
        "FB_Ctu",
        "functionBlock",
        B.Fbd(
            [B.Network([B.Out("xQ", B.Box("CTU", inst="fbC", inputs={"CU": B.In("a"), "PV": B.In("3")}, out_pin="Q"))])]
        ),
        [B.V("a", "BOOL", "VAR_INPUT"), B.V("xQ", "BOOL", "VAR_OUTPUT"), B.V("fbC", "CTU")],
    )
    res, _, xml = _emit(tmp_path, ctu)
    assert xml is None
    assert any(f.rule == "C2S7-GFX-SCL" and "CTU" in f.detail for f in res.collector.findings)  # type: ignore[attr-defined]
    ret = B.Pou(
        "FB_Ret",
        "functionBlock",
        B.Ld([B.LdReturn(cond=B.Contact("a")), B.Rung(B.Series(B.Contact("a"), B.Coil("xQ")))]),
        [B.V("a", "BOOL", "VAR_INPUT"), B.V("xQ", "BOOL", "VAR_OUTPUT")],
    )
    res2, _, xml2 = _emit(tmp_path, ret)
    assert xml2 is None
    assert any(f.rule == "C2S7-GFX-SCL" for f in res2.collector.findings)  # type: ignore[attr-defined]
    _res3, _, xml3 = _emit(tmp_path, FBD, tia="V19")
    assert xml3 is not None and validate(xml3, "V19") == [] and "<Namespace/>" not in xml3
