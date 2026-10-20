"""FlgNet V19/V21: свой валидатор (у каждого правила — негатив), XSD (job xsd), обратное чтение, golden.

XSD Siemens в git нет: без `.cache/xsd` тест XSD пропускается, при REQUIRE_XSD=1 (job `xsd` в CI) — падает.
Golden: `tests/golden/tia/*.xml`; пересборка — UPDATE_GOLDEN=1 (отдельным коммитом).
"""

from __future__ import annotations

import copy
import os
import random
import re
from pathlib import Path

import pytest

from c2s7.api import load_input, migrate
from c2s7.convert.core import Options, Result
from c2s7.emit.simaticml.validate import validate
from c2s7.emit.simaticml.xsd import validate_xsd, xsd_dir
from c2s7.model import Pou, Project
from c2s7.sim.interp import Sim
from c2s7.st import nodes as A
from c2s7.verify.s7xml_reader import read_flgnet

REPO = Path(__file__).resolve().parents[2]
SP17 = REPO / "tests" / "fixtures" / "sp17"
GOLDEN = REPO / "tests" / "golden" / "tia"
PROBES = ("FB_ProbeLd.xml", "FB_ProbeFbd.xml")


def run(name: str, tia: str = "V21") -> tuple[Result, Pou, str]:
    proj = load_input(SP17 / name)
    res = migrate(proj, Options(tia=tia))
    assert len(res.simaticml) == 1, [f.rule for f in res.collector.findings]
    return res, proj.pous[0], next(iter(res.simaticml.values()))


@pytest.mark.parametrize("tia", ["V19", "V21"])
@pytest.mark.parametrize("name", PROBES)
def test_probe_pous_pass_validator(name: str, tia: str) -> None:
    res, _, xml = run(name, tia)
    assert validate(xml, tia) == []
    assert f'<Engineering version="{tia}"/>' in xml
    assert ("<Namespace/>" in xml) == (tia == "V21")
    blk = next(b for b in res.blocks if b.flgnet)
    assert blk.flgnet == f"tia/simaticml/{blk.name}.xml"


@pytest.mark.parametrize("tia", ["V19", "V21"])
@pytest.mark.parametrize("name", PROBES)
def test_probe_pous_pass_xsd(name: str, tia: str) -> None:
    if xsd_dir(tia, REPO) is None:
        if os.environ.get("REQUIRE_XSD") == "1":
            pytest.fail("REQUIRE_XSD=1, а XSD нет: python tools/fetch_xsd.py")
        pytest.skip("нет XSD в .cache/xsd (python tools/fetch_xsd.py)")
    _, _, xml = run(name, tia)
    assert validate_xsd(xml, tia, REPO) == []


def test_flgnet_block_not_in_sources(tmp_path: Path) -> None:
    from c2s7.emit.files import source_files

    res, _, _ = run("FB_ProbeLd.xml")
    assert not any("FB_ProbeLd" in p for p, _ in source_files(res))


def test_scl_fallback_outside_subset() -> None:
    proj = load_input(REPO / "tests" / "corpus" / "C2S7-GFX-SCL" / "pos" / "input.xml")
    res = migrate(proj, Options())
    assert res.simaticml == {}
    assert any(f.rule == "C2S7-GFX-SCL" and "SEL" in f.detail for f in res.collector.findings)
    res2 = migrate(load_input(SP17 / "FB_ProbeLd.xml"), Options(graphics="scl"))
    assert res2.simaticml == {}


# ---------------------------------------------------------------- негативы валидатора
def _mut(xml: str, old: str, new: str, count: int = 1) -> str:
    assert old in xml, old
    return xml.replace(old, new, count)


def _ld() -> str:
    return run("FB_ProbeLd.xml")[2]


def _fbd() -> str:
    return run("FB_ProbeFbd.xml")[2]


