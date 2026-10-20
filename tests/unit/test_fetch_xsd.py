"""Матрица версий схем SimaticML по листингу dotnetprojects @ bbe5becc (ТЗ M4)."""

from __future__ import annotations

import fetch_xsd as FX


def test_matrix_p0_versions() -> None:
    m = FX.matrix()
    for ver in ("V19", "V21"):
        assert m[ver] == {"interface": "v5", "flgnet": "v5", "scl": "v4", "graph": "v6", "access": "v5"}


def test_matrix_v20_anomaly_and_p1() -> None:
    m = FX.matrix()
    assert m["V20"] == {"interface": "v5", "flgnet": "v4", "scl": "v3", "graph": "v5", "access": "v4"}
    assert m["V15.1"]["flgnet"] == "v3"
    assert m["V17"]["interface"] == "v4+v5"


def test_every_file_pinned() -> None:
    for files in FX.FILES.values():
        for digest in files.values():
            assert len(digest) == 64
