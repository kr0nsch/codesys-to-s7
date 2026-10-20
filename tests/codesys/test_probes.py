"""Пробы M0 в CODESYS 3.5.17.30 и Control Win (`pytest -m codesys`, локально).

Повторяют tools/probes/run_probes.py и tools/probes/controlwin_probe.py и проверяют выводы,
записанные в docs/PROBES.md. Без CODESYS — skip; рантайм занят — skip «runtime busy».
"""

from __future__ import annotations

import json

import cdsrun
import pytest

pytestmark = [pytest.mark.codesys, pytest.mark.skipif(not cdsrun.available(), reason="CODESYS 3.5.17.30 не найден")]


def test_import_per_language(repo) -> None:  # type: ignore[no-untyped-def]
    import run_probes

    assert run_probes.cmd_import() in (0, 1)
    res = json.loads((repo / "build" / "probes" / "import.json").read_text(encoding="utf-8"))
    created = {i["name"]: i["created"] for i in res["imports"]}
    for name in (
        "FB_ProbeSt",
        "FB_ProbeFbd",
        "FB_ProbeLd",
        "FB_ProbeCfc",
        "FB_ProbePcfc",
        "PRG_ProbeSfc",
        "FB_ProbeOop2",
    ):
        assert name in created[name], name
    assert created["FB_ProbeIl"] == []  # IL = N: стандартный <IL> молча пропускается
    bad = {m["object"] for m in res["build"]["messages"] if m["severity"] == "Error"}
    # ошибки только от POU, которые не импортировались (IL) или сломались (EN/ENO), и от PRG_ProbeMain
    assert bad <= {"PRG_ProbeMain"}, bad


def test_controlwin_behaviour(repo) -> None:  # type: ignore[no-untyped-def]
    import controlwin_probe

    import online

    try:
        code = controlwin_probe.main()
    except online.RuntimeBusy as exc:  # pragma: no cover
        pytest.skip(f"runtime busy: {exc}")
    if code == 3:
        pytest.skip("runtime busy")
    res = json.loads((repo / "build" / "probes" / "controlwin.json").read_text(encoding="utf-8"))
    v = res["values"]
    assert v["PRG_M0.iR25"] == "INT#3" and v["PRG_M0.iRm25"] == "INT#-3"
    assert v["PRG_M0.xSrQ"] == "TRUE" and v["PRG_M0.xRsQ"] == "FALSE"
    assert v["PRG_M0.wCtuCv"] == "WORD#65535" and v["PRG_M0.wCtdCv"] == "WORD#0"
    assert v["PRG_M0.iLim"] == "INT#0"
    assert v["PRG_M0.iO2"] == "INT#7"
    assert v["PRG_M0.xFtFirst"] == "FALSE"
    assert v["GVL_M0.xBit10"] == "TRUE"