NEGATIVES = {
    "V-ENG": lambda: _mut(_ld(), 'version="V21"', 'version="V20"'),
    "V-UID": lambda: re.sub(r'<Part Name="Coil" UId="(\d+)"', '<Part Name="Coil" UId="21"', _ld(), count=1),
    "V-REF": lambda: re.sub(r'<IdentCon UId="(\d+)"/>', '<IdentCon UId="999"/>', _ld(), count=1),
    "V-PIN": lambda: _mut(_ld(), 'Name="operand"/>', 'Name="opernd"/>'),
    "V-ONCE": lambda: re.sub(
        r"(<Wire UId=\"\d+\">\s*<Powerrail/>\s*<NameCon UId=\"(\d+)\" Name=\"in\"/>)",
        lambda m: m.group(1) + f'<NameCon UId="{m.group(2)}" Name="in"/>',
        _ld(),
        count=1,
    ),
    "V-PART": lambda: _mut(_ld(), 'Name="SCoil"', 'Name="SuperCoil"'),
    "V-TEMPLATE": lambda: re.sub(
        r'<TemplateValue Name="SrcType" Type="Type">Real</TemplateValue>', "", _fbd(), count=1
    ),
    "V-VERSION": lambda: _mut(_ld(), '<Part Name="Coil"', '<Part Name="Coil" Version="1.0"'),
    "V-REACH": lambda: re.sub(r"<Powerrail/>\s*<NameCon", '<OpenCon UId="998"/><NameCon', _ld(), count=1),
    "V-SCOPE": lambda: _mut(_ld(), 'Scope="LocalVariable"', 'Scope="GlobalVariable"'),
}


@pytest.mark.parametrize("rule", sorted(NEGATIVES))
def test_validator_negative(rule: str) -> None:
    errs = validate(NEGATIVES[rule](), "V21")
    assert any(e.startswith(rule) for e in errs), errs


# ---------------------------------------------------------------- обратное чтение
def _sim_pair(pou: Pou, xml: str) -> tuple[Sim, Sim, Pou]:
    rb = read_flgnet(xml)
    p2 = copy.deepcopy(pou)
    p2.text.body = rb.body
    p2.text.var_blocks.append(A.VarBlock("VAR_TEMP", [], [A.VarDecl(t, A.NamedType("BOOL")) for t in rb.temps]))
    s1 = Sim(Project("src", "st", "src", "-", pous=[pou]))
    s2 = Sim(Project("rd", "st", "rd", "-", pous=[p2]))
    return s1, s2, p2


@pytest.mark.parametrize("name", PROBES)
def test_reader_equivalence_random_cycles(name: str) -> None:
    """NetIR → ST (понижение) и NetIR → FlgNet → reader → ST дают одинаковые выходы и статику."""
    _, pou, xml = run(name)
    s1, s2, _ = _sim_pair(pou, xml)
    i1 = s1.new_instance(s1.pous[pou.name.upper()])
    i2 = s2.new_instance(s2.pous[pou.name.upper()])
    bools = [d.name for b, d in pou.decls() if b.kind == "VAR_INPUT" and getattr(d.type, "name", "") == "BOOL"]
    reals = [d.name for b, d in pou.decls() if b.kind == "VAR_INPUT" and getattr(d.type, "name", "") == "REAL"]
    keep = [d.name.upper() for b, d in pou.decls() if b.kind in ("VAR_OUTPUT", "VAR")]
    rnd = random.Random(20261019)
    for _ in range(400):
        vals: dict[str, object] = {n: rnd.random() < 0.5 for n in bools}
        vals.update({n: rnd.choice([0.0, 1.0, 2.0]) for n in reals})
        s1.call_fb(i1, dict(vals))
        s2.call_fb(i2, dict(vals))
        assert {k: i1.vars[k] for k in keep} == {k: i2.vars[k] for k in keep}


# ---------------------------------------------------------------- golden
@pytest.mark.parametrize("tia", ["V19", "V21"])
@pytest.mark.parametrize("name", PROBES)
def test_golden(name: str, tia: str) -> None:
    _, _, xml = run(name, tia)
    path = GOLDEN / f"{Path(name).stem}.{tia}.xml"
    data = xml.replace("\n", "\r\n").encode("utf-8")
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    assert path.read_bytes() == data, f"golden {path.name} устарел (UPDATE_GOLDEN=1)"
