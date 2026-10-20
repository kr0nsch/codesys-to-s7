"""Генератор PLCopen корпуса: формы, которые CODESYS 3.5.17.30 принял на пробе M0."""

from __future__ import annotations

import builder as B
import probe_specs as PS
from lxml import etree

NS = {"p": B.NS}


def _xml(pou: B.Pou) -> etree._Element:
    return etree.fromstring(B.project_xml(B.Case(pou.name, pous=[pou])).encode("utf-8"))


def test_project_is_wellformed_and_deterministic() -> None:
    case = PS.probe_case()
    a = B.pretty(B.project_xml(case))
    b = B.pretty(B.project_xml(case))
    assert a == b
    assert a.startswith("﻿<?xml")
    root = etree.fromstring(a.lstrip("﻿").split("\n", 1)[1].encode("utf-8"))
    names = [p.get("name") for p in root.iterfind(".//p:pou", NS)]
    assert "FB_ProbeLd" in names and "PRG_ProbeSfc" in names


def test_ld_single_left_rail_and_network_titles() -> None:
    root = _xml(PS.LD_POU)
    rails = root.findall(".//p:leftPowerRail", NS)
    assert [r.get("localId") for r in rails] == ["0"]
    titles = [
        v for v in root.iterfind(".//p:vendorElement", NS) if "networktitle" in etree.tostring(v, encoding="unicode")
    ]
    assert len(titles) == len(PS.LD_POU.body.networks)  # type: ignore[union-attr]
    edges = {c.get("edge") for c in root.iterfind(".//p:contact", NS)}
    assert {"rising", "falling", "none"} <= edges
    storages = {c.get("storage") for c in root.iterfind(".//p:coil", NS)}
    assert {"set", "reset", "none"} <= storages


def test_fbd_negated_jump_uses_not_block() -> None:
    root = _xml(PS.FBD_POU)
    jump = root.find(".//p:jump", NS)
    assert jump is not None and jump.get("negated") is None
    ref = jump.find(".//p:connection", NS)
    assert ref is not None
    src = root.find(f".//p:block[@localId='{ref.get('refLocalId')}']", NS)
    assert src is not None and src.get("typeName") == "NOT"
    neg = [v for v in root.iterfind(".//p:inputVariables/p:variable", NS) if v.get("negated") == "true"]
    assert neg, "отрицание входа блока AND"


def test_fbd_networks_by_localid_stride() -> None:
    root = _xml(PS.FBD_POU)
    nets = {int(e.get("localId")) // B.NET_STRIDE for e in root.iterfind(".//p:FBD/*", NS)}
    assert nets == {1, 2, 3, 4}


def test_cfc_wires_go_through_connectors() -> None:
    root = _xml(PS.CFC_POU)
    cfc = root.find(".//p:CFC", NS)
    assert cfc is not None
    by_id = {e.get("localId"): e for e in cfc}
    for blk in cfc.iterfind("p:block", NS):
        assert blk.get("executionOrderId")
        for var in blk.iterfind("p:inputVariables/p:variable", NS):
            conn = var.find(".//p:connection", NS)
            assert conn is not None and conn.get("formalParameter") is None
            assert by_id[conn.get("refLocalId")].tag.endswith("connector")
    formals = {c.get("formalParameter") for c in cfc.iterfind("p:connector/p:connectionPointIn/p:connection", NS)}
    assert "" in formals  # выход оператора
    assert "rIn" in formals  # выражение входной переменной


def test_sfc_step_action_and_qualifiers() -> None:
    root = _xml(PS.SFC_POU)
    quals = {a.get("qualifier") for a in root.iterfind(".//p:action", NS) if a.get("qualifier")}
    assert quals == {"N", "S", "R", "P"}
    attrs = [a.text for a in root.iter("attribute") if a.get("guid") == B.SFC_STEP_ACTION]
    assert attrs == ["ActInit"]
    assert root.find(".//p:selectionDivergence", NS) is not None
    assert root.find(".//p:simultaneousConvergence", NS) is not None
    assert root.find(".//p:jumpStep", NS).get("targetName") == "Init"  # type: ignore[union-attr]


def test_gvl_mixed_retain_persistent() -> None:
    xml = B.project_xml(B.Case("g", gvls=[PS.GVL]))
    root = etree.fromstring(xml.encode("utf-8"))
    mixed = root.findall(".//p:MixedAttrsVarList/p:globalVars", NS)
    assert {(g.get("retain"), g.get("persistent")) for g in mixed} == {(None, None), ("true", None), ("true", "true")}
    # GVL с PERSISTENT — без interfaceasplaintext (иначе CODESYS делает из него Persistent Variables)
    assert "interfaceasplaintext" not in xml


def test_type_xml() -> None:
    assert B.type_xml("BOOL") == "<BOOL />"
    assert B.type_xml("STRING(20)") == '<string length="20" />'
    assert B.type_xml("ARRAY[0..3] OF INT").startswith('<array><dimension lower="0" upper="3" />')
    assert B.type_xml("TON") == '<derived name="TON" />'
    assert B.type_xml("TIME_OF_DAY") == "<TOD />"
