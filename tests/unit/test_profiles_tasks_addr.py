"""Профили CPU/TIA (у каждого значения — источник), матрица XSD, формула приоритетов OB, адреса."""

from __future__ import annotations

from importlib import resources

import fetch_xsd as FX
import pytest
import yaml
from c2s7.convert import addr as AD
from c2s7.convert.tasks import ob_priorities
from c2s7.profiles import ProfileError, load, tia_table


@pytest.mark.parametrize("cpu", ["s7-1200", "s7-1500"])
def test_every_supported_value_has_source(cpu: str) -> None:
    data = yaml.safe_load(resources.files("c2s7.profiles").joinpath(f"{cpu}.yaml").read_text(encoding="utf-8"))
    sources = data["sources"]
    for group in ("languages", "types"):
        for name, info in data[group].items():
            assert "supported" in info, (cpu, name)
            assert info.get("source") in sources, (cpu, name)
            assert sources[info["source"]].startswith("https://"), (cpu, name)
    assert data["ob"]["source"] in sources and data["retain"]["source"] in sources


def test_profile_facts() -> None:
    p12, p15 = load("s7-1200", "V19"), load("s7-1500", "V21")
    assert not p12.language("GRAPH") and not p12.language("STL") and not p12.language("CFC")
    assert p15.language("GRAPH") and p15.language("SCL")
    assert not p12.type_supported("LInt") and p15.type_supported("LInt")
    assert p12.ob["max_cyclic_interrupts"] == 4
    assert p15.namespace("flgnet").endswith("FlgNet/v5")


def test_tia_yaml_matches_xsd_matrix() -> None:
    table = tia_table()["versions"]
    matrix = FX.matrix()
    for ver, row in matrix.items():
        for key, val in row.items():
            assert str(table[ver][key]) == val, (ver, key)


def test_v20_and_unknown_rejected() -> None:
    with pytest.raises(ProfileError, match="V20"):
        load("s7-1500", "V20")
    with pytest.raises(ProfileError):
        load("s7-1200-g2", "V21")


def test_ob_priority_formula() -> None:
    assert ob_priorities([1, 2, 3], 15) == {1: 15, 2: 14, 3: 13}
    assert ob_priorities([0, 0, 5], 15) == {0: 15, 5: 14}
    many = ob_priorities(list(range(20)), 15)
    assert many[0] == 15 and many[19] == 2
    assert len(set(many.values())) < 20  # слияние неизбежно → C2S7-TASK-PRIO-MERGE


@pytest.mark.parametrize(
    ("cds", "s7"),
    [
        ("%IX0.3", "%I0.3"),
        ("%QX1.0", "%Q1.0"),
        ("%IW5", "%IW10"),
        ("%ID2", "%ID8"),
        ("%IB3", "%IB3"),
        ("%MW11", "%MW22"),
        ("%QL1", "%QL8"),
    ],
)
def test_address_byte_mode(cds: str, s7: str) -> None:
    assert AD.to_s7(cds)[0] == s7


def test_address_word_bits_and_overlap() -> None:
    assert AD.to_s7("%IX0.3", "word")[0] is None
    a = [("w", AD.parse("%MW5")), ("x", AD.parse("%MX10.0")), ("b", AD.parse("%MB10"))]
    assert AD.overlaps([(n, x) for n, x in a if x]) == {"w", "x", "b"}
    same = [("a", AD.parse("%MW5")), ("i", AD.parse("%MW5"))]
    assert AD.overlaps([(n, x) for n, x in same if x]) == set()
    bitbyte = [("x", AD.parse("%MX10.0")), ("b", AD.parse("%MB10"))]
    assert AD.overlaps([(n, x) for n, x in bitbyte if x]) == set()
